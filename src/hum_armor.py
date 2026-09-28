"""Leather armour for the humans: same machinery as the villager clothes (hum_cloth), one layer further out.

Jerkin     sleeveless boiled-leather body armour: a stiff torso shell (lower neckline), three overlapping
           bands around waist and hips (each flares over the next), iron studs along the band edges and
           down the front
Pauldrons  two overlapping stiff plates per shoulder (uniform weights: they turn, never bend)
Bracers    thick forearm guards with a row of studs
Greaves    curved shin plates over trousers/boots, stiff on the calf
Cap        round leather cap bound to the head keys like hair; hair above its rim is hidden (CapCut UV)
Coat       full coverage: long sleeves, stand collar, split skirt panels to above the knee
Leggings   waist to ankle, stiff domed knee guards
Gloves     hand shell + flared gauntlet cuff
Hood       the cap + an aventail over ears, neck and nape (hides the hair; beards and brows stay)

Studs are separate little pyramids flagged as metal (ClothData.b = 1): the fabric shader shades them as iron,
and the LODs drop them. Registered into hum_cloth.GARMENTS (layers 3-4, over everything else).
A part may carry a 6th item: {bone: weight}, uniform over the part (stiff plates).
"""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import hum_cloth as C

ss = C.ss
STUD_R, STUD_H = 0.0065, 0.0055


# ------------------------------------------------------------------ helpers

def studs(points, normals, r=STUD_R, h=STUD_H):
    """Round iron studs: low domes (8 sides, two rings and a cap vertex), base sunk 1 mm into the leather.
    Faces wind outward. Returns (verts, faces)."""
    V, F = [], []
    seg = 8
    for p, n in zip(points, normals):
        n = C._unit(np.asarray(n, float))
        t1 = C._unit(np.cross(n, [0, 0, 1.0]) if abs(n[2]) < 0.9 else np.cross(n, [1.0, 0, 0]))
        t2 = np.cross(n, t1)
        base = np.asarray(p) - n * 0.001
        k = len(V)
        for rr, hh in ((1.0, 0.0), (0.72, 0.7)):
            for a in range(seg):
                ang = a * 2 * math.pi / seg
                V.append(base + (t1 * math.cos(ang) + t2 * math.sin(ang)) * r * rr + n * (h + 0.001) * hh)
        V.append(base + n * (h + 0.001))
        tip = k + 2 * seg
        for a in range(seg):
            b = (a + 1) % seg
            F.append((k + a, k + b, k + seg + b, k + seg + a))
            F.append((k + seg + a, k + seg + b, tip))
    return np.array(V).reshape(-1, 3), F


def cast(V, F, origins, dirs):
    """First hits of rays cast from inside a piece outward: (points, outward normals) of the rays that hit."""
    bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in V], [tuple(f) for f in F])
    P, N = [], []
    for o, d in zip(origins, dirs):
        loc, n, i, dist = bvh.ray_cast(Vector(o), Vector(d))
        if loc is not None:
            n = np.array(n)
            if np.dot(n, d) < 0:                     # the stud stands out along the ray, not into the leather
                n = -n
            P.append(np.array(loc))
            N.append(n)
    return P, N


def ring_studs(V, F, a, b, t0, t1, rings, per, stagger=True):
    """Studs in rings around the axis a -> b (t0..t1 along it), `per` per ring, alternate rings offset by
    half a step: rays from the axis outward, so studs land wherever the piece is."""
    axis = C._unit(b - a)
    e1 = C._unit(np.cross(axis, [0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.cross(axis, [1.0, 0, 0]))
    e2 = np.cross(axis, e1)
    O, D = [], []
    for k, t in enumerate(np.linspace(t0, t1, rings)):
        o = a + (b - a) * t
        off = math.pi / per if (stagger and k % 2) else 0.0
        for j in range(per):
            ang = 2 * math.pi * j / per + off
            O.append(o)
            D.append(e1 * math.cos(ang) + e2 * math.sin(ang))
    return cast(V, F, O, D)


def with_studs(V, F, U, kind, P, N):
    """A part plus studs on it (same kind, so they move with it). 5-tuple: the last item flags metal."""
    SV, SF = studs(P, N)
    n = len(V)
    V2 = np.vstack([V, SV]) if len(SV) else V
    F2 = list(F) + [tuple(i + n for i in f) for f in SF]
    metal = np.r_[np.zeros(n), np.ones(len(SV))]
    U2 = None if U is None else np.vstack([U, np.zeros((len(SV), 2))])
    return V2, F2, U2, kind, metal


# ------------------------------------------------------------------ jerkin

JERKIN_OFF = 0.027                    # over a coat (0.016), a tunic (0.011) or a dress bodice (0.006)
BANDS = 3


def _torso_shell(B):
    """Torso from the waist up, cut by clean shapes rather than the ragged torso/arm weight border:
    armholes = a plane just past each shoulder joint, neckline = a cylinder around the neck base. Both
    lie beyond the regions the jerkin covers on inner layers (chest, belly), so no gaps open there."""
    co = B.co
    arms = np.char.startswith(B.part, "arm")
    m = ((B.part == "torso") | arms) & (co[:, 2] >= B.waist_z - 0.03)
    for side in "lr":
        a0 = B.j[f"upperarm_{side}"]
        axis = C._unit(B.j[f"lowerarm_{side}"] - a0)
        sign = 1.0 if a0[0] > 0 else -1.0
        m &= sign * co[:, 0] < abs(a0[0]) + 0.03                        # vertical armhole plane
        m &= ~(arms & ((co - a0) @ axis > 0.03))                      # just a lip onto the arm
    # neckline 2.5 cm off the neck: below the tunic's (1.5 cm) and the shirt's, well inside the 3.5 cm collar band
    m &= B.neck_dist() >= 0.025
    V, F = C.shell(B, m.astype(float), lambda p, i: JERKIN_OFF, smooth=30, edge_smooth=40)
    return C.add_rim(V, F, 0.006, B)


def _bands(B):
    """Overlapping hoops from the waist over the hips; each flares out at its bottom edge over the next."""
    parts = []
    top = B.waist_z + 0.01
    h, lap = 0.065, 0.015
    for k in range(BANDS):
        zt = top - k * (h - lap)
        zb = zt - h
        base = 0.030 - 0.003 * k                         # upper bands sit outside the lower ones
        V, F, U = C.loft_skirt(B, zt, zb, base, flare=0.5, folds=0, fold_amp=0.0, rings=4, segs=48)
        V, F = C.add_rim(V, F, 0.005, B)
        # studs along the lower edge, every other segment
        cx = 0.0
        cy = float(np.mean(V[:, 1]))
        ang = np.linspace(-math.pi, math.pi, 24, endpoint=False) + (math.pi / 24 if k % 2 else 0)
        z = zb + 0.013
        O = [np.array([cx, cy, z])] * len(ang)
        D = [np.array([math.sin(a), -math.cos(a), 0.0]) for a in ang]
        P, N = cast(V, F, O, D)
        parts.append(with_studs(V, F, None, "skirt", P, N))
    return parts


def arc_loft(P, origin, axis, center, span, t0, t1, offset, rings=5, segs=16, flare=0.0):
    """A curved plate around an axis: rings from t0 to t1 (metres along axis), each an arc of +-span
    radians around the `center` direction at the convex support radius of the points P there, + offset,
    widening by `flare` toward t1. Returns (verts, faces, uv)."""
    axis = C._unit(axis)
    e1 = C._unit(center - axis * (center @ axis))
    e2 = np.cross(axis, e1)
    Q = P - origin
    t = Q @ axis
    X = np.stack([Q @ e1, Q @ e2], 1)
    th = np.linspace(-span, span, segs + 1)
    D = np.stack([np.cos(th), np.sin(th)], 1)
    T = np.linspace(t0, t1, rings)
    R = np.zeros((rings, len(th)))
    for k, tk in enumerate(T):
        sel = np.abs(t - tk) < 0.02
        R[k] = (X[sel] @ D.T).max(0) if sel.sum() >= 4 else (R[k - 1] if k else 0.05)
    for _ in range(3):
        R[:, 1:-1] = 0.5 * R[:, 1:-1] + 0.25 * (R[:, :-2] + R[:, 2:])
        R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
    R = R + offset + flare * ((T - t0) / (t1 - t0))[:, None] ** 1.5
    V = np.array([origin + axis * T[k] + (e1 * math.cos(a) + e2 * math.sin(a)) * R[k, j]
                  for k in range(rings) for j, a in enumerate(th)])
    n = len(th)
    F = [(k * n + j, (k + 1) * n + j, (k + 1) * n + j + 1, k * n + j + 1) for k in range(rings - 1) for j in range(n - 1)]
    U = np.array([(th[j] * float(R.mean()) / 0.25, (T[k] - t0) / 0.25) for k in range(rings) for j in range(n)])
    return V, F, U


def _outward(V, F, origin):
    """Flip the winding if the faces point toward `origin` (normals must face out)."""
    f = F[len(F) // 2]
    a, b, c = V[f[0]], V[f[1]], V[f[2]]
    n = np.cross(b - a, c - a)
    return F if n @ (a - origin) > 0 else [tuple(reversed(f)) for f in F]


def _pauldrons(B):
    """Two overlapping curved leather plates over each shoulder (the upper one outside the lower one),
    lofted around the upper arm's outer/top side and flaring toward their lower edges.
    Each plate is weighted uniformly (a stiff plate: it turns with the arm but never bends): the upper one
    shares the collarbone, the lower one rides the upper arm."""
    parts = []
    for side in "lr":
        a0 = B.j[f"upperarm_{side}"]
        a1 = B.j[f"lowerarm_{side}"]
        axis = C._unit(a1 - a0)
        L = float(np.linalg.norm(a1 - a0))
        sign = 1.0 if a0[0] > 0 else -1.0
        up = C._unit(np.array([sign * 0.35, 0.0, 1.0]))
        P = B.co[np.isin(B.part, [f"arm_{side}", "torso"]) & (np.linalg.norm(B.co - a0, axis=1) < 0.25)]
        plates = ((-0.10, 0.20, 0.036, {f"upperarm_{side}": 0.7, f"clavicle_{side}": 0.3}),
                  (0.14, 0.36, 0.030, {f"upperarm_{side}": 1.0}))
        for k, (t0, t1, off, w) in enumerate(plates):
            V, F, U = arc_loft(P, a0, axis, up, math.radians(95), t0 * L, t1 * L, off, flare=0.012)
            F = _outward(V, F, a0 + axis * (t0 + t1) / 2 * L)
            V, F = C.add_rim(V, F, 0.005, B)
            O, D = [], []
            if k == 0:                                     # a row of studs along the upper plate's edge
                e2 = np.cross(axis, up)
                for a in np.linspace(-0.9, 0.9, 5):
                    d = C._unit(up * math.cos(a) + e2 * math.sin(a))
                    O.append(a0 + axis * (t1 - 0.05) * L)
                    D.append(d - axis * (d @ axis))
            P2, N2 = cast(V, F, O, D)
            parts.append(with_studs(V, F, None, "shell", P2, N2) + (w,))
    return parts


def _jerkin(B, studded=True):
    V, F = _torso_shell(B)
    if not studded:
        return [(V, F, None, "shell")] + [p[:4] for p in _bands(B)]
    # studs down the front, two rows beside the lacing line
    zs = np.linspace(B.waist_z + 0.03, B.neck_z - 0.07, 6)
    O, D = [], []
    for x in (-0.018, 0.018):
        for z in zs:
            O.append(np.array([x, float(B.j["spine_03"][1]), z]))
            D.append(np.array([0, -1.0, 0]))
    P, N = cast(V, F, O, D)
    return [with_studs(V, F, None, "shell", P, N)] + _bands(B)


# ------------------------------------------------------------------ bracers, greaves

def _bracers(B):
    parts = []
    for side in "lr":
        arm = B.part == f"arm_{side}"
        m = arm & (B.s >= 0.6) & (B.s < 0.9)
        off = lambda p, i: 0.024 + 0.004 * ss(0.75, 0.9, B.s[i])
        V, F = C.shell(B, m.astype(float), off, smooth=24, edge_smooth=30, decimate=0.5)
        V, F = C.add_rim(V, F, 0.005, B)
        a = B.j[f"lowerarm_{side}"]
        b = B.j[f"hand_{side}"]
        axis = C._unit(b - a)
        up = C._unit(np.array([0, 0, 1.0]) - axis * axis[2])
        L = float(np.linalg.norm(b - a))
        O = [a + axis * t * L for t in np.linspace(0.3, 0.8, 4)]
        P, N = cast(V, F, O, [up] * len(O))
        parts.append(with_studs(V, F, None, "shell", P, N))
    return parts


def _greaves(B):
    """Boiled-leather shin guards: a curved plate over the front of each shin, outside boot shafts, with a
    small flared knee lip and a stud row down the middle. Stiff: all on the calf bone."""
    parts = []
    for side in "lr":
        k0 = B.j[f"calf_{side}"]
        a = B.j[f"foot_{side}"]
        axis = C._unit(a - k0)
        L = float(np.linalg.norm(a - k0))
        P = B.co[(B.part == f"leg_{side}") & (B.s > 0.4)]
        fwd = np.array([0, -1.0, 0])
        V, F, U = arc_loft(P, k0, axis, fwd, math.radians(80), 0.08 * L, 0.80 * L, 0.031, rings=9, segs=14,
                           flare=0.006)
        # knee lip: the top ring leans out
        n = 15
        e = C._unit(fwd - axis * (fwd @ axis))
        V[:n] += e * 0.006 - axis * 0.004
        F = _outward(V, F, k0 + axis * 0.45 * L)
        V, F = C.add_rim(V, F, 0.005, B)
        O = [k0 + axis * t * L for t in np.linspace(0.2, 0.7, 5)]
        P2, N2 = cast(V, F, O, [e] * len(O))
        parts.append(with_studs(V, F, None, "shell", P2, N2) + ({f"calf_{side}": 1.0},))
    return parts


# ------------------------------------------------------------------ head: leather cap

CAP_CUT = 0.001          # hair above the cap rim is hidden under the cap (0 would mean "no cap")
# rim height over the eyes by angle around the head (front 0 deg): f = c0 + c1 cos + c2 cos2
# front 3.8 cm (just over the brows), sides 2.8 cm (over the ears), nape 2 cm below eye height
RIM_C = (0.0185, 0.029, -0.0095)


class HeadShellFrame:
    """The head (ears as domes, no eyes) in the shape hum_cloth.shell expects, plus the cap rim:
    rim(P) = height above a rim line that runs over the brows, over the ears and down to the nape."""

    def __init__(self, head):
        import bmesh
        import hum_hair
        H = hum_hair.HeadFrame(head)
        self.H = H
        self.co = np.array(H.proxy)
        self.faces = list(H.faces)
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in self.co]
        for f in self.faces:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
        bm.normal_update()
        self.no = np.array([v.normal[:] for v in vs])
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()
        upper = self.co[self.co[:, 2] > H.eye_z]
        self.y_front = float(upper[:, 1].min())
        self.y_back = float(upper[:, 1].max())
        self.eye_z = H.eye_z
        self.cx = float(np.mean(upper[:, 0]))
        self.cy = float(np.mean(upper[:, 1]))

    def rim_z(self, P):
        P = np.atleast_2d(P)
        th = np.arctan2(P[:, 0] - self.cx, -(P[:, 1] - self.cy))
        c0, c1, c2 = RIM_C
        return self.eye_z + c0 + c1 * np.cos(th) + c2 * np.cos(2 * th)

    def rim(self, P):
        P = np.atleast_2d(P)
        return P[:, 2] - self.rim_z(P)

    def nearest(self, p):
        loc, n, i, d = self.bvh.find_nearest(Vector(p))
        return np.array(loc), np.array(n), d


def _cap_band(Hs, rows=((-0.020, 0.014), (-0.014, 0.019), (0.002, 0.019), (0.008, 0.014)), segs=48):
    """The raised band around the rim: rings cast from inside the head onto its surface at rim + t,
    pushed out by the offset (a rounded profile). A loft, not a smoothed strip: smoothing a strip this
    narrow pulls its two edges together."""
    ang = np.linspace(-math.pi, math.pi, segs, endpoint=False)
    V = []
    for t, off in rows:
        for a in ang:
            d = np.array([math.sin(a), -math.cos(a), 0.0])
            o = np.array([Hs.cx, Hs.cy, 0.0])
            o[2] = float(Hs.rim_z(o + d * 0.08)[0]) + t
            loc, n, i, dist = Hs.bvh.ray_cast(Vector(o), Vector(d))
            loc, n = (np.array(loc), np.array(n)) if loc is not None else (o + d * 0.08, d)
            n = C._unit(n - np.array([0, 0, n[2] * 0.5]))              # keep the band upright
            V.append(loc + n * off)
    F = [(k * segs + j, k * segs + (j + 1) % segs, (k + 1) * segs + (j + 1) % segs, (k + 1) * segs + j)
         for k in range(len(rows) - 1) for j in range(segs)]
    V = np.array(V)
    F = _outward(V, F, np.array([Hs.cx, Hs.cy, float(V[:, 2].mean())]))
    return V, F


def _cap(Hs):
    """A round boiled-leather cap: a dome down to the rim, a raised band around the rim with studs, and a
    crest strip front to back."""
    c = Hs.rim(Hs.co)
    parts = []
    # the cap reaches 1.5 cm below the rim: hair rooted just under the rim disappears under its edge
    V, F = C.shell(Hs, (c > -0.015).astype(float), lambda p, i: 0.013, smooth=40, edge_smooth=6, decimate=0.5)
    V, F = C.add_rim(V, F, 0.004, Hs)
    parts.append((V, F, None, "shell"))
    V, F = _cap_band(Hs)
    ang = np.linspace(-math.pi, math.pi, 18, endpoint=False)
    O, D = [], []
    for a in ang:
        d = np.array([math.sin(a), -math.cos(a), 0.0])
        o = np.array([Hs.cx, Hs.cy, 0.0])
        o[2] = float(Hs.rim_z(o + d * 0.08)[0]) - 0.0045                # the band's middle
        O.append(o)
        D.append(d)
    P, N = cast(V, F, O, D)
    parts.append(with_studs(V, F, None, "shell", P, N))
    crest = (c > 0.0) & (np.abs(Hs.co[:, 0] - Hs.cx) < 0.011)
    V, F = C.shell(Hs, crest.astype(float), lambda p, i: 0.019, smooth=20, edge_smooth=40, decimate=0.6)
    V, F = C.add_rim(V, F, 0.004, Hs)
    parts.append((V, F, None, "shell"))
    return parts


def _sphere_uv(Hs, V):
    a = np.arctan2(V[:, 0] - Hs.cx, -(V[:, 1] - Hs.cy))
    return np.stack([a * 0.1 / 0.25, V[:, 2] / 0.25], 1)


def build_headgear(scene, name, arm, sk):
    """Like hum_cloth.build_garment, for things worn on the head: bound to the head's keys (like hair),
    rigid on the head bone."""
    import bpy
    import hum_hair
    import hum_rig
    rec = C.GARMENTS[name]
    head = bpy.data.objects["Head"]
    hum_rig.rest(arm)
    for k in head.data.shape_keys.key_blocks[1:]:
        k.value = 0.0
    Hs = HeadShellFrame(head)
    parts = rec["build"](Hs)
    verts, faces, uvs, metals, fades, polishes, mats, orns, pats = [], [], [], [], [], [], [], [], []
    off = 0
    for part in parts:
        V, F, U, kind = part[:4]
        metal, polish, mat = C.part_channels(part, len(V))
        metals.append(metal)
        polishes.append(polish)
        mats.append(mat)
        orns.append(C.part_orn(part, len(V)))
        pats.append(C.part_orn_pat(part, len(V)))
        extra = part[5] if len(part) > 5 else None
        fades.append(extra[1] if isinstance(extra, tuple) and extra[0] == "neckfade" else np.zeros(len(V)))
        uvs += C.loop_uvs(F, U if U is not None else _sphere_uv(Hs, V))
        verts.append(V)
        faces += [tuple(i + off for i in f) for f in F]
        off += len(V)
    V = np.vstack(verts)
    me = bpy.data.meshes.new(C.cloth_name(name))
    me.from_pydata(V.tolist(), [], faces)
    me.update()
    lay = me.uv_layers.new(name="UVMap")
    lay.data.foreach_set("uv", np.array(uvs, np.float32).ravel())
    for p in me.polygons:
        p.use_smooth = True
    ao = C.vertex_ao(V, faces, Hs.bvh)
    data = C.cloth_data(rec["material"], ao, C.edge_factor(V, faces), np.concatenate(metals),
                        np.concatenate(polishes), np.concatenate(mats))
    att = me.color_attributes.new("ClothData", 'FLOAT_COLOR', 'POINT')
    att.data.foreach_set("color", data.astype(np.float32).ravel())
    ob = hum_hair.replace_object(scene, C.cloth_name(name), me)
    col = bpy.data.collections.get(C.CLOTH_COL) or bpy.data.collections.new(C.CLOTH_COL)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    for cc in list(ob.users_collection):
        cc.objects.unlink(ob)
    col.objects.link(ob)
    ob["hum_slot"] = rec["slot"]
    ob["hum_hide"] = 0.0
    C.write_regions(ob, np.zeros(len(V), int))
    C.write_rest_uv(ob.data, V)
    if rec["material"] == "plate":
        C.write_ornament_uv(ob.data, np.concatenate(orns), np.concatenate(pats))
    ob.data.materials.append(C.garment_material(rec["material"]))
    nk, _ = hum_hair.bind_keys(ob, head)
    if C.BUILD is not None:                               # the build's shape is in the geometry already:
        import hum_builds                                 # keep only the face keys
        for kb in list(ob.data.shape_keys.key_blocks[1:]):
            if kb.name in hum_builds.BODY_KEYS:
                ob.shape_key_remove(kb)
    hum_hair.smooth_keys_spatial(ob, 0.03)               # parts below the head bind to its neck edge
    # above the jaw: the head (its keys, rigid on the head bone); below it (throat, collar, cape): the body
    # under it - its key offsets and bone weights - so the cape rides the shoulders and chest
    # in front the handover is under the chin; at the back it starts at the base of the skull, so the nape
    # of the hood moves with the neck under it when the head nods
    z_chin = float(Hs.H.F.chin[2])
    z_skull = float(Hs.co[:, 2].min()) + 0.05
    back = np.clip((V[:, 1] - Hs.cy) / 0.06, 0, 1)
    z_top = z_chin * (1 - back) + z_skull * back
    g = C.ss(z_top - 0.005, z_top - 0.05, V[:, 2])
    if (g > 0).any() and C.BUILD is None:
        Wb, Db, names = _body_follow(bpy.data.objects["Body"], sk, V[g > 0])
        _blend_keys(ob, g, Db, names)
    # bones: every point moves like the skin under it (head or body), smoothed over the mesh - the crown
    # with the head, the nape with the neck, the cape with the shoulders
    W = _skin_weights_under(V, faces, sk)
    hum_rig.skin(ob, arm, sk, W)
    return ob, nk


def _skin_weights_under(V, faces, sk, smooth=4):
    import hum_rig
    from mathutils.bvhtree import BVHTree
    co, fs, Ws = [], [], []
    off = 0
    for name in ("Head", "Body"):
        o = bpy.data.objects[name]
        me = o.data
        kb = me.shape_keys.key_blocks[0] if me.shape_keys else None
        c = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in me.vertices])
        co.append(c)
        fs += [tuple(i + off for i in p.vertices) for p in me.polygons]
        Ws.append(hum_rig.weights_of(o, sk))
        off += len(c)
    co = np.vstack(co)
    Wall = np.vstack(Ws)
    bvh = BVHTree.FromPolygons([tuple(v) for v in co], fs)
    W = np.zeros((len(V), len(sk.bones)))
    for i, p in enumerate(V):
        loc, n, fi, d = bvh.find_nearest(Vector(p))
        ids = list(fs[fi])
        w = 1.0 / (np.linalg.norm(co[ids] - np.array(loc), axis=1) + 1e-6)
        W[i] = (Wall[ids] * (w / w.sum())[:, None]).sum(0)
    E = np.array([(f[k], f[(k + 1) % len(f)]) for f in faces for k in range(len(f))])
    E = np.vstack([E, E[:, ::-1]])
    deg = np.bincount(E[:, 0], minlength=len(V)).astype(float)[:, None]
    for _ in range(smooth):
        avg = np.zeros_like(W)
        np.add.at(avg, E[:, 0], W[E[:, 1]])
        W = 0.5 * W + 0.5 * avg / np.maximum(deg, 1)
    W[W < 0.01] = 0.0
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def _body_follow(body, sk, P):
    """For points near the body: the body's bone weights and key offsets there (inverse-distance over the
    nearest face's corners). Returns (W [n, bones], D [keys, n, 3], key names)."""
    import hum_rig
    from mathutils.bvhtree import BVHTree
    me = body.data
    kbs = me.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kbs[0].data])
    faces = [tuple(p.vertices) for p in me.polygons]
    bvh = BVHTree.FromPolygons([tuple(v) for v in base], faces)
    Wb = hum_rig.weights_of(body, sk)
    keys = [k for k in kbs[1:]]
    Dk = np.stack([np.array([d.co[:] for d in k.data]) - base for k in keys])      # keys, verts, 3
    W = np.zeros((len(P), Wb.shape[1]))
    D = np.zeros((len(keys), len(P), 3))
    for i, p in enumerate(P):
        loc, n, fi, dist = bvh.find_nearest(Vector(p))
        ids = list(faces[fi])
        w = 1.0 / (np.linalg.norm(base[ids] - np.array(loc), axis=1) + 1e-6)
        w /= w.sum()
        W[i] = (Wb[ids] * w[:, None]).sum(0)
        D[:, i] = (Dk[:, ids] * w[None, :, None]).sum(1)
    return W, D, [k.name for k in keys]


def _blend_keys(ob, g, D, names):
    """Mix the body's key offsets into ob's keys by g (0 keep the head's .. 1 the body's)."""
    me = ob.data
    if not me.shape_keys:
        ob.shape_key_add(name="Basis", from_mix=False)
    kbs = me.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kbs[0].data])
    idx = np.where(g > 0)[0]
    for k, name in enumerate(names):
        kb = kbs.get(name) or ob.shape_key_add(name=name, from_mix=False)
        co = np.array([d.co[:] for d in kb.data])
        off = co - base
        off[idx] = off[idx] * (1 - g[idx, None]) + D[k] * g[idx, None]
        kb.data.foreach_set("co", (base + off).astype(np.float32).ravel())


def _ombre_coord(me, co, vi):
    """Per vertex: 0 at the top of the hairstyle .. 1 at its lowest ends, by height. A dyed ombre follows how
    the hair hangs; measured along each clump instead, a short clump near the crown turned fully
    tip-coloured and clumps from crown and nape disagreed at the same height (pale flakes among dark roots)."""
    z = co[:, 2]
    top = float(np.percentile(z, 97))
    bot = float(np.percentile(z, 2))
    return np.clip((top - z) / max(top - bot, 0.02), 0.0, 1.0)


def write_cap_coords(head):
    """Every hair/beard/brow piece gets a "CapCut" UV:
    x = height above the cap rim (the hair shader hides what's above _CapCut while a cap is worn, 0 = none)
    y = ombre coordinate: 0 at the top of the style .. 1 at its lowest ends (by height)"""
    import bpy
    Hs = HeadShellFrame(head)
    n = 0
    for cname in ("HUM_Hair", "HUM_LOD1", "HUM_LOD2"):
        col = bpy.data.collections.get(cname)
        for ob in (col.objects if col else []):
            if ob.type != 'MESH' or not ob.name.startswith(("Hair_", "Beard_", "Brows_")):
                continue
            me = ob.data
            kb = me.shape_keys.key_blocks[0] if me.shape_keys else None
            co = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in me.vertices])
            c = Hs.rim(co)
            vi = np.empty(len(me.loops), np.int64)
            me.loops.foreach_get("vertex_index", vi)
            om = _ombre_coord(me, co, vi)
            lay = me.uv_layers.get("CapCut") or me.uv_layers.new(name="CapCut")
            uv = np.zeros((len(me.loops), 2), np.float32)
            uv[:, 0] = c[vi]
            uv[:, 1] = om[vi]
            lay.data.foreach_set("uv", uv.ravel())
            # HoodCut (x > 0: hidden under the cloak's hood); brows are never hidden
            import hum_cloak
            h = hum_cloak.hood_cut(Hs, co, beard=ob.name.startswith("Beard_"))
            if ob.name.startswith("Brows_"):
                h = np.full(len(co), -1.0)
            lay2 = me.uv_layers.get("HoodCut") or me.uv_layers.new(name="HoodCut")
            uv2 = np.zeros((len(me.loops), 2), np.float32)
            uv2[:, 0] = h[vi]
            lay2.data.foreach_set("uv", uv2.ravel())
            me.uv_layers.active = me.uv_layers["UVMap"] if "UVMap" in me.uv_layers else me.uv_layers[0]
            n += 1
    return n



# ------------------------------------------------------------------ full coverage: coat, leggings, gloves, hood

COAT_OFF = 0.016


def _coat(B, studded=False, off0=None, skirt_off=0.021, hem_drop=0.24, flare=0.28, collar=True, closure=True,
          sleeve_s=0.93, skirt=True, hem_z=None):
    """Long-sleeved leather coat: torso and sleeves to the wrist, a stand collar open at the throat, and a
    skirt of two panels (front and back, split at the hips for walking) to above the knee. Studded closure."""
    co = B.co
    arms = np.char.startswith(B.part, "arm")
    zh0 = B.hip_z - 0.03 if hem_z is None else hem_z
    m = ((B.part == "torso") & (co[:, 2] >= zh0) & (B.neck_dist() >= 0.004)) | (arms & (B.s < sleeve_s))
    base = COAT_OFF if off0 is None else off0
    off = lambda p, i: base + (0.006 * B.s[i] if B.part[i].startswith("arm") else 0.0)
    V, F = C.shell(B, m.astype(float), off, smooth=30, edge_smooth=30)
    V, F = C.add_rim(V, F, 0.005, B)
    zs = np.linspace(B.hip_z + 0.02, B.neck_z - 0.03, 8)
    O = [np.array([0.0, float(B.j["spine_03"][1]), z]) for z in zs]
    P, N = cast(V, F, O, [np.array([0, -1.0, 0])] * len(O))
    if not closure:
        P, N = [], []
    if studded:                                           # rivets all over: torso rings + sleeves
        cy = float(B.j["spine_02"][1])
        Pt, Nt = ring_studs(V, F, np.array([0, cy, B.hip_z + 0.03]), np.array([0, cy, B.neck_z - 0.05]),
                            0.0, 1.0, 7, 14)
        P, N = list(P) + Pt, list(N) + Nt
        for side in "lr":
            Ps, Ns = ring_studs(V, F, B.j[f"upperarm_{side}"], B.j[f"hand_{side}"], 0.18, 0.85, 7, 7)
            P, N = P + Ps, N + Ns
    parts = [with_studs(V, F, None, "shell", P, N)]
    zt, zh = B.hip_z + 0.02, B.crotch_z - hem_drop
    for center in ((0.0, math.pi) if skirt else ()):
        SV, SF, _ = C.loft_skirt(B, zt, zh, skirt_off, flare=flare, folds=0, fold_amp=0.0, rings=10, segs=20,
                                 front_only=74, center=center)
        SV, SF = C.add_rim(SV, SF, 0.005, B)
        cy = float(np.mean(SV[:, 1]))
        O, D = [], []
        for a in np.linspace(-1.1, 1.1, 7) + center:
            O.append(np.array([0.0, cy, zh + 0.02]))
            D.append(np.array([math.sin(a), -math.cos(a), 0.0]))
        P, N = cast(SV, SF, O, D) if closure else ([], [])
        if studded:
            Pk, Nk = ring_studs(SV, SF, np.array([0, cy, zt]), np.array([0, cy, zh]), 0.15, 0.6, 3, 16)
            P, N = list(P) + Pk, list(N) + Nk
        parts.append(with_studs(SV, SF, None, "skirt", P, N))
    if not collar:
        return parts
    # stand collar around the back and sides of the neck, open in front (beards hang there)
    nb = B.j["neck_01"]
    Pn = co[B.part == "neck"]
    CV, CF, _ = arc_loft(Pn, nb - np.array([0, 0, 0.012]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0]),
                         math.radians(140), 0.0, 0.045, 0.013, rings=4, segs=22, flare=0.01)
    CF = _outward(CV, CF, nb + np.array([0, 0, 0.02]))
    CV, CF = C.add_rim(CV, CF, 0.004, B)
    parts.append((CV, CF, None, "shell", np.zeros(len(CV)), {"neck_01": 0.5, "spine_03": 0.5}))
    return parts


def _leggings(B, studded=False, extra=0.003, knees=True):
    """Leather leggings from the waist to the ankle (the trousers' fit, 3 mm further out, so boots and
    greaves built around trousers still fit over them), with stiff domed knee guards."""
    m = (C._torso_mask(B, -1, B.waist_z + 0.005) | C._leg_mask(B, -1, 0.97)).astype(float)
    V, F = C.shell(B, m, lambda p, i: C.trouser_offset(B, i) + extra)
    V, F = C.add_rim(V, F, 0.003, B)
    if not knees:
        return [(V, F, None, "shell")]
    if studded:
        P, N = [], []
        for side in "lr":
            Ps, Ns = ring_studs(V, F, B.j[f"thigh_{side}"], B.j[f"calf_{side}"], 0.15, 0.8, 5, 8)
            P, N = P + Ps, N + Ns
        parts = [with_studs(V, F, None, "shell", P, N)]
    else:
        parts = [(V, F, None, "shell")]
    for side in "lr":
        hip, knee, ank = B.j[f"thigh_{side}"], B.j[f"calf_{side}"], B.j[f"foot_{side}"]
        axis = C._unit(ank - hip)
        P = B.co[(B.part == f"leg_{side}") & (np.abs(B.s - 0.5) < 0.2)]
        fwd = np.array([0, -1.0, 0])
        KV, KF, _ = arc_loft(P, knee, axis, fwd, math.radians(75), -0.065, 0.06, 0.024, rings=6, segs=12)
        e = C._unit(fwd - axis * (fwd @ axis))
        for k in range(6):                                  # dome it: the middle rows stand out
            KV[k * 13:(k + 1) * 13] += e * 0.008 * math.sin(math.pi * k / 5)
        KF = _outward(KV, KF, knee)
        KV, KF = C.add_rim(KV, KF, 0.004, B)
        P2, N2 = cast(KV, KF, [knee], [e])
        parts.append(with_studs(KV, KF, None, "shell", P2, N2) +
                     ({f"thigh_{side}": 0.5, f"calf_{side}": 0.5},))
    return parts


def _gloves(B):
    """Leather gloves (a thin shell over hand and fingers) with a flared gauntlet cuff over the sleeve."""
    parts = []
    for side in "lr":
        hand = (B.part == f"hand_{side}") | ((B.part == f"arm_{side}") & (B.s >= 0.9))
        V, F = C.shell(B, hand.astype(float), lambda p, i: 0.0035, smooth=6, edge_smooth=10, decimate=0.25)
        V, F = C.add_rim(V, F, 0.003, B)
        parts.append((V, F, None, "shell"))
        a, b = B.j[f"hand_{side}"], B.j[f"lowerarm_{side}"]
        axis = C._unit(b - a)                               # wrist -> elbow: the cuff flares up the arm
        P = B.co[(B.part == f"arm_{side}") & (B.s > 0.7)]
        CV, CF, _ = arc_loft(P, a, axis, np.array([0, 0, 1.0]), math.pi, -0.015, 0.085, 0.031, rings=4, segs=24,
                             flare=0.012)
        CF = _outward(CV, CF, a + axis * 0.035)
        CV, CF = C.add_rim(CV, CF, 0.004, B)
        parts.append((CV, CF, None, "shell"))
    return parts


def _aventail(Hs, span=math.radians(118), segs=30, rows=10, flare=0.03):
    """Leather neck guard hanging from under the cap band around the sides and back of the head down over
    the collar and the top of the shoulders. Each row is the convex support of the head (ears as domes) and
    the body's neck/trapezius at that height - a smooth bell, nothing pokes through - flaring toward the
    bottom, with a ridge every third row. Returns (V, F, fade): fade 0 at the top .. 1 at the bottom."""
    import bpy
    body = bpy.data.objects["Body"]
    kb = body.data.shape_keys.key_blocks[0] if body.data.shape_keys else None
    Bc = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in body.data.vertices])
    zb = float(Hs.co[:, 2].min()) - 0.035
    Pall = np.vstack([Hs.co, Bc[(Bc[:, 2] > zb - 0.03) & (Bc[:, 2] < Hs.eye_z)]])
    near = np.hypot(Pall[:, 0] - Hs.cx, Pall[:, 1] - Hs.cy) < 0.14
    Pall = Pall[near]
    ang = math.pi + np.linspace(-span, span, segs + 1)
    D = np.stack([np.sin(ang), -np.cos(ang)], 1)
    Z = np.zeros((segs + 1, rows))
    R = np.zeros((segs + 1, rows))
    Cy = np.zeros(rows)
    zt = np.array([float(Hs.rim_z(np.array([Hs.cx, Hs.cy, 0.0]) + np.r_[d, 0] * 0.08)[0]) - 0.006 for d in D])
    for k in range(rows):
        f = k / (rows - 1)
        Z[:, k] = zt * (1 - f) + zb * f
    z_mid = Z.mean(0)
    for k in range(rows):
        sl = np.abs(Pall[:, 2] - z_mid[k]) < 0.015
        pts = Pall[sl] if sl.sum() > 10 else Pall[np.argsort(np.abs(Pall[:, 2] - z_mid[k]))[:40]]
        Cy[k] = float(pts[:, 1].mean())
    for k in range(rows):
        for j in range(segs + 1):
            sl = np.abs(Pall[:, 2] - Z[j, k]) < 0.015
            pts = Pall[sl] if sl.sum() > 10 else Pall[np.argsort(np.abs(Pall[:, 2] - Z[j, k]))[:40]]
            Q = pts[:, :2] - np.array([Hs.cx, Cy[k]])
            R[j, k] = float((Q @ D[j]).max())
    for k in range(1, rows):                                # never narrower going down
        R[:, k] = np.maximum(R[:, k], R[:, k - 1] - 0.004)
    for _ in range(6):
        R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
        R[:, 1:-1] = 0.5 * R[:, 1:-1] + 0.25 * (R[:, :-2] + R[:, 2:])
    V, fade = [], []
    for j in range(segs + 1):
        for k in range(rows):
            f = k / (rows - 1)
            off = 0.012 + 0.008 * f + flare * f ** 1.5 + (0.003 if k % 3 == 2 else 0.0)
            r = R[j, k] + off
            V.append(np.array([Hs.cx + D[j, 0] * r, Cy[k] + D[j, 1] * r, Z[j, k]]))
            fade.append(f)
    F = [(j * rows + k, j * rows + k + 1, (j + 1) * rows + k + 1, (j + 1) * rows + k)
         for j in range(segs) for k in range(rows - 1)]
    V = np.array(V)
    F = _outward(V, F, np.array([Hs.cx, float(Cy.mean()), float(V[:, 2].mean())]))
    return V, F, np.array(fade)


def _hood(Hs):
    """The cap plus an aventail: head, ears and neck covered, the face open."""
    parts = _cap(Hs)
    V, F, fade = _aventail(Hs)
    V2, F2 = C.add_rim(V, F, 0.004, Hs)
    fade = np.r_[fade, np.ones(len(V2) - len(V))]
    parts.append((V2, F2, None, "shell", np.zeros(len(V2)), ("neckfade", fade)))
    return parts

R = C.REGIONS
ARMOR = {
    "Jerkin": dict(slot="armor", layer=3, material="leather", build=_jerkin, skirt_follow=0.9, skirt_shell=1.0,
                   smooth_keys=10,
                   hide=[R["chest"], R["belly"]], excludes=["Belt", "Apron"],
                   cover=[]),       # 2.2 cm out, stiff: inner layers stay whole (clipping them frays the neckline)
    "Pauldrons": dict(slot="shoulders", layer=4, material="leather", build=_pauldrons, hide=[], cover=[]),
    "Bracers": dict(slot="bracers", layer=3, material="leather", build=_bracers, hide=[], cover=[]),
    "Greaves": dict(slot="shins", layer=4, material="leather", build=_greaves, hide=[], cover=[]),
    "Cap": dict(slot="head", layer=4, material="leather", build=_cap, headgear=True, capcut=CAP_CUT,
                hide=[], cover=[]),
    # full coverage: coat + leggings + gloves + boots + hood cover everything but the face; they replace
    # the villager clothes (slots / excludes)
    "Coat": dict(slot="outer", layer=2, material="leather", build=_coat, skirt_follow=0.9, skirt_shell=1.0,
                 smooth_keys=10, excludes=["Shirt", "Dress", "Apron", "Belt"], cover=[],
                 hide=[R["chest"], R["belly"], R["pelvis"], R["upperarm"], R["forearm"], R["wrist"], R["collar"],
                       R["thigh_up"]]),
    "Leggings": dict(slot="legs", layer=1, material="leather", build=_leggings, cover=[],
                     hide=[R["pelvis"], R["thigh_up"], R["thigh_low"], R["shin_up"], R["shin_low"]]),
    "Gloves": dict(slot="hands", layer=3, material="leather", build=_gloves, cover=[],
                   hide=[R["hand"], R["wrist"]]),
    "Hood": dict(slot="head", layer=4, material="leather", build=_hood, headgear=True, hides_hair=True,
                 capcut=CAP_CUT, hide=[R["neck"], R["collar"]], cover=[]),
}
ARMOR["Cuirass"] = dict(ARMOR["Jerkin"], build=lambda B: _jerkin(B, studded=False))
ARMOR["StuddedCoat"] = dict(ARMOR["Coat"], build=lambda B: _coat(B, studded=True))
ARMOR["StuddedLeggings"] = dict(ARMOR["Leggings"], build=lambda B: _leggings(B, studded=True))

# padded (gambeson) and mail: quilted cloth under riveted rings
import hum_cloak as _K                                   # noqa: E402

ARMOR["Gambeson"] = dict(ARMOR["Coat"], material="quilt",
                         build=lambda B: _coat(B, off0=0.02, skirt_off=0.025, hem_drop=0.22, closure=False,
                                               collar=False))
ARMOR["PaddedLeggings"] = dict(ARMOR["Leggings"], material="quilt",
                               build=lambda B: _leggings(B, extra=0.004, knees=False))
ARMOR["Hauberk"] = dict(ARMOR["Jerkin"], material="mail", excludes=["Belt", "Apron"], smooth_keys=10,
                        hide=[R["chest"], R["belly"], R["pelvis"], R["upperarm"], R["forearm"]],
                        cover=[R["chest"], R["belly"], R["upperarm"]],       # the gambeson under the mail
                        build=lambda B: _coat(B, off0=0.036, skirt_off=0.047, hem_drop=0.30, flare=0.36,
                                              collar=False, closure=False, sleeve_s=0.9))
ARMOR["MailChausses"] = dict(ARMOR["Leggings"], material="mail",
                             build=lambda B: _leggings(B, extra=0.008, knees=False))
ARMOR["PaddedCoif"] = dict(slot="head", layer=4, material="quilt", headgear=True, hoodcut=True, cover=[],
                           hide=[R["neck"], R["collar"]],
                           build=lambda Hs: _K._cloak_hood(Hs, peak=False, off=0.017, drop=0.06, flare=0.008,
                                                           over=("Gambeson",)))
ARMOR["MailCoif"] = dict(slot="head", layer=4, material="mail", headgear=True, hoodcut=True, cover=[],
                         hide=[R["neck"], R["collar"]],
                         build=lambda Hs: _K._cloak_hood(Hs, peak=False, off=0.022, drop=0.07, flare=0.014,
                                                         over=("Gambeson", "Hauberk")))

# armour is worn as a complete set: it replaces the clothes and covers everything but the face
ARMOR_SETS = {
    "Padded": ["PaddedLeggings", "Gambeson", "Gloves", "Boots", "PaddedCoif"],
    "Mail": ["MailChausses", "Gambeson", "Hauberk", "Gloves", "Boots", "MailCoif"],
    "Leather": ["Leggings", "Coat", "Cuirass", "Gloves", "Boots", "Hood"],
    "Studded Leather": ["StuddedLeggings", "StuddedCoat", "Jerkin", "Pauldrons", "Bracers", "Greaves", "Gloves",
                        "Boots", "Hood"],
}
