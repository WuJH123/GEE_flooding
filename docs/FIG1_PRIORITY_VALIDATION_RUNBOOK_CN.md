# Figure 1 低成本优先验收与验证实施手册（独立 GEE_flooding）

研究目标：Communications Earth & Environment。不是 Nature Cities Global_flooding，也不在此处理 Figure2 训练。网页 GPT 负责代码和 GitHub 合并；本地 Codex 负责 E 盘真实运行。所有新输出在 E:\GEE_flooding，外部原始数据只读，不重复下载。

## 一、现有结果支持程度

已有 Groundsource 原始 2,646,302 条、映射 2,202,651、HIGH 1,788,759；GF10 城市网格 166,414；高定位唯一网格-日期 1,056,639；v3 GFID 通过条件记录 79,277（DesInventar 70,777）；开发期合格官方 UCDB 城市 4,765。

支持 Figure2 的新闻洪涝响应代理、城市/气候代表性及数据稀疏区。不能把原始新闻、同网格日期和连续报道簇当作独立洪水/独立降雨事件。不能把新闻响应预测当真实积水概率。不得先验断言贫困地区漏报更严重。

优先级：1 P0原始输入审计 -> 2 已有五面板和人口/地区分层 -> 3 人工定位复核 -> 4 IMERG/ERA5 气象试验 -> 5 卫星/现场独立物理验证 -> 6 正式出版图。

## 二、同步 GitHub 代码：不要覆盖用户的数据

如果 E:\GEE_flooding 没有 .git，让 Codex 从 GitHub main 通过连接或下载代码 ZIP，备份本地同名代码后只复制源代码、scripts、tests、docs。不要使用 git clean/reset 或重新克隆覆盖数据；保留 data、outputs、reports、.venv 与旧 Figure 1。

PowerShell:
    Set-Location E:\GEE_flooding
    $ROOT = "E:\GEE_flooding"
    $PY = "$ROOT\.venv\Scripts\python.exe"
    & $PY -m pip install -e ".[test]"
    & $PY -m pytest -q

自动选择已有 Groundsource，不重新下载:
    $RA="$ROOT\data\raw\groundsource_2026.parquet"
    $RB="E:\数据集\Groundsource_全球城市内涝点位\groundsource_2026.parquet"
    $RAW=if(Test-Path -LiteralPath $RA){$RA}elseif(Test-Path -LiteralPath $RB){$RB}else{throw "原始 Groundsource 文件找不到"}
    $GRID="$ROOT\data\reference\grid10_urban_2020.parquet"
    $MAPPED="$ROOT\outputs\labels\groundsource_gf10_primary.parquet"
    $CITY="$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    $QC="$ROOT\outputs\fig1_v3_full_r2\fig1_v3_qc.json"
    $CROSS="$ROOT\outputs\fig1_v2\fig1_grid_dominant_ucdb.parquet"

## 三、最容易：完整性核查与五面板

第一条只读取元数据和小型来源 QC，不重跑264万几何、不触发 EE：
    & $PY -m gee_flooding --root $ROOT fig1-preflight --raw "$RAW" --mapped "$MAPPED" --grid "$GRID" --city-file "$CITY" --v3-qc "$QC" --crosswalk "$CROSS" --tag fig1_preflight_r1

查看:
    Get-Content "$ROOT\outputs\fig1_preflight_r1\preflight\fig1_input_preflight.json" -Raw

要求 raw=2646302、mapped=2202651、GF10=166414、HIGH=1788759、GFID full ledger=136642，UCDB 分配加未分配等于 HIGH。若失败，先报错定位版本差异，不要假设新旧文件内容相同。

第二条运行主图完整处理（约束只读已有 SMOD、Groundsource、UCDB、GFID）：
    .\scripts\run_fig1_publication.ps1 -Root $ROOT -Raw "$RAW" -Tag fig1_publication_r1 -V2Tag fig1_v2 -V3Tag fig1_v3_full_r2

要检查的产物：
    $OUT="$ROOT\outputs\fig1_publication_r1"
    Get-Content "$OUT\grid\spatial_frame_qc.json" -Raw
    Get-Content "$OUT\labels\label_tier_qc.json" -Raw
    Get-Content "$OUT\paper\figure1_publication_gate.json" -Raw

主图是 Figure1a–e 五面板，原始 UUID / 唯一 grid-day / news episode 分开。ABC 基于原始 geocoder 面积、主网格交叠、候选网格数和新闻起止日期，是待校准质量代理，不是实测定位精度。

### 官方城市人口分层

已有 UCDB GPKG 路径：
    E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg

先查找真实列名:
    & $PY -m gee_flooding --root $ROOT fig1-ucdb-population --ucdb "E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg" --tag fig1_pop_schema_r1

查看 outputs\fig1_pop_schema_r1\ucdb_population\ucdb_population_schema.json，确认人口**总量**而不是人口密度/2025 年人口字段。根据实际图层和字段填写 --layer 与 --population-field，用新 tag fig1_pop_r2 导出 CSV，再用新 tag fig1_publication_r2 并添加 -CityPopulation 运行主图。387 座洲别 Unknown 保留并列出排除原因，不能猜国别。

## 四、分层人工复核（决定 ABC 质量是否能在正文声称“可靠”）

已有队列约600条:
    E:\GEE_flooding\outputs\fig1_v3_full_r2\independent_groundsource_annotation_queue.csv

让人类研究人员审查原始报道或可追溯独立官方证据，保存审稿结果：
    E:\GEE_flooding\data\validation\groundsource_reviewers.csv

CSV 每行 = 一个 UUID × 一个审查人，至少列 event_id, reviewer_id, evidence_source_uri, independent_of_groundsource, location_verified, date_verified, flood_occurrence_verified, pluvial_mechanism_verified。答 YES/NO/UNKNOWN；部分记录双审查人。没有新闻原文或位置无法核对就是 UNKNOWN，不是自动通过或否定。双人意见冲突请人工仲裁。

检查：
    & $PY -m gee_flooding --root $ROOT fig1-review-audit --queue "$ROOT\outputs\fig1_v3_full_r2\independent_groundsource_annotation_queue.csv" --reviews "$ROOT\data\validation\groundsource_reviewers.csv" --tag fig1_review_r1

读 outputs\fig1_review_r1\review\human_label_review_qc.json；如果未审完或存在冲突，结果明确写 REVIEW_INCOMPLETE_NO_ACCURACY_CLAIM。完成后需报告各 A/B/C 等级与国家/年份分层准确率及置信区间；当前脚本只是审查完成情况和初步比例，不能证明全部全球报道无偏。

## 五、Google Earth Engine：只做小试验，不向 EE 提交几百万条新闻

先做 IMERG V07 + ERA5-Land 观测一致性。2018 年以前的事件可同时考虑 GFD；2021–2025 年用 CEMS GFM/现场资料为主。GEE 用户应使用其实际已授权 Cloud project ID，不能无条件使用旧项目 ID。

生成小清单（从 A/B/C 与不同年代抽24条有报道日期，并尝试为每条配一个同一网格、相近季节的未报道参考日；通常得到至多48条）：
    & $PY -m gee_flooding --root $ROOT fig1-prepare-weather-pilot --tiers "$ROOT\outputs\fig1_publication_r1\labels\raw_uuid_tiers.parquet" --grid "$GRID" --n 24 --seed 42 --paired-controls --tag fig1_pilot_r1

输出 outputs\fig1_pilot_r1\gee\fig1_imerg_pilot_manifest.csv。包含 sample_role、pair_id：REPORTED_NEWS_DAY 与 UNLABELED_SAME_GRID_SEASON，后者**不是无洪涝负例**。脚本默认只取前12行（按 pair_id 排序，约6对）；先做 dry-run:
    $PROJECT="填入本人已授权的 EE Cloud project ID"
    $MANIFEST="$ROOT\outputs\fig1_pilot_r1\gee\fig1_imerg_pilot_manifest.csv"
    & $PY -m gee_flooding --root $ROOT fig1-gee-pilot --project "$PROJECT" --manifest "$MANIFEST" --max-rows 12

只有 dry-run 输出合法后才允许授权并提交：
    & $PY -m pip install earthengine-api
    & $PY -c "import ee; ee.Authenticate(); ee.Initialize(project='$PROJECT'); print('EE OK')"
    & $PY -m gee_flooding --root $ROOT fig1-gee-pilot --project "$PROJECT" --manifest "$MANIFEST" --max-rows 12 --description FIG1_IMERG_V07_PILOT_R1 --submit

GEE Tasks 必须 COMPLETED，Google Drive 中找到 GEE_flooding_fig1_validation 文件夹导出 CSV，保存到 E:\GEE_flooding\data\validation\gee_csv。

校核字段：p24_mm、p7ante_mm、n_imerg_24h、n_imerg_prior7d、soil_moisture_ante1d_m3m3、n_era5_ante1d。IMERG 提供 30min 降雨率 mm/h，累计降雨是总和×0.5h；UTC 日通常期待 48、前七日 336 幅，ERA5-Land 前一日24幅。有效影像不足必须标缺测，不可填0。降雨大不等于发生了实际积水。

**本试验不需要上传本地 Groundsource、GHSL、SMOD、GF10 全库到 EE；最多向 Earth Engine 代码嵌入12条 10km 格网-日期。** 若后续生产要做大规模样本，应将分片的 GF10 grid/date Table Asset 上传到 EE，严格分年/月批次和配额控制，这属于 Figure2 全量气象流程，不在本对话提交。

### GFD 卫星水体证据，可选且要真实 ID

GFD 仅覆盖 2000–2018 大型洪水，913 个 DFO 选样事件。先查 EE 中真实 GFD event id，和本地 GF10 cell ID；不可随意猜数。进行 dry-run:
    $GFD_ID=1
    $GRID_ID="真实 GF10 grid_id"
    & $PY -m gee_flooding --root $ROOT fig1-gfd-probe --project "$PROJECT" --grid "$GRID" --grid-id "$GRID_ID" --gfd-event-id $GFD_ID

将 GFD_ID=1 替换为真实 event id 后，再加 --submit。输出仅包含该格网临时洪水水体面积、有效可观测面积、晴空面积；并强制保留 DFO 目录依赖与 pluvial机制未确认标签。无晴空观测或无洪水检出不等于城市无积水。此 GFD 试验不适合代替 2021–2025 Sentinel-1 / CEMS 的独立观测。

## 六、现有独立洪水资料优先检查，不重下

优先核查 E:\数据集 下的 CN-Floods（2006–2024，中国事件级遥感30m）、河南2021内涝栅格、伦敦地表水文件及中国县城记录；检查 E:\Global_flooding\grid10\gfd_physical_v3，READY任务不是成功导出。必须审查各文件的来源论文、原始变量、卫星时间、有效观察掩膜、DEM/淹没定义与 pluvial/riverine/compound 类型。伦敦风险模拟图不能作为真实洪涝正例。

官方按事件下载（只有本地不足时）：
- CEMS https://emergency.copernicus.eu/data/ (按具体 flood activation 下载 GPKG/GeoJSON/矢量或栅格及产品日期、传感器元数据；不需要申请新 activation)
- Copernicus GFM https://global-flood.emergency.copernicus.eu/ (按实际日期检索 Sentinel-1 洪水影像，连同 exclusion/advisory/observability mask)
- GFD EE https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1 (已经在 EE 云端，不重新下载913事件)

独立实测正例必须具有事件来源 ID、传感器和覆盖、淹没证据、可核实时间地点、审查人、是否 pluvial。空白/未检测不要写成无洪涝。合格正例按照已有 fig1_v3_physical.py 模板进入 independent_physical_points.csv，之后用 run_fig1_publication.ps1 新 tag 的 -PhysicalReviewed 重新生成 Fig1d。

## 七、Figure1 发布门槛

- UUID/格网/日期守恒：代码可自动检查
- A/B/C 人工来源复核、双人审查分歧与分层置信区间：尚需真人
- 实测物理洪水支持和来源依赖识别：尚需真人审查与卫星产品
- 原始事件数、候选新闻 episode、独立风暴数绝不混淆
- 地区有效报道覆盖不等于真实发灾率/低收入漏报量
- Figure1 通过工程测试可以让 Figure2 继续，但不自动升级为正式发表结果。
