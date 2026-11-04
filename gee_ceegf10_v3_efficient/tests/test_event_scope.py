import pandas as pd,pytest
from ceeprodgee.grid import event_plan_from_records

def test_event_keys_and_day_not_label_driven():
 grid=pd.DataFrame({'grid_id':['0_0','0_1','9_9','10_10'],
  'grid_x':[0,0,9,10],'grid_y':[0,1,9,10]})
 event=pd.DataFrame({'grid_id':['0_0','0_0','0_1','10_10'],
  'date_utc':['2021-07-01','2021-07-01','2021-07-01','2021-07-02']})
 rows,plan=event_plan_from_records(event,grid)
 assert len(rows)==3
 assert plan.n_unique_grid_days.sum()==3
 assert len(plan)==2
 with pytest.raises(ValueError,match='absent'):event_plan_from_records(pd.DataFrame({'grid_id':['bad'],'date_utc':['2021-01-01']}),grid)
 with pytest.raises(ValueError,match='outside'):event_plan_from_records(pd.DataFrame({'grid_id':['0_0'],'date_utc':['2018-01-01']}),grid)
