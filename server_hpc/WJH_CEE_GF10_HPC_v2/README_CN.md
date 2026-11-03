# WJH_CEE — GF10 Global Land Local HPC v2（Windows 96核 / 128GB）

2026-11-03，GEE_flooding 项目，独立的高性能**本地数据生产包**。主要输入是冻结且已通过历史质量审核的 `E:\WJH_CEE\gf10_global_nonantarctic_land.parquet`（EPSG:6933，1,395,471个非南极陆地 GF10，陆地面积合计133,095,959.350 km²）。**不重建格网、不覆盖原始数据、不联网下载、不调用GEE、不自动承诺发表级准确性。**

## A. 先确认本轮真实数据

2026-11-03 的 Codex 上传清单显示：`E:\WJH_CEE\CEE数据` 单层目录，**35个文件/47.89 GB**（压缩包解压规模约60.24 GB）；此外先前服务器日志已确认：`E:\WJH_CEE\data\raw\groundsource\groundsource_2026.parquet` 已通过源MD5，GHSL 2000/2020 1km建成面积 ZIP 已完成长度校验，但后者还需要ZIP CRC与原始TIFF属性审计。所有脚本均从**现有文件**读取，无新下载。

| 数据 | 下载后真实源 | 首轮作用 | 本包支持 |
|---|---|---|---|
| GF10 | `E:\WJH_CEE\gf10_global_nonantarctic_land.parquet` | 唯一ID、100km²完整方格和真实陆地面积 | `audit`, `tiles` |
| GHSL BUILT-S 2000/2020 1km | `data\raw\ghsl\*` | 建成面积、扩张 | `stage`,`raster-fast`,`raster-exact`,`assemble` |
| GHSL POP2020 / NRES2020 / SMOD2020 | `data\raw\ghsl\*` | 人口、非住宅、城郊类别 | 同上，按变量分别计算 |
| GMTED2010 | `CEE数据\*.tif` | 高程、坡度、粗糙度、TPI、TRI | 两类 raster 引擎 |
| GRIP4道路密度 | `CEE数据\GRIP4_density_total.zip` | 5′道路背景（不可视作原生GF10实测） | `stage-archive`,`raster-fast`,`raster-exact` |
| WorldClim 2.1 | `CEE数据\wc2.1_30s_*.zip` | 长期气候背景1970–2000 | 精选ZIP成员提取 + raster |
| ERA5-EX v4 | `CEE数据\ERA5-EX v4.zip` | **年度**极端指数1950–2025 | `stage`,`era5ex`，0.1°源最近邻代理 |
| GISD30 1985–2020 | `CEE数据\GISD30_*.rar`（12包） | 2000、2020不透水面及历史变化 | `gisd-prep`：原30m先二值化、再1km比例，再raster |
| GHS-UCDB R2024A V1.2 | `CEE数据\GHS_UCDB*.zip` | 城市实体/背景（不是全球网格静态原生像元） | `stage-archive`,`vector-centroid`（明确为代理） |
| HydroATLAS Basin/River | `CEE数据\*ATLAS*.gdb.zip` | 流域/河网属性（**不能代替 GF10 HAND**） | `stage-archive`, Basin低层级`vector-centroid` |
| geoBoundaries ADM0/ADM1 | `CEE数据\geoBoundaries*.zip` | 国别和一级行政区 | `stage-archive`,`vector-centroid`（中心点代理） |
| Global Flood Records | `CEE数据\Global_Flood_Records.csv/gpkg` | 5503条外部洪灾事件，仅事件资料，非实测内涝边界 | 独立来源，**不进入静态宽表** |
| Groundsource2026 | `data\raw\groundsource\groundsource_2026.parquet` | 新闻报道及地理定位，独立 O 层 | 保留在旧 v1.1 `wjhcee.observations`，本轮不纳入静态层 |

重要源事实及语义：欧盟[JRC GHSL Download Wizard](https://human-settlement.emergency.copernicus.eu/downloadWizard.php)；[GISD30的官方论文](https://essd.copernicus.org/articles/14/1831/2022/)（0透水、1~8时段不透水）；[HydroATLAS](https://www.hydrosheds.org/hydroatlas)（流域背景）；[ERA5-EX论文](https://www.nature.com/articles/s41597-026-08312-x)（34项0.1°年度指数）；[ExactExtract技术说明](https://isciences.github.io/exactextract/)。

## B. 计算架构（为何比逐GF10打开栅格更快）

**GF10分块固定**。冻结网格ID不变，按格网索引x/y每64×64 GF10保存一份轻量Parquet，一次分片建立、所有栅格重用。每个worker处理一块地理区域，原始栅格文件只在相交分片时被读取。NoData和无源覆盖保持null；所有输出带年份、方法、源版本、进度、重复执行的job fingerprint。

**两种引擎：**

1. `raster-fast`：GDAL/Rasterio从原生源分块重投影到**与GF10严格对齐的1km工作网格**，每个GF10对应100个工作像元，在内存中NumPy批量聚合；采用24 worker×2 GDAL线程起步，允许通过性能测试逐步提升至32×2或48×2（上限96线程）。这是对原生像元的**近似重采样**，默认状态为 `...NEEDS_EXACT_AND_COAST_QA`，适合快速生成全量候选值/定位缺口。
2. `raster-exact`：以每个64×64块为任务，通过C++ exactextract对**原始本地GeoTIFF像元与完整10km多边形**精确交叠；使用多进程（建议16–24），而不是每个格网重新打开TIFF。对于JRC 1000m Mollweide面积和人口等像元总量，这是**首选正式源像元汇总引擎**。输出仍标记需要实际陆地多边形和外部产品面积守恒验证。

两者不能混称：`raster-fast`快，不是原生像元精确面积；`raster-exact`计算原始像元交叠，但GF10提供的仍是完整100km²方格而不是海岸线裁剪几何。后者**也不能自动把沿海海水像元排除**。

**类别数据不能按0..8求平均：**GISD30先在原生30m数据中将1~4转为2000年是否不透水、1~8转为2020是否不透水，生成EPSG:6933的1km**fraction**影像再汇总。SMOD使用类别统计，不做类别整数均值。历史2000与2020区分原始像元单位、日期、产品版本。

### CPU/RAM/磁盘调度

96核并不等于应开启96个重投影进程：磁盘吞吐、GDAL共享缓存和128GB内存更易成为瓶颈。推荐实测顺序：`8×2`、`16×2`、`24×2`、`32×2`、`48×2`（`workers×gdal_threads<=96`），选择**单位秒处理格网数最高**而且RAM峰值<100GB的方案。一个任务来源族跑完再提交下一类，避免5个任务同时竞争SSD缓存。ExactExtract多进程建议16–24个。GISD原生每幅18554×18554像元约344MB uint8，另有二值掩码/临时数组：**8–12worker**起步，更高并发可能导致内存峰值过高。`RTX6000`显卡不会自动被GDAL、exactextract或pyarrow使用；本包默认CPU，不需要CUDA。

建议分区输出到 `E:\WJH_CEE\data\derived\hpc_*`，原始ZIP保留在 `CEE数据` 和 `data\raw`，只暂存选中的ZIP成员。各来源生成`run_qc.json`且断点安全：重复执行同一作业会使用已验证、来源未变的已完成分片；如源文件改变，应选择新版本输出路径，不覆盖旧成果。

## C. 直接按顺序运行（PowerShell）

### C1. 环境与全域格网索引（先执行）

将代码ZIP解压到 `E:\WJH_CEE\WJH_CEE_GF10_HPC_v2`。Python沿用已经存在的 `E:\WJH_CEE\.venv\Scripts\python.exe`。

```powershell
$ROOT='E:\WJH_CEE'
$PKG="$ROOT\WJH_CEE_GF10_HPC_v2"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\00_preflight.ps1
```

它执行`pytest`、GF10 ID/面积检查、已有数据源清单、全球tile索引。已存在的完整分片按源指纹复用。输出：

- `E:\WJH_CEE\reports\hpc_sources_v2.csv`
- `E:\WJH_CEE\data\working\gf10_hpc_tiles64_v2\tile_index_qc.json`
- `E:\WJH_CEE\data\working\gf10_hpc_tiles64_v2\index.parquet`
- `E:\WJH_CEE\data\working\gf10_hpc_tiles64_v2\tiles\tile_*.parquet`

**没有GEE，零EECU。** 若真实GF10原始schema不满足`grid_x/y`或`grid_id=x_y`，明确报告实际列名后修复映射，不允许更改冻结坐标及ID。

### C2. GHSL 源文件试处理（必须先跑）

```powershell
.\scripts\01_ghsl_pilot.ps1
```

该脚本自动识别**服务器已下载**的GHSL 2000建成、2020建成、2020NRES、2020POP和2020SMOD官方ZIP，按需解压单个原生TIFF，抽取全球各地**12个分布式格网瓦片**测试，并生成QC。缺失的产品只报告未找到，不会替你下载。核实来源、原始1000m Mollweide投影及海岸格网覆盖，再继续。

若希望**原始源像元精确**而不是快速插值近似，建议在第一个GHSL2020源运行：

```powershell
$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$TIF="$ROOT\data\staged\ghsl_built_2020_1km\ghsl_built_2020_1km.tif"
& $PY -m gf10hpc raster-exact --tiles $TILES --source $TIF `
 --profile ghsl_built_2020 --out "$ROOT\data\derived\hpc_exact_built2020_v2" `
 --workers 16 --max-tiles 12
```

如果两个引擎的审计差值显著，或论文核心要求使用原始像元精确统计，后续正式GHSL优先运行不带 `--max-tiles` 的 `raster-exact` 版本；不要将快速近似值当正式数值。

### C3. 完整 GHSL 批处理（通过Pilot后）

```powershell
.\scripts\02_ghsl_full.ps1
```

该步骤重新使用同一输出目录，跳过完成分片，计算未完成部分。`raster-fast`默认`workers=24`, `gdal_threads=2`。若数据确实来自JRC1km原生等面积产品，原始建成面积单位是m²/像元，求和后转为km²；人口为人/像元，求和；SMOD城市类别为21/22/23/30，输出城市组成是**完整100km²格网面积占比**，不冒充陆地占比。

### C4. 地形五指标与道路背景

```powershell
.\scripts\03_gmted_pilot.ps1
```

检查源高度图文件名与内部描述“mean/maximum”不一致；坡度、TPI和TRI单位未逐项确认，输出字段故意标为`*_unverified_unit`。不要仅凭数值落在0..90就宣称坡度单位是角度。通过审计后，用以下同样命令移除 `--max-tiles 12` 并采用新版本目录或继续当前来源作业：

```powershell
$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
& $PY -m gf10hpc raster-exact --tiles $TILES `
 --source "$ROOT\CEE数据\elevation_1KMmn_GMTEDmn.tif" `
 --profile gmted_elevation --workers 16 `
 --out "$ROOT\data\derived\hpc_exact_gmted_elevation_v2"
```

地形源已核实的纬度范围约56°S至84°N，**不能把源外缺测自动补零**。对于你要求全域非南极基础表的研究目标，缺测区域后续由其他原始DEM或GEE补充，不得声称地形100%覆盖。

GRIP4 5′道路密度（m/km²）不用2500万条矢量道路重新求总长度。先从zip解压 `grip4_total_dens_m_km2.asc`，用`--profile grip_density`提取全域**代理道路密度**，需要精确GF10道路长度时再处理道路矢量：

```powershell
& $PY -m gf10hpc stage --zip "$ROOT\CEE数据\GRIP4_density_total.zip" `
 --member '*total_dens_m_km2.asc' `
 --out "$ROOT\data\staged\grip_density\grip4_total_dens_m_km2.asc"
& $PY -m gf10hpc raster-exact --tiles $TILES --workers 16 `
 --source "$ROOT\data\staged\grip_density\grip4_total_dens_m_km2.asc" `
 --profile grip_density --out "$ROOT\data\derived\hpc_exact_grip_density_v2"
```

### C5. 现有30GB以内气候原始数据的高效处理

从WorldClim 2.1先选取BIO1/BIO12/BIO15/BIO18/BIO19，不必立即全部解压103幅TIFF。示例：

```powershell
& $PY -m gf10hpc stage --zip "$ROOT\CEE数据\wc2.1_30s_bio.zip" `
 --member '*wc2.1_30s_bio_12.tif' `
 --out "$ROOT\data\staged\worldclim\bio12.tif"
& $PY -m gf10hpc raster-fast --tiles $TILES `
 --source "$ROOT\data\staged\worldclim\bio12.tif" `
 --profile worldclim_bio12 --workers 24 --gdal-threads 2 `
 --out "$ROOT\data\derived\hpc_worldclim_bio12_v2"
```

注意WorldClim是**1970–2000长期背景**，不代表2021–2025暴雨当日降水；对温度指数应核实源文件scale/offset和单位，不能直接把原生数值当摄氏度。

ERA5-EX具有0.1°、34年度指数，不应以1000m原生栅格流程处理。执行：

```powershell
.\scripts\05_era5ex_example.ps1
```

脚本只解压RX1day对应的一个年度NetCDF，然后读取指定年份（示例2000/2005/2010/2015/2020及2021–2025），直接在原始0.1°气象坐标用GF10中心做最近邻采样，生成每年Parquet并标记 `SOURCE_0P1_DEGREE`。作为区域气候背景与长期事件气候分区，不得宣称是10km实测极端降雨，也不能拿2024全年指数去预测2024年早期洪涝事件。

### C6. GISD30 1985–2020 全部原始分类本地处理

先安装Windows 7-Zip并确保`7z`命令可用：

```powershell
.\scripts\04_gisd_optional.ps1
```

该脚本解压已存在的12个RAR到**版本化临时目录**，先跑8张真实30m栅格。检查：每个像元类别0,1,..,8；2000期二值掩码=1–4，2020期=1–8；30m原生高分辨率类别**先转二值**，再经GDAL area-average到GF10对齐的1km预处理栅格。如果实际归档覆盖少于官方的961幅，必须记录空间缺口、不能造零。源资料不同纬度的30m经纬网格不能将原始类数均值直接当fraction。

只有Pilot QC通过，重跑以下命令移除`--max-files 8`处理全部：

```powershell
& $PY -m gf10hpc gisd-prep `
 --source-dir "$ROOT\data\staged\gisd30_native_v1" `
 --out "$ROOT\data\working\gisd30_binary_to_1km_v2" `
 --workers 8 --gdal-threads 2
```

之后按1km预处理产品的分区目录汇总：

```powershell
& $PY -m gf10hpc raster-fast --tiles $TILES `
 --source-dir "$ROOT\data\working\gisd30_binary_to_1km_v2\2020" `
 --glob '*.tif' --profile gisd2020_fraction_1km `
 --out "$ROOT\data\derived\hpc_gisd2020_v2" --workers 24 --gdal-threads 2
```

2000期同样使用`--profile gisd2000_fraction_1km`。**GISD30的30m细粒度城市结构已在1km预处理后损失；该结果用于GF10不透水总量及历史扩张敏感性，局部异质性/破碎度不能从它反推。**

### C7. 国家/城市/流域属性（不是静态栅格原生值）

```powershell
.\scripts\07_admin_country.ps1
.\scripts\08_hydroatlas_pilot.ps1
```

国家采用geoBoundaries ADM0、GF10中心所在国家**代理归属**；沿海微小岛屿的GF10中心可能落在海洋，应保留null和边界不确定性，不得随机归入最近国家。若要国家级严格面积分配，后续应按`GF10∩真实陆地∩国家边界`面积分配，不能用中心点取代。

HydroATLAS先用BasinATLAS level06/07提取预计算流域ID/大尺度环境背景；**不等价于GF10内90m HAND、坡度和局地汇流面积**。RiverATLAS 847万河段、GRIP 2576万道路线均属于P2大规模矢量计算，不建议在首次全局静态宽表生产中就进行全球道路/河网多层空间overlay。UCDB建议单独以城市ID+年份做城市属性表，不能将城市平均经济指标复制给所有GF10后宣称格网实测。

### C8. 全球静态宽表整合

在 GHSL五个来源**全域分片**均完成且QC无异常时：

```powershell
.\scripts\06_assemble_static.ps1
```

输出：`E:\WJH_CEE\data\derived\gf10_global_static_v2.parquet` 和 `*.qc.json`。它只收集**完成的静态来源**，保留缺测，并计算2000–2020建成面积增长、NRES不可大于总建成面积等物理核验。年度ERA5EX留在Y层，Groundsource留在O层，绝不混进S层。

注意：输出中的 `publication_ready=false` 是有意保留的科学门槛。**通过全球脚本不意味着所有139.5万格均具有可发表指标。**

## D. 源像元守恒与论文级质量门槛

1. **真实源 vs 工作源**：GHSL官方1000m等面积源总建成面积/人口应与GF10相交区域原生精确统计以及JRC产品说明一致，避免源像元单位错误；对于10m/30m分类不允许直接采用浮点类别值平均。
2. **陆地掩膜**：原始GF10 Parquet有完整方格与`land_area_km2`，没有真实海岸线裁剪多边形。海岸格网的WorldClim、地形、土地覆盖密度和城乡类别比例**不自动等于陆地内比例**。必须后续根据GSHHG full非南极陆地矢量构建精确`land_geometry`，与源原生像元重叠；在此之前必须保留`coast_approximation_flag`。Tiny-island的1km/0.1°源数据可能不足以可靠表征，必须标为低有效空间支持。
3. **单位/原始定义**：地形5TIF文件名和内部metadata“mean/maximum”矛盾；坡度、roughness、TPI、TRI单位未独立确认；ERA5EX每个指标的`units`需从实际NetCDF逐个核对。不能因为经过 GF10 汇总就抹掉原始不确定性。
4. **范围不完整**：GMTED约-56–84°、GISD30约-55–80°，部分非南极高纬与南部海岛仍缺失，不能将null设为0。MERIT Hydro、ESA WorldCover、夜光及真实逐日IMERG/ERA5-Land仍待第二阶段GEE或官方源补充。
5. **重复运行和版本**：一套源一个独立输出目录，完整QC与源指纹严格对应。全域程序可从Pilot同一输出目录续跑，若代码参数、产品版本或原始文件不同则新建v3目录。不要手动修改原始GF10。
6. **分组和时序**：主Figure2暴雨总体2021–2025 UTC逐日，M0真实最大3h（由半小时产品计算）+24h+前7日；年度极端指数不得在年内事件发生之前就被当作已知值；Fig1 Groundsource新闻记录只是报告O，非实际Flood F。Figure3独立正负物理观测。
7. **吞吐**：记录每源`n_tasks,elapsed_s,tiles_per_second,peak_ram_gb(外部监控)`，分别测速。Windows`Get-Counter '\Processor(_Total)\% Processor Time'`、`Get-Process python | Measure-Object WorkingSet64 -Sum`、SSD读写速度作为瓶颈诊断。不要无条件追求CPU100%，大文件解压/磁盘等待期CPU低是正常的。

## E. 后续真正需要交GEE的数据

仅在本地可复用产品不足时，才在GEE处理 `ESA/WorldCover/v200`（10m分类，全球约117GB）、`MERIT/Hydro/v1_0_1`（HAND/upa/90m水文）、必要的`NASA/GPM_L3/IMERG_V07`短时降雨峰值、和局部城市100m建成形态。GEE任务按GF10已冻结的分区统计、每类源一次导出到Parquet，而非每20格一个任务。先25/1000格真实 EECU benchmark，不将完成单幅TIFF的时间视为官方EECU消耗。

## F. 执行限制和验收状态

本代码通过沙盒**5项无PyArrow依赖的单元测试**；有2项需要PyArrow才能测试真实Parquet的tile/warp端到端流程，已保留在 `tests/`，会在你的Windows服务器安装依赖后运行。代码没有连接你服务器的`E:`、没有重新下载47.89GB、没有实际全球端到端计时，也没有用GEE额度。**首轮应当先运行00，然后01小样本，验证所有原生源后才跑02和后续大批次。**

## G. 2026-11-03 官网产品核验增强与正式任务顺序

针对作者要求的**只使用官网下载的真实源**，增加 `verify-source`，逐个核对原始 GeoTIFF 的实际投影、每像元单位、年份、NoData、采样值域和ZIP成员CRC来源。此检查只抽样三个窗口，**不能替代原产品全球总量/面积守恒核验**；且仅源文件自带相应元数据时才能声称已核对到具体单位。对 WorldClim 的历史温度和 GMTED 派生地形，在实际 TIFF 未注明 scale/offset/单位时，保留 `unverified`，不擅自换算为摄氏度或角度。常用官网：[GHSL 2023 建成面积](https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php)；[GHSL 人口](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php)；[SMOD V2 分类及 NoData -200](https://human-settlement.emergency.copernicus.eu/ghs_smod2023.php)；[WorldClim 2.1 1970–2000](https://www.worldclim.org/data/worldclim21.html)；[GMTED2010 原产技术资料](https://www.usgs.gov/coastal-changes-and-impacts/gmted2010)；[GISD30 正式论文](https://essd.copernicus.org/articles/14/1831/2022/)；[HydroATLAS 正式产品说明](https://www.hydrosheds.org/hydroatlas)。

**重要接口修复**：`exactextract` 的 `frac_as_map` 不是统计操作。应使用 `['count','frac']` 以及 `output_options={'frac_as_map':True}`，不可以调用不存在的 `['count','frac_as_map']`。此修复已同步 `gf10hpc/exact.py`。依据 [exactextract 分类官方使用示例](https://isciences.github.io/exactextract/landcov.html)。源 TIFF 从 ZIP 解压/再次复用时一律执行 ZIP成员 CRC32 完整性校验，防止“文件长度正确却损坏”被忽略。

正式顺序：

```powershell
$ROOT='E:\WJH_CEE'
$PKG="$ROOT\WJH_CEE_GF10_HPC_v2"
$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
Set-Location $PKG
.\scripts\00_preflight.ps1
.\scripts\01_ghsl_pilot.ps1
# 检查 reports\verify_ghsl_*.json 及每类产品12格pilot完整率
.\scripts\10_benchmark_workers.ps1  # 比较8/16/24/32/48 workers
.\scripts\11_ghsl_native_exact.ps1   # 先只跑12个地区分散tile的原生精确源审计
# 在小样本全部成功、资源监控允许后，再执行：
.\scripts\11_ghsl_native_exact.ps1 -Full -Workers 16
.\scripts\06_assemble_static.ps1
```

`11_ghsl_native_exact.ps1` 优先用于正式GHSL数值。若服务器上的 ExactExtract 0.3.0 对类别 `frac` 输出 `pandas` 字典形式不同，应在**12个真实 SMOD 原生栅格样本测试阶段**停下检查，不可改用类别代码均值应付。输出保留 `publication_ready=false` 直到全球陆地相交边界、官方参考总量和独立影像核验均完成。

源代码未连接实际服务器 E 盘，无法在这里证明整个139.5万格的真实全球数值、下载 ZIP 和任务吞吐。先在服务器运行全套 `pytest`（制作环境没有 pyarrow/exactextract，部分端到端测试是显式跳过），然后才可启动大计算。
