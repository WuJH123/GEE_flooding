# Codex 完整执行任务

现在只在本机 `E:\GEE_flooding` 上运行，不要重新下载Groundsource、不修改旧v3/v4/v5/v6账本、不上传原始Groundsource文件到GitHub，不进行无批准的全球GEE批量提交。阅读新v7 `README_CN.md` 和GitHub Figure1 `gee_flooding/fig1_tiers.py,fig1_v3_city.py,fig1_publication.py`，保证科学定义一致。

1. 确认已冻结GF10的1395471格SHA、UCDB官方GPKG和`raw_uuid_tiers`原文件。执行`00_check.ps1`，失败立即停止。脚本包含数值 `primary_overlap >=0.8` 的规则，绝不能改为bool。
2. 执行 `01_build_provenance.ps1`。完整读取原始`data/raw/groundsource_2026.parquet`2,646,302行，逐批精确UUID连接高Tier，依次完成原始single-day日期、GF10几何交叠、官方UCDB城市多边形检验，生成原UUID→格日→城市审计表和被排除原因。无“最近城市”模糊赋值。不把源多边形当积水范围。
3. 研究质量核验：QC原始UUID唯一，所选UUID能严格回溯到Groundsource源文件和原Figure1 A层；地理真实交叠/单位、投影、是否多城市竞争、城市覆盖率按年份分层；发布各过滤原因计数和入选比例。任何geocode质量标签不能当独立真值。
4. 执行 `02_preextract_plan.ps1 -Candidates 4`，生成唯一GF10×源UTC日历代理的病例/未标记候选日期，不能将新闻缺报当无洪水。按日期和10x10区域每次<=40格组织真实气象请求。若任务数过大，先生成小批次/预算预报，不提交全部。
5. 由人类审阅对分层抽样400条（可以先50条技术检查）逐条回找原始新闻链接/文字核对日期和地名，审计记录两名不同审阅者、原文URL和关键摘录。人工核实的病例另存；如果真实链接无法获得，保留PROVISIONAL，不得填写假URL或假勾选。
6. 执行 `03_one_gee_weather_pilot.ps1`（dry-run）。确认唯一真实date×grid组，投影分辨率、IMERG permanent和ERA5-Land前一日窗口。再明确`-Execute`**只提交一个**真实GEE表任务，保留operation ID并核销EECU。成功后下载CSV至新`downloads`目录，执行`weather-audit`、`weather-status`与`weather-assemble`（PARTIAL）。任何异常停止追加。
7. MERIT继续使用旧v6已验收的80km halo正式模块，不要重新执行9个收敛任务和已有375格。运行新CLI `merit-next`选择未提交安全块，安排5–10个跨纬度及城市/海岸样本，经在线EECU及CRC/SHA、16波段/仿射、数值QC后扩大。14接缝块/450格永远保留隔离直到另行科学验证。
8. 独立气象风暴ID和实际当地日P95基线均有数据且经验证后才可开启`weather-match --publication --verified-only`，并核对M0–M5后续跨城市/跨年份/独立风暴泛化与独立淹没物理验证。不要把PU的未标记样本叫真实干日负样本。

汇报必须包括实际运行命令、原始路径/文件sha、筛选原UUID/病例与城市数、排除率、审阅通过数、GEE task ID/状态、真实EECU、气象数据缺测与样本时区灵敏度缺口。未运行不得声称完成。任何本地修补先跑测试并归档补丁，不覆盖既有GitHub正式SCI数据。
