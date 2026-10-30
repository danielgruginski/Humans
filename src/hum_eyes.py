"""The eye pass (2026-10-30, Daniel: "something in the eyes... they look weird/from an ugly person").

The eyeballs were 36 mm across behind a 26 x 7.8 mm slit, set 2.7 mm behind the lids, the opening low on the ball and
the gaze 4.6 deg down and 2.4 deg out per eye. hum_head.STYLE and eye_verts now build the new shape; patch() takes an
existing head there in place (basis, every shape key, the LODs), so a rebuild of the whole wardrobe isn't needed.

Check tools: opening() measures an eye as seen from the front; sheet() renders a before/after close-up sheet.
"""
import os
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import hum_head, hum_faces, hum_rig, hum_scene

OLD_TARGETS = {"l-eye-height2-decr": 0.7, "r-eye-height2-decr": 0.7}


def _arrays(kb, n):
    a = np.empty(n * 3, np.float32)
    kb.data.foreach_get("co", a)
    return a.reshape(-1, 3).astype(np.float64)


def old_style():
    st = dict(hum_head.STYLE)
    st["targets"] = {k: v for k, v in hum_head.STYLE["targets"].items() if "-eye-" not in k}
    st["targets"].update(OLD_TARGETS)
    return st


def _old_eye(rig, C_old, side):
    """The old ball's centre, radius and axes in the old state (rows of Q: template axes in the world)."""
    c, r, fwd = hum_head.eye_fit(C_old, rig, side)
    q = Vector((0, -1, 0)).rotation_difference(Vector(fwd)).to_matrix()
    return c, r * 0.96, np.array(q).T


def _patch_keys(me, nh_mask, D, eyes, ratio):
    """Add D to the skin of every key; rebuild each eye: eyes = [(indices, u (template coords), new basis positions)]."""
    keys = me.shape_keys.key_blocks
    n = len(me.vertices)
    fits = {}
    worst = 0.0
    for k in keys:
        a = _arrays(k, n)
        for s, (idx, u, Q, _new) in enumerate(eyes):
            U = np.c_[u, np.ones(len(u))]
            M, *_ = np.linalg.lstsq(U, a[idx], rcond=None)     # a = [u 1] @ M
            worst = max(worst, float(np.abs(U @ M - a[idx]).max()))
            fits[(k.name, s)] = M
    basis = keys[0].name
    for k in keys:
        a = _arrays(k, n)
        a[nh_mask] += D
        for s, (idx, u, Q, new) in enumerate(eyes):
            M, M0 = fits[(k.name, s)], fits[(basis, s)]
            ue = u @ Q.T                                       # the same world direction in the old template's frame
            a[idx] = new + ue @ (M[:3] - M0[:3]) * ratio + (M[3] - M0[3])
        k.data.foreach_set("co", a.astype(np.float32).ravel())
        if k.name == basis:
            me.vertices.foreach_set("co", a.astype(np.float32).ravel())
    me.update()
    return worst


def _mirror_right_eye_uv(ob):
    """One mask for both eyes with the inner corner at u < 0.5: the right eye's u is flipped."""
    me = ob.data
    uv = me.uv_layers["UVMap"]
    co = me.vertices
    for p in me.polygons:
        if p.material_index == 1 and co[p.vertices[0]].co.x < 0:
            for li in p.loop_indices:
                uv.data[li].uv[0] = 1.0 - uv.data[li].uv[0]


def patch(head=None):
    """Old eyes -> new eyes on Head, Head_L1, Head_L2. Run once: the old state is the code's old_style()."""
    head = head or bpy.data.objects["Head"]
    if head.get("eye_pass"):
        raise RuntimeError("this head already has the new eyes")
    head["eye_pass"] = 1
    src = bpy.data.objects["MPFB_Source"]
    rig = hum_head.Rig(src)
    C_old = hum_head.full_coords(src, rig, style=old_style())
    C_new = hum_head.full_coords(src, rig)
    me = head.data
    nh, ne = head["n_head_verts"], head["n_eye_verts"]
    n = len(me.vertices)
    basis0 = _arrays(me.shape_keys.key_blocks[0], n)
    H_old, H_new = C_old[rig.head_idx], C_new[rig.head_idx]
    print("old state vs Head basis, max diff mm:", float(np.abs(H_old - basis0[:nh]).max()) * 1000)
    D = H_new - H_old
    print("skin moved: max mm", float(np.linalg.norm(D, axis=1).max()) * 1000, "verts >0.01mm", int((np.linalg.norm(D, axis=1) > 1e-5).sum()))
    new_l = hum_head.eye_verts(C_new, rig, "l")
    new_r = hum_head.eye_verts(C_new, rig, "r")
    ratio = hum_head.EYE_BALL
    U = hum_head._EYE[0]
    Q = {s: _old_eye(rig, C_old, s)[2] for s in "lr"}
    mask = np.zeros(n, bool)
    mask[:nh] = True
    eyes = [(np.arange(nh, nh + ne), U, Q["l"], new_l), (np.arange(nh + ne, nh + 2 * ne), U, Q["r"], new_r)]
    # the LODs first: they read the full head's old skin
    kd = KDTree(nh)
    for i, co in enumerate(basis0[:nh]):
        kd.insert(co, i)
    kd.balance()
    report = {}
    for name in ("Head_L1", "Head_L2"):
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        lm = ob.data
        ln = len(lm.vertices)
        b = _arrays(lm.shape_keys.key_blocks[0], ln)
        eye_v = {v for p in lm.polygons if p.material_index == 1 for v in p.vertices}
        leyes = []
        for side, sign in (("l", 1), ("r", -1)):
            c, R, Qs = _old_eye(rig, C_old, side)
            cn, Rn = hum_head.eye_centre(C_new, rig, side)
            idx = np.array(sorted(v for v in eye_v if b[v, 0] * sign > 0))
            u = (b[idx] - c) / R @ Qs.T                        # template coords of the LOD's eye verts
            leyes.append((idx, u, Qs, cn + u * Rn))
        lmask = np.ones(ln, bool)
        lmask[list(eye_v)] = False
        LD = np.zeros((int(lmask.sum()), 3))
        for j, co in enumerate(b[lmask]):                      # the skin's move, from the nearest verts of the full head
            near = kd.find_n(co, 4)
            w = np.array([1.0 / max(d, 1e-5) ** 2 for _, _, d in near])
            LD[j] = (D[[i for _, i, _ in near]] * w[:, None]).sum(0) / w.sum()
        report[name] = (_patch_keys(lm, lmask, LD, leyes, ratio), len(eye_v))
        _mirror_right_eye_uv(ob)
    worst = _patch_keys(me, mask, D, eyes, ratio)
    _mirror_right_eye_uv(head)
    print("eye fit residual mm: head", worst * 1000, {k: (round(v[0] * 1000, 3), v[1]) for k, v in report.items()})
    return worst


def retarget(old_targets):
    """The lids from an earlier STYLE["targets"] to the current ones: the skin only, on Head and its LODs, every key."""
    head = bpy.data.objects["Head"]
    src = bpy.data.objects["MPFB_Source"]
    rig = hum_head.Rig(src)
    st = dict(hum_head.STYLE)
    st["targets"] = old_targets
    D = hum_head.full_coords(src, rig)[rig.head_idx] - hum_head.full_coords(src, rig, style=st)[rig.head_idx]
    me = head.data
    nh = head["n_head_verts"]
    n = len(me.vertices)
    basis0 = _arrays(me.shape_keys.key_blocks[0], n)
    kd = KDTree(nh)
    for i, co in enumerate(basis0[:nh]):
        kd.insert(co, i)
    kd.balance()
    for name in ("Head_L1", "Head_L2"):
        lm = bpy.data.objects[name].data
        ln = len(lm.vertices)
        b = _arrays(lm.shape_keys.key_blocks[0], ln)
        lmask = np.ones(ln, bool)
        lmask[list({v for p in lm.polygons if p.material_index == 1 for v in p.vertices})] = False
        LD = np.zeros((int(lmask.sum()), 3))
        for j, co in enumerate(b[lmask]):
            near = kd.find_n(co, 4)
            w = np.array([1.0 / max(d, 1e-5) ** 2 for _, _, d in near])
            LD[j] = (D[[i for _, i, _ in near]] * w[:, None]).sum(0) / w.sum()
        _patch_keys(lm, lmask, LD, [], 1.0)
    mask = np.zeros(n, bool)
    mask[:nh] = True
    _patch_keys(me, mask, D, [], 1.0)
    return float(np.linalg.norm(D, axis=1).max())


def opening(C_or_none=None, side="l", step=0.0003):
    """The eye opening of the Head's basis as seen from the front, in mm, with its iris cover."""
    head = bpy.data.objects["Head"]
    me = head.data
    nh, ne = head["n_head_verts"], head["n_eye_verts"]
    n = len(me.vertices)
    co = _arrays(me.shape_keys.key_blocks[0], n)
    k = 0 if side == "l" else 1
    E = co[nh + k * ne: nh + (k + 1) * ne]
    c = E.mean(0)
    R = float(np.linalg.norm(E - c, axis=1).mean())
    polys = [tuple(p.vertices) for p in me.polygons]
    eye = [p[0] >= nh for p in polys]
    bvh = BVHTree.FromPolygons([Vector(v) for v in co], polys)
    pts = []
    for x in np.arange(c[0] - 1.6 * R, c[0] + 1.6 * R, step):
        for z in np.arange(c[2] - 1.2 * R, c[2] + 1.2 * R, step):
            hit = bvh.ray_cast(Vector((x, c[1] - 0.2, z)), Vector((0, 1, 0)), 0.5)
            if hit[0] is not None and eye[hit[2]]:
                pts.append((x, z))
    P = np.array(pts)
    ax = np.abs(P[:, 0])
    col = P[np.abs(P[:, 0] - c[0]) < step]
    pole = E[0]
    return dict(R=R * 1000, w=float(np.ptp(ax)) * 1000, h=float(np.ptp(col[:, 1])) * 1000,
                up=float(col[:, 1].max() - pole[2]) * 1000, dn=float(col[:, 1].min() - pole[2]) * 1000,
                off=float(abs(pole[0]) - (ax.max() + ax.min()) / 2) * 1000, pole=[round(float(v), 4) for v in pole - c],
                inner=float(ax.min()) * 1000, outer=float(ax.max()) * 1000, ipd=float(2 * abs(c[0])) * 1000)


def sheet(out, seeds=(1, 14, 3, 9, 20, 27), size=460):
    """Close-ups of random faces (bare heads, front and three-quarter), for comparing eye passes."""
    sc = bpy.context.window_manager.windows[0].scene
    head = bpy.data.objects["Head"]
    cams = {}
    for name, off, lens in (("Cam_EyeF", Vector((0, -0.55, 0.0)), 85), ("Cam_Eye34", Vector((-0.34, -0.42, 0.02)), 85)):
        cam = bpy.data.objects.get(name)
        if cam is None:
            cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
            sc.collection.objects.link(cam)
        cam.data.lens = lens
        cams[name] = (cam, off)
    paths = []
    tmp = os.path.join(hum_scene.RENDERS, "_tmp")
    for s in seeds:
        f = hum_faces.random_face(s)
        f = dict(f, style=None, beard=None, outfit={}, height=0.0)
        hum_faces.apply_face(head, f)
        for name, (cam, off) in cams.items():
            eyes = _eye_mid(head)
            cam.location = eyes + off
            hum_scene.look_at(cam, eyes)
            paths.append(hum_scene.render(sc, cam, os.path.join(tmp, f"eyes_{s}_{name}.png"), size))
    hum_faces.apply_face(head, dict(keys={}, props={}))
    return hum_scene.sheet(paths, 4, os.path.join(hum_scene.RENDERS, out))


def _eye_mid(head):
    """World position between the eyes, in the current key mix and pose."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = head.evaluated_get(dg)
    me = ev.to_mesh()
    nh, ne = head["n_head_verts"], head["n_eye_verts"]
    a = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", a)
    ev.to_mesh_clear()
    a = a.reshape(-1, 3)[nh:nh + 2 * ne]
    return head.matrix_world @ Vector(a.mean(0).tolist())
