# epson-card-print

Epson L8050/L8058 系列打印机、原装光盘/证卡托盘，PVC 证卡正反面批量打印的命令行工具。
纯 Python + CUPS，不依赖任何 AI/Agent，人直接在终端跑就行。

托盘只能一次放 2 张卡（一面），程序按 CSV 把任意数量的正反面图片排版成毫米级
PDF，逐盘、逐面提交给 CUPS 队列，每次投递后需要人工确认实际出纸再继续下一面——
这不是自动化连续出片，是"每一步都有人在场确认"的半自动工具，设计上就没有
"发了就不管"的模式。

## 依赖

```bash
bash scripts/setup.sh          # 建 venv、装依赖到 ./venv
```

或者自己管理环境：`pip install -r requirements.txt`（`requirements-tested.txt`
是锁定过版本号、`pytest` 通过的组合，环境有问题时对照这份排查）。

## 打印机端准备（一次性）

1. 装 Epson 官方 L8050 系列驱动（打印机在官网下载页选对应型号）。
2. 建一个绑定该驱动 PPD 的 CUPS 队列，例如：
   ```bash
   lpadmin -p EPSON_L8058 -E -v socket://<打印机IP>:9100 \
     -P "/Library/Printers/PPDs/Contents/Resources/EPSON L8050 Series.gz"
   ```
3. `profiles/` 下的 JSON 是"页面坐标 → 托盘卡槽"的映射档案，`cups_options` 字段
   要跟你自己 CUPS 队列实际支持的选项对上（用 `lpoptions -p <队列名> -l` 查）。
   直接照抄别人机器上跑通的 profile 大概率对不上，需要按下面「校准」重新走一遍。

## 使用

CSV 表头固定为 `id,front,back,quantity`（`quantity` 缺省为 1），路径相对 CSV
所在目录。

```bash
# 1. 排版：把 CSV 里的正反面图片切成按托盘容量分好盘的毫米 PDF
bash scripts/run.sh prepare --profile profiles/l8058-tray-portrait.json \
  --cards cards.csv --output job/ --dpi 600 --fit exact

# 2. 逐盘逐面投递：每次只发一面，打印机吐出来后人工确认再继续下一面
bash scripts/run.sh step --job job/ --queue EPSON_L8058 --execute --tray-loaded
# 确认这一面已经正确打印出来后：
bash scripts/run.sh step --job job/ --confirm-output
# 重复 step 直到 "All sides manually confirmed"
```

`--fit`：`contain` 完整保留图片（可能留白）、`cover` 居中裁切、`exact` 按卡片
标称尺寸 1:1 放置、四周出血向外延伸（配合 `profile.bleed_mm`，见
[references/profile.md](references/profile.md)）。

### 校准定位偏移

托盘物理位置和驱动页面坐标的对应关系，不同打印机/托盘会有几毫米出入。用一张
带毫米刻度尺的校准页量出实际偏移，再喂给程序算出修正矩阵：

```bash
bash scripts/run.sh prepare --profile profiles/l8058-tray-portrait.json \
  --calibration --output calib/
# 打印 calib/batch-0001-front.pdf，量出实测坐标，写成 samples.json：
# [{"expected_mm":[x,y],"observed_mm":[x,y]}, ...]（至少 4 点，覆盖两个槽位）
bash scripts/run.sh calibrate --profile profiles/l8058-tray-portrait.json \
  --samples samples.json --side front --output profiles/my-profile.json
```

### 量托盘可喷印范围

`scripts/area_grid.py` 生成整页毫米网格（每格标坐标），贴一张白纸在托盘上打这
一页，就能直接读出打印机在托盘上实际能喷到的矩形范围：

```bash
python3 scripts/area_grid.py --output grid.pdf
```

### 只读探测打印机连通性

`scripts/probe_printer.py` 检查本机打印队列、USB、Bonjour 服务里能不能发现
目标打印机，不提交任何打印任务：

```bash
python3 scripts/probe_printer.py --output-dir diagnostics/
```

## 测试

```bash
bash scripts/setup.sh
venv/bin/python -m pytest tests/ -v
```

## profile 字段说明

见 [references/profile.md](references/profile.md)（各字段含义、坐标系定义、
校准证据字段）与 [references/workflow.md](references/workflow.md)（逐盘作业
的完整流程和安全约束：为什么每次只发一面、为什么不能把全部正反 PDF 当一个
多页任务提交）。

## 安全设计说明

`cardprint.py step --execute` 在真正调用 `lp` 提交任务前会做一串检查（详见
`command()`/`step()`）：拒绝改队列名却复用旧标定、拒绝没有 `transport_verified`
的托盘 profile、拒绝跳过前一面确认就投递下一面、CUPS 选项名/值只接受
`[A-Za-z0-9_.-]` 白名单防注入。这些检查不是可选项，是这个工具唯一的"安全带"——
它假设操作者会犯错、会手滑，但不假设操作者会主动绕过检查。
