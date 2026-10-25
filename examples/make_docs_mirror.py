"""Copy the website into docs/, so it works whichever GitHub Pages source is chosen: / (root) or /docs.

    python3 -I examples/make_docs_mirror.py

docs/ gets byte-identical copies of preview.html, index.html and .nojekyll, plus every file those pages load
(site/ and the demo PDF), so all relative links keep working. Run it after changing any of them; the tests fail
if docs/ is out of date.
"""
import os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ['preview.html', 'index.html', '.nojekyll', 'examples/demo-invoice.pdf']
DIRS = ['site']


def mirror():
    docs = f'{ROOT}/docs'
    shutil.rmtree(docs, ignore_errors=True)
    for f in FILES:
        os.makedirs(os.path.dirname(f'{docs}/{f}'), exist_ok=True)
        shutil.copyfile(f'{ROOT}/{f}', f'{docs}/{f}')
    for d in DIRS:
        shutil.copytree(f'{ROOT}/{d}', f'{docs}/{d}')
    return docs


if __name__ == '__main__':
    print('mirrored into', mirror())
