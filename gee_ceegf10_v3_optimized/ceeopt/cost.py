"""Budget with measured pilot references; NEVER label extrapolation as a guarantee."""
from __future__ import annotations
from .base import GRID_N
MERIT_EECU_400=0.03032543261845906
WC_EECU_400=1.9442072465684677

def projected_hours(cells,per_400):
    if cells<0:raise ValueError('Negative cell count')
    return cells/400*per_400

def budget(cells=GRID_N,static_limit_h=700,**kwargs):
    if static_limit_h<=0:raise ValueError('budget must be positive')
    return {
      'grid_cells':cells, 'merit_4block_reference_h':MERIT_EECU_400,
      'worldcover_4block_reference_h':WC_EECU_400,
      'merit_global_LINEAR_SCENARIO_h':round(projected_hours(cells,MERIT_EECU_400),1),
      'worldcover_global_LINEAR_SCENARIO_h':round(projected_hours(cells,WC_EECU_400),1),
      'worldcover_if_downloaded_official_2021_map_local_GEE_EECU_h':0,
      'static_budget_warning_h':static_limit_h,
      'global_worldcover_gee_authorized':False,
      'note':'Four-region EECU is a scenario only; do not linearly forecast cost as a verified estimate. '
             'Full official WorldCover 2021 Map is 117GB/2651 source tiles, feasible only if download, local pilot QA, disk and network permit.',
    }
