# CEE GF10 V6 — MERIT缓冲科学闸门 + Groundsource高特异病例×气象候选日两阶段GEE

2026-11-05。独立源目录，不修改旧版v3/v4/v5任务、GeoTIFF或账本。**GitHub PR只提交源码，不向Earth Engine提交任务；此版本的真实GEE任务必须在用户的Windows电脑通过明确`--execute`启动。**

## 核心科学结论

- v5 `v5_science_equivalence.json` = `FAIL_COMPACT_ROI`。3区域×16波段，最大相对差8.982%，主要风险为上游汇流面积均值，不能以工程QC通过为由放行全球生产。
- v5有7个已工程验收文件、578个陆地格；16,860个安全父块包含1,395,021格；14个接缝隔离块涉及450格，仍然保留。所有已完成旧任务只读。
- v5项目监控记录已完成EECU约3.122255小时（batch+online），与v3记录的0.0267h不能混为一谈。项目非商业配额层级必须在Cloud Console核对。
- Figure1 `outputs/fig1_publication_r3/labels/grid_day_observations.parquet` 只是报道源，没法凭空生成真实洪涝阴性。`source_event_id`, `grid_id`, `date_utc`, `city_id`, `label_source`, `date_precision`, `location_precision` 必须可追溯、明确映射后才做报道病例；storm_id 必须来自独立且质量可核对的风暴目录，不得用新闻当气象独立风暴证据。
- **IMERG V07 permanent截止2025-09-30。** 日内3h峰是43个半小时起始位置、每窗口6个半小时雨量积分；雨强 mm/h ×0.5h；前7/30天要求336/1440条观测；ERA5-Land 前一个完整UTC日的土壤水、温度、日累计降水（m→mm）不能与当天变量混用，缺测保留缺测。

## 两条安全生产路径

### A. MERIT科学等价与首个正式生产块

**前置**：本机已部署并通过验证：

`E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105` （完整v3 16波段`ceeprodgee.ee_model.merit`）

`E:\GEE_flooding\CEE_GF10_GEE_RECOVERY_V4_20261105`（v4配置、真实GEE项目、16,860安全块、7个旧工程QC）

`E:\GEE_flooding\CEE_GF10_GEE_PRODUCTION_V5`（v5科学FAIL及缓冲测量输入，可读不改）

解压本ZIP到 `E:\GEE_flooding`，然后：

```powershell
$ROOT='E:\GEE_flooding'
$P="$ROOT\CEE_GF10_V6_SCIENCE_COHORT_20261105"
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\00_verify_and_inspect.ps1 -Root $ROOT
.\scripts\04_halo_and_weather_dryrun.ps1 -Root $ROOT
```

只读预览3个代表性旧v5比较地区，每个20/40/80 km缓冲：

```powershell
$PY="$ROOT\.venv\Scripts\python.exe"
$V3="$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
$env:PYTHONPATH="$P;$V3"
& $PY -m cee_v6 halo-submit --root $ROOT --key merit_1090_360_10 --halo 20
```

真正提交恰好一个：

```powershell
& $PY -m cee_v6 halo-submit --root $ROOT --key merit_1090_360_10 --halo 20 --execute --confirm CEE_GF10_MERIT_M0_SCIENCE_V6_20261105
& $PY -m cee_v6 status --root $ROOT
```

从Google Drive同名`CEE_GF10_MERIT_M0_SCIENCE_V6_20261105`文件夹下载该任务结果，放入本包`downloads`。**实际文件名以`reports/v6_tasks.json`为准**，不要改动v3/v4下载目录。

```powershell
& $PY -m cee_v6 halo-audit --key halo20_merit_1090_360_10 --file "$P\downloads\CEE_GF10_MERIT_M0_SCIENCE_V6_20261105_halo20_merit_1090_360_10.tif"
& $PY -m cee_v6 live-accept --root $ROOT --key halo20_merit_1090_360_10
```

每次需要`SUCCEEDED`、下载、宽高/16波段/仿射+物理约束审计、实际EECU到账才能提交下一任务。重复以上操作直至3区域×3缓冲共9次（均小样本）。区域：`merit_1090_360_10`、`merit_700_230_10`、`merit_-1720_670_10`。

每个区域有实际的三个TIF后：

```powershell
& $PY -m cee_v6 halo-compare --root $ROOT --tile-key merit_1090_360_10 --tif20 "<实际已验收halo20 TIF>" --tif40 "<实际已验收halo40 TIF>" --tif80 "<实际已验收halo80 TIF>"
# 对其余两个区域同样调用halo-compare
& $PY -m cee_v6 halo-approve
```

`halo-approve`除了数值收敛，还校验9个任务都已真实GEE成功及通过QC、TIF的SHA与比较报告一致；仅对40→80 km收敛限值执行判定（p95相对误差≤0.5%、最大≤2%、掩膜必须一致）。20→40 km只作为缓冲灵敏度证据。该阈值为预先冻结的**工程收敛门槛**，不是物理洪水真值验证；若未过不能通过扩大容差强行发布。

首批安全块正式生产：

```powershell
& $PY -m cee_v6 merit-submit --root $ROOT --key merit_1080_360_10
# 仅在科学闸门PASS后，显式submit一个真正安全块
& $PY -m cee_v6 merit-submit --root $ROOT --key merit_1080_360_10 --execute --confirm CEE_GF10_MERIT_M0_SCIENCE_V6_20261105
```

对正式块也须下载、`halo-audit --key merit_final80_merit_1080_360_10`、`live-accept`。冻结`merit_v6_science_accepted_partial.parquet`：

```powershell
& $PY -m cee_v6 merit-assemble --root $ROOT
```

只有全1395471格唯一覆盖且14隔离块单独完成才能说MERIT全球完成。当前版本只实现**单块严控提交和部分输出组装**，不允许未经分区成本实测批量提交上万个任务。

### B. Figure1报道病例 -> 未标记日候选 -> 正式M0 GEE预提取

**关键逻辑：先提取候选天气，然后匹配。没有气象信息时不可声称最终匹配对照。**

1. `inspect-fig1`只读取真实Figure1原始列名；显示`source_event_id,grid_id,date_utc,city_id,label_source,date_precision,location_precision`语义。`date_precision`与`location_precision`必须来自上游已审核QC，不得给所有记录填`exact_day`或`high_specificity`以通过。
2. 使用真实映射保存到`config/fig1_verified_column_mapping.json`，**由Codex实读本地文件自动映射，若字段缺失则修复上游Figure1处理并执行真实QC后重试**。
3. 默认正式开发期2021–2023。后续2024–2025-09-30须另建版本并保存变化审计；截至2025-09-30之外的雨量不得直接使用v07 permanent。
4. 将同一天同一GF10同一城市的报道折叠为一次`reported_case`，保留多个原始新闻事件ID/来源。排除时间/位置精度不足的观测并记录所有排除计数。
5. 同格按同星期±14..63天选择最多8个日期，排除全城市报道日期±7天：仅为`unlabeled_calendar_candidate`，不是无洪水阴性。按原事件映射来源+版本追踪。
6. 只提取候选病例/日的MERG/ERA气象，不触及全球所有陆地格的所有日期；按同日期×10x10 GF10块去重，最多100个格日一任务。每日气象图像共享同一任务的所有格。
7. 下载CSV后核对任务状态、键、48/336/1440半小时计数，缺失不填0。允许`ERA5-Land`在海岸/海面掩膜缺失并产生独立缺失率，但不能当作无土壤水；对模型样本严格要求变量完整性。
8. 使用已冻结/来源审计的**本地每日强降雨P95阈值**及相对降雨差距配对，输出`matched_unreported_exposure`。外部独立气象风暴/区域ID必须明确核验后才能宣称真正的留出风暴验证。阴性标签始终不是“真实没有洪水”。

命令（前3步不发生GEE费用）：

```powershell
.\scripts\01_inspect_fig1.ps1 -Root $ROOT
# Codex核对实际字段后生成 config/fig1_verified_column_mapping.json
.\scripts\02_freeze_real_cases.ps1 -Root $ROOT
.\scripts\03_prepare_candidate_meteo.ps1 -Root $ROOT -Candidates 8
.\scripts\04_halo_and_weather_dryrun.ps1 -Root $ROOT
```

真实天气首任务（从`plans/event_requests_v6.csv`读取实际Key）：

```powershell
$K=(Import-Csv "$P\plans\event_requests_v6.csv" | Select-Object -First 1).request_key
& $PY -m cee_v6 weather-submit --root $ROOT --key $K
& $PY -m cee_v6 weather-submit --root $ROOT --key $K --execute --confirm CEE_GF10_MERIT_M0_SCIENCE_V6_20261105
```

Google Drive输出CSV下载至 `downloads`后：

```powershell
& $PY -m cee_v6 weather-audit --root $ROOT --key $K --file (Join-Path $P ("downloads\CEE_GF10_MERIT_M0_SCIENCE_V6_20261105_$K.csv"))
& $PY -m cee_v6 live-accept --root $ROOT --key $K
& $PY -m cee_v6 weather-assemble --allow-partial  # 仅部分/小样本
```

全部预先冻结的候选天气任务验收后才运行不带`--allow-partial`的`weather-assemble`并开展主文配对。示例匹配（必须将政策中的20mm演示值改成经审计的预注册阈值，并且提交真实P95表）：

```powershell
& $PY -m cee_v6 weather-match --cohort "$P\data\cohort_v6\preweather_reported_and_unlabeled_candidates.parquet" --weather "$P\data\cohort_v6\weather_verified_v6.parquet" --policy "$P\config\exploratory_rain_matching_policy.json" --out "$P\data\cohort_v6\weather_matched_provisional.parquet"
```

正式稿气候百分位匹配必须追加 `--rain-p95 <真实GF10原始每日降水P95表> --publication`，且独立风暴留出必须有独立storm_map并 `--require-storms`；不能用ERA5-EX年度R95p累计量直接替代逐格日降雨P95阈值。

## 引用与官方说明

- Google EE best practices: https://developers.google.com/earth-engine/guides/best_practices
- Google EE projections: https://developers.google.com/earth-engine/guides/projections
- Google EE Export image: https://developers.google.com/earth-engine/guides/exporting_images
- IMERG v07 official: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5 Land Daily: https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- ERA5-EX Scientific Data 2026: https://www.nature.com/articles/s41597-026-08312-x

## 本包没有完成的环节

- 未取得用户本机`E:\GEE_flooding`源Parquet字节，因此没有在本对话生成真实病例/对照表、没有对任何真实事件提交GEE任务。
- 未获得v5新缓冲ROI的GEE结果，因此保持其科学等价状态FAIL。新v6要求9个真实任务的结果和独立对照。
- 已实现校验及单任务提交接口，但全域安全任务高可靠无人值守并发调度、14接缝块恢复、全部动态匹配及外部物理洪水证据必须继续在用户电脑执行。不能因代码运行成功而宣称主文完成。

### 旧v4工程通过但科学未等价的578格如何收尾

v5表明旧工程通过≠与缓冲科学等价。三个已提交的80km参考TIF若在新科学Gate通过后可直接复用为正式16波段数据，不必重新消耗GEE。其余旧工程通过的格网**不得自动沿用旧数值**。只有确有必要且有逐块理由，命令显式允许复算：

```powershell
& $PY -m cee_v6 merit-submit --root $ROOT --key <原工程成功块ID> --recalibrate-legacy --reason "v5 compact ROI differs from independently converged 80km buffered results; original engineering data retained" # DRY RUN
```

随后增加 `--execute --confirm` 才会重新提交该受控块；新文件与旧文件均保留SHA和任务记录，不修改旧成果。这是科学一致性所需的有限重算，不是默认重复提交。
