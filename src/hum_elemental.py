"""The earth elemental (2026-10-23, a card-game unit; Daniel: "Keep moving on the creatures / humanoids"): a Humanoid
made of boulders, so it walks and fights with the humans' clips like the game's fire elemental (a dressed Human).

EarthElemental is a garment like the Skeleton (its own maker, the Orc builds only - the bulkiest - slot `skeleton`,
material `bone` so slot 1 is the glow, colour group Stone): it hides the whole body and the head. Measured off the
build in build space: along every limb bone, chunky faceted rocks sized to the body's thickness there (a little
bulkier), big plates on the chest and back, boulders on the shoulders, a blocky head with a brow; each rock rigid on one
bone (joints part a little when bent, as stacked stones would). Glow (Humans/Glow, the preset's colour): two eye slits
under the brow and a core showing through a crack in the chest.

    hum_builds.build_wardrobe(scene, arm, sk, tags=["MOrc", "FOrc"], names=["EarthElemental"])
"""
import math

import numpy as np

import hum_cloth as C

# colour group "Stone" (sRGB): grey-brown rock (a step lighter than first: #77705f read near-black over dark ground)
STONE = ["#958f84", "#857f76", "#9c917c", "#7a756d", "#8e8672"]
LODS = {0: dict(subdiv=1, jag=0.22, eyes=True), 1: dict(subdiv=0, jag=0.2, eyes=True), 2: dict(subdiv=0, jag=0.15, eyes=False)}
# (bone, child joint or None, rocks along it, bulk: x the measured radius)
LIMBS = [
    ("upperarm", "lowerarm", 2, 1.25), ("lowerarm", "hand", 2, 1.3), ("hand", "middle_02", 1, 1.15),
    ("thigh", "calf", 2, 1.2), ("calf", "foot", 2, 1.25), ("foot", "ball", 1, 1.2), ("ball", None, 1, 1.1),
]


def _ico(subdiv):
    """Unit icosphere (V, faces)."""
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv + 1, radius=1.0)
    V = np.array([v.co[:] for v in bm.verts])
    F = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return V, F


def rock(c, R, radii, rng, lod):
    """A faceted rock: an icosphere as an ellipsoid (radii along R's columns), each vertex pushed in or out by a
    jagged amount, then flattened a little where it was pushed in (cut faces)."""
    L = LODS[lod]
    V, F = _ico(L["subdiv"])
    k = 1.0 + rng.uniform(-L["jag"], L["jag"], len(V))
    k = np.where(k < 1.0, 1.0 - (1.0 - k) * 1.6, k)          # dents deeper than bumps: flat cleaved faces
    V = V * k[:, None] * np.asarray(radii)
    return V @ R.T + c, F


def _frame(u, hint=np.array([0.0, -1.0, 0.0])):
    u = u / np.linalg.norm(u)
    a = hint - u * (hint @ u)
    if np.linalg.norm(a) < 1e-6:
        a = np.array([1.0, 0.0, 0.0]) - u * u[0]
    a /= np.linalg.norm(a)
    return np.stack([a, np.cross(u, a), u], 1)                # columns: across, across, along


def _radius(B, bone, a, b, t0, t1):
    """The body's thickness round the segment a -> b between params t0..t1: the 80th percentile of the skin's distance
    from the axis, over the vertices this bone carries there."""
    i = B.sk.index[bone]
    m = B.W[:, i] > 0.45
    P = B.co_raw[m]
    if not len(P):
        return 0.04
    u = b - a
    L = float(np.linalg.norm(u))
    u /= L
    t = (P - a) @ u / L
    sel = (t >= t0 - 0.05) & (t <= t1 + 0.05)
    Q = P[sel] if sel.sum() >= 4 else P
    tt = (Q - a) @ u
    d = np.linalg.norm(Q - a - tt[:, None] * u, axis=1)
    return float(np.percentile(d, 80))


def pieces(B, lod=0, seed=7):
    """[(V, faces, bone, material slot)] for the current build space."""
    rng = np.random.default_rng(seed + lod)
    j = B.j
    out = []

    def add(c, R, radii, bone, rs=None):
        V, F = rock(c, R, radii, rs or rng, lod)
        out.append((V, F, bone, 0))

    for side in ("l", "r"):
        for bone, child, n, bulk in LIMBS:
            bn = f"{bone}_{side}"
            a = j[bn]
            b = j[f"{child}_{side}"] if child else B.jt[bn]
            if child is None:                                     # the toes: out to the foot's front
                b = a + (B.jt[bn] - a) * 1.6
            u = b - a
            L = float(np.linalg.norm(u))
            R = _frame(u)
            for k in range(n):
                t0, t1 = k / n, (k + 1) / n
                r = _radius(B, bn, a, b, t0, t1) * bulk
                c = a + u * (t0 + t1) / 2 + R[:, 0] * rng.uniform(-0.15, 0.15) * r
                spin = rng.uniform(0, 2 * math.pi)
                Rs = R @ np.array([[math.cos(spin), -math.sin(spin), 0], [math.sin(spin), math.cos(spin), 0], [0, 0, 1]])
                add(c, Rs, (r * rng.uniform(0.95, 1.15), r * rng.uniform(0.85, 1.05), L / n * 0.62 + r * 0.25), bn)
        # the shoulder: a boulder over the joint, on the clavicle (it rides the shrug, not the arm's swing)
        sh = j["upperarm_" + side]
        s = np.sign(sh[0])
        r = _radius(B, "upperarm_" + side, sh, j["lowerarm_" + side], 0.0, 0.3) * 1.55
        add(sh + np.array([s * 0.02, 0.005, 0.035]), _frame(np.array([s * 0.3, 0.0, 1.0])), (r * 1.15, r, r * 0.9),
            "clavicle_" + side)
    # torso: plates front and back per spine bone, over the body's own front and back
    cy = float(np.mean([j[b][1] for b in ("spine_01", "spine_02", "spine_03")]))
    for bone, top, n_side in (("pelvis", "spine_01", 2), ("spine_01", "spine_02", 2), ("spine_02", "spine_03", 2),
                              ("spine_03", "neck_01", 2)):
        a, b = j[bone], j[top]
        zc = float((a[2] + b[2]) / 2)
        h = float(b[2] - a[2])
        P = B.co_raw[(B.part == "torso") & (np.abs(B.co_raw[:, 2] - zc) < max(h * 0.6, 0.03))]
        if not len(P):
            continue
        w = float(np.percentile(np.abs(P[:, 0]), 90))
        front = float(np.percentile(P[:, 1], 6))
        back = float(np.percentile(P[:, 1], 94))
        for sx in ((-1, 1) if n_side == 2 else (0,)):
            for y, depth in ((front, -1.0), (back, 1.0)):
                c = np.array([sx * w * 0.5, y - depth * 0.012, zc])
                R = _frame(np.array([0.0, 0.0, 1.0]), np.array([sx * 0.4, depth, 0.0]))   # columns: out, across, up
                add(c, R, (abs(back - front) * 0.3, w * 0.45, h * 0.62 + 0.03), bone)
        # the waist's sides between them
        for sx in (-1, 1):
            add(np.array([sx * w * 0.85, cy, zc]), _frame(np.array([0.0, 0.0, 1.0])),      # front-back, across, up
                (abs(back - front) * 0.42, w * 0.28, h * 0.55 + 0.02), bone)
    # neck and head
    nk, hd = j["neck_01"], j["head"]
    add((nk + hd) / 2, _frame(hd - nk), (0.055, 0.05, 0.05), "neck_01")
    top = B.jt["head"]
    hc = hd + (top - hd) * 0.45 + np.array([0.0, -0.01, 0.0])
    add(hc, _frame(np.array([0.0, 0.0, 1.0])), (0.105, 0.11, 0.12), "head")
    brow = hc + np.array([0.0, -0.085, 0.03])
    add(brow, _frame(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])), (0.04, 0.035, 0.1), "head")
    jaw = hc + np.array([0.0, -0.06, -0.075])
    add(jaw, _frame(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])), (0.045, 0.05, 0.075), "head")
    if LODS[lod]["eyes"]:
        import hum_skeleton
        for sx in (-1, 1):                                    # glowing slits under the brow
            V, F = hum_skeleton.ball(hc + np.array([sx * 0.042, -0.106, 0.0]), 0.018, 6, 3, scale=(1.4, 0.6, 0.5))
            out.append((V, F, "head", 1))
        # the core: a glow deep in the chest, showing through the gap between the front plates
        z3 = float((j["spine_02"][2] + j["spine_03"][2]) / 2)
        P = B.co_raw[(B.part == "torso") & (np.abs(B.co_raw[:, 2] - z3) < 0.04)]
        fy = float(np.percentile(P[:, 1], 6)) if len(P) else cy - 0.1
        V, F = hum_skeleton.ball(np.array([0.0, fy - 0.03, z3]), 0.04, 8, 5, scale=(0.7, 0.6, 1.3))
        out.append((V, F, "spine_02", 1))
    return out


def make_object(scene, name, parts, arm, sk, lod=0):
    """The Skeleton's mesh writer (rigid weights, ClothData, rest UVs, slots bone + glow), flat-shaded faces."""
    import hum_skeleton
    ob = hum_skeleton.make_object(scene, name, parts, arm, sk, lod)
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def build(scene, B, name, arm, sk, body=None):
    """Cloth_EarthElemental_<tag> and its LODs in the current build space; returns the LOD0 object."""
    import hum_builds
    import hum_rig
    hum_rig.rest(arm)
    out = None
    for lod in (0, 1, 2):
        nm = C.cloth_name(name) + ("" if lod == 0 else f"_L{lod}")
        ob = make_object(scene, nm, pieces(B, lod), arm, sk, lod)
        ob.hide_set(True)
        ob.hide_render = True
        if lod == 0:
            out = ob
        else:
            hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
    return out


ELEMENTAL_WEAR = {
    "EarthElemental": dict(slot="skeleton", layer=0, material="bone", group="Stone", make=build, builds=("Orc",),
                           hide=list(range(16)), cover=[], hides_head=True, hides_face_hair=True, hides_hair=True),
}
