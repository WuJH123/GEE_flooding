"""Regression tests for Windows-stderr logging and stage source recovery."""
from pathlib import Path
from types import SimpleNamespace
import json,sys,zipfile
import pytest


def test_windows_launcher_preserves_full_child_traceback(tmp_path):
    from scripts.run_with_log import run
    child=("import sys;print('BEGIN',flush=True);"
           "sys.stderr.write('Traceback (most recent call last):\\n');"
           "sys.stderr.write('ValueError: REAL_LAST_LINE\\n');"
           "sys.exit(5)")
    log=tmp_path/'all.log'
    assert run([sys.executable,'-c',child],log,echo=False)==5
    content=log.read_text()
    assert 'BEGIN' in content and 'ValueError: REAL_LAST_LINE' in content
    assert 'CHILD_EXIT_CODE=5' in content


def test_doctor_detects_missing_7zip_without_touching_raw(tmp_path,monkeypatch):
    from ceeprod import doctor
    raw=tmp_path/'CEE数据';raw.mkdir()
    archive=raw/'GISD30_part_01.rar';archive.write_bytes(b'not-a-real-rar')
    for i in range(2,13):(raw/f'GISD30_part_{i:02d}.rar').write_bytes(b'synthetic')
    monkeypatch.setattr(doctor,'sevenzip_executable',lambda:None)
    with pytest.raises(FileNotFoundError,match='7z.exe'):
        doctor.rar_preflight(tmp_path,require_tool=True)
    summary=doctor.rar_preflight(tmp_path,require_tool=False)
    assert summary['status']=='NEEDS_7ZIP'
    assert archive.read_bytes()==b'not-a-real-rar'


def test_gisd_stage_failure_writes_precise_source_family(tmp_path,monkeypatch):
    from ceeprod import runner,doctor
    (tmp_path/'CEE数据').mkdir()
    monkeypatch.setattr(doctor,'rar_preflight',lambda *a,**k:{'status':'TEST_7ZIP_OK'})
    from ceeall import staging
    def broken(*args,**kwargs):raise RuntimeError('synthetic RAR CRC failure from 7-Zip')
    monkeypatch.setattr(staging,'stage_family',broken)
    with pytest.raises(RuntimeError,match='STAGING FAILED family=gisd'):
        runner.stage(tmp_path,only_family='gisd')
    qc=json.loads((tmp_path/'reports/cee_full_v2/stages/staged_gisd_failed.json').read_text())
    assert qc['family']=='gisd' and 'CRC failure' in qc['error']


def test_zip_stage_reuses_crc_qc_without_reading_zip_payload_again(tmp_path,monkeypatch):
    from ceeall.staging import stage_zip
    src=tmp_path/'test.zip'
    with zipfile.ZipFile(src,'w') as f:f.writestr('myfile.tif',b'123456')
    out=tmp_path/'staged'
    assert stage_zip(src,out)['n_members']==1
    import zipfile as zm
    native=zm.ZipFile.open
    def bad_open(*a,**k):raise AssertionError('Should NOT CRC read finished staged archive again')
    monkeypatch.setattr(zm.ZipFile,'open',bad_open)
    q=stage_zip(src,out)
    assert q['status']=='REUSED_CRC_VERIFIED_STAGE'


def test_rar_stage_preserves_existing_staged_source(tmp_path,monkeypatch):
    from ceeall.staging import stage_rar
    src=tmp_path/'data/CEE数据/GISD30_A.rar';src.parent.mkdir(parents=True)
    src.write_bytes(b'fake original archive')
    dest=tmp_path/'data/staged/cee_all/GISD30_A'
    def mockrun(argv,**kwargs):
        if argv[1]=='x':
            outarg=next(x for x in argv if x.startswith('-o'))[2:]
            target=Path(outarg)/'GISD30_1985-2020_A.tif';target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'official source bytes')
        return SimpleNamespace(returncode=0,stdout='Everything is Ok')
    monkeypatch.setattr('ceeall.staging.subprocess.run',mockrun)
    a=stage_rar(src,dest,sevenzip='FAKE_7ZIP')
    assert a['status']=='STAGED_RAR_CRC_AND_CHECKSUM_CHECKED'
    original=(dest/'GISD30_1985-2020_A.tif').read_bytes()
    b=stage_rar(src,dest,sevenzip='FAKE_7ZIP')
    assert b['status']=='REUSED_VERIFIED_RAR_STAGE'
    assert (dest/'GISD30_1985-2020_A.tif').read_bytes()==original


def test_stale_production_lock_archived_but_derived_data_untouched(tmp_path,monkeypatch):
    from ceeprod import runner
    from types import SimpleNamespace
    from pathlib import Path
    import psutil
    lockdir=tmp_path/'reports/cee_full_v2';lockdir.mkdir(parents=True)
    lock=(lockdir/'global_run.lock');lock.write_text('pid=99999999,start=123456789')
    derived=tmp_path/'data/derived/cee_all_global_v2/vector/roads/tiles';derived.mkdir(parents=True)
    precious=derived/'tile_000.parquet';precious.write_bytes(b'original data must remain')
    monkeypatch.setattr(runner,'_preexisting_jobs',lambda:[])
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(total=128e9))
    monkeypatch.setattr(psutil,'pid_exists',lambda pid:False)
    def fakeplan(root):raise ValueError('synthetic stop after verified lock migration')
    monkeypatch.setattr(runner,'plan',fakeplan)
    with pytest.raises(ValueError,match='synthetic stop'):
        runner.run_all(tmp_path)
    assert not lock.exists()
    assert len(list(lockdir.glob('global_run.lock.stale_*')))==1
    assert precious.read_bytes()==b'original data must remain'
    failed=json.loads((lockdir/'failed_stage.json').read_text())
    assert failed['error_type']=='ValueError'
