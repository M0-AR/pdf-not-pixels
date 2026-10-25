# The method: rebuild a PDF from its own drawing instructions

This is a way to get **exact, controllable data** out of a PDF without OCR or AI: every character, shape and
image, with its position, style and drawing order, plus the text in reading order. The result can be redrawn so it
looks the same as the PDF, and then changed freely.

The steps below are in the order you apply them. Each one names the pitfalls that real files contain and how to
handle them. The code in `tools/` implements most of it. Not in `tools/`:
- Type 3 glyph outlines (2)
- bracket swapping (4c)
- per-style runs for overlapping texts (4f)
- the clipping check (4g)
- alignment to reference data (5), which depends on your reference.

---

## 0. Triage: is there anything to read?

Open the page and list what it draws (step 1). A page whose only content is one image covering the page is a
**scan**: there are no characters to read, and OCR is the right tool. Watch also for glyphs drawn in *invisible*
mode (text render mode 3) over an image. That is an OCR layer someone else added, with their errors.

Everything else (PDFs exported from Word, LaTeX, InDesign, browsers, reporting tools) carries its content as
instructions, and the rest of this method applies.

## 1. Read the instructions

PyMuPDF exposes the page's content stream as data:

| call | gives |
|---|---|
| `page.get_texttrace()` | every text span: font name, size, colour, opacity, render mode (fill / stroke / invisible), writing direction, and per glyph: Unicode, **glyph id**, origin, bbox |
| `page.get_drawings()` | every vector path: segments, fill, stroke, width, even-odd rule, opacities, dashes |
| `page.get_image_info(xrefs=True)` | every image placement: box, transform, image object |
| `page.get_bboxlog()` | every drawing operation **in order** |

Both text spans and paths carry a `seqno`, which is their index in the bbox log. Images don't, but you can find
their `fill-image` entry in the log by matching boxes. With that, **every item on the page has its place in the
drawing order**. You need it to redraw the page, and also to know what is hidden (step 4g).

Keep the glyph id, not just the Unicode text. The glyph id names the *shape*. The Unicode is only the file's
claim about what that shape means, and that claim can be wrong (step 4a).

## 2. Get the glyph shapes from the embedded fonts

To draw a glyph exactly, use its outline from the font program the PDF embeds. Don't use a system font that
happens to have the same name. `doc.extract_font(xref)` returns the program; fontTools reads it and draws any
glyph into an SVG path.

- **TrueType / OpenType** (`ttf`, `otf`): glyph id = index in the font's glyph order.
- **Bare CFF** (`cid`, `cff`): read with `fontTools.cffLib`. Glyph id = index in the charset.
- **Type 1** (`pfa`, `pfb`, classic PostScript fonts, e.g. from LaTeX): read with `fontTools.t1Lib`.
  - PDFs often drop the font's trailer (512 zeros and `cleartomark`), and the parser then fails. Append it.
  - Glyph ids follow the order of the CharStrings dictionary, with `.notdef` moved to id 0.
  - Verify this mapping on your files: the glyph names must agree with the Unicode the PDF claims.
- **The 14 standard fonts, not embedded** (Times-Roman, Helvetica, …): the viewer supplies them.
  `pymupdf.Font(name).buffer` is MuPDF's own copy, and the glyph ids in the trace refer to it.
- **Type 3** fonts define each glyph as a small PDF drawing program (CharProcs), so there is no outline font to
  read. They are common in charts made with matplotlib. You would have to interpret the glyph procedures as
  paths. `tools/` doesn't do this and falls back to drawing the text.

**One font name, several programs.** A file can embed the same font name several times as different subsets, and
the same glyph id means a different shape in each. The trace gives you the name, not the program. Choose the
program for each span by:
1. which programs have outlines for all of the span's glyph ids, then
2. which one's **advance widths** match the spacing of the glyphs on the page.

The second test is decisive: the wrong subset puts the right number of glyphs in the wrong places.

## 3. Rebuild the page

Draw every item in `seq` order:

- **Paths:** as SVG paths with their fill, stroke and fill rule.
- **Images:** in their boxes.
- **Glyphs:** the outline (font units, y up) placed with the matrix
  `[k·ux, k·uy, k·uy, −k·ux, x, y]`, where `k = size / unitsPerEm` and `(ux, uy)` is the writing direction.
  This one formula also handles rotated text.
- **Fill and stroke passes:** some producers fake bold by drawing a glyph twice, filled and then stroked. Keep
  both passes in the drawing.
- **Invisible glyphs:** skip them when drawing.

The output depends on no fonts at all and looks the same in every viewer.

Then **check it**: render the SVG in a real browser, render the PDF page with PyMuPDF, and compare
(`tools/check.py`). Sort pages by score and look at the worst ones side by side. The score tells you *where*
to look; your eyes tell you *what* is wrong. A page can score well and still have a wrong label inside a figure.

## 4. Get the text right

Drawing a page and reading it are different problems. The page can look perfect while its text is wrong.

### 4a. The glyph-to-text map can be broken

The text comes from the font's ToUnicode map, written by whatever produced the PDF. It can be:
- **Missing:** you get U+FFFD or nothing. Typical for ligature glyphs and maths fonts.
- **Wrong:** a glyph claims to be a different letter than it looks like. The same glyph can even be claimed as
  different letters on different pages.

The shape never lies, so repair by shape:
1. Make a **glyph sheet**: every glyph a font uses, drawn from its outline, next to its claimed text
   (`tools/glyph_sheet.py`).
2. Read the right text off the shapes and write a table: font → glyph id → text.
3. Apply the table when extracting (`--fixes`).

It's done once per font for the whole document. Then search all pages for characters that should never occur
in your text. That tells you whether the table is complete.

Caveat: in **simple (non-CID) fonts**, each subset numbers its glyphs from scratch. A low glyph id can then mean
different shapes in different subsets of the "same" font. Key fixes by the font program, or only fix ids that
you have checked are stable.

### 4b. Presentation forms and ligatures

Producers may write positional letter forms (Arabic initial / medial / final forms) or ligature characters
(`ﬂ`) into the text. Normalise those code points (NFKC on the presentation-form ranges) to get plain,
searchable text. Leave the rest of the text alone.

### 4c. Reading order is not drawing order

Glyphs are usually drawn left to right in visual order, even for right-to-left scripts. To get logical order:
1. Decide each line's direction from its letters only. Digits and punctuation are neutral, so a line like «م 2026 - 2025» is right-to-left.
2. For right-to-left lines, sort by descending position.
3. Restore left-to-right runs inside them (Latin words, numbers), which the sort reversed.
4. Brackets in right-to-left text are mirrored by the bidi algorithm when displayed. If a producer stored them
   in visual order, swap them in runs that contain no right-to-left letters.

### 4d. Diacritics are separate glyphs

Marks (harakat, niqqud, combining accents) are drawn as their own, often zero-width, glyphs. Neither their
position in the stream nor their origin is reliable:
- **Order varies by producer:** some put a mark just before its letter, others just after.
- **The origin isn't the ink:** fonts move marks onto their letter by shifting the outline, so a mark's origin
  can sit on the neighbouring letter.
- **Spans can be wrong:** some producers put a mark in an unrelated span, even one on another line.

So attach by where the mark is **drawn**:
1. Take the middle of the mark's outline (from the font) and find the letter on the same baseline whose box
   contains it. Search all spans.
2. Only if no letter contains it, fall back to the letter drawn just before or after it in the same span.
3. Only letters take marks, never digits or punctuation.

For scripts where one wrong mark changes the meaning, check pages from each producer by hand.

### 4e. Spaces

- **No spaces at all.** Some producers (TeX, many layout engines) never draw a space character; a word gap is
  just distance. Insert a space where the gap between letters is wider than about 0.2 em.
- **Stray spaces.** Some producers (word processors) scatter space glyphs from *other* fonts over the text,
  sometimes in the middle of a word. They break runs and words apart. A space in another font is a word gap only
  if it falls *between* letters, not on top of one.
- **Spaces in the wrong place.** With tight kerning, a real space's origin can fall inside the neighbouring
  letter's box, and sorting by position then puts it one letter off. A space that touches the glyph drawn just
  before it in the stream belongs right after that glyph.

Don't fix stray spaces by deleting every space that overlaps a letter: real spaces overlap wide letters too.
Compare the text before and after such a change across the whole document (step 6).

### 4f. Lines and runs

- **Baselines:** group glyphs into lines by baseline, in the text's own direction, so rotated text forms its own
  lines.
- **Superscripts and footnote marks** sit higher. Use a tolerance based on the larger font size on the line.
- **Style runs:** split a line into runs where the style changes (font, size, colour). Colour often carries
  meaning, such as highlighted words.
- **Overlapping texts:** two texts in different styles drawn over each other on one baseline (e.g. a note box
  over a footer) make the style alternate letter by letter. Detect that and build runs per style. Two
  overlapping texts in the *same* style can't be separated by style; use drawing order and occlusion (4g).

### 4g. Text that is in the file but not on the page

- **Covered:** a filled shape drawn **later** over the text hides it.
  - Mark glyphs under a later opaque, one-outline fill as hidden. Count outlines rather than trusting the
    even-odd flag: one outline has no hole, while a frame with a hole doesn't cover its inside.
  - Hidden text left in the reading text is a classic source of garbage, such as old words interleaved with the
    visible line.
- **Clipped:** text outside a clipping path. Check whether any dark pixels are drawn where the text would be.
- **Invisible:** render mode 3.

Keep hidden glyphs in the data, marked `hidden`, and leave them out of the text.

## 5. Use reference data when it exists

If the document reproduces content that exists somewhere in a trusted, structured form (a published standard, a
legal code, a product catalogue, a dataset, a canonical text), **don't take the text from the PDF at all**.
Match the PDF's glyph sequence to the reference and take the text, and its identifiers, from the reference.

- **Align, don't look up.** Align the glyph sequence with the reference sequence like a diff: dynamic
  programming with costs for a skip, a mismatch, and a swap of neighbours drawn out of order. Producers draw
  items out of order, drop marks, or use slightly different codes for the same thing (for example, a fixed
  offset in a private-use range).
- **Every leftover is a finding.** Something drawn but not in the reference, or in the reference but not drawn,
  needs a reason. Usually it's the document's own error. Record those in an errata list,
  *printed → intended*, and keep the data as printed.
- **Decorative labels:** titles drawn in a font with garbled text, or as small images, can't be read. Keep their
  position from the PDF and take their content from metadata you already have (section name, page number).

With a reference, the text is exact by construction, and the PDF only supplies positions, styles and colours.

## 6. Verify, at three levels, on every page

1. **Counts.** Per page: glyphs drawn vs. expected, glyphs without an outline font, unmapped glyphs, hidden
   glyphs. Anything non-zero has a known reason or is a bug.
2. **Known facts.** Regression tests on pages checked by hand: exact strings, diacritics, headers, the tricky
   cases you fixed. Each fix adds a test.
3. **Looks.**
   - Every page rebuilt and compared with the PDF's rendering.
   - The worst pages looked at side by side.
   - A sweep in a browser that loads every page and checks that everything in the data was drawn and nothing
     failed to load.

**After every fix, re-run every page** and compare the extracted text with the previous run, word by word:
- Which words disappeared?
- Which words are new?
- Which new words are two old words glued together (a lost space)?

A fix for one page silently breaking another is the most common failure in this work, and only a whole-document
comparison catches it.

## 7. Pitfalls in brief

| Symptom | Cause | Remedy |
|---|---|---|
| Text has U+FFFD or wrong letters | ToUnicode missing or wrong | glyph sheet → fixes by glyph id (4a) |
| Right glyph count, wrong shapes | several subsets share a font name | choose by outlines + advance widths (2) |
| Type 1 font won't parse | trailer missing | append zeros + `cleartomark` (2) |
| Words glued together | no space glyphs (TeX) | gap > 0.2 em = space (4e) |
| Word split in two | stray space from another font | foreign space counts only between letters (4e) |
| Space one letter off | origin inside a kerned neighbour | order after the glyph drawn before it (4e) |
| Diacritic one letter off, or missing | mark origin on a neighbour; mark put in another span | attach by the mark's ink, across spans (4d) |
| Garbage mixed into a line | hidden text under a later box | occlusion by drawing order (4g) |
| Each letter of rotated text on its own line | lines grouped in page coordinates | group in the text's own direction (4f) |
| Labels unreadable | decorative font or image | position from PDF, content from metadata (5) |
| Same page drawn twice in the file | duplicated pages | keep both as variants, choose one as main |

## 8. Where OCR and AI still fit

- **Scans and text inside images** need OCR.
- **AI models** are useful *after* extraction: for understanding the exact text you extracted, not for reading
  it. One limited use for vision is pointing at problems: comparing rebuilt and original pages to suggest where
  a human should look. Every fix should still come from the file's own data.
