"""Figure 1 for GEE_flooding only: observation coverage and label uncertainty.

Panels: (a) GF10 news reporting, (b) geocoding selection, (c) annual
availability, (d) GFID source-family candidate overlap, (e) official UCDB
city eligibility and pre-declared train/held-out sample. This is NOT the
Nature Cities Global_flooding Figure 1.

Never downloads anything, never edits source files, never treats GFID
representative point or Groundsource polygon as a flooded footprint.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from .paths import safe_output, atomic_json

QUALITY=("HIGH_GEOCODE_SPECIFICITY","MEDIUM_GEOCODE_SPECIFICITY",
         "LOW_GEOCODE_SPECIFICITY")
UCDB_LAYER="GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A"
SOURCE_MAP={"DFO":"DFO","DESINVENTAR":"DESINVENTAR",
            "EM-DAT":"EMDAT","EMDAT":"EMDAT","HANZE":"HANZE"}

def check_label_contract(labels,qc,grid):
    if qc.get("status")!="PASS_LABEL_GEOCODE_AUDIT":
        raise ValueError("Upstream label QC did not PASS")
    n=int(qc["rows_processed"])
    statuses=qc["count_by_status"];qualities=qc["count_by_quality"]
    if sum(int(x) for x in statuses.values())!=n or sum(int(x) for x in qualities.values())!=n:
        raise ValueError("Upstream label counts do not reconcile")
    if sum(int(qualities.get(q,0)) for q in QUALITY)!=int(statuses.get("MATCHED",0)):
        raise ValueError("Matched count != three localization classes")
    if len(labels)!=int(statuses["MATCHED"]):raise ValueError("Primary label rows disagree with QC")
    if labels.event_id.duplicated().any():raise ValueError("Primary event UUID is not unique")
    if not set(labels.geocode_quality.unique()).issubset(set(QUALITY)):
        raise ValueError("Unexpected geocode quality value")
    if not set(labels.grid_id).issubset(set(grid.grid_id)):
        raise ValueError("Some labels are outside frozen GF10 grid")
    if grid.grid_id.duplicated().any():raise ValueError("Frozen grid IDs are duplicated")
    return n

def load_ucdb(gpkg,layer=UCDB_LAYER):
    import geopandas as gpd
    import pyogrio
    if not Path(gpkg).is_file():raise FileNotFoundError(gpkg)
    available=[x[0] for x in pyogrio.list_layers(gpkg)]
    if layer not in available:raise ValueError("UCDB layer missing; available: "+str(available))
    fields=[str(x).lstrip("\ufeff") for x in pyogrio.read_info(gpkg,layer=layer)["fields"]]
    idcol=next((f for f in ("ID_UC_G0","ID_UC","city_id") if f in fields),None)
    if not idcol:raise ValueError("Official UCDB city ID not found; fields="+str(fields[:40]))
    # columns filter: do not read UCDB thousands of unused attributes
    cities=gpd.read_file(gpkg,layer=layer,columns=[idcol],engine="pyogrio")
    cities.columns=[str(x).lstrip("\ufeff") for x in cities.columns]
    if cities.crs is None:raise ValueError("UCDB has missing CRS")
    cities=cities.rename(columns={idcol:"city_id"})
    cities["city_id"]=cities.city_id.astype("string")
    cities=cities.loc[cities.geometry.notna()&~cities.geometry.is_empty].copy()
    cities.geometry=cities.geometry.make_valid()
    if cities.city_id.duplicated().any():
        cities=cities.dissolve(by="city_id",as_index=False)
    return cities.to_crs("EPSG:6933")[["city_id","geometry"]]

def assign_dominant_city(grid,cities,crosswalk=None):
    import geopandas as gpd
    import shapely
    if crosswalk is not None:
        d=pd.read_parquet(crosswalk,columns=["grid_id","city_id"])
        if d.grid_id.duplicated().any():raise ValueError("Existing crosswalk has duplicate grid IDs")
        if not set(d.grid_id).issubset(set(grid.grid_id)):
            raise ValueError("Old crosswalk is not aligned with NEW frozen grid")
        if not set(d.city_id.astype(str)).issubset(set(cities.city_id.astype(str))):
            raise ValueError("Crosswalk has unknown official UCDB city IDs")
        return d.assign(city_id=d.city_id.astype(str))
    out=[];cgeom=cities.geometry.to_numpy()
    for a in range(0,len(grid),20000):
        part=grid.iloc[a:a+20000]
        geom=shapely.box(part.grid_x.to_numpy()*10000,
                         part.grid_y.to_numpy()*10000,
                        (part.grid_x.to_numpy()+1)*10000,
                        (part.grid_y.to_numpy()+1)*10000)
        ge=gpd.GeoDataFrame(part[["grid_id"]].copy(),
                             geometry=gpd.GeoSeries(geom,crs="EPSG:6933",index=part.index),
                             crs="EPSG:6933")
        hits=gpd.sjoin(ge,cities,how="inner",predicate="intersects")
        if len(hits)==0:continue
        candidate=cgeom[hits.index_right.to_numpy()]
        overlap=shapely.area(shapely.intersection(hits.geometry.to_numpy(),candidate))
        hits["intersection_m2"]=overlap
        hits=hits.loc[hits.intersection_m2.gt(0)]
        hits=hits.sort_values(["grid_id","intersection_m2","city_id"],
                              ascending=[True,False,True]).drop_duplicates("grid_id")
        out.append(hits[["grid_id","city_id"]])
    if not out:raise ValueError("Zero intersections between UCDB and frozen GF10")
    result=pd.concat(out,ignore_index=True)
    if result.grid_id.duplicated().any():raise ValueError("Dominant city not unique by grid")
    return result

def city_profiles(cities,world=None,koppen=None):
    import geopandas as gpd
    from pyproj import Transformer
    c=cities.copy()
    c.geometry=c.geometry.representative_point()
    c=c.to_crs("EPSG:4326")
    c["lon"]=c.geometry.x;c["lat"]=c.geometry.y
    c["continent"]="Unknown";c["country"]="Unknown"
    if world:
        w=gpd.read_file(world).to_crs("EPSG:4326")
        continent=next((x for x in ("CONTINENT","continent") if x in w),None)
        country=next((x for x in ("ADMIN","NAME_EN","NAME","country") if x in w),None)
        if not continent or not country:raise ValueError("World borders missing continent/country fields")
        joined=gpd.sjoin(c[["city_id","geometry"]],
                        w[[continent,country,"geometry"]],how="left",predicate="within")
        joined=joined.drop_duplicates("city_id")
        geo=joined[["city_id",continent,country]].rename(columns={
            continent:"world_continent",country:"world_country"})
        c=c.merge(geo,on="city_id",how="left",validate="one_to_one")
        c["continent"]=c.world_continent.fillna("Unknown")
        c["country"]=c.world_country.fillna("Unknown")
        c=c.drop(columns=["world_continent","world_country"])
    c["koppen_broad"]="Unknown"
    if koppen:
        import rasterio
        with rasterio.open(koppen) as ds:
            if ds.crs is None or ds.count!=1:raise ValueError("Invalid Köppen raster")
            trans=Transformer.from_crs(4326,ds.crs,always_xy=True)
            x,y=trans.transform(c.lon.to_numpy(),c.lat.to_numpy())
            raw=list(ds.sample(zip(x,y),masked=True))
        code=np.ma.filled(np.ma.array(raw).ravel(),0).astype(int)
        c["koppen_broad"]=np.select([
            (code>=1)&(code<=3),(code>=4)&(code<=7),
            (code>=8)&(code<=16),(code>=17)&(code<=28),
            (code>=29)&(code<=30)],
            ["Tropical","Arid","Temperate","Cold","Polar"],default="Unknown")
    return c.drop(columns="geometry")

def read_gfid(path):
    """GFID source-family catalogue, NOT independent on-ground flood verification."""
    df=pd.read_excel(path,sheet_name="Aggregated",engine="openpyxl")
    names={re.sub(r"[^a-z0-9]","",str(x).lower()):x for x in df.columns}
    def col(*candidates):
        return next((names[x] for x in candidates if x in names),None)
    src=col("source");lat=col("lat","latitude");lon=col("lon","longitude")
    a=col("startdate","date");b=col("enddate")
    if not all((src,lat,lon,a)):
        raise ValueError("GFID Aggregated sheet lacks Source/Start Date/Lat/Lon; got "+str(df.columns.tolist()))
    def dates(s):
        txt=s.astype("string").str.strip()
        partial=txt.str.fullmatch(r"\d{4}(?:-\d{2})?",na=False)
        dt=pd.to_datetime(s,errors="coerce",format="mixed")
        return dt.dt.normalize().mask(partial)
    start=dates(df[a]);end=dates(df[b]) if b else start.copy()
    end=end.fillna(start) if b is None else end
    family=df[src].astype("string").str.upper().str.strip().str.replace(" ","",regex=False).map(SOURCE_MAP)
    la=pd.to_numeric(df[lat],errors="coerce")
    lo=pd.to_numeric(df[lon],errors="coerce")
    valid=start.notna()&end.notna()&(end>=start)&la.between(-90,90)&lo.between(-180,180)&family.notna()
    out=pd.DataFrame({"family":family[valid].astype(str),
                      "start":start[valid],"end":end[valid],
                      "lon":lo[valid].astype(float),"lat":la[valid].astype(float)})
    if out.empty:raise ValueError("Zero usable dated GFID records")
    diag={"raw_gfid_rows":len(df),"usable_gfid_records":len(out),
          "unusable_or_unknown_source":int((~valid).sum()),
          "source_families":out.family.value_counts().to_dict(),
          "lineage":"GFID combines DFO, DesInventar, EM-DAT and HANZE; not independent four ground truths"}
    return out.reset_index(drop=True),diag

def xyz(lon,lat):
    lon=np.deg2rad(np.asarray(lon,dtype=float))
    lat=np.deg2rad(np.asarray(lat,dtype=float))
    return np.stack([np.cos(lat)*np.cos(lon),
                     np.cos(lat)*np.sin(lon),np.sin(lat)],axis=1)

def candidate_catalogue_overlap(news,external,radius_km=75.,days=7):
    """Conservative time AND distance candidate screen of grid-centred news.
    Returns one row per matched grid-day and *source family*, never a flood truth.
    """
    from scipy.spatial import cKDTree
    if not (0<radius_km<=150 and 0<=days<=30):
        raise ValueError("Invalid candidate search radius or day window")
    news=news.copy()
    news["date"]=pd.to_datetime(news.date)
    ext=external.copy()
    ext["start"]=pd.to_datetime(ext.start);ext["end"]=pd.to_datetime(ext.end)
    r=2*np.sin((radius_km/6371.0088)/2)
    results=[]
    for month,n in news.groupby(news.date.dt.to_period("M"),sort=True):
        first=month.to_timestamp();last=(month+1).to_timestamp()-pd.Timedelta(days=1)
        ref=ext[(ext.start<=last+pd.Timedelta(days=days))&
                (ext.end>=first-pd.Timedelta(days=days))]
        if ref.empty:continue
        tree=cKDTree(xyz(ref.lon,ref.lat))
        neighbours=tree.query_ball_point(xyz(n.lon,n.lat),r=r)
        b=ref.reset_index(drop=True)
        left=b.start.to_numpy(dtype="datetime64[D]")
        right=b.end.to_numpy(dtype="datetime64[D]")
        ndays=n.date.to_numpy(dtype="datetime64[D]")
        for j,hits in enumerate(neighbours):
            if not hits:continue
            t=ndays[j];matched=set()
            for h in hits:
                if left[h]-np.timedelta64(days,"D")<=t<=right[h]+np.timedelta64(days,"D"):
                    matched.add(str(b.family.iat[h]))
            if matched:
                item=n.iloc[j]
                for family in sorted(matched):
                    results.append((str(item.grid_id),pd.Timestamp(item.date),family,
                                    int(item.news_count)))
    return pd.DataFrame(results,columns=["grid_id","date","family","news_count"])

def stable_city_split(city):
    """Predeclare candidate holdout independent of any ML score or validation."""
    c=city.copy()
    c["study_status"]="EVIDENCE_SPARSE"
    eligible=c.eligible
    for _,segment in c[eligible].groupby(["continent","koppen_broad"],dropna=False):
        ordered=sorted(segment.index,key=lambda i:hashlib.sha256(
            str(c.at[i,"city_id"]).encode()).hexdigest())
        nt=max(1,int(round(len(ordered)*.20))) if len(ordered)>=5 else 0
        c.loc[ordered,"study_status"]="TRAIN_CANDIDATE"
        c.loc[ordered[:nt],"study_status"]="HELDOUT_CITY_CANDIDATE"
    return c

def plot_figure(grid,news,annual,city,source,out,world=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family":"DejaVu Sans","pdf.fonttype":42,"font.size":9})
    fig=plt.figure(figsize=(17,11.4),layout="constrained")
    gs=fig.add_gridspec(2,3,height_ratios=[1,1],width_ratios=[1.1,1.1,1.0])
    aa=fig.add_subplot(gs[0,0]);bb=fig.add_subplot(gs[0,1])
    cc=fig.add_subplot(gs[0,2]);dd=fig.add_subplot(gs[1,0])
    ee=fig.add_subplot(gs[1,1:])
    borders=None
    if world:
        import geopandas as gpd
        borders=gpd.read_file(world).to_crs(4326)
    def base(ax):
        if borders is not None:
            borders.plot(ax=ax,facecolor="#F4F5F6",edgecolor="#BBC4C9",
                         linewidth=.25,zorder=0)
        ax.set_xlim(-180,180);ax.set_ylim(-58,83)
        ax.set_xlabel("Longitude");ax.set_ylabel("Latitude")
        ax.grid(alpha=.1)
    base(aa)
    h=aa.hexbin(news.lon,news.lat,C=news.news_count,reduce_C_function=np.sum,
                gridsize=(100,45),extent=(-180,180,-58,83),mincnt=1,
                cmap="inferno",norm=LogNorm(),alpha=.91)
    fig.colorbar(h,ax=aa,shrink=.65,pad=.01,label="High-specificity report UUIDs per display hexagon")
    aa.set_title("a  Global news observation coverage",loc="left",weight="bold")
    # b: account for all original rows and mapped quality classes.
    labels=["HIGH geocode","MEDIUM geocode","LOW geocode","Not eligible"]
    values=[int(source["quality"].get(k,0)) for k in QUALITY]+[
        int(source["raw_records"]-source["mapped_records"])]
    bb.barh(labels[::-1],np.array(values[::-1])/1e6,
            color=["#ADB8C2","#CDB388","#79AFA9","#287B76"])
    bb.set_xlabel("Groundsource UUID records (millions)")
    bb.set_title("b  Raw-to-grid localization audit",loc="left",weight="bold")
    for i,n in enumerate(values[::-1]):
        bb.text(n/1e6+max(values)/1e6*.015,i,f"{n:,}",va="center",fontsize=8)
    bb.set_xlim(0,max(values)/1e6*1.25)
    aa.grid(alpha=.12);bb.grid(axis="x",alpha=.1)
    # c: annual reporting not flood-incidence trends
    plot=annual.pivot_table(index="year",columns="quality",values="news_rows",
                            fill_value=0).sort_index()
    palette={QUALITY[0]:"#287B76",QUALITY[1]:"#C49B61",QUALITY[2]:"#8492A6"}
    for q in QUALITY:
        if q in plot.columns:cc.plot(plot.index,plot[q]/1000,label=q.split("_")[0],lw=1.8,color=palette[q])
    cc.legend(frameon=False,fontsize=8)
    cc.set(xlabel="Year",ylabel="Recorded news UUIDs (thousands)")
    cc.set_title("c  Availability, not true incidence",loc="left",weight="bold")
    cc.grid(alpha=.13)
    dd.set_title("d  External archive candidate concordance",loc="left",weight="bold")
    if source["external_status"]=="AVAILABLE":
        x=source["external_family_grid_days"]
        keys=sorted(x)
        dd.barh(keys,[x[k] for k in keys],color="#5888A5")
        dd.set_xlabel("GF10 grid-days near GFID events")
        dd.text(.01,.02,"DFO is also included in GFID; overlap is not independent ground truth",
                transform=dd.transAxes,fontsize=8,va="bottom")
    else:
        dd.axis("off");dd.text(.04,.60,"External catalogue: NOT YET ANALYSED",
                              transform=dd.transAxes,fontsize=11)
        dd.text(.04,.45,"No zero-match or physical-accuracy claim",
                transform=dd.transAxes,fontsize=9)
    ee.set_title("e  Official UCDB city sample status (pre-model)",loc="left",weight="bold")
    base(ee)
    colors={"EVIDENCE_SPARSE":"#B0B8BD","TRAIN_CANDIDATE":"#2D8191",
            "HELDOUT_CITY_CANDIDATE":"#D98B39"}
    for status,color in colors.items():
        sel=city[city.study_status.eq(status)]
        if len(sel):
            ee.scatter(sel.lon,sel.lat,s=3.0 if status=="EVIDENCE_SPARSE" else 7.,
                       color=color,alpha=.65 if status=="EVIDENCE_SPARSE" else .85,
                       rasterized=True,zorder=3)
    ee.legend(handles=[Line2D([0],[0],marker="o",color="w",markerfacecolor=v,
                               markersize=7,label=k.replace("_"," ").title())
                       for k,v in colors.items()],loc="lower left",fontsize=8,frameon=True)
    subtitle=("Catalogue candidates only; PHYSICAL VALIDATION PENDING"
              if not source["physical_validated"] else
              "Physical evidence subset supplied; check external QA")
    fig.suptitle("Figure 1 | Global urban flood-report coverage and study eligibility",
                 fontweight="bold",fontsize=16)
    fig.text(.5,.002,
             "Groundsource polygons are geocoded place extents, not flood footprints. "
             "No-report ≠ no-flood. "+subtitle,ha="center",fontsize=9)
    fig.savefig(out/"Figure1_GEE_observation.png",dpi=300,bbox_inches="tight")
    fig.savefig(out/"Figure1_GEE_observation.pdf",bbox_inches="tight")
    plt.close(fig)

def build(root,grid_path,labels_path,qc_path,ucdb,tag="fig1_v1",
          crosswalk=None,koppen=None,gfid=None,world=None,physical=None,
          city_min_reports=5,city_min_years=3):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",tag):
        raise ValueError("Output tag must be a simple folder name")
    if city_min_reports<1 or city_min_years<1:raise ValueError("Invalid city eligibility thresholds")
    out=safe_output(root,"outputs/"+tag)
    if out.exists():raise FileExistsError("Version already exists; use another --tag: "+str(out))
    required=[grid_path,labels_path,qc_path,ucdb]
    required.extend(x for x in [crosswalk,koppen,gfid,world,physical] if x)
    for p in required:
        if not Path(p).is_file():raise FileNotFoundError(p)
    qc=json.loads(Path(qc_path).read_text(encoding="utf-8"))
    grid=pd.read_parquet(grid_path)
    needed={"grid_id","grid_x","grid_y","longitude","latitude"}
    if needed-set(grid):raise ValueError("GF10 missing "+str(needed-set(grid)))
    primary=pd.read_parquet(labels_path,
                            columns=["event_id","grid_id","date","geocode_quality"])
    primary["date"]=pd.to_datetime(primary.date,errors="raise").dt.normalize()
    raw_n=check_label_contract(primary,qc,grid)
    print("[FIG1] labels and frozen GF10 verified",len(primary),len(grid),flush=True)
    annual=(primary.assign(year=primary.date.dt.year)
            .groupby(["year","geocode_quality"]).agg(news_rows=("event_id","size"),
                unique_grid_days=("grid_id",lambda x:0)).reset_index()
            .drop(columns="unique_grid_days").rename(columns={"geocode_quality":"quality"}))
    gd=primary.groupby(["grid_id","date","geocode_quality"]).size().rename("n").reset_index()
    distinct=primary.groupby(["grid_id","date"]).size().rename("news_count").reset_index()
    high=(primary[primary.geocode_quality.eq(QUALITY[0])]
          .groupby(["grid_id","date"]).size().rename("news_count").reset_index())
    if len(primary)!=int(gd.n.sum()) or len(distinct)>len(primary):
        raise ValueError("Unique grid-day audit failed")
    cities=load_ucdb(ucdb)
    dom=assign_dominant_city(grid,cities,crosswalk)
    if not set(dom.city_id.astype(str)).issubset(set(cities.city_id.astype(str))):
        raise ValueError("Dominant city IDs do not match UCDB official IDs")
    loc=city_profiles(cities,world=world,koppen=koppen)
    dom["city_id"]=dom.city_id.astype(str)
    report_city=(primary[primary.geocode_quality.eq(QUALITY[0])]
                 .merge(dom,on="grid_id",how="inner",validate="many_to_one"))
    stats=report_city.groupby("city_id").agg(n_high_reports=("event_id","nunique"),
                     n_report_years=("date",lambda x:x.dt.year.nunique())).reset_index()
    loc["city_id"]=loc.city_id.astype(str)
    loc=loc.merge(stats,on="city_id",how="left",validate="one_to_one")
    loc["n_high_reports"]=loc.n_high_reports.fillna(0).astype(int)
    loc["n_report_years"]=loc.n_report_years.fillna(0).astype(int)
    loc["eligible"]=(loc.n_high_reports>=city_min_reports)&(loc.n_report_years>=city_min_years)
    loc=stable_city_split(loc)
    # Retain every primary mapped UUID, including cells outside the official
    # UCDB reference: do not silently discard the 2020 GF10 / UCDB mismatch.
    geo=primary.merge(dom,on="grid_id",how="left",validate="many_to_one")
    geo=geo.merge(loc[["city_id","continent","country","koppen_broad"]],
                  on="city_id",how="left",validate="many_to_one")
    geo["continent"]=geo.continent.fillna("Not assigned to UCDB")
    geo["country"]=geo.country.fillna("Not assigned to UCDB")
    geo["year"]=geo.date.dt.year
    region_quality=(geo.groupby(["continent","geocode_quality"],dropna=False)
                    .agg(report_uuids=("event_id","nunique"),
                         distinct_grid_cells=("grid_id","nunique"),
                         assigned_ucdb_cities=("city_id","nunique")).reset_index())
    regional_year=(geo.groupby(["continent","year","geocode_quality"],dropna=False)
                   .agg(report_uuids=("event_id","nunique")).reset_index())
    city_strata=(loc.groupby(["continent","koppen_broad"],dropna=False)
                .agg(official_ucdb_cities=("city_id","size"),
                     eligible_cities=("eligible","sum")).reset_index())
    city_strata["eligibility_share"]=city_strata.eligible_cities/city_strata.official_ucdb_cities
    hi=high.merge(grid[["grid_id","longitude","latitude"]],
                 on="grid_id",validate="many_to_one").rename(
                     columns={"longitude":"lon","latitude":"lat"})
    external="NOT_AVAILABLE";source_counts={};match=None;gfdiag={}
    if gfid:
        refs,gfdiag=read_gfid(gfid)
        match=candidate_catalogue_overlap(hi,refs)
        source_counts=match.groupby("family")[["grid_id"]].size().astype(int).to_dict()
        external="AVAILABLE"
        print("[FIG1] GFID source family candidate overlaps",source_counts,flush=True)
    physical_info={"status":"NOT_AVAILABLE"}
    if physical:
        # A supplied dataset must be an existing independently validated TABLE.
        # Do not interpret unobserved pixels as verified flood-free.
        df=pd.read_csv(physical)
        need={"grid_id","date","sensor","valid_observation","flood_observed"}
        if need-set(df):raise ValueError("Physical evidence missing "+str(need-set(df)))
        if not df["valid_observation"].isin([0,1,True,False]).all():
            raise ValueError("Invalid physical-observation availability flag")
        if not df["flood_observed"].isin([0,1,True,False]).all():
            raise ValueError("Invalid physical-flood observation flag")
        if (df.flood_observed.astype(bool)&~df.valid_observation.astype(bool)).any():
            raise ValueError("Flood observed without valid observation")
        physical_info={"status":"EXTERNAL_TABLE_REQUIRES_MANUAL_INDEPENDENCE_AUDIT",
                       "observed_valid_rows":int(df.valid_observation.sum()),
                       "observed_flood_rows":int(df.flood_observed.sum()),
                       "sensor_types":df.sensor.astype(str).value_counts().to_dict()}
    out.mkdir(parents=True,exist_ok=False)
    annual.to_csv(out/"fig1_annual_quality.csv",index=False)
    city_strata.to_csv(out/"fig1_city_strata.csv",index=False)
    region_quality.to_csv(out/"fig1_regional_geocode_quality.csv",index=False)
    regional_year.to_csv(out/"fig1_regional_annual_quality.csv",index=False)
    loc.to_csv(out/"fig1_ucdb_city_sample_audit.csv",index=False)
    dom.to_parquet(out/"fig1_grid_dominant_ucdb.parquet",index=False)
    gd.to_parquet(out/"fig1_grid_day_by_quality.parquet",index=False)
    if match is not None:match.to_parquet(out/"fig1_gfid_candidate_concordance.parquet",index=False)
    qcout={"status":"DRAFT_NEEDS_INDEPENDENT_PHYSICAL_VALIDATION",
           "raw_groundsource_rows":raw_n,
           "mapped_geocoded_reports":len(primary),
           "high_reports":int(primary.geocode_quality.eq(QUALITY[0]).sum()),
           "all_distinct_grid_days":len(distinct),
           "high_distinct_grid_days":len(high),
           "gf10_urban_grid_cells":len(grid),
           "ucdb_official_cities":len(loc),
           "ucdb_cities_with_high_report":int(loc.n_high_reports.gt(0).sum()),
           "eligible_cities":int(loc.eligible.sum()),
           "train_candidate_cities":int(loc.study_status.eq("TRAIN_CANDIDATE").sum()),
           "heldout_candidate_cities":int(loc.study_status.eq("HELDOUT_CITY_CANDIDATE").sum()),
           "unassigned_primary_high_reports":int(primary.geocode_quality.eq(QUALITY[0]).sum()-len(report_city)),
           "climate_stratum_available":bool(koppen),
           "continent_stratum_available":bool(world),
           "gfid_catalogue_status":external,
           "gfid_candidate_grid_days_by_source_family":source_counts,
           "gfid_diagnostics":gfdiag,
           "physical_independent_validation":physical_info,
           "sources":{name:str(path) if path else None for name,path in
                      [("grid",grid_path),("labels",labels_path),("qc",qc_path),
                       ("ucdb",ucdb),("crosswalk",crosswalk),("koppen",koppen),
                       ("world",world),("gfid",gfid),("physical",physical)]},
           "cautions":["News UUID != independent physical flood occurrence or storm",
                       "GFID representative coordinate and Groundsource grid center are NOT flood footprints",
                       "DFO and GFID-DFO share data lineage; candidate overlaps do NOT validate true pluvial floods",
                       "Unreported is UNLABELED, not confirmed nonflood",
                       "Study training/holdout cities are candidates, not performance-validated regions"]}
    summary={"quality":qc["count_by_quality"],"raw_records":raw_n,
             "mapped_records":len(primary),"external_status":external,
             "external_family_grid_days":source_counts,
             "physical_validated":bool(physical)}
    plot_figure(grid,hi,annual,loc,summary,out,world=world)
    atomic_json(out/"fig1_qc_and_provenance.json",qcout)
    return qcout
