"""Figure 2 frozen, leakage-controlled 2021–2025 evaluation.

News-positive versus storm-exposed UNLABELED is the sole proxy target.
Figure1-v3 2021–2023 city selection is frozen before 2024–2025 evaluation.
This is NOT verified physical flood susceptibility. No weights or incidence
calibration are inferred from unlabeled rows.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss

from .fig2 import MODELS, TARGET, _read, validate_contract
from .paths import safe_output, atomic_json

CORE = [k for k in MODELS if k != "M5_selection_sensitivity"]
PERIOD_TRAIN = (2021, 2022, 2023)
PERIOD_TEST = (2024, 2025)
MIN_POSITIVE = 10
MIN_STORMS = 5


def freeze(panel, city_audit, weather_contract):
    """Only Figure1 v3 development-frozen city eligibility may select cities."""
    contract=validate_contract(weather_contract)
    df=_read(panel).copy()
    city=_read(city_audit).copy()
    required={"city_id", "fig1_v3_status", "eligible_using_only_development_years"}
    if required-set(city):
        raise ValueError("Require Figure1 v3 development-year city audit, not older all-year split")
    if city.city_id.duplicated().any():
        raise ValueError("Duplicated official UCDB city")
    if not set(city.fig1_v3_status.dropna()).issubset({
        "TRAIN_CANDIDATE", "HELDOUT_CITY_CANDIDATE", "EVIDENCE_SPARSE"}):
        raise ValueError("Unsupported Figure1 v3 city status")
    if set(["grid_id","date","city_id","storm_id","observed_news_onset","target_semantics"]) - set(df):
        raise ValueError("Figure2 panel lacks core model or provenance fields")
    if not df.target_semantics.eq(TARGET).all():
        raise ValueError("News positive / unlabeled semantics contract violated")
    if df.duplicated(["grid_id","date"]).any():
        raise ValueError("Duplicate grid-day rows")
    df["date"]=pd.to_datetime(df.date,errors="raise").dt.normalize()
    if df.date.isna().any():
        raise ValueError("Invalid event date")
    df["year"]=df.date.dt.year
    if not df.year.isin(PERIOD_TRAIN+PERIOD_TEST).all():
        raise ValueError("Frozen publication study window is 2021-2025, split externally")
    for col in ("grid_id","city_id","storm_id"):
        if df[col].isna().any() or df[col].astype(str).str.strip().eq("").any():
            raise ValueError("Missing grid/city/meteorological storm ID")
        df[col]=df[col].astype(str)
    outcome=pd.to_numeric(df.observed_news_onset,errors="coerce")
    if outcome.isna().any() or not outcome.isin([0,1]).all():
        raise ValueError("Invalid 0/1 news-proxy labels")
    df["observed_news_onset"]=outcome.astype(int)
    if not contract.get("coverage_complete_within_scope"):
        raise ValueError("No complete IMERG storm-exposure universe")
    for col in MODELS["M4_growth"]:
        if col not in df:
            raise ValueError("Cannot compare M0-M4 on identical data without "+col)
        values=pd.to_numeric(df[col],errors="coerce")
        if not np.isfinite(values).all():
            raise ValueError("Missing/non-finite "+col+"; cannot drop selectively by model")
        df[col]=values.astype(float)
    city["city_id"]=city.city_id.astype(str)
    city=city[["city_id","fig1_v3_status",
               "eligible_using_only_development_years"]].copy()
    df=df.merge(city,on="city_id",how="left",validate="many_to_one")
    if df.fig1_v3_status.isna().any():
        raise ValueError("Panel has city absent from frozen v3 UCDB audit")
    if df.eligible_using_only_development_years.isna().any():
        raise ValueError("Missing frozen eligibility")
    eligible=df.eligible_using_only_development_years.astype(str).str.lower().isin(["true","1"])
    inconsistent=(df.fig1_v3_status.isin(["TRAIN_CANDIDATE","HELDOUT_CITY_CANDIDATE"])
                  & ~eligible)
    if inconsistent.any():
        raise ValueError("Figure1 v3 selection marks city as heldout/train but not development-eligible")
    return df,contract


def prospective_splits(df):
    """Pre-registered temporal and city transfer; never use 2024-25 to select cities."""
    train=(df.year.isin(PERIOD_TRAIN)&df.fig1_v3_status.eq("TRAIN_CANDIDATE"))
    evals={
        "prospective_2024_2025_seen_city": (df.year.isin(PERIOD_TEST)
                                          & df.fig1_v3_status.eq("TRAIN_CANDIDATE")),
        "prospective_2024_2025_new_city": (df.year.isin(PERIOD_TEST)
                                         & df.fig1_v3_status.eq("HELDOUT_CITY_CANDIDATE")),
        "cross_city_2021_2023": (df.year.isin(PERIOD_TRAIN)
                                & df.fig1_v3_status.eq("HELDOUT_CITY_CANDIDATE")),
    }
    train_ids=np.flatnonzero(train.to_numpy())
    if len(train_ids)==0:
        raise ValueError("No development-period frozen training exposures")
    storms=set(df.iloc[train_ids].storm_id)
    splits={}
    failed={}
    for name,flag in evals.items():
        idx=np.flatnonzero(flag.to_numpy())
        before=len(idx)
        idx=np.array([i for i in idx if df.iloc[i].storm_id not in storms],dtype=int)
        # Explicitly remove weather-object overlap; no label-based rerouting.
        if len(idx)==0 or before==0:
            failed[name]={"reason":"EMPTY_AFTER_STORM_EMBARGO","candidate_rows":before,
                          "dropped_storm_overlap_rows":before}
            continue
        if set(df.iloc[train_ids].storm_id) & set(df.iloc[idx].storm_id):
            raise AssertionError("Meteorological storm leakage")
        if name.endswith("new_city") or name.startswith("cross_city"):
            if set(df.iloc[train_ids].city_id) & set(df.iloc[idx].city_id):
                raise AssertionError("Official city leakage")
        y0=df.iloc[train_ids].observed_news_onset
        y1=df.iloc[idx].observed_news_onset
        if (int(y0.sum()) < MIN_POSITIVE or int(y1.sum()) < MIN_POSITIVE
            or len(idx) < 40 or int(df.iloc[idx].storm_id.nunique()) < MIN_STORMS
            or y0.nunique()!=2 or y1.nunique()!=2):
            failed[name]={"reason":"INSUFFICIENT_COVERAGE_POSITIVES_OR_STORMS",
                          "n_train":len(train_ids),"n_test":len(idx),
                          "test_positives":int(y1.sum()),
                          "test_storms":int(df.iloc[idx].storm_id.nunique()),
                          "dropped_storm_overlap_rows":before-len(idx)}
            continue
        splits[name]=(train_ids,idx,before-len(idx))
    return splits,failed


def model_for(name,seed=42):
    if name=="logistic":
        return make_pipeline(StandardScaler(),
                             LogisticRegression(max_iter=2000,random_state=seed))
    if name=="hist_gb":
        return HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,
                                              min_samples_leaf=12,
                                              l2_regularization=2,learning_rate=.055,
                                              random_state=seed)
    raise ValueError("Unknown fixed baseline "+name)


def _metric(y,p):
    return dict(pr_auc=float(average_precision_score(y,p)),
                roc_auc=float(roc_auc_score(y,p)),
                brier_proxy=float(brier_score_loss(y,p)),prevalence=float(np.mean(y)))


def paired_delta_ci(y,p0,p1,clusters,seed=42,replications=400):
    """Paired meteorological-storm bootstrap. Never bootstrap two models independently."""
    y=np.asarray(y,dtype=int)
    clusters=np.asarray(clusters).astype(str)
    uniq=np.unique(clusters)
    if len(uniq)<MIN_STORMS:
        return np.nan,np.nan,0
    indices={s:np.flatnonzero(clusters==s) for s in uniq}
    rng=np.random.default_rng(seed)
    delta=[]
    for _ in range(replications):
        selected=rng.choice(uniq,len(uniq),replace=True)
        ii=np.concatenate([indices[s] for s in selected])
        if len(np.unique(y[ii]))<2:continue
        delta.append(float(average_precision_score(y[ii],p1[ii])
                           -average_precision_score(y[ii],p0[ii])))
    if len(delta)<max(30,round(.6*replications)):
        return np.nan,np.nan,len(delta)
    lo,hi=np.quantile(delta,[.025,.975])
    return float(lo),float(hi),len(delta)


def run(root,panel,city_audit,contract,tag="fig2_frozen_2021_2025",
        algorithms=("logistic","hist_gb")):
    if not tag.startswith("fig2_") or "/" in tag or "\\" in tag:
        raise ValueError("Use new versioned fig2_* output name")
    root=Path(root)
    out=safe_output(root,"outputs/"+tag)
    if out.exists():raise FileExistsError("Frozen Figure2 output already exists")
    df,manifest=freeze(panel,city_audit,contract)
    splits,failed=prospective_splits(df)
    if not splits:
        raise ValueError("No valid frozen prospective/cross-city tests; run QC, not paper Figure2")
    metrics=[]
    preds=[]
    for algorithm in algorithms:
        if algorithm not in ("logistic","hist_gb"):
            raise ValueError("Only fixed scikit-learn baseline methods presently implemented")
        for comparison,(tr,te,embargoed) in splits.items():
            y0=df.iloc[tr].observed_news_onset.to_numpy()
            y1=df.iloc[te].observed_news_onset.to_numpy()
            yprob={}
            for model_name in CORE:
                cols=MODELS[model_name]
                fit=model_for(algorithm)
                fit.fit(df.iloc[tr][cols].to_numpy(),y0)
                scores=fit.predict_proba(df.iloc[te][cols].to_numpy())[:,1]
                yprob[model_name]=scores
                metric=_metric(y1,scores)
                metrics.append({"comparison":comparison,"algorithm":algorithm,
                                "model":model_name,"train_years":"2021-2023",
                                "test_years":"2024-2025" if comparison.startswith("prospective") else "2021-2023",
                                "n_train":len(tr),"n_test":len(te),
                                "positive_test":int(y1.sum()),"n_cities_test":int(df.iloc[te].city_id.nunique()),
                                "n_storms_test":int(df.iloc[te].storm_id.nunique()),
                                "storm_embargo_rows":embargoed,**metric})
                if model_name=="M4_growth":
                    p=df.iloc[te][["grid_id","date","city_id","storm_id","observed_news_onset"]].copy()
                    p["algorithm"]=algorithm
                    p["comparison"]=comparison
                    p["score_news_proxy"]=scores
                    preds.append(p)
            for m in CORE[1:]:
                a=next(i for i in metrics if i["comparison"]==comparison and
                       i["algorithm"]==algorithm and i["model"]==m)
                a["delta_pr_auc_vs_m0"]=float(a["pr_auc"]-
                         next(i["pr_auc"] for i in metrics if i["comparison"]==comparison
                              and i["algorithm"]==algorithm and i["model"]=="M0_rain"))
                lo,hi,n=paired_delta_ci(y1,yprob["M0_rain"],yprob[m],
                                       df.iloc[te].storm_id.to_numpy())
                a["paired_delta_ci_025"]=lo
                a["paired_delta_ci_975"]=hi
                a["n_valid_bootstraps"]=n
    results=pd.DataFrame(metrics)
    out.mkdir(parents=True,exist_ok=False)
    results.to_csv(out/"fig2_frozen_prospective_ablation.csv",index=False)
    pd.DataFrame(preds).to_parquet(out/"fig2_frozen_m4_news_proxy_predictions.parquet",index=False)
    pd.DataFrame([{"comparison":k,**v} for k,v in failed.items()]).to_csv(
        out/"fig2_frozen_invalid_evaluations.csv",index=False)
    _plot(out,results)
    qc={
      "status":"FROZEN_NEWS_PROXY_NOT_PHYSICAL_VALIDATION",
      "development_years":list(PERIOD_TRAIN),"evaluation_years":list(PERIOD_TEST),
      "city_assignment":"Figure1 v3 2021-23-only eligible city status",
      "meteorological_event_embargo":True,
      "all_transformations_training_only":True,
      "train_only_algorithms":list(algorithms),
      "n_panel_rows":len(df),"n_cities":int(df.city_id.nunique()),
      "n_storms":int(df.storm_id.nunique()),
      "valid_comparisons":list(splits),"failed_comparisons":failed,
      "require_all_three_comparisons_for_complete_transfer":len(splits)==3,
      "no_external_physical_evidence_in_this_module":True,
      "do_not_infer_true_flood_probability":True,
      "weather_provenance":manifest,
      "inputs_sha256":{"contract":hashlib.sha256(Path(contract).read_bytes()).hexdigest(),
                       "fig1_city_audit":hashlib.sha256(Path(city_audit).read_bytes()).hexdigest()},
      "publication_gate":"INCOMPLETE until GEE source QA, full heldout support, and independent observed pluvial positive+dry negative reference"}
    atomic_json(out/"fig2_frozen_publication_gates.json",qc)
    return qc


def _plot(out,results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout="constrained")
    alg="hist_gb" if "hist_gb" in set(results.algorithm) else results.algorithm.iloc[0]
    a=results[(results.algorithm==alg)&
              (results.comparison=="prospective_2024_2025_new_city")]
    if a.empty:a=results[(results.algorithm==alg)&
                          (results.comparison==results.comparison.iloc[0])]
    a=a.set_index("model").reindex(CORE)
    x=np.arange(len(CORE))
    base=a.pr_auc.to_numpy()
    axes[0].bar(x,base)
    axes[0].set_xticks(x,[m.split("_")[0] for m in CORE])
    axes[0].set_ylim(0,1)
    axes[0].set_ylabel("PR-AUC (news-positive vs unlabeled)")
    axes[0].set_title("b  Same-heldout-sample M0–M4 ablation")
    axes[0].axhline(a.prevalence.iloc[0],ls="--",color="gray",lw=1)
    z=results[(results.algorithm==alg)&(results.model=="M4_growth")]
    axes[1].barh(z.comparison,z.pr_auc)
    axes[1].set_xlim(0,1)
    axes[1].set_xlabel("PR-AUC (news proxy only)")
    axes[1].set_title("c  Frozen transfer domains")
    fig.suptitle("Figure 2 supplement — fixed development and heldout periods; NOT true pluvial risk")
    fig.savefig(out/"Figure2_frozen_prospective_support.png",dpi=250,bbox_inches="tight")
    fig.savefig(out/"Figure2_frozen_prospective_support.pdf",bbox_inches="tight")
    plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--panel",type=Path,required=True)
    p.add_argument("--city-audit-v3",type=Path,required=True)
    p.add_argument("--weather-contract",type=Path,required=True)
    p.add_argument("--tag",default="fig2_frozen_2021_2025")
    a=p.parse_args(argv)
    print(json.dumps(run(a.root,a.panel,a.city_audit_v3,a.weather_contract,a.tag),
                     ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":main()
