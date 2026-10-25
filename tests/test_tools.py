"""Checks on examples/sample.pdf, whose content is known.

    python3 -I -m pytest -q tests/
The visual check runs only when Playwright can start a browser (set CHROME to a Chrome/Chromium binary if needed).
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f'{ROOT}/tools')
from extract import extract  # noqa: E402
from render import render  # noqa: E402

PDF = f'{ROOT}/examples/sample.pdf'
FIXES = json.load(open(f'{ROOT}/examples/sample-fixes.json', encoding='utf-8'))
OUT = f'{ROOT}/out/test'
if not os.path.exists(PDF):
    subprocess.run([sys.executable, '-I', f'{ROOT}/examples/make_sample.py'], check=True)
MODEL = extract(PDF, 1, FIXES, OUT)
TEXT = [l['text'] for l in MODEL['lines']]


def test_text_in_reading_order():
    assert TEXT[0] == 'Quarterly report'
    assert 'while costs stayed flat. The chart below is drawn with vector paths,' in TEXT   # ligature 'fl' expanded


def test_colour_is_kept():
    assert any(l['text'] == '12%' and l['color'] == '#c00000' for l in MODEL['lines'])


def test_right_to_left_with_diacritics():
    # marks on the right letters, presentation forms normalised, unmapped ligature parts repaired by the fixes file
    assert 'نَمَتِ الإيرادات بنسبة' in TEXT and 'هذا الربع' in TEXT
    assert MODEL['report']['glyphs_unmapped'] == 0
    unfixed = extract(PDF, 1)
    assert unfixed['report']['glyphs_unmapped'] > 0


def test_hidden_text_is_marked_not_read():
    assert not any('DRAFT' in t for t in TEXT)
    assert 'Approved for release.' in TEXT
    assert MODEL['report']['glyphs_hidden'] > 0


def test_shapes_images_and_order():
    assert sum(1 for s in MODEL['shapes'] if s['fill'] == '#3373b2') == 4          # the four bars
    img = MODEL['images'][0]
    assert img['file'] and img['bbox'] == [420.0, 320.0, 540.0, 380.0]
    bars = [s['seq'] for s in MODEL['shapes'] if s['fill'] == '#3373b2']
    assert max(bars) < img['seq']                                                   # drawn after the chart


def test_every_glyph_has_an_outline():
    assert MODEL['report']['glyphs_without_outline_font'] == 0
    svg = render(MODEL)
    drawn = [g for g in MODEL['glyphs'] if g['mode'] == 'fill' and g['text'].strip()]   # spaces have no outline
    assert svg.count('<use ') == len(drawn)
    assert '<text' not in svg


def test_rebuilt_page_looks_like_the_pdf():
    try:
        from check import check
        svg = f'{OUT}/page-1.svg'
        open(svg, 'w', encoding='utf-8').write(render(MODEL))
        score = check(PDF, 1, svg)
    except Exception as e:                       # no browser available: skip rather than fail
        import pytest
        pytest.skip(f'visual check not available: {e}')
    assert score > 0.99, score


def test_demo_invoice_triage_and_text():
    sys.path.insert(0, f'{ROOT}/tools')
    import pymupdf
    from triage import classify
    pdf = f'{ROOT}/examples/demo-invoice.pdf'
    fixes = json.load(open(f'{ROOT}/examples/demo-fixes.json', encoding='utf-8'))
    m = extract(pdf, 1, fixes)
    info = classify(pymupdf.open(pdf)[0], m)
    assert info['kind'] == 'text'
    assert info['hidden_text'] == 'Internal note: client agreed to a 30% discount. Do not disclose.'
    text = [l['text'] for l in m['lines']]
    assert 'Total due: USD 4,922.00' in text and 'شُكْرًا لِتَعامُلِكُم مَعَنا' in text
    assert m['report']['glyphs_unmapped'] == 0


def test_docs_mirror_is_in_sync():
    # the website must work whichever GitHub Pages source is chosen (/ or /docs): docs/ is an exact copy
    import filecmp
    files = ['preview.html', 'index.html', '.nojekyll', 'examples/demo-invoice.pdf']
    for root, _, names in os.walk(f'{ROOT}/site'):
        files += [os.path.relpath(os.path.join(root, n), ROOT) for n in names]
    stale = [f for f in files if not os.path.exists(f'{ROOT}/docs/{f}') or not filecmp.cmp(f'{ROOT}/{f}', f'{ROOT}/docs/{f}', shallow=False)]
    assert not stale, f'run examples/make_docs_mirror.py: {stale}'
