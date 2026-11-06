import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from cee_v8.budget_v9 import pacific_month_start_utc,budget_decision
import datetime as dt

def test_pacific_dst_boundaries():
 x=pacific_month_start_utc(dt.datetime(2026,11,6,15,tzinfo=dt.timezone.utc))
 assert x==dt.datetime(2026,11,1,7,tzinfo=dt.timezone.utc)
 y=pacific_month_start_utc(dt.datetime(2026,12,6,15,tzinfo=dt.timezone.utc))
 assert y==dt.datetime(2026,12,1,8,tzinfo=dt.timezone.utc)

def test_fuse_stops_when_usage_nears_900():
 assert not budget_decision({'conservative_total_eecu_h':897},900,simultaneous=2)['can_submit']
 assert budget_decision({'conservative_total_eecu_h':850},900,simultaneous=2)['can_submit']
