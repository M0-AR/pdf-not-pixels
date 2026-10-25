"""Record the demo media used by README.md and preview.html, from the real live demo page.

    python3 -I examples/make_media.py          # needs Playwright (+ CHROME=/path/to/chrome if needed) and ffmpeg

Writes site/media/: demo.mp4 and demo.gif (the live demo, step by step), hero.png, xray.png, reveal.png,
inspect.png, cost.png, academy.png and check.png (rebuilt | original | difference).
"""
import functools, http.server, os, shutil, socketserver, subprocess, sys, tempfile, threading
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = f'{ROOT}/site/media'
W = 1280


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=ROOT)
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


def font(size):
    for f in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
              '/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf'):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def caption(img, step, text):
    """A caption bar above a frame: step number + one plain sentence."""
    bar = 76
    out = Image.new('RGB', (img.width, img.height + bar), (20, 33, 61))
    out.paste(img, (0, bar))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((24, 18, 64, 58), 10, fill=(230, 57, 70))
    d.text((44, 38), str(step), font=font(24), fill='white', anchor='mm')
    d.text((84, 38), text, font=font(26), fill='white', anchor='lm')
    return out


def main():
    os.makedirs(MEDIA, exist_ok=True)
    httpd, base = serve()
    exe = os.environ.get('CHROME')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(viewport={'width': W, 'height': 1000}, device_scale_factor=1)
        page.goto(f'{base}/preview.html')
        page.evaluate("try { localStorage.clear() } catch (e) {}")
        page.wait_for_function('document.body.dataset.ready')
        page.add_style_tag(content='nav.top{display:none} video{display:none}')

        def demo_shot():
            # from the toolbar to the bottom of the rebuilt page, in page (not window) coordinates
            y0, y1 = page.evaluate("""() => {
                const top = el => el.getBoundingClientRect().top + scrollY;
                const st = document.querySelector('#stage');
                return [top(document.querySelector('#demo .toolbar')) - 8, top(st) + st.offsetHeight + 8]; }""")
            path = tempfile.mktemp(suffix='.png')
            page.screenshot(path=path, clip={'x': 0, 'y': y0, 'width': W, 'height': y1 - y0}, full_page=True)
            return Image.open(path).convert('RGB')

        total = page.evaluate("model.glyphs.findIndex(g => g.text === 'T' && g.color === '#2a9d8f')")
        steps = [
            ('This invoice is redrawn from the data in the PDF. It is not a picture.', lambda: None),
            ('Click any character: exact font, size, colour and position.',
             lambda: page.locator(f'rect.hit[data-i="{total}"]').click(force=True)),
            ('X-ray: every character, shape and image inside the file.', lambda: page.click('[data-mode=xray]')),
            ('A black box hides a note. The words are still in the file.', lambda: page.click('#reveal')),
            ('Everything is data: recolour, restyle, reuse.',
             lambda: (page.click('[data-mode=normal]'), page.click('#reveal'), page.click('#recolor'))),
        ]
        frames = []
        for i, (text, act) in enumerate(steps, 1):
            act()
            page.wait_for_timeout(250)
            frames.append(caption(demo_shot(), i, text))
            if i == 2:
                frames[-1].save(f'{MEDIA}/inspect.png')
            if i == 4:
                frames[-1].save(f'{MEDIA}/reveal.png')
        frames[0].save(f'{MEDIA}/hero.png')

        # stills
        page.click('#reset'); page.click('[data-mode=xray]'); page.wait_for_timeout(200)
        page.locator('#stage').screenshot(path=f'{MEDIA}/xray.png')
        page.click('#reset')
        page.locator('#cost').screenshot(path=f'{MEDIA}/cost.png')
        page.locator('#academy .opts button').nth(1).click()
        page.locator('#academy .opts button').nth(4).click()
        page.wait_for_timeout(200)
        page.locator('#academy').screenshot(path=f'{MEDIA}/academy.png')
        page.evaluate("try { localStorage.clear() } catch (e) {}")
        browser.close()
    httpd.shutdown()

    # video: hold each step, cross-fade between them
    tmp = tempfile.mkdtemp()
    h = max(f.height for f in frames)
    frames = [f.resize((W, h)) if f.height != h else f for f in frames]
    n = 0
    for k, f in enumerate(frames):
        for _ in range(30):                      # 2.5 s at 12 fps
            f.save(f'{tmp}/f{n:04d}.png'); n += 1
        nxt = frames[(k + 1) % len(frames)]
        for t in range(1, 7):                    # 0.5 s cross-fade
            Image.blend(f, nxt, t / 7).save(f'{tmp}/f{n:04d}.png'); n += 1
    ff = shutil.which('ffmpeg')
    subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', '12', '-i', f'{tmp}/f%04d.png', '-vf',
                    'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '30',
                    '-movflags', '+faststart', f'{MEDIA}/demo.mp4'], check=True)
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', f'{MEDIA}/demo.mp4', '-vf',
                    'fps=8,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];'
                    '[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle', f'{MEDIA}/demo.gif'], check=True)
    shutil.rmtree(tmp)

    # rebuilt | original | difference, from the command-line tools
    out = tempfile.mkdtemp()
    py = sys.executable
    subprocess.run([py, '-I', f'{ROOT}/tools/extract.py', f'{ROOT}/examples/demo-invoice.pdf', '1', '--out', out,
                    '--fixes', f'{ROOT}/examples/demo-fixes.json'], check=True, capture_output=True)
    subprocess.run([py, '-I', f'{ROOT}/tools/render.py', f'{out}/page-1.json'], check=True, capture_output=True)
    subprocess.run([py, '-I', f'{ROOT}/tools/check.py', f'{ROOT}/examples/demo-invoice.pdf', '1', f'{out}/page-1.svg',
                    '--png', f'{MEDIA}/check.png'], check=True, capture_output=True)
    im = Image.open(f'{MEDIA}/check.png'); im.resize((1400, round(im.height * 1400 / im.width))).save(f'{MEDIA}/check.png')
    shutil.rmtree(out)
    for f in sorted(os.listdir(MEDIA)):
        print(f'{f:12} {os.path.getsize(f"{MEDIA}/{f}") / 1024:8.0f} KB')


if __name__ == '__main__':
    main()
