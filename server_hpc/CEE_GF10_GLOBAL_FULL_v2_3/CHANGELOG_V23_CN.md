# CEE GF10 Global Full v2.3 — 2026-11-03

## 已定位的真实故障

上一次运行 `full_run_v22_20261103_230733.log`：715个GF10几何缓存完整；109个静态来源中108个全域来源已经在缓存中，唯一正在计算的 `grip-density/grip4_total_dens_m_km2.asc` 在 `ceeall/raster.py:72` 因 `src.crs is None` 失败。源文件是PBL/GLOBIO官方GRIP4的全球5角分ASCII Grid；GDAL的AAIGrid驱动依赖可选的同名`.prj`识别CRS。该异常与已暂存的GISD30、WorldClim、FileGDB、道路矢量没有关系。

## 已修复

1. 在 `ceeall/raster.py` 增加 `ensure_grip4_georeference(root,source,profile)`。只接受项目固定的官方全类型 GRIP4 密度路径，**严格要求** AAIGRID驱动、4320×2160、全球范围 `(-180,-90,180,90)`、5角分分辨率、单波段和有效的仿射变换。若本身具有WGS84经纬度坐标，则复用；若缺少CRS，才在已解压暂存目录创建 `grip4_total_dens_m_km2.prj`（WGS84/ESRI WKT1），不修改ASCII数值和原始ZIP。
2. 再次打开ASC，确认GDAL已经识别地理WGS84。**部分GDAL版本将其规范化显示为 `OGC:CRS84`，这是与EPSG:4326坐标等价、轴顺序不同的WGS84经纬度CRS，不是另一个投影**。代码使用`equals(ignore_axis_order=True)`而不是硬性要求`to_epsg()==4326`。
3. GRIP的已验证PRJ SHA-256保存在最终`run_qc.json`及 `reports\cee_full_v2\grip4_ascii_crs_audit_v23.json`，不修改原v2.2失败时写入的`job.json`任务指纹，因而可直接断点续跑。ASCII数值保持不变。统计仍按每源像元有效面积求密度空间均值（原生单位米/平方公里）；这**不**代表10km格网精确的道路中心线密度，后续GRIP4矢量还有独立的全球线段裁剪任务。
4. `ceeprod/vector_full.py:185` 改用 `shapely.transform(geom,to_ll.transform,interleaved=False)`，`tests/test_fullprod_science.py` 同步修改，消除此前三条Shapely弃用警告，同时保留原椭球长度统计方法，不通过全局忽略警告掩盖其他问题。
5. 补充GDAL原生AAIGrid（4320×2160模拟全球）端到端`.prj`读回测试、严格源路径/非GRIP拒绝测试及Shapely弃用告警回归测试。

## 验收与限制

本地制作环境41 passed、4 skipped（缺少PyArrow/ExactExtract，**用户服务器已有这两项，应全部运行**），0 warnings；另外实际以GDAL打开4320×2160合成AAIGrid证明补写PRJ后可识别为OGC:CRS84。不能在未访问服务器原始GRIP文件的情况下宣布其生产结果已通过。不要删除108个已完成源的715分区结果，也不要修改原始下载ZIP。

官网：
- https://www.globio.info/download-grip-dataset
- https://dataportaal.pbl.nl/GRIP4
- https://gdal.org/en/stable/drivers/raster/aaigrid.html
- https://shapely.readthedocs.io/en/latest/reference/shapely.transform.html
