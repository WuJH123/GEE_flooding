import pandas as pd
import pytest
from ceeprodgee.contract import WC_BANDS,MERIT_BANDS,budget_projection,WC_CODES
from ceeprodgee.grid import block_id,make_plan,tile_bounds

def test_bands_frozen():
 assert len(MERIT_BANDS)==16 and len(WC_BANDS)==25
 assert len(set(MERIT_BANDS))==16 and len(set(WC_BANDS))==25
 assert WC_BANDS[0]=='wc_10_fraction_fullcell'
 assert WC_BANDS[-1]=='wc_gshhg_land_fraction_raster'

def test_budget_protects_full_global():
 assert budget_projection(1_395_471,'worldcover')['eecu_hours_base']>6000
 assert budget_projection(400,'merit')['eecu_hours_base']<0.1

def test_negative_index_blocks_floor_correct():
 assert block_id(-2,573,5)==(-5,570)
 assert block_id(-2,573,10)==(-10,570)
 assert tile_bounds(-5,570,5)==[-50000,5700000,0,5750000]

def test_tile_plan_never_drops_grid_ids():
 frame=pd.DataFrame({'grid_id':['-2_573','-1_573','4_573','100_-1'],
   'grid_x':[-2,-1,4,100],'grid_y':[573,573,573,-1],'land_area_km2':[1,2,3,4]})
 p=make_plan(frame,'worldcover')
 assert p.n_land_cells.sum()==4
 assert p.n_work_pixels.sum()==3*25
 assert len(p)==3
 q=make_plan(frame,'merit')
 assert q.n_land_cells.sum()==4
 assert len(q)==3
 assert make_plan(frame,'worldcover',['-2_573']).n_land_cells.sum()==1
 with pytest.raises(ValueError):make_plan(frame,'worldcover',['NOT_PRESENT'])
