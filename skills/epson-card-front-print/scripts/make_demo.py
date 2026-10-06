#!/usr/bin/env python3
"""Create clearly numbered asymmetric front-only sample images for dry runs."""
import argparse
import csv
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    font_path=Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    font=ImageFont.truetype(str(font_path),70) if font_path.exists() else ImageFont.load_default(size=60)
    small=ImageFont.truetype(str(font_path),28) if font_path.exists() else ImageFont.load_default(size=28)
    rows=[]
    for i,color in enumerate(('#dbeafe','#dcfce7','#ffedd5'),1):
        im=Image.new('RGB',(860,540),color);draw=ImageDraw.Draw(im)
        draw.rectangle((6,6,853,533),outline='#0f172a',width=6)
        draw.rectangle((20,20,95,95),fill='#ef4444')
        draw.ellipse((765,20,840,95),fill='#2563eb')
        draw.polygon([(430,35),(405,75),(455,75)],fill='#0f172a')
        draw.text((120,170),f'CARD {i}',font=font,fill='#0f172a')
        draw.text((120,275),'FRONT',font=font,fill='#0f172a')
        draw.text((35,475),'L     SAMPLE - KEEP THIS EDGE AT BOTTOM     R',font=small,fill='#0f172a')
        filename=f'card-{i}-front.png';im.save(out/filename)
        rows.append({'id':f'DEMO-{i}','front':filename,'quantity':1})
    with (out/'cards.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['id','front','quantity']);w.writeheader();w.writerows(rows)
    print(out/'cards.csv')


if __name__=='__main__':main()
