# pdf-not-pixels

**Read the PDF, not the picture of it.**

When people need data out of a PDF, they often render the page to an image and run OCR, or send it to a vision
AI model. That throws away the most exact information the file has and replaces it with a guess. OCR and vision
models confuse similar letters, drop or move accents and diacritics, misread numbers, and give no guarantee
that the next page will be read as well as this one.

Most PDFs are not pictures. A PDF page is a **list of drawing instructions**:

```
draw glyph 57 of font F2, 12 pt, at (151.8, 178.6), colour #c00000
fill this path with #3373b2
draw image 3 in the box (420, 320, 540, 380)
draw glyph 58 ...
```

If you read those instructions directly, you get every character, shape and image with its **exact** position,
size, font, colour and drawing order. Nothing is guessed. From that you can:

- extract the text and its layout, including right-to-left scripts and diacritics
- rebuild the page in code (SVG, HTML, canvas), so it looks like the PDF
- change anything: recolour a word, hide a layer, restyle, translate, link items to other data
- check the result, page by page, against the PDF's own rendering

This repository explains the method ([METHOD.md](METHOD.md)) and gives a small working implementation in Python
(PyMuPDF + fontTools), with no OCR and no AI.

## What it does on real files

| File | Result |
|---|---|
| `examples/sample.pdf` (English, Arabic with diacritics, colours, chart, image, text hidden under a box) | Text exactly as written; hidden text detected; rebuilt page similarity **0.9985** |
| A 19-page LaTeX research paper (Type 1 and TrueType fonts, maths, figures, a rotated margin stamp) | All pages rebuilt from their own glyph outlines; similarity **0.966–0.997** per page |

Similarity is 1 minus the mean grey-level difference between the rebuilt page (drawn by a browser) and the PDF
rendered by PyMuPDF. The remaining difference is mostly anti-aliasing at glyph edges.

## Quick start

```
pip install pymupdf fonttools pillow playwright          # tested with PyMuPDF 1.28, Python 3.12
python3 -I examples/make_sample.py                        # writes examples/sample.pdf

python3 -I tools/extract.py examples/sample.pdf 1 --out out          # -> out/page-1.json
python3 -I tools/render.py out/page-1.json                           # -> out/page-1.svg
python3 -I tools/check.py examples/sample.pdf 1 out/page-1.svg       # similarity + side-by-side image
```

`check.py` draws the SVG in a real browser with Playwright. Run `playwright install chromium` once, or set
`CHROME=/path/to/chrome`.

### When the PDF's text is wrong: repair it from the glyph shapes

The text in a PDF comes from a map from glyphs to characters (ToUnicode). That map is sometimes missing or
wrong (`glyphs_unmapped` in the report counts these glyphs). The glyph shapes themselves are always right, so:

```
python3 -I tools/glyph_sheet.py out/page-*.json --html out/glyphs.html   # every glyph, drawn from its outline
# read the right text off the red cells, write it down:
echo '{"NotoNaskhArabic-Regular": {"446": "ل", "452": "ل", "12": "إ"}}' > fixes.json
python3 -I tools/extract.py examples/sample.pdf 1 --out out --fixes fixes.json
```

You do this once per font, not once per page, and the fix then applies to the whole document.

## The page model (`page-N.json`)

| key | content |
|---|---|
| `page` | number, width, height (PDF points, origin top-left, y down) |
| `shapes` | vector paths: SVG path data, fill, stroke, width, even-odd rule, opacity, dashes, `seq` |
| `images` | box, saved file, `seq` |
| `glyphs` | every drawn glyph: text, glyph id, font, origin `x`/`y`, `bbox`, size, direction, colour, opacity, mode (fill / stroke / invisible), `hidden`, `seq` |
| `fonts` | for each embedded font program: units per em and the outline (SVG path) of every glyph used |
| `lines` | the text in reading order: runs of same-style text with their box, colour and direction; runs with the same `line` share a baseline |
| `report` | counts to check: glyphs with no outline font, unmapped glyphs, hidden glyphs, fonts with several subsets |

`seq` is the drawing order. Draw everything sorted by `seq` and you get the page back. That is all
`tools/render.py` does.

## When you still need OCR

- **Scanned documents.** If the page is one big image, there are no instructions to read. Check first: if
  `glyphs` is empty and `images` covers the page, it's a scan.
- **Text inside images** (screenshots, photos, scanned figures).
- **Invisible OCR layers.** Some PDFs are scans with OCR text added in invisible mode. The tool marks these
  glyphs `mode: invisible`; their text is someone else's OCR, with its errors.

For everything else, which is most PDFs made by a program (Word, LaTeX, InDesign, browsers, report generators),
reading the instructions is exact and much cheaper.

## Limits of this implementation

It shows the method and is small on purpose (about 530 lines in all). It does not handle:
- **Type 3 fonts:** glyphs defined as little drawing programs, common in matplotlib charts. They fall back to
  plain text.
- **Clipping paths, shadings and gradients, blend modes, soft masks, annotations and form fields.** Layout
  programs build drop shadows and feathering from soft-masked, multiplied fills and images. Without the masks
  these come out as solid dark shapes, so such pages look darker when rebuilt. Their text is not affected.
- **Horizontal text scaling.**

[METHOD.md](METHOD.md) explains how each of these fits in.

## Files

```
METHOD.md               the method in full, with the pitfalls and how to handle them
tools/extract.py        PDF page -> page model (JSON)
tools/render.py         page model -> SVG
tools/check.py          rebuilt SVG vs the PDF's own rendering, in a real browser
tools/glyph_sheet.py    every glyph next to its claimed text, to repair broken text maps
examples/make_sample.py builds examples/sample.pdf; examples/sample-fixes.json repairs its 3 unmapped glyphs
tests/test_tools.py     checks on the sample, including the visual comparison
```
