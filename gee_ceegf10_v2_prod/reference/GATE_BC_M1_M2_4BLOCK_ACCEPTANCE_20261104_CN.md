# Figure 2：M1/M2 指标补验与四块连续区域导出验收（2026-11-04）

## 结论

在独立 Earth Engine 项目 `future-shuttle-513705-g9` 内，四块各 10×10 GF10 的 MERIT Hydro（M1）与 ESA WorldCover（M2）试验已完成，真实 Google Drive 批处理 GeoTIFF 已下载到本地并逐波段验收。M1 每块 16 波段；M2 采用四个 5×5 连续子块导出后无重采样拼接为每块 25 波段、10×10 像元。24 个最终采用的批处理任务全部成功，累计实测 1.97453 EECU 小时。先前孟买 M2 整块 10×10 方案因 `Reprojection output too large (11539x9218 pixels)` 失败，已由分块路径替代；失败记录保留在任务清单中。

这证明四种环境下的候选指标和有界栅格导出路径可运行，不构成全球条带生产许可，也不证明城市内涝机制或模型跨城市迁移能力。

## 区域与数据定义

| 区域 | GF10 左下角 `(grid_x, grid_y)` | GSHHG 矢量陆地面积 km² | 用途 |
| --- | ---: | ---: | --- |
| 武汉 | (1097, 367) | 8633.103 | 城市、湖泊和河流 |
| 孟买 | (697, 233) | 3963.926 | 海岸、建成区与红树林 |
| 冰岛 | (-166, 658) | 9365.258 | 雪冰、苔藓地衣和高纬地形 |
| 尼日尔三角洲 | (57, 52) | 6631.420 | 湿地、红树林和河口 |

GSHHG v2.3.7 Full Resolution 的 L1–L4 多边形在 EPSG:6933 下做陆地减湖泊、湖中岛恢复及裁切。四块精确矢量面积与冻结 GF10 格网陆地面积之和一致。MERIT 是静态水文地形产品；Earth Engine 目录的 1987–2017 为数据集可用时间标记，**不能解释为每年一张图**。其 `hnd`、`elv` 单位为 m，`upa` 为 km²，`wat=1` 为永久水体；`elv` 是水文调整高程。WorldCover v200 表示 **2021 年** 10 m 分类，代码 10–100 的 11 类均保留。[MERIT Hydro 数据目录](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)、[ESA WorldCover 数据目录](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200)。

## Gate B：指标科学补验

M1 新增 HAND ≤2/5/10 m 的有效像元面积比例、HAND p10/p50/p90、源高程坡度均值与 ≤2° 比例、最大上游汇流面积 `ln(1 + upa_max / 1 km²)` 和上游汇流面积 p90。分位数直接从 MERIT 源像元聚合到 GF10；未把 500 m 分位数再求分位数。16 格直接 90 m 对照下，HAND p10/p50/p90 的中位绝对差分别为 0.00040/0.00167/0.00380 m；最大差分别为 0.0144/0.2514/0.9000 m。这是聚合路径间的差，**不是对真实高程的误差**。HAND 阈值比例、坡度与汇流变量的值域、单调性和对数关系通过检查。武汉样格 `1102_372` 的新版正式 GeoTIFF 与原在线单格结果逐值一致；M1 v2 的前 12 波段与此前四块 M1 批处理在共同有效像元上完全一致。

M2 同时保存完整 10 km 方格分类比例和 GSHHG 陆地内分类比例。后者先在 10 m 网格用真实 GSHHG 多边形裁切类别，再分别聚合类别交集和陆地分母，**没有将全格比例直接除以 GF10 陆地比例**。孟买海岸格 `702_238` 的正式 GeoTIFF 给出陆地比例 0.348447，冻结矢量比例 0.348380，建成区占陆地 0.675665；11 类陆地比例之和约为 1。独立直接 10 m 原始类别统计与正式 GeoTIFF 的最大类别比例差为 0.000171。四块中，雪冰 70 与苔藓地衣 100 在冰岛、草本湿地 90 在四块、红树林 95 在孟买和尼日尔三角洲均有非零格。稀有类样本证明导出路径覆盖了这些类别，不代表原始 WorldCover 分类本身无误。

## Gate C：真实 GeoTIFF 路径

导出采用 EPSG:6933 的正式 WKT、`[10000,0,0,0,-10000,0]` 仿射网格、GeoTIFF、Cloud Optimized 选项和 `-9999` NoData。四块 M1 直接导出 10×10；M2 在每块内部用四个相邻 5×5 子块导出，随后按原网格拼接。Google 的导出文档明确支持用 CRS 与仿射变换固定像元对齐。[Earth Engine 图像导出文档](https://developers.google.com/earth-engine/guides/exporting_images)。

| 区域 | M1 有效格/100 | M2 栅格陆地面积 km² | 与冻结矢量相比的最大单格陆地比例差 | 类别比例最大守恒误差 |
| --- | ---: | ---: | ---: | ---: |
| 武汉 | 100 | 8635.931 | 0.001346 | 6.71×10⁻⁸ |
| 孟买 | 48 | 3965.547 | 0.001349 | 7.76×10⁻⁸ |
| 冰岛 | 99 | 9366.193 | 0.002740 | 7.36×10⁻⁸ |
| 尼日尔三角洲 | 76 | 6634.365 | 0.002269 | 8.36×10⁻⁸ |

栅格化海岸线的陆地面积与精确矢量面积有小差异；最大单格差不超过 0.00274（约 0.274 个百分点），四块均无单格差超过 0.01。M1 无值格仍保留为 NoData，不填零。所有正式文件的投影、10 km 像元、范围、波段名、NoData、HAND 阈值单调性、分位数次序、`upa_max ≥ upa_p90`、类别比例和值域均通过本地检查。

## 交付文件与后续边界

- 指标契约：`config/INDICATOR_CONTRACT.csv`。
- 16 格 M1 补验：`reports/m1_science_16_cells.csv`、`reports/m1_percentile_candidate_16.json`。
- 孟买 M2 10 m 独立对照：`reports/m2_direct_reference_mumbai.json`。
- 批处理任务及 EECU：`reports/gate_c_tasks.json`、`reports/gate_c_status.json`。
- 原始批处理 GeoTIFF：`reports/gate_c_drive_tifs/`；四块 M2 10×10 拼接产品：`reports/gate_c_mosaics/`。
- 机器可读像元验收：`reports/gate_c_tif_audit.json`。

当前 `pilot_approved=false`。现有 `static_full` 的旧 WorldCover 条带逻辑只导出完整方格比例，已增加明确拦截，避免误当作本次通过的陆地内比例算法。全球生产需先实现与本次 **5×5 有界分块**等价的 GSHHG 陆地裁切与拼接/回填路径，再单独做首条带成本和数据质量闸门。M1 的大流域 `upa` 信号必须在后续模型中与城市局地暴雨效应区分；本次没有洪涝真值验证。
