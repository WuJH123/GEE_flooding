"""GF10/UCDB coverage, missing-city audit and PRE-2024 split.

Never turn all-years news availability into a future-test eligibility filter.
Spatial absence from UCDB urban-centre polygons is not geocoding failure.
"""
from __future__ import annotations
import hashlib
import numpy as np
import pandas as pd

def city_v3_audit(labels,grid,dominant,cities,pre_end="2023-12-31",
                  start="2021-01-01",future_start="2024-01-01",
                  min_news=5,min_years=2,seed=42):
    required_labels={"event_id","grid_id","date","geocode_quality"}
    if required_labels-set(labels):raise ValueError("Missing label fields")
    if set(["grid_id","urban_fraction_2020"])-set(grid):
        raise ValueError("GF10 lacks urban fraction or grid ID")
    if dominant.grid_id.duplicated().any():raise ValueError("Duplicated GF10 -> UCDB crosswalk")
    if cities.city_id.duplicated().any():raise ValueError("Duplicated official UCDB city")
    if labels.event_id.duplicated().any():raise ValueError("Original Groundsource UUID duplicated")
    high=labels[labels.geocode_quality.eq("HIGH_GEOCODE_SPECIFICITY")].copy()
    high["date"]=pd.to_datetime(high.date,errors="raise").dt.normalize()
    high=high.merge(grid[["grid_id","urban_fraction_2020"]],
                    on="grid_id",how="left",validate="many_to_one")
    if high.urban_fraction_2020.isna().any():raise ValueError("Unmapped GF10 high report")
    high=high.merge(dominant[["grid_id","city_id"]],on="grid_id",
                    how="left",validate="many_to_one")
    high["city_id"]=high.city_id.astype("string")
    official=set(cities.city_id.astype(str))
    unknown=high.city_id.notna()&~high.city_id.isin(official)
    if unknown.any():raise ValueError("Crosswalk references nonofficial city IDs")
    high["assignment_class"]=np.where(high.city_id.isna(),
                       "OUTSIDE_UCDB_URBAN_CENTRE","WITHIN_UCDB_URBAN_CENTRE")
    high["year"]=high.date.dt.year
    high["era"]=np.where(high.date.lt(pd.Timestamp(start)),"PRE_PERIOD",
                    np.where(high.date.le(pd.Timestamp(pre_end)),"MODEL_DEVELOPMENT",
                    np.where(high.date.ge(pd.Timestamp(future_start)),"FUTURE_HOLDOUT",
                             "TRANSITION")))
    high["urban_share_bin"]=pd.cut(high.urban_fraction_2020,
           bins=[-1e-8,.01,.1,.5,1.000001],labels=["<1%","1-10%","10-50%","50-100%"],
           include_lowest=True).astype("string")
    missing=(high.groupby(["assignment_class","era","urban_share_bin"],observed=True)
                 .agg(reports=("event_id","size"),
                      grids=("grid_id","nunique")).reset_index())
    period=high[(high.era=="MODEL_DEVELOPMENT")&high.city_id.notna()]
    freq=period.groupby("city_id").agg(
        development_high_reports=("event_id","nunique"),
        development_report_years=("year","nunique")).reset_index()
    future=high[(high.era=="FUTURE_HOLDOUT")&high.city_id.notna()]
    recent=future.groupby("city_id").agg(
        future_high_reports=("event_id","nunique"),
        future_years_with_reports=("year","nunique")).reset_index()
    c=cities.copy()
    c.city_id=c.city_id.astype(str)
    c=c.merge(freq,on="city_id",how="left",validate="one_to_one")
    c=c.merge(recent,on="city_id",how="left",validate="one_to_one")
    for x in ("development_high_reports","development_report_years",
              "future_high_reports","future_years_with_reports"):
        c[x]=c[x].fillna(0).astype(int)
    c["eligible_using_only_development_years"]=(c.development_high_reports>=min_news)&(
        c.development_report_years>=min_years)
    c["fig1_v3_status"]="EVIDENCE_SPARSE"
    for _,indices in c[c.eligible_using_only_development_years].groupby(
             ["continent","koppen_broad"],dropna=False).groups.items():
        inds=list(indices)
        inds.sort(key=lambda i:hashlib.sha256(
            ("fig1v3::"+str(seed)+"::"+str(c.at[i,"city_id"])).encode()).hexdigest())
        n=max(1,round(.2*len(inds))) if len(inds)>=5 else 0
        c.loc[inds,"fig1_v3_status"]="TRAIN_CANDIDATE"
        c.loc[inds[:n],"fig1_v3_status"]="HELDOUT_CITY_CANDIDATE"
    strat=(c.groupby(["continent","koppen_broad"],dropna=False)
           .agg(official_cities=("city_id","size"),
                development_eligible=("eligible_using_only_development_years","sum"),
                future_reporting_cities=("future_high_reports",lambda a:int((a>0).sum()))).reset_index())
    strat["eligible_share"]=strat.development_eligible/strat.official_cities
    stats={
        "all_high_reports":len(high),
        "assigned_high_reports":int(high.city_id.notna().sum()),
        "unassigned_high_reports":int(high.city_id.isna().sum()),
        "distinct_urban_cells_high":int(high.grid_id.nunique()),
        "official_ucdb_cities":len(c),
        "development_eligible_cities":int(c.eligible_using_only_development_years.sum()),
        "development_train_candidate_cities":int(c.fig1_v3_status.eq("TRAIN_CANDIDATE").sum()),
        "development_heldout_city_candidates":int(c.fig1_v3_status.eq("HELDOUT_CITY_CANDIDATE").sum()),
        "unknown_continent_cities":int(c.continent.fillna("Unknown").eq("Unknown").sum()),
        "policy":"2021-2023 development labels only for eligibility; 2024-2025 label counts not used for split",
        "warning":"UCDB Urban Centre is narrower than broad GF10 urban domain; non-assignment != error"}
    if stats["assigned_high_reports"]+stats["unassigned_high_reports"]!=stats["all_high_reports"]:
        raise AssertionError("UCDB high report conservation failed")
    return c,missing,strat,high,stats

def annotation_queue(labels,high_with_city,total=600,seed=42):
    """Predefine stratified HUMAN annotation queue, no fake verification labels."""
    all_labels=labels[["event_id","grid_id","date","geocode_quality"]].copy()
    all_labels["date"]=pd.to_datetime(all_labels.date)
    all_labels=all_labels.merge(high_with_city[["event_id","assignment_class"]],
                                on="event_id",how="left",validate="one_to_one")
    all_labels["assignment_class"]=all_labels.assignment_class.fillna("OTHER_OR_NO_UCDB")
    all_labels["era"]=np.where(all_labels.date.dt.year>=2021,"2021PLUS","PRE2021")
    selected=[]
    groups=list(all_labels.groupby(["geocode_quality","assignment_class","era"],dropna=False))
    per=max(1,total//max(1,len(groups)))
    for key,g in groups:
        take=min(len(g),per)
        if take:
            selected.append(g.sample(n=take,random_state=seed).copy())
    sampled=pd.concat(selected,ignore_index=True) if selected else all_labels.head(0)
    # Record a known inclusion chance within each stratum for unbiased estimates
    counts=all_labels.groupby(["geocode_quality","assignment_class","era"],dropna=False).size()
    sampled["stratum_n"]=[int(counts.loc[(q,a,e)]) for q,a,e in zip(
        sampled.geocode_quality,sampled.assignment_class,sampled.era)]
    sampled["inclusion_probability"]=np.minimum(1.,per/sampled.stratum_n)
    for col in ("reviewer_id","evidence_source_uri","location_verified",
                "date_verified","flood_occurrence_verified","pluvial_mechanism_verified",
                "independent_of_groundsource","annotation_comment"):
        sampled[col]=""
    return sampled

def annotate_summary(completed):
    """Only genuine independently reviewed rows, with missing != False."""
    required={"event_id","location_verified","date_verified","flood_occurrence_verified",
              "independent_of_groundsource","inclusion_probability"}
    if required-set(completed):raise ValueError("Review table missing columns")
    c=completed.copy()
    for col in ("location_verified","date_verified","flood_occurrence_verified",
                "independent_of_groundsource"):
        c[col]=c[col].astype(str).str.upper().str.strip()
        if not c[col].isin(["YES","NO",""]).all():
            raise ValueError("Review answer must be YES/NO/blank: "+col)
    reviewed=c[(c.location_verified.ne(""))&(c.date_verified.ne(""))&
               (c.independent_of_groundsource.eq("YES"))].copy()
    if reviewed.empty:return {"reviewed_independent_rows":0,"status":"NOT_YET_VALIDATED"}
    weight=1/reviewed.inclusion_probability.astype(float)
    def w_rate(col):
        x=reviewed[col].eq("YES")
        return float(np.average(x,weights=weight))
    return {"reviewed_independent_rows":int(len(reviewed)),
            "weighted_location_verified_fraction":w_rate("location_verified"),
            "weighted_date_verified_fraction":w_rate("date_verified"),
            "status":"REVIEW_ESTIMATE_NOT_POPULATION_TRUTH",
            "note":"Use stratified/bootstrap CI, report selection and independence limitations."}
