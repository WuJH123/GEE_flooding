import numpy as np
from ceeall.gisd import _gf10_source_overlap_mask

def test_touching_cells_are_candidates_and_far_cells_are_not():
    # 10km square at index (0,0) touches [10000,20000] source bbox.
    hit=_gf10_source_overlap_mask(np.array([-4,-1,0,1,2,5]),
                                  np.zeros(6,dtype=int),
                                  (10000,0,20000,10000))
    assert hit.tolist()==[False,False,True,True,True,False]

def test_y_boundaries_correct_north_south():
    hit=_gf10_source_overlap_mask([0]*5,[-2,-1,0,1,2],(0,10000,10000,20000))
    assert hit.tolist()==[False,False,True,True,True]

def test_no_false_inclusion_of_distant_source():
    x=np.array([-140,-1,0,5,140]);y=np.array([0,0,0,0,0])
    assert _gf10_source_overlap_mask(x,y,(800000,800000,820000,820000)).sum()==0
