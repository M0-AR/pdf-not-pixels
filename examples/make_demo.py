"""Make examples/demo-invoice.pdf: a realistic business document for the live demo.

    python3 -I examples/make_demo.py

A bilingual (English / Arabic) invoice with a logo, a line-item table, totals in colour, and a confidential note
that someone "redacted" by drawing a black box over it. The box hides the note on screen, but the words are still
inside the file. Exactly the kind of thing a business needs to know before a document leaves the building.
"""
import io, os
import pymupdf
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = 'font-family: sans-serif'

HEAD = f"""
<div style="{FONT}">
<p style="font-size:22px; font-weight:bold; color:#1d3557; margin:0">Northwind Trading Co.</p>
<p style="font-size:10px; color:#555; margin:2px 0 0 0">12 Harbour Road, Port City &nbsp;·&nbsp; billing@northwind.example</p>
</div>"""

META = f"""
<div style="{FONT}; font-size:11px">
<p style="font-size:18px; font-weight:bold; margin:0 0 6px 0">INVOICE <span style="color:#e63946">#INV-2026-0417</span></p>
<p style="margin:0">Date: 15 October 2026</p>
<p style="margin:0">Due: 14 November 2026</p>
<p style="margin:6px 0 0 0"><b>Bill to:</b> Blue Lake Clinics Ltd.</p>
<p dir="rtl" style="margin:4px 0 0 0; text-align:right">فاتورة ضريبية — شُكْرًا لِتَعامُلِكُم مَعَنا</p>
</div>"""

ROWS = [('Document scanning audit (1,200 pages)', '1', '480.00'),
        ('Data extraction setup', '1', '1,250.00'),
        ('Monthly processing, Arabic + English', '3', '2,100.00'),
        ('Priority support', '3', '450.00')]

TABLE = f"""
<table style="{FONT}; font-size:11px; width:100%; border-collapse:collapse">
<tr style="background-color:#1d3557; color:#ffffff">
  <td style="padding:5px"><b>Description</b></td><td style="padding:5px; text-align:right"><b>Qty</b></td>
  <td style="padding:5px; text-align:right"><b>Amount (USD)</b></td></tr>
""" + ''.join(f"""<tr style="background-color:{'#f1f4f9' if i % 2 else '#ffffff'}">
  <td style="padding:5px">{d}</td><td style="padding:5px; text-align:right">{q}</td>
  <td style="padding:5px; text-align:right">{a}</td></tr>""" for i, (d, q, a) in enumerate(ROWS)) + """
</table>"""

TOTALS = f"""
<div style="{FONT}; font-size:11px; text-align:right">
<p style="margin:0">Subtotal: 4,280.00</p>
<p style="margin:0">VAT (15%): 642.00</p>
<p style="margin:4px 0 0 0; font-size:15px; font-weight:bold; color:#2a9d8f">Total due: USD 4,922.00</p>
</div>"""


def logo():
    im = Image.new('RGB', (240, 240), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 230, 230), fill=(29, 53, 87))
    d.polygon([(120, 40), (200, 180), (40, 180)], fill=(230, 57, 70))
    buf = io.BytesIO(); im.save(buf, 'PNG')
    return buf.getvalue()


def main():
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(0, 0, 595, 8), color=None, fill=(0.114, 0.208, 0.341))
    page.insert_image(pymupdf.Rect(40, 34, 92, 86), stream=logo())
    page.insert_htmlbox(pymupdf.Rect(102, 38, 380, 90), HEAD)
    page.insert_htmlbox(pymupdf.Rect(330, 110, 555, 230), META)
    page.draw_line((40, 245), (555, 245), color=(0.8, 0.8, 0.8), width=0.8)
    page.insert_htmlbox(pymupdf.Rect(40, 260, 555, 420), TABLE)
    page.insert_htmlbox(pymupdf.Rect(300, 430, 555, 500), TOTALS)

    # a bar chart of monthly volume, drawn as vector shapes
    page.insert_htmlbox(pymupdf.Rect(40, 515, 300, 535), f'<p style="{FONT}; font-size:10px; color:#555">Pages processed per month</p>')
    for i, h in enumerate((40, 62, 55, 88, 104, 96)):
        x = 50 + i * 38
        page.draw_rect(pymupdf.Rect(x, 640 - h, x + 24, 640), color=None, fill=(0.165, 0.616, 0.561))
    page.draw_line((44, 640), (282, 640), color=(0.3, 0.3, 0.3), width=0.8)

    # "redacted" internal note: the text stays in the file under the black box
    page.insert_htmlbox(pymupdf.Rect(320, 560, 555, 610),
                        f'<p style="{FONT}; font-size:10px">Internal note: client agreed to a 30% discount. Do not disclose.</p>')
    page.draw_rect(pymupdf.Rect(316, 556, 556, 600), color=None, fill=(0, 0, 0))
    page.insert_htmlbox(pymupdf.Rect(320, 606, 555, 630), f'<p style="{FONT}; font-size:8px; color:#777">[redacted]</p>')

    page.insert_htmlbox(pymupdf.Rect(40, 780, 555, 810),
                        f'<p style="{FONT}; font-size:9px; color:#777; text-align:center">Thank you for your business. '
                        'Payment by bank transfer within 30 days.</p>')
    doc.save(f'{HERE}/demo-invoice.pdf', garbage=3, deflate=True)
    print(f'wrote {HERE}/demo-invoice.pdf')


if __name__ == '__main__':
    main()
