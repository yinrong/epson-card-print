# Profile 与来源

- `page_mm`：实际打印页面尺寸，不是托架外廓尺寸。
- `slots`：页面左上原点，x/y 为卡片左上、w/h 为卡片宽高；rotation 为源图顺时针旋转角度。
- `inset_mm`：卡边向内留白；默认 3 mm。没有实现出血到卡外。
- `back_slot_map`：按正面 slots 顺序指定各卡背面放在哪个槽；默认原槽。
- `back_rotation`：背面额外旋转 0 或 180 度；不会镜像图像。
- `transforms`：front/back 各六值 `[a,b,c,d,e,f]`，`x'=a*x+b*y+c, y'=d*x+e*y+f`，均为 mm 坐标。
- `cups_options`：实际队列支持的介质／来源／质量选项。内置 profile 留空，待查队列。
- `queue_name`：实际校准所用队列名；`tray_option`：cups_options 中负责选托架来源的键。运行前与实时队列能力核对，拒绝换队列复用旧标定。
- `transport_verified`、`production_verified`、`verification_evidence`：分别记录实际托架通道、生产定位与正反配对验证；目前为 false/空。

原托架候选坐标取自 L8050 Mac 13.26 的 MediaID 199。驱动列出的两个裁剪区按 360 dpi 换算约 56.02×87.98 mm，以 54×86 mm 卡居中推得当前模板。L8058 的真实页面原点、裁剪和进料仍需验证。

公开方法依据：[pabr 的 R800 托架打印 PCB 案例](https://www.pabr.org/pcbprt/pcbprt.en.html)。案例证明其他机型可通过可控输出后端和托架打印；不能替代 L8058 兼容性结论。

CUPS 用法依据：[官方命令行打印](https://openprinting.github.io/cups/doc/options.html)、[lp 参数](https://openprinting.github.io/cups/doc/man-lp.html)。程序固定单份、单面、单页，显式关闭缩放；这些参数是否被目标后端遵守仍须尺规试印。

机械照片估算采用用户的 186×297 mm 外廓、3 mm 主体、0.6 mm 入口和 0.76 mm 卡材。侧边 30 mm、两端 25 mm 是首版结构预留，不是可打印区域。槽深先按卡面齐平假设；原件成功卡面仍是实物参照。
