"""Turn one PDF page into data: every shape, glyph and image the page draws, in drawing order, plus its text.

    python3 -I tools/extract.py input.pdf PAGE [--out DIR] [--fixes fixes.json]

PAGE is 1-based. Writes DIR/page-PAGE.json (default DIR: out/) and DIR/images/ for the page's raster images.
No OCR, no AI: everything is read from the PDF's own drawing instructions (PyMuPDF) and embedded fonts (fontTools).
See METHOD.md for why each step is done this way.
"""
import argparse, io, json, os, re, tempfile, unicodedata
from collections import Counter, defaultdict

import pymupdf
from fontTools.cffLib import CFFFontSet
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.t1Lib import T1Font
from fontTools.ttLib import TTFont

RTL = re.compile('[֐-ࣿיִ-﷿ﹰ-ﻼ]')     # Hebrew, Arabic and their presentation forms
LTR_RUN = re.compile(r'[A-Za-z0-9٠-٩۰-۹.,:/%\-]+')   # Latin words and digits inside RTL text


def normal(text):
    """Presentation forms (positional Arabic letters, Latin ligatures like 'ﬂ') -> the plain letters they stand for."""
    return ''.join(unicodedata.normalize('NFKC', ch) if 0xFB00 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF
                   else ch for ch in text)


def r2(v):
    return round(v, 2)


def hexcolor(c):
    if c is None:
        return None
    if isinstance(c, (int, float)):
        c = (c, c, c)
    if len(c) == 4:                                       # CMYK
        k = c[3]; c = [(1 - v) * (1 - k) for v in c[:3]]
    return '#' + ''.join(f'{round(max(0, min(1, v)) * 255):02x}' for v in c[:3])


def path_d(items, close):
    out = []
    for it in items:
        if it[0] == 'l':
            out.append(f'M{it[1].x:.2f},{it[1].y:.2f}L{it[2].x:.2f},{it[2].y:.2f}')
        elif it[0] == 'c':
            out.append(f'M{it[1].x:.2f},{it[1].y:.2f}C{it[2].x:.2f},{it[2].y:.2f} {it[3].x:.2f},{it[3].y:.2f} {it[4].x:.2f},{it[4].y:.2f}')
        elif it[0] == 're':
            r = it[1]; out.append(f'M{r.x0:.2f},{r.y0:.2f}H{r.x1:.2f}V{r.y1:.2f}H{r.x0:.2f}Z')
        elif it[0] == 'qu':
            q = it[1]; out.append(f'M{q.ul.x:.2f},{q.ul.y:.2f}L{q.ur.x:.2f},{q.ur.y:.2f}L{q.lr.x:.2f},{q.lr.y:.2f}L{q.ll.x:.2f},{q.ll.y:.2f}Z')
    d = ''.join(out)
    # consecutive segments repeat the pen position: drop the redundant moves so the outline stays one path
    d = re.sub(r'([LC][^MLCZHV]*?(-?[\d.]+,-?[\d.]+))M\2', r'\1', d)
    return d + ('Z' if close and not d.endswith('Z') else '')


def outlines(items):
    """Number of closed outlines in a path: one outline has no hole, so an opaque fill hides what is under it."""
    n, end = 0, None
    for it in items:
        if it[0] in ('re', 'qu'):
            n, end = n + 1, None
        else:
            if end is None or abs(it[1].x - end.x) > 0.01 or abs(it[1].y - end.y) > 0.01:
                n += 1
            end = it[-1]
    return n


def norm(name):
    """Font names differ between the text trace ('NimbusSans-Bold') and the font list ('ABCDEF+Nimbus Sans Bold')."""
    return re.sub(r'[^a-z0-9]', '', name.split('+', 1)[-1].lower())


class Outlines:
    """Glyph outlines of one embedded font program, by glyph id, as SVG path data in font units (y up)."""

    def __init__(self, ext, buf):
        self.upem, self.glyphs = 1000, None
        try:
            if ext in ('ttf', 'otf'):
                f = TTFont(io.BytesIO(buf))
                self.upem = f['head'].unitsPerEm
                self.order, self.glyphs = f.getGlyphOrder(), f.getGlyphSet()
            elif ext == 'cid' or ext == 'cff':                # bare CFF program (CID-keyed or not)
                cff = CFFFontSet(); cff.decompile(io.BytesIO(buf), None)
                top = cff[cff.fontNames[0]]
                self.upem = round(1 / top.FontMatrix[0]) if top.FontMatrix[0] else 1000
                self.order, self.glyphs = top.charset, top.CharStrings
            elif ext in ('pfa', 'pfb'):                       # Type 1 (classic PostScript fonts, e.g. from LaTeX)
                if b'cleartomark' not in buf[-600:]:          # PDFs often drop the trailer the parser expects
                    buf = buf + b'\n' + (b'0' * 64 + b'\n') * 8 + b'cleartomark\n'
                with tempfile.NamedTemporaryFile(suffix='.' + ext, delete=False) as fh:
                    fh.write(buf)
                try:
                    t1 = T1Font(fh.name); t1.parse()
                finally:
                    os.unlink(fh.name)
                self.upem = round(1 / t1.font['FontMatrix'][0])
                # glyph ids follow the CharStrings order, with .notdef moved to id 0 (as FreeType/MuPDF number them)
                self.order = list(t1.font['CharStrings'].keys())
                if '.notdef' in self.order:
                    i = self.order.index('.notdef'); self.order[0], self.order[i] = self.order[i], self.order[0]
                self.glyphs = t1.getGlyphSet()
        except Exception:                                      # Type1 / Type3 / damaged programs: not supported
            self.glyphs = None

    def advance(self, gid):
        """Advance width of a glyph in font units (None if unknown)."""
        if self.glyphs is None or not 0 <= gid < len(self.order):
            return None
        try:
            g = self.glyphs[self.order[gid]]
            if getattr(g, 'width', None) is None:            # CFF / Type 1: the width is known once drawn
                g.draw(SVGPathPen(self.glyphs))
            return g.width
        except Exception:
            return None

    def path(self, gid):
        """SVG path data of a glyph, '' when it has no outline (e.g. a space), None when it is not in this font."""
        if self.glyphs is None or not 0 <= gid < len(self.order):
            return None
        pen = SVGPathPen(self.glyphs)
        try:
            self.glyphs[self.order[gid]].draw(pen)
        except Exception:
            return None
        return pen.getCommands()


def spacing_error(prog, sp):
    """How far the font's advance widths are from the spacing of the span's glyphs on the page."""
    err, ux, uy = 0.0, *sp['dir']
    chars = [c for c in sp['chars'] if c[1] >= 0]
    for a, b in zip(chars, chars[1:]):
        adv = prog.advance(a[1])
        if adv is None:
            err += sp['size']; continue
        step = (b[2][0] - a[2][0]) * ux + (b[2][1] - a[2][1]) * uy     # distance along the writing direction
        err += abs(step - adv * sp['size'] / prog.upem)
    return err


def extract(pdf, pno, fixes=None, out=None):
    doc = pymupdf.open(pdf)
    page = doc[pno - 1]
    fixes = fixes or {}
    model = dict(page=dict(number=pno, width=r2(page.rect.width), height=r2(page.rect.height)),
                 shapes=[], images=[], glyphs=[], lines=[], fonts={}, report={})
    rep = model['report']

    # ---- shapes: vector paths with their fill, stroke and drawing order ----
    covers = []                                                # opaque one-outline fills: they hide what is below
    for dr in page.get_drawings():
        fill, stroke = dr.get('fill'), dr.get('color')
        model['shapes'].append(dict(
            d=path_d(dr['items'], dr.get('closePath')), fill=hexcolor(fill), stroke=hexcolor(stroke),
            width=r2(dr.get('width') or 0), even_odd=bool(dr.get('even_odd')),
            fill_opacity=r2(dr.get('fill_opacity') or 1), stroke_opacity=r2(dr.get('stroke_opacity') or 1),
            dashes=dr.get('dashes') if dr.get('dashes') not in (None, '[] 0') else None, seq=dr['seqno']))
        if fill is not None and (dr.get('fill_opacity') or 1) > 0.99 and outlines(dr['items']) == 1:
            covers.append((dr['rect'], dr['seqno']))

    # ---- images: position and drawing order (seqno = index in the page's bbox log) ----
    log = page.get_bboxlog()
    image_seqs = [i for i, (kind, _) in enumerate(log) if kind == 'fill-image']
    for k, info in enumerate(page.get_image_info(xrefs=True)):
        # the log entry drawn at the same place (each entry is used once)
        seq = min(image_seqs, key=lambda i: sum(abs(a - b) for a, b in zip(log[i][1], info['bbox'])), default=None)
        if seq is not None:
            image_seqs.remove(seq)
        img = dict(bbox=[r2(v) for v in info['bbox']], seq=seq, file=None)
        if out and info.get('xref'):
            try:
                pix = pymupdf.Pixmap(doc, info['xref'])
                if pix.n - pix.alpha > 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                os.makedirs(f'{out}/images', exist_ok=True)
                img['file'] = f'images/p{pno}-{k}.png'
                pix.save(f'{out}/{img["file"]}')
            except Exception:
                pass
        model['images'].append(img)

    # ---- fonts: which embedded program draws each font name (one name can have several subsets) ----
    programs = defaultdict(list)
    for f in page.get_fonts(full=True):
        xref, ext, basefont = f[0], f[1], f[3]
        try:
            if ext == 'n/a' and basefont.lower() in pymupdf.Base14_fontdict:   # standard font, not embedded:
                buf, ext = pymupdf.Font(basefont).buffer, 'cff'                 # use the viewer's own copy
            else:
                buf = doc.extract_font(xref)[3]
            programs[norm(basefont)].append((xref, Outlines(ext, buf)))
        except Exception:
            pass

    # ---- glyphs: one entry per drawn glyph ----
    spans = page.get_texttrace()
    font_ids, defs, ambiguous = {}, {}, 0
    for si, sp in enumerate(spans):
        mode = {0: 'fill', 1: 'stroke', 3: 'invisible'}.get(sp['type'], 'other')
        name = sp['font']
        gids = [c[1] for c in sp['chars'] if c[1] >= 0]
        # One font name can have several embedded subsets whose glyph ids mean different shapes. Pick the one
        # that has outlines for this span's glyphs and whose advance widths match the glyph spacing on the page.
        cands = [p for _, p in programs.get(norm(name), [])]
        prog = min(cands, key=lambda p: (-sum(1 for g in gids if p.path(g)), spacing_error(p, sp)), default=None)
        if len(cands) > 1:
            ambiguous += 1
        fid = None
        if prog and prog.glyphs is not None:
            fid = font_ids.setdefault(id(prog), f'f{len(font_ids)}')
            model['fonts'].setdefault(fid, dict(name=name, units_per_em=prog.upem, glyphs={}))
        fix = fixes.get(name, {})
        for u, gid, origin, bbox in sp['chars']:
            if gid == -1 and model['glyphs'] and model['glyphs'][-1]['span'] == si:   # rest of a ligature's text
                model['glyphs'][-1]['text'] += chr(u)
                continue
            if fid and str(gid) not in model['fonts'][fid]['glyphs']:
                p = prog.path(gid)
                if p is not None:
                    model['fonts'][fid]['glyphs'][str(gid)] = p
            model['glyphs'].append(dict(
                text=fix.get(str(gid), chr(u) if u > 0 else ''), gid=gid, font=name, font_id=fid,
                x=r2(origin[0]), y=r2(origin[1]), bbox=[r2(v) for v in bbox], size=r2(sp['size']),
                dir=[r2(v) for v in sp['dir']], color=hexcolor(sp['color']), opacity=r2(sp.get('opacity', 1)),
                mode=mode, stroke_width=r2(sp.get('linewidth') or 0), seq=sp['seqno'], span=si))
    rep['font_spans_with_several_subsets'] = ambiguous
    # U+FFFD / empty text on a visible glyph = the PDF's ToUnicode map has no entry: repair with a fixes file
    rep['glyphs_unmapped'] = sum(1 for g in model['glyphs'] if g['mode'] == 'fill' and (not g['text'] or '\ufffd' in g['text']))
    rep['glyphs_without_outline_font'] = sum(1 for g in model['glyphs'] if g['font_id'] is None)

    # a glyph drawn before an opaque box that covers it is hidden: it stays in the data, marked, but not in the text
    for g in model['glyphs']:
        cx, cy = (g['bbox'][0] + g['bbox'][2]) / 2, (g['bbox'][1] + g['bbox'][3]) / 2
        g['hidden'] = any(sq > g['seq'] and r.x0 < cx < r.x1 and r.y0 < cy < r.y1 for r, sq in covers)
    rep['glyphs_hidden'] = sum(g['hidden'] for g in model['glyphs'])

    model['lines'] = text_lines(model['glyphs'])
    if out:
        os.makedirs(out, exist_ok=True)
        with open(f'{out}/page-{pno}.json', 'w', encoding='utf-8') as fh:
            json.dump(model, fh, ensure_ascii=False)
    return model


def text_lines(glyphs):
    """The page's text: one entry per run of same-style text, in reading order; runs with the same `line` share a baseline."""
    seen, chars = set(), []
    for g in glyphs:
        key = (g['font'], g['gid'], g['x'], g['y'])
        if g['hidden'] or g['mode'] in ('invisible', 'other') or key in seen:   # bold = fill pass + stroke pass
            continue
        seen.add(key)
        c = dict(g)
        # work in the text's own frame: 'along' the writing direction and 'across' it (rotated text too)
        ux, uy = g['dir']
        along = lambda x, y: x * ux + y * uy
        c['across'] = -g['x'] * uy + g['y'] * ux
        corners = [along(x, y) for x in (g['bbox'][0], g['bbox'][2]) for y in (g['bbox'][1], g['bbox'][3])]
        c['a0'], c['a1'], c['order'] = min(corners), max(corners), along(g['x'], g['y'])
        c['dir_key'] = (round(ux, 2), round(uy, 2))
        chars.append(c)

    # combining marks (diacritics) are separate glyphs. Some producers draw a mark just before its letter, others
    # just after: attach it to the neighbour in the drawing stream (same span) whose box its position falls in
    is_mark = lambda c: c['text'] and all(unicodedata.category(ch) == 'Mn' for ch in c['text'])
    for c in chars:
        c['marks'] = ''
    bases = [i for i, c in enumerate(chars) if not is_mark(c) and c['text'].strip()]
    for i, c in enumerate(chars):
        if not is_mark(c):
            continue
        prev = next((j for j in reversed(bases) if j < i), None)
        nxt = next((j for j in bases if j > i), None)
        near = [j for j in (nxt, prev) if j is not None and chars[j]['span'] == c['span']]
        if not near:
            continue
        dist = lambda j: max(chars[j]['a0'] - c['order'], 0, c['order'] - chars[j]['a1'])
        chars[min(near, key=dist)]['marks'] += c['text']
    chars = [c for c in chars if not is_mark(c)]
    for c in chars:
        c['text'] = normal(c['text']) + c['marks']
    # a space touching the glyph drawn just before it belongs right after that glyph (its own position can fall
    # inside the next letter when letters are kerned tightly)
    for prev, c in zip(chars, chars[1:]):
        if not c['text'].strip() and prev['span'] == c['span'] and abs(prev['a1'] - c['order']) < 0.5:
            c['order'] = prev['order'] + 0.01

    # lines: same writing direction, baselines close (superscripts sit a little higher: allow for the larger size)
    lines = []
    for c in sorted(chars, key=lambda c: (c['dir_key'], c['across'])):
        ln = lines[-1] if lines else None
        if ln and ln['dir_key'] == c['dir_key'] and abs(c['across'] - ln['across']) <= 0.45 * max(c['size'], ln['size']):
            ln['chars'].append(c); ln['size'] = max(ln['size'], c['size'])
        else:
            lines.append(dict(dir_key=c['dir_key'], across=c['across'], size=c['size'], chars=[c]))

    result = []
    for n, ln in enumerate(lines):
        cs = ln['chars']
        letters = [c for c in cs if c['text'].strip()]
        rtl = sum(bool(RTL.search(c['text'])) for c in letters) > len(letters) / 2
        cs.sort(key=lambda c: -c['order'] if rtl else c['order'])
        runs = []
        for c in cs:
            style = (c['font'], c['size'], c['color'])
            if not c['text'].strip():
                if runs and style != runs[-1]['style']:
                    # a space in another font: a word gap only if it falls between letters, not on top of one
                    if any(l['a0'] <= c['order'] + 0.1 * c['size'] <= l['a1'] for l in letters):
                        continue
                if runs and not runs[-1]['text'].endswith(' '):
                    runs[-1]['text'] += ' '
                continue
            last = runs[-1] if runs else None
            gap = (last['edge'] - c['a1'] if rtl else c['a0'] - last['edge']) if last else None
            if last and gap < 1.5 * c['size'] and last['font'] == c['font'] and last['color'] == c['color'] \
                    and abs(last['size'] - c['size']) < 0.01:
                # many producers (e.g. TeX) draw no space characters: a wide gap is a word gap
                if gap > 0.2 * c['size'] and not last['text'].endswith(' '):
                    last['text'] += ' '
                last['text'] += c['text']
            else:
                if last and gap is not None and 0.2 * c['size'] < gap < 1.5 * c['size'] and not last['text'].endswith(' '):
                    last['text'] += ' '                  # style changes mid-sentence: keep the word gap
                runs.append(dict(style=style, font=c['font'], size=c['size'], color=c['color'], text=c['text'],
                                 boxes=[], rtl=rtl, y=c['y'], dir=list(ln['dir_key'])))
            r = runs[-1]
            r['boxes'].append(c['bbox'])
            r['edge'] = c['a0'] if rtl else c['a1']
        for r in runs:
            t = r['text'].strip()
            if r['rtl']:                      # Latin words and numbers inside RTL text were collected backwards
                t = LTR_RUN.sub(lambda m: m[0][::-1], t)
            if t:
                b = r['boxes']
                result.append(dict(text=t, line=n, bbox=[r2(min(x[0] for x in b)), r2(min(x[1] for x in b)),
                                                 r2(max(x[2] for x in b)), r2(max(x[3] for x in b))],
                                   y=r2(r['y']), dir=r['dir'], font=r['font'], size=r['size'], color=r['color'],
                                   direction='rtl' if r['rtl'] else 'ltr'))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf'); ap.add_argument('page', type=int)
    ap.add_argument('--out', default='out'); ap.add_argument('--fixes', help='JSON {font name: {glyph id: text}}')
    a = ap.parse_args()
    fixes = json.load(open(a.fixes, encoding='utf-8')) if a.fixes else None
    m = extract(a.pdf, a.page, fixes, a.out)
    print(f"page {a.page}: {len(m['shapes'])} shapes, {len(m['glyphs'])} glyphs, {len(m['images'])} images, "
          f"{len(m['lines'])} text runs -> {a.out}/page-{a.page}.json")
    print(json.dumps(m['report']))


if __name__ == '__main__':
    main()
