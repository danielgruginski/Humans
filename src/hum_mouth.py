"""The mouth pass (2026-10-30, Daniel: faces look ugly; the mouth after the eyes).

The mouth was 41.5 mm wide with the upper lip 3.8 mm over the lower and the seam 7.3 mm deep, a pout, and the slit at
the corners read as black hooks. hum_head.STYLE and lip_seal now build the new shape; these patches take an existing
head and its beards there in place (basis, every shape key, the LODs), so no rebuild of the wardrobe is needed.
"""
import numpy as np
import bpy
from mathutils.kdtree import KDTree

import hum_head, hum_eyes

OLD_TARGETS = {"mouth-scale-horiz-decr": 0.25, "mouth-scale-depth-decr": 0.35,
               "mouth-lowerlip-volume-decr": 0.3, "mouth-upperlip-volume-decr": 0.15}


def old_skin(src, rig):
    """The head's skin before the pass: the old targets, no seal."""
    st = dict(hum_head.STYLE)
    st["targets"] = {k: v for k, v in hum_head.STYLE["targets"].items() if not k.startswith("mouth-")}
    st["targets"].update(OLD_TARGETS)
    H = hum_head.full_coords(src, rig, style=st)[rig.head_idx]
    return H - hum_head.lip_seal(H)


def _kd(H):
    kd = KDTree(len(H))
    for i, co in enumerate(H):
        kd.insert(co, i)
    kd.balance()
    return kd


def _follow(b, kd, D):
    """A move for other vertices b, from the nearest vertices of the skin that moved."""
    out = np.zeros(b.shape)
    for j, co in enumerate(b):
        near = kd.find_n(co, 4)
        w = np.array([1.0 / max(d, 1e-5) ** 2 for _, _, d in near])
        out[j] = (D[[i for _, i, _ in near]] * w[:, None]).sum(0) / w.sum()
    return out


def seal(head=None):
    """Close the lips on Head + LODs, every key. Run once, after the mouth targets (hum_eyes.retarget)."""
    head = head or bpy.data.objects["Head"]
    if head.get("lip_seal"):
        raise RuntimeError("this head's lips are already closed")
    head["lip_seal"] = 1
    me = head.data
    nh = head["n_head_verts"]
    n = len(me.vertices)
    basis = hum_eyes._arrays(me.shape_keys.key_blocks[0], n)[:nh]
    D = hum_head.lip_seal(basis)
    kd = _kd(basis)
    for name in ("Head_L1", "Head_L2"):
        lm = bpy.data.objects[name].data
        ln = len(lm.vertices)
        b = hum_eyes._arrays(lm.shape_keys.key_blocks[0], ln)
        mask = np.ones(ln, bool)
        mask[list({v for p in lm.polygons if p.material_index == 1 for v in p.vertices})] = False
        hum_eyes._patch_keys(lm, mask, _follow(b[mask], kd, D), [], 1.0)
    mask = np.zeros(n, bool)
    mask[:nh] = True
    hum_eyes._patch_keys(me, mask, D, [], 1.0)
    return float(np.linalg.norm(D, axis=1).max())


def beards():
    """Beard_* and their LODs follow the skin's whole move, so a wider mouth doesn't push through the hole round it."""
    src = bpy.data.objects["MPFB_Source"]
    rig = hum_head.Rig(src)
    head = bpy.data.objects["Head"]
    if head.get("mouth_beards"):
        raise RuntimeError("the beards already follow the new mouth")
    head["mouth_beards"] = 1
    H0 = old_skin(src, rig)
    D = hum_head.full_coords(src, rig)[rig.head_idx] - H0
    kd = _kd(H0)
    report = {}
    for ob in bpy.data.objects:
        if not ob.name.startswith("Beard_") or not ob.data.shape_keys:
            continue
        me = ob.data
        n = len(me.vertices)
        b = hum_eyes._arrays(me.shape_keys.key_blocks[0], n)
        M = _follow(b, kd, D)
        hum_eyes._patch_keys(me, np.ones(n, bool), M, [], 1.0)
        report[ob.name] = round(float(np.linalg.norm(M, axis=1).max()) * 1000, 2)
    return report
