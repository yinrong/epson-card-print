# Epson L8058 多卡托架执行计划

目标：自编程序批量打印卡片正反面，手工翻面；按可喷印范围设计更密集的 3D 托架，交付以程序为主的 SKILL。[当前程序与验收状态](04-程序与SKILL执行结果.md)。

| 顺序与任务 | 状态 | 依赖 | 结果路径 |
|---|---|---|---|
| [01 设备与托架基线](40-任务排序/01-设备与托架基线.md) | 用户尺寸与照片估算已记录；本轮未发现目标机 | 现有 Mac、Remote 登记、原托架 | [连接诊断](/Users/derek.yin/db/epson-l8058/step01-20260921/connectivity/检查结果.md) · [测量清单](/Users/derek.yin/db/epson-l8058/step01-20260921/measurement/结构测量清单.md) |
| [02 托架进料与完整矩形输出适配](40-任务排序/02-托架进料与完整矩形输出适配.md) | 提交适配器已实现；实机通道待验证 | 01 的连接与机械基准 | `/Users/derek.yin/db/epson-l8058/step02-output/`（预定） |
| [03 实测喷印边界](40-任务排序/03-安全载体上实测喷印边界.md) | 待开始 | 02 可控输出、合适受墨载体 | `/Users/derek.yin/db/epson-l8058/step03-print-area/`（预定） |
| [04 最大槽数求解](40-任务排序/04-最大槽数求解.md) | 保留矩形内五卡已证明；实际范围待验证 | 01 机械禁占区＋03 喷印覆盖图 | `/Users/derek.yin/db/epson-l8058/step04-packing/`（预定） |
| [05 参数化托架与图像程序](40-任务排序/05-参数化3D托架与图像程序.md) | 排版程序及 SCAD 概念件完成 | 04 排布、02 输出后端 | `/Users/derek.yin/db/epson-l8058/step05-prototype/`（预定） |
| [06 正反面校准与重复试印](40-任务排序/06-正反面校准与重复试印.md) | 校准与逐盘程序已测试；实机待验 | 05 实物与程序 | `/Users/derek.yin/db/epson-l8058/step06-validation/`（预定） |

[固定目标与执行记录](PLAN.md) · [原话出处](10-原始需求/README.md) · [核心需求](15-核心需求/需求基线.md) · [验收清单](50-验收清单/README.md) · [epson-print-card 证卡程序](skills/epson-print-card/SKILL.md)（源码；已装 `~/.zcode/skills/`、`~/.codex/skills/`，PATH 命令 `epson-print-card`） · [print-preflight 打印预检](skills/print-preflight/SKILL.md)

已有研究：[多卡托架规划](/Users/derek.yin/.claude/delivered-results/epson-l8058/多卡托架规划/latest/L8058多卡托架规划.md)。四卡与十卡尺寸均为条件算例，最大卡数由实测确定。当前目录是本地任务目录；本轮不提交打印作业。
