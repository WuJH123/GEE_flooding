import csv
import json
import math
from pathlib import Path
import pytest
from ceeprodgee import grid,edge_safe,contract


def test_user_failed_tile_becomes_compact_three_grid_ids():
    cells=[(-1736,-235),(-1735,-235),(-1736,-234)]
    d=grid.tile_export_geometry(-1740,-240,10,cells)
    assert d['kind']=='edge_csv'
    assert d['expected_cells']==3
    assert d['roi'][0]==-17360000
    assert d['roi'][2]==-17340000
    assert d['roi'][2]-d['roi'][0]==20000
    assert d['grid_ids']==['-1736_-235','-1736_-234','-1735_-235']


def test_central_wuhan_no_boundary_fallback():
    d=grid.tile_export_geometry(1097,367,10,[(1097,367),(1102,372)])
    assert d['kind']=='geotiff'
    assert d['roi']==[10974900.0,3674900.0,11065100.0,3765100.0]


def test_domain_limit_auto_uses_table_even_when_sparse_land():
    d=grid.tile_export_geometry(1730,0,10,[(1735,0),(1736,0)])
    assert d['kind']=='edge_csv'
    assert d['roi'][2] <= grid.EPSG6933_X_LIMIT


def test_edge_centres_outside_domain_hard_fail():
    with pytest.raises(ValueError,match='(centre outside|No portion)'):
        grid.tile_export_geometry(-1740,0,10,[(-1739,0)])


def test_duplicate_or_outside_cells_fails():
    with pytest.raises(ValueError,match='duplicate'):
        grid.tile_export_geometry(0,0,10,[(2,3),(2,3)])
    with pytest.raises(ValueError,match='outside'):
        grid.tile_export_geometry(0,0,10,[(-1,4)])


def fake_csv(path,ids):
    with open(path,'w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['grid_id',*contract.MERIT_BANDS]);w.writeheader()
        for i,id in enumerate(ids):
            r={key:1. for key in contract.MERIT_BANDS}
            r.update({'grid_id':id,'merit_upa_max_km2':100.,
                      'merit_upa_p90_km2':50.,'merit_upa_max_log1p':math.log1p(100),
                      'merit_hand_p10_m':.1,'merit_hand_p50_m':1.0,'merit_hand_p90_m':2.0,
                      'merit_hand_le2_fraction_valid':.1,
                      'merit_hand_le5_fraction_valid':.2,
                      'merit_hand_le10_fraction_valid':.3})
            w.writerow(r)


def test_edge_csv_manifest_works_and_no_data_accepted_as_valid(tmp_path):
    p=tmp_path/'edge.csv';ids=['-1736_-235','-1735_-235','-1736_-234'];fake_csv(p,ids)
    q=edge_safe.check_edge_csv(p,ids)
    assert q['n_land_ids']==3 and q['n_bands']==16
    assert q['publication_ready'] is False
    with pytest.raises(ValueError,match='exactly match'):
        edge_safe.check_edge_csv(p,ids+['missing'])
    with p.open('a',encoding='utf8') as f:f.write('invalid,,,,\n')
    with pytest.raises(ValueError):edge_safe.check_edge_csv(p,ids)


def test_rejected_production_can_only_be_quarantined_explicitly():
    a=[{'key':edge_safe.KNOWN_BAD_KEY,'state':'SUCCEEDED','local_qc_pass':False}]
    with pytest.raises(ValueError):
        edge_safe.validate_reject_and_quarantine(a,edge_safe.KNOWN_BAD_KEY,'x')
    name=edge_safe.validate_reject_and_quarantine(a,edge_safe.KNOWN_BAD_KEY,edge_safe.BAD_ACK)
    assert name.endswith('_edgefix1')
    assert a[0]['quarantine']['do_not_use_data'] is True
    assert a[0]['local_qc_pass'] is False
    with pytest.raises(ValueError):
        edge_safe.validate_reject_and_quarantine(a,edge_safe.KNOWN_BAD_KEY,edge_safe.BAD_ACK)


def test_prior_quarantined_not_automatically_accepted():
    rejected={'key':edge_safe.KNOWN_BAD_KEY,'operation':'o','state':'SUCCEEDED',
              'local_qc_pass':False,'superseded_by':edge_safe.KNOWN_BAD_KEY+'_edgefix1',
              'quarantine':{'reason':'bad_shape'}}
    accepted={'key':rejected['superseded_by'],'operation':'p','local_qc_pass':True}
    live=lambda x:{'state':'SUCCEEDED'}
    with pytest.raises(RuntimeError,match='no approved QC'):
        edge_safe.guarded_previous_tasks([rejected],live)
    edge_safe.guarded_previous_tasks([rejected,accepted],live)


def test_merge_strictly_rejects_overlapping_grid_ids():
    with pytest.raises(ValueError,match='Duplicate'):
        edge_safe.compact_merge_rows([['a','b'],['b','c']])


def test_merit_edge_submission_uses_table_not_image_export(tmp_path,monkeypatch):
    """End-to-end fake EE dispatch: edge source uses exact cells + table CSV only."""
    import pandas as pd
    from types import SimpleNamespace
    from ceeprodgee import cli,ledger,ee_model

    log=[]
    class MockTask:
        id='MOCK_TASK_001'
        def start(self):log.append('started')
        def status(self):return {'state':'READY','name':'projects/mock/operations/MOCK_TASK_001'}
    class FakeImage:
        def unmask(self,*args):return self
        def sampleRegions(self,**kw):
            log.append(('sampleRegions',kw))
            return self
    class FakeEE:
        @staticmethod
        def FeatureCollection(items):return items
        @staticmethod
        def Feature(geometry,props):return (geometry,props)
        class Geometry:
            @staticmethod
            def Rectangle(*args,**kwargs):
                log.append(('rectangle',args[0]))
                return ('rectangle',args[0])
            @staticmethod
            def Point(*args,**kwargs):return ('point',args[0])
        @staticmethod
        def Projection(*args):return ('projection',args)
        class batch:
            class Export:
                class image:
                    @staticmethod
                    def toDrive(**kwargs):
                        raise AssertionError('Edge cell never uses image export')
                class table:
                    @staticmethod
                    def toDrive(**kwargs):
                        log.append(('table_export',kwargs))
                        return MockTask()
    monkeypatch.setattr(cli,'_ee',lambda conf:FakeEE)
    monkeypatch.setattr(ee_model,'merit',lambda *a,**kw:FakeImage())
    # A single accepted Wuhan pilot in existing ledger satisfies history gates.
    prior=[{'key':'merit_1097_367_10','operation':'projects/mock/operations/OLD',
            'state':'SUCCEEDED','local_qc_pass':True,'eecu_hours':0.01}]
    monkeypatch.setattr(ledger,'read_json',lambda path,default=None:prior)
    monkeypatch.setattr(ledger,'task_state',lambda ee,op:{'state':'SUCCEEDED','eecu_hours':0.01})
    monkeypatch.setattr(ledger,'atomic_json',lambda path,obj:log.append(('wrote_ledger',obj)))
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    plan=tmp_path/'merit_all.csv'
    pd.DataFrame([{'tile_key':'merit_-1740_-240_10','tile_x0':-1740,'tile_y0':-240,
                   'tile_size':10,'family':'merit','n_work_pixels':100}]).to_csv(plan,index=False)
    ids=['-1736_-235','-1735_-235','-1736_-234']
    subset=pd.DataFrame([{'grid_id':v,'grid_x':int(v.split('_')[0]),'grid_y':int(v.split('_')[1])} for v in ids])
    geom=grid.tile_export_geometry(-1740,-240,10,subset[['grid_x','grid_y']].itertuples(index=False,name=None))
    args=SimpleNamespace(plan=str(plan),repair_ack=None,bad_tif=None)
    conf={'project':'mock','run_id':'TEST','drive_folder':'mock','output_crs_wkt':'MOCK_WKT',
          'static_spend_limit_h':700.,'grid_sha256':'sha'}
    cli._submit_merit_edge(args,conf,None,subset,geom)
    table=[item for item in log if isinstance(item,tuple) and item[0]=='table_export']
    assert len(table)==1
    assert table[0][1]['fileFormat']=='CSV'
    assert len(table[0][1]['selectors'])==17
    samples=[item for item in log if isinstance(item,tuple) and item[0]=='sampleRegions']
    assert len(samples)==1
    assert samples[0][1]['geometries'] is False
    assert len(samples[0][1]['collection'])==3
    assert 'started' in log


def test_static_merge_skips_method_only_ledger_row_without_family():
    registry=[{'key':'event_method_20230601','kind':'EVENT_METHOD_ONLY','local_qc_pass':True},
              {'key':'merit_1097_367_10','family':'merit','local_qc_pass':True},
              {'key':'merit_-1740_-240_10','family':'merit','local_qc_pass':False}]
    out=edge_safe.accepted_static_records(registry,'merit')
    assert [r['key'] for r in out]==['merit_1097_367_10']
