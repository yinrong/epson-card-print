---
name: epson-card-front-print
description: Epson L8058 PVC 正卡打印——只打印卡片正面的批量排版与逐盘提交；CSV 只需正面图，无翻卡流程；适用于单面卡与双面流程的第一面实机验证。正反双面流程用 epson-pvc-print。
---

# 正卡打印（仅卡片正面）

用 `scripts/run.sh` 运行程序。输入 CSV 只需绑定正面图；输出按盘拆分的毫米尺寸单面 PDF、装卡表和可恢复作业记录。每盘流程：装卡 → 提交正面 → 确认实际出盘 → 下一盘；不翻卡、不打印背面。实际托架打印通道尚待 L8058 实机验证，不把 PDF 生成成功作为打印成功。

源码事实源在本仓库 `skills/epson-card-front-print/`；`~/.zcode/skills/` 与 `~/.codex/skills/` 下的同名目录是部署副本。

## 使用

相对路径以本技能目录为基准；CSV 图片相对路径以 CSV 所在目录为基准。

```bash
bash scripts/setup.sh
bash scripts/run.sh prepare --profile profiles/l8058-stock-provisional.json --cards /path/cards.csv --output /path/job
bash scripts/run.sh prepare --profile profiles/l8058-stock-provisional.json --calibration --output /path/calibration
bash scripts/run.sh step --job /path/job --queue VERIFIED_EPSON_QUEUE
```

CSV 表头为 `id,front,quantity`（存在 `back` 列则忽略）。每行 ID 唯一；quantity 默认为 1。支持 Pillow 可读取的栅格图片。默认 contain 保留完整画面；`--fit cover` 居中裁切，`--fit exact` 1:1 加出血。输出目录必须新建。默认 300 dpi，可用 150/600。

## 逐盘作业

`step` 默认显示单面提交命令；显式执行（`--execute --tray-loaded`）只投递当前一盘的正面，始终关闭自动双面、拼页和缩放。打印机出盘后 `step --confirm-output` 确认实物完成，再装下一盘。CUPS 接收任务不能代替实物确认。严禁把全部 PDF 作为一个多页任务提交给手动托盘。

样例图：`python scripts/make_demo.py --output /new/demo`（三张编号样卡，生成 2 盘单面 PDF）。

## 校准

校准只针对正面。每盘记录至少四个、跨槽分布的坐标点（mm，左上原点，右 x 下 y，`expected_mm`/`observed_mm` 成对），然后：

```bash
bash scripts/run.sh calibrate --profile /path/profile.json --samples /path/points.json --output /path/profile-front.json
```

最小二乘拟合二维仿射偏差并组合既有补偿；残差超过 0.5 mm 报错（数据一致性检查，不是验收公差）。每次计算后 `production_verified` 重新置 false，重复试印合格前不得用于生产提交。校准图（`prepare --calibration`）在卡区内画边框、十字与方向箭头，用于原盘试印定位。

## 配置与设备

- profile 与 epson-pvc-print 同一格式（字段定义与证据口径见该技能 `references/profile.md`）；`back_slot_map`、`back_rotation`、背面 transform 在本技能中不参与输出，仅为格式兼容保留。
- 原配 profile 是待校准候选（来自 L8050 驱动静态资料），不是 L8058 已验证坐标。用户已确认原托架用 0.76 mm 卡成功打印；卡材采用该规格。
- `production_verified` 只能依据实际作业、重复定位与样卡记录填写，不能为解除程序限制而设 true。
- 提交前的安全门（队列选项白名单、Epson 型号识别、托架来源选项校验、`submission_uncertain` 不自动重发）与 epson-pvc-print 相同。
- 先运行 `scripts/probe_printer.py --output-dir /new/diagnostics` 查当前连接状态，不能根据历史离线记录断言现在也离线。

## 依赖与检查

`setup.sh` 在 `~/.cache/epson-card-front-print/venv` 安装 `requirements-tested.txt` 固定版本依赖，保持系统 Python 独立；`run.sh` 依次尝试 `EPSON_CARD_FRONT_PYTHON`、该 venv、Codex runtime、系统 python3。测试：`~/.cache/epson-card-front-print/venv/bin/python -m unittest discover -s tests -v`。PDF 可用 `pdftoppm -scale-to 1200 -png -singlefile INPUT.pdf OUTPUT` 渲染检查。

颜色按 RGB 图片输出，由实际打印通道处理；未实现打印机 ICC 色彩校准，尺寸标定与颜色标定分别验收。
