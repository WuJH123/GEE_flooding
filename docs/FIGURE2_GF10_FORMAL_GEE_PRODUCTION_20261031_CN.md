# Figure 2 — GF10 正式GEE生产与数据验收（2026-10-31）

本文件基于本轮 Codex 的实际报告，而非示例数据。当前冻结试验范围：40个UCDB城市、182个EPSG:6933的10 km GF10格网。2020 GHSL BUILT-S 已有182/182格，最小有效像元覆盖率99.7567%；已知建成面积与建成比例同属一个JRC源，尚未通过独立原产品总量检验。12项核心/暴露指标只有城市比例、2020建成比例、建成面积完整；另外9项缺失。此前核心与扩展计划各40条任务均只经过dry-run，没有正式提交。**不要重复提交这两份旧计划。**

## 1. 数据与科研契约

P0 GEE必须获得：MERIT Hydro 的 HAND、坡度、上游汇流面积、地面高程、永久水体；ESA WorldCover v200 的植被与树林、草地、农田、湿地、水体、裸地比例；GHSL 2000历史建成比例、2000–2020增长、2020建成邻域密度和局部异质性；GHSL 2020人口总数、非住宅建成面积。已有2020年总建成比例、总建成面积和城市比例由本地数据保留，不重新提取。

核心指标不是实际内涝真值。自然植被仅为潜在自然适应条件代理变量，不能宣称为实际管网能力。2000、2020、2021数据的年代必须在模型中明确，不得把2021地表误说成2000历史特征。

## 2. 正确同步GitHub代码（数据目录没有.git）

使用PowerShell，保留E盘数据不重建、不删除。

    $ROOT = 'E:\GEE_flooding'
    $SRC  = 'E:\GEE_flooding_code'
    if (-not (Test-Path "$SRC\.git")) {
        git clone https://github.com/WuJH123/GEE_flooding.git $SRC
    } else {
        git -C $SRC pull --ff-only origin main
    }
    Set-Location $SRC
    git log -1 --oneline
    $PY = "$ROOT\.venv\Scripts\python.exe"
    if (-not (Test-Path $PY)) { py -3.11 -m venv "$ROOT\.venv" }
    & $PY -m pip install -e "$SRC"
    & $PY -m pytest -q

如果本机缺少exactextract而无法安装，两个跨后端对照测试需要明确跳过；真实数据仍可调用已审核的Shapely后端。GitHub CI已安装该依赖并运行完整测试。

## 3. 必须重新生成新版extended计划，替代旧core与extended两套

    $GRID="$ROOT\data\reference\fig2_subset_local_v1\fig2_GF10_selected_grid.parquet"
    $LOCAL="$ROOT\data\derived\fig2_local_ghsl182_v2\fig2_local_GF10_indicators.parquet"
    $MERGED="$ROOT\data\derived\fig2_integrated_ghsl182_v2\fig2_GF10_resilience_indicators.parquet"
    foreach ($file in @($GRID,$LOCAL,$MERGED)) {
        if (-not (Test-Path $file)) { throw "Missing validated local file: $file" }
    }
    & $PY -m gee_flooding.fig2_backfill_plan --root $ROOT --grid $GRID --indicators $MERGED --scope extended --max-cells 20 --tag fig2_gee_extended182_v3
    $PLAN="$ROOT\data\reference\fig2_gee_extended182_v3"
    Import-Csv "$PLAN\fig2_gee_backfill_tasks.csv" |
      Group-Object source_family | Select-Object Name,Count
    Get-Content "$PLAN\fig2_gee_backfill_plan_qc.json"

扩展计划预计仍为4类来源、每类10条左右、共40条；与此前不同，新增独立保存2000年建成基准值。结果会按实际缺测和指标签名决定任务数量。绝不同时提交旧核心、旧扩展和新扩展三套计划。

## 4. 先四类dry run，再只提交一个真实MERIT任务

    $PROJECT='REPLACE_WITH_REAL_EARTH_ENGINE_CLOUD_PROJECT'
    $EE="$ROOT\.venv\Scripts\earthengine.exe"
    & $EE authenticate
    & $EE set_project $PROJECT

    foreach ($family in @('merit','landcover','builtform','population')) {
        & $PY -m gee_flooding.fig2_gee_submit --root $ROOT --plan $PLAN --family $family --max-tasks 1
    }

上面的任务检查不提交任何远程任务。确定几何与波段无误后，只提交一条：

    & $PY -m gee_flooding.fig2_gee_submit --root $ROOT --plan $PLAN --family merit --max-tasks 1 --project $PROJECT --submit --confirm SUBMIT

程序每次最多接受4个提交，成功返回任务ID后会逐条追加到计划目录的 fig2_gee_submission_ledger.jsonl，避免重复提交。ledger中的SUBMITTED不等于COMPLETED。若进程恰好在服务端提交后、本地日志写入前中断，务必到GEE Tasks页面核对再重试。

查看 https://code.earthengine.google.com/tasks 。只有任务 COMPLETED 且下载到CSV才进入下一阶段。第一条真实任务验证后，每类先各提交一条，以免有一种源的 band 名称或采样计算失败而浪费配额。全部四类试验正常后，每次最多4个：

    & $PY -m gee_flooding.fig2_gee_submit --root $ROOT --plan $PLAN --family merit --max-tasks 4 --project $PROJECT --submit --confirm SUBMIT

手工依次改为 landcover、builtform、population；逐批检查GEE Tasks配额与状态。无需等待本对话在后台操作，全部由本地命令显式执行。

## 5. 每次下载后立即验收；拒绝错位格网、缺测、错误单位

GEE导出表将出现在Google Drive 的 GEE_flooding_Figure2 文件夹。下载完成的 f2_static_* CSV至E:\GEE_flooding\data\gee_exports\fig2_static；f2_exposure_* CSV至同级fig2_exposure目录。保留GEE输出原始文件名前缀及_bHASH后缀。

    $STATIC="$ROOT\data\gee_exports\fig2_static"
    $EXPOSURE="$ROOT\data\gee_exports\fig2_exposure"
    New-Item -ItemType Directory -Force $STATIC,$EXPOSURE | Out-Null
    & $PY -m gee_flooding.fig2_gee_qc --root $ROOT --plan $PLAN --gee-static $STATIC --gee-exposure $EXPOSURE --local $LOCAL --tag fig2_gee_smoke_v1

结果：reports\fig2_gee_smoke_v1\fig2_gee_file_audit.csv 和 fig2_gee_postdownload_qc.json。某个任务尚未下载时显示 PARTIAL；任何已存在文件如果重复/遗漏格网ID、缺失要求的波段、有NaN、负人口、超范围比例或与冻结城市比例不一致则拒绝通过。每次重新检查使用新的--tag。

全部计划表对应的GEE任务完成且CSV已下载后：

    & $PY -m gee_flooding.fig2_gee_qc --root $ROOT --plan $PLAN --gee-static $STATIC --gee-exposure $EXPOSURE --local $LOCAL --require-complete --tag fig2_gee_complete_v1

扩展计划还可以比较GEE 2000年建成比例 + 增长 是否近似等于本地GHSL 2020建成比例，并核查非住宅面积是否超过总建成面积；如果源投影/数据版本差异过大，禁止把结果标记为正式通过。

## 6. 一条必要的面积交叉检验任务：额外20格，不是另一套主数据

GEE人口和建成面从100m原始像元数值转换到经纬度坐标求和，成功导出不自动证明原始总量守恒。必须在冻结182格中选定同样的20格，用GEE独立计算2020总建成面积，对照本地原生JRC结果：

    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode exposure --bands built_area_km2_2020 --start-row 0 --count 20
    & $PY -m gee_flooding.fig2_gee --grid $GRID --mode exposure --bands built_area_km2_2020 --start-row 0 --count 20 --project $PROJECT --submit

下载这一个f2_exposure_* CSV并再次使用新版本标签运行fig2_gee_qc。若同格差异同时超过0.5 km²与5%的相对误差，验收失败。这里比较的是同一JRC产品的两个计算路径，仍不是独立遥感物理观测。

## 7. 全部通过后生成静态GF10宽表

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local $LOCAL --gee-static $STATIC --gee-exposure $EXPOSURE --tag fig2_integrated_extended182_v4
    $FINAL="$ROOT\data\derived\fig2_integrated_extended182_v4"
    Import-Csv "$FINAL\fig2_core_indicator_gate.csv" | Format-Table -AutoSize
    Import-Csv "$FINAL\fig2_source_conflicts.csv" | Format-Table -AutoSize
    Get-Content "$FINAL\fig2_GF10_indicator_merge_qc.json"

182/182数值齐全、零未解决冲突才说明182格试验范围内的核心静态指标完整。它不等于完整的全球GF10覆盖、没有证明城市排水工程适应能力、也不等于Figure2b-e的正式发表验证。

## 8. 哪些本地下载，哪些使用GEE？

- 直接本地保留：2020 JRC BUILT-S、冻结GF10、UCDB城市映射、Groundsource、历史已有的IMERG/ERA5/MERIT相关CSV（但必须核对时间/格网/产品版本后使用）。
- 必须本轮提交GEE：MERIT Hydro、ESA WorldCover v200、GHSL BUILT-S 2000历史值/邻域、GHSL GHS-POP 2020和非住宅建成面。这些已在上文extended计划中，无须下载全球高分辨率栅格。
- 本地处理的P1指标：已存在的GISD30约99份EPSG:4326切片；需先将动态编码0透水、1–8不透水分期转为二元掩码，再做等面积比例。不能直接平均原始类别，也不能把EPSG:4326扔进仅接受米制等面积投影的Shapely后端。
- 只有区域切片真实缺失才下载GISD30官方Zenodo压缩包，全部约1.3 GB；https://zenodo.org/records/5220816 ，按经纬覆盖查缺包并核验MD5，不重复下载已拥有的ZIP/RAR。
- 道路、夜间灯光、可达性、GDP、建筑体积和互联网普及率是附加暴露与观测选择机制指标；先复用本地E:/D:已经下载的原始来源，再考虑小于10GB且许可合格的区域下载。

## 9. 后续动态雨量与物理独立验证单独推进

IMERG V07半小时降水是mm/h，半小时累计须乘0.5；24h需要48个时间步，前7天336个，3h滑动窗6个。ERA5-Land用目标暴雨前的湿度和气温，禁止事后泄漏。现在先运行7天、20格GEE小批量天气测试，不能直接声称完成2021–2025全局暴雨面板：

    & $PY -m gee_flooding.fig2_gee_weekly --grid $GRID --start 2024-07-01 --days 7 --start-row 0 --count 20

正式发表还需要按城市、国家、年份、独立风暴的训练外泛化和真实城市内涝物理正例及有效观测未积水反例。CN-Floods、GFD、伦敦风险图、新闻与灾害目录不能未经观测/类型审查就混用为等价真值。若这项不满足，应称作新闻洪涝报道响应而非真实内涝概率。

官方依据：
GHSL BUILT-S https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S
GHS-POP https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_POP
MERIT https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
WorldCover https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
IMERG https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
GEE weighted reduceRegions https://developers.google.com/earth-engine/guides/reducers_reduce_region
GISD30 https://essd.copernicus.org/articles/14/1831/2022/


### GISD30本地99份切片：先做真实覆盖盘点，再决定是否下载1.3GB官方压缩包

对上轮已生成的read-only本地候选CSV运行，**不会读取整个30m栅格、不会下载数据、更不会冒充真实不透水比例**：

    $GISD_INDEX="$ROOT\reports\fig2_local_candidates_20261031\fig2_local_candidates.csv"
    if (-not (Test-Path $GISD_INDEX)) { throw "Locate existing fig2_local_candidates.csv from Codex" }
    & $PY -m gee_flooding.fig2_gisd30_coverage --root $ROOT --grid $GRID --candidates $GISD_INDEX --tag fig2_gisd30_tile_audit_v1
    Import-Csv "$ROOT\reports\fig2_gisd30_tile_audit_v1\fig2_gisd30_frozen_grid_tile_coverage.csv" |
      Where-Object requires_GISD30_source_tile -eq "True" |
      Select-Object grid_id,requires_GISD30_source_tile

这些是缺乏当前已解压GeoTIFF空间重叠的候选格网，还不能据此判断整个区域没有压缩包。先检查本地已有RAR是否包含对应5度切片，再通过 https://zenodo.org/records/5220816 下载确实缺失的原包。下载前核对文件MD5及位置，严禁删除旧版本。随后需要用按原生类别重编码和真正面积保守的算法产生0–1不透水比例。当前这一步只是P1的数据源空间覆盖与下载判定，并不替代GEE P0核心指标导出。
