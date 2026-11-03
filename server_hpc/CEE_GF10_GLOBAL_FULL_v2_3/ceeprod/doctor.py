"""Read-only preflight diagnostics for 35 downloaded GF10 source files.

No downloads, no extracted file deletion and no mutation of completed tiles.
"""
from __future__ import annotations
from pathlib import Path
import shutil, sys, os, json, traceback, subprocess, time
from .shared import read_json,write_json


def sevenzip_executable():
    paths=[shutil.which(x) for x in ('7z','7zz','7za')]
    paths+=['C:/Program Files/7-Zip/7z.exe', 'C:/Program Files (x86)/7-Zip/7z.exe']
    for p in paths:
        if p and Path(p).is_file():return str(Path(p))
    return None


def rar_preflight(root, *, test_integrity=False, require_tool=True):
    root=Path(root)
    archives=sorted((root/'CEE数据').glob('GISD30_*.rar'))
    exe=sevenzip_executable()
    evidence={'source_directory':str(root/'CEE数据'), 'n_gisd_rar':len(archives),
              'rar_files':[{'name':p.name,'size_gb':round(p.stat().st_size/1e9,3)} for p in archives],
              'sevenzip_path':exe,'free_disk_gb':round(shutil.disk_usage(root).free/1e9,1),
              'integrity_test_requested':test_integrity,
              'status':'NEEDS_7ZIP' if exe is None else 'RAR_TOOL_AVAILABLE',
              'hint':'Download Windows x64 7-Zip from https://www.7-zip.org/download.html; no GitHub sync required'}
    if require_tool and archives and not exe:
        raise FileNotFoundError('GISD30 RAR requires 7z.exe; not found in PATH nor standard Program Files. '
                                'Install official Windows 7-Zip x64 before running, or move 7z.exe to standard installation directory.')
    if archives and len(archives)!=12:
        raise ValueError(f'Expected 12 downloaded GISD30 RAR archives, found {len(archives)}. Verify inventory first.')
    if test_integrity and exe:
        for p in archives:
            t0=time.monotonic()
            proc=subprocess.run([exe,'t','-y','-bso0','-bsp0',str(p)],stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,text=True,errors='replace')
            evidence.setdefault('tested_archives',[]).append({'name':p.name,'exit_code':proc.returncode,
                'seconds':round(time.monotonic()-t0,1),'tail':proc.stdout[-1000:]})
            if proc.returncode:
                raise RuntimeError(f'7-Zip integrity test failed {p.name} (exit {proc.returncode}): {proc.stdout[-1000:]}')
        evidence['status']='ALL_12_RAR_INTEGRITY_PASS'
    return evidence


def diagnose(root, *, test_rar=False, save=True):
    root=Path(root)
    result={'status':'DIAGNOSTIC_NOT_COMPLETE_PRODUCTION','root':str(root),
            'python':sys.executable,'severe_failure_not_assumed_from_partial_traceback':True,
            'reports':{}}
    reports=root/'reports/cee_full_v2'
    for name in ('failed_stage.json','vector_source_autodetect.json'):
        p=reports/name
        if p.exists():
            try:result['reports'][name]=read_json(p)
            except Exception as e:result['reports'][name]={'parse_error':str(e)}
    for name in ('worldclim','era5ex','admin','ucdb','hydroatlas','roads','gisd'):
        p=reports/'stages'/f'staged_{name}.json'
        if p.exists():
            try:result['reports']['staged_'+name]=read_json(p).get('status')
            except Exception as e:result['reports']['staged_'+name]='INVALID_JSON_'+str(e)
    lock=reports/'global_run.lock'
    result['production_lock']={'exists':lock.exists(),'contents':lock.read_text(encoding='utf8',errors='replace')[:400] if lock.exists() else None}
    try:result['rar']=rar_preflight(root,test_integrity=test_rar)
    except Exception as e:
        result['rar']={'status':'FAIL','error_type':type(e).__name__,'error':str(e)}
    try:
        from .runner import _preexisting_jobs
        result['other_production_processes']=_preexisting_jobs()
    except Exception as e:result['other_production_processes_error']=str(e)
    files=sorted(reports.glob('full_run_*.log'))
    if files:
        last=files[-1];result['last_full_log']=str(last)
        try:result['last_full_log_tail']=last.read_text(encoding='utf-8',errors='replace')[-12000:]
        except Exception as e:result['last_full_log_tail_error']=str(e)
    if save:write_json(reports/'diagnostic_v21.json',result)
    return result
