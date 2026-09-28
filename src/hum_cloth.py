"""Clothing: garments built around the neutral body, bound to the body's keys (like hair to the head) and
skinned from the body, so they fit every build and animate.

Body coordinates (per body vertex): which part it belongs to (torso, arm, leg, hand, foot, head/neck by skin
weights) and, on limbs, s = position along the limb (0 at the shoulder/hip joint .. 1 at the wrist/ankle).

Body regions (UV "Region".x on the body, an integer id): the body shader hides the regions a character's
garments cover, so skin never pokes through.
"""
import math
import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import hum_hair, hum_paint, hum_rig

ss = hum_paint.smoothstep
CLOTH_COL = "HUM_Cloth"

# body regions a garment can hide (bit id in the body's "Region" UV). Margins: collar (skin just under the
# neck line), wrist and ankle are hidden only by garments that reach well past them, so no gaps open at
# necklines, cuffs and hems.
REGIONS = dict(none=0, chest=1, belly=2, pelvis=3, thigh_up=4, thigh_low=5, shin_low=6, foot=7,
               upperarm=8, forearm=9, hand=10, shin_up=11, wrist=12, collar=13, ankle=14, neck=15)
MARGIN = {REGIONS[k] for k in ("none", "hand", "wrist", "collar", "ankle", "neck")}   # never covered on inner layers


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


# ------------------------------------------------------------------ body frame

BUILD = None          # set by hum_builds.BuildSpace: dict(tag, dJ) while garments are built for a build


def cloth_name(name):
    """Cloth_<garment>[_<build tag>]."""
    return "Cloth_" + name + ("_" + BUILD["tag"] if BUILD else "")


def parse_cloth(obname):
    """(garment, build tag or None, lod) from Cloth_<G>[_<Tag>][_L<n>]."""
    parts = obname[6:].split("_")
    lod = 0
    if len(parts) > 1 and parts[-1][:1] == "L" and parts[-1][1:].isdigit():
        lod = int(parts[-1][1:])
        parts = parts[:-1]
    return parts[0], (parts[1] if len(parts) > 1 else None), lod


class BodyFrame:
    """Neutral body coords, normals, parts, limb parameters, joints and a BVH."""

    def __init__(self, body, arm, sk):
        me = body.data
        kb = me.shape_keys.key_blocks["Basis"] if me.shape_keys else None
        self.co = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in me.vertices])
        self.body = body
        self.faces = [tuple(p.vertices) for p in me.polygons]
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in self.co]
        for f in self.faces:
            bm.faces.new([vs[i] for i in f])
        bm.normal_update()
        self.no = np.array([v.normal[:] for v in bm.verts])
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()
        self.sk = sk
        self.W = hum_rig.weights_of(body, sk)
        self.j = {b.name: np.array(b.head_local) for b in arm.data.bones}
        self.jt = {b.name: np.array(b.tail_local) for b in arm.data.bones}
        if BUILD is not None:                             # the build's bones (pure translations)
            for i, b in enumerate(sk.bones):
                if b in self.j:
                    self.j[b] = self.j[b] + BUILD["dJ"][i]
                    self.jt[b] = self.jt[b] + BUILD["dJ"][i]
        g = lambda names: self.W[:, [sk.index[n] for n in names if n in sk.index]].sum(1)
        fingers = [b for b in sk.bones if b.startswith(("thumb", "index", "middle", "ring", "pinky"))]
        parts = {
            "torso": g(["pelvis", "spine_01", "spine_02", "spine_03", "clavicle_l", "clavicle_r"]),
            "neck": g(["neck_01", "head"]),
            "arm_l": g(["upperarm_l", "lowerarm_l"]), "arm_r": g(["upperarm_r", "lowerarm_r"]),
            "hand_l": g(["hand_l"] + [f for f in fingers if f.endswith("_l")]),
            "hand_r": g(["hand_r"] + [f for f in fingers if f.endswith("_r")]),
            "leg_l": g(["thigh_l", "calf_l"]), "leg_r": g(["thigh_r", "calf_r"]),
            "foot_l": g(["foot_l", "ball_l"]), "foot_r": g(["foot_r", "ball_r"]),
        }
        self.part_names = list(parts)
        P = np.stack([parts[k] for k in self.part_names], 1)
        self.part = np.array(self.part_names)[np.argmax(P, 1)]
        self.parts = parts
        self.s = np.zeros(len(self.co))
        for side in "lr":
            for kind, chain in (("arm", ("upperarm", "lowerarm", "hand")), ("leg", ("thigh", "calf", "foot"))):
                J = [self.j[f"{c}_{side}"] for c in chain]
                idx = np.where(np.isin(self.part, [f"{kind}_{side}", f"{'hand' if kind == 'arm' else 'foot'}_{side}"]))[0]
                self.s[idx] = self.limb_param(self.co[idx], J)
        self.waist_z = float(self.j["spine_02"][2])
        self.hip_z = float(self.j["spine_01"][2]) - 0.03
        self.crotch_z = float(self.j["thigh_l"][2]) - 0.07
        self.neck_z = float(self.j["neck_01"][2]) - 0.035
        self.smooth_anatomy()

    def smooth_anatomy(self, iters=40, apex_iters=1200):
        """Garments are built over this body: the torso Taubin-smoothed (nipples, navel and ribs melt away,
        the breasts' volume stays), so no fabric or leather shows them."""
        self.co_raw = self.co.copy()
        n = len(self.co)
        E = np.array([(f[k], f[(k + 1) % len(f)]) for f in self.faces for k in range(len(f))])
        E = np.vstack([E, E[:, ::-1]])
        deg = np.bincount(E[:, 0], minlength=n).astype(float)[:, None]
        move = (self.part == "torso")[:, None]
        V = self.co.copy()
        for it in range(iters):
            avg = np.zeros_like(V)
            np.add.at(avg, E[:, 0], V[E[:, 1]])
            lam = 0.5 if it % 2 == 0 else -0.53
            V = np.where(move, V + lam * (avg / np.maximum(deg, 1) - V), V)
        # the breast (or pec) comes to a cone at its apex: a garment (2 cm edges) puts one vertex on the tip
        # and its smooth normals read as a nipple. Many more Taubin steps inside a 6 cm falloff round the
        # tip into a dome and keep the breast's volume
        w = np.zeros(n)
        self.apex = []
        band = ((self.part == "torso") & (self.co_raw[:, 2] > self.waist_z + 0.08)
                & (self.co_raw[:, 2] < self.neck_z - 0.08) & (np.abs(self.co_raw[:, 0]) > 0.03))
        for sgn in (1, -1):
            m = band & (np.sign(self.co_raw[:, 0]) == sgn)
            if m.any():
                apex = self.co_raw[np.where(m)[0][np.argmin(self.co_raw[m, 1])]]
                self.apex.append(apex)
                d = np.linalg.norm(self.co_raw - apex, axis=1)
                w = np.maximum(w, hum_paint.smoothstep(0.06, 0.02, d) * (self.part == "torso"))
        w = w[:, None]
        for it in range(apex_iters):
            avg = np.zeros_like(V)
            np.add.at(avg, E[:, 0], V[E[:, 1]])
            lam = 0.5 if it % 2 == 0 else -0.53
            V = V + lam * w * (avg / np.maximum(deg, 1) - V)
        self.co = V
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in self.co]
        for f in self.faces:
            bm.faces.new([vs[i] for i in f])
        bm.normal_update()
        self.no = np.array([v.normal[:] for v in bm.verts])
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()

    @staticmethod
    def limb_param(P, J):
        """0 at J[0], 0.5 at J[1] (elbow/knee), 1 at J[2] (wrist/ankle); extrapolates past the ends."""
        best = np.full(len(P), np.inf)
        s = np.zeros(len(P))
        for k in range(2):
            a, b = J[k], J[k + 1]
            ab = b - a
            t = ((P - a) @ ab) / (ab @ ab)
            tc = np.clip(t, 0 if k else -0.5, 1 if k == 0 else 1.6)
            d = np.linalg.norm(P - (a + tc[:, None] * ab), axis=1)
            better = d < best
            best[better] = d[better]
            s[better] = 0.5 * k + 0.5 * tc[better]
        return s

    def regions(self):
        R = np.zeros(len(self.co), int)
        p, s, z = self.part, self.s, self.co[:, 2]
        W, ix = self.W, self.sk.index
        torso = p == "torso"
        R[torso & (z >= self.waist_z)] = REGIONS["chest"]
        R[torso & (z < self.waist_z) & (z >= self.hip_z)] = REGIONS["belly"]
        R[torso & (z < self.hip_z)] = REGIONS["pelvis"]
        arm = np.char.startswith(p, "arm")
        R[arm & (s < 0.5)] = REGIONS["upperarm"]
        R[arm & (s >= 0.5) & (s < 0.85)] = REGIONS["forearm"]
        R[arm & (s >= 0.85) & (s < 0.93)] = REGIONS["wrist"]
        R[np.char.startswith(p, "hand") | (arm & (s >= 0.93))] = REGIONS["hand"]
        leg = np.char.startswith(p, "leg")
        R[leg & (s < 0.25)] = REGIONS["thigh_up"]
        R[leg & (s >= 0.25) & (s < 0.5)] = REGIONS["thigh_low"]
        R[leg & (s >= 0.5) & (s < 0.72)] = REGIONS["shin_up"]
        R[leg & (s >= 0.72) & (s < 0.92)] = REGIONS["shin_low"]
        R[leg & (s >= 0.92)] = REGIONS["ankle"]
        R[np.char.startswith(p, "foot")] = REGIONS["foot"]
        R[p == "neck"] = REGIONS["neck"]                   # hidden under hoods and coifs
        # collar: torso skin within 3.5 cm of the neck
        neck = self.co[p == "neck"]
        if len(neck):
            from mathutils.kdtree import KDTree
            kd = KDTree(len(neck))
            for i, c in enumerate(neck):
                kd.insert(Vector(c), i)
            kd.balance()
            for i in np.where(torso)[0]:
                if kd.find(Vector(self.co[i]))[2] < 0.035:
                    R[i] = REGIONS["collar"]
        return R

    def neck_dist(self):
        """Distance of every body vertex to the neck (cached): outer layers get lower necklines."""
        if not hasattr(self, "_nd"):
            from mathutils.kdtree import KDTree
            neck = self.co[self.part == "neck"]
            kd = KDTree(len(neck))
            for i, c in enumerate(neck):
                kd.insert(Vector(c), i)
            kd.balance()
            self._nd = np.array([kd.find(Vector(c))[2] for c in self.co])
        return self._nd

    def nearest(self, p):
        loc, n, i, d = self.bvh.find_nearest(Vector(p))
        return np.array(loc), np.array(n), d


def write_garment_regions(B, ob, kinds):
    """Garment "Region" UV, like the body's: each face takes the region of the body under it, so an outer
    layer can hide it (a tunic hides the shirt's torso, boots the trouser shins). Hanging parts (skirts,
    belts) are region 0: never hidden."""
    if not hasattr(B, "_R"):
        B._R = B.regions()
    me = ob.data
    Rv = np.zeros(len(me.vertices), int)
    for v in me.vertices:
        if kinds[v.index] == "skirt":
            continue
        loc, n, fi, d = B.bvh.find_nearest(v.co)
        ids = [int(B._R[i]) for i in B.faces[fi]]
        Rv[v.index] = max(set(ids), key=ids.count)
    # per face; a face touching a margin region (never covered) stays visible: garment faces are coarse,
    # and a majority vote would bite teeth into the visible collar or cuff
    lay = me.uv_layers.get("Region") or me.uv_layers.new(name="Region")
    uv = np.zeros((len(me.loops), 2), np.float32)
    for p in me.polygons:
        ids = [int(Rv[v]) for v in p.vertices]
        keep = [r for r in ids if r in MARGIN]
        rid = keep[0] if keep else max(set(ids), key=ids.count)
        uv[p.loop_start:p.loop_start + p.loop_total, 0] = rid
    lay.data.foreach_set("uv", uv.ravel())
    me.uv_layers.active = me.uv_layers["UVMap"]


def cover_of(name):
    rec = GARMENTS[name]
    return rec.get("cover", rec["hide"])


def outfit_hides(outfit):
    """Per worn garment: the regions covered by the worn garments on higher layers (bit mask). A garment
    covers inner garments only where it is a tight shell ("cover", default "hide"): a skirt parts when
    walking, so what's under it must stay."""
    out = {}
    for g in outfit:
        m = 0
        for h in outfit:
            if GARMENTS[h]["layer"] > GARMENTS[g]["layer"]:
                for r in cover_of(h):
                    m |= 1 << r
        out[g] = m
    return out


def write_rest_uv(me, V, flat=None):
    """UV layers "RestXY" / "RestZ": every vertex's position on the undeformed body (metres), for the
    shader's 3D (triplanar) pattern - same scale everywhere, whatever the panel mapping. RestZ.y = 1 marks
    trims that keep their own flat UV."""
    V = np.asarray(V, float)
    flat = np.zeros(len(V)) if flat is None else np.asarray(flat, float)
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    a = me.uv_layers.get("RestXY") or me.uv_layers.new(name="RestXY")
    b = me.uv_layers.get("RestZ") or me.uv_layers.new(name="RestZ")
    a.data.foreach_set("uv", V[vi][:, :2].astype(np.float32).ravel())
    b.data.foreach_set("uv", np.stack([V[vi][:, 2], flat[vi]], 1).astype(np.float32).ravel())
    me.uv_layers.active = me.uv_layers["UVMap"]


def write_regions(body, R):
    """Body UV layer "Region": x = region id, constant per face (the majority of its vertices), so a
    face is hidden or shown whole - no interpolated ids along the region borders."""
    me = body.data
    lay = me.uv_layers.get("Region") or me.uv_layers.new(name="Region")
    uv = np.zeros((len(me.loops), 2), np.float32)
    for p in me.polygons:
        ids = [int(R[v]) for v in p.vertices]
        rid = max(set(ids), key=ids.count)
        uv[p.loop_start:p.loop_start + p.loop_total, 0] = rid
    lay.data.foreach_set("uv", uv.ravel())
    me.uv_layers.active = me.uv_layers["UVMap"]


# ------------------------------------------------------------------ garment geometry

def shell(B, mask, offset, smooth=12, decimate=0.4, name="_shell", restore=True, sole=False, edge_smooth=25):
    """Offset shell over the body faces where mask (per body vertex) > 0.5; offset(p, i) -> metres.
    Body details are smoothed out; returns (verts, faces) of a clean, decimated surface."""
    m = mask > 0.5
    faces = [f for f in B.faces if all(m[i] for i in f)]
    used = sorted({i for f in faces for i in f})
    remap = {v: k for k, v in enumerate(used)}
    F = [tuple(remap[i] for i in f) for f in faces]
    idx = np.array(used)
    off = np.array([offset(B.co[i], i) for i in idx])
    V = B.co[idx] + B.no[idx] * off[:, None]
    # smooth away anatomy (navel, nipples, ribs), keep boundaries, then restore the offset
    nb = [[] for _ in V]
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            nb[a].append(b)
            nb[b].append(a)
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
    boundary = np.zeros(len(V), bool)
    bnb = [[] for _ in V]
    for (a, b), c in edges.items():
        if c == 1:
            boundary[a] = boundary[b] = True
            bnb[a].append(b)
            bnb[b].append(a)
    # open edges follow the body's faces (a zigzag): straighten each edge loop along itself first,
    # dragging the next row of vertices along so the border faces don't fold
    bi = [i for i in range(len(V)) if boundary[i] and len(bnb[i]) == 2]
    for _ in range(edge_smooth):
        Q = V.copy()
        for i in bi:
            Q[i] = 0.5 * V[i] + 0.25 * (V[bnb[i][0]] + V[bnb[i][1]])
        for i in range(len(V)):
            if not boundary[i] and any(boundary[j] for j in nb[i]):
                Q[i] = 0.5 * V[i] + 0.5 * V[nb[i]].mean(0)
        V = Q
    for it in range(smooth):
        Q = V.copy()
        lam = 0.6 if restore else (0.5 if it % 2 == 0 else -0.53)   # Taubin (no shrink) when not restoring
        for i in range(len(V)):
            if nb[i]:
                w = (0.25 if boundary[i] else 1.0) * lam
                Q[i] = V[i] * (1 - w) + V[nb[i]].mean(0) * w
        if restore:
            for i in range(len(V)):
                loc, n, _ = B.nearest(Q[i])
                h = float(np.dot(Q[i] - loc, n))
                if h < off[i]:
                    Q[i] = Q[i] + n * (off[i] - h)
        V = Q
    if sole:                                                     # flat sole just under the ground
        low = V[:, 2] < 0.022
        V[low, 2] = np.minimum(V[low, 2], -0.004 + 0.3 * np.maximum(V[low, 2], 0))
    if decimate < 1.0:
        V, F = hum_hair._decimate(V, F, decimate)
    return V, F


def loft_skirt(B, z_top, z_hem, offset, flare=0.25, folds=7, fold_amp=0.006, rings=12, segs=40, front_only=None,
               stop_z=None, center=0.0):
    """A hanging skirt: rings from z_top down to z_hem around the body's hull, flaring out and folding.
    front_only=(deg) keeps only the front arc (an apron). Returns (verts, faces, uv)."""
    C = B.co
    torso_legs = np.isin(B.part, ["torso", "leg_l", "leg_r"])
    cx = 0.0
    cy = float(np.mean(C[torso_legs & (np.abs(C[:, 2] - z_top) < 0.03)][:, 1]))
    span = math.pi if front_only is None else math.radians(front_only)
    th = np.linspace(-span, span, segs + 1)                     # closed skirts duplicate the seam column
    if front_only is not None:
        th = th + center                                        # center: 0 = front, pi = back
    Z = np.linspace(z_top, z_hem, rings)
    R = np.zeros((rings, len(th)))
    for k, z in enumerate(Z):
        sl = torso_legs & (np.abs(C[:, 2] - z) < 0.025)
        if not sl.any():
            R[k] = R[k - 1]
            continue
        P = C[sl][:, :2] - np.array([cx, cy])
        # convex envelope (support function): smooth, no dip between the legs
        D = np.stack([np.sin(th), -np.cos(th)], 1)
        R[k] = (P @ D.T).max(0)
    for _ in range(4):                                          # smooth around the ring
        R[:, 1:-1] = 0.5 * R[:, 1:-1] + 0.25 * (R[:, :-2] + R[:, 2:])
        if front_only is None:
            R[:, 0] = R[:, -1] = 0.5 * (R[:, 0] + R[:, -1])
    for k in range(1, rings):                                   # never narrower going down
        R[k] = np.maximum(R[k], R[k - 1])
    t = np.linspace(0, 1, rings)[:, None]
    R = R + offset + flare * (z_top - z_hem) * t ** 1.5 * 0.35 + fold_amp * t * np.sin(folds * th[None, :] + 0.5)
    if stop_z is not None:                                      # keep only the rings above stop_z (an apron)
        keep = Z >= stop_z
        R, Z = R[keep], Z[keep]
        rings = len(Z)
    n = len(th)
    V = np.array([(cx + R[k, j] * math.sin(a), cy - R[k, j] * math.cos(a), Z[k])
                  for k in range(rings) for j, a in enumerate(th)])
    # winding: normals face out (front is -y, j runs toward +x, rings run down)
    F = [((k + 1) * n + j, (k + 1) * n + j + 1, k * n + j + 1, k * n + j) for k in range(rings - 1) for j in range(n - 1)]
    arc = np.r_[0, np.cumsum(np.abs(np.diff(th)))] * float(R.mean())
    UVv = np.array([(arc[j] / 0.25, (z_top - Z[k]) / 0.25) for k in range(rings) for j in range(n)])
    return V, F, UVv


def ring(B, z, height, offset, segs=48):
    """A band around the torso at height z (a belt)."""
    return loft_skirt(B, z + height / 2, z - height / 2, offset, flare=0.0, folds=0, fold_amp=0.0, rings=3, segs=segs)


def add_rim(V, F, depth=0.003, B=None):
    """Give open edges a visible thickness: a band folded inward toward the body."""
    edges = {}
    for fi, f in enumerate(F):
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges.setdefault(e, []).append((a, b))
    bnd = [ab[0] for e, ab in edges.items() if len(ab) == 1]
    if not bnd:
        return V, F
    V = list(map(tuple, V))
    F = list(F)
    inner = {}
    for (a, b) in bnd:
        for v in (a, b):
            if v not in inner:
                p = np.array(V[v])
                n = B.nearest(p)[1] if B is not None else np.array([0, 0, 1.0])
                inner[v] = len(V)
                V.append(tuple(p - n * depth))
        F.append((b, a, inner[a], inner[b]))
    return np.array(V), F


def cloth_uv(B, V):
    """Per-vertex UVs for a tiling fabric: cylindrical around the torso, arms or legs (by nearest body part)."""
    part = np.empty(len(V), dtype=object)
    s = np.zeros(len(V))
    for i, p in enumerate(V):
        loc, n, fi, d = B.bvh.find_nearest(Vector(p))
        vi = B.faces[fi][0]
        part[i] = B.part[vi]
        s[i] = B.s[vi]
    UV = np.zeros((len(V), 2))
    tile = 0.25
    for i, p in enumerate(V):
        pt = part[i]
        if pt in ("torso", "neck"):
            a = math.atan2(p[0], -(p[1] - 0.0))
            UV[i] = (a * 0.15 / tile, p[2] / tile)
        else:
            side = pt[-1]
            limb = "upperarm" if pt.startswith(("arm", "hand")) else "thigh"
            axis = B.jt[f"{limb}_{side}"] - B.j[f"{limb}_{side}"]
            axis = axis / np.linalg.norm(axis)
            ref = np.array([0, -1.0, 0]) - axis * axis[1] * -1
            ref = ref / np.linalg.norm(ref)
            q = p - B.j[f"{limb}_{side}"]
            q = q - axis * np.dot(q, axis)
            a = math.atan2(np.dot(np.cross(ref, q), axis), np.dot(ref, q))
            UV[i] = (a * 0.06 / tile + (10 if side == "l" else 20), float(np.dot(p - B.j[f"{limb}_{side}"], axis)) / tile)
    return UV


def loop_uvs(F, UVv):
    """Per-loop UVs from per-vertex UVs, unwrapping faces that straddle the cylinder seam."""
    out = []
    for f in F:
        us = [UVv[i] for i in f]
        u = np.array([x[0] for x in us])
        period = 2 * math.pi * (0.15 if u.max() < 5 else 0.06) / 0.25
        if u.max() - u.min() > 0.5 * period:
            u = np.where(u < u.mean(), u + period, u)
        out.extend((float(u[k]), float(us[k][1])) for k in range(len(f)))
    return out


def edge_factor(V, F, width=0.012):
    """1 near open edges (hems, cuffs, collars): the shader darkens a hem band there."""
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
    bv = np.array(sorted({v for e, c in edges.items() if c == 1 for v in e}), dtype=np.int64)
    if len(bv) == 0:
        return np.zeros(len(V))
    d = np.full(len(V), 1.0)
    for i in bv:
        d = np.minimum(d, np.linalg.norm(V - V[i], axis=1))
    return ss(width, width * 0.3, d)


def vertex_ao(V, F, extra_bvh, rays=12, dist=0.06):
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    for f in F:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bm.normal_update()
    own = BVHTree.FromBMesh(bm)
    no = np.array([v.normal[:] for v in bm.verts])
    bm.free()
    rng = np.random.default_rng(3)
    u1, u2 = rng.random(rays), rng.random(rays)
    r, phi = np.sqrt(u1), 2 * math.pi * u2
    Hs = np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - u1)], 1)
    ao = np.ones(len(V))
    for i, p in enumerate(V):
        n = Vector(no[i])
        if n.length < 1e-6:
            continue
        t = n.orthogonal().normalized()
        b = n.cross(t)
        o = Vector(p) + n * 0.0015
        hit = 0
        for h in Hs:
            dvec = t * h[0] + b * h[1] + n * h[2]
            if own.ray_cast(o, dvec, dist)[0] is not None or extra_bvh.ray_cast(o, dvec, dist)[0] is not None:
                hit += 1
        ao[i] = 1 - hit / rays
    return ao


# ------------------------------------------------------------------ recipes

def _arm_mask(B, s_max):
    return np.char.startswith(B.part, "arm") & (B.s < s_max)


def _leg_mask(B, s_min, s_max):
    p = B.part
    return (np.char.startswith(p, "leg") | np.char.startswith(p, "foot")) & (B.s >= s_min) & (B.s < s_max)


def _torso_mask(B, z_min, z_max=None):
    z = B.co[:, 2]
    m = (B.part == "torso") & (z >= z_min)
    if z_max is not None:
        m &= z < z_max
    return m


# each recipe: slot, material, hide (body regions), and a build(B) -> list of (verts, faces, uv, kind)
# kind "shell" = skinned from the body; "skirt" = hanging (pelvis/thigh blend)
def _shirt(B):
    m = (_torso_mask(B, B.hip_z - 0.05) | _arm_mask(B, 0.96)).astype(float)
    off = lambda p, i: 0.004 + (0.006 * B.s[i] if B.part[i].startswith("arm") else 0.0)
    V, F = shell(B, m, off)
    V, F = add_rim(V, F, 0.003, B)
    return [(V, F, None, "shell")]


def _trousers(B):
    m = (_torso_mask(B, -1, B.waist_z + 0.005) | _leg_mask(B, -1, 0.97)).astype(float)
    V, F = shell(B, m, lambda p, i: trouser_offset(B, i))
    V, F = add_rim(V, F, 0.003, B)
    return [(V, F, None, "shell")]


def _tunic(B):
    m = ((_torso_mask(B, B.hip_z - 0.01) & (B.neck_dist() >= 0.015)) | _arm_mask(B, 0.92)).astype(float)   # neckline below the shirt's
    off = lambda p, i: 0.011 + (0.008 * B.s[i] if B.part[i].startswith("arm") else 0.0)
    V, F = shell(B, m, off)
    V, F = add_rim(V, F, 0.004, B)
    SV, SF, SU = loft_skirt(B, B.hip_z + 0.01, B.crotch_z - 0.13, 0.013, flare=0.22, folds=6, fold_amp=0.005)
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


def _dress(B):
    m = (_torso_mask(B, B.waist_z - 0.07) | _arm_mask(B, 0.9)).astype(float)      # tucks under the skirt top
    off = lambda p, i: 0.006 + (0.008 * B.s[i] if B.part[i].startswith("arm") else 0.0)
    V, F = shell(B, m, off)
    V, F = add_rim(V, F, 0.003, B)
    SV, SF, SU = loft_skirt(B, B.waist_z - 0.01, 0.07, 0.012, segs=48, **DRESS_SKIRT)
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


def trouser_offset(B, i):
    return 0.0075 + (0.009 * max(B.s[i] - 0.2, 0) if B.part[i].startswith("leg") else 0.0)


def section_tube(P, origin, axis, up, t0, t1, rings=16, angles=32, offset=0.008):
    """A closed tube around the points P along axis (t0..t1 from origin): each ring is the convex envelope
    (support function) of the points' cross-section there, plus offset(t) (a number or a function).
    No concavities, so toes become a toe box and the calf a smooth shaft. Returns (verts, faces)."""
    axis = _unit(axis)
    e1 = _unit(up - axis * float(up @ axis))
    e2 = np.cross(axis, e1)
    Q = P - origin
    t = Q @ axis
    X = np.stack([Q @ e1, Q @ e2], 1)
    ph = np.linspace(0, 2 * np.pi, angles, endpoint=False)
    D = np.stack([np.cos(ph), np.sin(ph)], 1)
    T = np.linspace(t0, t1, rings)
    half = max(abs(T[1] - T[0]), 0.006)
    R, C = np.zeros((rings, angles)), np.zeros((rings, 2))
    for k, tk in enumerate(T):
        sel = np.abs(t - tk) < half
        if sel.sum() < 6:
            R[k], C[k] = (R[k - 1], C[k - 1]) if k else (0.02, 0.0)
            continue
        C[k] = X[sel].mean(0)
        R[k] = ((X[sel] - C[k]) @ D.T).max(0)
    for _ in range(3):
        R = 0.5 * R + 0.25 * (np.roll(R, 1, 1) + np.roll(R, -1, 1))
        R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
        C[1:-1] = 0.5 * C[1:-1] + 0.25 * (C[:-2] + C[2:])
    off = np.array([offset(tk) if callable(offset) else offset for tk in T])
    R = R + off[:, None]
    V = []
    for k in range(rings):
        for j in range(angles):
            q = C[k] + D[j] * R[k, j]
            V.append(origin + axis * T[k] + e1 * q[0] + e2 * q[1])
    F = [(k * angles + j, k * angles + (j + 1) % angles, (k + 1) * angles + (j + 1) % angles, (k + 1) * angles + j)
         for k in range(rings - 1) for j in range(angles)]
    # rounded ends: a smaller ring a little further out, then a centre fan
    for k, sgn in ((0, -1.0), (rings - 1, 1.0)):
        base = k * angles
        c3 = origin + axis * T[k] + e1 * C[k][0] + e2 * C[k][1]
        r_mean = float(R[k].mean())
        ring2 = len(V)
        for j in range(angles):
            V.append(c3 + (np.array(V[base + j]) - c3) * 0.7 + axis * sgn * r_mean * 0.45)
        tip = len(V)
        V.append(c3 + axis * sgn * r_mean * 0.7)
        for j in range(angles):
            a, b = base + j, base + (j + 1) % angles
            a2, b2 = ring2 + j, ring2 + (j + 1) % angles
            if sgn > 0:
                F += [(a, b, b2, a2), (a2, b2, tip)]
            else:
                F += [(b, a, a2, b2), (b2, a2, tip)]
    return np.array(V), F


def _remesh(V, F, voxel=0.004, smooth=4):
    """Union of closed surfaces as one clean surface (voxel remesh), lightly smoothed."""
    me = bpy.data.meshes.new("_rm")
    me.from_pydata(np.asarray(V).tolist(), [], F)
    ob = bpy.data.objects.new("_rm", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("r", 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    V2 = np.array([v.co[:] for v in bm.verts])
    F2 = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return V2, F2


def _cut_open(V, F, cuts):
    """Remove everything past each plane (co, no), near co and on its side of x = 0 (not the other boot)."""
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    for f in F:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    for co, no in cuts:
        co = Vector(co)
        mine = lambda v: (v.co - co).length < 0.15 and v.co.x * co.x > 0      # this leg's side only
        geom = [v for v in bm.verts if mine(v)]
        edges = {e for v in geom for e in v.link_edges}
        faces = {f for v in geom for f in v.link_faces}
        bmesh.ops.bisect_plane(bm, geom=geom + list(edges) + list(faces), plane_co=co, plane_no=Vector(no))
        kill = [v for v in bm.verts if mine(v) and (v.co - co).dot(Vector(no)) > 1e-5]
        bmesh.ops.delete(bm, geom=kill, context='VERTS')
    bm.verts.index_update()
    V2 = np.array([v.co[:] for v in bm.verts])
    F2 = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return V2, F2


def footwear(B, top_s, shaft_extra=0.005, sole_off=0.008, decimate=0.12):
    """A boot/shoe per foot: a foot tube (heel to toe, convex sections = toe box) and a shaft tube up the
    shin to limb param top_s (outside the trousers), fused by a voxel remesh, cut open at the top, a flat
    sole. Returns (verts, faces)."""
    Vs, Fs = [], []
    n = 0
    cuts = []
    for side in "lr":
        ank = B.j[f"foot_{side}"]
        knee = B.j[f"calf_{side}"]
        leg = B.part == f"leg_{side}"
        foot = (B.part == f"foot_{side}") | (leg & (B.s > 0.93))
        fwd = B.jt[f"ball_{side}"] - ank
        fwd[2] = 0.0
        P = B.co[foot]
        t = (P - ank) @ _unit(fwd)
        V, F = section_tube(P, ank, fwd, np.array([0, 0, 1.0]), t.min() + 0.012, t.max() - 0.006,
                            rings=18, offset=sole_off)
        Vs.append(V)
        Fs += [tuple(i + n for i in f) for f in F]
        n += len(V)
        up = _unit(knee - ank)
        shin = leg & (B.s > top_s - 0.08)
        Pl = B.co[shin]
        tl = (Pl - ank) @ up
        sl = B.s[shin]
        t_top = float(np.mean((B.co[leg & (np.abs(B.s - top_s) < 0.02)] - ank) @ up))

        def off(tk, tl=tl, sl=sl):
            near = np.abs(tl - tk) < 0.02
            sk = float(sl[near].mean()) if near.any() else top_s
            return 0.0075 + 0.009 * max(sk - 0.2, 0) + shaft_extra      # the trouser offset there + a bit
        V, F = section_tube(Pl, ank, up, -_unit(fwd), -0.01, t_top + 0.03, rings=14, offset=off)
        Vs.append(V)
        Fs += [tuple(i + n for i in f) for f in F]
        n += len(V)
        cuts.append((ank + up * t_top, up))
    V, F = _remesh(np.vstack(Vs), Fs)
    # smoothing and remeshing shrink the envelope a little: keep every vertex clear of the body
    # (shaft: clear of the trousers too)
    E = np.array([(f[k], f[(k + 1) % len(f)]) for f in F for k in range(len(f))])
    deg = np.bincount(E[:, 0], minlength=len(V)).astype(float)[:, None]
    for it in range(4):
        if it:                                            # smooth the pushed bumps, then push again
            avg = np.zeros_like(V)
            np.add.at(avg, E[:, 0], V[E[:, 1]])
            V = V * 0.5 + 0.5 * avg / np.maximum(deg, 1)
        for i, p in enumerate(V):
            loc, n, fi, d = B.bvh.find_nearest(Vector(p))
            vi = B.faces[fi][0]
            need = sole_off
            if B.part[vi].startswith("leg"):
                need = 0.0075 + 0.009 * max(B.s[vi] - 0.2, 0) + shaft_extra + 0.004
            h = float(np.dot(p - np.array(loc), np.array(n)))
            if h < need:
                V[i] = p + np.array(n) * (need - h)
    sole_z = float(B.co[np.char.startswith(B.part, "foot"), 2].min()) - 0.004
    low = V[:, 2] < sole_z + 0.018
    V[low, 2] = np.maximum(sole_z, sole_z + (V[low, 2] - sole_z) * 1.6 - 0.011)
    V, F = _cut_open(V, F, cuts)
    if decimate < 1.0:
        V, F = hum_hair._decimate(V, F, decimate)
    return V, F


def _boots(B):
    V, F = footwear(B, 0.64, decimate=0.06)
    V, F = add_rim(V, F, 0.004, B)
    return [(V, F, None, "shell")]


def _shoes(B):
    V, F = footwear(B, 0.9, shaft_extra=0.003, decimate=0.07)
    V, F = add_rim(V, F, 0.003, B)
    return [(V, F, None, "shell")]


def _belt(B):
    V, F, U = ring(B, B.hip_z + 0.03, 0.035, 0.019)
    return [(V, F, U, "skirt")]


DRESS_SKIRT = dict(flare=0.30, folds=9, fold_amp=0.008, rings=16)


def _apron(B):
    """The front of the dress's own skirt surface (same flare and folds), 1.2 cm further out, to the knee:
    it always lies on top of a dress (and hangs fine over trousers too)."""
    knee = float(B.j["calf_l"][2]) + 0.04
    V, F, U = loft_skirt(B, B.waist_z - 0.01, 0.07, 0.012 + 0.012, segs=16, front_only=60, stop_z=knee,
                         **DRESS_SKIRT)
    return [(V, F, U, "skirt")]


R = REGIONS
GARMENTS = {
    "Shirt": dict(slot="top", layer=1, material="cloth", build=_shirt, smooth_keys=10,
                  hide=[R["chest"], R["belly"], R["upperarm"], R["forearm"], R["wrist"]]),
    "Tunic": dict(slot="outer", layer=2, material="cloth", build=_tunic, skirt_follow=0.9, skirt_shell=1.0,
                  smooth_keys=10,
                  cover=[R["chest"], R["belly"], R["upperarm"]],       # not forearm: the cuff stays whole
                  hide=[R["chest"], R["belly"], R["pelvis"], R["upperarm"], R["forearm"], R["thigh_up"]]),
    "Dress": dict(slot="top", layer=1, material="cloth", build=_dress, smooth_keys=10,
                  hide=[R["chest"], R["belly"], R["pelvis"], R["upperarm"], R["forearm"], R["thigh_up"], R["thigh_low"],
                        R["shin_up"]]),                    # knees swing into the skirt when walking
    "Trousers": dict(slot="legs", layer=1, material="cloth", build=_trousers,
                     hide=[R["pelvis"], R["thigh_up"], R["thigh_low"], R["shin_up"], R["shin_low"]]),
    "Boots": dict(slot="feet", layer=2, material="leather", build=_boots, hide=[R["shin_low"], R["ankle"], R["foot"]],
                  smooth_keys=12),
    "Shoes": dict(slot="feet", layer=2, material="leather", build=_shoes, hide=[R["ankle"], R["foot"]], smooth_keys=12),
    "Belt": dict(slot="belt", layer=3, material="leather", build=_belt, hide=[]),
    "Apron": dict(slot="apron", layer=3, material="cloth", build=_apron, hide=[]),
}


import hum_armor                                          # noqa: E402  (leather armour, same machinery)
GARMENTS.update(hum_armor.ARMOR)
import hum_cloak                                          # noqa: E402
GARMENTS.update(hum_cloak.CLOAK)
import hum_plate                                          # noqa: E402  (after the cloak: its hull ignores plate)
GARMENTS.update(hum_plate.PLATE)
hum_armor.ARMOR_SETS.update(hum_plate.PLATE_SETS)


# ------------------------------------------------------------------ objects

def smooth_key_deltas(ob, iters):
    """Smooth each shape key's offsets over the garment: body details (toes, knuckles) that the binding
    carried over melt away, the overall change of size and shape stays."""
    me = ob.data
    E = np.array([e.vertices[:] for e in me.edges])
    E = np.vstack([E, E[:, ::-1]])
    deg = np.bincount(E[:, 0], minlength=len(me.vertices)).astype(float)[:, None]
    kb = me.shape_keys.key_blocks
    base = np.array([v.co[:] for v in kb[0].data])
    for k in kb[1:]:
        D = np.array([v.co[:] for v in k.data]) - base
        for _ in range(iters):
            avg = np.zeros_like(D)
            np.add.at(avg, E[:, 0], D[E[:, 1]])
            D = 0.5 * D + 0.5 * avg / np.maximum(deg, 1)
        k.data.foreach_set("co", (base + D).astype(np.float32).ravel())


def garment_material(kind):
    """M_HumanCloth (weave), M_HumanLeather (grain), M_HumanQuilt (padding), M_HumanMail (rings); made once,
    shared by every garment."""
    import hum_material
    name = {"leather": "M_HumanLeather", "quilt": "M_HumanQuilt", "mail": "M_HumanMail",
            "plate": "M_HumanPlate"}.get(kind, "M_HumanCloth")
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    if kind == "plate":
        tex = bpy.data.images.get("T_Plate_Steel") or hum_paint.plate_texture()
        return hum_material.plate_material(tex, name)
    if kind in ("quilt", "mail"):
        quilt, mail = (bpy.data.images.get("T_Cloth_Quilt"), bpy.data.images.get("T_Cloth_Mail"))
        if quilt is None or mail is None:
            quilt, mail = hum_paint.armour_textures()
        return hum_material.cloth_material(quilt if kind == "quilt" else mail, name,
                                           roughness=0.9 if kind == "quilt" else 0.5)
    weave = bpy.data.images.get("T_Cloth_Weave")
    leather = bpy.data.images.get("T_Cloth_Leather")
    if weave is None or leather is None:
        weave, leather = hum_paint.cloth_textures()
    if kind == "leather":
        return hum_material.cloth_material(leather, name, roughness=0.6)
    return hum_material.cloth_material(weave, name)


def skirt_weights(B, V, sk, hem_z=None, follow=0.65):
    """Hanging parts: pelvis at the top, blending into the thighs (by side) and a little into the calves.
    A short skirt (hem_z above the knee) reaches `follow` thigh weight at its own hem, so a striding thigh
    can't overtake its front."""
    W = np.zeros((len(V), len(sk.bones)))
    hip = float(B.j["thigh_l"][2])
    knee = float(B.j["calf_l"][2])
    low = knee if hem_z is None or hem_z < knee else hem_z
    for i, p in enumerate(V):
        t = ss(hip + 0.05, low, p[2])                         # 0 above the hips .. 1 at the knees (or hem)
        tc = ss(knee, knee - 0.3, p[2]) * 0.3                 # calves below the knee
        side = ss(-0.04, 0.04, p[0])                          # 1 = left (+x)
        W[i, sk.index["pelvis"]] = 1 - follow * t - tc
        W[i, sk.index["thigh_l"]] = follow * t * side
        W[i, sk.index["thigh_r"]] = follow * t * (1 - side)
        W[i, sk.index["calf_l"]] = tc * side
        W[i, sk.index["calf_r"]] = tc * (1 - side)
        if p[2] > B.hip_z - 0.02:                             # belts and waistbands ride the spine
            k = ss(B.hip_z - 0.02, B.hip_z + 0.04, p[2])
            W[i] *= 1 - k
            W[i, sk.index["spine_01"]] += k
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


# ------------------------------------------------------------------ UVs by panel, seams and seam trims

UV_TILE = 0.25
UV_WRAPS = {"torso": 4, "arm_l": 1, "arm_r": 1, "leg_l": 2, "leg_r": 2}   # whole repeats around: no wrap seam
GROUP_OF = {"torso": "torso", "neck": "torso", "arm_l": "arm_l", "hand_l": "arm_l", "arm_r": "arm_r",
            "hand_r": "arm_r", "leg_l": "leg_l", "foot_l": "leg_l", "leg_r": "leg_r", "foot_r": "leg_r"}


def _panel_uv(B, group, p):
    """(u, v) of point p on the panel `group`: around the body or limb axis, u in whole repeats per turn."""
    if group == "torso":
        cy = float(B.j["spine_02"][1])
        a = math.atan2(p[0], -(p[1] - cy))
        return a / (2 * math.pi) * UV_WRAPS["torso"], p[2] / UV_TILE
    side = group[-1]
    limb = "upperarm" if group.startswith("arm") else "thigh"
    o = B.j[f"{limb}_{side}"]
    axis = C_unit(B.jt[f"{limb}_{side}"] - o)
    ref = C_unit(np.array([0, -1.0, 0]) - axis * axis[1])
    q = p - o
    t = float(np.dot(q, axis))
    q = q - axis * t
    a = math.atan2(float(np.dot(np.cross(ref, q), axis)), float(np.dot(ref, q)))
    return a / (2 * math.pi) * UV_WRAPS[group], t / UV_TILE


def C_unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def cloth_face_uvs(B, V, F, group=None):
    """Per-loop UVs where every face takes one panel's mapping (the majority of its vertices' body parts):
    no face is stretched between the torso and a sleeve; the panels meet along seams instead. `group` forces
    one panel's mapping on every face (skirts: the torso's, so a gambeson's quilting runs on down from the
    body - mapped round each thigh, its channels restarted at the waist). Returns (loop uvs, face groups)."""
    vg = []
    for p in V:
        if group is not None:
            vg.append(group)
            continue
        loc, n, fi, d = B.bvh.find_nearest(Vector(p))
        vg.append(GROUP_OF.get(B.part[B.faces[fi][0]], "torso"))
    loops, fgroup = [], []
    for f in F:
        gs = [vg[i] for i in f]
        g = max(set(gs), key=gs.count)
        fgroup.append(g)
        uv = [_panel_uv(B, g, V[i]) for i in f]
        per = UV_WRAPS[g]
        u0 = uv[0][0]
        for u, v in uv:
            u = u + round((u0 - u) / per) * per                       # unwrap across the back / inner seam
            loops.append((float(u), float(v)))
    return loops, fgroup


def remap_skirt_uvs(ob, B, sk):
    """An already built garment's hanging faces (its skirt panels) re-mapped with the torso's mapping, like
    build_garment now does (call inside hum_builds.BuildSpace of the garment's build, B its BodyFrame)."""
    import hum_builds
    me = ob.data
    reg, lay = me.uv_layers.get("Region"), me.uv_layers.get("UVMap")
    if reg is None or lay is None:
        return 0
    P = hum_builds.build_coords(ob, sk)
    r = np.zeros(len(me.loops) * 2, np.float32)
    reg.data.foreach_get("uv", r)
    region = np.rint(r[0::2]).astype(int)
    uv = np.zeros(len(me.loops) * 2, np.float32)
    lay.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    vi = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    per = UV_WRAPS["torso"]
    n = 0
    for poly in me.polygons:
        li = range(poly.loop_start, poly.loop_start + poly.loop_total)
        if any(region[i] != 0 for i in li):
            continue
        us = [_panel_uv(B, "torso", P[vi[i]]) for i in li]
        u0 = us[0][0]
        for i, (u, v) in zip(li, us):
            uv[i] = (u + round((u0 - u) / per) * per, v)
        n += 1
    lay.data.foreach_set("uv", uv.ravel())
    me.update()
    return n


def seam_trim(V, F, fgroup, width=0.02, lift=0.004, min_len=0.2):
    """A raised binding strip (3 verts across, rounded) along every seam between the torso panel and a sleeve.
    The panel border zigzags over the decimated faces: the strip follows it smoothed and covers it."""
    edges = {}
    for fi, f in enumerate(F):
        for a, b in zip(f, f[1:] + f[:1]):
            edges.setdefault((min(a, b), max(a, b)), []).append(fi)
    bnd = [e for e, fs in edges.items() if len(fs) == 2 and
           {fgroup[fs[0]], fgroup[fs[1]]} in ({"torso", "arm_l"}, {"torso", "arm_r"})]
    if len(bnd) < 6:
        return None
    nb = {}
    for a, b in bnd:
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
    bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in V], [tuple(f) for f in F])
    TV, TF = [], []
    seen = set()
    for start in list(nb):
        if start in seen:
            continue
        ends = [v for v in nb if len(nb[v]) == 1 and v not in seen]
        cur = start
        # walk the component (prefer starting at an open end)
        comp = set()
        stack = [start]
        while stack:
            v = stack.pop()
            if v in comp:
                continue
            comp.add(v)
            stack += nb[v]
        ends = [v for v in comp if len(nb[v]) == 1]
        cur = ends[0] if ends else start
        chain = [cur]
        seen.add(cur)
        while True:
            nxt = [w for w in nb[cur] if w not in seen]
            if not nxt:
                break
            cur = nxt[0]
            chain.append(cur)
            seen.add(cur)
        seen |= comp
        if len(chain) < 5:
            continue
        closed = not ends and chain[0] in nb[chain[-1]]
        P = np.array([V[i] for i in chain], float)
        for _ in range(10):                                           # straighten the zigzag
            Q = P.copy()
            if closed:
                Q = 0.5 * P + 0.25 * (np.roll(P, 1, 0) + np.roll(P, -1, 0))
            else:
                Q[1:-1] = 0.5 * P[1:-1] + 0.25 * (P[:-2] + P[2:])
            P = Q
        if float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) < min_len:
            continue                                                  # stray faces, not a real seam
        m = len(P)
        k0 = len(TV)
        for i in range(m):
            loc, n, fi, d = bvh.find_nearest(Vector(P[i]))
            n = np.array(n)
            c = np.array(loc)
            t = P[(i + 1) % m] - P[i - 1] if closed else P[min(i + 1, m - 1)] - P[max(i - 1, 0)]
            s = C_unit(np.cross(n, t))
            TV += [c + n * lift - s * width / 2, c + n * (lift + 0.0025), c + n * lift + s * width / 2]
        rows = m if closed else m - 1
        for i in range(rows):
            a, b = k0 + 3 * i, k0 + 3 * ((i + 1) % m)
            TF += [(a, b, b + 1, a + 1), (a + 1, b + 1, b + 2, a + 2)]
    if not TV:
        return None
    return np.array(TV), TF


# one flat spot of each pattern for trims: a plain binding, not the fabric's pattern
TRIM_UV = {"mail": (0.5 / 24, 0.5 / 24), "quilt": (0.125, 0.3)}


def round_apex(B, V, F, iters=30, radius=0.06):
    """A garment's own vertices over the breast/pec apex, Taubin-smoothed (open edges kept): at 1.5-3 cm edges
    one vertex lands on the tip and its smooth normal reads as a nipple, however round the body under it."""
    apex = getattr(B, "apex", [])
    if not apex or not len(F):
        return V
    V = np.asarray(V, float)
    w = np.zeros(len(V))
    for a in apex:
        w = np.maximum(w, hum_paint.smoothstep(radius, radius / 3, np.linalg.norm(V - a, axis=1)))
    if w.max() <= 0:
        return V
    E = np.array([(f[k], f[(k + 1) % len(f)]) for f in F for k in range(len(f))])
    cnt = {}
    for a, b in E:
        e = (min(a, b), max(a, b))
        cnt[e] = cnt.get(e, 0) + 1
    edge = np.zeros(len(V), bool)
    for (a, b), c in cnt.items():
        if c == 1:
            edge[a] = edge[b] = True
    w = np.where(edge, 0.0, w)[:, None]
    E = np.vstack([E, E[:, ::-1]])
    deg = np.maximum(np.bincount(E[:, 0], minlength=len(V)), 1).astype(float)[:, None]
    for it in range(iters):
        avg = np.zeros_like(V)
        np.add.at(avg, E[:, 0], V[E[:, 1]])
        lam = 0.5 if it % 2 == 0 else -0.53
        V = V + lam * w * (avg / deg - V)
    return V


def part_channels(part, n):
    """A part's 5th item: an array (1 = metal studs/buckles, dropped at the LODs) or, for plate armour, a
    dict(detail=, polish=, mat=). Returns (detail, polish, mat) arrays."""
    x = part[4] if len(part) > 4 else None
    if isinstance(x, dict):
        return (np.asarray(x.get("detail", np.zeros(n)), float), np.asarray(x.get("polish", np.zeros(n)), float),
                np.asarray(x.get("mat", np.ones(n)), float))
    return (np.zeros(n) if x is None else np.asarray(x, float)), np.zeros(n), np.ones(n)


def part_orn(part, n):
    """A plate part's ornament weight per vertex (0 = plain), 0 for everything else."""
    x = part[4] if len(part) > 4 else None
    return np.asarray(x.get("orn", np.zeros(n)), float) if isinstance(x, dict) else np.zeros(n)


def part_orn_pat(part, n):
    """A plate part's ornament pattern (slice of T_Plate_Ornament) per vertex."""
    x = part[4] if len(part) > 4 else None
    return np.asarray(x.get("orn_pat", np.zeros(n)), float) if isinstance(x, dict) else np.zeros(n)


def write_ornament_uv(me, orn, pat=None):
    """UV layer "Ornament" (Unity uv4): x = ornament weight, y = pattern (slice of the ornament texture array)."""
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    uv = np.zeros((len(me.loops), 2), np.float32)
    uv[:, 0] = np.asarray(orn)[vi]
    if pat is not None:
        uv[:, 1] = np.asarray(pat)[vi]
    lay = me.uv_layers.get("Ornament") or me.uv_layers.new(name="Ornament")
    lay.data.foreach_set("uv", uv.ravel())
    me.uv_layers.active = me.uv_layers["UVMap"]


def cloth_data(material, ao, ed, detail, polish, mat):
    """ClothData colours. Fabrics: (AO, hem band, metal studs, 1). Plate: (AO, polish, LOD detail, material:
    1 steel / 0.5 trim / 0 leather)."""
    if material == "plate":
        return np.stack([ao, np.maximum(polish, 0.6 * ed), detail, mat], 1)
    return np.stack([ao, np.where(detail > 0.5, 0.0, ed), detail, np.ones_like(ao)], 1)


def build_garment(scene, B, name, arm, sk, body):
    rec = GARMENTS[name]
    hum_rig.rest(arm)
    for k in (body.data.shape_keys.key_blocks[1:] if body.data.shape_keys else []):
        k.value = 0.0
    parts = rec["build"](B)
    verts, faces, uvs, kinds, metals, stiff, trims, polishes, mats, orns, pats = [], [], [], [], [], [], [], [], [], [], []
    off = 0
    trim_uv = TRIM_UV.get(rec["material"], (0.37, 0.37))

    def add(V, F, loops, kind, metal, polish=None, mat=None, orn=None, pat=None):
        nonlocal off
        orns.append(np.zeros(len(V)) if orn is None else orn)
        pats.append(np.zeros(len(V)) if pat is None else pat)
        verts.append(V)
        faces.extend(tuple(i + off for i in f) for f in F)
        uvs.extend(loops)
        kinds.extend([kind] * len(V))
        metals.append(metal)
        polishes.append(np.zeros(len(V)) if polish is None else polish)
        mats.append(np.ones(len(V)) if mat is None else mat)
        off += len(V)

    for part in parts:
        V, F, U, kind = part[:4]
        metal, polish, mat = part_channels(part, len(V))
        plate = len(part) > 5 and part[5] is not None
        if plate:
            stiff.append((off, len(V), part[5]))           # {bone: w} (a stiff plate) or f(V, sk) -> W
        elif kind == "shell":
            V = round_apex(B, V, F)
        trim = None
        if U is not None:
            loops = loop_uvs(F, U)
        else:
            loops, fgroup = cloth_face_uvs(B, V, F, "torso" if kind == "skirt" else None)
            if kind == "shell" and not plate:
                trim = seam_trim(V, F, fgroup)             # binding over the torso/sleeve seams
        add(V, F, loops, kind, metal, polish, mat, part_orn(part, len(V)), part_orn_pat(part, len(V)))
        if trim is not None:
            TV, TF = trim
            trims.append((off, len(TV)))
            add(TV, TF, [trim_uv] * sum(len(f) for f in TF), kind, np.zeros(len(TV)))
    V = np.vstack(verts)
    me = bpy.data.meshes.new(cloth_name(name))
    me.from_pydata(V.tolist(), [], faces)
    me.update()
    lay = me.uv_layers.new(name="UVMap")
    lay.data.foreach_set("uv", np.array(uvs, np.float32).ravel())
    for p in me.polygons:
        p.use_smooth = True
    # data: R = AO (with the body), G = hem band
    ao = vertex_ao(V, faces, B.bvh)
    ed = edge_factor(V, faces)
    metal = np.concatenate(metals)                        # studs, buckles: shaded as iron
    for start, n in trims:                                # seam bindings read as a darker band
        ed[start:start + n] = 1.0
    att = me.color_attributes.new("ClothData", 'FLOAT_COLOR', 'POINT')
    data = cloth_data(rec["material"], ao, ed, metal, np.concatenate(polishes), np.concatenate(mats))
    att.data.foreach_set("color", data.astype(np.float32).ravel())
    ob = hum_hair.replace_object(scene, cloth_name(name), me)
    col = bpy.data.collections.get(CLOTH_COL) or bpy.data.collections.new(CLOTH_COL)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    col.objects.link(ob)
    ob["hum_slot"] = rec["slot"]
    ob["hum_hide"] = 0.0
    write_garment_regions(B, ob, np.array(kinds))
    flat = np.zeros(len(V))
    for start, n in trims:
        flat[start:start + n] = 1.0
    write_rest_uv(ob.data, V, flat)
    if rec["material"] == "plate":
        write_ornament_uv(ob.data, np.concatenate(orns), np.concatenate(pats))
    ob.data.materials.append(garment_material(rec["material"]))
    kinds = np.array(kinds)
    torso_faces = [fi for fi, f in enumerate(B.faces) if all(B.part[i] == "torso" for i in f)]
    if BUILD is not None:                                 # an exact fit for one build: no body keys
        nk = 0
    elif (kinds == "skirt").all():                          # hanging only: follow the waist and hips
        nk, _ = hum_hair.bind_keys_nearest(ob, body, faces=torso_faces)
    else:
        try:
            nk, _ = hum_hair.bind_keys(ob, body)
        except RuntimeError:                              # Surface Deform refused: nearest-point binding
            for m in list(ob.modifiers):
                ob.modifiers.remove(m)
            nk, _ = hum_hair.bind_keys_nearest(ob, body)
        if (kinds == "skirt").any():                      # the hanging part of a tunic/dress: torso only
            nk, _ = hum_hair.bind_keys_nearest(ob, body, faces=torso_faces,
                                               verts=np.where(kinds == "skirt")[0], merge=True)
    if rec.get("smooth_keys") and ob.data.shape_keys:
        smooth_key_deltas(ob, rec["smooth_keys"])
        # and over space: the body's keys carry nipples (feminine, bust, chest muscle, heavy); a 3 cm blur
        # removes them and keeps the muscle and belly shapes
        hum_hair.smooth_keys_spatial(ob, 0.03)
    Wt = hum_rig.transfer_weights(ob, body, sk)
    sv = kinds == "skirt"
    Ws = skirt_weights(B, V, sk, hem_z=float(V[sv, 2].min()) if sv.any() else None,
                       follow=rec.get("skirt_follow", 0.65))
    if rec.get("skirt_shell"):
        # a short skirt over the thighs moves like the body under it (like the trousers), so a striding
        # thigh can't poke through; only a centre band keeps the averaged weights (no crumpling between legs)
        k = np.array([ss(0.03, 0.08, abs(p[0])) for p in V])[:, None] * rec["skirt_shell"]
        Ws = Ws * (1 - k) + Wt * k
    W = np.where((kinds == "skirt")[:, None], Ws, Wt)
    for start, n, w in stiff:                             # stiff plates: the same weights on every vertex
        if callable(w):
            W[start:start + n] = w(V[start:start + n], sk)
            continue
        W[start:start + n] = 0.0
        for bone, x in w.items():
            W[start:start + n, sk.index[bone]] = x
    hum_rig.skin(ob, arm, sk, W)
    return ob, nk


# ------------------------------------------------------------------ LODs and the whole wardrobe

LOD_RATIO = {1: 0.4, 2: 0.18}


def _drop_metal(ob, channel=2, above=0.5):
    """Delete the vertices whose ClothData channel is above a threshold (b: studs, rivets, buckles)."""
    att = ob.data.color_attributes.get("ClothData")
    if att is None:
        return
    c = np.zeros(len(att.data) * 4, np.float32)
    att.data.foreach_get("color", c)
    kill = np.where(c[channel::4] > above)[0]
    if len(kill) == 0:
        return
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill], context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()


def garment_lod(scene, ob, arm, sk, lod):
    """<garment>_L<lod>: the garment decimated, bound to its own keys, weights interpolated from it
    (so skirts keep their hanging weights)."""
    import hum_lod
    name = ob.name + f"_L{lod}"
    old = bpy.data.objects.get(name)
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old)
        bpy.data.meshes.remove(me)
    me = ob.data.copy()
    me.name = name
    lo = bpy.data.objects.new(name, me)
    scene.collection.objects.link(lo)
    if lo.data.shape_keys:
        lo.shape_key_clear()
    _drop_metal(lo)                                       # studs are LOD0 detail
    if GARMENTS.get(parse_cloth(ob.name)[0], {}).get("material") == "plate":
        _drop_metal(lo, channel=1, above=0.9)             # rolled beads and rims: decimated, they fold over
    mod = lo.modifiers.new("Decimate", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = LOD_RATIO[lod]
    mod.use_symmetry = True
    mod.symmetry_axis = 'X'
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=lo, active_object=lo, selected_objects=[lo]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for vg in list(lo.vertex_groups):
        lo.vertex_groups.remove(vg)
    for p in lo.data.polygons:
        p.use_smooth = True
    lo["hum_slot"] = ob["hum_slot"]
    hum_lod._place(scene, lo, lod)
    hum_rig.rest(arm)
    for k in (ob.data.shape_keys.key_blocks[1:] if ob.data.shape_keys else []):
        k.value = 0.0
    nk = 0
    if ob.data.shape_keys is not None:                    # per-build garments have no keys to follow
        try:
            nk, _ = hum_hair.bind_keys(lo, ob)
        except RuntimeError:
            for m in list(lo.modifiers):
                lo.modifiers.remove(m)
            nk, _ = hum_hair.bind_keys_nearest(lo, ob)
    gname = parse_cloth(ob.name)[0]
    if GARMENTS.get(gname, {}).get("material") == "plate":
        W = plate_lod_weights(lo, ob, sk)                  # rigid plates: each piece keeps its plate's weights
    else:
        W = hum_rig.transfer_weights(lo, ob, sk)
    hum_rig.skin(lo, arm, sk, W)
    lo.hide_set(True)
    lo.hide_render = True
    return lo, nk


def _islands(me):
    """Connected-component label per vertex."""
    n = len(me.vertices)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return np.array([find(i) for i in range(n)])


def plate_lod_weights(lo, ob, sk):
    """LOD weights for plate armour: every piece of the decimated mesh takes the weights of the LOD0 plate
    most of its vertices are nearest to. Nearest-vertex transfer mixed overlapping lames (a lame got its
    neighbour's bones at the overlap) and the lames crumpled when animated."""
    from mathutils.kdtree import KDTree
    W0 = hum_rig.weights_of(ob, sk)
    lab0 = _islands(ob.data)
    lab1 = _islands(lo.data)
    P0 = np.array([v.co[:] for v in ob.data.vertices])
    P1 = np.array([v.co[:] for v in lo.data.vertices])
    kd = KDTree(len(P0))
    for i, p in enumerate(P0):
        kd.insert(p, i)
    kd.balance()
    near = np.array([kd.find(p)[1] for p in P1])
    W = np.zeros((len(P1), W0.shape[1]))
    for isl in np.unique(lab1):
        m = lab1 == isl
        src, cnt = np.unique(lab0[near[m]], return_counts=True)
        best = src[np.argmax(cnt)]
        W[m] = W0[lab0 == best].mean(0)
    return W


def build_all(scene, body, arm, sk):
    """The body's Region UV (its LODs copy it), then every garment for every body build (LOD0 in HUM_Cloth,
    L1/L2 in HUM_LOD1/2). Long: over MCP run hum_builds.build_wardrobe in chunks (tags=, names=) instead."""
    import hum_builds
    B = BodyFrame(body, arm, sk)
    write_regions(body, B.regions())
    hum_armor.write_cap_coords(bpy.data.objects["Head"])
    return {name: (t, 0) for name, t in hum_builds.build_wardrobe(scene, arm, sk, log=print).items()}


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
