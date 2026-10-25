"""Make examples/sample.pdf: a small page with the things that trip up PDF extraction.

    python3 -I examples/make_sample.py

It has English and Arabic (right-to-left, with diacritics) text, coloured words, a vector chart, a raster image,
and a sentence that a box is later drawn over (so it is in the PDF but hidden).
"""
import io, os
import pymupdf
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

HTML = """
<h2 style="font-family: sans-serif">Quarterly report</h2>
<p style="font-family: sans-serif">Revenue grew by <b style="color:#c00000">12%</b> while costs stayed flat.
The chart below is drawn with vector paths, not pixels.</p>
<p dir="rtl" style="font-family: sans-serif; text-align: right">نَمَتِ الإيرادات بنسبة <span style="color:#0060c0">١٢٪</span> هذا الربع.</p>
"""


def main():
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(pymupdf.Rect(50, 50, 545, 260), HTML)

    # a vector bar chart
    for i, h in enumerate((60, 95, 80, 130)):
        x = 80 + i * 70
        page.draw_rect(pymupdf.Rect(x, 450 - h, x + 40, 450), color=None, fill=(0.2, 0.45, 0.7))
    page.draw_line((70, 450), (370, 450), color=(0, 0, 0), width=1)

    # a raster logo
    im = Image.new('RGB', (120, 60), (240, 200, 60))
    ImageDraw.Draw(im).ellipse((20, 10, 100, 50), fill=(200, 60, 40))
    buf = io.BytesIO(); im.save(buf, 'PNG')
    page.insert_image(pymupdf.Rect(420, 320, 540, 380), stream=buf.getvalue())

    # a sentence, then an opaque box drawn over it: it stays in the PDF but nobody can see it
    page.insert_htmlbox(pymupdf.Rect(50, 500, 545, 540), '<p style="font-family: sans-serif">DRAFT: do not publish these numbers.</p>')
    page.draw_rect(pymupdf.Rect(45, 495, 400, 530), color=(0, 0, 0), fill=(1, 1, 0.85), width=0.5)
    page.insert_htmlbox(pymupdf.Rect(55, 503, 395, 528), '<p style="font-family: sans-serif">Approved for release.</p>')

    doc.save(f'{HERE}/sample.pdf')
    print(f'wrote {HERE}/sample.pdf')


if __name__ == '__main__':
    main()
