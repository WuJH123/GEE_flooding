"""GFID source-by-source quality audit for the independent GEE manuscript.

Representative GFID event coordinates and Groundsource geocoded grid centres
are not observed flood footprints. Candidate concordance is not verification.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

FAMILIES=("DFO","DESINVENTAR","EMDAT","HANZE")

def normalize_source(value):
    s=re.sub(r"[^A-Z0-9]","",str(value).upper())
    if "DESINVENTAR" in s:return "DESINVENTAR"
    if "EMDAT" in s:return "EMDAT"
    if "HANZE" in s:return "HANZE"
    if "DARTMOUTH" in s or s=="DFO":return "DFO"
    return "UNKNOWN"

def field(columns,*choices):
    norm={re.sub(r"[^a-z0-9]","",str(c).lower()):c for c in columns}
    return next((norm.get(k) for k in choices if norm.get(k) is not None),None)

def parse_dates(series):
    """Return parsed days AND precision flags; never coerce a year to Jan 1."""
    s=series.astype("string").str.strip()
    partial=s.str.fullmatch(r"\d{4}(?:[-/]\d{1,2})?",na=False)
    # Some dates are Excel date objects and some are source strings.
    parsed=pd.to_datetime(series,errors="coerce",format="mixed")
    if getattr(parsed.dt,"tz",None) is not None:parsed=parsed.dt.tz_localize(None)
    return parsed.dt.normalize().mask(partial),partial

def gfid_audit(workbook,begin="2000-01-01",end="2025-12-31"):
    """Keep every raw row with an *exclusive* documented failure reason.

    When End Date is unknown, use a one-day candidate with explicit flag;
    consolidated Date is legitimate fallback, but can be insufficiently precise.
    """
    raw=pd.read_excel(workbook,sheet_name="Aggregated",engine="openpyxl")
    src=field(raw.columns,"source")
    if src is None:raise ValueError("GFID Aggregated sheet lacks Source")
    st=field(raw.columns,"startdate")
    en=field(raw.columns,"enddate")
    consolidated=field(raw.columns,"date")
    lat=field(raw.columns,"lat","latitude")
    lon=field(raw.columns,"lon","longitude")
    eid=field(raw.columns,"id","eventid")
    if not (st or consolidated) or not lat or not lon:
        raise ValueError("GFID missing date/Lat/Lon; fields: "+str(raw.columns.tolist()))
    family=raw[src].map(normalize_source)
    start,partial_start=parse_dates(raw[st]) if st else (pd.Series(pd.NaT,index=raw.index),pd.Series(False,index=raw.index))
    if consolidated:
        fallback,partial_fallback=parse_dates(raw[consolidated])
        use=start.isna() & fallback.notna()
        start=start.where(~use,fallback)
    else:
        use=pd.Series(False,index=raw.index)
        partial_fallback=pd.Series(False,index=raw.index)
    if en:end,partial_end=parse_dates(raw[en])
    else:end,partial_end=pd.Series(pd.NaT,index=raw.index),pd.Series(False,index=raw.index)
    imputed_end=end.isna()&start.notna()
    end=end.where(~imputed_end,start)
    la=pd.to_numeric(raw[lat],errors="coerce")
    lo=pd.to_numeric(raw[lon],errors="coerce")
    valid_xy=la.between(-90,90)&lo.between(-180,180)
    # Strict exclusive classification, preserving raw-row denominators.
    reason=np.full(len(raw),"ACCEPTED",dtype=object)
    def mark(cond,label):
        mask=np.asarray(cond,dtype=bool)&(reason=="ACCEPTED")
        reason[mask]=label
    mark(family.eq("UNKNOWN"),"UNKNOWN_SOURCE")
    mark(start.isna(),"MISSING_OR_IMPRECISE_START")
    mark(end.isna(),"MISSING_END_AND_START")
    mark(end<start,"END_BEFORE_START")
    mark(~valid_xy,"MISSING_OR_INVALID_COORDINATES")
    begin=pd.Timestamp(begin);finish=pd.Timestamp(end if isinstance(end,str) else "2025-12-31")
    # Date window overlap (only actual dated events, not assumed year-only dates).
    mark((start>finish)|(end<begin),"OUTSIDE_ANALYSIS_WINDOW")
    eventids=raw[eid].astype("string") if eid else pd.Series([f"ROW_{i}" for i in range(len(raw))])
    audit=pd.DataFrame({"raw_row":np.arange(len(raw)), "event_id":eventids.fillna("").astype(str),
                        "family":family,"start":start,"end":end,
                        "lat":la,"lon":lo,"source_date_fallback":use.fillna(False).astype(bool),
                        "imputed_one_day_end":imputed_end.fillna(False).astype(bool),
                        "reason":reason})
    accepted=audit[audit.reason.eq("ACCEPTED")].copy()
    summary=audit.groupby(["family","reason"],dropna=False).size().rename("n").reset_index()
    if int(summary.n.sum())!=len(raw):raise AssertionError("GFID accounting mismatch")
    diagnostics={
        "raw_rows":int(len(raw)), "accepted_rows":int(len(accepted)),
        "rejected_rows":int(len(raw)-len(accepted)),
        "date_fallback_rows":int(use.fillna(False).sum()),
        "end_imputed_one_day_rows":int(imputed_end.fillna(False).sum()),
        "source_counts":{str(k):int(v) for k,v in family.value_counts().items()},
        "accepted_by_family":{str(k):int(v) for k,v in accepted.family.value_counts().items()},
        "reason_counts":{str(k):int(v) for k,v in audit.reason.value_counts().items()},
        "source_lineage":"USGS GFID; DFO, DesInventar, EM-DAT, HANZE can overlap.",
        "date_policy":"Date fallback allowed for full day; missing end imputed to one day and flagged.",
        "spatial_policy":"Representative points, NOT precise flood footprints."
    }
    return accepted,audit,summary,diagnostics

def candidate_sensitivity(high_grid_days,gfid,windows=((25,0),(75,3),(75,7),(150,7))):
    """Compute actual grid-day associations with two negative-control shuffles.

    This reports family-level catalogue proximity, never physical ground truth.
    """
    from .fig1 import candidate_catalogue_overlap
    reports=[]
    for radius,days in windows:
        matched=candidate_catalogue_overlap(high_grid_days,gfid,radius_km=radius,days=days)
        groups=matched.groupby("family").size().to_dict() if not matched.empty else {}
        for family in FAMILIES:
            reports.append({"radius_km":radius,"day_window":days,"control":"OBSERVED",
                            "family":family,"candidate_grid_days":int(groups.get(family,0)),
                            "high_grid_days_examined":len(high_grid_days)})
    # Avoid expensive spatial reshuffling for all windows; one falsification
    # control preserves location density and shifts event dates by 183 days.
    shifted=high_grid_days.copy()
    shifted["date"]=pd.to_datetime(shifted.date)+pd.Timedelta(days=183)
    neg=candidate_catalogue_overlap(shifted,gfid,radius_km=75,days=7)
    counts=neg.groupby("family").size().to_dict() if not neg.empty else {}
    for family in FAMILIES:
        reports.append({"radius_km":75,"day_window":7,"control":"SHIFT_NEWS_183_DAYS",
                        "family":family,"candidate_grid_days":int(counts.get(family,0)),
                        "high_grid_days_examined":len(high_grid_days)})
    return pd.DataFrame(reports)
