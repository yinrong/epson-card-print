# 作业与校准

## 逐盘作业

1. 检查 PDF、装卡表、目标队列和实物介质。`step --job DIR --queue NAME` 只预览命令。
2. 已校验 profile、已装本面卡后，使用 `step --job DIR --queue NAME --execute --tray-loaded`。只提交当前一面，始终关闭自动双面、拼页和缩放。
3. 打印机出盘后确认该面实际完成：`step --job DIR --confirm-output`。CUPS 接收任务不能代替实物确认。
4. 正面完成后按装卡表翻卡、保持托盘进机方向；再次 execute 提交背面。背面确认后进入下一盘。

作业文件和 manifest 具有 SHA256 校验，状态更新加文件锁。网络异常或提交超时保留 `submission_uncertain`，不会自动重发。先检查打印机与队列；实际已输出可 confirm-output。确认未输出而需重做时，新建只含未完成卡的作业，并记录旧任务处理结果；勿清空状态盲目重发。

最后一盘空槽不会生成图片。正反始终来自同一 CSV 行及份数序号；若背面换槽，空槽也随映射移动。人工更换卡片顺序后必须重新生成装卡表。

## 校准

先验证托架送料、介质选项和实际队列。校准图只在候选卡区内画边框、五个十字和上方向箭头；在原托架、合适的试印介质上进行。页面尺寸与图形位置未获验证前，校准图不宣称能准确落入实物卡槽。

profile 的 transport_verified=true 表示已取得“这个队列和选项确实使用托架”的证据。production_verified=true 还要求正反面重复试印、卡片身份和方向匹配、位置误差满足约定。verification_evidence 填具体证据路径和结论。

每面记录至少四个、跨槽分布的坐标点，单位 mm、左上为原点、右为 x、下为 y：

```json
[
  {"expected_mm":[20,50],"observed_mm":[21,49]},
  {"expected_mm":[120,50],"observed_mm":[121,49]},
  {"expected_mm":[20,110],"observed_mm":[21,109]},
  {"expected_mm":[120,110],"observed_mm":[121,109]}
]
```

示例值只说明格式。expected 是目标位置，observed 是同一基准下实物读数。用实际数据运行：

```bash
bash scripts/run.sh calibrate --profile /path/profile.json --samples /path/front-points.json --side front --output /path/profile-front.json
```

最小二乘拟合二维仿射偏差，再求逆得到发送坐标。已存在的补偿会参与组合，不被丢弃。残差超过默认 0.5 mm 则报错；这个阈值是数据一致性检查，不是最终验收公差。每次计算后 production_verified 重新置 false，重复试印后才确认。

## 依赖与检查

`run.sh` 优先使用 EPSON_PVC_PYTHON，再使用本技能缓存虚拟环境、Codex 自带 Python，最后系统 python3。`setup.sh` 在 `~/.cache/epson-pvc-print/venv` 安装排版和网格依赖，保持系统 Python 独立。测试：`~/.cache/epson-pvc-print/venv/bin/python -m unittest discover -s tests -v`。PDF 可用 `pdftoppm -scale-to 1200 -png -singlefile INPUT.pdf OUTPUT` 渲染检查。

颜色当前按 RGB 图片输出，由实际打印通道处理；尚未实现打印机 ICC 色彩校准。尺寸标定与颜色标定分别验收。

默认安装 requirements-tested.txt 中已通过本轮测试的固定版本；requirements.txt 和 requirements-mesh.txt 保留基础依赖范围，供维护时升级并重新验证。
