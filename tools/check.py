"""Compare a rebuilt page (SVG drawn by a real browser) with the PDF's own rendering of that page.

    python3 -I tools/check.py input.pdf PAGE out/page-PAGE.svg [--png out/check-PAGE.png]

Prints a similarity score (1.0 = identical; 1 - mean absolute grey difference after a slight blur) and saves
rebuilt | PDF | difference side by side. Needs Playwright for Python; set CHROME to a Chrome/Chromium binary
if Playwright's own browser is not installed.
"""
import argparse, io, os
import pymupdf
from PIL import Image, ImageChops, ImageFilter, ImageOps
from playwright.sync_api import sync_playwright

DPI = 96


def grey(im):
    return ImageOps.grayscale(im.convert('RGB')).filter(ImageFilter.GaussianBlur(1))


def check(pdf, pno, svg, png=None):
    page = pymupdf.open(pdf)[pno - 1]
    pix = page.get_pixmap(dpi=DPI)
    ref = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    with sync_playwright() as pw:
        exe = os.environ.get('CHROME')
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        tab = browser.new_page(viewport={'width': pix.width, 'height': pix.height})
        tab.goto('file://' + os.path.abspath(svg))
        tab.wait_for_timeout(300)
        shot = tab.locator('svg').first.screenshot()
        browser.close()
    rebuilt = Image.open(io.BytesIO(shot)).convert('RGB').resize(ref.size)
    diff = ImageChops.difference(grey(rebuilt), grey(ref))
    score = 1 - sum(i * n for i, n in enumerate(diff.histogram())) / (255 * ref.size[0] * ref.size[1])
    if png:
        w, h = ref.size
        out = Image.new('RGB', (w * 3 + 20, h), 'white')
        out.paste(rebuilt, (0, 0)); out.paste(ref, (w + 10, 0))
        out.paste(ImageOps.invert(ImageOps.autocontrast(diff)).convert('RGB'), (2 * w + 20, 0))
        out.save(png)
    return score


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf'); ap.add_argument('page', type=int); ap.add_argument('svg'); ap.add_argument('--png')
    a = ap.parse_args()
    png = a.png or os.path.join(os.path.dirname(a.svg), f'check-{a.page}.png')
    print(f'similarity {check(a.pdf, a.page, a.svg, png):.4f}  (side by side: {png})')


if __name__ == '__main__':
    main()
