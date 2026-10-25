"""Sort every page of a PDF before extracting it: real text, image-only (a scan: needs OCR), or outlined text.
Also lists text that is in the file but hidden on the page (e.g. under a black "redaction" box).

    python3 -I tools/triage.py input.pdf [--json report.json]

Use it to send only the pages that really need OCR to a paid OCR service, and to check documents for hidden text
before they are shared.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf  # noqa: E402
from extract import extract  # noqa: E402


def words(glyphs):
    """Glyphs in drawing order -> text, with a space wherever the gap between two glyphs looks like a word gap."""
    out, prev = '', None
    for g in glyphs:
        if prev and (abs(g['y'] - prev['y']) > 0.5 * g['size'] or g['bbox'][0] - prev['bbox'][2] > 0.2 * g['size']):
            out += ' '
        out += g['text']
        prev = g
    return ' '.join(out.split())


def ranges(nums):
    """[2, 3, 4, 7] -> '2-4, 7'"""
    out, start = [], None
    for i, n in enumerate(nums):
        if start is None:
            start = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(f'{start}' if start == n else f'{start}-{n}')
            start = None
    return ', '.join(out)


def classify(page, model):
    letters = [g for g in model['glyphs'] if g['text'].strip() and g['mode'] == 'fill']
    w, h = page.rect.width, page.rect.height
    full = any((i['bbox'][2] - i['bbox'][0]) > 0.8 * w and (i['bbox'][3] - i['bbox'][1]) > 0.8 * h
               for i in model['images'] if i.get('drawn', True))
    # words converted to vector paths: one filled path of hundreds of segments in a dark colour
    outlined = sum(1 for dr in page.get_drawings()
                   if dr.get('fill') and len(dr['items']) > 300 and sum(dr['fill']) / len(dr['fill']) < 0.45
                   and dr['rect'].height < 200)
    if full and len(letters) < 40:
        kind = 'image-only'
    elif not letters and not model['images'] and not outlined:
        kind = 'blank'
    else:
        kind = 'text'
    hidden = words([g for g in model['glyphs'] if g['hidden']])
    return dict(page=page.number + 1, kind=kind, letters=len(letters), outlined_text_blocks=outlined,
                invisible_text=sum(1 for g in model['glyphs'] if g['mode'] == 'invisible'), hidden_text=hidden)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf'); ap.add_argument('--json')
    a = ap.parse_args()
    doc = pymupdf.open(a.pdf)
    pages = [classify(doc[n - 1], extract(a.pdf, n)) for n in range(1, doc.page_count + 1)]
    count = lambda k: sum(1 for p in pages if p['kind'] == k)
    print(f'{doc.page_count} pages: {count("text")} with real text, {count("image-only")} image-only (need OCR), '
          f'{count("blank")} blank')
    for kind in ('image-only', 'blank'):
        nums = [p['page'] for p in pages if p['kind'] == kind]
        if nums:
            print(f'  {kind}: pages {ranges(nums)}')
    for p in pages:
        notes = []
        if p['outlined_text_blocks']:
            notes.append(f"{p['outlined_text_blocks']} block(s) of outlined text (not readable as text)")
        if p['invisible_text']:
            notes.append(f"{p['invisible_text']} invisible glyphs (an OCR layer added by someone else)")
        if p['hidden_text']:
            notes.append(f"HIDDEN TEXT: \"{p['hidden_text'][:80]}\"")
        if notes:
            print(f"  page {p['page']}: " + ' · '.join(notes))
    if a.json:
        json.dump(pages, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
