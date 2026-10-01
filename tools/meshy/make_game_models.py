#!/usr/bin/env python3
"""Make the game's hero files (models/<hero>.glb) from Meshy's results (the meshy-out branch).

  python3 make_game_models.py OUT_DIR GAME_MODELS_DIR [hero ...] [--share-from=kira,leo] [--mode=world] [--raw]

Every hero file has the model with its skeleton, its own walk and run, and the other moves (idle, jump, punch, cheer,
wave, knocked down, sit, swim): the hero's own when Meshy made them for this hero, otherwise the moves of a hero that has
them (girls from the first, boys from the second --share-from hero), turned onto this skeleton bone by bone.
The files are made small for the game (--raw keeps everything as Meshy made it): only the part of each move the game
plays, sampled again (slow moves fewer times a second), and the vertices and turns stored in fewer bytes.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glbtool

NAMES = {'Idle': 'idle', 'Regular_Jump': 'jump', 'Right_Jab_from_Guard': 'punch', 'Victory_Cheer': 'cheer',
         'Big_Wave_Hello': 'wave', 'Knock_Down': 'ko', 'Chair_Sit_Idle_M': 'sit', 'Chair_Sit_Idle_F': 'sit', 'Swim_Forward': 'swim'}
# the part of each move the game uses (seconds, None = all of it) and how many times a second it is sampled
GAMECUT = {'walk': (None, None, 30), 'run': (None, None, 30), 'idle': (None, None, 15), 'jump': (1.2, 2.0, 30), 'punch': (0, 1.2, 30),
           'cheer': (0, 3.6, 30), 'wave': (0, 3.0, 30), 'ko': (None, None, 30), 'sit': (None, None, 10), 'swim': (None, None, 20)}
# better moves bought for one hero and shared with everybody: Meshy's 'Idle' is a fighting stance turned to the side and
# its 'Regular Jump' is turned too, so every hero stands with Kira's 'Idle 3' and jumps with her 'Jump with Arms Open'
BETTER = [('kira', 'x_try1.glb', {'Idle_3': 'idle', 'Jump_with_Arms_Open': 'jump'})]
GIRLS = set('mia,layla,ruby,noor,aya,kat,fay,nora,bella,lulu,mira,wanda,salma,tala,zara,kira,bushra,yasmin,sama,lina,sara,amira,uma,aisha,rina'.split(','))


def build(out, dest, h, share, mode, raw=False):
    src = os.path.join(out, h)
    if not os.path.exists(os.path.join(src, 'model.glb')):
        return None
    # the same model with its full-size picture (2048 pixels) when it was read again, else the smaller one
    full = os.path.join(src, 'model_full.glb')
    d = glbtool.Doc.load(full if os.path.exists(full) and '--small' not in sys.argv else os.path.join(src, 'model.glb'))
    d.shrink_textures(2048, 90)
    d.J.pop('animations', None)
    got = []
    for f, name in (('walk.glb', 'walk'), ('run.glb', 'run')):
        p = os.path.join(src, f)
        if os.path.exists(p):
            got += glbtool.merge_animations(d, glbtool.Doc.load(p), name, 'copy')
    own = os.path.join(src, 'anims.glb')
    if os.path.exists(own):
        got += glbtool.merge_animations(d, glbtool.Doc.load(own), NAMES, 'copy')
        how = 'own'
    else:
        donor = share[0] if h in GIRLS else share[-1]
        p = os.path.join(out, donor, 'anims.glb')
        if os.path.exists(p):
            sd = glbtool.Doc.load(os.path.join(out, donor, 'model.glb'))  # the donor's rest pose and bone axes
            anim = glbtool.Doc.load(p)
            # the clips live on the donor's armature file; its nodes carry the donor's rest pose
            if mode == 'world':
                got += glbtool.retarget_world(d, anim, NAMES)
            else:
                got += glbtool.merge_animations(d, anim, NAMES, mode)
            how = 'from ' + donor
        else:
            how = 'none'
    for donor, f, names in BETTER:
        p = os.path.join(out, donor, f)
        if not os.path.exists(p):
            continue
        src = glbtool.Doc.load(p)
        for old_name, new_name in names.items():
            if h == donor:
                glbtool.merge_animations(d, src, {old_name: new_name}, 'copy', only=[old_name])
            else:
                glbtool.retarget_world(d, src, {old_name: new_name}, only=[old_name])
    fixed = glbtool.fix_arm_weights(d) if '--no-armfix' not in sys.argv else 0
    if not raw:
        for name, (t0, t1, fps) in GAMECUT.items():
            glbtool.resample_clip(d, name, t0, t1, fps)
        glbtool.quantize_rotations(d)
        glbtool.quantize_mesh(d)
    os.makedirs(dest, exist_ok=True)
    n = d.save(os.path.join(dest, h + '.glb'))
    return {'hero': h, 'bytes': n, 'clips': got, 'moves': how, 'fixed': fixed}


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    opts = dict(a[2:].split('=', 1) for a in argv[1:] if a.startswith('--') and '=' in a)
    out, dest = args[0], args[1]
    heroes = args[2:] or sorted(h for h in os.listdir(out) if os.path.exists(os.path.join(out, h, 'model.glb')))
    share = opts.get('share-from', 'kira,leo').split(',')
    mode = opts.get('mode', 'world')
    made = []
    for h in heroes:
        r = build(out, dest, h, share, mode, '--raw' in argv)
        if r:
            made.append(h)
            print('%-8s %5.2f MB  %-10s cape/hair fix %5d  %s' % (h, r['bytes'] / 1e6, r['moves'], r['fixed'], ','.join(r['clips'])))
    lst = os.path.join(dest, 'list.json')
    old = []
    if os.path.exists(lst):
        try: old = json.load(open(lst))
        except Exception: old = []
    ids = {(q if isinstance(q, str) else q.get('id')) for q in old}
    for h in made:
        if h not in ids: old.append(h)
    json.dump(old, open(lst, 'w'))
    print(len(made), 'hero files;', len(old), 'in list.json')


if __name__ == '__main__':
    main(sys.argv)
