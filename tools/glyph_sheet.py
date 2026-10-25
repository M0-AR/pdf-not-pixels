"""Draw every glyph the extracted pages use, next to the text the PDF claims for it, to repair broken text.

    python3 -I tools/glyph_sheet.py out/page-*.json --html out/glyphs.html

Each cell shows the glyph's real shape (from the embedded font), its glyph id and the claimed text. Cells whose
claimed text is missing or U+FFFD are red. Read the right text off the shape and put it in a fixes file
{"font name": {"glyph id": "text"}} for tools/extract.py --fixes.
"""
import argparse, html, json


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pages', nargs='+'); ap.add_argument('--html', default='out/glyphs.html')
    a = ap.parse_args()
    fonts = {}                                         # font name -> {gid: (path, upem, claimed texts)}
    for fn in a.pages:
        m = json.load(open(fn, encoding='utf-8'))
        for g in m['glyphs']:
            f = m['fonts'].get(g['font_id']) if g['font_id'] else None
            path = f['glyphs'].get(str(g['gid'])) if f else None
            if not path:                               # spaces and glyphs without an outline
                continue
            cell = fonts.setdefault(g['font'], {}).setdefault(g['gid'], [path, f['units_per_em'], set()])
            cell[2].add(g['text'])
    out = ['<!doctype html><meta charset="utf-8"><title>Glyph sheet</title><style>'
           'body{font-family:sans-serif;margin:16px}.g{display:inline-block;width:86px;margin:3px;border:1px solid #ccc;'
           'text-align:center;font-size:12px}.bad{border-color:#d00;background:#fee}svg{width:64px;height:64px}</style>']
    for name, cells in sorted(fonts.items()):
        out.append(f'<h2>{html.escape(name)} ({len(cells)} glyphs)</h2>')
        for gid, (path, upem, texts) in sorted(cells.items()):
            claimed = ' | '.join(sorted(texts))
            bad = any(not t or '�' in t for t in texts)
            # font units: y up, glyph box roughly -0.3..1 em high
            box = f'0 {-upem} {upem * 1.1:.0f} {upem * 1.4:.0f}'
            out.append(f'<div class="g{" bad" if bad else ""}"><svg viewBox="{box}"><path transform="scale(1,-1)" '
                       f'd="{path}"/></svg><br>id {gid}<br><b>{html.escape(claimed) or "∅"}</b></div>')
    open(a.html, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'{sum(len(c) for c in fonts.values())} glyphs in {len(fonts)} fonts -> {a.html}')


if __name__ == '__main__':
    main()
