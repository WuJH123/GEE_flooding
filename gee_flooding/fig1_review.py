"""Human independent-label review audit. NEVER invent reference judgements.

Requires one or two traceable independent reviewer rows per preselected UUID.
Unreviewed/missing records do not count as negative labels; if any queue
member lacks a valid review, no population-level validation is claimed.
"""
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json

FIELDS=("location_verified","date_verified","flood_occurrence_verified",
        "pluvial_mechanism_verified")
CHOICES={"YES","NO","UNKNOWN"}
def summarize(root,queue_path,reviews_path,tag="fig1_review_r1",seed=42):
    queue=pd.read_csv(queue_path,dtype={"event_id":str})
    reviews=pd.read_csv(reviews_path,dtype={"event_id":str})
    if queue.event_id.duplicated().any():raise ValueError("Duplicate review queue UUID")
    base={"event_id","inclusion_probability","geocode_quality",
          "assignment_class","era"}
    if base-set(queue):raise ValueError("Missing queue sampling fields "+str(base-set(queue)))
    req={"event_id","reviewer_id","evidence_source_uri","independent_of_groundsource",*FIELDS}
    if req-set(reviews):raise ValueError("Missing reviewer fields "+str(req-set(reviews)))
    if (~reviews.event_id.isin(queue.event_id)).any():
        raise ValueError("Review contains UUIDs outside predeclared sample")
    if reviews.duplicated(["event_id","reviewer_id"]).any():
        raise ValueError("Same reviewer repeated for an event")
    prob=pd.to_numeric(queue.inclusion_probability,errors="coerce")
    if prob.isna().any() or (~prob.between(0,1)).any() or (prob==0).any():
        raise ValueError("Invalid sampling inclusion probabilities")
    for k in (*FIELDS,"independent_of_groundsource"):
        reviews[k]=reviews[k].fillna("UNKNOWN").astype(str).str.strip().str.upper()
        if not reviews[k].isin(CHOICES).all():
            raise ValueError("Reviewer answers must be YES/NO/UNKNOWN: "+k)
    reviewer=reviews.reviewer_id.fillna("").astype(str).str.strip().ne("")
    evidence=reviews.evidence_source_uri.fillna("").astype(str).str.strip().ne("")
    # Metadata of evidence matters. A nonempty URI is a traceable claim,
    # NOT programmatic proof of evidence independence.
    complete=reviewer&evidence&reviews.independent_of_groundsource.eq("YES")&(
        reviews.location_verified.ne("UNKNOWN"))&reviews.date_verified.ne("UNKNOWN")&(
        reviews.flood_occurrence_verified.ne("UNKNOWN"))
    reviews["review_valid"]=complete
    valid=reviews[reviews.review_valid].copy()
    n_reviewers=valid.groupby("event_id").reviewer_id.nunique()
    adjudication=[]
    for eid,g in valid.groupby("event_id"):
        if len(g)>2:raise ValueError("Protocol allows no more than two independent reviews per UUID")
        rec={"event_id":eid,"review_count":len(g),
             "reviewer_disagreement":False}
        for col in FIELDS:
            values=g[col].tolist()
            rec[col]=values[0] if len(set(values))==1 else "DISAGREEMENT"
            if len(set(values))>1:rec["reviewer_disagreement"]=True
        adjudication.append(rec)
    consensus=pd.DataFrame(adjudication,columns=[
        "event_id","review_count","reviewer_disagreement",*FIELDS])
    joined=queue.merge(consensus,on="event_id",how="left",validate="one_to_one")
    n_valid=int(joined.review_count.notna().sum())
    n_missing=len(queue)-n_valid
    disagree=int(joined.reviewer_disagreement.fillna(False).sum())
    # Only uncontested, fully adjudicated responses constitute confirmed review.
    accepted=joined[joined.review_count.notna()&
         ~joined.reviewer_disagreement.fillna(False)].copy()
    strata_cols=["geocode_quality","assignment_class","era"]
    by=joined.groupby(strata_cols,dropna=False).agg(
         selected_uuids=("event_id","size"),
         valid_reviewed_uuids=("review_count",lambda x:int(x.notna().sum())),
         dual_reviewed=("review_count",lambda x:int(x.eq(2).sum())),
         disagreements=("reviewer_disagreement",lambda x:int(x.fillna(False).sum()))
         ).reset_index()
    # Do not extrapolate a partial and nonrandomly completed queue.
    fully_complete=(n_missing==0 and disagree==0)
    estimates={}
    if fully_complete:
        rng=np.random.default_rng(seed)
        for tier,g in accepted.groupby("geocode_quality",dropna=False):
            w=1/pd.to_numeric(g.inclusion_probability).to_numpy(dtype=float)
            for col in ("location_verified","date_verified","flood_occurrence_verified"):
                yes=(g[col]=="YES").to_numpy(dtype=float)
                if len(g)<2:
                    bounds=[None,None]
                else:
                    vals=[]
                    for _ in range(500):
                        ix=rng.integers(0,len(g),len(g))
                        vals.append(float(np.average(yes[ix],weights=w[ix])))
                    bounds=np.quantile(vals,[.025,.975]).round(5).tolist()
                estimates[f"{tier}::{col}"]={
                    "weighted_review_positive_fraction":float(np.average(yes,weights=w)),
                    "n":len(g),"bootstrap_95_ci_approx":bounds}
    out=safe_output(root,f"outputs/{tag}/review")
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    joined.to_csv(out/"review_adjudication.csv",index=False)
    by.to_csv(out/"review_response_by_stratum.csv",index=False)
    state="PRELIMINARY_FULL_QUEUE_ADJUDICATED" if fully_complete else "REVIEW_INCOMPLETE_NO_ACCURACY_CLAIM"
    qc={"status":state,"selected":len(queue),"valid_independently_reviewed":n_valid,
        "missing":n_missing,"reviewer_disagreements":disagree,
        "dual_reviewed":int(joined.review_count.eq(2).sum()),
        "estimates":estimates,
        "critical_limitations":[
           "Independence remains a human-source judgement; traceable URI alone does not prove it",
           "Reviewer disagreements require third-party adjudication rather than majority vote",
           "Stratum bootstrap is descriptive; full design variance requires accounting for strata selection",
           "Even a reviewed news queue cannot provide global pluvial flood sensitivity without monitored true negatives"],
        "peer_review_ready":False}
    atomic_json(out/"human_label_review_qc.json",qc)
    return qc
