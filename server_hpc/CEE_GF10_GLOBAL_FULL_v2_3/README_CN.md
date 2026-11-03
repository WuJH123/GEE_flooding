# CEE GF10 — 全部35个本地下载文件的自动全球指标生产包 v2.1（GISD30/PowerShell 故障修复）

2026-11-03 / `GEE_flooding` 论文（目标 **Communications Earth & Environment**），**不属于 Nature Cities 主文**。

## 紧急修复与续跑（v2.1，2026-11-03）

**针对已经发生的错误**：终端只展示 `[stage] gisd` 后 `python.exe : Traceback (most recent call last)`，缺少 traceback 最后一行，**目前不能从这段信息推断是缺少7-Zip、RAR损坏、磁盘满还是Python自身错误**。此前的Windows PowerShell 5.1组合 `$ErrorActionPreference='Stop'` + `python ... 2>&1 | Tee-Object` 可能在首行stderr处终止运行。v2.1使用 `scripts/run_with_log.py` 将Python子进程的stdout和stderr合并成stdout，同时保存完整日志，故障时打印最后75行及结构化JSON。依据：[微软PowerShell官方文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_preference_variables)；[官方7-Zip下载](https://www.7-zip.org/download.html)。

**完全独立的服务器代码目录**：`E:\WJH_CEE\CEE_GF10_GLOBAL_FULL_v2_1`；原v2目录保留不动。原有的 GHSL、GMTED、WorldClim 已完成数据继续使用 `E:\WJH_CEE\data\derived\...`，**不会重新运行已验收的715分区**。原始下载的35文件、冻结GF10和GEE账户没有任何变化。

### 1）在有网络的终端下载ZIP，拷贝到远程E盘；服务器无需GitHub

```powershell
$ROOT = 'E:\WJH_CEE'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GLOBAL_FULL_v2_1.zip" -DestinationPath $ROOT
$PKG = "$ROOT\CEE_GF10_GLOBAL_FULL_v2_1"
$PY = "$ROOT\.venv\Scripts\python.exe"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\00_prepare_full.ps1 -Root $ROOT -SkipPip
```

预检应显示 `PACKAGE_SHA256_VERIFIED`、服务器安装依赖成功、**34项Python测试**全部通过（之前v2的28项，加上v2.1的6项），冻结1395471 GF10/715 shards/35下载文件通过。若服务器环境出现失败，修复失败原因而非跳过。

### 2）只读诊断 + 可选RAR压缩完整性测试

```powershell
.\scripts\04_diagnose_gisd.ps1 -Root $ROOT
Get-Content "$ROOT\reports\cee_full_v2\diagnostic_v21.json" -Raw
```

该命令读取v2旧日志末尾、`failed_stage.json`、12个GISD30 RAR、磁盘剩余空间和7-Zip位置；不解压、不做全球统计。若需真正读取/校验12个RAR的压缩数据（会花费较多磁盘读取时间），执行：

```powershell
.\scripts\04_diagnose_gisd.ps1 -Root $ROOT -TestAllRar
```

如果诊断显示 `NEEDS_7ZIP`，在另一台能上网的电脑从 https://www.7-zip.org/download.html 获取官方Windows x64安装包，拷贝到远程安装到默认的 `C:\Program Files\7-Zip`，然后重跑诊断。**不要把 `7zr.exe` 当作完整RAR解码器**。

### 3）只恢复12个GISD30 RAR 的本地暂存（先定位具体问题）

```powershell
.\scripts\05_stage_gisd_only.ps1 -Root $ROOT
```

它只处理 GISD30 压缩归档，不运行全域指标计算；如果失败会把**真实异常最后75行**输出到屏幕，完整日志保存在 `reports\cee_full_v2\gisd_rar_staging_v21_*.log`，并生成 `stages\staged_gisd_failed.json`。它会复用以前通过验证的RAR暂存。对于上次中断、尚无QC的RAR，先用7-Zip校验整包，然后只在一个新的临时目录解压；对以前已存在的暂存文件比对SHA256，**不覆盖冲突文件**。原始ZIP/RAR、GF10及已完成的Parquet永不修改。

### 4）全球自动生产（与v2相同的来源/输出路径，断点续跑）

```powershell
.\scripts\01_run_all_full.ps1 -Root $ROOT -RasterJobs 4 -RasterWorkers 16 -VectorJobs 2 -VectorWorkers 16
```

如果你只想验证全套归档（包括WorldClim、ERA5EX、GISD、行政/城市/流域），暂不跑715分区计算：

```powershell
.\scripts\01_run_all_full.ps1 -Root $ROOT -StageOnly
```

成功产物仍在 **`E:\WJH_CEE\data\derived\cee_all_global_v2`**，故不改变旧结果。监控日志仍在 `reports\cee_full_v2\resource_monitor.csv`；新的完整stdout/stderr日志名为 `reports\cee_full_v2\full_run_v21_*.log`。

### 5）论文级验收

```powershell
.\scripts\02_verify_all_full.ps1 -Root $ROOT
.\scripts\03_status_and_cpu.ps1 -Root $ROOT
```

**验证合格意味着结构完整，不表示 `publication_ready=true`。** ERA5-EX 仍是0.1°年度指数；GMTED高程像元元数据的 Maximum/人工认定 Mean 冲突尚未消失；WorldClim是1970–2000长期气候常态；沿海GF10真实陆地几何交叠、GISD30源缺瓦片、道路/河网原始覆盖及论文动态气象数据仍需独立QC。请保留这些警告，不要强制标为精确全球实测。

---

## 0. 为什么要升级

此前 v1.2 的 `--max-cells 5000` 是人为试算，不能用于道路和流域的全球正式统计。CPU只有16%也不能说明96核机器不够快：AMD EPYC 9654 是96物理核/192逻辑线程，单一12 worker加上少量GDAL线程不会占满。本次补丁还修复 Windows PowerShell 5.1 只显示 Traceback 第一行的故障、7-Zip 来源诊断和中断后安全恢复。新包采用**4个独立来源×每来源16个CPU进程=64并行进程**作为全球连续栅格的初始配置，同时用磁盘吞吐、CPU和内存峰值判断是否调到96。对于原生30m分类/GDB矢量/NetCDF，为防止内存I/O放大改为8/16/2 worker等更合适的配置，**不是所有数据都用64进程**。

服务器日志当前真实状态：预检20项测试通过；35个下载文件与715个GF10原始分区核查通过；GMTED五个来源各715/715全域完成，约1,395,370有效格；WorldClim已解压八个zip，BIO1 pilot通过，随后的 `worldclim-bio -Full` 命令是否已结束**不能仅凭截图推断**。已有5类GHSL全球结果在 `data/derived/hpc_exact_ghsl_*_v2` 可复用。

## 1. 交付物与脚本

把 `CEE_GF10_GLOBAL_FULL_v2_1.zip` 复制到远程服务器 `E:\WJH_CEE`。新包内 **`ceeall/`** 是兼容原v1.2的原生栅格处理引擎，**`ceeprod/`** 是新的一键全域数据生产引擎：

- `ceeprod/discover.py`：**自动识别本地各GDB/SHP/GPKG真实图层和稳定ID字段**；来源歧义时保存错误而非胡乱选字段，不再需要手填 `--source` / `--layer` / `--fields`。
- `ceeprod/vector_full.py`：**完整715分区**；GRIP4道路/ RiverATLAS河网精确与GF10相交并用WGS84椭球长度统计；geoBoundaries、UCDB、BasinATLAS按**完整10km方格等面积交叠**建立主归属与所有相交关系crosswalk，拒绝5000格试算冒充全球成果。
- `ceeprod/gridcache.py`：**715个**分区的GF10多边形投影缓存；WorldClim的103个栅格复用同一套EPSG4326边界，减少重复投影。
- `ceeprod/era_wide.py`：ERA5-EX **全部34项年度指数、所有源文件共同拥有的年份（目标1950–2025）**，逐年一张GF10×year宽表，省去每指标每年的碎小文件。原生0.1°中心点代理，不能冒充10km原生数据。
- `ceeprod/gisd_history.py`：GISD30原生30m分类从0–8，计算1985、1990、1995、2000、2005、2010、2015、2020八个时点的累计不透水覆盖，不直接平均类别整数；必须审计官方961幅和本地实际953幅覆盖差异。
- `ceeprod/source_attributes.py`：保存UCDB、BasinATLAS、ADM0/ADM1**全部原始字段**为独立实体属性表（保留来源ID），不把城市/流域平均值假装成GF10原生观测。
- `ceeprod/observations_full.py`：Groundsource原始Parquet逐批读取，保留所有原始报告的时间、UUID、代表性GF10地理定位和不确定性，不把新闻定位当洪水足迹或未报道=未淹没。
- `ceeprod/assemble_full.py`：从原有5 GHSL、5 GMTED、103 WorldClim、1 GRIP道路密度、8期GISD30和6类矢量结果建立**每格一行的全局静态分区宽表**，ERA5-EX的年度数据、Groundsource事件数据分别保存，不混时序。
- `ceeprod/quality.py` 与 `dictionary.py`：715分区与1,395,471唯一ID结构审计；真实输出字段字典；来源范围、单位及发表门槛的显式标记。
- `ceeprod/runner.py`：全自动来源发现→原始ZIP/RAR安全解压→缓存→多来源并行→网络→分片/年度输出→QC；同一输入/配置重启只复用已通过QC的输出，发生错误保存`failed_stage.json`。

**包内不会下载数据，也不会调用GEE/上传任何私有文件。** 只使用 `E:\WJH_CEE\gf10_global_nonantarctic_land.parquet`、`E:\WJH_CEE\CEE数据` 的35个下载文件、已有 GHSL 和 Groundsource。

## 2. 一次性准备（不需要手填任何图层/字段）

```powershell
$ROOT='E:\WJH_CEE'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GLOBAL_FULL_v2_1.zip" -DestinationPath $ROOT
$PKG="$ROOT\CEE_GF10_GLOBAL_FULL_v2_1"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\00_prepare_full.ps1 -Root $ROOT
```

`00_prepare_full.ps1` 在已存在的 `E:\WJH_CEE\.venv` 内安装全部依赖（TUNA PyPI）、校验ZIP SHA256清单、执行所有Python回归测试、生成全球GF10索引、建立已下载文件的自动发现计划。**要求测试全部通过**。如果服务器无法连接清华源而已有相应Python依赖，则可以执行 `-SkipPip` 并依靠完整的 import + pytest 进行检查。

如果之前的WorldClim/其它生产任务仍在运行，**先正常结束该任务再启动一键全量任务**。脚本会检查其他活跃 `-m ceeall raster`/GISD/ERA5EX进程，禁止两套任务并发写同一输出目录。

## 3. 只执行下面的一条正式全球命令

```powershell
.\scripts\01_run_all_full.ps1 -Root 'E:\WJH_CEE'
```

不需要再手工填写 `--source`、`--layer`、`--fields`、`--tag` 或 `--max-cells`。默认栅格并行 **4×16=64个独立进程**（每个Python独立栅格来源内部采用`ProcessPoolExecutor`，并在输入来源完成后自动调度下一来源），网络线矢量并行为**2×16**；30m GISD30限8并行，NetCDF限2，遵守128GB内存预算。

高级配置（仅当资源日志证实增加worker仍可加速）：

```powershell
.\scripts\01_run_all_full.ps1 -Root 'E:\WJH_CEE' -RasterJobs 6 -RasterWorkers 16 -VectorJobs 2 -VectorWorkers 16
```

此时栅格阶段最多96个进程，不是要求单个Windows`ProcessPoolExecutor`启动96个（Windows单池上限61）；大型压缩栅格和FileGDB的性能可能受SSD/内存限制，**CPU100%不是目标**。首次生产保守选择默认64进程；读写日志判断提升是否有意义。

每阶段写入：`E:\WJH_CEE\reports\cee_full_v2\stages`，每个栅格子进程写入`reports\cee_full_v2\logs`，整轮日志见`reports\cee_full_v2\full_run_*.log`，每15s监控CPU、内存、累计进程数量、磁盘读写MB/s在 `resource_monitor.csv`。如任一来源GDB字段与官方结构不符，自动停止相应来源并留下`failed_stage.json`，已完成715分区仍在盘上，修复后**再次执行完全相同的一条命令即可续跑**。绝不自动删除旧数据或将失败当成功。

## 4. 正式执行后只读验证

```powershell
.\scripts\02_verify_all_full.ps1 -Root 'E:\WJH_CEE'
.\scripts\03_status_and_cpu.ps1 -Root 'E:\WJH_CEE'
```

验证门槛：5 GHSL、5 GMTED、19 BIO、84月度、1 GRIP4密度来源皆有715分区，格网数守恒；原生GRIP4道路/ RiverATLAS河流/国家/省级/城市/流域**六族矢量全都715分区**；GISD30所有实际原始TIFF完成分类并给出8期历史GF10表，ERA5-EX 34指标完整年度宽表，Groundsource原始记录数守恒，外部灾害事件表存在；任何缺失报告结构性失败。

注意：结构性计算通过后**`publication_ready=false` 仍是正确状态**，下列科学门槛不能用代码强行跳过。详见第6节。

## 5. 输出结构与独立时态

| 数据表 | 关键键 | 实际目标 |
|---|---|---|
| `data/derived/cee_all_global_v2/gf10_static_wide/tiles/*.parquet` | `grid_id` | 715个分片、全部GF10、GHSL/GMTED/WorldClim/GRIP密度/GISD/矢量背景 |
| `.../era5ex_annual_wide/year_YYYY.parquet` | `grid_id×source_year` | 每个源年份全部34项年度气候指数，和静态表分开 |
| `.../gisd30_history/gf10_gisd30_history_1985_2020.parquet` | `grid_id` | 历史8期不透水比例，保留未覆盖格网为缺测 |
| `.../vector/roads/tiles/*.parquet` | `grid_id` | 道路总长度(km)、陆地面积道路密度、线段数、0值缺测不确定性 |
| `.../vector/river/tiles/*.parquet` | `grid_id` | 河段测地长度、长度密度和河段数 |
| `.../vector/{admin0,admin1,ucdb,basin}/crosswalk/*.parquet` | `grid_id×原生提供者ID` | 所有相交polygon的实际等面积重叠面积；非简化中心点归属 |
| `.../native_attributes/*/parts/*.parquet` | 来源原始ID | 原始城市、流域及行政区的全部下载字段；不复制成格网实测 |
| `.../groundsource_reports/parts/*.parquet` | `uuid` | 完整新闻/定位事件表，与实际淹没相互独立 |
| `data/derived/cee_all_v11/flood_catalogue/` | 事件ID/日期 | Global Flood Records历史灾害事件上下文 |
| `.../gf10_static_wide/indicator_dictionary.csv` | 指标字段 | 全字段来源/单位/时态和QA状态 |

表名仍包含`v11`的旧源是为了**无损复用服务器已算完的GMTED等成果**；新生产品固定为`cee_all_global_v2`以防误覆盖。

## 6. 不能省略的正式论文质量门槛

1. **海岸线分母**：冻结GF10按完整100km²方格执行原生像元统计，但实际土地面积 `land_area_km2` 仅是分母；必须后续获得 `GF10∩GSHHG` 真实土地几何，对141,078个部分陆地格网特别是9,734个面积不足1km²格网，核查建成比例、WorldClim、GISD30、道路密度是否需要按陆地有效几何重算。不能直接宣称海岸所有百分比精准。
2. **GMTED高程元数据矛盾**：用户确认五种下载产品按均值统计，但 elevation TIFF 的内部 description 明确写了 **Maximum elevation**。修正版继续作为均值口径的试算统计，**不能将该字段正式标为已经验证的mean elevation**；须以源发行记录/上游数据说明判定，必要时替换高程原产品。Slope/TPI/TRI的源单位也须人工或自动依据官方metadata核定。
3. **原生物理意义**：WorldClim为**1970–2000气候常态**，有103幅原生产品；ERA5-EX为历史**年度**0.1°指数；GHSL为2000/2020/2015等epoch变量；Groundsource是报道定位。不能拿完整2024年极端指数当预测2024年早期暴雨的已知暴露，不可把新闻多边形当真淹没范围。<https://www.worldclim.org/data/worldclim21.html>
4. **道路和河网**：GRIP4道路数据源非全球完全观测，且局地无记录`0`未必证明没有道路；代码留有 `zero_length_source_coverage_unverified`。按WGS84测地长度统计后的数值还要与GRIP官方5'道路密度作源覆盖交叉比较，并对反子午线和高纬度格网单独QC。RiverATLAS 的主河段长度不代表地表所有水路密度。
5. **GISD30来源完整性**：论文发布为961幅5° TIFF，你的此前盘点发现953幅；代码要求至少已有953原生TIFF，实际与961的差额不得自动认为都是海洋，应生成缺测支持范围、核对12个RAR包的来源hash/瓦片覆盖，并审查瓦片交叠及原生经纬像元面积对比例的影响。<https://essd.copernicus.org/articles/14/1831/2022/essd-14-1831-2022.html>
6. **因果和负例**：Figure 2的城市内涝韧性研究仍须补足IMERG当日24h和最大3h雨量、ERA5-Land前期土壤条件、MERIT Hydro的HAND与汇流、WorldCover地表覆盖，以及独立卫星/现场真实淹没和可靠观测负例。现有全本地指标处理成功也不能替代这些，故默认不把整体标记为“论文已经可以投稿”。

## 7. 官网方法依据（按源原文，不改变原始物理含义）

- [AMD EPYC 9654（96核192线程）](https://www.amd.com/en/products/processors/server/epyc/4th-generation-9004-and-8004-series/amd-epyc-9654.html)。
- [ExactExtract native covered-cell statistics](https://isciences.github.io/exactextract/operations.html)。
- [Pyogrio GeoPackage/GDB空间bbox与Arrow分区读取](https://pyogrio.readthedocs.io/en/latest/introduction.html)。
- [WorldClim 2.1 官方](https://www.worldclim.org/data/worldclim21.html)。
- [GISD30原始论文](https://essd.copernicus.org/articles/14/1831/2022/essd-14-1831-2022.html)。
- [GRIP4数据源简介](https://www.globio.info/download-grip-dataset)。
- [HydroATLAS官方](https://www.hydrosheds.org/hydroatlas)。
- [USGS GMTED2010](https://www.usgs.gov/coastal-changes-and-impacts/gmted2010)。

## 8. 已验证与未验证的范围

此发布包完成了Python语法检查、离线单元测试、GPKG道路线段与行政面自动字段发现及几何相交的合成计算。制作环境没有挂载你服务器的47.89GB原始文件、GDB内部真实图层和完整1,395,471行GF10基底，因此**不能保证每个来源在你的服务器上没有因真实字段/物理单位或原生文件损坏而触发阻塞**。这正是 fail-closed 的目的：给出可追溯错误，修复后继续原有分区，而非默默跳过并声称正式完成。

---

# v2.2 补充：FileGDB嵌套与UCDB全部主题自动处理

本节覆盖 v2.1 真实运行时的两个阻塞：`Automatic provider vector detection incomplete`、`BasinATLAS_Data_v10.gdb: Permission denied`。**已确认数据已正确解压**，不要再下载或手动移动它们。

实际路径：

```
E:\WJH_CEE\data\staged\cee_all\BasinATLAS_Data_v10.gdb\BasinATLAS_v10.gdb
E:\WJH_CEE\data\staged\cee_all\RiverATLAS_Data_v10.gdb\RiverATLAS_v10.gdb
E:\WJH_CEE\data\staged\cee_all\GRIP4_global_vector_fgdb\GRIP4_GlobalRoads.gdb
```

外层文件夹后缀 `.gdb` 不代表真实FileGDB；内层拥有`.gdbtable`才是真正数据库。新代码只使用这些真正的FileGDB路径，保留原数据源完整性。`pyogrio.list_drivers().get('OpenFileGDB')` 为 `raw` 表示包含读取权限（r），并非权限不足。数据库几何与数据字典原有原生源的定义保持不变。

UCDB的多个 `GHSL_UCDB_THEME_*_GLOBE_R2024A` 面图层是**不同主题属性**，不是重复错误。新代码为GF10空间分配优先选择 `THEME_GEOGRAPHY`，主题数据在源级实体表按城市原生ID全部单独导出；不把气候等城市级年度属性任意广播到每个10km格网。

## 只执行两条正式指令（服务器不需要 GitHub）

将 `CEE_GF10_GLOBAL_FULL_v2_2.zip` 复制至 `E:\WJH_CEE` 后：

```powershell
$ROOT = 'E:\WJH_CEE'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GLOBAL_FULL_v2_2.zip" -DestinationPath $ROOT
$PKG = "$ROOT\CEE_GF10_GLOBAL_FULL_v2_2"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force

# 自动完成 35文件与冻结GF10审计、全部测试、矢量源识别、全球断点生产
.\scripts\07_resume_after_provider_fix.ps1 -Root $ROOT `
  -RasterJobs 4 -RasterWorkers 16 -VectorJobs 2 -VectorWorkers 16

# 以上成功结束后执行严格全局结构QC
.\scripts\02_verify_all_full.ps1 -Root $ROOT
```

若想先单独验证路径/图层不启动重任务：

```powershell
.\scripts\06_validate_provider_sources.ps1 -Root $ROOT
```

输出 `E:\WJH_CEE\reports\cee_full_v2\vector_source_autodetect_v22.json` 必须无 `errors` 且至少发现6类空间来源；`ucdb_attribute_layers` 应列出本地可用的所有主题。**不能仅靠脚本最终返回0就直接宣称论文数据达到发表标准。**

## v2.2结果与复用

- 仍复用 `data\derived\hpc_exact_ghsl_*_v2`、`data\derived\cee_all_v11\gmted`、`worldclim-bio`、`worldclim-monthly` 和其它已成功QC结果；不会因为代码包目录升级就重新下载数据。
- 完成的矢量产出位于 `data\derived\cee_all_global_v2\vector\{admin0,admin1,ucdb,basin,roads,river}`，每类715格网分区。
- UCDB全部主题在 `data\derived\cee_all_global_v2\native_attributes\ucdb\themes`，应和GF10空间crosswalk独立使用。
- 失败时看 `reports\cee_full_v2\failed_stage.json` 和 `full_run_v22_*.log`，修复后重跑相同命令；不要清空`data\derived`。
- 有效格网行数、不透水占比/年限、道路河网长度零值含义、实际陆地面积的限制以及UCDB城市与暴雨事件时间泄漏仍需要后续审查。

---

## v2.3: GRIP4官方ASCII Grid空间参考与Shapely警告修复

已通过上次失败日志定位GRIP4总密度数据`.asc`因缺少坐标系导致程序终止。v2.3仅对经4320×2160、全球经纬度界限、5角分、单波段严格验收的官方源在**已解压暂存文件夹**创建同名`.prj`，未对原始GRIP4数值重采样或更改原始ZIP。此类数据源由GDAL显示为`OGC:CRS84`属于WGS84经纬度轴顺序的规范化表示，不是错误。独立修复脚本为`scripts\08_prepare_grip_crs.ps1`，一键完成修复与正式生产为`scripts\09_resume_v23.ps1`。消除`shapely.ops.transform`弃用警告但不掩盖数值和几何异常，其他说明见 `CHANGELOG_V23_CN.md` 和 `README_START_HERE_CN.md`。
