# v2.2 修复清单（2026-11-03）

**本版在用户提供的真实服务器日志基础上修复；不修改已有 `data/derived` 统计结果。**

## 真实日志定位

1. **BasinATLAS / RiverATLAS 文件夹嵌套**：下载文件名 `BasinATLAS_Data_v10.gdb.zip` 对应的解压容器是 `.../BasinATLAS_Data_v10.gdb/`，真正 FileGDB 位于 `.../BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb/`。RiverATLAS 同理。此前 `ceeprod.discover._file_sources` 把所有后缀 `.gdb` 的目录都视为可读取 FileGDB，因此先访问了不可读的容器，返回 `Permission denied`，导致本地自动生产停止。
2. **UCDB 六个主题**：官方 GHS-UCDB R2024A 包含 `THEME_CLIMATE / EMISSIONS / EXPOSURE / GENERAL_CHARACTERISTICS / GEOGRAPHY / GHSL` 等多个主题。它们用于不同变量，不是可任选其一的重复图层。原脚本只按有无城市ID和图层名打分，分数相同即当成错误，错过了所有后续统计。

## v2.2 具体变更

- `ceeprod/discover.py`：现在只把直接包含 `*.gdbtable` 的目录认定为真正 FileGDB；排除上层同名 `.gdb` ZIP容器。递归保留真正的 `BasinATLAS_v10.gdb / RiverATLAS_v10.gdb / GRIP4_GlobalRoads.gdb`；只在真实可读取图层中选择。默认使用 BasinATLAS Level 07 作为**区域流域背景**，原始级别另行保留为可用来源，不能混称格网汇流面积。
- UCDB：GF10空间crosswalk优先正式 `GHS_UCDB_GLOBE` 面图层，若仅有主题下载包，则明确选择 `THEME_GEOGRAPHY` 面图层，不再将 `THEME_CLIMATE/EMISSIONS/...` 互相竞争为唯一图层。`discover_ucdb_themes()`保留所有实际可读取的主题图层及ID。
- `ceeprod/source_attributes.py`：UCDB全部本地主题**分别**按官方ID输出到 `data/derived/cee_all_global_v2/native_attributes/ucdb/themes/*`，保留原始列、年份和缺失值。根目录QC记录所有主题，防止只读一个主题就宣称UCDB全部完成。不同ID域不擅自混用。
- `ceeprod/shared.py`：给FileGDB目录新增递归文件清单摘要；文件GDB内部文件变化后，任务指纹不会仅因父目录元数据未变而错误复用旧结果。
- 新增 `python -m ceeprod --root E:\WJH_CEE verify-providers` 和 `scripts/06_validate_provider_sources.ps1`：**只读**检查6类矢量的来源实际路径、图层、原生ID、UCDB所有主题；要求无错误才能继续。
- `scripts/07_resume_after_provider_fix.ps1`：从源码验收、来源预检查到全球断点生产一条命令完成；不包含5000格限制。
- 新增 6 项回归测试（含真实OpenFileGDB驱动往返测试）：双层 GDB 目录、FileGDB驱动真实目标路径、六主题并列UCDB优先GEOGRAPHY、全部UCDB主题属性分发、FileGDB内部数据变更导致来源指纹失效、无稳定ID时明确拒绝错误自动连接。

## 真实性和论文边界

- v2.2 是**完整离线程序包**，包含原来所有 raster、ERA5-EX、GISD30、GMTED、WorldClim、GRIP道路、RiverATLAS、BasinATLAS、UCDB、Groundsource、GF10宽表、日志和测试模块，非仅一个GDB补丁。
- 预检查和代码测试通过不等于700多个真实全球分区运行结束；服务器上的真实GDB尚未在当前环境直接运行。实际处理仍须严格QC、空间交叠物理定义、原始单位和陆地裁剪验证。
- 必须保留 `E:\WJH_CEE\data\derived\` 已完成数据，不要删除已解压的GISD30、WorldClim或已完成的GHSL/GMTED结果，也不要让旧版v2.1与新版v2.2同时运行。

官方来源：[Pyogrio的 `list_layers` 支持真实FileGDB和多图层](https://pyogrio.readthedocs.io/en/latest/api.html)、[UCDB R2024A的多主题产品说明](https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php)、[HydroATLAS官方归档](https://doi.org/10.6084/m9.figshare.9890531)。
