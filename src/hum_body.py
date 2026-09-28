"""The body: MPFB's body minus the head faces (they share the neck ring exactly), skinned to the
game_engine rig, with the same macro keys as the head stored as residuals (see hum_rig).
"""
import os
import bpy
import numpy as np

import hum_mpfb, hum_head, hum_rig

BODY = "Body"


class BodyIndex:
    """Which source vertices/faces make the body, and their UVs."""

    def __init__(self, src, rig):
        C = hum_mpfb.capture(src)
        body = hum_mpfb.group_members(src, "body")
        me = src.data
        keep_head, _ = hum_head.head_faces(me, C, body)
        body_set = np.zeros(len(C), bool)
        body_set[body] = True
        faces = [p for p in me.polygons if not keep_head[p.index] and all(body_set[v] for v in p.vertices)]
        used = np.array(sorted({v for p in faces for v in p.vertices}), dtype=np.int64)
        remap = {int(v): i for i, v in enumerate(used)}
        self.idx = used
        self.faces = [tuple(remap[v] for v in p.vertices) for p in faces]
        uv = me.uv_layers[0].data
        self.face_uvs = [[tuple(uv[li].uv) for li in p.loop_indices] for p in faces]


def build(scene, bi, C, name=BODY, materials=()):
    """Create/replace the body object at coords C (full MPFB coords of the neutral state)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(C[bi.idx].tolist(), [], bi.faces)
    me.update()
    for m in materials:
        me.materials.append(m)
    uvl = me.uv_layers.new(name="UVMap")
    for fi, p in enumerate(me.polygons):
        for k, li in enumerate(p.loop_indices):
            uvl.data[li].uv = bi.face_uvs[fi][k]
        p.use_smooth = True
    old = bpy.data.objects.get(name)
    if old is not None:
        old_me = old.data
        old.data = me
        if old_me.users == 0:
            bpy.data.meshes.remove(old_me)
        ob = old
    else:
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
    return ob


def add_key(ob, name, co):
    if ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    kb = ob.data.shape_keys.key_blocks.get(name) or ob.shape_key_add(name=name, from_mix=False)
    kb.data.foreach_set("co", co.astype(np.float32).ravel())
    kb.slider_min = -1.0
    return kb


# ------------------------------------------------------------------ paint (masks, like the head)

def paint_masks(body, sk, joints, nipple_z, size=1024):
    """T_Body_MaskA: R blush (knees, elbows, knuckles, toes), G shorts, B shading (/SHADE_MAX), A chest band.
    T_Body_MaskB: R freckles. joints: {bone: head position} of the neutral body."""
    import hum_paint
    ss = hum_paint.smoothstep
    me = body.data
    co, no, e = hum_paint.mesh_arrays(me)
    W = hum_rig.weights_of(body, sk)
    group = lambda names: W[:, [sk.index[n] for n in names if n in sk.index]].sum(1)
    torso = group(["pelvis", "spine_01", "spine_02", "spine_03"])
    fingers = group([b for b in sk.bones if any(b.startswith(f) for f in ("thumb", "index", "middle", "ring", "pinky"))])
    toes = group(["ball_l", "ball_r"])
    ao = hum_paint.smooth_vals(hum_paint.ray_ao(body, co, no, rays=20, dist=0.08), e, len(co), it=2)
    cav = hum_paint.smooth_vals(hum_paint.curvature(co, no, e), e, len(co), it=3)
    hum_paint.write_attr(me, "_hb_a", np.stack([ao, np.clip(cav / 400.0 + 0.5, 0, 1), torso], 1))
    hum_paint.write_attr(me, "_hb_b", np.stack([fingers, toes, np.zeros(len(co))], 1))
    P, valid = hum_paint.bake_map(body, "pos", size)
    N, _ = hum_paint.bake_map(body, "nrm", size)
    A, _ = hum_paint.bake_map(body, "attr", size, "_hb_a")
    B, _ = hum_paint.bake_map(body, "attr", size, "_hb_b")
    AO, CAV, TORSO = A[..., 0], (A[..., 1] - 0.5) * 400.0, A[..., 2]
    FING, TOES = B[..., 0], B[..., 1]
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    g = lambda c, r: np.exp(-((P - c) ** 2).sum(-1) / (2 * r * r))

    blush = 0.5 * FING + 0.5 * TOES
    for side in ("l", "r"):
        blush += 0.7 * g(joints["calf_" + side] + np.array([0, -0.04, 0]), 0.035)          # knees (front)
        blush += 0.5 * g(joints["lowerarm_" + side], 0.03)                                 # elbows
    blush = np.clip(blush, 0, 1)

    # shorts: from the waist to mid-thigh (plain painted underclothes)
    waist = joints["spine_01"][2] + 0.01
    leg = joints["thigh_l"][2] - 0.10
    shorts = ss(waist + 0.006, waist - 0.006, z) * ss(leg - 0.006, leg + 0.006, z) * (1 - np.clip(FING * 3, 0, 1))
    shorts *= ss(0.30, 0.22, np.abs(x))                                                   # not the hanging hands
    # chest band (worn by feminine characters)
    band = ss(nipple_z - 0.055, nipple_z - 0.045, z) * ss(nipple_z + 0.06, nipple_z + 0.05, z) * ss(0.5, 0.8, TORSO)

    light = 0.92 + 0.12 * N[..., 2]
    aot = 0.55 + 0.45 * np.clip(AO, 0, 1)
    c = np.clip(CAV / 60.0, -1, 1)
    shade = np.clip(light * aot * (1 - 0.3 * np.clip(c, 0, 1)) / hum_paint.SHADE_MAX, 0, 1)

    zone = ss(nipple_z - 0.02, nipple_z + 0.08, z) * (1 - np.clip(FING * 3, 0, 1))
    spots = hum_paint._noise3(P, 700.0, 5, valid & (zone > 0.05))
    frk = ss(0.38, 0.55, spots) * zone

    MA = np.stack([blush, shorts, shade, band], -1)
    MB = np.stack([frk, np.zeros_like(frk), np.zeros_like(frk), np.ones_like(frk)], -1)
    for M in (MA, MB):
        M[~valid] = 0
    MA = hum_paint.dilate(MA, valid)
    MB = hum_paint.dilate(MB, valid)
    ia = hum_paint.save_image("T_Body_MaskA", MA, os.path.join(hum_paint.TEX_DIR, "T_Body_MaskA.png"))
    ib = hum_paint.save_image("T_Body_MaskB", MB, os.path.join(hum_paint.TEX_DIR, "T_Body_MaskB.png"))
    return ia, ib
