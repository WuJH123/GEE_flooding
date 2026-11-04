"""Frozen research variable contract. Do not conflate land, valid, full-cell.

MERIT Hydro v1_0_1 is static. ESA WorldCover v200 is 2021 only.
IMERG is 30-min precipitation *rate* (mm/h); ERA5-Land daily sums differ
from daily means. The model response variable is NOT in this module.
"""
from __future__ import annotations

GRID_N=1_395_471
GRID_LAND_KM2=133_095_959.350
CELL_METERS=10000
WC_CODES=(10,20,30,40,50,60,70,80,90,95,100)
MERIT_BANDS=(
'merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2',
'merit_permanent_water_fraction','merit_valid_fraction',
'merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
'merit_hand_le10_fraction_valid','merit_slope_mean_deg',
'merit_slope_le2_fraction_valid','merit_upa_max_km2',
'merit_upa_max_log1p','merit_hand_p10_m','merit_hand_p50_m',
'merit_hand_p90_m','merit_upa_p90_km2')
WC_BANDS=tuple(f'wc_{k}_fraction_fullcell' for k in WC_CODES)+('wc_valid_fraction_fullcell',)+tuple(f'wc_{k}_fraction_land' for k in WC_CODES)+('wc_valid_fraction_land','wc_gshhg_land_fraction_raster')
# Costs below are estimates from 4 submitted 2026-11-04 geographical pilot blocks.
# These are not quotas and cannot be extrapolated without 1st-production-area pilot.
EECU_PER_CELL_BASE={'merit':0.03032543261845906/400,
                    'worldcover':1.9442072465684677/400}
EECU_PER_CELL_UPPER={'merit':0.006480899386935764/100,
                     'worldcover':0.19931905110677084/25}
# M1 upper from high-cost 100-cell Iceland block, includes v2 quantile bands.
EECU_PER_CELL_UPPER['merit']=max(EECU_PER_CELL_BASE['merit'],EECU_PER_CELL_UPPER['merit'])
STATIC_SOURCE={'merit':'MERIT/Hydro/v1_0_1','worldcover':'ESA/WorldCover/v200'}
DYNAMIC_SOURCE={'imerg':'NASA/GPM_L3/IMERG_V07','era5land':'ECMWF/ERA5_LAND/DAILY_AGGR'}

def frozen_bands(family):
    return {'merit':MERIT_BANDS,'worldcover':WC_BANDS}[family]

def budget_projection(n_cells,family):
    if n_cells<0:raise ValueError('negative cells')
    return {'n_cells':n_cells,'family':family,
            'eecu_hours_base':round(n_cells*EECU_PER_CELL_BASE[family],2),
            'eecu_hours_high':round(n_cells*EECU_PER_CELL_UPPER[family],2),
            'calibration':'four 2026-11-04 gate-C blocks; not a prediction guarantee'}
