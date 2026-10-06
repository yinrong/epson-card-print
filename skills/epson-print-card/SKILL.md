---
name: epson-print-card
description: Epson L8058 证卡（PVC 卡）组批打印程序——目录正面图＋共享背面图，2 卡托盘×N 盘分组，正/背面之间设墨水干燥门控；epson-pvc-print 的证卡链路也调用本程序。通用 CSV 双面批量排版仍用 epson-pvc-print。
---

# 证卡组批打印（epson-print-card）

核心命令（全局 PATH 直接可用；源码事实源在本仓库 `skills/epson-print-card/`，`~/.zcode/skills/` 与 `~/.codex/skills/` 下是部署副本）：

```bash
epson-print-card prepare --front-dir {dir} --back-img {path} --group 2x5 \
  --profile ~/.codex/skills/epson-print-card/profiles/l8058-stock-provisional.json --output /new/job
epson-print-card step --job /new/job --queue VERIFIED_EPSON_QUEUE
```

`--group 2x5` 含义：每托盘 2 张卡（原配双卡托盘，槽数不能变，程序强制校验），每批 5 个托盘＝10 张卡。批次流程：装满 5 盘 → 逐盘打印正面（每盘确认出盘）→ 整批干燥（`--confirm-dry`）→ 按背面槽位翻卡装回 → 逐盘打印背面 → 再次干燥（`--confirm-dry`）→ 换下一批卡。

输入：`--front-dir` 目录内每张图片是一张卡的正面（卡号＝去扩展名文件名，按文件名排序，png/jpg/jpeg/tif/bmp/webp）；`--back-img` 是全部卡共用的背面图。末批不满 10 张时空槽留白。

## 作业推进（step）

- `step --job DIR --queue NAME`：显示当前这一盘一面的提交命令（预览，不动打印机）。
- 确认装好该盘后 `--execute --tray-loaded` 才真投递；始终关闭自动双面、拼页和缩放。
- 打印机出盘后 `--confirm-output` 确认实物完成，才推进到下一盘。
- 每批正面（或背面）全部确认后到达**干燥门**：`step` 显示 waiting:drying；油墨干燥后 `--confirm-dry` 放行。干燥门前 `--confirm-output`/`--confirm-dry` 混用会报错。
- 全部批次完成打印并干燥后，`step` 报 `All groups printed and dried`。
- CUPS 接收任务不能代替实物确认；`submission_uncertain` 状态不自动重发，先查打印机再 confirm。

## 校准

`prepare --calibration`（免 `--front-dir/--back-img`）生成单盘正反尺规图（边框、十字、方向箭头）；打印后实测坐标点（mm、左上原点、`expected_mm`/`observed_mm` 成对、跨两槽至少 4 点），再：

```bash
epson-print-card calibrate --profile P --samples points.json --output P-front.json
```

最小二乘拟合正面仿射补偿并与既有补偿组合；残差超 0.5 mm 报错（数据一致性检查，非验收公差）。校准后 `production_verified` 重置为 false，重复试印合格前不得生产提交。

## 配置与设备

- profile 与 epson-pvc-print 同一格式（字段定义与证据口径见该技能 `references/profile.md`）；本程序强制 profile 槽数＝`--group` 每盘卡数（2）。
- 原配 profile 是待校准候选（L8050 驱动静态资料推算），不是 L8058 已验证坐标；用户已确认原托架用 0.76 mm 卡成功打印。
- 提交安全门（队列选项白名单、Epson 型号识别、托架来源选项、profile 队列绑定）与 epson-pvc-print 同口径；`production_verified` 只能凭实际作业证据填写。
- 先跑 `scripts/probe_printer.py --output-dir /new/diagnostics` 查当前连接状态，不能按历史离线记录断言现在也离线。
- L8058 实机输出尚未验证：PDF 生成成功不等于打印成功。

## 依赖与检查

`setup.sh` 在 `~/.cache/epson-print-card/venv` 装固定版本依赖（Pillow/reportlab/numpy/pypdf），保持系统 Python 独立；`epson-print-card` 命令封装依次尝试 `EPSON_PRINT_CARD_PYTHON`、该 venv、Codex runtime、系统 python3。测试：`~/.cache/epson-print-card/venv/bin/python -m unittest discover -s tests -v`。样例图：`python scripts/make_demo.py --output /new/demo`（3 正面＋1 共享背面）。颜色按 RGB 输出，未做打印机 ICC 校准。
