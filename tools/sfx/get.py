#!/usr/bin/env python3
"""Fetch free (CC0) sound effect packs by Kenney (kenney.nl), convert every sound to a small mono MP3,
and list them in index.json with their length and loudness. Runs in GitHub Actions (.github/workflows/sfx.yml);
the results go to the branch 'sfx-out'. Kenney's sounds are public domain (CC0): free for any game."""
import io, json, os, re, subprocess, sys, tempfile, urllib.request, zipfile

OUT = os.environ.get('SFX_OUT', 'out')
PACKS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packs.json')))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def probe(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
    dur = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r.stderr); mx = re.search(r'max_volume: ([-\d.]+) dB', r.stderr); mean = re.search(r'mean_volume: ([-\d.]+) dB', r.stderr)
    d = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0
    return round(d, 3), float(mx.group(1)) if mx else None, float(mean.group(1)) if mean else None


def main():
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for pack in PACKS:
        try:
            page = get('https://kenney.nl/assets/' + pack).decode('utf8', 'ignore')
            links = re.findall(r'href="([^"]+?\.zip)"', page)
            if not links: print(pack, 'no download link found'); continue
            url = links[0] if links[0].startswith('http') else 'https://kenney.nl' + links[0]
            print(pack, '<-', url, flush=True)
            z = zipfile.ZipFile(io.BytesIO(get(url)))
        except Exception as e:
            print(pack, 'FAILED', e); continue
        folder = os.path.join(OUT, pack); os.makedirs(folder, exist_ok=True)
        for name in z.namelist():
            low = name.lower()
            if low.endswith(('license.txt', 'license.md')):
                open(os.path.join(folder, 'License.txt'), 'wb').write(z.read(name)); continue
            if not low.endswith(('.ogg', '.wav', '.mp3', '.flac')): continue
            base = re.sub(r'[^A-Za-z0-9_\-]+', '_', os.path.splitext(os.path.basename(name))[0])
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1]) as tmp:
                tmp.write(z.read(name)); tmp.flush()
                dst = os.path.join(folder, base + '.mp3')
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp.name, '-ac', '1', '-ar', '44100', '-b:a', '96k', dst], check=False)
            if os.path.exists(dst):
                index[pack + '/' + base] = probe(dst)
        print(pack, 'sounds so far', len(index), flush=True)
    json.dump(index, open(os.path.join(OUT, 'index.json'), 'w'), indent=0, sort_keys=True)
    print('done', len(index), 'sounds')


if __name__ == '__main__':
    main()
