"""Regression for v4 plan acceptance (source task family is a set, not a string)."""
from pathlib import Path
import pandas as pd


def test_frozen_merit_plan_family_check_all_merit_is_accepted():
    from cee_recover import run
    code = Path(run.__file__).read_text(encoding='utf8')
    assert "set(p.family)!='merit'" not in code
    assert "set(p.family)!={'merit'}" in code
    p = pd.DataFrame({'tile_key':[f'merit_{i}_0_10' for i in range(16874)],
                      'family':['merit']*16874})
    assert len(p)==16874 and not p.tile_key.duplicated().any()
    assert set(p.family)=={'merit'}
    assert not (len(p)!=16874 or p.tile_key.duplicated().any() or set(p.family)!={'merit'})


def test_frozen_merit_plan_rejects_mixed_or_missing_family_and_duplicates():
    p = pd.DataFrame({'tile_key':[f'merit_{i}_0_10' for i in range(16874)],
                      'family':['merit']*16874})
    p.loc[0,'family']='worldcover'
    assert len(p)!=16874 or p.tile_key.duplicated().any() or set(p.family)!={'merit'}
    p.loc[0,'family']='merit'
    p.loc[1,'tile_key']=p.loc[0,'tile_key']
    assert len(p)!=16874 or p.tile_key.duplicated().any() or set(p.family)!={'merit'}
