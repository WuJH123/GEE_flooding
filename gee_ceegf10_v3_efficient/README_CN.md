# CEE GF10 Efficient v3 — 10 km 全部指标、GEE额度节约版（2026-11-05）

目标是本地原始官方数据能处理的一律本地，GEE只进行缺口计算；**正式处理结果均需独立检验**。本包保留了 v2 完整可执行 `ceeprodgee` GEE生产CLI与严格生产闸门，同时新增 ESA WorldCover 2021 原始 COG 的本地分块提取引擎和 M0 时间完整性修复。不会自动提交任何全球GEE任务。

## 科学指标合同

- M1 MERIT Hydro（GEE）：既定 16 波段，HAND/水文调整高程/UPA均值、UPA最大、HAND阈值低洼比例、分位数、坡度、永久水体、有效覆盖。**上游汇流面积不是城市排水管网能力**。
- M2 WorldCover v200 2021（本地优先）：完整 GF10 11类面积比例、GSHHG真实陆地内11类比例、完整格网/陆地有效率、海陆栅格面积比例，共25波段。额外9个指标（绿地不含农田/绿地含农田/湿地/建成/水体）纯本地相加，无新GEE处理。
- M0 IMERG（事件×UTC日）：永久产品每半小时雨强 mm/h×0.5h；UTC自然日总降雨、日内43个三小时完整滚动窗口中的最大值、前7/14/30完整日雨量，缺少48/336/672/1440个半小时观测则该项输出缺测。**修复旧版误把前一日午夜前半小时算入当日3h窗口的问题。**
- M0 ERA5-Land：前一个完整UTC日的气温K转℃、土壤湿度、日降雨量m转mm；日累计与日平均不同。均保留来源网格的原生分辨率，不声称10km更细实测。
- P1 VIIRS、MODIS NDVI、JRC历史水体不提交，此版本只登记来源候选，后续研究问题需要才冻结新字段。

## 为什么推荐本地 WorldCover

ESA官方提供公开AWS S3中 WorldCover 2021 v200 全套3° COG原始分类TIFF（约117GB Map产品），2TB磁盘足以容纳这类原始数据及过渡空间。Gate C 400格试验用GEE完成M2的成本为约1.944 EECU小时，线性外推全球1,395,471格约6,780 EECU小时。**这只是预算风险外推，并非生产成本保证；本地计算可省下主要GEE EECU，代价是高CPU、网络和磁盘IO。**

官方下载：https://esa-worldcover.org/en/data-access
AWS官方命令：`aws s3 sync s3://esa-worldcover/v200/2021/map E:\WJH_CEE\data\raw\ESA_WorldCover_2021_v200_COG --no-sign-request`

### 本地方法与准确性

- 将每个官方 COG 的原生分类值**一次**以最近邻重投影到EPSG6933、原点(0,0)、10 m像元网格，5×5个GF10为一个有界计算单元，不对类别代码求平均。
- 在同一10 m网格将本地GSHHG v2.3.7 Full L1−L2+L3−L4陆地多边形栅格化，再**先求类别与陆地交集面积**，最后除以陆地面积；不能把`fraction_fullcell`简单除以`land_area_km2/100`。
- 每个5×5块最多2500万10m像元；处理时原始分类只重投影一次，内存峰值受workers限制。建议服务器128GB先用16 workers，每warp可用2线程，稳定后尝试24–32并比较真实tile/s；各进程独立读取GF10索引一次。
- 重要：**原始像元最近邻→10m等面积格网仍是数值近似，不是原始10m多边形的精确交叠。** 不能直接标记为发表级。必须比较既有武汉、孟买、冰岛、尼日尔三角洲四块Gate C独立GeoTIFF，且全域记录真实GSHHG陆地面积与栅格近似的偏差。微小岛屿和复杂海岸线可用GEE或更精确的源像元矢量相交作补验。
- 本地输出25波段与已通过GEE Gate C的顺序、NoData约定及GF10坐标一一对应；原生源片与运行脚本指纹冻结。分区失败后续跑时不会删除已完成tile。

## A. 远程96核服务器：完整WorldCover本地提取

1. 将v3完整ZIP解压到 `E:\WJH_CEE\CEE_GF10_EFFICIENT_V3_20261105`，确保有现有 `E:\WJH_CEE\.venv\Scripts\python.exe` 和冻结 `E:\WJH_CEE\gf10_global_nonantarctic_land.parquet`。
2. 将已在其它电脑使用的 GSHHG Full L1–L4 四个shp及同名 `.dbf/.shx/.prj`，复制到服务器 `E:\WJH_CEE\reference\GSHHG`（程序自动搜索，无需手填单文件路径）。
3. 安装AWS CLI（https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html）；无需 AWS账号即可下载公开COG。
4. 服务器PowerShell：

```powershell
$ROOT='E:\WJH_CEE'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_EFFICIENT_V3_20261105.zip" -DestinationPath $ROOT
$P="$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\09_verify_offline_v3.ps1
.\scripts\10_worldcover_aws_download.ps1 -Root $ROOT # 只读下载预览
.\scripts\10_worldcover_aws_download.ps1 -Root $ROOT -Execute # 下载117GB官方COG
.\scripts\11_worldcover_local_pilot.ps1 -Root $ROOT # 四块验证；共16个5×5计算块
```

5. 从目前可访问的 `E:\GEE_flooding\gee_ceegf10_v1\reports\gate_c_mosaics` 复制四个WorldCover 10×10参考tif到服务器 `E:\WJH_CEE\reference\GATE_C_20261104`，文件名须保持 `worldcover_wuhan_10x10.tif` 等四个名称：`worldcover_wuhan_10x10.tif`、`worldcover_mumbai_10x10.tif`、`worldcover_iceland_10x10.tif`、`worldcover_niger_delta_10x10.tif`。

```powershell
.\scripts\13_compare_gate_c.ps1 -Root $ROOT
```

只有比较完成且 `PASS_GATE_C_INDEPENDENT_COMPARISON`，才执行全球生产：

```powershell
.\scripts\12_worldcover_local_full.ps1 -Root $ROOT -Workers 24
.\scripts\14_merge_worldcover_global.ps1 -Root $ROOT
```

全球 1,395,471 GF10必须一一对应；25类源字段 +9个派生变量，缺失原始覆盖保留NaN。预计有大量5×5计算块，**这是一项真实高耗时、仅消耗本地CPU/磁盘的处理工作，不应假定短时间完成**。

## B. 当前可登录GEE的Windows电脑：MERIT与事件气象

保留旧项目和配置，不修改旧已通过Gate C数据。将v3包放到 `E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105`，随后：

```powershell
$ROOT='E:\GEE_flooding'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_EFFICIENT_V3_20261105.zip" -DestinationPath $ROOT
$P="$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
Set-Location $P
.\scripts\00_preflight.ps1
.\scripts\01_plan_cost.ps1
.\scripts\02_submit_pilot_merit.ps1
.\scripts\04_show_task_status.ps1
```

新GEE计算图尚未在线验证，即使旧Gate C已经成功也必须使用同一位置GeoTIFF重复验收：本包 `downloads/` 保存新的武汉MERIT TIF，按记录的任务键执行 `audit`，经独立对照通过方可放行。

```powershell
$PY="$P\.venv\Scripts\python.exe"
& $PY -m ceeprodgee audit --key merit_1097_367_10
& $PY -m ceeprodgee plan --family merit --scope all
& $PY -m ceeprodgee submit --family merit --plan "$P\plans\merit_all.csv" --tile-key auto # 默认DRY_RUN
```

正式每次仅提交一个通过成本与QC批准的连续10×10格网任务，必须使用配置中真实run_id：

```powershell
& $PY -m ceeprodgee submit --family merit --plan "$P\plans\merit_all.csv" --tile-key auto --execute --confirm CEE_GF10_M0M1M2_EFFICIENT_20261105_V3
& $PY -m ceeprodgee status
```

等完成后下载、audit该tile再下一项。全球MERIT每格16指标不重复提交其它项目已完成GHSL/WorldClim/GMTED。

M0动态气象**只对冻结GF10×UTC日的病例和对照日期提取**，不是对全球139.5万格×每一天盲提取。当前电脑操作：

```powershell
.\scripts\05_event_method_only.ps1  # dry-run方法验证
& $PY -m ceeprodgee event-plan --events "$P\config\case_control_gf10_dates.parquet"
```

上述事件Parquet必须来自已经完成严格GF10重映射后的真实病例/对照事件，不会在包中虚构。执行脚本所用的GEE账户是专门的CEE项目，不读其它项目资产。P1没有GEE提交入口。

## 代码质量与限制

- 离线单元测试覆盖分类守恒、真实陆地分母、源代码完整性、时间窗口、唯一GF10和GEE任务成本闸门。
- GEE quota默认保留至少300h给M0动态；单任务GEE真实 `batchEecuUsageSeconds` 决定是否放行下一分区。
- **本地WorldCover最终与Gate C差异超阈值时，必须调整本地10m近似计算或仅补验异常区域，不能将数值近似声明为精确遥感像元交叠。**

## 官方来源

- ESA原版AWS：https://esa-worldcover.org/en/data-access
- MERIT：https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
- IMERG：https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5-Land：https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- GEE best practices：https://developers.google.com/earth-engine/guides/best_practices
