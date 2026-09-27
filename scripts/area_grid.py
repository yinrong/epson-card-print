#!/usr/bin/env python3
"""Full-page millimetre grid for measuring the printable area on a tray (tape paper over the tray)."""
import argparse
from reportlab.pdfgen import canvas

PT = 72 / 25.4


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--page-mm', nargs=2, type=float, default=[209.9733333333, 296.9683333333])
    p.add_argument('--clip-mm', nargs=4, type=float, metavar=('X0','Y0','X1','Y1'), help='only draw inside this page rectangle')
    a = p.parse_args()
    w, h = a.page_mm
    c = canvas.Canvas(a.output, pagesize=(w*PT, h*PT))
    c.setTitle('tray printable-area grid')
    c.translate(0, h*PT); c.scale(PT, -PT)
    if a.clip_mm:
        x0, y0, x1, y1 = a.clip_mm
        clip = c.beginPath(); clip.rect(x0, y0, x1-x0, y1-y0); c.clipPath(clip, stroke=0)
    for x in range(0, int(w)+1):
        major = x % 10 == 0
        c.setStrokeColorRGB(*((0, 0, 0) if major else (.6, .6, .6))); c.setLineWidth(.2 if major else .08)
        if major or x % 5 == 0:
            c.line(x, 0, x, h)
        else:
            for y in range(0, int(h)+1, 10):
                c.line(x, y-1, x, y+1)
    for y in range(0, int(h)+1):
        major = y % 10 == 0
        c.setStrokeColorRGB(*((0, 0, 0) if major else (.6, .6, .6))); c.setLineWidth(.2 if major else .08)
        if major or y % 5 == 0:
            c.line(0, y, w, y)
        else:
            for x in range(0, int(w)+1, 10):
                c.line(x-1, y, x+1, y)
    c.setFillColorRGB(.8, 0, 0)
    for x in range(0, int(w)+1, 10):
        for y in range(0, int(h)+1, 10):
            c.saveState(); c.translate(x+.5, y+2.3); c.scale(1, -1); c.setFont('Helvetica-Bold', 1.8)
            c.drawString(0, 0, f'{x},{y}'); c.restoreState()
    c.saveState(); c.translate(w/2, 20); c.scale(1, -1); c.setFont('Helvetica-Bold', 5); c.setFillColorRGB(0, 0, 1)
    c.drawCentredString(0, 0, 'PAGE TOP  (x,y mm from page top-left)'); c.restoreState()
    c.showPage(); c.save()


if __name__ == '__main__':
    main()
