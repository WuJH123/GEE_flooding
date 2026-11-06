import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import pytest
pytest.importorskip("cee_v8.core")
from cee_v8.pilot_v9 import _reference_compare
import pandas as pd

def test_pilot_output_missing_is_error():
 with pytest.raises((OSError,ImportError)):
  _reference_compare('/absent/source.tif',pd.Series({'land_ids':'0_0'}),pd.DataFrame({'grid_id':['0_0']}))
