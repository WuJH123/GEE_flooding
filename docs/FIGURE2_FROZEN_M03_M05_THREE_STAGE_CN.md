# Figure 2 冻结版 M03–M05：三步数据获取及五面板执行手册（2026-11-02）

**项目 GEE_flooding，目标 Communications Earth & Environment。** 冻结大纲的 Figure 2 研究问题：在相近极端降雨条件下，地形汇流、建成环境及历史增长对**洪涝新闻响应 O**是否提供跨城市可迁移的额外预测信息。Figure 3 才负责独立实际内涝 F 的物理正负验证；不能将 Groundsource 新闻与未报道暴雨直接解释为真实积水/无积水。

**Figure 2a** 暴雨总体、地形和观测机制示意；**2b** 相同留出样本的M0–M4 AP与配对增益；**2c** 时间、新城市、风暴和国家迁移；**2d** 气候区差异中的 M4−M0 配对增益；**2e** HAND×建成比例×暴雨强度条件响应，标注关联而非因果。

主模型变量：M0=真实日最大3h降水、日24h降水、前7个完整UTC日累计；M1=M0+HAND+坡度+上游汇流面积；M2=M1+城市建成比例和绿地/土地覆盖；M3=M2+邻域建成密度/局部异质性；M4=M3+历史建成增长。前期土壤水分/气温属于有用的可选M0b稳健性。M5必须有外部验证的报道选择机制，不能用任意权重伪称真实漏报修复。

底层分析时段 2021–2025、日尺度UTC；2021–2023开发，2024–2025未来留出；长期环境是固定2020、2021，以及GHSL 2000–2020历史变化。独立暴雨事件是目标分析单元；当无法独立追踪天气系统时保留GF10×UTC日，气象相连成分标成“代理风暴”，并在分组中审计事件独立性。千万不要为主论文永久保存全球半小时GF10面板；仅对分区时间块做短时滚动计算，输出每日3小时最大值。

## 第一步：已存在本地数据优先（不联网下载）

- 本地实际已有2020 GHSL BUILT-S，试验182/182个GF10有效；不要重复下载。源原生建成m²/100m像元按多边形原始像元交叠求和。E:\GEE_flooding 下的182格试验不是全球166414个冻结GF10全部研究域。
- 优先核查E:\数据集、D:\博士资料\GIS材料及只读E:\Global_flooding中MERIT、HAND、DEM、HydroATLAS、GHSL POP/2000/NRES、GISD30、WorldCover与NASA/ERA5旧成果；只有确实匹配GF10几何、原始单位和年份的才可使用。旧20km数据不可直接命名为GF10。
- Figure1 原始标签在E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet；高定位特异性代理还需人工审核，报道O≠积水F。禁止直接对新闻坐标KDE得到物理积水密度。
- 资料源自原始经纬度栅格时必须使用真实面积权重，不是简单最近邻映射。已验证ESRI:54009/EPSG:6933原生米制栅格可用 fig2_local_exact --backend shapely。

PowerShell：

    $ROOT='E:\GEE_flooding'
    $SRC='E:\GEE_flooding_code'
    if (-not (Test-Path "$SRC\.git")) { git clone https://github.com/WuJH123/GEE_flooding.git $SRC }
    else { git -C $SRC pull --ff-only origin main }
    Set-Location $SRC
    $PY="$ROOT\.venv\Scripts\python.exe"
    if (-not (Test-Path $PY)) { py -3.11 -m venv "$ROOT\.venv" }
    & $PY -m pip install -e "$SRC[climate]"
    & $PY -m gee_flooding.fig2_preflight --root $ROOT --city-audit-v3 "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"

将实际已有合格源与完成后的GEE表格合并成版本化审计宽表：

    $GRID="$ROOT\data\reference\fig2_subset_local_v1\fig2_GF10_selected_grid.parquet"
    $STATIC="$ROOT\data\derived\fig2_integrated_extended182_v4\fig2_GF10_resilience_indicators.parquet"
    if (-not (Test-Path $STATIC)) { throw "Static table not yet complete; finish stage 3 before models." }

## 第二步：可公开下载的小体积/分区数据优先，在本地聚合

1. NASA Earthdata GPM_3IMERGDF_07 Final V07B：每日0.1°、precipitation单位mm/day，precipitation_cnt为有效半小时时次。只下载研究城市/日期的空间子集；2021–2025每天和2020-12-25至12-31前7日必需。官方：https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary
2. ERA5-Land Daily Statistics：CDS按区域与年份下载前一UTC日 soil water layer1/layer2、2m温度，日统计请求时形成、非静态日文件。官方：https://cds.climate.copernicus.eu/datasets/derived-era5-land-daily-statistics?tab=download
3. 3小时极值：优先NASA IMERG Final V07B原生半小时产品，只按小区域/有限时间块下载；fig2_cf_grid将原生mm/h映射GF10×30min，在fig2_rolling3h中按连续6格乘0.5h计算真正滚动3h最大值，**最终只保存每日一行**。如采用8个固定3h窗的替代定义，使用fig2_3h但必须声明这是aligned不是rolling，不允许从日降水推导3h。https://gpm.nasa.gov/data/directory
4. 缺少2000 GHSL、2020 GHS-POP/NRES时，先从JRC官方选择地区和年份的栅格/区域瓦片；局部形态必须原生100m而不能直接用1km均值代替。https://human-settlement.emergency.copernicus.eu/download.php
5. ERA5-EX v4的1950–2025年年度极端降水指标与EarthEnv已预计算地形可选作国家/气候背景和独立核对，绝不代替事件当日降水。https://figshare.com/articles/dataset/ERA5-EX_v1_0_dataset/31812172 和 https://www.earthenv.org/topography
6. GISD30已有本地切片，确实缺地区再下载Zenodo地区压缩包（全球约1.3GB）。编码0透水、1–8历史不透水，不得直接数值均值。https://zenodo.org/records/5220816

### 2A. 原始已下载的 CF NetCDF → 真实GF10日雨量/ERA5

每次<=500 GF10，<=400个文件；输入为已裁剪的规则1D经纬度CF NetCDF。源像元与冻结等面积10km多边形真实面积相交，不假设0.1度就是GF10。源不是0.1度规则经纬或坐标跨反子午线则拒绝，需核对原产品并专项处理。

    $RND="$ROOT\data\external\IMERG_Final_V07B\region_202407"
    & $PY -m gee_flooding.fig2_cf_grid --root $ROOT --grid $GRID --input-dir $RND --glob "*.nc4" --variables "precipitation:rain_d_mm,precipitation_cnt:precipitation_cnt" --tag fig2_nasa_daily_202407_v1

    $ERA="$ROOT\data\external\ERA5Land_Daily\region_202407"
    & $PY -m gee_flooding.fig2_cf_grid --root $ROOT --grid $GRID --input-dir $ERA --glob "*.nc" --variables "swvl1:soil_water_0_7cm,swvl2:soil_water_7_28cm,t2m:temperature_2m_c" --tag fig2_era_daily_202407_v1

上面ERA5源字段示例需先用xarray核实真实变量名，源温度单位K会自动明确转换°C。结果 data\derived\<tag>\fig2_CF_daily_GF10.parquet。按年运行后，用：

    & $PY -m gee_flooding.fig2_cf_merge --root $ROOT --input-dir "$ROOT\data\derived" --glob "fig2_nasa_daily_*/fig2_CF_daily_GF10.parquet" --tag fig2_nasa_daily_2021_25_merged_v1

ERA5按实际年度范围同样合并到独立版本，不与NASA同字段重叠混用。

### 2B. 有界半小时原始数据只用于计算每日真正3小时滚动峰值

NASA Final V07B的原始mm/hour乘0.5小时；连续6个半小时时次形成一个3h窗口。每个7日小批次需额外向前包含2.5小时的5个半小时时次，避免UTC首日不完整。

    $HH="$ROOT\data\external\IMERG_Final_HH_V07B\region_20240701"
    & $PY -m gee_flooding.fig2_cf_grid --root $ROOT --grid $GRID --input-dir $HH --glob "*.nc4" --variables "precipitation:precipitation_rate_mm_h" --time-step halfhour --tag fig2_hh_region_20240701_v1

    & $PY -m gee_flooding.fig2_rolling3h --root $ROOT --input-dir "$ROOT\data\derived\fig2_hh_region_20240701_v1" --glob "fig2_CF_halfhour_GF10.parquet" --start 2024-07-01 --end 2024-07-07 --tag fig2_peak3h_20240701_v1

分区、分周得到真实3h峰值后：

    & $PY -m gee_flooding.fig2_cf_merge --root $ROOT --input-dir "$ROOT\data\derived" --glob "fig2_peak3h_*/fig2_daily_rolling_3h_max_GF10.parquet" --tag fig2_peak3h_2021_25_merged_v1

### 2C. 生成完整独立暴雨总体，要求气象和静态资料真实齐全

    $RAIN="$ROOT\data\derived\fig2_nasa_daily_2021_25_merged_v1\fig2_merged_daily_GF10.parquet"
    $PEAK="$ROOT\data\derived\fig2_peak3h_2021_25_merged_v1\fig2_merged_daily_GF10.parquet"
    $ERA_D="$ROOT\data\derived\fig2_era_daily_2020_25_merged_v1\fig2_merged_daily_GF10.parquet"
    $UCDB="$ROOT\outputs\fig1_v2\fig1_grid_dominant_ucdb.parquet"
    & $PY -m gee_flooding.fig2_daily --root $ROOT --grid $GRID --grid-cities $UCDB --rain-daily $RAIN --rain-3h-max $PEAK --rain3h-definition rolling_3h_max --era-daily $ERA_D --static $STATIC --start 2021-01-01 --end 2025-12-31 --tag fig2_daily_real182_v1

必须满足所宣称的全部GF10×UTC日期 + 前7日、每天原始48次有效观测、前7日336次、非伪造的3h、土壤水分只用前一UTC日。用 news 选择日期或把缺测天补零都将被拒绝。40城/182格如正例不足，仅用于技术pilot，不是可发表的全球总体。

## 第三步：只有本地缺失或公开下载规模过大时才用GEE

已有脚本 fig2_backfill_plan / fig2_gee_submit / fig2_gee_qc / fig2_indicators。优先在步骤1、2真正计算并合并本地数据后生成**一个新的扩展缺口计划**，不得把以前的40条core和40条extended两批都提交。

本轮保留GEE兜底：MERIT Hydro hnd/elv/upa/wat与坡度；ESA WorldCover 2021 v200分类比例；GHSL 2000基准及2020 100m邻域结构；缺失的GHSL GHS-POP 2020/NRES。全球10m WorldCover不建议全部下载，地理范围小可以只下载所需COG；2020与2021两版算法不同，不能未经修正直接解释两年土地覆盖变化。

    $MERGED="$ROOT\data\derived\fig2_integrated_ghsl182_v2\fig2_GF10_resilience_indicators.parquet"
    & $PY -m gee_flooding.fig2_backfill_plan --root $ROOT --grid $GRID --indicators $MERGED --scope extended --max-cells 20 --tag fig2_gee_gap_localfirst_v4
    $PLAN="$ROOT\data\reference\fig2_gee_gap_localfirst_v4"
    $PROJECT="YOUR_REAL_EE_CLOUD_PROJECT"
    $EE="$ROOT\.venv\Scripts\earthengine.exe"
    & $EE authenticate
    & $EE set_project $PROJECT
    foreach ($family in @("merit","landcover","builtform","population")) {
        & $PY -m gee_flooding.fig2_gee_submit --root $ROOT --plan $PLAN --family $family --max-tasks 1
    }
    # 确认干运行后才允许提交第一条
    & $PY -m gee_flooding.fig2_gee_submit --root $ROOT --plan $PLAN --family merit --max-tasks 1 --project $PROJECT --submit --confirm SUBMIT

GEE任务须实际在 https://code.earthengine.google.com/tasks 显示 COMPLETED。下载CSV到 data\gee_exports\fig2_static 与 fig2_exposure，再运行下面两个检查/合并（版本标签不可覆盖）：

    & $PY -m gee_flooding.fig2_gee_qc --root $ROOT --plan $PLAN --gee-static "$ROOT\data\gee_exports\fig2_static" --gee-exposure "$ROOT\data\gee_exports\fig2_exposure" --local "$ROOT\data\derived\fig2_local_ghsl182_v2\fig2_local_GF10_indicators.parquet" --require-complete --tag fig2_gee_gap_qc_v4

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local "$ROOT\data\derived\fig2_local_ghsl182_v2\fig2_local_GF10_indicators.parquet" --gee-static "$ROOT\data\gee_exports\fig2_static" --gee-exposure "$ROOT\data\gee_exports\fig2_exposure" --tag fig2_integrated_extended182_v4

若不使用GEE，只以已审计的本地源拼合；不可为了跳过门槛而填零。扩大到全球需按区域及年份分块，而非用182格试验冒称166414格。

## 四、得到真实数据后：Figure2全部分析模型与五面板

M03输出到 data\derived\fig2_daily_real182_v1，包括 storm_exposure_weather.parquet、static_grid_factors.parquet、fig2_extended_grid_factors.parquet 和 fig2_weather_provenance.json。与Figure1高定位特异性新闻标签按同一grid_id×date合并；未报道暴雨记未标记：

    $DER="$ROOT\data\derived\fig2_daily_real182_v1"
    $LABEL="$ROOT\outputs\labels\groundsource_gf10_primary.parquet"
    & $PY -m gee_flooding --root $ROOT panel --weather "$DER\storm_exposure_weather.parquet" --static "$DER\static_grid_factors.parquet" --labels $LABEL --tag fig2_daily_news182_v1
    $PANEL="$ROOT\outputs\panels\fig2_daily_news182_v1\storm_exposure_with_news_labels.parquet"

    $V3="$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_frozen --root $ROOT --panel $PANEL --city-audit-v3 $V3 --weather-contract "$DER\fig2_weather_provenance.json" --tag fig2_frozen_daily_real182_v1

    $CITYMETA="$ROOT\outputs\fig1_v2\fig1_ucdb_city_sample_audit.csv"
    & $PY -m gee_flooding.fig2_publication --root $ROOT --frozen-dir "$ROOT\outputs\fig2_frozen_daily_real182_v1" --panel $PANEL --cities $CITYMETA --tag fig2_a_e_daily_real182_v1

主要输出：outputs\fig2_a_e_daily_real182_v1\Figure2_a_e_news_proxy.pdf、PNG、fig2d_climate_paired_delta_AP.csv、fig2e_hand_built_rain_news_rates.csv 和全部QC。模型训练、拟合及留出验证在本地执行，不需要在GEE上训练XGBoost。原有Fig2_frozen提供Logistic（训练内标准化）与HistGradientBoosting基线、2021–23/2024–25冻结城市与事件留出、按风暴配对bootstrap差值。

**正式投稿门槛**：同一个暴雨测试总体比较所有M0–M4；完整新闻阳性样本和未标记总体；开发期冻结、城市/国家/风暴分组无泄漏；每个气候区足够独立事件；Fig2e有足够高/低HAND和建成水平的实际样本；低样本时拒绝输出或标记不支持。Figure3仍需独立物理积水正例+有实际监测覆盖的无积水反例，才能将新闻响应解释为真正pluvial flood susceptibility。

现有182格试验通常可能没有足够新闻正例来通过以上门槛。遇到拒绝不能人为降低门槛，应扩大开发期冻结的城市和气候带样本，且不因2024–25新闻数量选择样本。

本流程没有连接用户E:/实际数据，也没有提交真实GEE任务或下载NASA/CDS数据。GitHub CI只验证代码与合成数据，不是已经得到发表级Fig2结果。


### 额外国家留出、气候留出和多随机种子的诊断（Supplement）

冻结前瞻Fig2_frozen的主比较是2021–23训练、2024–25新/旧城市测试以及开发期留出城市。国家和气候带留出不能仅靠这三个分组自称完成；使用已有Fig2 GROUPS扩展诊断，训练和测试还须保持无公共气象事件ID。这一诊断随机按整组留出，必须标成开发期或跨期的辅助诊断，而不是取代正式前瞻评价。

    & $PY -m gee_flooding.fig2 --root $ROOT --panel $PANEL --contract "$DER\fig2_weather_provenance.json" --cities $CITYMETA --grid-cities $UCDB --tag fig2_country_climate_group_diagnostic_v1

重点查看输出 fig2_ablation_generalization.csv 和 fig2_invalid_splits.csv。无效的留出（样本太少、阳性不足）必须保留失败原因，不能改为随机行拆分。若国家/气候带元数据不完整，先从官方UCDB补齐，而不是制造 Unknown。纸面M1–M4差值应始终采用同一测试集和相同的最小资料覆盖要求。
