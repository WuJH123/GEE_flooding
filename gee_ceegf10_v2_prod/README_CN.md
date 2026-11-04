# CEE GF10 GEE Production v2（2026-11-04）

**目标论文**：*Communications Earth & Environment*，全球城市暴雨内涝的可迁移解释机制。与 `Global_flooding` 的 *Nature Cities* 主文分开。

## 正式结论与使用边界

- GF10全陆地注册基底：1,395,471个10 km正陆地格；EPSG:6933、0 m原点，格网面积100 km²；`land_area_km2`为精确GSHHG矢量面积，不可直接当每格100 km²。
- Gate C四块试验：MERIT 16波段×4个10×10块；WorldCover 25波段×4个由5×5拼接的10×10块。24项成功任务合计1.97453 EECU-h；WorldCover均值约0.00486 EECU-h/格，全部1,395,471格线性外推约6782小时（只用于说明不能盲提交，不是费用预报）。
- 原有GEE v1开发分支的在线Gate C试验已经完成；**本v2重新实现的新计算图还没有通过真实GEE在线验收**。因此代码默认 `DRY_RUN`，且要求与原Gate C同位置GeoTIFF重新对照才能放开该数据族的任何正式生产任务。绝不宣称离线测试等于GEE实测成功。
- M1和M2原始类别只用于解释暴雨洪涝的背景条件，并不能推断真实积水深度、城市排水能力或因果效应。事件研究需单独构建风暴簇、新闻报告选择机制及外部淹没真值。

## 科学指标一次性冻结

- **M1 MERIT Hydro (16bands)**：高程、HAND、UPA均值；永久水体、有效像元覆盖；HAND≤2/5/10 m比例；源高程坡度均值及≤2°比例；UPA最大值及`ln(1+upa_max/1 km²)`；直接源像元HAND p10/p50/p90、UPA p90。`elv`是水文调整高程，UPA是流域上游面积而非城市排水管道容量。
- **M2 ESA WorldCover 2021 (25bands)**：11类土地覆盖的完整方格比例和GSHHG真实陆地比例、分别的有效覆盖比例、GSHHG 10 m栅格化陆地比例。`wc_80`水体与GSHHG海陆分母不是同一分类体系；不允许将整格比例简单除以`land_area_km2/100`。
- **M0动态事件（18bands）**：IMERG permanent半小时雨强→半小时深度、D日总量、30分钟峰值、连续6个半小时组成的滚动3小时最大深度、D前7/14/30整日累计、观测数；ERA5-Land D前一个完整UTC日土壤湿度1/2层、气温、雨、径流、风速/分量。保持 `grid_id × date_utc` 单独宽表，与静态产品分开。没有有效终态观测不填零。
- **从本地复用**：GHSL SMOD/POP/BUILT/NRES，2000–2020 built扩张，GISD30历史不透水度，GRIP4道路，River/BasinATLAS，GMTED五个地形源，WorldClim 103层，ERA5-EX 34指标，UCDB，Groundsource及多源观测。**这些由本地全局QC控制，本包不自动重新提交GEE。**
- **P1需由研究问题决定**：JRC长期水体、VIIRS 2020夜光、MODIS 2020 NDVI，当前仅列入字典，**未实现/未提交生产**，不能提前宣称采集完成。

完整字段、单位、来源及分母见 `config/INDICATOR_CONTRACT_V2.csv`。

## 部署：当前能够登录GEE的Windows电脑

代码解压到：`E:\GEE_flooding\CEE_GF10_GEE_PRODUCTION_V2_20261104`，与旧 `gee_ceegf10_v1` 并存，不覆盖旧代码、GEE资产及已验收GeoTIFF。

```powershell
$P = 'E:\GEE_flooding\CEE_GF10_GEE_PRODUCTION_V2_20261104'
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\00_preflight.ps1
.\scripts\01_plan_cost.ps1
```

`00_preflight`从旧工程的 `E:\GEE_flooding\gee_ceegf10_v1\config\local_run.json` 读取既有独立GEE项目ID与真实GF10 Parquet路径，验证ID、1,395,471行、陆地面积、文件SHA；不会创建新项目或开始EE任务。必须先通过全部离线测试。

`01_plan_cost`只生成两类全球计划和模拟EECU区间，**绝不提交任务**。

### 唯一建议立即提交的两项新实现验证

在当前电脑具有GSHHG v2.3.7 full `GSHHS_f_L1.shp`~`L4.shp` 来源后执行：

```powershell
.\scripts\02_submit_pilot_merit.ps1
.\scripts\03_submit_pilot_worldcover.ps1
.\scripts\04_show_task_status.ps1
```

两个任务分别是武汉已经验收过的MERIT 10×10和WorldCover左下方5×5。程序不会把全球分散16格的边界拼为一个中间重投影区域。WorldCover首先要求找到真正的四级GSHHG海岸线；找不到时**拒绝执行，而不是退回错误的100 km²完整格网分母**。

等GEE任务显示SUCCEEDED，从本次项目的Google Drive文件夹将两个TIF下载到本包`downloads/`，保留程序输出的确切文件名（单个小块通常直接对应该文件名）。**这一步不是自动的**，Google Drive下载需要当前账户授权。

```powershell
$PY = "$P\.venv\Scripts\python.exe"
& $PY -m ceeprodgee status
& $PY -m ceeprodgee audit --key merit_1097_367_10
& $PY -m ceeprodgee audit --key worldcover_1097_367_5
```

`audit`要求成功任务、16/25波段与GF10地理对齐、物理不等式、类别/陆地守恒，并且自动对照原v1 Gate C武汉GeoTIFF；不通过不得提交新的静态任务。

### 在线复验成功之后，如何进行正式计划

MERIT全域（高纬无源值保留NoData），生成的计划包括所有正陆地GF10：

```powershell
& $PY -m ceeprodgee plan --family merit --scope all
& $PY -m ceeprodgee submit --family merit --plan "$P\plans\merit_all.csv" --tile-key auto
```

上面的`submit`是**DRY RUN**。正式对每块人工核准一次：

```powershell
& $PY -m ceeprodgee submit --family merit --plan "$P\plans\merit_all.csv" --tile-key auto --execute --confirm CEE_GF10_M1M2_PRODUCTION_20261104_V2
```

完成一块后必须运行 `status`，下载该块TIF并`audit --key <任务命令输出的key>`；当前版本特意**不支持一口气批量自动提交全球**，直到真正的首批EECU及文件质量分布独立复核。

WorldCover全域计划仅用于估算和分层；按当前四区试验估算超1000h，不得执行。正式M2应先按照2020基线GHSL预注册城市研究域，生成与冻结GF10一致的`grid_id`表（CSV/Parquet），且不能用Groundsource是否发生洪涝筛选。这份研究域应由本地服务器最终QC输出；复制到当前电脑后：

```powershell
& $PY -m ceeprodgee plan --family worldcover --scope study --study-ids "$P\config\study_gf10_ids.csv"
& $PY -m ceeprodgee submit --family worldcover --plan "$P\plans\worldcover_study.csv" --tile-key auto
```

这里的 `study_gf10_ids.csv` 必须是真实的研究样本清单，格式为单列`grid_id`；本包不会虚构城市范围。以上命令在文件未准备好时会停止。

### 事件气象研究（必须先冻结GF10日样本）

可在已完成的本地病例–对照设计后构造包含`grid_id,date_utc`的事件样本表。**以前在20 km格网生成的事件ID不能直接加入10 km GF10宽表。** 需要在原始事件几何与气象日期基础上明确重新映射。该表不得由结局标签决定哪些气象字段可见。

```powershell
# 首次只检验事件日期与单位，不是洪涝真值
.\scripts\05_event_method_only.ps1
# 正式事件/对照组表准备后；无匹配时拒绝运行
& $PY -m ceeprodgee event-plan --events "$P\config\case_control_gf10_dates.parquet"
```

生成 `plans/event_task_plan.csv` 后，每批以GEE实际EECU为预算人工单个提交：

```powershell
& $PY -m ceeprodgee event-submit --key event_2021-07-01_1100_370 --execute --confirm CEE_GF10_M1M2_PRODUCTION_20261104_V2
& $PY -m ceeprodgee status
& $PY -m ceeprodgee event-audit --key event_2021-07-01_1100_370
```

上述事件`key`只是**命令格式演示**，必须在真实冻结计划中存在，否则会拒绝执行。**绝不将事件气象提取成功等同于真实洪涝验证**。

### 全球或局部数据组装

```powershell
& $PY -m ceeprodgee merge --family merit
& $PY -m ceeprodgee merge --family worldcover
```

输出保留1,395,471个`grid_id`，仅在通过QA的格网填写值；其余`NaN`而非零，报告`all_global_complete=false`时严禁称全球完整。

## 非商业额度科学约束

- 当前预算为每月最多1000 EECU-hours **只有Cloud项目实际升级至Contributor才成立**；Community仅150h。配置对静态阶段设置700h预警，余下至少300h为动态研究与必要的失败重算留空间。
- 四区任务属于小范围，不能直接预测全球费用。WorldCover全部GF10按当前平均单位成本粗略推算约6782h，超额；即使一次性全提取也不构成更好的因果研究设计。
- 每批保留`task_ledger.json`、源版本、项目、GF10 SHA、波段顺序、实际`batchEecuUsageSeconds`与本地GeoTIFF QC；第一次出错立即停止而非自动更换粗像元/`bestEffort`。

## 科学来源

- MERIT Hydro：https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
- ESA WorldCover 2021：https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- IMERG V07：https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5-Land Daily：https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- GEE最佳实践：https://developers.google.com/earth-engine/guides/best_practices
- Earth Engine非商业额度：https://developers.google.com/earth-engine/guides/noncommercial_tiers
