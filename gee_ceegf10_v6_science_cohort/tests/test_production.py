from pathlib import Path
import pytest,pandas as pd,json
from cee_v6 import production


def test_no_global_merit_before_science_gate(monkeypatch,tmp_path):
    monkeypatch.setattr(production,'ROOT',tmp_path)
    with pytest.raises(RuntimeError,match='blocked until'):
        production.static_production_submit('E:/GEE_flooding','merit_1090_360_10')


def test_task_budget_prevents_duplicate_or_unresolved_intents(monkeypatch,tmp_path):
    class EE:
        class data:
            @staticmethod
            def getOperation(k):return {'metadata':{'state':'SUCCEEDED','batchEecuUsageSeconds':200}}
    monkeypatch.setattr(production,'CLOUD',tmp_path/'ledger.json')
    class Job:
        id='x123'
        def start(self):pass
        def status(self):return {'name':'projects/test/operations/x123','state':'READY'}
    from cee_v6.common import save
    save(production.CLOUD,[{'key':'task_old','operation':'opold','local_qc_pass':False}])
    with pytest.raises(RuntimeError,match='not accepted'):
        production._register_task(EE(),{},'another','a.csv',Job(),{})
    save(production.CLOUD,[{'key':'task_old','operation':None,'local_qc_pass':False}],overwrite=True)
    with pytest.raises(RuntimeError,match='Unreconciled'):
        production._register_task(EE(),{},'another','a.csv',Job(),{})


def test_invalid_extra_gf10_false_control_key_rejected(monkeypatch,tmp_path):
    monkeypatch.setattr(production,'ROOT',tmp_path)
    (tmp_path/'plans').mkdir()
    pd.DataFrame([{'request_key':'M0_20220701_10_20','date_utc':'2022-07-01',
        'tile_x0':10,'tile_y0':20,'n_grid_days':1}]).to_csv(tmp_path/'plans'/'event_requests_v6.csv',index=False)
    # Date candidate source must exist, no synthetic weather exposure can be submitted.
    with pytest.raises(FileNotFoundError):
        production.request_submit('E:/GEE_flooding','M0_20220701_10_20',execute=False)
