from pathlib import Path
from ceeprodgee.cli import configure

def test_windows_gee_launch_scripts_never_use_old_v2_runid():
    root=Path(__file__).resolve().parents[1]
    for name in ('02_submit_pilot_merit.ps1','03_submit_pilot_worldcover.ps1','05_event_method_only.ps1'):
        src=(root/'scripts'/name).read_text(encoding='utf8')
        assert 'CEE_GF10_M1M2_PRODUCTION_20261104_V2' not in src
        assert '--confirm $RunId' in src
        assert 'production.json' in src
