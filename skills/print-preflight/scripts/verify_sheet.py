#!/usr/bin/env python3
"""渲染 PDF 指定页，取指定格区域与源图候选方向（原样/上下镜像/左右镜像/180）做整格像素比对。

判定规则：次小差 ÷ 最小差 ≥ 1.5 才给结论，否则 inconclusive；只有判为 original 才退出码 0。
渲染：优先 pdftoppm；没有则 pypdf 拆单页后用 macOS sips（sips 只渲染第 1 页且不报错）。
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def render_page(pdf, page_index, out_png):
    if shutil.which('pdftoppm'):
        subprocess.run(['pdftoppm', '-f', str(page_index+1), '-l', str(page_index+1), '-scale-to', '1200',
                        '-png', '-singlefile', str(pdf), str(out_png)], check=True, capture_output=True)
        return
    import pypdf
    reader = pypdf.PdfReader(str(pdf))
    writer = pypdf.PdfWriter(); writer.add_page(reader.pages[page_index])
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        writer.write(f); part = f.name
    subprocess.run(['sips', '-s', 'format', 'png', part, '--out', str(out_png)+'.tmp.png'], check=True, capture_output=True)
    Path(str(out_png)+'.tmp.png').replace(out_png)


def region_diff(a, b):
    b = b.resize(a.size)
    stat = ImageStat.Stat(ImageChops.difference(a, b))
    return sum(stat.mean)/3


def content_bbox(im, tol=12):
    """页面内容区（自动裁掉白边），整页铺满时即整页；四个候选共用同一裁剪，保持公平。"""
    diff = ImageChops.difference(im, Image.new('RGB', im.size, 'white')).convert('L')
    return diff.point(lambda v: 255 if v > tol else 0).getbbox()


def parse_mm(text):
    w, h = text.lower().split('x', 1)
    return float(w), float(h)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf', required=True)
    p.add_argument('--page', type=int, default=1, help='1-based')
    p.add_argument('--source', required=True, help='拼版前的一张源图')
    p.add_argument('--cell', default=None, help='格尺寸 mm，如 46.7x74.3；默认整页')
    p.add_argument('--row', type=int, default=0)
    p.add_argument('--col', type=int, default=0)
    p.add_argument('--page-mm', default='210x297')
    p.add_argument('--margin', type=float, default=1.5, help='次小/最小倍差阈值')
    args = p.parse_args()

    with tempfile.TemporaryDirectory() as td:
        png = Path(td)/'page.png'
        render_page(args.pdf, args.page-1, png)
        page = Image.open(png).convert('RGB')
    pw_mm, ph_mm = parse_mm(args.page_mm)
    cw = page.width * ((parse_mm(args.cell)[0] if args.cell else pw_mm)/pw_mm)
    ch = page.height * ((parse_mm(args.cell)[1] if args.cell else ph_mm)/ph_mm)
    x0, y0 = int(args.col*cw), int(args.row*ch)
    region = page.crop((x0, y0, min(int(x0+cw), page.width), min(int(y0+ch), page.height)))
    bbox = content_bbox(region)
    if bbox and (bbox[2]-bbox[0]) > 8 and (bbox[3]-bbox[1]) > 8:
        region = region.crop(bbox)

    src = Image.open(args.source).convert('RGB')
    candidates = {
        'original': src,
        'mirror_tb': src.transpose(Image.FLIP_TOP_BOTTOM),
        'mirror_lr': src.transpose(Image.FLIP_LEFT_RIGHT),
        'rotate180': src.rotate(180),
    }
    diffs = {name: round(region_diff(region, im), 2) for name, im in candidates.items()}
    ranked = sorted(diffs, key=diffs.get)
    best, second = ranked[0], ranked[1]
    ratio = round(diffs[second]/diffs[best], 2) if diffs[best] else float('inf')
    verdict = best if ratio >= args.margin else 'inconclusive'
    print(json.dumps({'page': args.page, 'row': args.row, 'col': args.col, 'diffs': diffs,
                      'best': best, 'margin_ratio': ratio, 'verdict': verdict}, ensure_ascii=False))
    sys.exit(0 if verdict == 'original' else 1)


if __name__ == '__main__':
    main()
