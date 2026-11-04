# CEE全球GF10（10 km）高效正式数据生产 v3 — 2026-11-04

## 本次关键决策

1. 全局空间基底始终是 EPSG:6933，GF10 `grid_id=grid_x_grid_y`，**1,395,471** 非南极正陆地格网。每格边长10 km、平面面积100 km²，但真实陆地面积 `land_area_km2` 不恒等于100。
2. **ESA WorldCover v200/2021：优先官网下载117GB Map 10m COG，远程96核128GB/2TB服务器本地逐10km汇总，不消耗GEE EECU**。官方产品2651个3°×3° COG。禁用100m多数类/10km nearest类别直接当分类比例。需要 GSHHG v2.3.7 Full L1–L4原始多边形，在10 m等面积目标网格做海陆分类交叠。它属于10 m投影栅格面积近似（不是原始EPSG4326像元严格多边形交集）；必须在武汉、孟买、冰岛、尼日尔三角洲4块同旧GEE Gate C GeoTIFF比较后方可跑全球。
3. **MERIT Hydro：保留16项M1静态指标，GEE先20×20格小样本在线同旧Gate C 10×10比对，合格后采用20×20有界分块**（比10×10任务数量最多降低约75%，不能据此推断EECU降幅）；按任务实际EECU+下载后QA闸门逐块继续。
4. **IMERG V07+ERA5-Land：先冻结 `grid_id,date_utc` 事件/对照表，按唯一UTC日期和连续50×50 GF10区域拆任务**。IMERG半小时雨强mm/h乘0.5得到mm；先做空间GF10聚合后求时序连续3小时最大（不是先原像元最大后空间均值）；D当日和D之前7/30完整UTC日，48/336/1440张覆盖校验；ERA5只读D前一完整日，防止未来信息泄漏。GPM V07永久版本截至2025-09-30。
5. 已完成 **GHSL、GMTED、WorldClim、GISD30、GRIP、HydroATLAS、ERA5-EX、UCDB** 等已有本地数据只复用，不重新让GEE处理。2020/2021静态基线用于回顾性解释，前瞻预测需要额外避免当年信息泄漏。
6. **P1 VIIRS、MODIS NDVI、JRC历史水体仅入指标字典，未提交计算**；后续需根据M0–M4模型增量决定是否必要。

## 字段说明

- `config/INDICATOR_CONTRACT_V3.csv` 包含 MERIT 16项、WorldCover源25项、完全由源分类比例推导的10项绿地/湿地/建成/水体/蓝绿空间、IMERG/ERA5-Land事件12项、五个本地重用数据族和P1计划。
- WorldCover `(10/20/30)` 是**自然植被**，`(90/95)` 是**湿地**，`(80)` 是**水体**，`(50)` 是**建成**；`蓝绿=植被+湿地+水体`（类别互斥，没有重复求和）。农田40不纳入自然植被定义；如需含农田指标应另行命名。
- `*_fraction_fullcell` 分母100 km²；`*_fraction_land` 使用GSHHG栅格化10m陆地分母；同时保留 `land_area_km2` 冻结精确矢量面积用于两者差异QC。
- WorldCover类比例缺测仍为NaN，非零海洋比例不能简单解释成城市不透水度。10m GSHHG微小岛屿可能不足一个像元，保留陆地而该类指标缺测，决不填零。
- 全球M1需预防 `upa_max` 对跨流域河洪的混杂；HAND、汇流区面积不能充当“排水管网容量”。

## 服务器：WorldCover 2021全域本地处理（无需GitHub/GEE）

将 `CEE_GF10_EFFICIENT_V3_20261104.zip` 复制到服务器 `E:\WJH_CEE`，按下列命令：

```powershell
$R='E:\WJH_CEE'
Expand-Archive "$R\CEE_GF10_EFFICIENT_V3_20261104.zip" -DestinationPath $R
$P="$R\CEE_GF10_EFFICIENT_V3_20261104"
Set-ExecutionPolicy -Scope Process Bypass -Force
& "$P\scripts\00_server_preflight.ps1" -Root $R
```

服务器已有 Python `.venv` 且应装有numpy/pandas/pyarrow/rasterio/geopandas/shapely/pyproj/pytest。若缺依赖，在服务器：

```powershell
& "$R\.venv\Scripts\python.exe" -m pip install -r "$P\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**首先确保剩余可用磁盘≥300 GiB**。官方世界覆盖图下载是约117GB，磁盘和网络压力需要确认：

```powershell
& "$P\scripts\01_worldcover_download.ps1" -Root $R
```

该脚本只下载 `s3://esa-worldcover/v200/2021/map`，不下载质量通道，不需AWS账户，支持同一 `aws s3 sync` 断点重复执行。共2651 COG，官方来源 <https://esa-worldcover.org/en/data-access>。

需有GSHHG Full v2.3.7 L1–L4 `.shp/.shx/.dbf/.prj`：如果在E盘以前已下载，复制到 `E:\WJH_CEE\data\raw\gshhg` 任意子目录即可；**无需重新生成GF10**。若服务器没有，官方 <https://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip>，下载解压到同一路径（参考历史冻结源的SHA256核查）。

```powershell
& "$P\scripts\02_worldcover_pilot.ps1" -Root $R -Workers 8
```

为4块独立空间测试提供原先成功的 Gate C 10×10 GeoTIFF：从可登录GEE电脑复制以下4个小文件到 `E:\WJH_CEE\gate_c_reference\`：

- `worldcover_wuhan_10x10.tif`
- `worldcover_mumbai_10x10.tif`
- `worldcover_iceland_10x10.tif`
- `worldcover_niger_delta_10x10.tif`

```powershell
& "$P\scripts\03_worldcover_gatec_compare.ps1" -Root $R
# 必须为 GATE_C_LOCAL_VS_GEE_PASS
& "$P\scripts\04_worldcover_full.ps1" -Root $R -Workers 16
```

正式计算每个10km格平均处理100万个10m像元，按10×10 GF10块分片，不读入整全球栅格；96核服务器建议8→16→24个worker测真实吞吐，不宜一次使用64。**中断后保留分片，重新运行同命令续跑**；冲突/孤立Parquet必须审计，不盲目删除。输出 `E:\WJH_CEE\data\derived\gf10_worldcover2021_native10m_v3\tiles\*.parquet`、每块QC、`global_qa.json`。

## 当前可登录GEE电脑：MERIT先扩大分块再批量

```powershell
$R='E:\GEE_flooding'
Expand-Archive "$R\CEE_GF10_EFFICIENT_V3_20261104.zip" -DestinationPath $R
$P="$R\CEE_GF10_EFFICIENT_V3_20261104"
Set-ExecutionPolicy -Scope Process Bypass -Force
& "$P\scripts\05_gee_preflight.ps1" -Root $R
& "$P\scripts\06_gee_merit_pilot20.ps1" -Root $R
```

预检从已完成Gate B/C的 `E:\GEE_flooding\gee_ceegf10_v1\config\local_run.json` 读取**原独立CEE GEE项目**，不重建项目也不访问其他项目资产。`06` 只提交 **1个武汉20×20 MERIT**，与原10×10 Gate C 16波段做在线等价性核验，未批准前不允许全球20×20。

待GEE任务`SUCCEEDED`，将该新GeoTIFF下载到 `$P\downloads\`，保留名称（`CEE_GF10_OPTIMIZED_V3_20261104_merit_1090_360_20.tif`），再执行：

```powershell
$PY="$R\.venv\Scripts\python.exe"; Set-Location $P; $env:PYTHONPATH=$P
& $PY -m ceeopt gee-status
& $PY -m ceeopt merit-audit --key merit_1090_360_20
```

若差异95分位≤1%、16波段数值合法，放行下一任务：

```powershell
& "$P\scripts\07_gee_merit_next.ps1" -Root $R
```

每次`07`提交**下一个尚未提交的有界20×20任务**，已经完成任务会自动跳过；上一个任务必须已成功、下载并`merit-audit --key 本任务key`验收，未通过不得提交下一项。**不同版本任务的产物不可自动混合**。MERIT所有任务完成后执行：

```powershell
& $PY -m ceeopt merit-merge
```

输出 `data\gf10_merit_partial_v3.parquet`；只有全部冻结格网完成并通过源有效覆盖检查才能把QC标记为全全球完整。已通过的块无需再次计算。若数千个文件下载操作成为瓶颈，可以设置一次Drive桌面同步/Rclone，之后在本地批量审计；不要通过跳过QA达到高速提交。

## 动态M0：先单日技术试验，后真实事件/对照日期

```powershell
& "$P\scripts\08_gee_weather_pilot.ps1" -Root $R
& "$P\scripts\11_gee_status.ps1" -Root $R
```

这是2023-06-01的**方法试验日期**，不代表真实洪涝事件。完成后下载 `CEE_GF10_OPTIMIZED_V3_20261104_met_20230601_1100_370_10.tif` 到`downloads\`，运行：

```powershell
& $PY -m ceeopt weather-audit --key met_2023-06-01_1100_370_10
```

实际案例/对照来自Figure 1冻结暴雨事件表。请先由本地项目把**真实GF10** `grid_id,date_utc` 列生成Parquet并复制到 `$P\config\gf10_event_dates.parquet`；旧20km事件ID不能直接当作10km。

```powershell
& "$P\scripts\09_gee_weather_plan.ps1" -Root $R
& "$P\scripts\10_gee_weather_next.ps1" -Root $R
```

`weather-plan`先去重所有`GF10×日期`，然后仅把有事件/对照的日期与连续50×50区域编为正式任务，无用户数据则拒绝虚构。`weather-next`一次提交1个，经任务状态、下载GeoTIFF、`weather-audit --key ...` 验收后继续。动态任务EECU设300h预算警戒，仅参考当前运行台账；**原云项目其他已使用EECU须在Cloud Console核对**。

## EECU预算和数据准确性

- 四块Gate C：400 GF10试验中MERIT 0.0303 EECU-h；WorldCover 1.9442 EECU-h。线性全球情景约MERIT 106h、WorldCover 6782h；**仅供判断量级，不能作为保证或未经验证的费用预测**。
- ESA WorldCover 10m COG约117GB、2651个公开瓦片。只在磁盘/网络可承受时采用本地路径，EECU为0；如果不愿下载117GB，GEE版只能覆盖预注册的城市研究域，不能冒充完整全球139.5万格。
- 不应通过“直接把10m分类最近邻缩放到10km”“GEE bestEffort强行降精度”获得看似完整的低成本指标。
- 地表覆盖比例是2021年土地覆被分类，不等于2020年建筑面积/不透水率；与GHSL 2020比较需保留年份口径。
- IMERG V07 `status=permanent` 在2025-09-30之后不可用，不可混用临时产品。日雨量与前7/30天均需要完整原始时段数据；前期ERA5-Land只用D-1日。
- 当前所有GEE v3**在线计算图尚未实测执行**，必须先完成MERIT20×20和M0日期Pilot后放行；本地测试与GitHub CI不能替代线上EECU测量。

## 官方来源

- ESA WordCover Download: <https://esa-worldcover.org/en/data-access>
- MERIT Hydro: <https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1>
- ESA WorldCover GEE: <https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200>
- GPM IMERG V07: <https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07>
- ERA5-Land daily: <https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR>
- GEE reduceResolution: <https://developers.google.com/earth-engine/guides/resample>
- GEE export alignment: <https://developers.google.com/earth-engine/guides/exporting_images>
- GEE tier/quota: <https://developers.google.com/earth-engine/guides/noncommercial_tiers>
