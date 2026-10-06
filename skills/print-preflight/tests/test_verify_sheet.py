import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts'/'verify_sheet.py'


def make_source(path):
    im = Image.new('RGB', (200, 100), 'white')
    for box, color in (((0, 0, 100, 50), (255, 0, 0)), ((100, 0, 200, 50), (0, 0, 255)),
                       ((0, 50, 100, 100), (0, 255, 0)), ((100, 50, 200, 100), (255, 255, 0))):
        im.paste(color, box)
    im.save(path)


def make_pdf(path, source, mirror):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    PT = 72/25.4
    c = canvas.Canvas(str(path), pagesize=(210*PT, 297*PT))
    c.translate(0, 297*PT)
    c.scale(PT, -PT)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, 210, 297, stroke=0, fill=1)
    x, y, w, h = 10, 10, 180, 90
    if mirror:
        c.drawImage(ImageReader(source), x, y, width=w, height=h)  # 缺局部翻转 → 上下镜像
    else:
        c.saveState(); c.translate(x, y+h); c.scale(1, -1)
        c.drawImage(ImageReader(source), 0, 0, width=w, height=h)
        c.restoreState()
    c.showPage(); c.save()


class VerifySheet(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'src.png'
        make_source(self.source)

    def run_verify(self, pdf):
        r = subprocess.run([sys.executable, str(SCRIPT), '--pdf', str(pdf), '--page', '1', '--source', str(self.source)],
                           capture_output=True, text=True)
        return r

    def test_correct_orientation_passes(self):
        pdf = self.base/'correct.pdf'; make_pdf(pdf, self.source, mirror=False)
        r = self.run_verify(pdf)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn('"verdict": "original"', r.stdout)

    def test_mirrored_detected(self):
        pdf = self.base/'mirrored.pdf'; make_pdf(pdf, self.source, mirror=True)
        r = self.run_verify(pdf)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('"verdict": "mirror_tb"', r.stdout)


if __name__ == '__main__':
    unittest.main()
