# CEE GF10全球正式生产 v8：MERIT Hydro 16指标 + IMERG V07/ERA5-Land事件暴露

**版本**：2026-11-06，独立代码包，目标仓库 `WuJH123/GEE_flooding`，**目标期刊：Communications Earth & Environment**。不修改/覆盖v3–v7历史任务、已有GeoTIFF、源Parquet或费用账本。本代码在GitHub本地/CI中测试，不代表已经通过真实全球GEE运行；所有云任务在用户有授权的Windows电脑上启动。

## 1. 冻结的源数据与科学定义

- 全陆地非南极GF10：1,395,471格，EPSG:6933，10km，源Parquet SHA-256 `4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d`，**只有GF10具有正陆地面积**，沿海统计有`land_area_km2`，不拿整格100km²当陆地面积。
- V6 MERIT：40→80km缓冲计算在3地区×16波段收敛；v7新增5块，原v6和v7共有863格科学验收，不复算。MERIT 16波段名称冻结于`cee_v8/core.py`。正式计划还要为每个安全块生成不可变的`land_ids`列表，逐格核对真实GF10陆地成员；沿海导出矩形内即使海水像元有有限值，也不能写入陆地宽表。v4安全块共16,860；14个反子午线接缝父块的450格继续独立QC，不能算已完成全球指标。
- V7 Figure1报道日期：80,456原始UUID→43,694个城市报道格网日；152,889未标记候选日期，196,496唯一GF10×UTC**代理**日期；141,917个v7旧date×tile请求**不允许批量提交**；3个真实天气GEE任务/46格日已经验收，原CSV SHA与GEE task账本必须真实存在才复用。
- IMERG V07 `status=permanent`，日48半小时；前7日336、前14日672、前30日1440；48个日内半小时构成43个连续3h窗口，单位为mm/h乘0.5h，降水深度mm。目标日期2021–2023，前30日需保留相应前期窗口。2025-09-30以后的数据不能混入本论文冻结的V07 permanent基线。
- ERA5-Land DAILY_AGGR：病例**前一个完整UTC日**的两层土壤含水量、2m温度、降水、地表径流、风速分量及风速；温度K转°C、降水m转mm。缺测保留为NaN，不能补零。原始气象分辨率约0.1°/11km，GF10表示采样单元，不代表气象源变成原生10km实测值。
- 来源日期=`SOURCE_LOCAL_CALENDAR_DAY_AS_UTC_PROXY`，不是核验的准确UTC时刻。候选日=`unlabeled_calendar_candidate`，**不是确定无洪水**。D−1/D+1独立气象敏感性默认纳入v8计划。独立洪水实测和两个审阅者的新闻原文核验仍需单独证据。

## 2. 正式生产与此前的决定性区别

| v7瓶颈 | v8策略 |
| --- | --- |
| 141,917个小气象任务 | 按固定日期窗口+最多260行/批分组（默认4日期），自动计算真实宏任务数；保留全部GF10×日期原始键 |
| 担心宏任务计算图不等价 | 用原v7通过的46条数据组成**一个真实GEE跨日期合批canary**，逐列数值/掩膜比较；不通过则阻止全量展开 |
| MERIT只能手动一块块跑 | 同一已验收v3计算图、v6 80km缓冲与v4安全格网清单，程序自动选择全部未运行块并逐块QC |
| 任务id丢失或Drive迟到重复提交 | SQLite事务状态机：先记录task.id再start；上传后保存operation；终态SUCCEEDED与下载后精确QC均通过才标ACCEPTED |
| 需要手动下载所有结果 | 支持Drive API ADC或者预配置GCS bucket的自动落盘；GCS会产生Google Cloud存储费用，请自行审查和配置 |
| 批任务失败 | 天气批次自动日期/空间二分，最多6层；MERIT及单行系统错误进入隔离，不能假报完成 |
| 额度未知 | 必须以Cloud Monitoring当前整项目月EECU起点设`--month-used-eecu`，默认保守上限900 EECU，预留余量；平台官方非商业项目分150/1000/100000三层，**以实际账户层级为准** |
| 反子午线14块未解 | 生成450格真实GF10隔离审计，按独立源像元与split-geography核对；没有通过独立科学验证，不允许释放`GLOBAL_COMPLETE` |

默认日期分组是**先检查来源恒等性，再按4天内且最多260格日构造稀疏格网FeatureCollection**；每个实际格网分别按约11km源尺度计算统计，不在全球高分辨率投影上创建一幅巨图。宏批次试验成功以前，不声称节省幅度或成本。若某批出现内存、投影或掩膜失败，将保留原失败任务并拆分，不进行自动科学阈值放宽。最初的3日期/46行宏任务若失败，也会自动拆为日期子任务，并逐行对照v7原数值；全部对照通过才放行正式批次。跨反子午线的天气格网采用EPSG:6933周期经度的有界两侧多边形，不能用整幅全球重投影；此项仍需开展专项地理一致性审计。

## 3. 在Windows部署（PowerShell）

假设下载的zip位于`E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106.zip`，以下命令没有用户待填的源数据路径：

```powershell
$ROOT='E:\GEE_flooding'
$PKG="$ROOT\CEE_GF10_GLOBAL_EE_V8_20261106"
$PY="$ROOT\.venv\Scripts\python.exe"
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GLOBAL_EE_V8_20261106.zip" -DestinationPath $ROOT
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force
& $PY -m pip install -r "$PKG\requirements.txt"
$env:PYTHONPATH="$PKG;$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
& $PY -m pytest "$PKG\tests" -q -W error
& $PY -m cee_v8 --root $ROOT --pkg $PKG prepare
& $PY -m cee_v8 --root $ROOT --pkg $PKG register
& $PY -m cee_v8 --root $ROOT --pkg $PKG status
```

`prepare`冻结来源、发现已经验收的旧GEE CSV、为源日期+/-1天自动加入敏感性日期并做GF10守恒；自动写`plans/weather_batches.csv`、`plans/merit_batches.csv`、`plans/merit_quarantine.csv`。已有v8 plan不被覆盖。`register`生成可重启SQLite任务账本，重复调用不会重复插入任务。

## 4. 一次启动整个正式生产（选择已具备认证的一种导出）

**推荐完全自动的GCS**（先由用户/管理员创建一个具备Earth Engine写权限、客户端读取权限的**已有**Cloud Storage bucket；Cloud Storage本身可能产生费用，代码不创建云收费资源）：

```powershell
# 设置你的已经存在、且已通过授权的bucket。不是GEE新资产项目。
$BUCKET = '<已有且已授权的GCS-bucket-name>'
# 此数值必须依据GEE Cloud Monitoring项目本月已消费总EECU填写，例如仅作命令结构演示3.5，绝不能把3.5当作实时值。
$USED = <CloudMonitoring查询所得本月项目EECU小时数>
& $PY -m cee_v8 --root $ROOT --pkg $PKG run `
  --storage gcs --bucket $BUCKET `
  --max-inflight 4 --max-unaccepted 20 `
  --month-used-eecu $USED --budget-limit-eecu 900 `
  --poll-seconds 90 `
  --execute --confirm CEE_GF10_GLOBAL_EE_V8_20261106
```

**Google Drive自动下载**：如果Windows电脑已有具备`drive.readonly`范围的应用默认凭据（ADC），可省去GCS额外费用：

```powershell
# 先用Google Cloud SDK的ADC认证，并确保该ADC拥有Drive readonly范围；
# 若此账号不具备Drive授权，程序在云任务提交前停止。
# $USED须从Cloud Monitoring读取本项目本月EECU小时数。
& $PY -m cee_v8 --root $ROOT --pkg $PKG run `
  --storage drive --max-inflight 4 --max-unaccepted 20 `
  --month-used-eecu $USED --budget-limit-eecu 900 `
  --poll-seconds 90 `
  --execute --confirm CEE_GF10_GLOBAL_EE_V8_20261106
```

**注意**：GCS bucket和Cloud Monitoring真实用量不是本地Parquet提供的信息，无法由代码自动猜出或代替用户授权。此版本会先检查认证，再开始收费或消费额度的EE批处理，避免任务完成后无法自动下载。若因网络中断退出，重新执行同一条`run`，数据库将恢复现有任务，不自动重复提交`INTENT`/已验收项。

在不打算长时间保持PowerShell窗口的远程服务器上，可以由Codex建立Windows任务计划程序调用相同命令运行；这属于**用户电脑执行**，不是ChatGPT在后台运行。

## 5. 运行与最终完整性检查

```powershell
& $PY -m cee_v8 --root $ROOT --pkg $PKG status
# 只读生成450格反子午线科学诊断，保留隔离状态：
& $PY -m cee_v8 --root $ROOT --pkg $PKG seam-diagnostic
# 允许看当前局部成果：
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-weather --allow-partial
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-merit --allow-partial
# 只有全部格日GEE验收后，气象最终表才能不加allow-partial：
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-weather
# 只有安全块+经过独立验证的450个接缝格均完整后：
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-merit
```

最终目录（不可覆盖）：
`data/GF10_IMERG_ERA5_LAND_EVENT_EXPOSURES.parquet`、`data/GF10_MERIT_HYDRO_16_BANDS.parquet`、对应`.qc.json`、每项下载的原CSV/GeoTIFF和`.qc.json`、`reports/v8_production.sqlite`。

**全球完成标准**：MERIT每个矩形必须只合并原冻结`land_ids`对应的陆地像元，海洋像元不得计入，也不得用海洋像元代替缺测陆地。气象所有冻结原始与D±1敏感性格日都唯一、可追溯，IMERG观测计数真实，ERA5缺测保留；MERIT 1,395,471唯一GF10均有科学验收16个字段（接缝450格独立核查）；所有任务有真实GEE终态、源Hash与EECU。仅有任务`SUCCEEDED`而没有下载/文件QC不得计为完成。即使两项完成，也不等于城市内涝的真实物理独立验证完成。

## 6. 真实来源（需按论文Data Availability引用）

- EE官方配额：https://developers.google.com/earth-engine/guides/usage
- 非商业层级：https://developers.google.com/earth-engine/guides/noncommercial_tiers
- EE计算最佳实践：https://developers.google.com/earth-engine/guides/best_practices
- MERIT Hydro：https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1 （注意CC-BY-NC/ODbL许可与Yamazaki原论文引用）
- IMERG V07：https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5-Land DAILY_AGGR：https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR
- GCS表导出：https://developers.google.com/earth-engine/apidocs/export-table-tocloudstorage

## 7. 当前严格未完成事项

截至v8源代码生成时，本对话的执行环境**没有你的Earth Engine项目凭据、真实196,496行v7 Parquet、GCS bucket或有权限的Drive ADC**，因此不能提交全球真实任务，也不能给出真实的v8任务次数/EECU/全部通过结论。代码执行前的GitHub测试只证明回归逻辑。14个接缝块的严格科学等价性未解决；`seam-diagnostic`是可审核的输入清单而不是最终通过结果。当地逐日P95、独立风暴ID、两个审阅者核验与外部物理洪涝数据也都不是GEE统计能自动补造的。对这些事项Codex需按照`docs/CODEX_FULL_RUN_PROMPT_CN.md`完成实际工作，不得以论文发表标准不足时虚报成果。
