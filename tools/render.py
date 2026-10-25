"""Draw a page back from its JSON, as SVG: shapes, images and glyphs in the PDF's drawing order.

    python3 -I tools/render.py out/page-1.json            # -> out/page-1.svg

Glyphs are drawn from their own outlines (taken from the PDF's embedded fonts), so the SVG needs no fonts.
"""
import argparse, html, json, math, os


def render(model):
    p = model['page']
    defs, items = [], []
    for fid, f in model['fonts'].items():
        for gid, d in f['glyphs'].items():
            if d:
                defs.append(f'<path id="{fid}-{gid}" d="{d}"/>')
    for s in model['shapes']:
        a = [f'd="{s["d"]}"', f'fill="{s["fill"] or "none"}"', f'stroke="{s["stroke"] or "none"}"']
        if s['stroke']:
            a.append(f'stroke-width="{s["width"]}"')
            if s.get('dashes'):
                a.append(f'stroke-dasharray="{s["dashes"].split("]")[0].strip("[ ") or "none"}"')
        if s['even_odd']:
            a.append('fill-rule="evenodd"')
        if s['fill_opacity'] < 1:
            a.append(f'fill-opacity="{s["fill_opacity"]}"')
        if s['stroke_opacity'] < 1:
            a.append(f'stroke-opacity="{s["stroke_opacity"]}"')
        items.append((s['seq'], f'<path {" ".join(a)}/>'))
    for im in model['images']:
        if im['file'] and im.get('drawn', True):
            x0, y0, x1, y1 = im['bbox']
            items.append((im['seq'] if im['seq'] is not None else 1e9,
                          f'<image href="{im["file"]}" x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" preserveAspectRatio="none"/>'))
    for g in model['glyphs']:
        if g['mode'] not in ('fill', 'stroke'):
            continue                                     # invisible text (e.g. an OCR layer) is not drawn
        f = model['fonts'].get(g['font_id']) if g['font_id'] else None
        paint = (f'fill="none" stroke="{g["color"]}"' if g['mode'] == 'stroke' else f'fill="{g["color"]}"')
        if g['opacity'] < 1:
            paint += f' opacity="{g["opacity"]}"'
        if f and f['glyphs'].get(str(g['gid'])):
            # glyph units (y up) -> page (y down), along the text direction
            k = g['size'] / f['units_per_em']
            ux, uy = g['dir']
            m = f'matrix({k * ux:.5f} {k * uy:.5f} {k * uy:.5f} {-k * ux:.5f} {g["x"]} {g["y"]})'
            if g['mode'] == 'stroke':
                paint += f' stroke-width="{g["stroke_width"] / k:.2f}"'
            items.append((g['seq'], f'<use href="#{g["font_id"]}-{g["gid"]}" transform="{m}" {paint}/>'))
        elif g['text'].strip():                           # no usable font program: fall back to the text
            turn = math.degrees(math.atan2(g['dir'][1], g['dir'][0]))
            rot = f' transform="rotate({turn:.1f} {g["x"]} {g["y"]})"' if abs(turn) > 0.1 else ''
            items.append((g['seq'], f'<text x="{g["x"]}" y="{g["y"]}" font-size="{g["size"]}" {paint}{rot}>{html.escape(g["text"])}</text>'))
    items.sort(key=lambda it: it[0])                      # stable: same seq keeps the PDF's order
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {p["width"]} {p["height"]}" '
            f'width="{p["width"]}" height="{p["height"]}"><rect width="100%" height="100%" fill="#fff"/>'
            f'<defs>{"".join(defs)}</defs>{"".join(svg for _, svg in items)}</svg>')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('page_json'); ap.add_argument('--svg')
    a = ap.parse_args()
    svg = a.svg or os.path.splitext(a.page_json)[0] + '.svg'
    open(svg, 'w', encoding='utf-8').write(render(json.load(open(a.page_json, encoding='utf-8'))))
    print(f'-> {svg}')


if __name__ == '__main__':
    main()
