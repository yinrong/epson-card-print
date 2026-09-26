#!/usr/bin/env python3
"""Create the L8058 stock-tray survey pack; no printer access or derived dimensions."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

REF = Path('/Users/derek.yin/.codex/research/epson-l8058-20260921/trays')
OFFICIAL = 'https://download4.epson.biz/sec_pubs/l8050_series/useg/sc/manual.pdf'
ROWS = []


def add(key, group, label, method, affects, unit='mm', nominal=None, phase='bench', notes=''):
    ROWS.append(dict(id=key, group=group, label=label, unit=unit, nominal=nominal,
                     measured=None, uncertainty=None, datum='A/Z0; B/Y0; C/X0',
                     method=method, affects=affects, phase=phase,
                     source_url=OFFICIAL if nominal is not None else None,
                     evidence='official_nominal' if nominal is not None else 'not_measured',
                     photo_id=None, notes=notes))


add('card.long_edge', 'card', '卡片长边', '卡尺；记录同批至少一张', '卡槽尺寸/最大卡数', nominal=86)
add('card.short_edge', 'card', '卡片短边', '卡尺', '卡槽尺寸/最大卡数', nominal=54)
add('card.thickness', 'card', '卡片厚度', '卡尺轻合；不压弯', '卡面高度/头部间隙', nominal=0.76)
add('card.inkjet_coated', 'card', '是否喷墨涂层', '核对耗材包装/厂家说明；未知留 null', '吸墨/成像/试印', unit='boolean', notes='measured 填 true 或 false；不凭白色外观判断')
add('card.coating_sides', 'card', '涂层面数', '核对包装并记录可印面；未知留 null', '手动双面打印/背面验证', unit='enum', notes='measured 填 single 或 double；不确定保持 null')
add('card.corner_radius', 'card', '卡片圆角半径', '圆角规或后续轮廓拟合；未测留空', '卡槽圆角')
add('tray.length', 'outline', '托架前后总长', '直尺/卡尺；包含刚性凸耳', '进盘/退盘行程')
add('tray.width_max', 'outline', '托架最大左右宽度', '直尺/卡尺；包含刚性凸耳', '入口/导向/最大卡数')
for station in ['front', 'middle', 'rear']:
    add(f'tray.width_{station}', 'outline', f'{station} 截面宽度', '卡尺；在照片标注取样截面', '导向/最大卡数')
    add(f'tray.width_{station}_d', 'outline', f'{station} 截面距前基准深度 d', '直尺；沿 Y 反方向量正距离', '截面定位', notes='CAD y=-d')
    add(f'tray.top_z_{station}', 'height', f'{station} 托架上表面相对 A 的 Z', '平板+高度/深度测量；记录取样点', '头部间隙')
add('tray.flatness_peak_to_valley', 'height', '底面支承状态下上表面高低差', '直尺+塞尺或高度规；不压平', '卡面平整/头部间隙')
add('tray.max_rigid_z', 'height', '所有刚性凸起最高点 Z', '平板+高度/深度测量', '头部间隙')
for end in ['cd', 'pvc']:
    add(f'lead.{end}.t_tip', 'entry', f'{end} 端入口尖部厚度', '卡尺；对照侧视照片', '进盘')
    add(f'lead.{end}.ramp_length', 'entry', f'{end} 端斜面长度', '卡尺；记录起止点', '进盘')
    add(f'lead.{end}.ramp_rise', 'entry', f'{end} 端斜面高度差', '卡尺/深度规', '进盘')
for side in ['left', 'right']:
    for field, label in [('x_inner','内边 X'), ('x_outer','外边 X'), ('d_start','起点深度 d'), ('d_end','终点深度 d'), ('z_min','最低 Z'), ('z_max','最高 Z')]:
        add(f'guide.{side}.{field}', 'guide', f'{side} 导轨/导向带 {label}', '卡尺；对应实物编号后测量', '进盘/导向/保留区域', notes='多段或变截面复制记录；CAD y=-d')
for slot in ['1', '2']:
    for field, label in [('x_min','左边 X'), ('d_near','近前端深度 d'), ('width_x','X 向内尺寸'), ('length_y','Y 向内尺寸'), ('floor_z','槽底支承面 Z'), ('loaded_top_z','装卡后卡面 Z'), ('corner_radius','内圆角半径'), ('retention_z','最高限位点 Z')]:
        add(f'slot.{slot}.{field}', 'slot', f'原厂卡槽 {slot} {label}', '卡尺/深度规；按原厂印刷槽号', '卡面高度/定位/卡槽设计', notes='卡片应自然落座，禁止压弯；CAD y=-d')
for field,label in [('center_x','中心 X'), ('center_d','中心深度 d'), ('recess_diameter','圆槽实测内径'), ('support_z','圆盘支承面 Z'), ('loaded_top_z','装盘后光盘上表面 Z'), ('hub_max_z','中心卡扣最高 Z')]:
    add(f'cd.{field}', 'disc', f'CD 区 {label}', '卡尺/深度规；装盘项有介质才测', '打印面高度/保留结构', notes='圆槽尺寸不是喷印范围；CAD y=-d')
for field,label in [('x_min','左界 X'), ('d_near','近前端深度 d'), ('width_x','X 向尺寸'), ('length_y','Y 向尺寸'), ('top_z','上表面 Z')]:
    add(f'mark.M01.{field}', 'mark', f'待识别标记 M01 {label}', '逐个编号，卡尺量边界；不要遮挡或擦除', '检测/送料定位', notes='M01 为记录模板，非照片对应结论；按实际数量复制 M02…；功能未确认')
for side in ['left', 'right']:
    for field,label in [('x_min','左界 X'), ('x_max','右界 X'), ('d_start','起点深度 d'), ('d_end','终点深度 d')]:
        add(f'roller_candidate.{side}.{field}', 'contact', f'{side} 候选滚轮接触带 {label}', '仅根据可见磨痕/结构登记候选，附照片', '驱动接触/槽位禁入区', notes='未经实机观察不能认定为真实滚轮带')
for field,label in [('x_min','左界 X'), ('x_max','右界 X'), ('d_start','起点深度 d'), ('d_end','终点深度 d'), ('z_min','最低 Z'), ('z_max','最高 Z')]:
    add(f'keepout.K01.{field}', 'keepout', f'保留结构 K01 {label}', '原托架实测；按实际结构复制 K02…', '导向/检测/滚轮/结构强度', notes='K01 为记录模板；形状不规则时用 feature_points.csv')
for mode in ['cd_end_first','pvc_end_first']:
    for field,label in [('entry_body_line_d','装载对齐时机身前沿对应深度 d'), ('travel_min_d','机械行程近界 d'), ('travel_max_d','机械行程远界 d'), ('repeatability_y','重复定位 Y 偏差')]:
        add(f'travel.{mode}.{field}', 'travel', f'{mode} {label}', '后续经授权的正常作业观察/坐标校准；本步骤不执行', '进盘/有效行程/最大卡数', phase='deferred_machine', notes='机械行程与可喷印边界分开记录，不推拉机器内托架')
    for field,label in [('x_min','喷印左界 X'), ('x_max','喷印右界 X'), ('d_start','喷印近界 d'), ('d_end','喷印远界 d')]:
        add(f'print_envelope.{mode}.{field}', 'print_envelope', f'{mode} {label}', '后续独立校准；本步骤不打印', '最大卡数', phase='deferred_print', notes='不能由 A4、圆盘外径、托架外形或机械行程代填')
add('printer.head_clearance_min', 'clearance', '打印头相对最高介质面的最小间隙', '后续具备方法及授权再验证；不把卡尺伸进机器', '头部间隙', phase='deferred_machine')


def write_base(output_dir):
    output_dir = Path(output_dir).expanduser().resolve()
    protected = ('测量表.json', '测量表.csv', 'feature_points.csv')
    existing = [name for name in protected
                if (output_dir / name).exists() or (output_dir / name).is_symlink()]
    if existing:
        raise FileExistsError(
            f'拒绝覆盖：{output_dir} 已有 {", ".join(existing)}。请指定独立的新模板目录。')
    output_dir.mkdir(parents=True, exist_ok=True)
    pack = dict(schema_version='1.0', purpose='stock_tray_metrology',
                specimen=dict(printer_model=None, tray_part_number=None, original_or_compatible=None,
                              operator=None, measured_at=None, instrument=None, instrument_resolution_mm=None),
                units='mm', coordinate_frame=dict(
                    handedness='right', top_view='CD end at top; PVC end at bottom',
                    origin='intersection of front tangent B, left tangent C and underside support plane A',
                    x_positive='right in top view', y_positive='toward CD/front, outside tray',
                    z_positive='up from underside support plane A toward printable face',
                    depth_d='positive distance rearward from B; CAD y=-d',
                    datum_A='plane established by three identified underside support points A1/A2/A3',
                    datum_B='frontmost rigid CD-end boundary tangent plane',
                    datum_C='leftmost rigid outline tangent plane in the stated top view'),
                measurements=ROWS,
                features=[],
                feature_template=dict(id=None, kind=None, face=None, function=None, function_evidence=None,
                                      geometry_type=None, points_mm=[], center_mm=None, radius_mm=None,
                                      material=None, color=None, photo_id=None, notes=None),
                constraints=dict(verified_print_polygon_xy=None, verified_motion_polygon_xy=None,
                                 keepout_polygons_xy=[], minimum_structure_web_mm=None,
                                 slot_clearance_mm=None, maximum_card_count=None))
    with (output_dir/'测量表.json').open('x', encoding='utf-8') as f:
        f.write(json.dumps(pack,ensure_ascii=False,indent=2)+'\n')
    with (output_dir/'测量表.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=ROWS[0].keys()); writer.writeheader()
        writer.writerows({k:'null' if v is None else v for k,v in r.items()} for r in ROWS)
    with (output_dir/'feature_points.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f); writer.writerow(['feature_id','kind','face','point_order','x_mm','depth_d_mm','y_mm','z_mm','photo_id','notes'])
        writer.writerow(['null','null','null','null','null','null','null','null','null','每个实际轮廓点一行；y=-depth_d；逆时针闭合轮廓；不要同时填互相冲突的d与y'])
    (output_dir/'结构测量清单.md').write_text(ONE_PAGE)
    refs=[]
    for name,url,caption in SOURCES:
        target=output_dir/'reference'/name; target.parent.mkdir(exist_ok=True)
        shutil.copy2(REF/name,target)
        refs.append(dict(file='reference/'+name,source_url=url,caption=caption,
                         sha256=hashlib.sha256(target.read_bytes()).hexdigest(),edited=False))
    (output_dir/'图源.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2)+'\n')
    (output_dir/'测量基准示意.svg').write_text(SVG)
    print(f'{len(ROWS)} measurements created: {output_dir}')


CHECKLIST = '''# 原托架结构测量清单

目的：把 L8058 原托架转成可追溯的 CAD 输入。先量原件，再确定保留区域和可排卡区域。

## 本次填写

- [ ] 记录打印机型号、托架料号/字样、原厂或兼容、测量日期和量具分辨率。
- [ ] 用实物确认 CD 端、PVC 端和原厂卡槽 1/2；所有照片保持同一前端标识。
- [ ] 完成正面、底面、装卡侧面带尺照片；尺与被量平面尽量共面，镜头正对平面。
- [ ] 量总长、最大宽度、前中后三个截面的宽度及其位置、入口尖部厚度与斜面。
- [ ] 记录底面支承点 A1/A2/A3，量导轨/筋条/凸耳/缺口，保留原有外形分段。
- [ ] 量两个卡槽的内尺寸、位置、支承面 Z、自然落座后的卡面 Z；卡片长短边和厚度另量。
- [ ] 逐个编号检测片候选、白色印记、通孔及机械缺口，附位置、边界、照片；功能栏未确认就留空。
- [ ] 记录可见磨痕与候选滚轮接触带，区分“看见的痕迹”和“已验证的接触功能”。
- [ ] 测量上表面高低差和最高刚性凸起；不按压托架消除翘曲。

## 后续验证字段

- CD 端先入与 PVC 端先入分别记录装载对齐线、机械行程、重复定位。
- 两种模式分别验证可喷印多边形；遇到孔洞、圆形裁切或缺印时保留实际多边形，不能只填一个包围矩形。
- 打印头间隙、机内实际滚轮带、动态送料行程留待后续验证。本次不启动作业，不用手推拉机内托架，不把量具伸进打印机。

## 对设计的影响

| 尺寸/结构 | 影响 |
|---|---|
| 外廓、导轨、入口斜面、底部凸起 | 能否进盘、是否偏斜、是否顺利退盘 |
| 槽底 Z、装卡后 Z、最高凸起、平面度 | 卡面与原厂打印面的高度关系、头部间隙 |
| 检测片与缺口、装载对齐线 | 模式识别和重复定位；功能未明时保留原结构 |
| 滚轮带、筋条、最小连接宽度 | 送料接触与托架刚度，需要从排卡区域扣除 |
| 实测喷印区域与送料范围 | 最大卡数；仅有托架总长宽还不能确定 |

## 填表规则

- 优先填写 `测量表.json` 或 `测量表.csv` 中的一份，回传时说明哪份为事实源。JSON 的 `null` 与 CSV 的文本 `null` 都表示未测，不能用 0 代替。
- 官方 86×54×0.76 mm 只放 `nominal`。所有 `measured` 初始为 `null`，现场测完才填数字。
- 单位默认 mm；`uncertainty` 写所采用的不确定度，没有估计就保持 `null`。量具分辨率独立登记，不能当作测量精度。
- `photo_id` 指向实际照片。新出现的导轨段、标记、孔或保留结构按编号复制记录；模板 M01/K01 不表示实物已有对应结构。
- 复杂轮廓填写 `feature_points.csv`，或 JSON `features`。坐标采用同一 A/B/C 基准，顶视轮廓按逆时针记录，曲线另记圆心/半径或足够采样点。
- 没有测到的尺寸继续留空；照片用于结构与测点对照，不从透视照片填工程毫米数。

交接最低内容见 `60秒现场操作.md`；完整 CAD 前仍需补齐导轨、Z 高度和保留区域。
'''

ONE_PAGE = '''# 原托架测量准备

本轮在桌面测原托架。`测量表.csv/json` 初始实测值均为 `null`，官方卡片 86×54×0.76 mm 只填 `nominal`。填写其中一份作为事实源，未测项目保持 `null`，不用 0 代替。

## 基准与方向

顶视装载面：CD 端在前（图上方），PVC 端在后。左右固定，底面照片翻转后仍沿用顶视左右。官方图确认 CD 和 PVC 作业从相反两端进入，模式另记，原件坐标保持不变。

- A / Z=0：托架底部实际支承平面。空托架放平整台面，拍照标出支承点 A1/A2/A3；摇晃或支承不明确时，先保留照片，Z 值待确认。
- B / Y=0：CD 端最前刚性外廓的切平面；C / X=0：顶视最左刚性外廓的切平面，含凸耳。
- O=A/B/C 交点。X+ 向右，Y+ 向 CD 前方，Z+ 向装载面，为右手坐标；主体 Y≤0。现场向后量正深度 d，CAD 用 **y=-d**。
- 卡面 Z 相对 A；局部上下厚度不能替代卡面 Z。SVG 不按比例，任何示意位置都不是测量值。

## 测量清单

本轮验收测量资料是否可用；后续桌面测绘按 `bench` 范围验收。`deferred_machine` 与 `deferred_print` 属于后续受控验证，不作为桌面测绘完成条件。

| 勾选 | 需记录 | 影响 |
|---|---|---|
| ☐ | 型号、托架字样、原厂/兼容、量具分辨率、日期 | 实物版本和量测追溯 |
| ☐ | 实际卡长/宽/厚、喷墨涂层、单/双面涂层 | 卡槽尺寸、图像尺寸与双面验证 |
| ☐ | 总长宽、分段外廓、入口斜面、凸耳/缺口 | 进盘、导向、退盘 |
| ☐ | 底部支承点、导轨/筋条的位置和高度 | 导向、接触、刚度 |
| ☐ | 两槽内尺寸/位置/槽底 Z、装卡后 Z、最高凸起、平面度 | 定位和头部间隙 |
| ☐ | 印记/检测片候选/通孔逐个编号，保留形状、位置、照片 | 检测与送料定位，未知功能留空 |
| ☐ | 可见磨痕和候选滚轮接触带 | 排卡需避让区域；真实接触功能待验证 |
| 后续 | 两种进盘模式各自的有效送料行程、重复定位、喷印边界 | 最大卡数；本轮保持 null |

**有效行程属于后续受控作业/试印验证；不要手动硬推机内托架测行程，不把卡尺伸进打印机。** 托架总面积、A4 画布和原生圆盘直径均不能代替实测喷印区域。

## 60 秒最小采集

1. **0–15 秒**：装载面向上、CD 端朝前，带直尺拍正面全貌，记录型号/托架字样。
2. **15–30 秒**：拍底面全貌，在旁用纸标 CD 端和顶视左侧，不遮挡原标记。
3. **30–45 秒**：原厂槽自然放一张卡，拍带尺侧面，包含底面、槽边与卡面。
4. **45–60 秒**：记总长、最大宽度、入口局部厚度、卡片厚度；卡尺读数可拍照，来不及就留空。

**最少回传 3 张带尺原图 + 上述 4 项读数 + 型号/托架字样。** 尺与被拍平面尽量共面，镜头正对平面；厚度读数标测点。照片用于识别结构，不能单独完成工程尺寸或可打印范围确认。耗材涂层信息一并回传，未知允许留空。

## 数据与图证

CSV 与 JSON 字段一致；`photo_id` 关联现场照片，`uncertainty` 未估计就留空。标记 M01、保留区 K01 为模板，按实物新增编号；复杂轮廓用 `feature_points.csv` 或 JSON `features`，顶视轮廓逆时针记录。初始最大卡数为 `null`。

参考图在 `reference/`，来源及 SHA-256 在 `图源.json`。官方英文手册 p32/35 是 CD/PVC 加载方向图；PrinterPartsPoint 图片是 L8050 等型号兼容托架照片，PrinterPartner 商品列 L8058、1888952、Import，均不作为原厂尺寸证据。

[官方中文 L8058 手册](https://download4.epson.biz/sec_pubs/l8050_series/useg/sc/manual.pdf) · [官方英文系列手册](https://download.epson-europe.com/pub/download/6538/epson653845eu.pdf) · [PrinterPartsPoint](https://printerpartspoint.com/products/pvc-id-card-tray-for-epson-l8050-l18050-l8180) · [PrinterPartner](https://printerpartner.in/product/pvc-id-card-tray-cd-dvd-tray-for-epson-l8050-l8058-l18058-l18050-printer-1888952-import/)
'''

DATUM = '''# 测量基准说明

## 固定方向

从装卡面俯视：CD 圆槽端在图上方，定义为前端；PVC 两槽端在下方，定义为后端。左右始终依据此顶视方向，不随翻转底面照片改变。底面照片须标出实物的 CD 端与左右，不能直接当成顶视坐标。

官方 L8058 手册 p34/p36 说明 CD 模式让 CD 端先入，PVC 模式让 PVC 端先入。原件坐标始终固定；进盘模式另记，不能通过改变坐标定义混用两个方向。

## A/B/C 与右手坐标

- A：原托架底部实际支承面基准，Z=0。将卸下的空托架放在平整台面，识别并标记照片中的三个支承点 A1/A2/A3。若筋条、翘曲或摇晃使支承不明确，先记录现象和照片，A 的具体点位待确认，不随意选择上表面代替。
- B：包含 CD 端最前方刚性外廓的切平面，Y=0。凸耳计入；松动附件另记。
- C：固定顶视方向下，包含最左侧刚性外廓的切平面，X=0。
- 原点 O 为 A/B/C 的交点。X+ 向右，Y+ 朝 CD 前方，Z+ 从底面朝装载面，为右手坐标。托架主体位于 Y≤0。
- 现场沿 B 向后量正距离 d；导入 CAD 时 y=-d。所有长度仍填写正数；Z、X、Y 坐标保留符号。
- Z 高度须相对 A。局部上下表面厚度不能直接当卡面 Z；须同时知道局部底面相对 A 的台阶。

完整测点由现场照片与卡尺读数建立。自绘 `测量基准示意.svg` 只解释方向和测量类别，不按比例，不代表检测片、导轨或滚轮的真实位置。

## 图证与用途

| 文件 | 来源与证明内容 |
|---|---|
| `reference/official-l8050-page-032.png` | Epson L8050 系列官方英文手册 p32：CD 端先入、托架标记对齐机身前沿。 |
| `reference/official-l8050-page-035.png` | 同手册 p35：PVC 端先入；卡片通过槽底孔取出。 |
| `reference/printerpartspoint-l8050-stock-tray.jpg` | 商家标为 L8050/L18050/L8180 New Compatible 的托架正面。可辨认装载区域和外形，不是 L8058 原厂身份凭证或尺寸图。 |
| `reference/printerpartner-tray.png` | 商家商品标题列 L8050/L8058/L18058/L18050、1888952、Import 的斜视照片；用于辨认结构。 |

官方英文 PDF：[Epson 手册](https://download.epson-europe.com/pub/download/6538/epson653845eu.pdf)。中文型号依据：[L8058 手册](https://download4.epson.biz/sec_pubs/l8050_series/useg/sc/manual.pdf)。原始图片 URL、来源身份和 SHA-256 见 `图源.json`。照片按原字节复制，官方页面为既有完整渲染图。

## 后续 CAD 的计算边界

可排卡区域取“经验证的喷印区域、送料可达区域、允许改变的托架结构区域”的交集，再扣除导向/滚轮/检测/加强结构及卡槽留量。A4 画布、120 mm 光盘外径与整托架外廓各有用途，不能相互替代。当前各区域尚待测定，`maximum_card_count` 保持 `null`。
'''

FIELD = '''# 60秒现场操作

准备卸下的原托架、同批空白卡、直尺/卷尺和卡尺。托架留在桌上，打印机无需操作。60 秒用于最小资料采集；完整导轨与 Z 高度测量另做。

| 时间 | 操作 |
|---|---|
| 0–15 秒 | 装载面朝上、CD 端朝前，旁放直尺，拍正面全貌。记录型号和托架可见料号。 |
| 15–30 秒 | 翻转拍底面全貌，仍让 CD 端朝前；用纸条在旁标“CD 前端、顶视左侧”。不要覆盖托架标记。 |
| 30–45 秒 | 在原厂槽自然放入一张卡，直尺与侧边共面拍侧面，能看见托架底面、槽边与卡面。 |
| 45–60 秒 | 记录总长、最大宽度、入口边可夹持处的厚度，以及卡片厚度；卡尺读数可直接拍照。做不完就留空。 |

最少回传：**正面、底面、装卡侧面 3 张带尺原图 + 4 项读数（总长、最大宽度、入口局部厚度、卡片厚度）+ 打印机型号/托架字样**。厚度读数须标测点，别把局部厚度标成全部托架厚度。

拍摄时镜头尽量正对被拍平面，尺靠近且与该平面共面，保留全外廓。照片可先启动建模检查，不能单独完成打印面高度、滚轮带和有效行程确认。现场数值不足时保留 `null`。
'''

SOURCES = [
    ('official-l8050-page-032.png','https://download.epson-europe.com/pub/download/6538/epson653845eu.pdf','Official L8050 series manual p32; CD end first; full-page render'),
    ('official-l8050-page-035.png','https://download.epson-europe.com/pub/download/6538/epson653845eu.pdf','Official L8050 series manual p35; PVC end first; full-page render'),
    ('printerpartspoint-l8050-stock-tray.jpg','https://printerpartspoint.com/cdn/shop/files/WhatsApp_Image_2024-07-23_at_3.59.23_PM.jpg?v=1721827704&width=952','Merchant compatible tray for L8050/L18050/L8180; unchanged photo'),
    ('printerpartner-tray.png','https://printerpartner.in/wp-content/uploads/2026/04/tray.png','Merchant lists L8058 among compatible models; Import; unchanged photo'),
]

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="1280" viewBox="0 0 1280 1280">
<title>L8058 原托架测量基准示意，不按比例</title>
<desc>右手坐标，CD 端为前端，X 向右，Y 向前，Z 从托架底面支承平面向上。仅说明测量基准，所有轮廓和位置均为示意。</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z" fill="#275b9a"/></marker></defs>
<rect width="1280" height="1280" fill="white"/>
<g font-family="Arial,PingFang SC,Microsoft YaHei,sans-serif" fill="#172b43">
<text x="50" y="48" font-size="27" font-weight="bold">原托架测量基准 · CD 端朝前 · 不按比例</text>
<text x="50" y="80" font-size="17">自绘工程示意。外廓、孔位、卡槽位置均未测量；不得据本图制造。</text>
<g stroke="#172b43" stroke-width="2" fill="none">
<path d="M155 175 H490 V202 H514 V639 H490 V675 H155 V642 H130 V201 H155Z" fill="#f1f5f9"/>
<circle cx="323" cy="302" r="100"/><circle cx="323" cy="302" r="15"/>
<rect x="196" y="445" width="110" height="175" rx="7"/><rect x="338" y="445" width="110" height="175" rx="7"/>
<line x1="95" y1="175" x2="580" y2="175" stroke-dasharray="6 5"/>
<line x1="130" y1="135" x2="130" y2="715" stroke-dasharray="6 5"/>
</g>
<text x="252" y="143" font-size="22">CD 前端</text><text x="270" y="365" font-size="21">CD 圆槽</text>
<text x="214" y="537" font-size="18">原厂卡槽</text><text x="356" y="537" font-size="18">原厂卡槽</text>
<text x="204" y="650" font-size="16">两槽左右并列 · 卡长边沿 Y</text>
<text x="260" y="706" font-size="22">PVC 后端</text>
<g stroke="#275b9a" stroke-width="2.5" marker-end="url(#arrow)">
<line x1="130" y1="175" x2="235" y2="175"/><line x1="130" y1="175" x2="130" y2="103"/>
<line x1="82" y1="196" x2="82" y2="350"/>
</g>
<text x="90" y="168" font-size="18">O</text><text x="240" y="190" font-size="19">X+</text><text x="145" y="113" font-size="19">Y+</text>
<text x="38" y="284" font-size="18">d+</text><text x="20" y="380" font-size="16">y = −d</text>
<text x="530" y="182" font-size="16">B：最前刚性外廓</text><text x="140" y="736" font-size="16">C：最左刚性外廓</text>
<g font-size="18">
<text x="675" y="165" font-size="23" font-weight="bold">测量并保留的结构</text>
<text x="675" y="209">① 外廓：凸耳、缺口、入口斜面</text>
<text x="675" y="249">② 底部：支承点、导轨、筋条</text>
<text x="675" y="289">③ 卡槽：位置、内尺寸、槽底及卡面 Z</text>
<text x="675" y="329">④ 标记：印刷片、反射片候选、通孔</text>
<text x="675" y="369">⑤ 接触带：磨痕候选；实际滚轮带待验证</text>
<text x="675" y="427">①② 影响进盘与导向</text>
<text x="675" y="462">②③ 影响打印面高度与头部间隙</text>
<text x="675" y="497">④⑤ 影响检测与送料；功能未明先保留</text>
<text x="675" y="555">有效行程 / 喷印边界：后续分别验证</text>
<text x="675" y="590">托架外形不等于可喷印区域</text>
<text x="675" y="640" fill="#a14025">所有实测值初始为 null</text>
<text x="675" y="675">官方 86 × 54 × 0.76 mm 仅作卡片标称</text>
</g>
<text x="50" y="795" font-size="23" font-weight="bold">侧视：Z 基准取托架底部支承平面 A</text>
<g stroke="#172b43" stroke-width="2" fill="none">
<path d="M140 925 L170 895 H495 V913 H680 V890 H1020 L1050 925 Z" fill="#e2e8f0"/>
<rect x="500" y="889" width="170" height="23" fill="#b6d3f2"/>
<line x1="100" y1="925" x2="1100" y2="925" stroke-dasharray="8 5"/>
</g>
<g stroke="#275b9a" stroke-width="2.5" marker-end="url(#arrow)"><line x1="140" y1="925" x2="140" y2="830"/><line x1="725" y1="925" x2="725" y2="889"/></g>
<text x="100" y="840" font-size="18">Z+</text><text x="1110" y="931" font-size="18">A / Z=0</text>
<text x="520" y="874" font-size="17">自然落座卡片</text><text x="740" y="883" font-size="17">装卡后卡面 Z</text>
<text x="148" y="952" font-size="16">CD 前端</text><text x="955" y="952" font-size="16">PVC 后端</text>
<text x="50" y="1000" font-size="18">局部厚度 ≠ 相对 A 的卡面高度。支承不明确时，先拍底面与侧面，Z 值保留 null。</text>
<text x="50" y="1037" font-size="17">示意卡片位置仅解释 Z 测量，不对应上图卡槽位置或真实结构截面。</text>
</g></svg>'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='生成原托架空白测量资料；已有测量表时拒绝写入。')
    parser.add_argument('--output-dir', required=True, type=Path,
                        help='新模板输出目录；必须不含测量表.json/csv 或 feature_points.csv')
    args = parser.parse_args()
    try:
        write_base(args.output_dir)
    except OSError as exc:
        parser.exit(2, f'{parser.prog}: error: {exc}\n')
