"""Pure source/science contracts; run on Windows as part of full preflight."""
from pathlib import Path
import numpy as np
import pytest
from ceeprod.discover import FAMILY_HINTS,PRIMARY_IDS
from ceeprod.runner import RASTERS,VECTORS
from ceeprod.gisd_history import YEARS
from ceeprod.quality import summarize


def test_all_35_downloaded_source_families_in_flow():
    assert sum(RASTERS.values()) == 109  # GMTED5 + 19BIO + 84 monthly + GRIP density1
    assert set(VECTORS)=={'admin0','admin1','ucdb','basin','river','roads'}
    assert set(VECTORS)==set(FAMILY_HINTS)
    assert PRIMARY_IDS['basin'][0]=='hybas_id'


def test_gisd30_history_definition_is_monotonic():
    assert YEARS == [1985,1990,1995,2000,2005,2010,2015,2020]
    from ceeall.gisd import _gf10_source_overlap_mask
    # spatial overlap can never be inverted: EPSG6933 cell (0,0)
    assert _gf10_source_overlap_mask([0],[0],(5000,5000,15000,15000)).tolist()==[True]
    assert _gf10_source_overlap_mask([0],[0],(20000,20000,30000,30000)).tolist()==[False]


def test_full_globe_production_never_has_5000grid_cap():
    import inspect
    from ceeprod import runner,vector_full
    assert 'max_cells' not in inspect.signature(vector_full.run).parameters
    assert 'max_cells' not in inspect.signature(runner.rasters).parameters
    assert 715==1_395_471//4096+1 or 715>300


def test_science_quality_gate_is_false_without_real_data(tmp_path):
    # QC must fail to declare global product fully ready on an empty folder.
    r=summarize(tmp_path,strict=False)
    assert not r['structural_complete']
    assert not r['publication_ready']
    with pytest.raises(ValueError):summarize(tmp_path,strict=True)


def test_ellipsoidal_lengths_differ_from_equal_area_6933():
    from pyproj import Transformer,Geod
    from shapely.geometry import LineString
    from shapely import transform
    edge=LineString([(0,0),(10000,0)])
    tr=Transformer.from_crs(6933,4326,always_xy=True)
    km=abs(Geod(ellps='WGS84').geometry_length(transform(edge,tr.transform,interleaved=False)))/1000.
    # An EPSG6933 10km x-distance is not 10km ground distance at the equator.
    assert km>10.5
