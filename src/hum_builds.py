"""Body builds: the body comes in 3 builds per sex; the face keeps every slider.

Why: garments followed ~90 body/face keys through approximate bindings (Surface Deform / nearest), and
layered armour stacked those errors (poke-through, returning nipples, torn napes). With a few fixed builds
every garment is built once per build, as an exact fit, and can be checked on every build.

Keys are split in two:
BODY_KEYS  sex, weight and muscle macros, the body sliders, neck width - set by the build only; they stay
           residual keys (bones + blend shapes) on head and body, and drive the skeleton.
face keys  everything else (face sliders, age, ancestry, their correctives) - head only. They stay residual
           (their bone movement is dropped with their joint deltas; folding it in stretched the neck by up to
           13 cm) and fade to zero at the neck ring, so the head always meets the build's body there.

Garments are built per build in "build space": Head and Body temporarily take the build's shape as their
basis (all keys shifted with it) and the joints move by the build's bone deltas, then every garment is
built as usual and finally moved back to the rest skeleton (v -= W @ dJ: the build's bones are pure
translations), so at runtime the build's bone deltas put it exactly on the build's body.
Names: Cloth_<Garment>_<Tag>[_L1|_L2], tag = M|F + build name.
"""
import numpy as np

import hum_faces as F
import hum_paint
import hum_rig

BUILD_NAMES = ["Slim", "Strong", "Heavy"]
BODY_KEYS = ({"Masculine", "Feminine", "Heavy", "Thin", "Muscular", "Slight"}
             | {f"{s}_{d}" for s in F.BODY_SLIDERS + ["NeckWidth"] for d in ("Pos", "Neg")})

_BASE = {
    "M": dict(Masculine=0.8, ShoulderWidth_Pos=0.24, ChestMuscle_Pos=0.2),
    "F": dict(Feminine=0.8, Hips_Pos=0.28, Waist_Neg=0.24, ShoulderWidth_Neg=0.2, Bust_Pos=0.16),
}
_SHAPE = {
    ("M", "Slim"): dict(Thin=0.4, Slight=0.25),
    ("F", "Slim"): dict(Thin=0.4, Slight=0.25, NeckWidth_Neg=0.2),
    ("M", "Strong"): dict(Muscular=0.8, ArmMuscle_Pos=0.6, ShoulderMuscle_Pos=0.6, LegMuscle_Pos=0.5,
                          ChestMuscle_Pos=0.5, BackMuscle_Pos=0.5, VShape_Pos=0.5, NeckWidth_Pos=0.3),
    ("F", "Strong"): dict(Muscular=0.7, ArmMuscle_Pos=0.5, ShoulderMuscle_Pos=0.45, LegMuscle_Pos=0.45,
                          ChestMuscle_Pos=0.25, BackMuscle_Pos=0.4, VShape_Pos=0.25, NeckWidth_Pos=0.1),
    ("M", "Heavy"): dict(Heavy=0.8, Belly_Pos=0.5, NeckWidth_Pos=0.35),
    ("F", "Heavy"): dict(Heavy=0.75, Belly_Pos=0.35, Hips_Pos=0.4, Waist_Neg=0.0),
}
BUILDS = {}
for _sex in "MF":
    for _name in BUILD_NAMES:
        _k = dict(_BASE[_sex])
        _k.update(_SHAPE[(_sex, _name)])
        BUILDS[_sex + _name] = dict(sex=_sex, name=_name, keys={k: v for k, v in _k.items() if v > 0})
BUILD_ODDS = {"Slim": 0.4, "Strong": 0.3, "Heavy": 0.3}


def tag_of(masc, name):
    return ("M" if masc else "F") + name


def body_weights(keys):
    return {k: v for k, v in keys.items() if k in BODY_KEYS}


def joint_offsets(keys, sk):
    dJ = np.zeros((len(sk.bones), 3))
    for k, w in keys.items():
        d = hum_rig.JOINT_DELTAS.get(k)
        if d is not None:
            dJ += w * np.asarray(d)
    return dJ


# ------------------------------------------------------------------ one-time key split

def _co(kb):
    a = np.empty(len(kb.data) * 3, np.float32)
    kb.data.foreach_get("co", a)
    return a.reshape(-1, 3).astype(float)


def _set_co(kb, V):
    kb.data.foreach_set("co", np.asarray(V, np.float32).ravel())


def neck_fade(ob, base):
    """0 on the neck edge of a head mesh, 1 from ~4 cm up: by height above its lowest point and by distance
    to the edge ring itself (the ring rises ~4 cm from throat to nape, so height alone left the nape edge
    moving with ancestry/age keys and the seam opened)."""
    import bmesh
    from mathutils.kdtree import KDTree
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    z0 = float(base[:, 2].min())
    ring = sorted({v.index for e in bm.edges if e.is_boundary for v in e.verts if base[v.index, 2] < z0 + 0.12})
    bm.free()
    kd = KDTree(len(ring))
    for k, i in enumerate(ring):
        kd.insert(base[i], k)
    kd.balance()
    d = np.array([kd.find(p)[2] for p in base])
    return hum_paint.smoothstep(z0, z0 + 0.045, base[:, 2]) * hum_paint.smoothstep(0.0, 0.035, d)


def split_keys(head, body, sk):
    """Face keys -> residual shapes faded at the neck ring (head); body loses them; joint deltas keep only
    the body keys. Idempotent (flag on the head)."""
    if head.get("keys_split"):
        return 0
    kbs = head.data.shape_keys.key_blocks
    base = _co(kbs[0])
    fade = neck_fade(head, base)[:, None]
    n = 0
    for kb in kbs[1:]:
        if kb.name in BODY_KEYS:
            continue
        _set_co(kb, base + (_co(kb) - base) * fade)
        n += 1
    for kb in list(body.data.shape_keys.key_blocks[1:]):
        if kb.name not in BODY_KEYS:
            body.shape_key_remove(kb)
    for k in list(hum_rig.JOINT_DELTAS):
        if k not in BODY_KEYS:
            del hum_rig.JOINT_DELTAS[k]
    head["keys_split"] = True
    return n


# ------------------------------------------------------------------ build space

class BuildSpace:
    """with BuildSpace(tag, sk): Head and Body have the build's shape as basis (keys shifted along) and
    hum_cloth.BUILD carries the tag and bone deltas. Restored on exit."""

    def __init__(self, tag, sk):
        self.tag, self.sk = tag, sk
        self.keys = BUILDS[tag]["keys"]
        self.dJ = joint_offsets(self.keys, sk)

    def __enter__(self):
        import bpy
        import hum_cloth
        self.saved = []
        for name in ("Head", "Body"):
            ob = bpy.data.objects[name]
            me = ob.data
            kbs = me.shape_keys.key_blocks
            base = _co(kbs[0])
            S = base.copy()
            for k, w in self.keys.items():
                kb = kbs.get(k)
                if kb is not None:
                    S += w * (_co(kb) - base)
            S += hum_rig.weights_of(ob, self.sk) @ self.dJ
            D = S - base
            self.saved.append((ob, [_co(kb) for kb in kbs], np.array([v.co[:] for v in me.vertices])))
            for kb in kbs:
                _set_co(kb, _co(kb) + D)
                kb.value = 0.0
            me.vertices.foreach_set("co", (np.array([v.co[:] for v in me.vertices]) + D).astype(np.float32).ravel())
            me.update()
        hum_cloth.BUILD = dict(tag=self.tag, dJ=self.dJ)
        return self

    def __exit__(self, *exc):
        import hum_cloth
        for ob, keys, vco in self.saved:
            for kb, K in zip(ob.data.shape_keys.key_blocks, keys):
                _set_co(kb, K)
            ob.data.vertices.foreach_set("co", vco.astype(np.float32).ravel())
            ob.data.update()
        hum_cloth.BUILD = None
        return False


def build_coords(ob, sk):
    """A garment's basis coords in the current build space (garments are stored at rest)."""
    import hum_cloth
    kb = ob.data.shape_keys.key_blocks[0] if ob.data.shape_keys else None
    P = _co(kb) if kb else np.array([v.co[:] for v in ob.data.vertices])
    if ob.get("at_rest") and hum_cloth.BUILD is not None:
        P = P + hum_rig.weights_of(ob, sk) @ hum_cloth.BUILD["dJ"]
    return P


def to_rest(ob, dJ, sk):
    """Move a garment built in build space back onto the rest skeleton (translation-only skinning)."""
    W = hum_rig.weights_of(ob, sk)
    D = W @ dJ
    me = ob.data
    if me.shape_keys:
        for kb in me.shape_keys.key_blocks:
            _set_co(kb, _co(kb) - D)
    me.vertices.foreach_set("co", (np.array([v.co[:] for v in me.vertices]) - D).astype(np.float32).ravel())
    me.update()
    ob["at_rest"] = True


def build_wardrobe(scene, arm, sk, tags=None, names=None, log=print):
    """Every garment for every build (LOD0 + L1/L2)."""
    import bpy
    import hum_armor
    import hum_cloth
    body = bpy.data.objects["Body"]
    out = {}
    for tag in (tags or list(BUILDS)):
        with BuildSpace(tag, sk) as bs:
            hum_rig.rest(arm)
            B = hum_cloth.BodyFrame(body, arm, sk)
            B._R = B.regions()
            for name in (names or list(hum_cloth.GARMENTS)):
                if hum_cloth.GARMENTS[name].get("bodysuit"):  # painted on the body: no geometry
                    continue
                if hum_cloth.GARMENTS[name].get("headgear"):
                    ob, nk = hum_armor.build_headgear(scene, name, arm, sk)
                else:
                    ob, nk = hum_cloth.build_garment(scene, B, name, arm, sk, body)
                to_rest(ob, bs.dJ, sk)                        # others read it back via build_coords
                if name in ("Cloak", "KnightCape"):           # capes: weights smoothed over the mesh
                    import hum_cloak
                    hum_cloak.reskin(ob, arm, sk)
                ob.hide_set(True)
                ob.hide_render = True
                out[ob.name] = hum_cloth.tris(ob)
                for lod in (1, 2):
                    lo, _ = hum_cloth.garment_lod(scene, ob, arm, sk, lod)
                    out[lo.name] = hum_cloth.tris(lo)
        log(tag)
    return out
