# 原托架测量资料

生成测量说明、CSV/JSON、轮廓点模板、SVG 与参考图来源记录：

```bash
python3 /Users/derek.yin/dev/mac-manage/epson-l8058/measurement/prepare_measurement.py \
  --output-dir /Users/derek.yin/db/epson-l8058/new-measurement
```

`--output-dir` 必填；目录里已有任一测量表或轮廓点文件时拒绝运行。新模板使用独立目录。

生成器不访问打印机；只复制已下载的参考图。测量表以空值开始，只有官方卡片 86×54×0.76 mm 保留标称值。

本轮成果：[测量清单](/Users/derek.yin/db/epson-l8058/step01-20260921/measurement/结构测量清单.md)；填写 CSV 或 JSON 其中一份作为实测事实源。
