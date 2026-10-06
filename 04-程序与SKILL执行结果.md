# 程序与 SKILL 执行结果

> **2026-09-27 复刻托盘的 3D 打印设计部分已搬到独立项目**：
> [`dev2/3d-man5/01-需求/epson-card-tray/`](/Users/derek.yin/dev2/3d-man5/01-需求/epson-card-tray/README.md)
> （代码在该仓库 `03-流水线/epson-card-tray/`，产物在 `~/db/3d/epson-card-tray/`）。
> 本文件下方记录的托架 STL/SCAD 是搬家前的早期概念版本，当前有效版本见新项目。
> 本项目继续只管喷墨打印那条链路（驱动、CUPS、`cardprint.py` 排版与坐标校准）。

已安装 [epson-pvc-print SKILL](/Users/derek.yin/.codex/skills/epson-pvc-print/SKILL.md) 和 [epson-card-front-print 正卡打印 SKILL](/Users/derek.yin/dev2/epson/skills/epson-card-front-print/SKILL.md)（仅正面、无翻卡；源码在本仓库，另装至 `~/.zcode/skills/` 与 `~/.codex/skills/`）。批量排版、逐盘正反面作业、仿射校准、托架参数生成及 STL 导出已实现；L8058 实机输出尚未验证。

| 交付 | 当前证据 |
|---|---|
| 正反面批量排版 | CSV 配对、数量展开、任意槽数、旋转、留白、完整保留或居中裁切；毫米尺寸 PDF |
| 逐盘作业 | 每次投递一面；实际出盘确认后再翻面；末盘空槽保持空白；记录任务 ID 和文件校验值 |
| 定位补偿 | 分面拟合二维仿射变换；支持既有补偿组合；校准后重新等待重复试印 |
| 打印通道 | 通用 CUPS 适配器已实现；绑定指定 Epson 队列、读取实时来源选项，关闭自动缩放和双面；目标机通道待接通 |
| 多卡托架 | 自动排布、SVG、槽位 JSON、OpenSCAD、STL 概念模型；当前保留区域内五卡有几何上界证明 |
| 验证 | 21 项测试通过；3 张编号样卡生成 2 盘、4 个单面 PDF，均已渲染检查正反配对、旋转、空槽和页面尺寸 |

## 五卡结论的适用范围

186×297 mm 托架，两侧各保留 30 mm、两端各保留 25 mm，中部矩形为 126×247 mm。54×86 mm 卡按每边 0.2 mm 槽隙、槽间 2 mm，可排四张竖卡加一张横卡。

限定卡片旋转 0/90 度且全部处于这个中部矩形，最多五张：一张横卡宽 86 mm，与另一张最窄 54 mm 卡相加超过 126 mm，因此横卡占用的纵向带内容不下其他卡；剩余竖卡最多两列。假设放六张，横卡数从 0 到 6，所需高度下界依次为 258、312、280、334、302、356、324 mm，均超过 247 mm。该上界放宽了间隙和公差，仍排不下六张；已有五卡构造包含实际槽隙。

这证明的是指定保留矩形内的几何数量，不是打印机最大可喷印数量。底面、侧边异形、识别特征和卡面高度尚未制造验证，SCAD/STL 为概念件。

## STL 与多卡程序检查

- STL：186×297×3 mm，712 个顶点、1420 个三角面，单个闭合实体；重新导入后尺寸、法向和体积检查通过。
- Bambu Studio 2.8.2.61 的命令行导入确认 manifold=yes、单个实体及上述尺寸；只做模型读取，未发送切片或打印任务。
- 托架布局、STL 和页面映射共用槽位编号。CAD 顶视坐标为 X=x、Y=297−深度，保持 CD 端朝上时的左右关系。
- 五槽程序以七张示例卡验证，分为 5＋2 两盘；四个单面 PDF 均已渲染核对正反配对、混合朝向及末盘空槽。
- 页面偏移 12、0 mm 和旋转 180 度是显式候选参数，尚未作为真实 L8058 定位值确认。

[STL 文件](/Users/derek.yin/db/epson-l8058/implementation/tray-cad/mesh/tray.stl) · [网格检查](/Users/derek.yin/db/epson-l8058/implementation/tray-cad/mesh/mesh-audit.json) · [Bambu 导入日志](/Users/derek.yin/db/epson-l8058/implementation/bambu-check/import-log.txt) · [七卡装卡顺序](/Users/derek.yin/db/epson-l8058/implementation/seven-card-job-validated/装卡顺序.html)

## 当前实机状态

本轮重新检查：Epson 本地队列 0、USB 相关记录 0、Bonjour Epson 服务 0。观察结果不能证明打印机不存在，仅说明本机当前未发现可用目标。[本轮连接检查](/Users/derek.yin/db/epson-l8058/implementation/connectivity-20260922-3/检查结果.md)。没有提交实际打印任务。

连续三个目标轮次均未发现目标机，当前等待设备接通。剩余验收为实际托架输出、喷印边界、正反定位和新托架进盘；现有软件测试不能替代这些验收。

需将打印机开机并通过 USB 连接本机，或使两者处于可互访的同一局域网。设备出现后，核对来源与页面选项、生成实际通道 profile、原盘定位试印，再验证矩形覆盖和多卡托架。用户已提供的尺寸与照片估算继续使用。

## 开源后端核查

本轮检查 [yibiao-h/gutenprint](https://github.com/yibiao-h/gutenprint/tree/96c80e3dc338ef95d863b47a7452c7b5941311ac) 与 [guten-rip-worker](https://github.com/yibiao-h/guten-rip-worker/tree/711f6685aeb064594188c39fd84843c99af2ec0e)。前者当前型号目录未列 L8050/L8058；历史提交涉及 L805 和 L18050，不能当作 L8058 托架实测证据。RIP 程序能接收栅格行并返回打印字节，但型号、送料及喷印边界仍需适配。源码记录保存在 backend-research 目录。

## 文件

- [正卡打印 SKILL（源码）](/Users/derek.yin/dev2/epson/skills/epson-card-front-print/SKILL.md)（[zcode 全局副本](/Users/derek.yin/.zcode/skills/epson-card-front-print/SKILL.md) · [codex 全局副本](/Users/derek.yin/.codex/skills/epson-card-front-print/SKILL.md)）：CSV 只需正面图，逐盘提交仅正面；2026-10-06 建，14 项测试通过，样卡 3 张生成 2 盘单面 PDF 已核
- [SKILL](/Users/derek.yin/.codex/skills/epson-pvc-print/SKILL.md)
- [可分发技能包](/Users/derek.yin/db/epson-l8058/implementation/epson-pvc-print.zip)
- [示例装卡顺序](/Users/derek.yin/db/epson-l8058/implementation/demo-job/装卡顺序.html)
- [五卡槽位与证明](/Users/derek.yin/db/epson-l8058/implementation/tray-cad/layout.json)
- [五卡 OpenSCAD 概念模型](/Users/derek.yin/db/epson-l8058/implementation/tray-cad/tray.scad)
- [测试记录](/Users/derek.yin/db/epson-l8058/implementation/test-results.txt)

完整目标仍包括：用户图片的实机批量正反打印、可用的多卡托架和最终 SKILL。软件离线检查完成，整体目标保持进行中。
