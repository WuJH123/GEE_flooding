你在 E:\GEE_flooding 的 Windows PC 上运行Codex。请按照本包 README_CN.md 持续推进**已实现接口的本地真实质量验收与有界GEE试验**，禁止伪造日志、样本或事件ID。

项目：CEE论文Figure 2，独立于Nature Cities主文。

任务A：只读检查v3/v4/v5现有工程成果，确认v5 `v5_science_equivalence.json` 为 FAIL_COMPACT_ROI，7个v4工程通过文件、578个陆地格；完全不覆盖原账本，核对已有11条GEE operations和GF10 SHA及138万+格的冻结坐标系。读取 `v5_roi_buffer_independent_qc.csv`，逐变量解释8.98%最大差异，特别是武汉 `merit_upa_mean_km2`；不要为了通过而修改阈值。

任务B：部署新的 `CEE_GF10_V6_SCIENCE_COHORT_20261105`，复用v3的完整MERIT 16波段计算图及v4安全计划。安装项目requirements、运行全部pytest与compileall。依次对武汉、孟买、冰岛三个既有v5对照块分别提交20、40、80 km缓冲计算，但固定最终10km核心输出和EPSG6933原点；每次最多提交1项且前项需要GEE SUCCEEDED、TIF下载、完整QC、实际EECU记录才继续。9个任务全部完成再运行halo_compare/halo_approve。如40→80有任意波段超预注册误差限，停止全球MERIT，先定位具体像元的重投影边缘传播/Mask差异，必要时增设160km实验且版本升级。只有真实通过后使用`merit-submit`提交1个未运行的安全区正式任务，并进行本地验收与partial assemble。禁止一口气提交16,860块；14个接缝块继续隔离，所有旧通过块不重复提交。

任务C：优先用本地真实Figure1 `outputs\fig1_publication_r3\labels\grid_day_observations.parquet`，只读打印列名、部分非敏感样例、缺失率、日期精度、空间精度、原始事件ID、UCDB城市映射。禁止臆造字段。按同项目冻结论文大纲和Fig1的高特异性筛选文件追溯每个字段来源，必要时向上游真实GF10映射流程获取。为v6 `config/fig1_verified_column_mapping.json` 生成真实已审核字段映射；不得在没有明确来源的情况下将每行都设为高精度日期/位置。执行`freeze-cases`先仅2021–2023主文开发窗口，生成精确排除原因统计、保留原始报道事件ID与文章来源。确认本地旧650k的20km episodes和对照不能按ID直接硬拼新10km GF10；如需复用，必须用真实几何和时间重新重构。

任务D：运行`calendar-candidates`，对每个有效GF10报道病例在同格/同星期±14..63日选最多8个未标记日期，排除全城市已有报道±7日，确保没有抽样碰撞、无跨季节日期过大变化，并形成匹配方法日志。与冻结GF10 merge并按Date×10x10 tile去重生成M0提取计划。先选5个病例及其候选日期作为试验；检查IMERG permanent有效版本及半小时单位转换、一天43个3h滚动窗、前7/30天336/1440个观测，ERA5-Land前一天土壤/温度/降水单位。成功后明确提交一个真实小范围的 `weather-submit --execute`任务，下载CSV，校验日期、GF10、IMERG完整性、ERA5的空值原因，调用`live-accept`。不把没新闻的日期叫真实无洪水。

任务E：使用已下载的ERA5-EX/原有气候层识别可复用的**逐格日降水P95**基线；ERA5-EX年度R95p总量不能直接代替每日P95阈值。若缺真实P95，在气象预提取成功后只生成探索性配对结果，不生成`FINAL`。若取得可靠的P95和独立风暴ID，执行`weather-match --rain-p95 --publication --storm-map --require-storms`，输出最终可审计 `grid_id × date_utc × pair_id × storm_id × city_id`表；保留匹配失败、零降雨、缺测、重复事件及观察选择偏差。所有对照标签仍称`matched_unreported_exposure`而非无洪水阴性。按独立城市、国家、年份、风暴预注册留出方案，禁止随机打散同场风暴。

任务F：生成合并和完整QC。输出本地路径、文件SHA、数据来源许可证、GF10数目、时间日期范围、样本量、可用/缺测占比、任务总EECU、逐批失败和重试原因、已验收/待处理区别。不得把局部MERIT回填或候选天气计划称全球完成。

当前Codex无须询问任何已提供的路径和项目ID；发现实际字段缺失或没有权限必须输出明确阻塞原因，不能填假数据继续。请从只读预检开始实施上述A–F，并给出每项Windows PowerShell实际执行记录。源代码若需修改，提交到独立本地分支；不强推、不覆盖用户现有本地修改。GitHub远程更新由当前ChatGPT连接器统一处理。
