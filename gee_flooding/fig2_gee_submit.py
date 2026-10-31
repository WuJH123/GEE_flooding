"""Bounded, restartable Figure2 GEE submission from a frozen planned task CSV.

No background scheduler. DRY_RUN by default. To submit requires the explicit
--submit --confirm SUBMIT --project; <=4 tasks in one invocation. After each
accepted task, append a durable JSONL ledger record. Never auto-resubmit
ledgered tasks; inspect EE Tasks manually if a process was interrupted.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .fig2_gee import launch

FAMILIES=("merit","landcover","builtform","population")

def dispatch(root,plan,family,project=None,max_tasks=1,submit=False,
             confirm=None,only_job=None):
    root=Path(root)
    plan=Path(plan)
    if family not in FAMILIES:
        raise ValueError("Unknown Figure2 source family")
    if not 1<=int(max_tasks)<=4:
        raise ValueError("At most 4 GEE tasks per explicit invocation")
    if submit and (not project or confirm!="SUBMIT"):
        raise ValueError("Real submission requires --project and --confirm SUBMIT")
    task_csv=plan/"fig2_gee_backfill_tasks.csv"
    if not task_csv.is_file():raise FileNotFoundError(str(task_csv))
    tasks=pd.read_csv(task_csv)
    if tasks.job_id.duplicated().any():raise ValueError("Duplicate plan job_id")
    tasks=tasks.loc[tasks.source_family.eq(family)].copy()
    if only_job is not None:
        tasks=tasks.loc[tasks.job_id.eq(only_job)]
        if tasks.empty:raise ValueError("Requested job is not in the selected family")
    # Ledger is next to the task plan, not downloaded GEE data. Only records
    # success AFTER Earth Engine task.start() returns an ID.
    ledger=plan/"fig2_gee_submission_ledger.jsonl"
    seen=set()
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record=json.loads(line)
                if record.get("submitted") is True:
                    seen.add(record["job_id"])
    pending=tasks.loc[~tasks.job_id.isin(seen)].head(max_tasks)
    if pending.empty:
        return dict(status="NO_UNSUBMITTED_JOBS_IN_REQUESTED_FAMILY",
                    family=family,submitted_now=0,already_ledgered=len(seen),
                    ledger=str(ledger))
    attempted=[]
    for row in pending.itertuples(index=False):
        grid=plan/row.grid_file
        if not grid.is_file():raise FileNotFoundError(str(grid))
        result=launch(grid,0,int(row.n_grid),row.mode,None,
                      "GEE_flooding_Figure2",
                      submit=submit,project=project,bands=row.bands)
        entry=dict(job_id=row.job_id,family=family,mode=row.mode,bands=row.bands,
                   n_grid=int(row.n_grid),description=result["description"],
                   submitted=bool(result["task_submitted"]),
                   task_id=result.get("task_id"),status=result["status"])
        attempted.append(entry)
        if submit:
            if not result["task_submitted"] or not result.get("task_id"):
                raise RuntimeError("GEE submission did not return an ID")
            entry["submitted_utc"]=datetime.now(timezone.utc).isoformat()
            # O_APPEND and flush; no fictitious completion state recorded.
            with ledger.open("a",encoding="utf-8") as f:
                f.write(json.dumps(entry,ensure_ascii=False)+"\n")
                f.flush()
                os.fsync(f.fileno())
    return dict(status="SUBMITTED_NOT_COMPLETED" if submit else "DRY_RUN",
                family=family,submitted_now=sum(x["submitted"] for x in attempted),
                planned_now=len(attempted),jobs=attempted,
                ledger=str(ledger),
                note="Check GEE Tasks for COMPLETED, then download and audit CSV. "
                     "After interruption cross-check task list before re-running.")


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--family",choices=FAMILIES,required=True)
    p.add_argument("--job-id")
    p.add_argument("--max-tasks",type=int,default=1)
    p.add_argument("--project")
    p.add_argument("--submit",action="store_true")
    p.add_argument("--confirm",help="Required exact word SUBMIT for a real EE task")
    a=p.parse_args(argv)
    print(json.dumps(dispatch(a.root,a.plan,a.family,a.project,a.max_tasks,
                              a.submit,a.confirm,a.job_id),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
