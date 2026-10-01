#!/usr/bin/env python3
"""Small tools for .glb files (glTF binary), only Python and Pillow needed.

  python3 glbtool.py info FILE.glb
  python3 glbtool.py shrink IN.glb OUT.glb [--max 1024] [--quality 88]
        make the pictures inside smaller (JPEG unless they need see-through parts)
  python3 glbtool.py armature IN.glb OUT.glb
        keep only the skeleton and the animations (no mesh, no pictures)
  python3 glbtool.py merge MODEL.glb OUT.glb [--mode=copy|delta|world] ANIM.glb[:new_name] ...
        copy the animations of other files onto the model's skeleton, matching bones by name.
        name the clip(s) of a file with :new_name (one clip) or :old=new,old2=new2
        --mode=world turns each bone the way the other skeleton's bone turns (any rest pose or axes)

The block heroes' 3D models come from Meshy (image to 3D, then rigging and animations).
"""
import json, struct, sys, io, math, copy

GLB_MAGIC, CH_JSON, CH_BIN = 0x46546C67, 0x4E4F534A, 0x004E4942
CT_SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
CT_FMT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}


class Doc:
    def __init__(self, J, BIN):
        self.J, self.BIN = J, BIN or b''

    @staticmethod
    def load(path):
        data = open(path, 'rb').read()
        magic, ver, length = struct.unpack_from('<III', data, 0)
        if magic != GLB_MAGIC:
            raise ValueError(path + ': not a .glb file')
        off, J, BIN = 12, None, b''
        while off + 8 <= len(data):
            clen, ctype = struct.unpack_from('<II', data, off)
            chunk = data[off + 8: off + 8 + clen]
            if ctype == CH_JSON:
                J = json.loads(chunk.decode('utf-8'))
            elif ctype == CH_BIN and not BIN:
                BIN = bytes(chunk)
            off += 8 + clen
        if J is None:
            raise ValueError(path + ': no JSON chunk')
        return Doc(J, BIN)

    def save(self, path):
        self.compact()
        J = self.J
        if self.BIN:
            J['buffers'] = [{'byteLength': len(self.BIN)}]
        else:
            J.pop('buffers', None)
        js = json.dumps(J, separators=(',', ':')).encode('utf-8')
        js += b' ' * ((4 - len(js) % 4) % 4)
        binb = self.BIN + b'\0' * ((4 - len(self.BIN) % 4) % 4)
        total = 12 + 8 + len(js) + (8 + len(binb) if binb else 0)
        out = io.BytesIO()
        out.write(struct.pack('<III', GLB_MAGIC, 2, total))
        out.write(struct.pack('<II', len(js), CH_JSON)); out.write(js)
        if binb:
            out.write(struct.pack('<II', len(binb), CH_BIN)); out.write(binb)
        open(path, 'wb').write(out.getvalue())
        return total

    # ---------- raw data ----------
    def view_bytes(self, bv_index):
        bv = self.J['bufferViews'][bv_index]
        o = bv.get('byteOffset', 0)
        return self.BIN[o:o + bv['byteLength']]

    def accessor_bytes(self, ai):
        """the accessor's data, tightly packed (no stride, no sparse support beyond plain arrays)"""
        a = self.J['accessors'][ai]
        n, es = NCOMP[a['type']], CT_SIZE[a['componentType']]
        elem = n * es
        if 'bufferView' not in a:
            return b'\0' * (elem * a['count'])
        bv = self.J['bufferViews'][a['bufferView']]
        stride = bv.get('byteStride') or elem
        base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        if stride == elem:
            raw = self.BIN[base: base + elem * a['count']]
        else:
            raw = b''.join(self.BIN[base + k * stride: base + k * stride + elem] for k in range(a['count']))
        if a.get('sparse'):
            raise ValueError('sparse accessors are not supported')
        return raw

    def accessor_values(self, ai):
        a = self.J['accessors'][ai]
        raw = self.accessor_bytes(ai)
        n = NCOMP[a['type']]
        vals = struct.unpack('<%d%s' % (len(raw) // CT_SIZE[a['componentType']], CT_FMT[a['componentType']]), raw)
        return [vals[k * n:(k + 1) * n] for k in range(a['count'])]

    def add_view(self, data, target=None):
        pad = (4 - len(self.BIN) % 4) % 4
        self.BIN += b'\0' * pad
        bv = {'buffer': 0, 'byteOffset': len(self.BIN), 'byteLength': len(data)}
        if target:
            bv['target'] = target
        self.BIN += data
        self.J.setdefault('bufferViews', []).append(bv)
        return len(self.J['bufferViews']) - 1

    def add_accessor(self, src_doc, ai):
        a = copy.deepcopy(src_doc.J['accessors'][ai])
        data = src_doc.accessor_bytes(ai)
        a.pop('byteOffset', None); a.pop('sparse', None)
        a['bufferView'] = self.add_view(data)
        self.J.setdefault('accessors', []).append(a)
        return len(self.J['accessors']) - 1

    def add_float_accessor(self, rows, typ, minmax=False):
        flat = [v for r in rows for v in r]
        data = struct.pack('<%df' % len(flat), *flat)
        a = {'bufferView': self.add_view(data), 'componentType': 5126, 'count': len(rows), 'type': typ}
        if minmax:
            n = NCOMP[typ]
            a['min'] = [min(r[c] for r in rows) for c in range(n)]
            a['max'] = [max(r[c] for r in rows) for c in range(n)]
        self.J.setdefault('accessors', []).append(a)
        return len(self.J['accessors']) - 1

    # ---------- clean up: keep only what is used, pack the binary again ----------
    def compact(self):
        J = self.J
        used_acc, used_img = set(), set()
        for m in J.get('meshes', []):
            for p in m.get('primitives', []):
                used_acc.update(p.get('attributes', {}).values())
                if 'indices' in p: used_acc.add(p['indices'])
                for t in p.get('targets', []): used_acc.update(t.values())
        for s in J.get('skins', []):
            if 'inverseBindMatrices' in s: used_acc.add(s['inverseBindMatrices'])
        for an in J.get('animations', []):
            for smp in an.get('samplers', []):
                used_acc.add(smp['input']); used_acc.add(smp['output'])
        for t in J.get('textures', []):
            if 'source' in t: used_img.add(t['source'])
            for ext in (t.get('extensions') or {}).values():
                if isinstance(ext, dict) and 'source' in ext: used_img.add(ext['source'])
        acc_map, new_acc = {}, []
        for i, a in enumerate(J.get('accessors', [])):
            if i in used_acc:
                acc_map[i] = len(new_acc); new_acc.append(a)
        img_map, new_img = {}, []
        for i, im in enumerate(J.get('images', [])):
            if i in used_img:
                img_map[i] = len(new_img); new_img.append(im)
        # the data each kept bufferView needs, repacked
        bv_old = J.get('bufferViews', [])
        chunks, bv_new, bv_map = [], [], {}
        def keep_view(i):
            if i in bv_map: return bv_map[i]
            bv = dict(bv_old[i]); data = self.view_bytes(i)
            bv_map[i] = len(bv_new); bv_new.append(bv); chunks.append(data)
            return bv_map[i]
        for a in new_acc:
            if 'bufferView' in a: a['bufferView'] = keep_view(a['bufferView'])
        for im in new_img:
            if 'bufferView' in im: im['bufferView'] = keep_view(im['bufferView'])
        out = b''
        for bv, data in zip(bv_new, chunks):
            out += b'\0' * ((4 - len(out) % 4) % 4)
            bv['buffer'] = 0; bv['byteOffset'] = len(out); bv['byteLength'] = len(data)
            out += data
        self.BIN = out
        J['accessors'] = new_acc; J['images'] = new_img; J['bufferViews'] = bv_new
        def ra(i): return acc_map[i]
        for m in J.get('meshes', []):
            for p in m.get('primitives', []):
                p['attributes'] = {k: ra(v) for k, v in p.get('attributes', {}).items()}
                if 'indices' in p: p['indices'] = ra(p['indices'])
                if 'targets' in p: p['targets'] = [{k: ra(v) for k, v in t.items()} for t in p['targets']]
        for s in J.get('skins', []):
            if 'inverseBindMatrices' in s: s['inverseBindMatrices'] = ra(s['inverseBindMatrices'])
        for an in J.get('animations', []):
            for smp in an.get('samplers', []):
                smp['input'] = ra(smp['input']); smp['output'] = ra(smp['output'])
        for t in J.get('textures', []):
            if 'source' in t: t['source'] = img_map[t['source']]
            for ext in (t.get('extensions') or {}).values():
                if isinstance(ext, dict) and 'source' in ext: ext['source'] = img_map[ext['source']]
        for k in ('accessors', 'images', 'bufferViews', 'textures', 'samplers', 'materials', 'meshes', 'skins', 'animations'):
            if k in J and not J[k]: del J[k]

    # ---------- pictures ----------
    def shrink_textures(self, max_size=1024, quality=88):
        from PIL import Image
        J = self.J
        for im in J.get('images', []):
            if 'bufferView' not in im: continue
            data = self.view_bytes(im['bufferView'])
            pic = Image.open(io.BytesIO(data)); pic.load()
            w, h = pic.size
            s = min(1.0, max_size / max(w, h))
            has_alpha = pic.mode in ('RGBA', 'LA') or (pic.mode == 'P' and 'transparency' in pic.info)
            if has_alpha:
                rgba = pic.convert('RGBA'); lo = rgba.getchannel('A').getextrema()[0]
                has_alpha = lo < 250
            if s < 1:
                pic = pic.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
            buf = io.BytesIO()
            if has_alpha:
                pic.convert('RGBA').save(buf, 'PNG', optimize=True); mime = 'image/png'
            else:
                pic.convert('RGB').save(buf, 'JPEG', quality=quality, optimize=True); mime = 'image/jpeg'
            new = buf.getvalue()
            if s >= 1 and len(new) >= len(data):
                continue  # already small: keep it
            im['bufferView'] = self.add_view(new); im['mimeType'] = mime
        # textures that used EXT_texture_webp etc. now point at a plain picture we can read
        return self

    # ---------- only the skeleton and the animations ----------
    def armature_only(self):
        J = self.J
        for n in J.get('nodes', []):
            n.pop('mesh', None); n.pop('skin', None); n.pop('weights', None)
        for k in ('meshes', 'skins', 'materials', 'textures', 'images', 'samplers'):
            J.pop(k, None)
        J.pop('extensionsUsed', None); J.pop('extensionsRequired', None)
        return self

    def node_names(self):
        return [n.get('name', '') for n in self.J.get('nodes', [])]


def bone_key(name):
    """bone names from different tools: 'mixamorig:LeftArm', 'Armature|LeftArm', 'LeftArm.001' are the same bone"""
    s = name.split('|')[-1].split(':')[-1]
    if '.' in s and s.rsplit('.', 1)[1].isdigit(): s = s.rsplit('.', 1)[0]
    return s.replace('_', '').replace(' ', '').lower()


def quat_mul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def quat_inv(q):
    x, y, z, w = q; return (-x, -y, -z, w)


def merge_animations(model, src, rename=None, mode='copy', hips_scale=True, only=None):
    """copy the animations of src onto model's bones (matched by name).
    mode 'copy': the bones take the clip's rotations as they are (same skeleton type, like Meshy's own rigs);
    mode 'delta': the clip's change from its own rest pose is added to the model's rest pose."""
    J = model.J; SJ = src.J
    mkeys = {}
    for i, n in enumerate(J.get('nodes', [])):
        mkeys.setdefault(bone_key(n.get('name', '')), i)
    skel = set()
    for s in J.get('skins', []): skel.update(s['joints'])
    src_nodes = SJ.get('nodes', [])
    # the hips: the one bone whose position moves; scale it by the two skeletons' hip heights
    hips_m = next((i for i in skel if 'hips' in bone_key(J['nodes'][i].get('name', '')) or 'pelvis' in bone_key(J['nodes'][i].get('name', ''))), None)
    added = []
    for an in SJ.get('animations', []):
        name = an.get('name', '')
        if only and name not in only: continue
        if rename:
            if isinstance(rename, str): new_name = rename
            else: new_name = rename.get(name, name)
        else: new_name = name
        out = {'name': new_name, 'channels': [], 'samplers': []}
        for ch in an.get('channels', []):
            t = ch.get('target', {}); sn = t.get('node'); path = t.get('path')
            if sn is None or path not in ('rotation', 'translation'): continue
            mn = mkeys.get(bone_key(src_nodes[sn].get('name', '')))
            if mn is None: continue
            smp = an['samplers'][ch['sampler']]
            if smp.get('interpolation', 'LINEAR') == 'CUBICSPLINE': continue
            mnode, snode = J['nodes'][mn], src_nodes[sn]
            if path == 'translation':
                if mn != hips_m: continue  # bones keep their own lengths
                vals = src.accessor_values(smp['output'])
                st = snode.get('translation', [0, 0, 0]); mt = mnode.get('translation', [0, 0, 0])
                k = (abs(mt[1]) / abs(st[1])) if (hips_scale and abs(st[1]) > 1e-6 and abs(mt[1]) > 1e-6) else 1.0
                vals = [(mt[0] + (v[0] - st[0]) * k, mt[1] + (v[1] - st[1]) * k, mt[2] + (v[2] - st[2]) * k) for v in vals]
                inp = model.add_accessor(src, smp['input']); outp = model.add_float_accessor(vals, 'VEC3')
            else:
                if mode == 'delta':
                    vals = src.accessor_values(smp['output'])
                    rs = tuple(snode.get('rotation', [0, 0, 0, 1])); rm = tuple(mnode.get('rotation', [0, 0, 0, 1]))
                    inv = quat_inv(rs)
                    vals = [quat_mul(rm, quat_mul(inv, tuple(v))) for v in vals]
                    inp = model.add_accessor(src, smp['input']); outp = model.add_float_accessor(vals, 'VEC4')
                else:
                    inp = model.add_accessor(src, smp['input']); outp = model.add_accessor(src, smp['output'])
            out['samplers'].append({'input': inp, 'output': outp, 'interpolation': smp.get('interpolation', 'LINEAR')})
            out['channels'].append({'sampler': len(out['samplers']) - 1, 'target': {'node': mn, 'path': path}})
        if out['channels']:
            J.setdefault('animations', [])
            J['animations'] = [a for a in J['animations'] if a.get('name') != new_name]
            J['animations'].append(out); added.append(new_name)
    return added


# ---------- retargeting in world space (skeletons with the same bones but different rest poses or axes) ----------
def _q_mul(a, b):
    import numpy as np
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def _q_inv(q):
    import numpy as np
    return q * np.array([-1, -1, -1, 1.0])


def _q_rot(q, v):
    import numpy as np
    qv = np.concatenate([v, np.zeros(v.shape[:-1] + (1,))], -1)
    return _q_mul(_q_mul(q, qv), _q_inv(q))[..., :3]


def _mat_to_trs(m):
    import numpy as np
    M = np.array(m, dtype=float).reshape(4, 4).T  # glTF matrices are column-major
    t = M[:3, 3]; sx, sy, sz = [np.linalg.norm(M[:3, i]) for i in range(3)]
    R = M[:3, :3] / np.array([sx, sy, sz])
    w = math.sqrt(max(0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    if w > 1e-4:
        q = np.array([(R[2, 1] - R[1, 2]) / (4 * w), (R[0, 2] - R[2, 0]) / (4 * w), (R[1, 0] - R[0, 1]) / (4 * w), w])
    else:
        i = int(np.argmax([R[0, 0], R[1, 1], R[2, 2]])); j, k = (i + 1) % 3, (i + 2) % 3
        r = math.sqrt(max(0, 1 + R[i, i] - R[j, j] - R[k, k])); q = np.zeros(4); q[i] = r / 2
        q[j] = (R[j, i] + R[i, j]) / (2 * r); q[k] = (R[k, i] + R[i, k]) / (2 * r); q[3] = (R[k, j] - R[j, k]) / (2 * r)
    return t, q / np.linalg.norm(q), np.array([sx, sy, sz])


class _Skel:
    def __init__(self, doc):
        import numpy as np
        J = doc.J; nodes = J.get('nodes', [])
        self.n = len(nodes); self.parent = [-1] * self.n
        for i, nd in enumerate(nodes):
            for c in nd.get('children', []): self.parent[c] = i
        self.T = np.zeros((self.n, 3)); self.R = np.tile([0, 0, 0, 1.0], (self.n, 1)); self.S = np.ones((self.n, 3))
        for i, nd in enumerate(nodes):
            if 'matrix' in nd:
                self.T[i], self.R[i], self.S[i] = _mat_to_trs(nd['matrix'])
            else:
                self.T[i] = nd.get('translation', [0, 0, 0]); self.R[i] = nd.get('rotation', [0, 0, 0, 1]); self.S[i] = nd.get('scale', [1, 1, 1])
        self.order = []
        seen = set()
        def visit(i):
            if i in seen: return
            seen.add(i); self.order.append(i)
            for c in nodes[i].get('children', []): visit(c)
        for i in range(self.n):
            if self.parent[i] < 0: visit(i)
        self.names = [nd.get('name', '') for nd in nodes]

    def world(self, T, R, S):
        """world rotation (F x n x 4) and position (F x n x 3) for local T, R, S (F x n x k)"""
        import numpy as np
        F = R.shape[0]
        WR = np.zeros((F, self.n, 4)); WP = np.zeros((F, self.n, 3)); WS = np.ones((F, self.n, 3))
        for i in self.order:
            p = self.parent[i]
            if p < 0:
                WR[:, i] = R[:, i]; WP[:, i] = T[:, i]; WS[:, i] = S[:, i]
            else:
                WR[:, i] = _q_mul(WR[:, p], R[:, i]); WS[:, i] = WS[:, p] * S[:, i]
                WP[:, i] = WP[:, p] + _q_rot(WR[:, p], WS[:, p] * T[:, i])
        return WR, WP, WS


def _sample(times, vals, t, rot):
    import numpy as np
    times = np.asarray(times, float); vals = np.asarray(vals, float)
    if len(times) == 1: return np.repeat(vals[:1], len(t), 0)
    idx = np.clip(np.searchsorted(times, t, side='right') - 1, 0, len(times) - 2)
    t0, t1 = times[idx], times[idx + 1]; f = np.clip((t - t0) / np.maximum(t1 - t0, 1e-9), 0, 1)[:, None]
    a, b = vals[idx], vals[idx + 1]
    if not rot: return a + (b - a) * f
    d = np.sum(a * b, -1, keepdims=True); b = np.where(d < 0, -b, b); out = a + (b - a) * f  # nlerp is plenty at 30 frames a second
    return out / np.linalg.norm(out, axis=-1, keepdims=True)


def retarget_world(model, src, rename=None, fps=30, only=None):
    """copy src's clips onto model: every bone turns in the world the way the same bone turns in src (from each one's own
    rest pose), and the hips move up and down scaled to the model's size. Works across different exporters and axes."""
    import numpy as np
    tg, sk = _Skel(model), _Skel(src)
    skel = set()
    for s in model.J.get('skins', []): skel.update(s['joints'])
    smap = {}
    for i, nm in enumerate(sk.names): smap.setdefault(bone_key(nm), i)
    pairs = {i: smap[bone_key(tg.names[i])] for i in skel if bone_key(tg.names[i]) in smap}
    hips_t = next((i for i in tg.order if i in skel and ('hips' in bone_key(tg.names[i]) or 'pelvis' in bone_key(tg.names[i]))), None)
    # rest pose of both (frame axis of size 1)
    sWR0, sWP0, _ = sk.world(sk.T[None], sk.R[None], sk.S[None]); tWR0, tWP0, tWS0 = tg.world(tg.T[None], tg.R[None], tg.S[None])
    k = 1.0
    if hips_t is not None and hips_t in pairs:
        hs, ht = sWP0[0, pairs[hips_t]], tWP0[0, hips_t]
        # heights above the lowest bone of each skeleton
        lo_s = min(sWP0[0, j, 1] for j in pairs.values()); lo_t = min(tWP0[0, j, 1] for j in pairs)
        if hs[1] - lo_s > 1e-6: k = (ht[1] - lo_t) / (hs[1] - lo_s)
    added = []
    for an in src.J.get('animations', []):
        name = an.get('name', '')
        if only and name not in only: continue
        new_name = (rename if isinstance(rename, str) else (rename or {}).get(name, name)) if rename else name
        chans = []
        dur = 0
        for ch in an.get('channels', []):
            t = ch.get('target', {}); smp = an['samplers'][ch['sampler']]
            if t.get('node') is None or t.get('path') not in ('rotation', 'translation', 'scale'): continue
            if smp.get('interpolation', 'LINEAR') == 'CUBICSPLINE': continue
            tm = [v[0] for v in src.accessor_values(smp['input'])]; dur = max(dur, tm[-1] if tm else 0)
            chans.append((t['node'], t['path'], tm, src.accessor_values(smp['output']), smp.get('interpolation', 'LINEAR')))
        if not chans: continue
        F = max(2, int(round(dur * fps)) + 1); times = np.linspace(0, dur, F)
        T = np.repeat(sk.T[None], F, 0); R = np.repeat(sk.R[None], F, 0); S = np.repeat(sk.S[None], F, 0)
        for node, path, tm, vals, ip in chans:
            v = _sample(tm, vals, times, path == 'rotation')
            if path == 'rotation': R[:, node] = v
            elif path == 'translation': T[:, node] = v
            else: S[:, node] = v
        sWR, sWP, _ = sk.world(T, R, S)
        # the model, bone by bone from the root: wanted world turn -> local turn
        tR = np.repeat(tg.R[None], F, 0); tT = np.repeat(tg.T[None], F, 0)
        WR = np.zeros((F, tg.n, 4)); WP = np.zeros((F, tg.n, 3)); WS = np.ones((F, tg.n, 3))
        for i in tg.order:
            p = tg.parent[i]
            pR = WR[:, p] if p >= 0 else np.tile([0, 0, 0, 1.0], (F, 1)); pS = WS[:, p] if p >= 0 else np.ones((F, 3)); pP = WP[:, p] if p >= 0 else np.zeros((F, 3))
            if i in pairs:
                j = pairs[i]
                want = _q_mul(_q_mul(sWR[:, j], _q_inv(sWR0[0, j])[None]), tWR0[0, i][None])
                tR[:, i] = _q_mul(_q_inv(pR), want)
                if i == hips_t:
                    wpos = tWP0[0, i][None] + (sWP[:, j] - sWP0[0, j][None]) * k
                    tT[:, i] = _q_rot(_q_inv(pR), wpos - pP) / np.maximum(pS, 1e-9)
            WR[:, i] = _q_mul(pR, tR[:, i]); WS[:, i] = pS * tg.S[i]; WP[:, i] = pP + _q_rot(pR, pS * tT[:, i])
        # keep the turns continuous (no flips between frames)
        for i in pairs:
            q = tR[:, i]
            for f2 in range(1, F):
                if np.dot(q[f2], q[f2 - 1]) < 0: q[f2] = -q[f2]
        out = {'name': new_name, 'channels': [], 'samplers': []}
        tin = model.add_float_accessor([(float(x),) for x in times], 'SCALAR', minmax=True)
        for i in sorted(pairs):
            out['samplers'].append({'input': tin, 'output': model.add_float_accessor([tuple(map(float, r)) for r in tR[:, i]], 'VEC4'), 'interpolation': 'LINEAR'})
            out['channels'].append({'sampler': len(out['samplers']) - 1, 'target': {'node': i, 'path': 'rotation'}})
        if hips_t is not None and hips_t in pairs:
            out['samplers'].append({'input': tin, 'output': model.add_float_accessor([tuple(map(float, r)) for r in tT[:, hips_t]], 'VEC3'), 'interpolation': 'LINEAR'})
            out['channels'].append({'sampler': len(out['samplers']) - 1, 'target': {'node': hips_t, 'path': 'translation'}})
        model.J['animations'] = [a for a in model.J.get('animations', []) if a.get('name') != new_name] + [out]
        added.append(new_name)
    return added


# ---------- smaller files for the game: clips sampled again, vertices and turns stored in fewer bytes ----------
_NORM = {5120: 127., 5121: 255., 5122: 32767., 5123: 65535.}


def _values(doc, ai):
    import numpy as np
    a = doc.J['accessors'][ai]; v = np.array(doc.accessor_values(ai), float)
    if a.get('normalized') and a['componentType'] in _NORM:
        v = np.maximum(v / _NORM[a['componentType']], -1)
    return v


def _rest(node, path):
    import numpy as np
    if 'matrix' in node:
        t, q, s = _mat_to_trs(node['matrix'])
        return {'translation': t, 'rotation': q, 'scale': s}[path]
    return np.array(node.get(path, {'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}[path]), float)


def resample_clip(doc, name, t0=None, t1=None, fps=30, drop_rest=True, new_name=None):
    """sample clip `name` again at `fps` from t0 to t1 (seconds; None = the whole clip), with its times starting at 0
    and one time track for the whole clip. Channels that never leave the rest pose are left out."""
    import numpy as np
    J = doc.J
    an = next((a for a in J.get('animations', []) if a.get('name') == name), None)
    if an is None: return False
    chans, dur = [], 0.0
    for ch in an.get('channels', []):
        t = ch.get('target', {}); smp = an['samplers'][ch['sampler']]
        if t.get('node') is None or t.get('path') not in ('rotation', 'translation', 'scale'): continue
        ip = smp.get('interpolation', 'LINEAR')
        if ip == 'CUBICSPLINE': continue
        tm = _values(doc, smp['input'])[:, 0]; vals = _values(doc, smp['output'])
        chans.append((t['node'], t['path'], tm, vals, ip)); dur = max(dur, float(tm[-1]) if len(tm) else 0.0)
    a0 = 0.0 if t0 is None else max(0.0, t0); a1 = dur if t1 is None else min(dur, t1)
    F = max(2, int(round((a1 - a0) * fps)) + 1); times = np.linspace(a0, a1, F)
    out = {'name': new_name or name, 'channels': [], 'samplers': []}
    tin = doc.add_float_accessor([(float(x - a0),) for x in times], 'SCALAR', minmax=True)
    for node, path, tm, vals, ip in chans:
        if ip == 'STEP':
            v = vals[np.clip(np.searchsorted(tm, times, side='right') - 1, 0, len(tm) - 1)]
        else:
            v = _sample(tm, vals, times, path == 'rotation')
        if path == 'rotation':
            v = v / np.linalg.norm(v, axis=-1, keepdims=True)
            for f in range(1, F):
                if np.dot(v[f], v[f - 1]) < 0: v[f] = -v[f]
        if drop_rest:
            r = _rest(J['nodes'][node], path)
            if path == 'rotation':
                if np.all(np.abs(v @ r) > 0.9999995): continue
            elif np.all(np.abs(v - r[None]) < 1e-5): continue
        out['samplers'].append({'input': tin, 'output': doc.add_float_accessor([tuple(map(float, x)) for x in v], 'VEC4' if path == 'rotation' else 'VEC3'),
                                'interpolation': 'LINEAR'})
        out['channels'].append({'sampler': len(out['samplers']) - 1, 'target': {'node': node, 'path': path}})
    J['animations'] = [out if a is an else a for a in J['animations']]
    return True


def quantize_rotations(doc):
    """the turns of all clips as 16-bit numbers (allowed by plain glTF 2.0 for rotations)"""
    import numpy as np
    J = doc.J; acc = J.get('accessors', [])
    other = set()
    for an in J.get('animations', []):
        for ch in an['channels']:
            smp = an['samplers'][ch['sampler']]
            if ch['target'].get('path') != 'rotation' or smp.get('interpolation') == 'CUBICSPLINE': other.add(smp['output'])
    done = {}
    for an in J.get('animations', []):
        for ch in an['channels']:
            smp = an['samplers'][ch['sampler']]; o = smp['output']
            if ch['target'].get('path') != 'rotation' or o in other or acc[o]['componentType'] != 5126: continue
            if o not in done:
                v = np.array(doc.accessor_values(o), float); v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)
                q = np.round(v * 32767).astype('<i2')
                acc.append({'bufferView': doc.add_view(q.tobytes()), 'componentType': 5122, 'normalized': True, 'count': int(len(q)), 'type': 'VEC4'})
                done[o] = len(acc) - 1
            smp['output'] = done[o]
    return len(done)


def quantize_mesh(doc, uv=True, weights=True, pos_nor=True):
    """vertices in fewer bytes: weights as 8-bit and texture places as 16-bit (plain glTF 2.0), and for skinned meshes the
    positions as 16-bit and the normals as 8-bit (KHR_mesh_quantization; the scale back is put into the skin's inverse bind matrices)"""
    import numpy as np
    J = doc.J; acc = J['accessors']; nodes = J.get('nodes', [])
    def add(arr, ct, typ, norm, stride=None, mm=False):
        dt = {5120: '<i1', 5121: '<u1', 5122: '<i2', 5123: '<u2'}[ct]; a2 = arr.astype(dt)
        n, es = NCOMP[typ], CT_SIZE[ct]
        if stride and stride != n * es:
            a2 = np.concatenate([a2, np.zeros((a2.shape[0], stride // es - n), dt)], 1)
        bv = doc.add_view(np.ascontiguousarray(a2).tobytes(), 34962)
        if stride and stride != n * es: J['bufferViews'][bv]['byteStride'] = stride
        A = {'bufferView': bv, 'componentType': ct, 'count': int(arr.shape[0]), 'type': typ}
        if norm: A['normalized'] = True
        if mm: A['min'] = [int(x) for x in arr.min(0)]; A['max'] = [int(x) for x in arr.max(0)]
        acc.append(A); return len(acc) - 1
    skins_of = {}
    for n in nodes:
        if 'mesh' in n: skins_of.setdefault(n['mesh'], set()).add(n.get('skin'))
    # positions: one box per skin (all of its meshes), only when every mesh is drawn with exactly one skin
    can_pos = pos_nor and skins_of and all(len(s) == 1 and None not in s for s in skins_of.values())
    box = {}
    if can_pos:
        for mi, sks in skins_of.items():
            sk = next(iter(sks))
            for p in J['meshes'][mi]['primitives']:
                if 'POSITION' not in p.get('attributes', {}): continue
                v = _values(doc, p['attributes']['POSITION']); lo, hi = v.min(0), v.max(0)
                b = box.get(sk); box[sk] = (lo, hi) if b is None else (np.minimum(b[0], lo), np.maximum(b[1], hi))
        for sk, (lo, hi) in list(box.items()):
            c = (lo + hi) / 2; h = max(float(np.max(hi - lo)) / 2, 1e-6)
            D = np.eye(4); D[:3, :3] *= h; D[:3, 3] = c
            S = J['skins'][sk]; nj = len(S['joints'])
            ibm = np.array(doc.accessor_values(S['inverseBindMatrices']), float).reshape(nj, 4, 4).transpose(0, 2, 1) if 'inverseBindMatrices' in S else np.tile(np.eye(4), (nj, 1, 1))
            new = (ibm @ D).transpose(0, 2, 1).reshape(nj, 16)
            S['inverseBindMatrices'] = doc.add_float_accessor([tuple(map(float, r)) for r in new], 'MAT4')
            box[sk] = (c, h)
    done = {}
    for mi, m in enumerate(J.get('meshes', [])):
        sk = next(iter(skins_of.get(mi, {None})))
        for p in m['primitives']:
            A = p.get('attributes', {})
            for k in list(A):
                ai = A[k]; a = acc[ai]; key = (k, ai)
                if key in done: A[k] = done[key]; continue
                if k == 'POSITION' and can_pos and sk in box and a['componentType'] == 5126:
                    c, h = box[sk]; q = np.clip(np.round((_values(doc, ai) - c) / h * 32767), -32767, 32767)
                    done[key] = add(q, 5122, 'VEC3', True, stride=8, mm=True)
                elif k == 'NORMAL' and can_pos and a['componentType'] == 5126:
                    v = _values(doc, ai); v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)
                    done[key] = add(np.round(v * 127), 5120, 'VEC3', True, stride=4)
                elif k.startswith('TEXCOORD') and uv and a['componentType'] == 5126:
                    v = _values(doc, ai)
                    if v.min() < 0 or v.max() > 1: continue
                    done[key] = add(np.round(v * 65535), 5123, 'VEC2', True)
                elif k.startswith('WEIGHTS') and weights and a['componentType'] == 5126:
                    v = np.maximum(_values(doc, ai), 0); s = v.sum(1, keepdims=True); v = np.where(s > 0, v / np.maximum(s, 1e-12), 0)
                    q = np.round(v * 255).astype(int); big = q.argmax(1); rows = np.arange(len(q))
                    q[rows, big] += np.where(q.sum(1) > 0, 255 - q.sum(1), 0)
                    done[key] = add(q, 5121, 'VEC4', True)
                else:
                    continue
                A[k] = done[key]
    if can_pos and box:
        for k in ('extensionsUsed', 'extensionsRequired'):
            J[k] = sorted(set(J.get(k, [])) | {'KHR_mesh_quantization'})
    return bool(done)


# ---------- capes, long hair and wings that the automatic skeleton tied to the arms ----------
def _seg_dist(P, a, b):
    import numpy as np
    ab = b - a; t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def _rest_skinned(doc, prim):
    """vertex positions of one primitive in the rest pose (world space of the skeleton)"""
    import numpy as np
    J = doc.J; sk = _Skel(doc)
    WR, WP, WS = sk.world(sk.T[None], sk.R[None], sk.S[None])
    S = J['skins'][0]; nj = len(S['joints'])
    ibm = np.array(doc.accessor_values(S['inverseBindMatrices']), float).reshape(nj, 4, 4).transpose(0, 2, 1)
    def mat(i):
        x, y, z, w = WR[0, i]; s = WS[0, i]
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]) * s
        M = np.eye(4); M[:3, :3] = R; M[:3, 3] = WP[0, i]; return M
    JM = np.stack([mat(j) @ ibm[k] for k, j in enumerate(S['joints'])])
    A = prim['attributes']
    P = _values(doc, A['POSITION']); Jt = _values(doc, A['JOINTS_0']).astype(int); W = _values(doc, A['WEIGHTS_0'])
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-12)
    Ph = np.concatenate([P, np.ones((len(P), 1))], 1); out = np.zeros((len(P), 3))
    for c in range(4):
        out += W[:, c:c + 1] * np.einsum('nij,nj->ni', JM[Jt[:, c]], Ph)[:, :3]
    return out, Jt, W, WP[0], sk


def fix_arm_weights(doc, min_dist=0.1):
    """Meshy's automatic skeleton ties parts of a cape, long hair, wings or a skirt that hang next to the arms (A-pose) to
    the arm bones, so they fly up with the arms. A vertex that moves with an arm, but is far from the arm and nearer to the
    body, gets the weights of the nearest vertex that does not move with an arm. Returns how many vertices changed."""
    import numpy as np
    J = doc.J
    if not J.get('skins') or not J.get('meshes'): return 0
    changed = 0
    for m in J['meshes']:
        for prim in m['primitives']:
            A = prim.get('attributes', {})
            if not all(k in A for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')): continue
            pos, Jt, W, WP, sk = _rest_skinned(doc, prim)
            nm = [n.split('|')[-1].split(':')[-1] for n in sk.names]; ix = {n: i for i, n in enumerate(nm)}
            if not all(s + b in ix for s in ('Left', 'Right') for b in ('Arm', 'ForeArm', 'Hand')): continue
            joints = J['skins'][0]['joints']; slot = {j: k for k, j in enumerate(joints)}
            arm_slots = [slot[ix[s + b]] for s in ('Left', 'Right') for b in ('Arm', 'ForeArm', 'Hand') if ix[s + b] in slot]
            is_arm = np.isin(Jt, arm_slots); wa = (W * is_arm).sum(1)
            darm = np.full(len(pos), 9.0)
            for s in ('Left', 'Right'):
                a, f, h = WP[ix[s + 'Arm']], WP[ix[s + 'ForeArm']], WP[ix[s + 'Hand']]
                darm = np.minimum(darm, np.minimum(np.minimum(_seg_dist(pos, a, f), _seg_dist(pos, f, h)), _seg_dist(pos, h, h + (h - f) * .7)))
            dbody = np.full(len(pos), 9.0)
            for a, b in (('Hips', 'Spine'), ('Spine', 'Spine01'), ('Spine01', 'Spine02'), ('Spine02', 'neck'), ('neck', 'Head'), ('Head', 'head_end'),
                         ('Hips', 'LeftUpLeg'), ('Hips', 'RightUpLeg'), ('LeftUpLeg', 'LeftLeg'), ('LeftLeg', 'LeftFoot'), ('RightUpLeg', 'RightLeg'), ('RightLeg', 'RightFoot')):
                if a in ix and b in ix: dbody = np.minimum(dbody, _seg_dist(pos, WP[ix[a]], WP[ix[b]]))
            strong = wa > 0.9
            r_arm = float(np.percentile(darm[strong], 75)) if strong.any() else 0.08
            height = float(np.ptp(pos[:, 1])) or 1.4
            thr = max(min_dist * height / 1.4, 1.5 * min(r_arm, 0.09 * height / 1.4))
            # how far behind the back each vertex is (the hero faces +z): capes, wings and long hair hang there, arms do not
            hp, sp2 = WP[ix['Hips']], WP[ix['Spine02']] if 'Spine02' in ix else WP[ix['Hips']] + np.array([0, .3, 0])
            zrel = pos[:, 2] - np.interp(pos[:, 1], [hp[1], sp2[1]], [hp[2], sp2[2]])
            k = height / 1.4
            bad = (wa > 0.02) & (((darm > thr) & (dbody < darm)) | ((zrel < -0.09 * k) & (darm > 0.09 * k)))
            good = wa < 1e-3
            bi, gi = np.where(bad)[0], np.where(good)[0]
            if not len(bi) or not len(gi): continue
            near = np.empty(len(bi), int); G = pos[gi]
            for s0 in range(0, len(bi), 256):
                d = ((pos[bi[s0:s0 + 256]][:, None, :] - G[None, :, :]) ** 2).sum(-1); near[s0:s0 + 256] = gi[d.argmin(1)]
            nj = len(joints); newJ = Jt.copy(); newW = W.copy()
            for k, v in enumerate(bi):
                acc = np.zeros(nj)
                for c in range(4):
                    if not is_arm[v, c]: acc[Jt[v, c]] += W[v, c]
                dn = near[k]
                for c in range(4): acc[Jt[dn, c]] += wa[v] * W[dn, c]
                top = np.argsort(-acc)[:4]; w = acc[top]; s1 = w.sum()
                newJ[v] = top; newW[v] = w / s1 if s1 > 0 else W[v]
            ct = 5121 if nj <= 255 else 5123
            J['accessors'].append({'bufferView': doc.add_view(newJ.astype('<u1' if ct == 5121 else '<u2').tobytes(), 34962), 'componentType': ct, 'count': int(len(newJ)), 'type': 'VEC4'})
            A['JOINTS_0'] = len(J['accessors']) - 1
            J['accessors'].append({'bufferView': doc.add_view(newW.astype('<f4').tobytes(), 34962), 'componentType': 5126, 'count': int(len(newW)), 'type': 'VEC4'})
            A['WEIGHTS_0'] = len(J['accessors']) - 1
            changed += len(bi)
    return changed


def info(path):
    d = Doc.load(path); J = d.J
    print(path, '| JSON nodes', len(J.get('nodes', [])), '| BIN', round(len(d.BIN) / 1e6, 2), 'MB')
    print(' extensionsUsed', J.get('extensionsUsed'), 'required', J.get('extensionsRequired'))
    tris = 0
    for m in J.get('meshes', []):
        for p in m['primitives']:
            if 'indices' in p: tris += J['accessors'][p['indices']]['count'] // 3
            else: tris += J['accessors'][p['attributes']['POSITION']]['count'] // 3
    print(' meshes', len(J.get('meshes', [])), 'triangles', tris, 'materials', len(J.get('materials', [])))
    for i, im in enumerate(J.get('images', [])):
        size = '?'
        try:
            from PIL import Image
            pic = Image.open(io.BytesIO(d.view_bytes(im['bufferView']))); size = '%dx%d %s' % (pic.size[0], pic.size[1], pic.mode)
        except Exception as e: size = 'unreadable ' + str(e)
        print('  image', i, im.get('mimeType'), size, round(J['bufferViews'][im['bufferView']]['byteLength'] / 1e3), 'kB')
    for s in J.get('skins', []):
        names = [J['nodes'][j].get('name', '') for j in s['joints']]
        print(' skin', len(names), 'joints:', ', '.join(names[:70]))
    for an in J.get('animations', []):
        dur = 0
        for smp in an['samplers']:
            dur = max(dur, (J['accessors'][smp['input']].get('max') or [0])[0])
        print(' animation', repr(an.get('name')), 'channels', len(an['channels']), 'seconds', round(dur, 2))


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 1
    cmd = argv[1]
    if cmd == 'info':
        for p in argv[2:]: info(p)
        return 0
    if cmd == 'shrink':
        mx, q = 1024, 88
        args = argv[2:]
        if '--max' in args: i = args.index('--max'); mx = int(args[i + 1]); del args[i:i + 2]
        if '--quality' in args: i = args.index('--quality'); q = int(args[i + 1]); del args[i:i + 2]
        d = Doc.load(args[0]); d.shrink_textures(mx, q); n = d.save(args[1]); print('wrote', args[1], round(n / 1e6, 2), 'MB'); return 0
    if cmd == 'armature':
        d = Doc.load(argv[2]); d.armature_only(); n = d.save(argv[3]); print('wrote', argv[3], round(n / 1e3), 'kB'); return 0
    if cmd == 'merge':
        model = Doc.load(argv[2]); out = argv[3]; mode = 'copy'
        for spec in argv[4:]:
            if spec.startswith('--mode='): mode = spec[7:]; continue
            path, _, ren = spec.partition(':')
            rename = None
            if ren:
                rename = dict(p.split('=', 1) for p in ren.split(',')) if '=' in ren else ren
            src = Doc.load(path)
            if mode == 'world':
                print(' from', path, '->', retarget_world(model, src, rename))
            else:
                print(' from', path, '->', merge_animations(model, src, rename, mode))
        n = model.save(out); print('wrote', out, round(n / 1e6, 2), 'MB'); return 0
    print(__doc__); return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
