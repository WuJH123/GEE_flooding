"""Project-wide EECU guardrail: current usage, not stale CLI snapshot.

Cloud Monitoring metric types documented at
https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h .
Metrics are BETA / can lag; this is a *soft* throttle and not a guaranteed
hard monthly quota enforcement mechanism. Always leave 10% monthly reserve.
"""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo

METRICS={
 'completed':'earthengine.googleapis.com/project/cpu/usage_time',
 'inprogress':'earthengine.googleapis.com/project/cpu/in_progress_usage_time'
}


def pacific_month_start_utc(now_utc):
    if now_utc.tzinfo is None:raise ValueError('UTC aware clock required')
    z=now_utc.astimezone(ZoneInfo('America/Los_Angeles'))
    local=dt.datetime(z.year,z.month,1,tzinfo=z.tzinfo)
    return local.astimezone(dt.timezone.utc)


def current_month_eecu_hours(project_id, now_utc=None):
    """Read full PROJECT usage across batch/online and *all users*.

    This method requires Monitoring Viewer IAM and Cloud Monitoring API. It
    raises rather than inferring usage from a subset of task ledger entries.
    """
    from google.cloud import monitoring_v3
    from google.protobuf.timestamp_pb2 import Timestamp
    from google.protobuf.duration_pb2 import Duration
    now=now_utc or dt.datetime.now(dt.timezone.utc)
    start=pacific_month_start_utc(now)
    c=monitoring_v3.MetricServiceClient()
    interval=monitoring_v3.TimeInterval(
      start_time=start,end_time=now)
    agg=monitoring_v3.Aggregation(
      alignment_period=dt.timedelta(hours=1),
      per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_SUM)
    values={}
    for key,mtype in METRICS.items():
        q=f'metric.type = "{mtype}"'
        s=c.list_time_series(request={
           'name':f'projects/{project_id}','filter':q,
           'interval':interval,'view':monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
           'aggregation':agg})
        seconds=0.0
        for series in s:
            for point in series.points:
                v=point.value
                seconds += float(v.double_value or v.int64_value or 0.0)
        values[key]=seconds/3600.0
    return {'status':'MONITORING_PROJECT_WIDE_EECU',
         'project':project_id,'month_start_utc':start.isoformat(),
         'asof_utc':now.isoformat(),
         'completed_eecu_h':values['completed'],
         'inprogress_eecu_h':values['inprogress'],
         'conservative_total_eecu_h':values['completed']+values['inprogress'],
         'monitoring_can_lag':True}


def budget_decision(live,limit=900,expected_remaining_tasks=0,
                    simultaneous=2,max_unknown_task_eecu_h=5):
    if limit<=0 or simultaneous<1:raise ValueError('Invalid cost fuse inputs')
    observed=float(live['conservative_total_eecu_h'])
    if observed<0:raise ValueError('Invalid Cloud Monitoring EECU')
    headroom=simultaneous*max_unknown_task_eecu_h
    ok=observed+headroom<limit
    return {'can_submit':ok,'remaining_eecu_h':max(0,limit-observed),
            'project_eecu_h':observed,'inflight_uncertainty_buffer_eecu_h':headroom,
            'not_a_hard_spend_cap':True,'remaining_jobs':int(expected_remaining_tasks)}
