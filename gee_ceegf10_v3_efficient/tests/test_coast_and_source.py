from pathlib import Path
import pytest
from ceeprodgee.coast import discover_gshhg

def test_coast_4_files_required(tmp_path):
 for n in [1,2,3]: (tmp_path/f'GSHHS_f_L{n}.shp').touch()
 with pytest.raises(FileNotFoundError):discover_gshhg(tmp_path)
 (tmp_path/'GSHHS_f_L4.shp').touch()
 files=discover_gshhg(tmp_path)
 assert len(files)==4

def test_ee_model_is_import_safe_without_credentials():
 from ceeprodgee import ee_model
 assert len(ee_model.TRANSFORM_10)==6
 assert ee_model.TRANSFORM_10==[10000,0,0,0,-10000,0]
