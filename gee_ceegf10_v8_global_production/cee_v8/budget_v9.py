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
    from google.auth.transport.requests import AuthorizedSession
    import ee
    now=now_utc or dt.datetime.now(dt.timezone.utc)
    start=pacific_month_start_utc(now)
    credentials=ee.data.get_persistent_credentials().with_quota_project(project_id)
    session=AuthorizedSession(credentials)
    endpoint=f'https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries'
    values={}
    for key,mtype in METRICS.items():
        seconds=0.0
        token=None
        while True:
            params={'filter':f'metric.type = "{mtype}"',
                    'interval.startTime':start.isoformat().replace('+00:00','Z'),
                    'interval.endTime':now.isoformat().replace('+00:00','Z'),
                    'aggregation.alignmentPeriod':'3600s',
                    'aggregation.perSeriesAligner':'ALIGN_SUM',
                    'view':'FULL','pageSize':1000}
            if token:params['pageToken']=token
            response=session.get(endpoint,params=params,timeout=60)
            response.raise_for_status()
            body=response.json()
            for series in body.get('timeSeries',[]):
                for point in series.get('points',[]):
                    v=point.get('value',{})
                    seconds+=float(v.get('doubleValue',v.get('int64Value',0)))
            token=body.get('nextPageToken')
            if not token:break
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
