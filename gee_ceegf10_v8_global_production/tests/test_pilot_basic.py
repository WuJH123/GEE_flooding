import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]))
import pytest
pytest.importorskip("cee_v8.core")
from cee_v8.pilot_v9 import _reference_compare, _accepted_reference


def test_v7_sparse_global_product_only_measured_cells_are_reference():
    frame=pd.DataFrame({'grid_id':[f'{x}_1' for x in range(864)],
                        'merit_valid_fraction':[0.75]*863+[float('nan')]})
    accepted=_accepted_reference(frame)
    assert len(accepted)==863
    assert '863_1' not in set(accepted.grid_id)

def test_pilot_output_missing_is_error():
 with pytest.raises((OSError,ImportError)):
  _reference_compare('/absent/source.tif',pd.Series({'land_ids':'0_0'}),pd.DataFrame({'grid_id':['0_0']}))
