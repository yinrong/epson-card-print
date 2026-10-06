---
name: epson-print-card
description: Epson L8058 证卡（PVC 卡）组批打印程序——目录正面图＋共享背面图，2 卡托盘×N 盘分组，正/背面之间设墨水干燥门控；规格内建（86×54 卡、双卡托架），无需 profile 参数；epson-pvc-print 的证卡链路也调用本程序。
---

# 证卡组批打印（epson-print-card）

核心命令（全局 PATH 直接可用；源码事实源在本仓库 `skills/epson-print-card/`，`~/.zcode/skills/` 与 `~/.codex/skills/` 下是部署副本）：

```bash
epson-print-card prepare --front-dir {dir} --back-img {path} --group 2x5 --output /new/job
epson-print-card step --job /new/job --queue VERIFIED_EPSON_QUEUE
```

`--group 2x5` 含义：每托盘 2 张卡（原配双卡托盘，槽数不能变，程序强制校验），每批 5 个托盘＝10 张卡。批次流程：装满 5 盘 → 逐盘打印正面（每盘确认出盘）→ 整批干燥（`--confirm-dry`）→ 按背面槽位翻卡装回 → 逐盘打印背面 → 再次干燥（`--confirm-dry`）→ 换下一批卡。

输入：`--front-dir` 目录内每张图片是一张卡的正面（卡号＝去扩展名文件名，按文件名排序，png/jpg/jpeg/tif/bmp/webp）；`--back-img` 是全部卡共用的背面图。末批不满 10 张时空槽留白。

## 规格与坐标（内建，无参数）

本目录 PVC 证卡只有一种规格：86×54 mm、原配双卡托架。卡槽页面坐标、安全边距等已内建在程序里（初值由 L8050 驱动静态资料推算）。实机校准结果存在 `~/.config/epson-print-card/profile.json`（环境变量 `EPSON_PRINT_CARD_CONFIG_DIR` 可重定向），存在即优先生效，不存在就用内建值——日常使用不需要管这个文件。

## A4 拼版打印（sheet）

把一个目录的所有图片拼成 A4、0 间距网格，整册一个多页 PDF 一次提交（普通纸，不走托盘流程）：

```bash
epson-print-card sheet --front-dir {dir} --queue NAME [--columns N] [--execute] --output /new/dir
```

列数默认自动：按图片宽高比选格比最贴合的网格（比例优先、格子大者优先、页数少者优先）；格间距与页边距均为 0。`--queue` 给出即显示提交命令，`--execute` 真投递（队列需存在、启用、识别为 Epson；显式 `EPIJ_Size=1`＝A4）。例：75 张 1276×2031 竖版图 → 9 列×8 行、2 页（72+3）。

## 作业推进（step）

- `step --job DIR --queue NAME`：显示当前这一盘一面的提交命令（预览，不动打印机）。
- 确认装好该盘后 `--execute --tray-loaded` 才真投递；始终关闭自动双面、拼页和缩放。
- 打印机出盘后 `--confirm-output` 确认实物完成，才推进到下一盘。
- 每批正面（或背面）全部确认后到达**干燥门**：`step` 显示 waiting:drying；油墨干燥后 `--confirm-dry` 放行。干燥门前 `--confirm-output`/`--confirm-dry` 混用会报错。
- 全部批次完成打印并干燥后，`step` 报 `All groups printed and dried`。
- CUPS 接收任务不能代替实物确认；`submission_uncertain` 状态不自动重发，先查打印机再 confirm。

## 校准（可选）

`prepare --calibration`（免 `--front-dir/--back-img`）生成单盘正反尺规图（边框、十字、方向箭头）；打印后实测坐标点（mm、左上原点、`expected_mm`/`observed_mm` 成对、跨两槽至少 4 点）：

```bash
epson-print-card calibrate --samples points.json   # 就地更新活动校准文件
epson-print-card calibrate --reset                 # 恢复内建规格
```

最小二乘拟合正面仿射补偿并与既有补偿组合；残差超 0.5 mm 报错（数据一致性检查，非验收公差）。校准后 `production_verified` 重置为 false，重复试印合格前不得生产提交。

## 实机状态与安全门

- Derek 2026-10-06 报告：托盘复刻件已完成 3D 打印（`--group 2x5` 的 5 盘硬件就位），且最后一次证卡打印成功（原配托架链路）。本程序输出 PDF 的坐标与该次实印的对应关系尚未比对，`production_verified` 仍为 false。
- 提交安全门（队列选项白名单、Epson 型号识别、托盘来源选项、队列绑定）与 epson-pvc-print 同口径；`production_verified` 只能凭实际作业证据填写。
- 先跑 `scripts/probe_printer.py --output-dir /new/diagnostics` 查当前连接状态，不能按历史离线记录断言现在也离线。

## 依赖与检查

`setup.sh` 在 `~/.cache/epson-print-card/venv` 装固定版本依赖（Pillow/reportlab/numpy/pypdf），保持系统 Python 独立；`epson-print-card` 命令封装依次尝试 `EPSON_PRINT_CARD_PYTHON`、该 venv、Codex runtime、系统 python3。测试：`~/.cache/epson-print-card/venv/bin/python -m unittest discover -s tests -v`。样例图：`python scripts/make_demo.py --output /new/demo`（3 正面＋1 共享背面）。颜色按 RGB 输出，未做打印机 ICC 校准。
