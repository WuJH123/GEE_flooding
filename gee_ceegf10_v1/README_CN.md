# CEE GF10 GEE V1：新项目隔离、pilot先行、实测EECU闸门

**范围**：本项目单独使用全陆地非南极GF10（EPSG:6933，10km，1,395,471格，格网左下角锚定(0,0)），**代码不读取本账号历史项目的任何私人资产**。本包包含之前的 `local_static_v2_3` 完整离线修复静态栅格代码快照，和独立运行的新 GEE Python API 代码。

## 科学策略与成本约束

- **不用 GEE 重做**：已经完成全球分区计算的 GHSL、GMTED、WorldClim。GRIP4、GISD30、ERA5-EX 和原生道路数据仍按服务器v2.3流水线继续处理并做QC，GEE不得重复计算这些已下载来源。
- **GEE 静态 P0**：MERIT Hydro (~90m，`hnd`/`upa`/`elv`/`wat`) 和 ESA WorldCover2021 (10m，11类占整个100km²格比例及影像覆盖率)；它们不是雨天积水观测，不能用于替代标签。
- **GEE 动态 P0**：IMERG V07半小时 `precipitation` 带单位mm/h，乘以0.5h转成每半小时mm，事件日逐窗口3h、24h及事件前7天/30天；ERA5-Land 前一天土壤水、温度和日降水。事件匹配仅在具有真实 `grid_id × date_utc` 表后才能正式跑。无案例不得创建虚假的观测日期。
- **面积/尺度**：所有静态输出首先是100km²完整正方形汇总。沿海后续按 GSHHG 陆地裁剪或分母敏感性分析；MERIT Hydro研究的是流域地貌背景，不是城市工程排水容量。
- **费用**：项目额度1000 EECU-hours / 月（仅当该独立项目已获Google Contributor Tier）。pilot 四任务先测试，完成后在本地收集 `batchEecuUsageSeconds`、核查类别守恒和近似精度；仅提交1条全球条带，下载GeoTIFF做对齐QC，实测EECU后才放开下一条。静态全部任务不自动发起。

## 在目前有 GEE 网页登录的 Windows 电脑运行

1. 将 ZIP 解压在任意目录，复制服务器中的 `E:\WJH_CEE\gf10_global_nonantarctic_land.parquet` 到代码包根目录（约10MB）；不需要复制47GB原始数据。
2. 新建**独立的Google Cloud项目**并注册启用Earth Engine API，给其绑定正确非商业层级。请勿用老项目ID代替。创建Cloud项目：https://console.cloud.google.com/projectcreate；Earth Engine项目登记：https://code.earthengine.google.com/register 。
3. 用PowerShell运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\00_setup.ps1
.\scripts\01_initialize_and_probe.ps1
.\scripts\02_pilot_static.ps1
```

`00_setup.ps1`只要求输入一次**真实新项目ID**，配置在`config/local_run.json`中；Google弹出授权页面。在GEE端只创建自己新项目下的唯一试验文件夹，不读取已有项目资产。`02_pilot_static`会提交MERIT和WorldCover各2个pilot表（原生参考/生产分辨率）到EE资产中。**不会提交任何全球任务。**

待试验任务显示完成，在同一目录执行：

```powershell
.\scripts\03_collect_and_check.ps1
.\scripts\06_check_quota.ps1
```

核对`reports/pilot_qa.json`中的参照精度、世界覆盖分类加总和当前实测EECU。没有看到 `PILOT_TECHNICAL_QA_PASS_NEEDS_MANUAL_REVIEW` 就不要继续。通过之后，才运行：

```powershell
.\scripts\04_approve_and_submit_first.ps1
```

此命令要求键入本次运行的`run_id`，然后只提交**MERIT全球区域的1/12条带**到仅此项目的Google Drive文件夹。不要连续把12条都投递。等Google Drive中有第1条带的GeoTIFF后下载到本地：

```powershell
$ROOT=(Resolve-Path '.').Path
& "$ROOT\.venv\Scripts\python.exe" -m ceegee tasks
& "$ROOT\.venv\Scripts\python.exe" -m ceegee validate-tif --family merit --file "实际下载的GeoTIFF完整路径"
& "$ROOT\.venv\Scripts\python.exe" -m ceegee submit-static --family merit --strip 1 --count 1 --strips 12
```

后一条命令会强制要求第1条实际完成、可查询EECU和本地10km GeoTIFF坐标对齐QC，且通过**估算留有2倍裕量、静态来源不超过250h**的费用闸门。可以后续递增`--strip 2`等命令。WorldCover 由于10m数据量大，建议更晚启动，先完整核对真实10m试验表。

## 全球12条带全部完成后的本地GF10指标连接

完成全部12条带的 Drive GeoTIFF 下载后，按族复制到 `data\downloads\merit` 或 `data\downloads\worldcover`，确保文件名维持 `full_merit_strip_00_of_12.tif` 到 `...11_of_12.tif`（同理 WorldCover）。执行：

```powershell
.\scripts\07_merge_downloads.ps1 -Family merit
.\scripts\07_merge_downloads.ps1 -Family worldcover
```

将严格核验 715 等价区域的完整GF10索引、EPSG6933 10km零原点、文件不重叠、全部1,395,471格正好出现一次、类别加总不大于有效覆盖分数；不自动填充缺测。输出 `data/derived/GF10_GEE_merit_20261103.parquet` 和 `...worldcover...parquet`，同目录 `.qc.json`。该步骤只支持GEE导出的完整100km² GF10值；沿海真正陆地裁剪仍须另行验证。

## 动态暴雨核验（此时只测试方法，不作为真实洪水事件）

```powershell
.\scripts\05_pilot_event_method.ps1
```

选取日期 `2023-06-01` 是演示处理时间维度的 **技术测试日期**，并不意味着这天测试网格实际发生了城市内涝。真正事件日期、暴雨窗口、前期降雨等需要在论文事件清单独立冻结后再批量导出。

## 输出与门禁

- `config/local_run.json`：Project ID、专用EE资产前缀、冻结GF10编号及10km仿射变换；**不含任何凭证或密钥**，也不应加入Git仓库。
- `reports/tasks.json`：只记录本次运行提交的EE任务，不跟踪其他项目任务。
- `reports/sources.json`：四类官方数据的实际band目录。
- `reports/pilot_cells.json`：全球分布16个严格GF10试验单元。
- `reports/pilot_qa.json`：与原生提取比较、分类守恒、精度闸门。
- `reports/local_tif_verified_merit.json`：下载图像的EPSG6933、10km像元尺寸和(0,0)网格锚点检查。
- `config/INDICATOR_CONTRACT.csv`：固定指标定义、时间戳、真实单位和论文声明限制。

**与本地最终静态成果合并**：下载的GeoTIFF以10km、EPSG6933、原点0的完整格网像元编码；必须使用被冻结的`grid_x/grid_y`，按GF10中心坐标读取对应像元，再与本地Parquet的`grid_id`一对一连接；未完成沿海分母修正和跨数据源数值审计前不标记 `publication_ready=true`。本包同时实现`validate-tif`单片空间检查与`merge-static`完整12条带的GeoTIFF→GF10 Parquet精确格网映射；不提前宣称所有事件数据和沿海陆地裁剪已经齐备。

## 研究标准与进一步迭代

实际生产前还需加上 **USGS GSHHG陆地掩膜、非南极陆地面积分母、WorldCover沿海原生像元抽样核验、IMERG缺半小时观测和跨时区局地暴雨窗口敏感性**。所有时序数据严格区分静态S、年度Y、逐日D、事件E。对2021–2023开发集，禁止把2025年的UCDB暴露指标直接视作2021年前可观测变量。事件后同年的累计气候指标不能作为前瞻预报变量。

## 官方数据参考

- https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
- https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- https://developers.google.com/earth-engine/guides/noncommercial_tiers
- https://developers.google.com/earth-engine/guides/monitoring_usage
- https://developers.google.com/earth-engine/guides/exporting_images
