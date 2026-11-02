"""Frozen-outline Figure2a–e plotting and subgroup uncertainty from M03–M05.

a methodology; b same-test M0–M4 paired delta AP; c prospective transfer;
d climate / built-form subgroup paired M4-M0 AP where supported;
e HAND×built×daily rainfall empirical news-onset cells. This module does NOT
run physical flood tests (those are the frozen manuscript's Figure3 M06).
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from .fig2_frozen import paired_delta_ci
from .paths import safe_output,atomic_json


def make(root, frozen_dir,panel,city_meta,tag="fig2_publication_news_v1",
         algorithm="hist_gb",min_positives=10):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use new immutable fig2_* tag")
    output=safe_output(root,"outputs/"+tag)
    if output.exists():raise FileExistsError(output)
    frozen=Path(frozen_dir)
    gate=json.loads((frozen/"fig2_frozen_publication_gates.json").read_text())
    if gate["status"]!="FROZEN_NEWS_PROXY_NOT_PHYSICAL_VALIDATION":
        raise ValueError("Requires frozen M03–M05 NEWS PROXY prediction contract")
    metrics=pd.read_csv(frozen/"fig2_frozen_prospective_ablation.csv")
    preds=pd.read_parquet(frozen/"fig2_frozen_m4_news_proxy_predictions.parquet")
    data=pd.read_parquet(panel)
    if not {"grid_id","date","city_id","storm_id","rain_24h_mm",
            "hand_m","built_fraction_2020","observed_news_onset"}<=set(data):
        raise ValueError("Figure2 event panel lacks key explanatory factors")
    if data.duplicated(["grid_id","date"]).any():raise ValueError("Duplicate panel grid-date")
    if not {"score_M0_rain","score_M4_growth","score_news_proxy"}<=set(preds):
        raise ValueError("Require rerun of new frozen prospective pipeline for paired scores")
    meta=pd.read_csv(city_meta) if str(city_meta).lower().endswith(".csv") else pd.read_parquet(city_meta)
    if "city_id" not in meta or meta.city_id.duplicated().any():
        raise ValueError("City metadata must contain one UCDB row per city")
    climate=next((x for x in ("koppen_broad","climate_zone") if x in meta),None)
    if not climate:raise ValueError("Climate context absent; cannot publish Figure2d")
    meta=meta[["city_id",climate]].rename(columns={climate:"climate_zone"})
    for x in (data,preds,meta):x["city_id"]=x.city_id.astype(str)
    for x in (data,preds):x["grid_id"]=x.grid_id.astype(str);x["date"]=pd.to_datetime(x.date).dt.normalize()
    needed=data[["grid_id","date","storm_id","rain_24h_mm","hand_m",
                 "built_fraction_2020"]].copy()
    z=preds.loc[preds.algorithm.eq(algorithm)].merge(
       needed,on=["grid_id","date"],how="left",validate="many_to_one",suffixes=("","_panel"))
    if z[["rain_24h_mm","hand_m","built_fraction_2020"]].isna().any().any():
        raise ValueError("Heldout evaluations do not align with source event panel")
    if (z.storm_id.astype(str)!=z.storm_id_panel.astype(str)).any():
        raise ValueError("Storm identity changes between evaluation and panel")
    z=z.drop(columns="storm_id_panel").merge(meta,on="city_id",how="left",validate="many_to_one")
    if z.climate_zone.isna().any():raise ValueError("Unknown climate subgroup")
    if z.duplicated(["grid_id","date","comparison"]).any():
        raise ValueError("Repeat prediction in same split")
    subgroup=[]
    for (comparison,zone),r in z.groupby(["comparison","climate_zone"],sort=True):
        if len(r)<50 or r.observed_news_onset.sum()<min_positives or r.storm_id.nunique()<5:
            subgroup.append(dict(comparison=comparison,group=zone,n_rows=len(r),
                                 positive=int(r.observed_news_onset.sum()),status="INSUFFICIENT"))
            continue
        y=r.observed_news_onset.to_numpy(int)
        if y.sum()==len(y):continue
        p0=r.score_M0_rain.to_numpy(float);p4=r.score_M4_growth.to_numpy(float)
        delta=float(average_precision_score(y,p4)-average_precision_score(y,p0))
        lo,hi,n=paired_delta_ci(y,p0,p4,r.storm_id.to_numpy(),seed=42)
        subgroup.append(dict(comparison=comparison,group=zone,n_rows=len(r),
                             positive=int(y.sum()),delta_ap=delta,ci_lo=lo,ci_hi=hi,
                             bootstraps=n,status="EVALUABLE"))
    out_groups=pd.DataFrame(subgroup)
    if out_groups.empty:raise ValueError("No climate contexts in heldout predictions")
    # 2e: only test observations, three daily rain strata, HAND x built tertiles.
    # Do NOT call these causal effects or true flood probabilities.
    zz=z.loc[z.comparison.eq("prospective_2024_2025_new_city")].copy()
    if len(zz)<100:
        zz=z.loc[z.comparison.eq("cross_city_2021_2023")].copy()
    if len(zz)<100:
        raise ValueError("Insufficient heldout new-city exposures for reliable Fig2e")
    for col in ("rain_24h_mm","hand_m","built_fraction_2020"):
        if zz[col].nunique()<3:
            raise ValueError("No variation for Figure2 interaction: "+col)
        bins=3 if col=="rain_24h_mm" else 2
        labs=["low","mid","high"] if bins==3 else ["low","high"]
        zz[col+"_tercile"]=pd.qcut(zz[col].rank(method="first"),bins,labels=labs)
    interaction=zz.groupby(["rain_24h_mm_tercile","hand_m_tercile",
                             "built_fraction_2020_tercile"],observed=True).agg(
       n=("observed_news_onset","size"),
       reported=("observed_news_onset","sum"),
       news_rate=("observed_news_onset","mean")).reset_index()
    interaction.loc[interaction.n.lt(20),"news_rate"]=np.nan
    if int(interaction.news_rate.notna().sum())<3:
        raise ValueError("Figure2e interaction cells underpowered; enlarge frozen city/storm sample")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(15,10),layout="constrained")
    gs=fig.add_gridspec(3,6,height_ratios=[1,1,1])
    axa=fig.add_subplot(gs[0,:2]);axb=fig.add_subplot(gs[0,2:4]);axc=fig.add_subplot(gs[0,4:])
    axd=fig.add_subplot(gs[1,:]);axe=[fig.add_subplot(gs[2,i*2:(i+1)*2]) for i in range(3)]
    axa.axis("off");axa.set_title("a  Frozen exposure design",loc="left",weight="bold")
    axa.text(.03,.85,"GF10 × independent rain object",transform=axa.transAxes,fontsize=11)
    axa.text(.03,.60,"NEWS positive / UNLABELED",transform=axa.transAxes)
    axa.text(.03,.35,"Train 2021–23, evaluate 2024–25",transform=axa.transAxes)
    axa.text(.03,.10,"Physical validation: Figure 3",transform=axa.transAxes)
    m=metrics.loc[metrics.algorithm.eq(algorithm)].copy()
    focus=m.loc[m.comparison.eq("prospective_2024_2025_new_city")]
    if focus.empty:focus=m.loc[m.comparison.eq("cross_city_2021_2023")]
    if focus.empty:raise ValueError("Frozen new-city comparison absent")
    order=["M0_rain","M1_terrain","M2_surface","M3_form","M4_growth"]
    focus=focus.set_index("model").reindex(order)
    xb=np.arange(len(order))
    axb.bar(xb,focus.pr_auc.values)
    axb.set_xticks(xb,["M0","M1","M2","M3","M4"])
    axb.set_ylim(0,1)
    axb.set_ylabel("AP (news proxy)")
    axb.set_title("b  Same heldout rows",loc="left",weight="bold")
    for i,model in enumerate(order[1:],1):
        lo=focus.loc[model,"paired_delta_ci_025"]
        hi=focus.loc[model,"paired_delta_ci_975"]
        axb.text(i,float(focus.loc[model,"pr_auc"])+.025,
                 f"Δ{float(focus.loc[model,'delta_pr_auc_vs_m0']):+.2f}",
                 rotation=90,fontsize=7,ha="center")
    transfer=m[m.model.eq("M4_growth")].sort_values("comparison")
    axc.barh(transfer.comparison,transfer.pr_auc)
    axc.set_xlim(0,1);axc.set_xlabel("M4 AP (news proxy)")
    axc.set_title("c  Frozen transfer",loc="left",weight="bold")
    good=out_groups.loc[out_groups.status.eq("EVALUABLE")].copy()
    axd.set_title("d  Climate-specific paired ΔAP(M4–M0), within test group",loc="left",weight="bold")
    if not good.empty:
        good=good.sort_values(["comparison","group"])
        x=np.arange(len(good))
        axd.errorbar(x,good.delta_ap,yerr=np.vstack([
            good.delta_ap-good.ci_lo,good.ci_hi-good.delta_ap]),fmt="o",capsize=2)
        axd.set_xticks(x,(good.comparison.str.replace("prospective_2024_2025_","")+
                          " / "+good.group).tolist(),rotation=25,ha="right",fontsize=8)
        axd.axhline(0,linestyle="--",color="gray")
    else:
        axd.text(.5,.5,"No group meets sample/cluster threshold",ha="center",transform=axd.transAxes)
    axd.set_ylabel("ΔAP and storm bootstrap 95% CI")
    for idx,rainlevel in enumerate(["low","mid","high"]):
        ax=axe[idx]
        sub=interaction.loc[interaction.rain_24h_mm_tercile.eq(rainlevel)]
        matrix=sub.pivot(index="hand_m_tercile",columns="built_fraction_2020_tercile",
                         values="news_rate").reindex(index=["low","high"],
                                                       columns=["low","high"])
        ax.imshow(matrix.to_numpy(float),vmin=0,vmax=.3,cmap="viridis")
        ax.set_xticks(range(2),["L","H"]);ax.set_yticks(range(2),["L","H"])
        ax.set_title(f"e  Rain {rainlevel}",fontsize=10)
        ax.set_xlabel("Built");ax.set_ylabel("HAND")
    fig.suptitle("Figure 2  |  Rain-conditioned NEWS REPORT response (NOT observed pluvial flood risk)")
    output.mkdir(parents=True,exist_ok=False)
    fig.savefig(output/"Figure2_a_e_news_proxy.pdf",bbox_inches="tight")
    fig.savefig(output/"Figure2_a_e_news_proxy.png",dpi=250,bbox_inches="tight")
    plt.close(fig)
    out_groups.to_csv(output/"fig2d_climate_paired_delta_AP.csv",index=False)
    interaction.to_csv(output/"fig2e_hand_built_rain_news_rates.csv",index=False)
    qc=dict(status="FIG2_FROZEN_NEWS_PROXY_ONLY",algorithm=algorithm,
            figure3_physical_verification_separate=True,
            n_heldout_predictions=len(z),
            n_qualified_climate_subgroups=int(len(good)),
            n_interaction_groups_with_support=int(interaction.news_rate.notna().sum()),
            all_three_transfer_tests=bool(gate.get("require_all_three_comparisons_for_complete_transfer")),
            warning="Not a physical urban flood susceptibility map, association not causality")
    atomic_json(output/"fig2a_e_publication_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--frozen-dir",type=Path,required=True)
    p.add_argument("--panel",type=Path,required=True)
    p.add_argument("--cities",type=Path,required=True)
    p.add_argument("--algorithm",choices=["logistic","hist_gb"],default="hist_gb")
    p.add_argument("--tag",default="fig2_publication_news_v1")
    a=p.parse_args(argv)
    print(json.dumps(make(a.root,a.frozen_dir,a.panel,a.cities,a.tag,a.algorithm),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
