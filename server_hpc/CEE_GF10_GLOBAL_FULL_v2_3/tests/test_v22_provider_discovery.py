"""Regression tests for actual nested HydroATLAS FileGDB and multi-theme UCDB.

These are synthetic fixtures only: real large global GDB source content must
still be validated on the remote Windows server before publishing metrics.
"""
from pathlib import Path
import json
import pytest


def _fake_gdb(root,kind):
    from ceeprod.discover import _real_gdb
    outer=root/'data/staged/cee_all'/f'{kind}ATLAS_Data_v10.gdb'
    inner=outer/f'{kind}ATLAS_v10.gdb'
    inner.mkdir(parents=True,exist_ok=True)
    (outer/'HydroATLAS_TechDoc_v10.pdf').write_bytes(b'PDF fake fixture')
    (inner/'a00000001.gdbtable').write_bytes(b'synthetic FileGDB marker')
    (inner/'a00000001.gdbtablx').write_bytes(b'synthetic index')
    assert not _real_gdb(outer)
    assert _real_gdb(inner)
    return outer,inner


def test_nested_gdb_auto_discovery_excludes_outer_container(tmp_path,monkeypatch):
    from ceeprod import discover
    import pyogrio
    basinwrap,basin=_fake_gdb(tmp_path,'Basin')
    riverwrap,river=_fake_gdb(tmp_path,'River')
    paths=discover._file_sources(tmp_path/'data/staged/cee_all')
    assert basin in paths and river in paths
    assert basinwrap not in paths and riverwrap not in paths

    def layers(path):
        if str(path)==str(basin):return [('BasinATLAS_v10_lev06','Polygon'),('BasinATLAS_v10_lev07','MultiPolygon')]
        if str(path)==str(river):return [('RiverATLAS_v10','LineString')]
        raise RuntimeError('Called invalid outer GDB wrapper!')
    def info(path,layer):
        return dict(fields=['HYBAS_ID'] if 'Basin' in layer else ['HYRIV_ID'],
                    crs='EPSG:4326',features=1200)
    monkeypatch.setattr(pyogrio,'list_layers',layers)
    monkeypatch.setattr(pyogrio,'read_info',info)
    b=discover.discover_family(tmp_path,'basin')
    r=discover.discover_family(tmp_path,'river')
    assert Path(b.path)==basin and b.layer=='BasinATLAS_v10_lev07'
    assert Path(r.path)==river and r.layer=='RiverATLAS_v10'
    assert b.id_field=='HYBAS_ID' and r.id_field=='HYRIV_ID'


def _theme_file(tmp_path):
    from ceeprod.discover import _file_sources
    p=tmp_path/'data/staged/cee_all/GHS_UCDB_GLOBE_R2024A_V1_2.gpkg'
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fake GPkg; mocked metadata')
    assert p in _file_sources(p.parent)
    return p


def test_ucdb_six_theme_tie_resolves_to_geography(tmp_path,monkeypatch):
    from ceeprod import discover
    import pyogrio
    p=_theme_file(tmp_path)
    themes=['CLIMATE','EMISSIONS','EXPOSURE','GENERAL_CHARACTERISTICS','GEOGRAPHY','GHSL']
    names=[f'GHSL_UCDB_THEME_{v}_GLOBE_R2024A' for v in themes]
    monkeypatch.setattr(pyogrio,'list_layers',lambda path:[(v,'MultiPolygon') for v in names])
    monkeypatch.setattr(pyogrio,'read_info',lambda path,layer:dict(fields=['ID_UC_G0','A','B'],crs='ESRI:54009',features=11422))
    selected=discover.discover_family(tmp_path,'ucdb')
    assert selected.layer=='GHSL_UCDB_THEME_GEOGRAPHY_GLOBE_R2024A'
    extracted=discover.discover_ucdb_themes(tmp_path)
    assert {x.layer for x in extracted}==set(names)
    assert {x.id_field for x in extracted}=={'ID_UC_G0'}


def test_ucdb_theme_attribute_export_dispatches_each_layer(tmp_path,monkeypatch):
    from ceeprod import discover,source_attributes
    import pyogrio
    _theme_file(tmp_path)
    names=[f'GHSL_UCDB_THEME_{v}_GLOBE_R2024A' for v in ('GEOGRAPHY','CLIMATE','EMISSIONS')]
    monkeypatch.setattr(pyogrio,'list_layers',lambda path:[(v,'Polygon') for v in names])
    monkeypatch.setattr(pyogrio,'read_info',lambda path,layer:dict(fields=['ID_UC_G0','CLIMATE_VAR'],crs='EPSG:4326',features=7))
    calls=[]
    def mockexport(outroot,source,family,batch_size):
        calls.append((source.layer,str(outroot)))
        return dict(status='ALL_ORIGINAL_SOURCE_ATTRIBUTES_STREAMED',family=family,
                    native_layer=source.layer,native_id=source.id_field,n_source_rows=7,n_fields=2)
    monkeypatch.setattr(source_attributes,'_export_one',mockexport)
    res=source_attributes.run(tmp_path,'ucdb')
    assert res['n_theme_layers']==3
    assert len(calls)==3
    assert all('/themes/' in x[1].replace('\\','/') for x in calls)
    assert (tmp_path/'data/derived/cee_all_global_v2/native_attributes/ucdb/run_qc.json').is_file()


def test_directory_source_identity_detects_modified_gdbtable(tmp_path):
    from ceeprod.shared import file_identity
    _,gdb=_fake_gdb(tmp_path,'Basin')
    first=file_identity(gdb)
    q=gdb/'a00000001.gdbtable'
    q.write_bytes(q.read_bytes()+b'CHANGE')
    second=file_identity(gdb)
    assert first!=second
    assert first['kind']=='filegdb_directory'
    assert second['total_bytes']>first['total_bytes']


def test_required_uncertain_theme_ids_not_silently_guessed(tmp_path,monkeypatch):
    from ceeprod import discover
    import pyogrio
    _theme_file(tmp_path)
    monkeypatch.setattr(pyogrio,'list_layers',lambda p:[('GHSL_UCDB_THEME_GEOGRAPHY_GLOBE_R2024A','Polygon')])
    monkeypatch.setattr(pyogrio,'read_info',lambda path,layer:dict(fields=['NON_OFFICIAL_COL'],crs='EPSG:4326',features=11))
    with pytest.raises(ValueError,match='No documented stable ID'):
        discover.discover_family(tmp_path,'ucdb')


def test_real_openfilegdb_nested_read_roundtrip_if_writable(tmp_path):
    """Actual OGR driver roundtrip, not only monkeypatched catalogue strings."""
    import pyogrio
    import geopandas as gpd
    from shapely.geometry import Polygon,LineString
    from ceeprod.discover import discover_family
    driver=pyogrio.list_drivers().get('OpenFileGDB','')
    if 'w' not in driver:pytest.skip('Installed OpenFileGDB can read but cannot create synthetic fixture')
    root=tmp_path/'data/staged/cee_all'
    for fam,outer,inner,layer,idfield,geom in (
        ('basin','BasinATLAS_Data_v10.gdb','BasinATLAS_v10.gdb',
         'BasinATLAS_v10_lev07','HYBAS_ID',Polygon([(0,0),(1,0),(1,1),(0,1)])),
        ('river','RiverATLAS_Data_v10.gdb','RiverATLAS_v10.gdb',
         'RiverATLAS_v10','HYRIV_ID',LineString([(0,0),(1,1)])),
    ):
        target=root/outer/inner
        target.parent.mkdir(parents=True,exist_ok=True)
        frame=gpd.GeoDataFrame({idfield:['12']},geometry=[geom],crs='EPSG:4326')
        try:
            pyogrio.write_dataframe(frame,target,layer=layer,driver='OpenFileGDB')
        except Exception as exc:
            pytest.skip(f'Installed OpenFileGDB cannot write fixture: {exc}')
        found=discover_family(tmp_path,fam)
        assert Path(found.path)==target and found.layer==layer
        assert found.id_field==idfield and found.count==1
