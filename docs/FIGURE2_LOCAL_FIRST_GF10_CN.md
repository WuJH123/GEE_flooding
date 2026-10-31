# Figure 2 — 本地优先提取 10km GF10 韧性指标（中文版）

仓库：WuJH123/GEE_flooding。新产生的全部文件只写在 E:\GEE_flooding；E:\Global_flooding、E:\数据集、D:\博士资料\GIS材料只读。本流程不删除、不移动、不解压655GB历史文件，不自动下载数据或向GEE提交任务。

【科研定位】强降雨条件下的城市暴露性、敏感性与潜在绿蓝空间适应条件代理量。它们不是工程管网的实测韧性，不能替代后续城市积水独立验证。Fig2a已画好，但2b–e正式实证还需要真实的2021–2025暴雨完整面板与物理正负样本。

## A. 优先使用本地的什么

- GF10、Groundsource及Figure1-v2/v3的交叉表：使用现有Parquet，不生成第二套全球网格。
- GHSL BUILT-S 2000/2020：按原始100m像元的建成面积(m²/pixel)精确交叠求和；除1e8可转为10km格内建成份额，除1e6可得km²。
- MERIT Hydro hnd/elv/upa：hnd和elv为米，upa本身为km²，计算10km区域均值；没有验证的DEM或20km衍生结果不能替代。
- 本地土地覆盖/GAIA/GISD30：必须核对原产品类别和年代，2021 ESA WorldCover的类别编码只能用于ESA v200，不适用于任意1km土地利用。
- GHSL GHS-POP：只准使用人数/原始像元的计数图来做精确sum。WorldPop若是人口密度，必须先换算为每像元人数，不能当作计数sum。
- NDVI、GRIP道路、旅行时间、夜间灯光、GDP、BUILT-V：作为第二阶段需要单独空间/时段对齐的指标，不自动混入核心M0–M4；绿地和道路均不是已测排水能力。
- CN-Floods、河南、伦敦、武汉监测：只作为候选真实水体/水深或城市积水证据，不能把风险图/新闻事件/模拟场当真实正负标签。

公开权威资料（核对原生产品定义）：
IMERG https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
ERA5-Land https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY
MERIT https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
GHSL https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S
ESA WorldCover https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
原生像元与GF10多边形精确叠加 https://isciences.github.io/exactextract/

## B. 先运行最便宜、最快且不下载数据的盘点

在PowerShell依次运行：

    Set-Location E:\GEE_flooding
    git status --short
    git fetch origin
    git pull --ff-only origin main
    $ROOT = "E:\GEE_flooding"
    $PY = "$ROOT\.venv\Scripts\python.exe"
    & $PY -m pip install -e ".[test,local]"
    & $PY -m pytest -q
    & $PY -m gee_flooding.fig2_preflight --root $ROOT --city-audit-v3 "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_local_first --index "$ROOT\outputs\dataset_inventory_20261031.csv" --root $ROOT --tag fig2_local_candidates_20261031

如果git status显示有本地未提交修改，先检查而非硬重置。如v3审计实际为另一版本，替换为真实已验收文件路径。

打开如下CSV：
- reports\fig2_local_candidates_20261031\fig2_local_candidates.csv：真实路径、CRS、波段、分辨率、文件大小与能否继续人工审查。
- reports\fig2_local_candidates_20261031\fig2_family_gaps.csv：数据类别，本地候选存在数及GEE候补来源。
- reports\fig2_local_candidates_20261031\fig2_local_first_qc.json：盘点仅为存在性与元数据审计，非提取结果。

注意：如果原库存CSV只有“文件名”而不是完整绝对路径，程序会明确报错，先修改Codex索引列，不要假设路径。ZIP和RAR仅登记为候选，不会自动解压。

## C. 建立地理分层 GF10 试验子集，避免随机挑同一城市

    $F1 = "$ROOT\outputs\fig1_v2"
    $AUDIT = "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_sampling --root $ROOT --grid "$ROOT\data\reference\grid10_urban_2020.parquet" --crosswalk "$F1\fig1_grid_dominant_ucdb.parquet" --cities "$F1\fig1_ucdb_city_sample_audit.csv" --city-audit-v3 $AUDIT --max-cities 40 --cells-per-city 12 --seed 42 --tag fig2_subset_local_v1
    $GRID = "$ROOT\data\reference\fig2_subset_local_v1\fig2_GF10_selected_grid.parquet"

计划约40个城市、上限480个10km格。实际检查sample_qc，训练候选与2021–2023期冻结的留出城市是否同时包含。该子集是任务pilot，不代表全球事件发生率。若所选20格不落在某本地栅格覆盖范围内，该指标应当为空，换目标城市/格网或用GEE补采。

## D. 用本地合格栅格生成第一个10km指标

从候选CSV中找到真实的、已检查单位与年份的栅格。复制示例JSON并改成真实文件路径和产品band：

    New-Item -ItemType Directory -Force "$ROOT\data\reference\fig2_manual" | Out-Null
    Copy-Item "$ROOT\config\fig2_local_sources.example.json" "$ROOT\data\reference\fig2_manual\my_sources.json"
    notepad "$ROOT\data\reference\fig2_manual\my_sources.json"

默认模板包含GHSL BUILT-S(2020)以及MERIT HAND的两个示例；并不保证示例路径真实存在，必须逐一替换。只保留实际有数据的变量。要处理其他变量，参考 gee_flooding/fig2_local_exact.py 中的 SUPPORTED 与 CLASS_CODES。每个变量必须声明name、dataset、epoch、kind、paths及band，GHSL BUILT-S额外要求native_units为m2_per_native_pixel。

执行（首先20格，之后按范围分批增大）：

    & $PY -m gee_flooding.fig2_local_exact --root $ROOT --grid $GRID --manifest "$ROOT\data\reference\fig2_manual\my_sources.json" --start-row 0 --count 20 --min-coverage 0.95 --tag fig2_local_exact_pilot_v1

输出:
- data\derived\fig2_local_exact_pilot_v1\fig2_local_GF10_indicators.parquet
- data\derived\fig2_local_exact_pilot_v1\fig2_local_exact_qc.json

特别注意：这里严格要求源Raster为**已验证的米制投影CRS**，不接受EPSG4326经纬度像元直接求物理面积，也不静默用重采样替代原生像元。原生像元与GF10边缘的交集按覆盖比例精确计入。有效覆盖不足95%则输出NaN并标记coverage字段；大于100%说明tile重叠或面积不一致，直接报错。若源文件是多波段或单位不明，不要猜band。

本地某源资料不覆盖当前格网，属于空间缺测而不是“没有洪水/没有建筑”。

## E. 先不下载新数据，得到GF10统一指标宽表和GEE精确缺口

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local "$ROOT\data\derived\fig2_local_exact_pilot_v1\fig2_local_GF10_indicators.parquet" --tag fig2_integrated_GF10_pilot_v1

结果：
- data\derived\fig2_integrated_GF10_pilot_v1\fig2_GF10_resilience_indicators.parquet
- 同目录fig2_indicator_coverage.csv：每列实际有效格数
- 同目录fig2_core_indicator_gate.csv：核心指标是否覆盖完整
- 同目录fig2_gee_missing_indicator_plan.csv：哪些字段/多少格需要GEE补采
- 同目录fig2_source_conflicts.csv：本地与GEE重叠时的数值冲突
- 同目录fig2_GF10_indicator_merge_qc.json：本批次质量状态。不得仅凭这一步称发表验证通过。

## F. 只对缺口提交GEE，继续使用新版有界CSV导出避免旧错误

先DRY_RUN（这三行均不会提交）：

    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode static --start-row 0 --count 20
    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode exposure --start-row 0 --count 20
    & $PY -m gee_flooding.fig2_gee_weekly --grid $GRID --start 2024-07-01 --days 7 --start-row 0 --count 20

已存在的本地MERIT/GHSL可减少GEE静态提取；完整2021–2025 IMERG和ERA5天气更可能是P0缺口。实际提交先配置GEE Cloud project，之后**仅提交真实缺失的模式**：

    $PROJECT = "YOUR_EARTH_ENGINE_CLOUD_PROJECT"
    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode static --start-row 0 --count 20 --project $PROJECT --submit
    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode exposure --start-row 0 --count 20 --project $PROJECT --submit
    & $PY -m gee_flooding.fig2_gee_weekly --grid $GRID --start 2024-07-01 --days 7 --start-row 0 --count 20 --project $PROJECT --submit

GEE任务须显示COMPLETED，并从Google Drive下载CSV到数据文件夹后才算有数据；READY或SUBMITTED不是完成。本版本保持本地EPSG6933的10km格网，云端用EPSG4326几何和小范围reduceRegions输出CSV，不导出巨幅全球GeoTIFF。单周天气任务最多30格、7天，不能直接批量循环覆盖全球五年。生产级月度分区任务管理仍是后续P0。

下载到：
- data\gee_exports\fig2_static\ 下的 f2_static_*.csv
- data\gee_exports\fig2_exposure\ 下的 f2_exposure_*.csv
- data\gee_exports\fig2_weather\ 下的 f2_weather_*.csv

此时可把已完成静态/人口GEE CSV与本地GF10栅格指标合并：

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local "$ROOT\data\derived\fig2_local_exact_pilot_v1\fig2_local_GF10_indicators.parquet" --gee-static "$ROOT\data\gee_exports\fig2_static" --gee-exposure "$ROOT\data\gee_exports\fig2_exposure" --tag fig2_integrated_GF10_pilot_v2

如果没做合格本地提取，则去掉--local。没有下载某类GEE CSV则不要传对应--gee-static或--gee-exposure，缺口将如实保留。出现同一指标明显不一致时，保留本地优先值并生成source_conflicts.csv，正式发表前必须复核来源单位、地理范围与算法。

## G. 后续正式Fig2的发表验收

必须通过六项：GF10格网和UCDB城市归属唯一；GHSL像元面积及人口总量守恒；IMERG每天48幅、前期七天336幅有效影像与±日期位移审计；M0–M4相同留出城市/风暴和训练集内调参；独立的实际内涝正例+有效观测未淹没记录；Fig2b–e指标来源、有效覆盖、无法推断地区及不确定性明确。

对实在缺失且下载量小于10GB的区域小数据，可以从产品官方链接按城市/事件取得（先核查许可与文件体积），不得自动抓取整个全球资料。CN-Floods、河南、伦敦及武汉本地已存在时，不重新下载同类事件包。

**本次代码只实现local-first的真实格网指标路径与GEE静态补缺判断；还没有读取用户本机655GB实际文件，不能报出全球已得到多少有效指标。**


## H. 新增：最精确的GEE缺失波段与缺失格网补采（不要重采全部静态变量）

先检查 integrated_GF10 宽表和 gap CSV；例如仅有部分城市的 HAND 不完整：

    $INTEGRATED="$ROOT\data\derived\fig2_integrated_GF10_pilot_v1\fig2_GF10_resilience_indicators.parquet"
    & $PY -m gee_flooding.fig2_gap_grid --root $ROOT --grid $GRID --indicators $INTEGRATED --indicator hand_m --tag fig2_gap_hand_v1
    $GAP="$ROOT\data\reference\fig2_gap_hand_v1\fig2_GF10_missing_grid.parquet"
    $GAP_QC=Get-Content "$ROOT\data\reference\fig2_gap_hand_v1\fig2_gap_grid_qc.json" -Raw | ConvertFrom-Json
    $GAP_N=[Math]::Min(20,[int]$GAP_QC.missing_GF10_count)

用只有缺失格网的文件，且只选缺失波段先dry-run：

    & $PY -m gee_flooding.fig2_gee --grid $GAP --mode static --bands hand_m --start-row 0 --count $GAP_N

核对任务描述、GF10首末格ID、GEE project和差异，再明确提交：

    & $PY -m gee_flooding.fig2_gee --grid $GAP --mode static --bands hand_m --start-row 0 --count $GAP_N --project $PROJECT --submit

对于坡度和汇流面积可使用 --bands slope_deg,upstream_area_km2；GHSL人口仅缺失时用 --mode exposure --bands population_count_2020。**不需要下载任意全球高分辨率GeoTIFF。**

这类选定波段任务文件名包含一致性hash，避免不同网格或不同指标导出同名。多个GEE表格CSV可以放在同一fig2_static/fig2_exposure文件夹，fig2_indicators 会按grid_id和字段逐个合并；若同一格同一字段重复且值不同，则报错，不会随意取平均。

完整GEE后续fig2_prepare模型准备仍要求完整静态因子。这个针对缺口的导出与合并用于构建GF10韧性静态指标表，**不等于已有真实的整个2021–2025事件暴露/物理验证**。
