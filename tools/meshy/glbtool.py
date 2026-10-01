#!/usr/bin/env python3
"""Small tools for .glb files (glTF binary), only Python and Pillow needed.

  python3 glbtool.py info FILE.glb
  python3 glbtool.py shrink IN.glb OUT.glb [--max 1024] [--quality 88]
        make the pictures inside smaller (JPEG unless they need see-through parts)
  python3 glbtool.py armature IN.glb OUT.glb
        keep only the skeleton and the animations (no mesh, no pictures)
  python3 glbtool.py merge MODEL.glb OUT.glb ANIM.glb[:new_name] ...
        copy the animations of other files onto the model's skeleton, matching bones by name.
        name the clip(s) of a file with :new_name (one clip) or :old=new,old2=new2

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
            print(' from', path, '->', merge_animations(model, src, rename, mode))
        n = model.save(out); print('wrote', out, round(n / 1e6, 2), 'MB'); return 0
    print(__doc__); return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
