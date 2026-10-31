"""Five-panel paper-facing Figure 1 and hard publication-readiness contract.

Uses only locally existing GF10, raw-groundsource derived A/B/C labels, official
UCDB city audit, and independently reviewed physical supports. Never creates
meteorological storm counts from news UUIDs or candidate episode clusters.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json

STATES=("TRAIN_CANDIDATE","HELDOUT_CITY_CANDIDATE","EVIDENCE_SPARSE")

def city_attributes(city,crosswalk,labels,city_pop=None):
    c=city.copy()
    c["city_id"]=c.city_id.astype(str)
    x=crosswalk[["grid_id","city_id"]].copy()
    x["city_id"]=x.city_id.astype(str)
    if x.grid_id.duplicated().any():raise ValueError("Dominant crosswalk not one-to-one for each grid")
    report=labels.merge(x,on="grid_id",how="left",validate="many_to_one")
    report["year"]=pd.to_datetime(report.date).dt.year
    counts=(report.dropna(subset=["city_id"]).groupby("city_id")
            .agg(raw_uuid_count=("event_id","nunique"),
                 annual_coverage=("year","nunique"),
                 A_count=("spatial_temporal_tier",lambda z:int((z=="A").sum())),
                 B_count=("spatial_temporal_tier",lambda z:int((z=="B").sum())),
                 C_count=("spatial_temporal_tier",lambda z:int((z=="C").sum()))).reset_index())
    c=c.merge(counts,on="city_id",how="left",validate="one_to_one")
    for f in ("raw_uuid_count","annual_coverage","A_count","B_count","C_count"):
        c[f]=c[f].fillna(0).astype(int)
    c["population_2020"]=np.nan
    if city_pop is not None:
        pop=pd.read_csv(city_pop,dtype={"city_id":str})
        if not {"city_id","population_2020"}.issubset(pop):
            raise ValueError("Population input must have city_id, population_2020")
        if pop.city_id.duplicated().any():raise ValueError("Duplicate population UCDB IDs")
        p=pop.set_index("city_id").population_2020
        c["population_2020"]=pd.to_numeric(c.city_id.map(p),errors="coerce")
        if (c.population_2020.dropna()<0).any():raise ValueError("Negative population")
    c["population_class"]=pd.cut(c.population_2020,
            bins=[0,100000,500000,1000000,5000000,np.inf],
            labels=["<100k","100–500k","500k–1m","1–5m",">=5m"],
            right=False).astype("string").fillna("Unknown")
    c["country"]=c.country.fillna("Unknown").replace("", "Unknown")
    c["continent"]=c.continent.fillna("Unknown").replace("", "Unknown")
    c["koppen_broad"]=c.koppen_broad.fillna("Unknown")
    c["evidence_status"]=c.fig1_v3_status.map({
        "TRAIN_CANDIDATE":"NEWS_TRAIN_CANDIDATE",
        "HELDOUT_CITY_CANDIDATE":"NEWS_HELDOUT_CANDIDATE",
        "EVIDENCE_SPARSE":"INSUFFICIENT_NEWS_EVIDENCE"})
    if c.evidence_status.isna().any():raise ValueError("Unknown city split; must freeze v3 pre-2024 split")
    c["prediction_validated"]=False
    strata=(c.groupby(["country","continent","koppen_broad","population_class"],dropna=False)
            .agg(ucdb_total_cities=("city_id","nunique"),
                 eligible_news_cities=("eligible_using_only_development_years","sum"),
                 news_tier_A=("A_count","sum"),news_tier_B=("B_count","sum"),
                 news_tier_C=("C_count","sum")).reset_index())
    strata["eligible_share"]=strata.eligible_news_cities/strata.ucdb_total_cities
    if c.city_id.duplicated().any():raise ValueError("Official UCDB city denominator corrupted")
    return c,strata,report

def physical_support(path,known_cells):
    """No observed negative; validate independent positive measurements from v3.

    Inputs are previously adjudicated field/SAR/optical evidence, not GFID point
    coincidences or uninspected CEMS catalogues. Mechanism must be PLUVIAL to
    make a pluvial claim. Returns only verified positive evidence.
    """
    from .fig1_v3_physical import validate_reference
    d=pd.read_parquet(known_cells)
    high=d[["grid_id","date"]]
    # Expects input grid separate: callers provide high plus grid through wrapper.
    raise RuntimeError("Use summarize_physical with explicit frozen GF10")

def summarize_physical(physical_csv,grid,high_days):
    from .fig1_v3_physical import validate_reference
    reviewed,pluvial,qc=validate_reference(physical_csv,grid,high_days)
    if not len(pluvial):raise ValueError("No confirmed independently reviewed pluvial positives")
    out=pluvial[["source_record_id","source_family","date","grid_id","news_matches_within_window",
                 "observation_type","pluvial_class","evidence_uri"]].copy()
    return out,qc

def plot_five_panels(frame,days,tiers,city,physical,external_qc,out,summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    plt.rcParams.update({"pdf.fonttype":42,"svg.fonttype":"none",
                         "font.family":"DejaVu Sans","font.size":8.5,
                         "axes.spines.right":False,"axes.spines.top":False})
    fig=plt.figure(figsize=(17.4,10.8),layout="constrained")
    gs=fig.add_gridspec(3,6,height_ratios=[1,1,.08])
    a=fig.add_subplot(gs[0,0:3]);b=fig.add_subplot(gs[0,3:5])
    c=fig.add_subplot(gs[0,5]);d=fig.add_subplot(gs[1,0:2])
    e=fig.add_subplot(gs[1,2:6]);foot=fig.add_subplot(gs[2,:]);foot.axis("off")
    # a: separate true independent frozen urban/periphery frame from covered cells
    per=frame[frame.domain.eq("PERIPHERY_10KM_RING")]
    core=frame[frame.domain.eq("GF10_2020_URBAN_CORE")]
    a.scatter(per.longitude,per.latitude,s=.12,c="#D4DADD",alpha=.18,rasterized=True)
    a.scatter(core.longitude,core.latitude,s=.18,c="#B0B9BF",alpha=.25,rasterized=True)
    rich=days.groupby("grid_id").raw_uuid_count.sum().reset_index()
    good=rich.merge(core[["grid_id","longitude","latitude"]],on="grid_id",
                    how="inner",validate="one_to_one")
    sc=a.scatter(good.longitude,good.latitude,c=good.raw_uuid_count,s=.8,
                 norm=LogNorm(vmin=1,vmax=max(2,good.raw_uuid_count.max())),
                 cmap="viridis",rasterized=True,alpha=.9)
    fig.colorbar(sc,ax=a,shrink=.62,pad=.01,label="Raw news UUIDs per GF10 cell")
    a.set(xlim=(-180,180),ylim=(-60,83),xlabel="Longitude",ylabel="Latitude")
    a.set_title("a  Frozen urban / 10 km peripheral frame and observed news",loc="left",weight="bold")
    a.grid(alpha=.1)
    # b: different statistical units; cluster distinct not independent floods
    tiersn=tiers.spatial_temporal_tier.value_counts()
    labels=["Raw news","Mapped news","A","A+B","Grid-days","Grid news clusters"]
    vals=[summary["raw_news"],summary["mapped_news"],int(tiersn.get("A",0)),
          int(tiersn.get("A",0)+tiersn.get("B",0)),len(days),
          summary["grid_candidate_clusters"]]
    yy=np.arange(len(vals))
    b.barh(yy,np.asarray(vals)/1e6,color=["#9DA7B1","#7BA89F","#1E756D",
            "#3F9388","#5883A5","#C4A578"])
    b.set(yticks=yy,yticklabels=labels,xlabel="Millions (different statistical units)")
    b.invert_yaxis();b.grid(axis="x",alpha=.1)
    b.set_title("b  Traceable reports, tiers and candidate observation units",loc="left",weight="bold")
    for i,n in enumerate(vals):b.text(n/1e6+max(vals)/1e6*.015,i,f"{n:,}",va="center",fontsize=7)
    b.set_xlim(0,max(vals)/1e6*1.3)
    # c: region-specific A/B/C and annual reporting in a compact panel
    cityq=(city.groupby("continent")[["A_count","B_count","C_count"]].sum())
    cityq=cityq.drop(index="Unknown",errors="ignore")
    cityq=cityq.loc[cityq.sum(axis=1).sort_values().index]
    if len(cityq):
        total=cityq.sum(axis=1).replace(0,np.nan)
        bottom=np.zeros(len(cityq));yy=np.arange(len(cityq))
        for key,color in [("A_count","#27877A"),("B_count","#BB9865"),("C_count","#939FA9")]:
            val=(100*cityq[key]/total).fillna(0).to_numpy()
            c.barh(yy,val,left=bottom,label=key[0],color=color,height=.72)
            bottom+=val
        c.set(yticks=yy,yticklabels=cityq.index.tolist(),xlabel="Tier share (%)",xlim=(0,100))
        c.legend(fontsize=7,frameon=False,loc="lower right")
    c.set_title("c  City-linked geocode quality by region",loc="left",weight="bold")
    c.grid(axis="x",alpha=.10)
    # d: independent physical observations vs mere GFID catalogue candidates
    d.set_title("d  Independent flood evidence and catalogues",loc="left",weight="bold")
    d.axis("off")
    candidate=external_qc.get("gfid_audit",{}).get("accepted_rows")
    message=(f"GFID: {candidate:,} dated representative records; NOT physical truth."
             if isinstance(candidate,int) else "GFID catalogue QC unavailable.")
    d.text(.02,.82,message,fontsize=10,transform=d.transAxes)
    if physical is None:
        d.text(.02,.51,"Independent observed PLUVIAL support: PENDING",
               color="#A55F26",fontsize=11,weight="bold",transform=d.transAxes)
        d.text(.02,.25,"GFD/CEMS: no vetted spatial-temporal physical rows supplied.",
               fontsize=9,transform=d.transAxes,wrap=True)
    else:
        n=len(physical);flood=physical.news_matches_within_window.sum()
        d.text(.02,.51,f"Reviewed pluvial positives: {n:,}",fontsize=11,
               color="#237C6D",weight="bold",transform=d.transAxes)
        d.text(.02,.26,f"Coincident HIGH news grid-days: {flood:,} (selected-case support)",
               fontsize=9,transform=d.transAxes)
    # e: cities split based only on 2021–2023; 'sparse' never 'safe from flooding'.
    e.set_title("e  Predeclared city candidates; sparse ≠ flood-free",loc="left",weight="bold")
    colors={"INSUFFICIENT_NEWS_EVIDENCE":"#AFB6BD",
            "NEWS_TRAIN_CANDIDATE":"#2B808B",
            "NEWS_HELDOUT_CANDIDATE":"#D3934C"}
    for key,col in colors.items():
        sub=city[city.evidence_status.eq(key)]
        e.scatter(sub.lon,sub.lat,c=col,s=6 if key!="INSUFFICIENT_NEWS_EVIDENCE" else 3,
                  rasterized=True,alpha=.82,label=key.replace("_"," ").title())
    e.set(xlim=(-180,180),ylim=(-60,83),xlabel="Longitude",ylabel="Latitude")
    e.grid(alpha=.1);e.legend(fontsize=7,loc="lower left",frameon=True)
    foot.text(.5,.5,"Static 2020 study domain; Groundsource polygon is a geocoder extent, not inundation. "
              "A/B/C = location/interval proxy only. Independent meteorological storm count not inferred. "
              "GFID/GFD may share DFO event selection.",ha="center",va="center",
              fontsize=8,transform=foot.transAxes)
    fig.suptitle("Figure 1 | Global urban flood-report observation coverage and uncertainty",
                 fontsize=14,fontweight="bold")
    for ext in ("pdf","svg","png"):
        fig.savefig(out/f"Figure1_publication_draft.{ext}",
                    dpi=300 if ext=="png" else None,bbox_inches="tight")
    plt.close(fig)

def run(root,tag,spatial_dir,tier_dir,city_file,crosswalk_file,v3_qc,
        physical_file=None,city_population=None,storms=None):
    root=Path(root)
    frame=pd.read_parquet(Path(spatial_dir)/"gf10_core_periphery_2020.parquet")
    qcsp=json.loads((Path(spatial_dir)/"spatial_frame_qc.json").read_text(encoding="utf-8"))
    if qcsp["status"]!="PASS_FROZEN_SPATIAL_LATTICE":raise ValueError("Invalid study frame")
    tierqc=json.loads((Path(tier_dir)/"label_tier_qc.json").read_text(encoding="utf-8"))
    if tierqc["status"]!="PASS_NEWS_UNITS_AUDIT":raise ValueError("Invalid tier/UUID audit")
    tiers=pd.read_parquet(Path(tier_dir)/"raw_uuid_tiers.parquet")
    days=pd.read_parquet(Path(tier_dir)/"grid_day_observations.parquet")
    clusters=pd.read_parquet(Path(tier_dir)/"candidate_grid_episodes.parquet")
    c=pd.read_csv(city_file,dtype={"city_id":str})
    cx=pd.read_parquet(crosswalk_file)
    if not set(tiers.grid_id).issubset(set(frame.loc[
                      frame.domain=="GF10_2020_URBAN_CORE","grid_id"])):
        raise ValueError("Historic geocoded reports unexpectedly placed in new peripheral frame")
    c,strata,news=city_attributes(c,cx,tiers,city_pop=city_population)
    external=json.loads(Path(v3_qc).read_text(encoding="utf-8"))
    if external.get("gfid_audit",{}).get("raw_rows")!=136642:
        raise ValueError("Expected full USGS GFID source ledger, no reduced/smoke data")
    if external.get("sensitivity_is_full_data") is not True:
        raise ValueError("GFID sensitivity is smoke sample, not full data")
    phys=None;physical_qc={"status":"INDEPENDENT_OBSERVED_PLUVIAL_NOT_PROVIDED"}
    if physical_file:
        core=frame[frame.domain=="GF10_2020_URBAN_CORE"]
        phys,physical_qc=summarize_physical(physical_file,core,days)
    storm_qc={"status":"INDEPENDENT_METEOROLOGICAL_STORM_CATALOGUE_NOT_PROVIDED","n_storms":None}
    if storms:
        meteor=pd.read_csv(storms)
        required={"storm_id","date","grid_id","method","meteorological_source"}
        if required-set(meteor):raise ValueError("Storm manifest missing "+str(required-set(meteor)))
        if meteor.storm_id.isna().any() or meteor.method.isna().any() or meteor.meteorological_source.isna().any():
            raise ValueError("Storm manifest lacks independent identification")
        if meteor.duplicated(["grid_id","date","storm_id"]).any():
            raise ValueError("Duplicate independent meteorology storm-grid-day")
        if meteor.meteorological_source.astype(str).str.contains("news|groundsource",case=False).any():
            raise ValueError("Storm IDs may not derive from news")
        storm_qc={"status":"USER_SUPPLIED_METEOROLOGICAL_CATALOGUE_NOT_YET_INDEPENDENTLY_VERIFIED",
                  "n_storms":int(meteor.storm_id.nunique()),
                  "meteorological_sources":meteor.meteorological_source.unique().tolist()}
    out=safe_output(root,f"outputs/{tag}/paper")
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    c.to_csv(out/"official_city_coverage_and_split.csv",index=False)
    strata.to_csv(out/"country_climate_city_size_coverage.csv",index=False)
    yr=(tiers.assign(year=pd.to_datetime(tiers.date).dt.year)
        .groupby(["year","spatial_temporal_tier"]).agg(
        report_uuids=("event_id","nunique"),
        distinct_grid_cells=("grid_id","nunique")).reset_index())
    yr.to_csv(out/"annual_ABC_news_coverage.csv",index=False)
    if phys is not None:phys.to_csv(out/"reviewed_external_pluvial_support.csv",index=False)
    counts={"raw_news":tierqc["raw_source_rows"],
            "mapped_news":tierqc["matched_unique_uuids"],
            "grid_candidate_clusters":len(clusters)}
    plot_five_panels(frame,days,tiers,c,phys,external,out,counts)
    size_missing=int(c.population_2020.isna().sum())
    unknown_countries=int(c.country.eq("Unknown").sum())
    independent_present=bool(physical_file)
    status=("DRAFT_PENDING_PHYSICAL_AND_SAMPLING"
            if not independent_present else "PHYSICAL_CASE_STUDIES_AVAILABLE_NOT_POPULATION_VALIDATION")
    if not city_population:status+="__POPULATION_STRATA_MISSING"
    qc={"status":status,"scientific_claim_allowed":"spatial availability of news and geocoding quality proxy",
        "raw_report_uuids":tierqc["raw_source_rows"],
        "mapped_uuids":tierqc["matched_unique_uuids"],
        "distinct_grid_days":len(days),"candidate_grid_contiguous_clusters":len(clusters),
        "tier_counts":tierqc["tier_counts"],
        "independent_rain_storms":storm_qc,
        "urban_core":qcsp["urban_core_cells"],"periphery":qcsp["valid_one_cell_periphery"],
        "official_ucdb_cities":len(c),
        "news_train_candidates":int(c.evidence_status.eq("NEWS_TRAIN_CANDIDATE").sum()),
        "news_heldout_candidates":int(c.evidence_status.eq("NEWS_HELDOUT_CANDIDATE").sum()),
        "evidence_sparse_cities":int(c.evidence_status.eq("INSUFFICIENT_NEWS_EVIDENCE").sum()),
        "country_unknown_cities":unknown_countries,
        "population_missing_cities":size_missing,
        "independent_physical_support":physical_qc,
        "hard_gates":{"UUID_TRACE":True,"ABC_PROXY_VALIDATION_REVIEWED":False,
                      "INDEPENDENT_PHYSICAL_EVENT_EVIDENCE":independent_present,
                      "METEOROLOGICAL_STORMS_INDEPENDENTLY_VERIFIED":False,
                      "REGIONAL_POPULATION_COVERAGE_COMPLETE":size_missing==0 and unknown_countries==0,
                      "SOURCE_LINEAGE_REVIEWED":False},
        "notes":["No media-report absence is a confirmed flood-free observation",
                 "Contiguous grid candidate clusters are NOT independently established floods or meteorological storms",
                 "Population and country groups use official UCDB denominator; Unknown are not imputed",
                 "Reported date-span proxies are NOT observed timing precision",
                 "Freeze Figure1 publication only after external label reviews, true event source audits and uncertainty"],
        "sources":{"spatial":str(spatial_dir),"tier":str(tier_dir),"city":str(city_file),
                   "external_v3":str(v3_qc),"physical":str(physical_file)}
    }
    atomic_json(out/"figure1_publication_gate.json",qc)
    return qc
