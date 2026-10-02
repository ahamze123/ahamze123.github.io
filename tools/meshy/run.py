#!/usr/bin/env python3
"""Make the heroes' 3D models with Meshy. Runs on GitHub Actions (.github/workflows/meshy.yml) whenever
tools/meshy/queue.json changes on main, and saves everything to the 'meshy-out' branch:

  state.json        every Meshy task made so far, per hero (so a task is never paid for twice)
  log.txt           what happened, run by run
  library.json      Meshy's animation library (free to read)
  <hero>/thumb.png  Meshy's picture of the finished model
  <hero>/model.glb  the model with its skeleton (pictures inside made smaller)
  <hero>/walk.glb, run.glb   the walk and run that come with the skeleton (skeleton + clip only)
  <hero>/anims.glb  the extra animations, when bought for this hero (skeleton + clips only)
  <hero>/x_<set>.glb more moves to try (skeleton + clips only)

For every hero in queue.json 'heroes':
  1. image to 3D from tools/meshy/pics/<hero>.jpg (A-pose, textured, remeshed)   ~30 credits
  2. rigging (a skeleton, with a free walk and run)                               5 credits
  3. animations from the library, if the hero is in queue.json 'anims.heroes'      3 credits each
  4. more moves to try, queue.json 'extra': {"hero": {"set": [action ids]}}  ->  <hero>/x_<set>.glb   3 credits each
A step that already worked is never made again, unless the hero is listed in 'redo'.
No more than 'max_credits' are spent in one run.

Pictures (queue.json 'images', made before the heroes): {"name": {"prompt": "...", "ai_model": "gpt-image-2",
"aspect_ratio": "2:3", "refs": ["tools/meshy/pics/kira.jpg", "out:images/x.png"]}} -> images/<name>.png
  text to image (no refs) or image to image (1-5 reference pictures from the repo, or 'out:' a picture made earlier)
  3 to 12 credits each. A picture that worked is never made again, unless its name is in 'redo_images'.
"""
import base64, json, os, subprocess, sys, threading, time, traceback, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import glbtool  # noqa: E402

OUT = os.path.abspath(os.environ.get('MESHY_OUT', os.path.join(HERE, 'out')))
API = os.environ.get('MESHY_API', 'https://api.meshy.ai').rstrip('/')
KEY = os.environ.get('MESHY_API_KEY', '').strip()
POLL = float(os.environ.get('MESHY_POLL', '10'))
PUSH = os.environ.get('MESHY_PUSH', '') == '1'
COST = {'model': 30, 'rig': 5, 'anim': 3}
IMG_COST = {'nano-banana': 3, 'nano-banana-2': 6, 'nano-banana-pro': 9, 'gpt-image-2': 12, 'gpt-image-2-5-flare': 12, 'gpt-image-2-5-sunburst': 12}
ROOT = os.path.dirname(os.path.dirname(HERE))

lock = threading.Lock()
state = {'heroes': {}, 'runs': []}
run_info = {'spent': 0, 'limit': 0}
lines = []


def log(*a):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with lock:
        lines.append(line)


def save(push=False, msg='state'):
    with lock:
        os.makedirs(OUT, exist_ok=True)
        tmp = os.path.join(OUT, 'state.json.tmp')
        with open(tmp, 'w') as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(tmp, os.path.join(OUT, 'state.json'))
        with open(os.path.join(OUT, 'log.txt'), 'a') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
        lines.clear()
        if push and PUSH:
            try:
                subprocess.run(['git', '-C', OUT, 'add', '-A'], check=True)
                c = subprocess.run(['git', '-C', OUT, 'commit', '-qm', msg], capture_output=True)
                if c.returncode == 0:
                    subprocess.run(['git', '-C', OUT, 'push', '-q', 'origin', 'HEAD:meshy-out'], check=True, timeout=120)
            except Exception as e:  # the last step of the job pushes again
                print('push failed:', e, flush=True)


def api(method, path, body=None):
    """call Meshy. A request that makes a new task (POST) is only repeated when Meshy said 'too many requests',
    so a task is never made (and paid for) twice by mistake."""
    data = json.dumps(body).encode() if body is not None else None
    for k in range(8):
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode() or 'null'
                return json.loads(txt)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors='replace')[:600]
            again = e.code == 429 or (method == 'GET' and e.code >= 500)
            if again and k < 7:
                time.sleep(min(90, 5 * 2 ** k)); continue
            raise RuntimeError('%s %s: HTTP %s %s' % (method, path, e.code, msg))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if method == 'GET' and k < 7:
                time.sleep(min(90, 5 * 2 ** k)); continue
            raise RuntimeError('%s %s: %s' % (method, path, e))


def download(url, path):
    for k in range(6):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'block-buddies-meshy'})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
            return len(data)
        except Exception as e:
            if k == 5:
                raise RuntimeError('download failed: %s' % e)
            time.sleep(5 * 2 ** k)


def wait(kind, tid, who):
    """wait for a Meshy task to finish (kind: image-to-3d, rigging, animations)"""
    t0, last = time.time(), -1
    while True:
        t = api('GET', '/openapi/v1/%s/%s' % (kind, tid))
        st, pr = t.get('status'), t.get('progress', 0)
        if pr != last and (pr // 25 != last // 25 or st != 'IN_PROGRESS'):
            log(who, kind, st, '%s%%' % pr)
        last = pr
        if st in ('SUCCEEDED', 'FAILED', 'CANCELED', 'EXPIRED'):
            return t
        if time.time() - t0 > 60 * 60:
            raise RuntimeError('%s %s still not finished after an hour' % (kind, tid))
        time.sleep(POLL)


def budget(n):
    with lock:
        if run_info['spent'] + n > run_info['limit']:
            return False
        run_info['spent'] += n
        return True


def pic_uri(h):
    p = os.path.join(HERE, 'pics', h + '.jpg')
    if not os.path.exists(p):
        p = os.path.join(HERE, 'pics', h + '.png')
    mime = 'image/png' if p.endswith('.png') else 'image/jpeg'
    return 'data:%s;base64,%s' % (mime, base64.b64encode(open(p, 'rb').read()).decode())


def glb_info(path):
    d = glbtool.Doc.load(path)
    J = d.J
    tris = 0
    for m in J.get('meshes', []):
        for p in m['primitives']:
            a = J['accessors'][p['indices'] if 'indices' in p else p['attributes']['POSITION']]
            tris += a['count'] // 3
    return {'bytes': os.path.getsize(path), 'triangles': tris,
            'joints': max([len(s['joints']) for s in J.get('skins', [])] or [0]),
            'clips': [a.get('name', '') for a in J.get('animations', [])]}


def keep_glb(url, path, armature=False, shrink=1024):
    tmp = path + '.download'
    download(url, tmp)
    d = glbtool.Doc.load(tmp)
    if armature:
        d.armature_only()
    elif shrink:
        d.shrink_textures(shrink, 88)
    d.save(path)
    os.remove(tmp)
    return glb_info(path)


def anim_task(h, slot, key, g, ids, path):
    """one animation task (up to 10 moves from the library) for a rigged hero, saved as a skeleton + clips file"""
    who = '[%s]' % h
    a = slot.get(key)
    if a and (a.get('rig') != g['id'] or a.get('action_ids') != ids):
        a = None
    if not a or a.get('status') in ('FAILED', 'CANCELED', 'EXPIRED'):
        if not budget(COST['anim'] * len(ids)):
            log(who, 'animations skipped: this run may not spend more credits'); return False
        r = api('POST', '/openapi/v1/animations', {'rig_task_id': g['id'], 'action_ids': ids})
        a = slot[key] = {'id': r['result'], 'status': 'PENDING', 'rig': g['id'], 'action_ids': ids, 'made': time.strftime('%Y-%m-%d %H:%M')}
        log(who, 'animation task made', key, a['id'], ids)
        save(True, '%s: animation task %s' % (h, key))
    if a['status'] != 'SUCCEEDED' or not os.path.exists(path):
        t = wait('animations', a['id'], who)
        a.update(status=t.get('status'), credits=t.get('consumed_credits'), error=(t.get('task_error') or {}).get('message') or None)
        if t.get('status') != 'SUCCEEDED':
            log(who, 'animations FAILED:', key, a.get('error')); save(True, '%s: animations failed' % h); return False
        res = t.get('result') or {}
        a['file'] = keep_glb(res['animation_glb_url'], path, armature=True)
        log(who, 'animations', key, a['file'].get('clips'))
        save(True, '%s: animations %s' % (h, key))
    return True


def ref_uri(ref):
    """a reference picture as a data URI: a path in the repo, or 'out:<path>' for a picture made in an earlier run"""
    p = os.path.join(OUT, ref[4:]) if ref.startswith('out:') else os.path.join(ROOT, ref)
    raw = open(p, 'rb').read()
    mime = 'image/png' if raw[:4] == b'\x89PNG' else 'image/jpeg'
    return 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode())


def do_image(name, job, cfg):
    who = '[img %s]' % name
    S = state.setdefault('images', {})
    I = S.get(name)
    if I and name in (cfg.get('redo_images') or []) and I.get('run') != cfg.get('run'):
        S.setdefault('_old', []).append(I); I = None
    try:
        if not I or I.get('status') in ('FAILED', 'CANCELED', 'EXPIRED'):
            model = job.get('ai_model', 'nano-banana-pro')
            if not budget(IMG_COST.get(model, 12)):
                log(who, 'skipped: this run may not spend more credits'); return
            body = {'ai_model': model, 'prompt': job['prompt']}
            for k in ('aspect_ratio', 'remove_background', 'generate_multi_view', 'pose_mode'):
                if k in job: body[k] = job[k]
            refs = (job.get('refs') or [])[:5]
            kind = 'image-to-image' if refs else 'text-to-image'
            if refs: body['reference_image_urls'] = [ref_uri(r) for r in refs]
            r = api('POST', '/openapi/v1/%s' % kind, body)
            I = S[name] = {'id': r['result'], 'kind': kind, 'status': 'PENDING', 'run': cfg.get('run'), 'made': time.strftime('%Y-%m-%d %H:%M'),
                           'settings': {k: v for k, v in body.items() if k != 'reference_image_urls'}, 'refs': refs}
            log(who, kind, 'task made', I['id'])
            save(True, 'picture %s: task' % name)
        if I['status'] != 'SUCCEEDED' or not all(os.path.exists(os.path.join(OUT, f)) for f in I.get('files') or ['-']):
            t = wait(I['kind'], I['id'], who)
            I.update(status=t.get('status'), credits=t.get('consumed_credits'), error=(t.get('task_error') or {}).get('message') or None)
            if t.get('status') != 'SUCCEEDED':
                log(who, 'picture FAILED:', I.get('error')); save(True, 'picture %s failed' % name); return
            urls = t.get('image_urls') or []
            I['files'] = []
            for k, u in enumerate(urls):
                base = os.path.join(OUT, 'images', name + ('' if len(urls) == 1 else '_%d' % k))
                download(u, base + '.tmp')
                head = open(base + '.tmp', 'rb').read(4)
                path = base + ('.png' if head == b'\x89PNG' else '.jpg')
                os.replace(base + '.tmp', path)
                I['files'].append(os.path.relpath(path, OUT))
            log(who, 'saved', I['files'])
            save(True, 'picture %s' % name)
    except Exception as e:
        log(who, 'ERROR', e)
        traceback.print_exc()
        if I is not None: I['last_error'] = str(e)[:500]
        save(True, 'picture %s: error' % name)


def do_hero(h, cfg):
    who = '[%s]' % h
    S = state['heroes'].setdefault(h, {})
    M = dict(cfg.get('model', {}))
    M.update((cfg.get('per') or {}).get(h, {}))
    redo = h in (cfg.get('redo') or [])
    folder = os.path.join(OUT, h)
    try:
        # ---------- 1. image to 3D ----------
        m = S.get('model')
        if redo and m and m.get('status') == 'SUCCEEDED' and m.get('run') != cfg.get('run'):
            S.setdefault('old', []).append({k: S.get(k) for k in ('model', 'rig', 'anim') if S.get(k)})
            S.pop('model', None); S.pop('rig', None); S.pop('anim', None); m = None
        if not m or m.get('status') in ('FAILED', 'CANCELED', 'EXPIRED'):
            if not os.path.exists(os.path.join(HERE, 'pics', h + '.jpg')) and not os.path.exists(os.path.join(HERE, 'pics', h + '.png')):
                log(who, 'no picture in tools/meshy/pics'); return
            if not budget(COST['model']):
                log(who, 'skipped: this run may not spend more credits'); return
            body = {'image_url': pic_uri(h), 'ai_model': M.get('ai_model', 'latest'), 'should_texture': True,
                    'enable_pbr': False, 'should_remesh': True, 'topology': M.get('topology', 'triangle'),
                    'target_polycount': int(M.get('target_polycount', 20000)), 'pose_mode': M.get('pose_mode', 'a-pose')}
            for k in ('texture_prompt', 'texture_resolution', 'image_enhancement', 'model_type', 'geometry_resolution'):
                if k in M: body[k] = M[k]
            r = api('POST', '/openapi/v1/image-to-3d', body)
            m = S['model'] = {'id': r['result'], 'status': 'PENDING', 'run': cfg.get('run'), 'made': time.strftime('%Y-%m-%d %H:%M'),
                              'settings': {k: v for k, v in body.items() if k != 'image_url'}}
            log(who, 'model task made', m['id'])
            save(True, '%s: model task' % h)
        if m['status'] != 'SUCCEEDED':
            t = wait('image-to-3d', m['id'], who)
            m.update(status=t.get('status'), credits=t.get('consumed_credits'), error=(t.get('task_error') or {}).get('message') or None)
            if t.get('status') != 'SUCCEEDED':
                log(who, 'model FAILED:', m.get('error')); save(True, '%s: model failed' % h); return
            m['thumb_url'] = t.get('thumbnail_url')
            if t.get('thumbnail_url'):
                try:
                    download(t['thumbnail_url'], os.path.join(folder, 'thumb.png'))
                    from PIL import Image
                    im = Image.open(os.path.join(folder, 'thumb.png')); im.thumbnail((512, 512)); im.save(os.path.join(folder, 'thumb.png'), optimize=True)
                except Exception as e:
                    log(who, 'thumbnail:', e)
            save(True, '%s: model ready' % h)
        # ---------- 2. rigging ----------
        if cfg.get('rig') is False:
            return
        R = cfg.get('rig') or {}
        g = S.get('rig')
        if g and g.get('model') != m['id']:
            g = None
        if not g or g.get('status') in ('FAILED', 'CANCELED', 'EXPIRED'):
            if not budget(COST['rig']):
                log(who, 'rigging skipped: this run may not spend more credits'); return
            body = {'input_task_id': m['id']}
            if 'height_meters' in R: body['height_meters'] = R['height_meters']
            r = api('POST', '/openapi/v1/rigging', body)
            g = S['rig'] = {'id': r['result'], 'status': 'PENDING', 'model': m['id'], 'made': time.strftime('%Y-%m-%d %H:%M')}
            log(who, 'rig task made', g['id'])
            save(True, '%s: rig task' % h)
        if g['status'] != 'SUCCEEDED' or not os.path.exists(os.path.join(folder, 'model.glb')):
            t = wait('rigging', g['id'], who)
            g.update(status=t.get('status'), credits=t.get('consumed_credits'), error=(t.get('task_error') or {}).get('message') or None)
            if t.get('status') != 'SUCCEEDED':
                log(who, 'rigging FAILED:', g.get('error')); save(True, '%s: rig failed' % h); return
            res = t.get('result') or {}
            files = g['files'] = {}
            files['model'] = keep_glb(res['rigged_character_glb_url'], os.path.join(folder, 'model.glb'))
            ba = res.get('basic_animations') or {}
            for clip in ('walking', 'running'):
                url = ba.get(clip + '_armature_glb_url') or ba.get(clip + '_glb_url')
                if url:
                    files[clip] = keep_glb(url, os.path.join(folder, ('walk' if clip == 'walking' else 'run') + '.glb'), armature=True)
            log(who, 'rigged:', json.dumps(files))
            save(True, '%s: rigged' % h)
        # ---------- the model again with bigger pictures (free: the finished rigging task is only read again) ----------
        if h in (cfg.get('refetch') or []) and not os.path.exists(os.path.join(folder, 'model_full.glb')):
            t = api('GET', '/openapi/v1/rigging/%s' % g['id'])
            url = (t.get('result') or {}).get('rigged_character_glb_url')
            if url:
                tmp = os.path.join(folder, 'model_full.glb.download'); download(url, tmp)
                d0 = glbtool.Doc.load(tmp)
                sizes = []
                for im in d0.J.get('images', []):
                    try:
                        from PIL import Image
                        import io as _io
                        pic = Image.open(_io.BytesIO(d0.view_bytes(im['bufferView']))); sizes.append('%dx%d %s' % (pic.size[0], pic.size[1], im.get('mimeType', '')))
                    except Exception as e:
                        sizes.append(str(e)[:60])
                d0.shrink_textures(int(cfg.get('refetch_max', 2048)), int(cfg.get('refetch_quality', 92)))
                d0.save(os.path.join(folder, 'model_full.glb')); os.remove(tmp)
                S['full'] = {'pictures': sizes, 'bytes': os.path.getsize(os.path.join(folder, 'model_full.glb'))}
                log(who, 'model with bigger pictures:', json.dumps(S['full']))
                save(True, '%s: bigger pictures' % h)
        # ---------- 3. animations ----------
        A = cfg.get('anims') or {}
        ids = [int(x) for x in (A.get('action_ids') or [])][:10]
        if h in (A.get('heroes') or []) and ids:
            if not anim_task(h, S, 'anim', g, ids, os.path.join(folder, 'anims.glb')):
                return
        # ---------- 4. more moves to try: one file per set, x_<set>.glb ----------
        sets = S.setdefault('extra', {})
        for name, xids in ((cfg.get('extra') or {}).get(h) or {}).items():
            xids = [int(x) for x in xids][:10]
            if xids:
                anim_task(h, sets, name, g, xids, os.path.join(folder, 'x_%s.glb' % name))
    except Exception as e:
        log(who, 'ERROR', e)
        traceback.print_exc()
        S['last_error'] = str(e)[:500]
        save(True, '%s: error' % h)


def main():
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, 'state.json')
    if os.path.exists(p):
        state.update(json.load(open(p)))
    cfg = json.load(open(os.path.join(HERE, 'queue.json')))
    run_info['limit'] = int(cfg.get('max_credits', 150))
    state['runs'].append({'run': cfg.get('run'), 'at': time.strftime('%Y-%m-%d %H:%M'), 'heroes': cfg.get('heroes'), 'limit': run_info['limit']})
    if not KEY:
        log('MESHY_API_KEY is not set yet: add it in the repository settings (Secrets and variables > Actions). Nothing was made.')
        save(); return 0
    log('run', cfg.get('run'), 'heroes', cfg.get('heroes'), 'max credits', run_info['limit'])
    for path, name in (('/openapi/v1/balance', 'balance.json'),):
        try:
            with open(os.path.join(OUT, name), 'w') as f: json.dump(api('GET', path), f, indent=1)
        except Exception as e:
            log('could not read', path, e)
    if cfg.get('library') or not os.path.exists(os.path.join(OUT, 'library.json')):
        # the animation library is free to read: every page, and a few searches for the moves the game needs
        lib = {'pages': [], 'search': {}}
        try:
            lib['first'] = api('GET', '/openapi/v1/animations/library')
        except Exception as e:
            log('could not read the animation library', e)
        for n in range(1, 15):
            try:
                pg = api('GET', '/openapi/v1/animations/library?page_size=50&page_num=%d' % n)
            except Exception as e:
                log('library page', n, e); break
            lib['pages'].append(pg)
            items = pg if isinstance(pg, list) else next((v for v in (pg or {}).values() if isinstance(v, list)), [])
            if len(items) < 50: break
        for term in ('idle', 'jump', 'jab', 'punch', 'cheer', 'victory', 'wave', 'dead', 'fall', 'knock', 'sit', 'happy', 'run', 'walk', 'fly', 'swim'):
            try:
                lib['search'][term] = api('GET', '/openapi/v1/animations/library?search=' + term)
            except Exception as e:
                lib['search'][term] = str(e)[:200]
        with open(os.path.join(OUT, 'library.json'), 'w') as f: json.dump(lib, f, indent=1)
        log('animation library saved')
    save(True, 'run %s started' % cfg.get('run'))
    jobs = cfg.get('images') or {}
    if jobs:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda kv: do_image(kv[0], kv[1], cfg), jobs.items()))
    heroes = [h for h in (cfg.get('heroes') or []) if h]
    with ThreadPoolExecutor(max_workers=int(cfg.get('parallel', 3))) as ex:
        list(ex.map(lambda h: do_hero(h, cfg), heroes))
    state['runs'][-1]['spent_estimate'] = run_info['spent']
    log('run finished; credits used by new tasks (estimate):', run_info['spent'])
    save(True, 'run %s finished' % cfg.get('run'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
