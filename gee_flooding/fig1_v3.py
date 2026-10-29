"""Standalone CEE paper Figure 1 v3 — reproducible P0 evidence audits.

Read-only references (including OLD project); ALL writes versioned under
E:\GEE_flooding. No download, no GEE task, no changes to Figure 2 code.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import safe_output,atomic_json
from .fig1_v3_gfid import gfid_audit,candidate_sensitivity,FAMILIES
from .fig1_v3_city import city_v3_audit,annotation_queue,annotate_summary
from .fig1_v3_physical import template,source_inventory,validate_reference

DEFAULT_EXISTING=[
    ("CN_FLOODS",r"E:\数据集\CN-Floods（2006–2024，中国洪水事件级遥感数据）30m"),
    ("HENAN_2021",r"E:\数据集\2021年中国河南内涝栅格数据"),
    ("LONDON_SURFACE_WATER",r"E:\数据集\英国伦敦地表水数据集"),
    ("CHINA_COUNTY_WATERLOGGING",r"E:\数据集\中国县城尺度内涝数据集（2000-2022）"),
    ("GFD_OLD_TASKS",r"E:\Global_flooding\grid10\gfd_physical_v3"),
    ("SOCIAL_FLOOD",r"E:\数据集\基于社交媒体的全球洪水点位信息"),
]

def resolve_unclassified_continents(cities,world):
    """Fill unknown city continents only from actual point-in-polygon evidence."""
    if world is None:return cities,{"resolved":0,"unresolved":int(cities.continent.eq("Unknown").sum())}
    import geopandas as gpd
    c=cities.copy()
    missing=c.continent.fillna("Unknown").eq("Unknown")
    if not missing.any():return c,{"resolved":0,"unresolved":0}
    w=gpd.read_file(world).to_crs("EPSG:4326")
    continent=next((x for x in ("CONTINENT","continent") if x in w),None)
    country=next((x for x in ("ADMIN","NAME","NAME_EN") if x in w),None)
    if not continent or not country:raise ValueError("World layer missing continent/country")
    points=gpd.GeoDataFrame(c[missing][["city_id"]].copy(),
        geometry=gpd.points_from_xy(c.loc[missing,"lon"],c.loc[missing,"lat"]),
        crs="EPSG:4326")
    hits=gpd.sjoin(points,w[[continent,country,"geometry"]],how="left",
                   predicate="intersects").drop_duplicates("city_id")
    mapping=hits.set_index("city_id")
    for i in c.index[missing]:
        key=c.at[i,"city_id"]
        if key in mapping.index and pd.notna(mapping.loc[key,continent]):
            c.at[i,"continent"]=mapping.loc[key,continent]
            c.at[i,"country"]=mapping.loc[key,country]
    return c,{"resolved":int((missing & c.continent.ne("Unknown")).sum()),
              "unresolved":int(c.continent.eq("Unknown").sum()),
              "method":"Natural Earth representative-point intersects; unresolved remains Unknown"}

def draw_v3(root,city,grid,high,miss,gfid_rows,sensitivity,validation,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    plt.rcParams.update({"font.size":9,"font.family":"DejaVu Sans","pdf.fonttype":42,
                         "svg.fonttype":"none","axes.spines.right":False,
                         "axes.spines.top":False})
    fig=plt.figure(figsize=(18,11),layout="constrained")
    gs=fig.add_gridspec(2,3,height_ratios=[1,1],width_ratios=[1.25,1,.95])
    a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1]);c=fig.add_subplot(gs[0,2])
    d=fig.add_subplot(gs[1,0]);e=fig.add_subplot(gs[1,1:])
    a.set_title("a  Urban study frame and news coverage",loc="left",weight="bold")
    valid=set(high.grid_id)
    zero=grid[~grid.grid_id.isin(valid)]
    a.scatter(zero.longitude,zero.latitude,c="#CBD2D7",s=.17,alpha=.25,
              rasterized=True,zorder=1)
    high_grids=high.groupby("grid_id").agg(reports=("event_id","size")).reset_index()
    coords=high_grids.merge(grid[["grid_id","longitude","latitude"]],
                            on="grid_id",how="left",validate="one_to_one")
    h=a.hexbin(coords.longitude,coords.latitude,C=coords.reports,
                reduce_C_function=np.sum,gridsize=(108,48),extent=(-180,180,-60,83),
                mincnt=1,cmap="viridis",norm=LogNorm(),alpha=.91)
    fig.colorbar(h,ax=a,shrink=.60,pad=.01,label="High-specificity report UUIDs / display hexagon")
    a.set(xlim=(-180,180),ylim=(-60,83),xlabel="Longitude",ylabel="Latitude")
    a.grid(alpha=.12)

    b.set_title("b  News label localization audit",loc="left",weight="bold")
    by=high.attrs.get("quality_counts",{})
    vals=[by.get(x,0) for x in (
        "HIGH_GEOCODE_SPECIFICITY","MEDIUM_GEOCODE_SPECIFICITY",
        "LOW_GEOCODE_SPECIFICITY","NOT_ELIGIBLE")]
    labels=["HIGH","MEDIUM","LOW","Not eligible"]
    b.barh(labels[::-1],np.array(vals[::-1])/1e6,
           color=["#A5AFB9","#BBA471","#76A89A","#2B7F7A"])
    b.set(xlabel="Groundsource news UUIDs (millions)")
    b.grid(axis="x",alpha=.15)
    b.set_xlim(0,max(vals)/1e6*1.25)
    for i,v in enumerate(vals[::-1]):
        b.text(v/1e6+max(vals)/1e6*.02,i,f"{v:,}",fontsize=8,va="center")

    c.set_title("c  GFID source/date acceptance",loc="left",weight="bold")
    pivot=gfid_rows.pivot_table(index="family",columns="reason",
                values="n",aggfunc="sum",fill_value=0)
    order=[x for x in FAMILIES if x in pivot.index]+[x for x in pivot.index if x not in FAMILIES]
    accepted=np.array([pivot.loc[x,"ACCEPTED"] if "ACCEPTED" in pivot else 0 for x in order])
    rejected=pivot.sum(axis=1).reindex(order).to_numpy()-accepted
    y=np.arange(len(order))
    c.barh(y,accepted/1000,color="#2B7F7A",label="Accepted")
    c.barh(y,rejected/1000,left=accepted/1000,color="#C8B8A1",label="Excluded / uncertain")
    c.set(yticks=y,yticklabels=order,xlabel="GFID source records (thousands)")
    c.legend(loc="lower right",fontsize=8,frameon=False)
    c.grid(axis="x",alpha=.14)

    d.set_title("d  GFID catalogue concordance — not physical truth",loc="left",weight="bold")
    if not sensitivity.empty:
        obs=sensitivity[(sensitivity.radius_km.eq(75))&
                        (sensitivity.day_window.eq(7))]
        obs=obs.pivot(index="family",columns="control",values="candidate_grid_days")
        fam=[x for x in FAMILIES if x in obs.index]
        yy=np.arange(len(fam))
        one=obs.reindex(fam).get("OBSERVED",pd.Series(0,index=fam)).fillna(0)
        two=obs.reindex(fam).get("SHIFT_NEWS_183_DAYS",pd.Series(0,index=fam)).fillna(0)
        d.barh(yy-.16,one.to_numpy()/1000,height=.30,label="Observed 75 km / 7 d",color="#537FA0")
        d.barh(yy+.16,two.to_numpy()/1000,height=.30,label="Shifted-date control",color="#C4A26E")
        d.set(yticks=yy,yticklabels=fam,xlabel="Candidate GF10 grid-days (thousands)")
        d.legend(fontsize=8,frameon=False)
    else:
        d.text(.05,.55,"GFID sensitivity pending",transform=d.transAxes)

    e.set_title("e  Official-city development eligibility, by continent",loc="left",weight="bold")
    x=(city.groupby("continent",dropna=False)
       .agg(n=("city_id","size"),eligible=("eligible_using_only_development_years","sum"))
       .sort_values("n",ascending=True))
    y=np.arange(len(x))
    e.barh(y,100*x.eligible/x.n,color="#2D8191")
    e.set(yticks=y,yticklabels=[str(s) for s in x.index],
          xlabel="Eligible UCDB cities using 2021–2023 (%)",xlim=(0,100))
    e.grid(axis="x",alpha=.13)
    title="Figure 1 v3 | Global urban flood observation coverage and evidence limitations"
    fig.suptitle(title,fontsize=16,weight="bold")
    fig.text(.5,.003,
             "News location is a geocoder polygon, not inundation. No-report ≠ no-flood. "
             "GFID overlap = candidate catalogue concordance. "
             f"Physical review: {validation.get('status','PENDING')}.",
             ha="center",fontsize=9)
    for ext in ("png","pdf","svg"):
        fig.savefig(out/f"Figure1_GEE_v3.{ext}",
                    dpi=300 if ext=="png" else None,bbox_inches="tight")
    plt.close(fig)

def build(root,labels_path,grid_path,label_qc_path,v2_dir,gfid,
          duplicates=None,physical=None,tag="fig1_v3",world=None,
          reviewer_table=None,review_n=600,fast=False):
    from .fig1_v3_gfid import gfid_audit
    root=Path(root)
    out=safe_output(root,"outputs/"+tag)
    if out.exists():raise FileExistsError("Never overwrite Figure1 versions: "+str(out))
    for item in (labels_path,grid_path,label_qc_path,gfid,
                 Path(v2_dir)/"fig1_ucdb_city_sample_audit.csv",
                 Path(v2_dir)/"fig1_grid_dominant_ucdb.parquet"):
        if not Path(item).is_file():raise FileNotFoundError(item)
    import re
    if not re.fullmatch(r"fig1_v3_[A-Za-z0-9_-]+|fig1_v3",tag):
        raise ValueError("Use versioned tag fig1_v3 or fig1_v3_<run>")
    from .fig1 import check_label_contract
    qc=json.loads(Path(label_qc_path).read_text(encoding="utf-8"))
    grid=pd.read_parquet(grid_path)
    labels=pd.read_parquet(labels_path,columns=["event_id","grid_id","date","geocode_quality"])
    labels["date"]=pd.to_datetime(labels.date)
    n=check_label_contract(labels,qc,grid)
    city=pd.read_csv(Path(v2_dir)/"fig1_ucdb_city_sample_audit.csv",
                     dtype={"city_id":"string"})
    city["city_id"]=city.city_id.astype(str)
    crosswalk=pd.read_parquet(Path(v2_dir)/"fig1_grid_dominant_ucdb.parquet")
    crosswalk["city_id"]=crosswalk.city_id.astype(str)
    city,resolved=resolve_unclassified_continents(city,world)
    city,missing,strata,high,city_qc=city_v3_audit(
        labels,grid,crosswalk,city)
    news=high[["event_id","grid_id","date","geocode_quality"]].copy()
    # Single HIGH group news UUID count for every grid/day, not storm count.
    high_gd=(news.groupby(["grid_id","date"]).size().rename("news_count").reset_index()
             .merge(grid[["grid_id","longitude","latitude"]],on="grid_id",
                    validate="many_to_one"))
    high_gd=high_gd.rename(columns={"longitude":"lon","latitude":"lat"})
    accepted,audit,reason_table,gfid_qc=gfid_audit(gfid)
    if fast:
        # Only for code/QC smoke; never claim the reduced set gives full match statistics.
        high_for_match=high_gd.iloc[:min(1000,len(high_gd))]
    else:high_for_match=high_gd
    sensitivity=candidate_sensitivity(high_for_match,accepted)
    valid_report={"status":"PENDING_INDEPENDENT_PHYSICAL_REVIEW"}
    phys=None;phys_points=None
    if physical:
        phys,phys_points,valid_report=validate_reference(
            physical,grid,high_gd[["grid_id","date"]])
    samples=annotation_queue(labels,high,total=review_n)
    if reviewer_table:
        reviewed=pd.read_csv(reviewer_table,dtype={"event_id":"string"})
        valid_report["manual_review"]=annotate_summary(reviewed)
    dirs=source_inventory(DEFAULT_EXISTING)
    out.mkdir(parents=True,exist_ok=False)
    audit.to_parquet(out/"gfid_row_level_quality.parquet",index=False)
    reason_table.to_csv(out/"gfid_reason_by_family.csv",index=False)
    sensitivity.to_csv(out/"gfid_candidate_sensitivity.csv",index=False)
    city.to_csv(out/"ucdb_city_development_holdout.csv",index=False)
    missing.to_csv(out/"ucdb_missing_assignment_by_period_and_urban_share.csv",index=False)
    strata.to_csv(out/"ucdb_eligibility_by_continent_koppen.csv",index=False)
    samples.to_csv(out/"independent_groundsource_annotation_queue.csv",index=False)
    dirs.to_csv(out/"local_physical_source_inventory.csv",index=False)
    if duplicates:
        dup=pd.read_csv(duplicates,nrows=0)
        # No automatic assumption: USGS flags *potential* duplicates, not confirmed pairs.
        dups={"source_path":str(duplicates),"columns":dup.columns.tolist(),
              "note":"Do not deduplicate GFID automatically from potential duplicate flags."}
    else:dups={"status":"DUPLICATE_SCREEN_NOT_PROVIDED"}
    if phys is None:
        template(out/"physical_evidence_input_template.csv")
    else:
        phys.to_parquet(out/"physical_reviewed_events.parquet",index=False)
        phys_points.to_csv(out/"physical_pluvial_support.csv",index=False)
    high.attrs["quality_counts"]=qc["count_by_quality"]
    draw_v3(root,city,grid,high,missing,reason_table,sensitivity,valid_report,out)
    result={
        "status":"PREPUBLICATION_P0_PENDING" if not physical else "PHYSICAL_CASE_STUDY_REVIEW_PENDING",
        "source_original_raw_rows":n,
        "news_mapped_high_count":city_qc["all_high_reports"],
        "distinct_high_grid_days":len(high_gd),
        "study_grid_count":len(grid),"city_audit":city_qc,
        "natural_earth_unknown_city_repair":resolved,
        "gfid_audit":gfid_qc,"potential_duplicate_screen":dups,
        "sensitivity_is_full_data":not fast,
        "physical_evidence":valid_report,
        "outputs_directory":str(out),
        "limitations":[
            "GFID coordinates are representative and data-family nonindependence is material",
            "Without reviewed external physical positives, Fig1d is catalogue concordance only",
            "No-report GF10 grid-day is unlabeled, not flood-free",
            "UCDB Urban Centre is narrower than the 2020 broad GF10 urban frame",
            "City eligibility uses only 2021–2023; future 2024–2025 never selects eligibility",
            "News HIGH is geometry specificity, not independently confirmed flooded cell",
            "No flood-susceptibility prediction is evaluated by this figure"],
        "inputs":{"labels":str(labels_path),"grid":str(grid_path),
                  "label_qc":str(label_qc_path),"v2_dir":str(v2_dir),
                  "gfid":str(gfid),"world":str(world),"physical":str(physical)}
    }
    atomic_json(out/"fig1_v3_qc.json",result)
    return result
