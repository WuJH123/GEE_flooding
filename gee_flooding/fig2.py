"""Figure 2: transfer of news-report discrimination under rainfall exposure.

All outputs are explicitly observational proxy outputs, NEVER true flood risk.
Usage: python -m gee_flooding.fig2 --help
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from .paths import safe_output, atomic_json

MODELS = {
    "M0_rain": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm"],
    "M1_terrain": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm", "hand_m", "slope_deg"],
    "M2_surface": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm", "hand_m", "slope_deg",
                   "urban_fraction_2020", "vegetation_fraction"],
    "M3_form": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm", "hand_m", "slope_deg",
                "urban_fraction_2020", "vegetation_fraction", "built_fraction_2020",
                "built_neighbor_density", "built_fragmentation"],
    "M4_growth": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm", "hand_m", "slope_deg",
                  "urban_fraction_2020", "vegetation_fraction", "built_fraction_2020",
                  "built_neighbor_density", "built_fragmentation", "built_growth_2000_2020"],
    "M5_selection_sensitivity": ["rain_24h_mm", "rain_3h_mm", "api_7d_mm",
                                  "hand_m", "slope_deg", "urban_fraction_2020",
                                  "vegetation_fraction", "built_fraction_2020",
                                  "built_neighbor_density", "built_fragmentation",
                                  "built_growth_2000_2020"],
}
BASE = ["grid_id", "date", "storm_id", "city_id", "observed_news_onset", "target_semantics"]
TARGET = "positive_vs_unlabeled_not_true_flood_vs_no_flood"
PROXY_NOTE = ("Reported news onsets versus unlabeled storm-exposed grid-days. "
              "Unreported does not mean flood-free; scores and calibration are NOT "
              "true pluvial flood probabilities.")
GROUPS = [("unseen_city_and_storm", "city_id"),
          ("unseen_country_and_storm", "country"),
          ("unseen_climate_and_storm", "climate_zone"),
          ("unseen_year_and_storm", "year")]


def _read(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError("Expected parquet or CSV: " + str(path))


def validate_contract(path):
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = ["meteorology_source", "exposure_sampling_rule", "storms_independent_of_labels",
              "coverage_complete_within_scope", "spatial_scope", "start_date", "end_date",
              "time_basis", "rain_units"]
    absent = [x for x in fields if x not in c or c[x] in ("", None)]
    if absent:
        raise ValueError("Weather provenance contract missing: " + ", ".join(absent))
    if c["storms_independent_of_labels"] is not True or c["coverage_complete_within_scope"] is not True:
        raise ValueError("Meteorological storms and complete exposure universe are mandatory")
    if c["rain_units"] != "mm":
        raise ValueError("Precipitation features must be in mm; IMERG mm/h needs 0.5h integration")
    if c["time_basis"] != "UTC":
        raise ValueError("Use UTC days and explicitly audit onset-date time mismatch")
    if "news" in str(c["exposure_sampling_rule"]).lower():
        raise ValueError("Exposure universe must not be conditioned on news reporting")
    return c


def prepare(panel, cities=None, grid_cities=None, extended=None, resilience_static=None):
    df = _read(panel)
    missing = set(BASE + MODELS["M2_surface"]) - set(df)
    if missing:
        raise ValueError("Panel lacks required columns: " + str(sorted(missing)))
    if not df.target_semantics.eq(TARGET).all():
        raise ValueError("News-vs-unlabeled outcome semantics missing")
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.normalize()
    if df["date"].isna().any() or df["date"].min() < pd.Timestamp("2021-01-01"):
        raise ValueError("Fixed 2020/2021 surface predictors require 2021+ exposure dates")
    for col in ["grid_id", "storm_id", "city_id"]:
        if df[col].isna().any():
            raise ValueError("Missing group key: " + col)
        df[col] = df[col].astype(str)
        if df[col].str.strip().eq("").any():
            raise ValueError("Blank group key: " + col)
    if df.duplicated(["grid_id", "date"]).any():
        raise ValueError("Multiple grid-day rows; resolve storm attribution before modelling")
    y = pd.to_numeric(df.observed_news_onset, errors="raise")
    if y.isna().any() or not set(y.unique()).issubset({0, 1}):
        raise ValueError("Outcomes must be 0/1")
    df["observed_news_onset"] = y.astype("int8")
    if df["observed_news_onset"].sum() < 5:
        raise ValueError("At least five independent positive exposure rows required")
    if grid_cities:
        x = _read(grid_cities)
        if set(["grid_id", "city_id"]) - set(x):
            raise ValueError("Figure1 UCDB grid crosswalk missing grid_id/city_id")
        if x.grid_id.duplicated().any():
            raise ValueError("Duplicate Figure1 crosswalk grid")
        x = x[["grid_id", "city_id"]].astype(str).rename(columns={"city_id": "fig1_city_id"})
        df = df.merge(x, on="grid_id", how="left", validate="many_to_one")
        invalid = df.fig1_city_id.notna() & df.fig1_city_id.ne(df.city_id)
        if invalid.any():
            raise ValueError("Meteorological panel city IDs disagree with Figure1 UCDB crosswalk")
        if df.fig1_city_id.isna().any():
            raise ValueError("Unassigned Figure1 UCDB city in model universe")
        df = df.drop(columns="fig1_city_id")
    if cities:
        c = _read(cities)
        if "city_id" not in c or c.city_id.duplicated().any():
            raise ValueError("Figure1 city audit requires unique city IDs")
        for col, alternate in [("country", "country"), ("climate_zone", "koppen_broad")]:
            if col not in df:
                if alternate not in c:
                    raise ValueError("Figure1 audit lacks " + alternate)
                df = df.merge(c[["city_id", alternate]].assign(city_id=lambda x: x.city_id.astype(str))
                              .rename(columns={alternate: col}), on="city_id", how="left",
                              validate="many_to_one")
    if extended:
        x = _read(extended)
        want = ["grid_id", "built_fraction_2020", "built_neighbor_density",
                "built_fragmentation", "built_growth_2000_2020"]
        if set(want) - set(x):
            raise ValueError("Extended raster data missing: " + str(sorted(set(want) - set(x))))
        if x.grid_id.duplicated().any():
            raise ValueError("Duplicate extended grid factor")
        overlap = set(want[1:]) & set(df)
        if overlap:
            raise ValueError("Extended factors already in panel: " + str(sorted(overlap)))
        x = x[want].copy()
        x.grid_id = x.grid_id.astype(str)
        df = df.merge(x, on="grid_id", how="left", validate="many_to_one")
    if resilience_static:
        rich=_read(resilience_static)
        if "grid_id" not in rich or rich.grid_id.duplicated().any():
            raise ValueError("Resilience static GF10 requires unique grid_id")
        rich.grid_id=rich.grid_id.astype(str)
        # Existing validated predictors remain authoritative; no suffix collisions.
        newcols=[x for x in rich if x not in df.columns and x!="grid_id"]
        allowed=set(["elevation_m","upstream_area_km2","river_water_fraction",
                     "built_nres_fraction_2020","tree_fraction","grass_fraction",
                     "cropland_fraction","wetland_fraction","water_fraction",
                     "bare_fraction"])
        newcols=[x for x in newcols if x in allowed]
        if newcols:
            rich=rich[["grid_id"]+newcols]
            df=df.merge(rich,on="grid_id",how="left",validate="many_to_one")
            for key in newcols:
                if not np.isfinite(pd.to_numeric(df[key],errors="coerce")).all():
                    raise ValueError("Invalid optional resilience GF10 indicator "+key)
    df["year"] = df.date.dt.year.astype(int)
    if "country" not in df:
        df["country"] = np.nan
    if "climate_zone" not in df:
        df["climate_zone"] = np.nan
    if "n_report_uuids" in df:
        mismatch = (df.n_report_uuids.gt(0) != df.observed_news_onset.eq(1))
        if mismatch.any():
            raise ValueError("Report UUID count/positive target mismatch")
    return df


def _split(df, field, seed):
    # Meteorological storms are also withheld for EVERY domain test.
    if df[field].isna().any() or df[field].astype(str).isin(["Unknown", "", "nan"]).any():
        raise ValueError("Missing/unknown " + field)
    if df[field].nunique() < 3 or df.storm_id.nunique() < 5:
        raise ValueError("Insufficient independent group diversity")
    a, b = next(GroupShuffleSplit(test_size=.25, random_state=seed).split(
        df, groups=df[field]))
    s, t = next(GroupShuffleSplit(test_size=.25, random_state=seed+1901).split(
        df, groups=df.storm_id))
    train, test = np.intersect1d(a, s), np.intersect1d(b, t)
    y = df.observed_news_onset.to_numpy()
    if len(train) < 40 or len(test) < 20 or min(y[train].sum(), y[test].sum()) < 2:
        raise ValueError("No reliable dual-heldout support (rows/positives)")
    if len(np.unique(y[train])) < 2 or len(np.unique(y[test])) < 2:
        raise ValueError("Only one class in train or test")
    if set(df.iloc[train][field]) & set(df.iloc[test][field]):
        raise AssertionError("Domain group leakage")
    if set(df.iloc[train].storm_id) & set(df.iloc[test].storm_id):
        raise AssertionError("Storm group leakage")
    return train, test


def _fit(X, y, seed, weights=None):
    model = HistGradientBoostingClassifier(
        max_iter=180, max_leaf_nodes=15, min_samples_leaf=12,
        l2_regularization=2, learning_rate=.055, random_state=seed)
    model.fit(X, y, sample_weight=weights)
    return model


def _score(y, p):
    if not np.isfinite(p).all():
        raise ValueError("Invalid predicted scores")
    bins = np.minimum((p * 10).astype(int), 9)
    ece = sum((bins == i).mean() * abs(float(y[bins == i].mean()) -
                  float(p[bins == i].mean())) for i in range(10) if (bins == i).any())
    return dict(pr_auc_proxy=float(average_precision_score(y, p)),
                roc_auc_proxy=float(roc_auc_score(y, p)),
                brier_proxy=float(brier_score_loss(y, p)),
                ece_proxy=float(ece), test_prevalence=float(y.mean()))


def _bootstrap(y, p, storm, seed, n=150):
    rng = np.random.default_rng(seed)
    groups = np.asarray(storm, dtype=str)
    names = np.unique(groups)
    idx = {s: np.flatnonzero(groups == s) for s in names}
    scores = []
    for _ in range(n):
        draw = rng.choice(names, len(names), replace=True)
        take = np.concatenate([idx[x] for x in draw])
        if len(np.unique(y[take])) > 1:
            scores.append(average_precision_score(y[take], p[take]))
    if len(scores) < 20:
        return np.nan, np.nan
    return [float(x) for x in np.quantile(scores, [.025, .975])]


def _physical(df, predictions, external_path):
    if not external_path:
        return {"status": "NOT_AVAILABLE", "reason": "Independent pluvial flood/non-flood labels absent"}, pd.DataFrame()
    x = _read(external_path)
    need = {"grid_id", "date", "valid_observation", "flood_observed",
            "source_independent", "pluvial_confirmed", "sensor"}
    if need - set(x):
        raise ValueError("Independent physical audit lacks " + str(sorted(need-set(x))))
    x = x.copy()
    x["date"] = pd.to_datetime(x.date).dt.normalize()
    x["grid_id"] = x.grid_id.astype(str)
    if x.duplicated(["grid_id", "date"]).any():
        raise ValueError("Conflicting physical labels for grid-day")
    for field in ["valid_observation", "source_independent", "pluvial_confirmed"]:
        if not x[field].isin([0, 1, True, False]).all():
            raise ValueError("Physical field must be verified boolean: " + field)
    eligible = x.loc[x.valid_observation.eq(1) & x.source_independent.eq(1) &
                     x.pluvial_confirmed.eq(1)].copy()
    if eligible.empty:
        return {"status": "NOT_AVAILABLE", "reason": "No verified independent pluvial cases"}, pd.DataFrame()
    if not eligible.flood_observed.isin([0, 1, True, False]).all():
        raise ValueError("Physical class label must be 0/1")
    if eligible.sensor.isna().any() or eligible.sensor.astype(str).str.strip().eq("").any():
        raise ValueError("Sensor source required")
    z = eligible.merge(predictions[["grid_id", "date", "prediction"]], on=["grid_id", "date"],
                       how="inner", validate="one_to_one")
    npositive = int(z.flood_observed.eq(1).sum())
    nnegative = int(z.flood_observed.eq(0).sum())
    info = dict(status="INSUFFICIENT_CLASS_SUPPORT", matched_verified=len(z),
                physical_positives=npositive, physical_negatives=nnegative,
                original_audited_rows=len(x))
    if min(npositive, nnegative) >= 10:
        y = z.flood_observed.astype(int).to_numpy()
        p = z.prediction.to_numpy()
        info.update(status="EXTERNAL_RANKING_ONLY",
                    roc_auc_external=float(roc_auc_score(y, p)),
                    pr_auc_external=float(average_precision_score(y, p)),
                    note="Independent observed event discrimination; not an absolute risk calibration")
    return info, z


def _figure(path, results, preds, physical, df, m4, split):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(15, 9), layout="constrained")
    gs = fig.add_gridspec(2, 6, height_ratios=[.83, 1.1])
    a = fig.add_subplot(gs[0, :2])
    b = fig.add_subplot(gs[0, 2:4])
    c = fig.add_subplot(gs[0, 4:])
    d = fig.add_subplot(gs[1, :3])
    e = fig.add_subplot(gs[1, 3:])
    a.set_axis_off()
    a.set_title("a | Observation-aware design", loc="left", fontweight="bold")
    a.text(.03, .86, "IMERG-defined storm exposures", transform=a.transAxes, fontsize=11)
    a.text(.03, .66, "GF10 + terrain + land-cover epochs", transform=a.transAxes, fontsize=10)
    a.text(.03, .46, "News positives vs UNLABELED", transform=a.transAxes, fontsize=10)
    a.text(.03, .26, "Hold out geography + storms", transform=a.transAxes, fontsize=10)
    a.text(.03, .06, "External flood/non-flood audit", transform=a.transAxes, fontsize=10)
    for y in [.76, .56, .36, .16]:
        a.annotate("", xy=(.5,y-.065), xytext=(.5,y+.025),
                   xycoords="axes fraction", arrowprops={"arrowstyle":"->","lw":1})
    primary = results.loc[(results.split=="unseen_city_and_storm") & (results.seed==42)]
    b.set_title("b | Ablation on fixed test set", loc="left", fontweight="bold")
    if len(primary):
        order=list(MODELS)
        v=[primary.loc[primary.model==name,"pr_auc_proxy"].iloc[0]
           if (primary.model==name).any() else np.nan for name in order]
        b.barh([n.split("_")[0] for n in order][::-1], np.asarray(v)[::-1])
        b.set_xlim(0, 1)
        b.set_xlabel("PR-AUC, reported-news proxy")
    c.set_title("c | Cross-domain transfer", loc="left", fontweight="bold")
    pivot = results.loc[results.model=="M4_growth"].pivot_table(
        index="split", columns="seed", values="pr_auc_proxy")
    if not pivot.empty:
        values=pivot.to_numpy()
        im=c.imshow(values, aspect="auto", vmin=0, vmax=1, cmap="viridis")
        c.set_yticks(np.arange(len(pivot.index)), [s.replace("_and_storm","") for s in pivot.index], fontsize=8)
        c.set_xticks(np.arange(len(pivot.columns)), [str(s) for s in pivot.columns])
        c.set_xlabel("Random seed")
        fig.colorbar(im, ax=c, shrink=.68)
    d.set_title("d | Proxy calibration / physical audit", loc="left", fontweight="bold")
    xx=np.linspace(0,1,10)
    d.plot(xx, xx, "--", color=".55", lw=1, label="Identity (proxy)")
    if not preds.empty:
        q=preds.copy()
        q["bin"]=np.minimum((q.prediction*10).astype(int),9)
        cal=q.groupby("bin").agg(p=("prediction","mean"), y=("observed_news_onset","mean"))
        d.plot(cal.p,cal.y,marker="o",label="Withheld city+storm, M4")
    d.text(.05,.94,"Independent physical: "+physical["status"],transform=d.transAxes,
           va="top",fontsize=9)
    d.set(xlim=(0,1),ylim=(0,1),xlabel="Model score",ylabel="Observed news-report frequency")
    d.legend(fontsize=8,loc="lower right")
    e.set_title("e | Terrain x surface: observed response",loc="left",fontweight="bold")
    _, test=split
    sub=df.iloc[test].copy()
    sub=sub.loc[sub.rain_24h_mm>=sub.rain_24h_mm.quantile(.75)].copy()
    if not sub.empty:
        # Observed rates, NOT causal partial dependence or physical thresholds.
        sub["hand_group"]=pd.qcut(sub.hand_m.rank(method="first"), 3, labels=["Low","Mid","High"])
        sub["built_group"]=pd.qcut(sub.built_fraction_2020.rank(method="first"),3,
                                   labels=["Low","Mid","High"])
        matrix=sub.pivot_table(index="hand_group", columns="built_group",
                               values="observed_news_onset", aggfunc="mean", observed=True)
        view=matrix.reindex(index=["Low","Mid","High"],columns=["Low","Mid","High"])
        im=e.imshow(view.to_numpy(float),cmap="magma",vmin=0,vmax=max(.01,float(sub.observed_news_onset.mean()*2)))
        e.set_xticks([0,1,2], ["Low","Mid","High"])
        e.set_yticks([0,1,2], ["Low","Mid","High"])
        e.set_xlabel("GHS built fraction quantile")
        e.set_ylabel("HAND quantile")
        fig.colorbar(im,ax=e,shrink=.7,label="News-onset share")
    fig.suptitle("Figure 2 | Transferability under extreme rainfall — NEWS PROXY / NOT PHYSICAL RISK",
                 fontsize=13,fontweight="bold")
    fig.savefig(path/"Figure2_news_proxy.png",dpi=300,bbox_inches="tight")
    fig.savefig(path/"Figure2_news_proxy.pdf",bbox_inches="tight")
    plt.close(fig)


def run(root, panel, contract, cities=None, grid_cities=None, extended=None,
        physical=None, tag="fig2_v1", seeds=(42,43,44), require_physical=False,
        resilience_static=None):
    c = validate_contract(contract)
    df = prepare(panel, cities, grid_cities, extended, resilience_static)
    if not tag.startswith("fig2_") or "/" in tag or "\\" in tag or tag in (".", ".."):
        raise ValueError("Tag must be a simple fig2_* directory")
    out=safe_output(root, "outputs/"+tag)
    if out.exists():
        raise FileExistsError("Refusing to overwrite immutable Figure2 result: "+str(out))
    for col in MODELS["M4_growth"]:
        if col not in df:
            raise ValueError("Cannot claim M0-M4 complete; missing "+col+". Export new GF10 factors first")
        x=pd.to_numeric(df[col], errors="coerce")
        if not np.isfinite(x).all():
            raise ValueError("Non-finite predictive feature: "+col+"; no imputation/zero fill")
        df[col]=x.astype(float)
    for col in ["urban_fraction_2020","vegetation_fraction","built_fraction_2020",
                "built_neighbor_density","built_fragmentation"]:
        if df[col].lt(0).any() or df[col].gt(1).any():
            raise ValueError("Fraction metric outside [0,1]: "+col)
    if df.rain_24h_mm.lt(0).any() or df.rain_3h_mm.lt(0).any() or df.api_7d_mm.lt(0).any():
        raise ValueError("Negative rainfall")
    # M5 is a separately labelled sensitivity scenario; not an identifiable correction.
    m5 = "reporting_propensity" in df
    if m5:
        p=pd.to_numeric(df.reporting_propensity, errors="coerce")
        if p.isna().any() or not p.between(.05,1).all():
            raise ValueError("Independent reporting propensity must fall within [0.05,1]")
        if not c.get("reporting_propensity_external_audit", False):
            raise ValueError("M5 weights require separate external coverage audit declared in contract")
        df["reporting_propensity"]=p.astype(float)
    # Optional ERA5 and hydrology tests are separately labelled; the main
    # M0-M5 comparison remains on the same withheld rows as before.
    optional={}
    met=["rain_24h_mm","rain_3h_mm","api_7d_mm",
         "soil_water_0_7cm","soil_water_7_28cm","temperature_2m_c"]
    if set(met)<=set(df):
        optional["M0b_rain_ERA5"]=met
    hydro=list(MODELS["M1_terrain"])+["upstream_area_km2","elevation_m"]
    if set(hydro)<=set(df):
        optional["M1b_terrain_runoff"]=hydro
    green=list(MODELS["M3_form"])+["tree_fraction","wetland_fraction","water_fraction"]
    if set(green)<=set(df):
        optional["M3b_green_blue"]=green
    for model,columns in optional.items():
        for key in columns:
            if not np.isfinite(pd.to_numeric(df[key],errors="coerce")).all():
                raise ValueError("Missing optional indicator for "+model+": "+key)
    experiments={**MODELS,**optional}
    y=df.observed_news_onset.to_numpy(dtype=int)
    records=[]; failed=[]; main_preds=None; main_model=None; main_split=None
    for domain, field in GROUPS:
        for seed in seeds:
            try:
                i,j=_split(df,field,int(seed))
            except ValueError as err:
                failed.append(dict(split=domain,seed=int(seed),reason=str(err)))
                continue
            if domain=="unseen_city_and_storm" and seed==seeds[0]:
                main_split=(i,j)
            for name, cols in experiments.items():
                if name=="M5_selection_sensitivity" and not m5:
                    continue
                X=df[cols].to_numpy(dtype=float)
                weights=None
                if name=="M5_selection_sensitivity":
                    # Inverse observation propensity: scenario analysis, not true risk identification.
                    weights=1/df.reporting_propensity.iloc[i].to_numpy(dtype=float)
                    weights=weights/weights.mean()
                model=_fit(X[i],y[i],int(seed),weights)
                pred=model.predict_proba(X[j])[:,1]
                lo,hi=_bootstrap(y[j],pred,df.iloc[j].storm_id,int(seed))
                records.append(dict(split=domain,seed=int(seed),model=name,n_train=len(i),
                                    n_test=len(j),test_news_positives=int(y[j].sum()),
                                    train_cities=int(df.iloc[i].city_id.nunique()),
                                    test_cities=int(df.iloc[j].city_id.nunique()),
                                    train_storms=int(df.iloc[i].storm_id.nunique()),
                                    test_storms=int(df.iloc[j].storm_id.nunique()),
                                    ci_low_pr_auc=lo,ci_high_pr_auc=hi,**_score(y[j],pred)))
                if domain=="unseen_city_and_storm" and seed==seeds[0] and name=="M4_growth":
                    main_model=model
                    main_preds=df.iloc[j][["grid_id","date","storm_id","city_id","observed_news_onset"]].copy()
                    main_preds["prediction"]=pred
    if main_model is None:
        raise ValueError("No valid joint held-out city + storm split; cannot publish Figure2")
    result=pd.DataFrame(records)
    external_qc, external_matches=_physical(df,main_preds,physical)
    if require_physical and external_qc["status"]!="EXTERNAL_RANKING_ONLY":
        raise ValueError("Publication gate: independently verified pluvial flood AND non-flood evidence missing")
    out.mkdir(parents=True,exist_ok=False)
    result.to_csv(out/"fig2_ablation_generalization.csv",index=False)
    pd.DataFrame(failed).to_csv(out/"fig2_invalid_splits.csv",index=False)
    main_preds.to_parquet(out/"fig2_heldout_news_proxy_predictions.parquet",index=False)
    if not external_matches.empty:
        external_matches.to_csv(out/"fig2_external_matched_audit.csv",index=False)
    _figure(out,result,main_preds,external_qc,df,main_model,main_split)
    quality={"status":"DRAFT_NEWS_PROXY_ONLY" if external_qc["status"]!="EXTERNAL_RANKING_ONLY"
             else "EXTERNAL_RANKING_VERIFIED_NOT_CALIBRATED_RISK",
             "n_exposures":len(df),"n_news_positive_exposures":int(y.sum()),
             "n_cities":int(df.city_id.nunique()),"n_meteorological_storm_ids":int(df.storm_id.nunique()),
             "models_completed":list(result.model.unique()),
             "optional_resilience_ablation_models":list(optional),
             "actual_physical_risk_calibration":False,
             "m5_status":"EXTERNAL_PROPENSITY_SENSITIVITY_ONLY" if m5 else "NOT_IDENTIFIABLE_WITHOUT_EXTERNAL_COVERAGE",
             "valid_splits":len(set(zip(result.split,result.seed))),
             "invalid_splits":failed,"physical_validation":external_qc,"weather_contract":c,
             "paper_claim_boundary":PROXY_NOTE,
             "input_sha256":{key:hashlib.sha256(Path(value).read_bytes()).hexdigest()
                            for key,value in [("weather_contract",contract)]},
             "no_actual_flood_risk_probability":True}
    atomic_json(out/"fig2_qc_and_provenance.json",quality)
    return quality


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--panel",type=Path,required=True)
    p.add_argument("--contract",type=Path,required=True)
    p.add_argument("--cities",type=Path)
    p.add_argument("--grid-cities",type=Path)
    p.add_argument("--extended",type=Path)
    p.add_argument("--resilience-static",type=Path,help="Optional audited GF10 static resilience indicators")
    p.add_argument("--physical",type=Path)
    p.add_argument("--tag",default="fig2_v1")
    p.add_argument("--require-physical",action="store_true")
    args=p.parse_args(argv)
    result=run(args.root,args.panel,args.contract,args.cities,args.grid_cities,
               args.extended,args.physical,args.tag,require_physical=args.require_physical,
               resilience_static=args.resilience_static)
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":
    main()
