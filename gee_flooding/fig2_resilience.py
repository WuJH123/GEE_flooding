"""Figure2 resilience indicator metadata, local-source READ-ONLY inventory and QA.

Indicators are grouped by hazard, exposure, sensitivity, adaptation proxy,
and reporting selection. Structural proxies are not measured drainage capacity.
Nothing from 20km historic outputs is silently transplanted into GF10.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .paths import safe_output,atomic_json

# name, pillar, source, unit, native_scale_m, temporal_epoch, method, training role
SPEC = [
 ("rain_3h_mm","hazard","NASA IMERG V07","mm",11132,"daily UTC","maximum 3h rolling sum", "M0"),
 ("rain_24h_mm","hazard","NASA IMERG V07","mm",11132,"daily UTC","daily sum", "M0"),
 ("api_7d_mm","hazard","NASA IMERG V07","mm",11132,"prior 7 days","previous 7d sum", "M0"),
 ("soil_water_0_7cm","sensitivity","ERA5-Land","m3/m3",11132,"previous 24h","mean hourly prior", "optional"),
 ("soil_water_7_28cm","sensitivity","ERA5-Land","m3/m3",11132,"previous 24h","mean hourly prior", "optional"),
 ("temperature_2m_c","hazard","ERA5-Land","degC",11132,"previous 24h","mean prior", "optional"),
 ("hand_m","sensitivity","MERIT Hydro hnd","m",93,"static","area-weighted GF10 mean", "M1"),
 ("elevation_m","sensitivity","MERIT Hydro elv","m",93,"static","area-weighted GF10 mean", "optional"),
 ("slope_deg","sensitivity","MERIT Hydro elv","degree",93,"static","mean elevation slope", "M1"),
 ("upstream_area_km2","sensitivity","MERIT Hydro upa","km2",93,"static","mean upstream drainage area", "optional"),
 ("river_water_fraction","sensitivity","MERIT Hydro wat","fraction",93,"static","surface water channel proxy", "optional"),
 ("urban_fraction_2020","exposure","2020 GHS-SMOD frozen GF10","fraction",10000,"2020","fixed frozen GF10", "M2"),
 ("built_fraction_2020","exposure","GHSL BUILT-S","fraction",100,"2020","mean of built_surface/10000", "M3"),
 ("built_fraction_2000","exposure","GHSL BUILT-S","fraction",100,"2000","historical baseline area share for M4 growth identity", "M4 QC"),
 ("built_nres_fraction_2020","exposure","GHSL BUILT-S NRES","fraction",100,"2020","mean of built_surface_nres/10000", "optional"),
 ("population_count_2020","exposure","GHSL GHS-POP","people",100,"2020","GF10 sum; validate resampling/conservation", "optional"),
 ("built_area_km2_2020","exposure","GHSL BUILT-S","km2",100,"2020","GF10 sum; validate resampling/conservation", "optional"),
 ("built_nres_area_km2_2020","exposure","GHSL BUILT-S NRES","km2",100,"2020","GF10 sum", "optional"),
 ("vegetation_fraction","adaptation_proxy","ESA WorldCover v200","fraction",10,"2021","tree+shrub+grass+crop+wetland+mangrove", "M2"),
 ("tree_fraction","adaptation_proxy","ESA WorldCover v200","fraction",10,"2021","tree-share GF10", "optional"),
 ("grass_fraction","adaptation_proxy","ESA WorldCover v200","fraction",10,"2021","grass-share GF10", "optional"),
 ("cropland_fraction","adaptation_proxy","ESA WorldCover v200","fraction",10,"2021","crop-share GF10", "optional"),
 ("wetland_fraction","adaptation_proxy","ESA WorldCover v200","fraction",10,"2021","wetland+mangrove GF10", "optional"),
 ("water_fraction","sensitivity","ESA WorldCover v200","fraction",10,"2021","permanent water share", "optional"),
 ("bare_fraction","sensitivity","ESA WorldCover v200","fraction",10,"2021","bare ground share", "optional"),
 ("built_neighbor_density","exposure","GHSL BUILT-S","fraction",100,"2020","focal mean built fraction 1.5km", "M3"),
 ("built_fragmentation","sensitivity","GHSL BUILT-S","fraction",100,"2020","focal std built fraction 1km; not patch metrics", "M3"),
 ("built_growth_2000_2020","exposure","GHSL BUILT-S","fraction delta",100,"2000-2020","difference of shares, not growth of 2021-25", "M4"),
 ("n_obs_24h","data_quality","NASA IMERG V07","images",11132,"daily UTC","expected >=48", "QC"),
 ("n_obs_7d","data_quality","NASA IMERG V07","images",11132,"prior 7d","expected >=336", "QC"),
 ("flood_fraction_observable","external_physical_context","GFD MODIS","fraction",250,"2000-2018 only","flood fraction among observable nonpermanent land", "external only"),
 ("observable_fraction","data_quality","GFD MODIS clear_views","fraction",250,"2000-2018 only","availability mask fraction", "QC"),
 ("internet_use_country_year","reporting_selection","Local reporting-bias data","percent",None,"by year","must verify source and mapping", "not_m5_until_audited"),
 ("road_density_km_km2","adaptation_proxy","GRIP/Roads locally held","km/km2",None,"varies","potential access proxy; roads can exacerbate runoff", "optional"),
 ("travel_time_city_min","adaptation_proxy","Global travel time local","minutes",None,"2015","accessibility proxy; not emergency capacity", "optional"),
 ("night_lights","reporting_selection","Local nightlight","radiance",None,"2022","visibility/surveillance proxy, temporal caveat", "optional"),
 ("gdp_per_capita","vulnerability","Local global GDP + GHS POP","currency/person",None,"varies","socioeconomic context, NOT engineering drainage", "optional"),
 ("impervious_fraction","sensitivity","Local GAIA/GISD30","fraction",30,"2020/2024","harmonize epoch and source before use", "optional"),
 ("built_volume_m3","exposure","Local GHSL BUILT-V","m3",100,"multi epoch","sum per GF10 only if verified", "optional"),
]

HISTORICAL_LOCAL = {
 "original_groundsource":r"E:\GEE_flooding\data\raw\groundsource_2026.parquet",
 "frozen_GF10":r"E:\GEE_flooding\data\reference\grid10_urban_2020.parquet",
 "mapped_news":r"E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet",
 "fig1_city_crosswalk":r"E:\GEE_flooding\outputs\fig1_v2\fig1_grid_dominant_ucdb.parquet",
 "old_imerg_era5_check_only":r"E:\Global_flooding\Climate_all",
 "old_merit_check_only":r"E:\Global_flooding\MERIT_all",
 "old_HAND_check_only":r"E:\Global_flooding\external_data\HAND",
 "old_ghsl_built_s_check_only":r"E:\数据集\全球人类居住层GHS built-up surface (R2023)",
 "old_ghsl_built_v_check_only":r"E:\数据集\全球GHS-BUILT-V建筑体积数据集",
 "old_WorldPop_check_only":r"E:\数据集\Worldpop人口统计数据",
 "old_roads_check_only":r"E:\Global_flooding\external_data\Roads",
 "old_reporting_check_only":r"E:\Global_flooding\external_data\Reporting_bias",
 "old_gfd_QUEUED_not_evidence":r"E:\Global_flooding\grid10\gfd_physical_v3",
 "old_CN_Floods_check_only":r"E:\数据集\CN-Floods（2006–2024，中国洪水事件级遥感数据）30m",
}


def catalog():
    rows=[dict(name=name,pillar=pillar,source=source,unit=unit,native_scale_m=native,
               epoch=epoch,aggregation_to_GF10=method,model_role=role,
               target_resolution_m=10000,
               note=("Proxy for green-blue capacity, not measured infrastructure adaptation"
                     if pillar=="adaptation_proxy" else
                     "This native-resolution field is aggregated, not a new 10km observation"))
          for name,pillar,source,unit,native,epoch,method,role in SPEC]
    d=pd.DataFrame(rows)
    if d.name.duplicated().any():raise AssertionError("Duplicate indicator name")
    return d


def inventory(root):
    """Return path existence only; deliberately do not trust old 20km products."""
    import os
    r=str(Path(root).resolve())
    a=[]
    for name,p in HISTORICAL_LOCAL.items():
        if p.startswith(r):
            real=Path(p)
        else:
            real=Path(p)
        a.append(dict(dataset=name,path=str(real),exists=real.exists(),
                      type="directory" if real.is_dir() else "file" if real.is_file() else "missing",
                      usable_GF10_directly=bool(name in
                        ("original_groundsource","frozen_GF10","mapped_news","fig1_city_crosswalk"))))
    return pd.DataFrame(a)


def write(root,tag="fig2_inputs_v2"):
    if not tag.startswith("fig2_") or "/" in tag or "\\" in tag:
        raise ValueError("Version tag must start with fig2_ without separators")
    out=safe_output(root,"reports/"+tag)
    if out.exists():raise FileExistsError("Refuse to overwrite audit directory "+str(out))
    out.mkdir(parents=True,exist_ok=False)
    table=catalog();local=inventory(root)
    table.to_csv(out/"fig2_GF10_indicator_dictionary.csv",index=False)
    local.to_csv(out/"fig2_local_readonly_inventory.csv",index=False)
    qc=dict(status="CATALOG_AND_EXISTENCE_ONLY_NOT_EXTRACTED",
            indicator_count=len(table), local_source_count=len(local),
            local_present=int(local.exists.sum()),global_complete=False,
            physical_validated=False,
            warning="Existing historic 20km data are not compatible with GF10 until grid-id, units and epoch audit")
    atomic_json(out/"fig2_inventory_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--tag",default="fig2_inputs_v2")
    a=p.parse_args(argv)
    print(json.dumps(write(a.root,a.tag),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
