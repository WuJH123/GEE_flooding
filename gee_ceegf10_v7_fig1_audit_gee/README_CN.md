# CEE Figure 1 → Figure 2 v7：逐条溯源的报道病例与 GEE 气象暴露生产包

**研究问题**：暴雨条件下，地形、汇流与城市地表是否使新闻中记录的城市洪涝响应发生可跨地域迁移的差异？本代码产出的是**可溯源的 Groundsource 报道正例**及其 *IMERG/ERA5-Land 气象暴露*，不是实测洪水真值，也不是每个格网每天的洪水概率。

**已知真正的项目结果**：冻结 GF10=1,395,471 陆地格（EPSG:6933，每格10km，不依赖城市筛选）；v6在武汉、沿海及高纬的3处20/40/80km计算缓冲数值收敛通过，16个MERIT波段与掩膜40→80km一致；已独立验收一个新10×10安全块、partial MERIT仅375格。14个接缝块的450格仍未完成。**本次v7的GitHub源码不代表新GEE任务已运行，也不改变任何旧任务账本。**

## 1. 为什么不能把`start_date=end_date`写成“已核实UTC日”

原 Groundsource v1 公共Parquet共2,646,302条，列为`uuid,area_km2,geometry,start_date,end_date`。官方文献说明：日期是新闻抽取得到的连续洪涝报道日界，geometry是被提到地点的地理编码区域，可能是行政区多边形或点缓冲，并非实测积水范围。论文随机审查400条，60%同时在时间和地点上完全匹配，另外22%实用但不精确；这个结果绝不是任一记录的独立质量标签。因此：

- `source_local_date`：只接收原始`start_date==end_date`且与`raw_uuid_tiers.date`一致的一日范围（不是独立验证准确日期）。
- `date_utc`：提供**供GEE运行的日历UTC代理键**，源新闻**未提供事件时刻或时区**。论文需报告D−1/D/D+1灵敏度；没有新闻原件不得标注为`verified_UTC_day`。
- `uuid`：原始来源记录；不同UUID不等于不同独立风暴。
- `geometry`：新闻提及地点的地理编码范围；只能用于定位报告，绝不能当实际淹没范围或水深。
- `city_id`：按官方GHS-UCDB R2024A唯一地理交叠归属，不由城市名字符串臆断；非UCDB城市中心地带不是“错误新闻”。

官方资料：
- 原文（含Table 2及人工审查）：https://eartharxiv.org/repository/object/12083/download/21690/
- Groundsource正式文件与MD5：https://zenodo.org/records/18647054
- UCDB R2024A：https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php
- IMERG V07：https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5-Land每日集合：https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- GEE多多边形结果导出：https://developers.google.com/earth-engine/guides/exporting_tables

## 2. 来源和冻结策略

从用户本地**真实已有文件**读取，绝不从20km旧标签推导10km：

| 数据 | 路径 | 用途 |
|---|---|---|
| Groundsource原始 | `E:\GEE_flooding\data\raw\groundsource_2026.parquet` | 2,646,302条真实UUID、原始日期及几何，按当前审计SHA冻结 |
| Fig1逐UUID质量层 | `E:\GEE_flooding\outputs\fig1_publication_r3\labels\raw_uuid_tiers.parquet` | `event_id, grid_id, date, primary_overlap, n_candidate_cells, geocode_quality, spatial_temporal_tier` |
| 冻结GF10 | `E:\GEE_flooding\gee_ceegf10_v1\gf10_global_nonantarctic_land.parquet` | `grid_id,grid_x,grid_y,land_area_km2`，SHA固定 `4ebf864c...` |
| UCDB官方GPKG | 优先 `E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg` 或 `E:\GEE_flooding\data\reference\GHS_UCDB_GLOBE_R2024A.gpkg` | 真实UCDB城市多边形，不使用未经空间核验的34,428格主导交叉表 |
| MERIT已验收 | `E:\GEE_flooding\CEE_GF10_V6_SCIENCE_COHORT_20261105` | v6的科学闸门、16波段及已接受TIF，只读 |

**A类来源筛选**与原库一致：`spatial_temporal_tier='A'`，`primary_overlap>=0.8`（**小数，不是Boolean**），`n_candidate_cells<=4`，`geocode_quality='HIGH_GEOCODE_SPECIFICITY'`。本版本增加：原始`start=end`且Figure1日期一致、实际几何投影到冻结GF10交叠>=85%、地理编码地点范围<=25km²、GHS-UCDB官方城市多边形重叠>=85%且不存在多个城市竞争。被剔除UUID都登记排除原因；此处过滤的UCDB核心之外报告不可当作假记录。

**注意**：A质量层、85% overlap及地理编码范围阈值是位置**特异性筛选条件**，**并不是**独立新闻核验或卫星洪水证据；它们既有地理覆盖不均衡，也可能因国家新闻习惯和UCDB面积偏差导致选择偏差。Figure1必须报告入选率和每国/城市覆盖分母。

## 3. 一键运行（PowerShell，任何一步FAIL即停止）

将`CEE_GF10_FIG1_AUDIT_GEE_V7_20261106.zip`复制到`E:\GEE_flooding`。开PowerShell：

```powershell
$ROOT = 'E:\GEE_flooding'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_FIG1_AUDIT_GEE_V7_20261106.zip" -DestinationPath $ROOT
$PKG = "$ROOT\CEE_GF10_FIG1_AUDIT_GEE_V7_20261106"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force
$PY = "$ROOT\.venv\Scripts\python.exe"
if(!(Test-Path $PY)) { $PY="$ROOT\CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe" }
& $PY -m pip install -r "$PKG\requirements.txt"
.\scripts\00_check.ps1 -Root $ROOT
.\scripts\01_build_provenance.ps1 -Root $ROOT
.\scripts\02_preextract_plan.ps1 -Root $ROOT -Candidates 4
```

> `01_build_provenance.ps1`会对约2.6百万条逐批扫描；不需要把所有原始地理编码多边形一次加载到内存。UCDB唯一官方多边形层读取一次，GF10只需整数索引。若官方UCDB文件具有不止一个可用图层/ID字段，代码仅在能按原Figure1约定唯一识别`GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A`、`ID_UC_G0`时自动选取；否则**停止**要求本地文件真实字段检查，不会猜测。若某输入SHA变动也停止，需先审计数据版本。

产物：

1. `data/source_lineage/groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet`（逐条源UUID、原始行号、来源日期/范围、几何SHA、GF10/UCDB重叠比例及城市ID）。
2. `data/source_lineage/rejected_high_tier_uuid_reasons.csv`（源定位或日期不满足条件的逐条原因）。
3. `data/case_source/reported_source_day_cases_PROVISIONAL.parquet`（源报告格网日）。
4. `data/case_source/case_uuid_membership.parquet`（一对多原始UUID溯源，不把多UUID当多风暴）。
5. `data/case_source/independent_review_template.csv`（真实400条分层人工复核队列，来源URL/原文证据需要人工真实填写）。
6. `plans/reported_and_UNLABELED_calendar_candidates.parquet`（同格相近季节星期候选，未报道**不是**洪水阴性）。
7. `plans/unique_GF10_UTC_proxy_days.parquet`、`plans/gee_weather_date_tile_plan.csv`（有真实数据的格网×日期任务计划）。
8. QC JSON和每个原始数据SHA256。全球计划生成后**不会自动提交**，先检查`planned_GEE_tasks`与预算可接受程度。

## 4. 真实GEE试验：先一项；后最多3项

```powershell
# 先查看已冻结日期与计划数（无GEE费用）
& $PY -m cee_v7 --root $ROOT weather-preflight

# 先用真正可用的计划文件选取一个request_key。PowerShell脚本自动取首个，不用自己写日期：
.\scripts\03_one_gee_weather_pilot.ps1 -Root $ROOT

# 人工阅读单项预览，确认时间窗口与格网数量后才真正提交 ONE TASK：
.\scripts\03_one_gee_weather_pilot.ps1 -Root $ROOT -Execute

# 任务状态/真实EECU
& $PY -m cee_v7 --root $ROOT weather-status
```

GEE使用现有`future-shuttle-513705-g9`项目；沿用经验证的v3 `event_image`表达式：IMERG V07 permanent半小时雨强mm/h×0.5为mm，UTC日最大3h的43个完整窗口、日累计、前7/14/30日累计以及各区间观测计数；ERA5-Land只读取**前一日**土壤含水量、气温、累计降水、径流及风速。输出按**源气象原生约0.1°尺度**对每个GF10多边形聚合，不能将重采样结果称为原生10km气象观测。

IMERG permanent目前截止**2025-09-30**，因此该版本严格拒绝更新日期。模型请求的UTC日是源报告日历代理，并非当地真实洪水发生时刻；D±1日期灵敏度和风暴ID独立验收仍是论文的必需项。

每次真实表任务成功后：从Google Drive专属文件夹`CEE_GF10_FIG1_AUDITED_WEATHER_V7_20261106`下载对应的CSV至本包`downloads`（不会自动下载或上传私有Drive文件）。

```powershell
$K=(Import-Csv "$PKG\plans\gee_weather_date_tile_plan.csv" | Select-Object -First 1).request_key
$CSV="$PKG\downloads\CEE_GF10_FIG1_AUDIT_GEE_V7_20261106_$K.csv"
& $PY -m cee_v7 --root $ROOT weather-audit --key $K --file $CSV
& $PY -m cee_v7 --root $ROOT weather-assemble
```

凡CSV行数不符、重复格网日、缺半小时数据或ERA5空缺都不标记完整成功，也不补0。需要真实云端`SUCCEEDED`、本地CSV、SHA、源计数、GEE EECU才可放行下一批。默认单次最多3个GEE气象试验；扩大并发必须根据真实EECU和UCDB病例规模测算，非商业额度不等于无限。

## 5. 两位审阅者的独立报道证据：正式发表层

Groundsource公开Parquet不含新闻URL或人工逐条核实字段。不能用同一Parquet自动验证自己。需从真实新闻链接、可引用的地方记录（独立性另行审核）完成以下人工模板，列值必须来自**实际的证据来源**：

`uuid,source_article_url,excerpt_confirms_flood_day,excerpt_confirms_locality,reviewer1,reviewer2,reviewer1_verdict,reviewer2_verdict,audit_date_utc,evidence_kind,independent_evidence_url`

只有两个不同审阅者均填`CONFIRMED_DAY_AND_LOCATION`且新闻链接及关键文字均真实存在时，才形成`MANUALLY_VERIFIED`报道日层（仍不是独立水深/淹没真值；源日期仍按日历UTC代理需要敏感性）。

```powershell
& $PY -m cee_v7 --root $ROOT verify-manual --review-file "$PKG\data\case_source\independent_review_template.csv"
```

**注意**：刚生成的空白模板运行会主动失败，而不是自动制造“核实通过”。

## 6. 事件后处理和论文因果边界

v7试验气象输出仍属于**报道响应**的M0暴露，若想实现对照匹配，需要所有日期真实气象完成后使用v6匹配逻辑，且匹配前冻结规则与独立GF10日降水P95基线。`v7 weather-match`提供对既有v6方法的严格调用；`--publication`必须额外提供真实双人审核病例、当地P95和外部独立风暴目录，仍不能把“未报道”当真实阴性。

MERIT全球16波段的真实GEE计算使用v6已经通过的80km计算缓冲和固定EPSG6933 10km核心像元；v7仅输出安全下一个任务建议，**不复制或重跑**已有9个缓冲任务与375个accepted格。14接缝块450格仍保留隔离。

```powershell
& $PY -m cee_v7 --root $ROOT merit-next --n 6
```

以该命令真实列出的`merit_tile_key`逐块执行v6 `merit-submit`、下载GeoTIFF、`halo-audit/live-accept`，并通过其科学闸门。未经多区域/成本充分验收不一次提交16,860个安全块，也不得将不完整的部分Parquet命名为全球完备指标。

## 7. 无法通过自动生成消除的科学缺口

- Groundsource无原文URL：需要真实新闻/地方记录复核，并抽样估计地理与时间错误率，不可把全部高Tier写成verified。
- UCDB仅覆盖官方urban centres：报告入选概率、国家与城市层面的选择偏差，不可将缺失匹配当作无洪水。
- 源日期无时区/时刻：需D−1/D/D+1和独立风暴窗口稳健性；GEE UTC日只是计算时标。
- 物理淹没及独立观测的“干日”仍缺失：无此证据只能称Flood Reporting Response；城市基础设施与气象因果机制需要外部物理验证。
- 3地区的40→80km收敛不是全球每个区域的物理水文真值；14个接缝格未恢复，不可宣布全球MERIT覆盖100%。

**代码CI只验证算法和质量闸门，不能替代你本地2.6百万原始数据的实际运行与Google Cloud任务。**
