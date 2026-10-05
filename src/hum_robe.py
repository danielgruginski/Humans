"""Robes (Daniel, 2026-10-04: "some robes for the wizard"): a long wool robe and its trim, worn as complete sets over
trousers. The apprentice's, the journeyman's and the magister's robes are one cut in three colourings (ROBE_SETS;
their colours, SET_COLOURS, ship with the sets in the config, so every game shows a tier the same).

Robe      wool. The body: the dress's shell with a round neckline 2.2 cm lower (ROBE_NECK) and long sleeves that
          widen into bells over the wrists (ROBE_BELL more at the cuff). The skirt: the dress's loft (the body's
          convex envelope, flare, folds) from the waist to just above the ground, hanging on the skirt ring (Unity
          HumanSkirt) like the dress. Worn over the set's trousers, which keep the legs covered when a stride parts
          the skirt.
RobeTrim  the second colour (a companion of the Robe, never worn alone; group "Trim"): a binding over the hem, each
          cuff and the neckline, wrapped round the edge, and a sash at the waist knotted in front with two ends
          hanging down the skirt. Built on the Robe of the same build: the robe's own parts are made again here
          (the same recipe, so the bands follow its edges exactly), and every vertex takes the weights of the
          built Robe's nearest vertex - the hem band hangs on the ring with the skirt, the cuffs ride the forearms.
"""
import math

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import hum_cloth as C

ss = C.ss
R_ = C.REGIONS

ROBE_NECK = 0.022                          # neckline: torso skin at least this far from the neck (a shirt's: 0)
ROBE_SLEEVE = 0.92                         # sleeve end on the arm (0 shoulder .. 1 wrist)
ROBE_BELL = 0.045                          # bell sleeves: this much wider at the cuff than a plain sleeve
ROBE_HEM_Z = 0.045                         # the hem just above the ground (the dress's: 0.07)
ROBE_SKIRT_OFF = 0.015                     # out from the legs' envelope: clears the trousers under it
ROBE_SKIRT = dict(flare=0.32, folds=10, fold_amp=0.009, rings=18)
TRIM_LIFT = 0.0045                         # bindings stand this far off the robe
TRIM_WIDTH = dict(hem=0.07, cuff=0.04, neck=0.03)


# ------------------------------------------------------------------ the robe

def _robe_shell(B):
    """Torso from below the waist (tucked under the skirt's top) to the neckline, sleeves to the wrist, widening into
    bells. The open edges are the neckline, the cuffs and the bottom (hidden under the skirt)."""
    nd = B.neck_dist()
    m = ((C._torso_mask(B, B.waist_z - 0.07) & (nd >= ROBE_NECK)) | C._arm_mask(B, ROBE_SLEEVE)).astype(float)

    def off(p, i):
        if B.part[i].startswith("arm"):
            s = B.s[i]
            return 0.011 + 0.006 * s + ROBE_BELL * float(ss(0.5, ROBE_SLEEVE, s)) ** 1.5
        # close to the skin at the neckline (4 mm), 1.1 cm a few centimetres down: from above, a centimetre's gap at
        # the neckline read as a dark ring round the neck
        return 0.004 + 0.007 * float(ss(ROBE_NECK, ROBE_NECK + 0.045, nd[i]))
    V, F = C.shell(B, m, off)
    return _straighten(B, V, F), F


def _face_normal(V, f):
    p = [V[i] for i in f]
    return np.cross(p[1] - p[0], p[2] - p[0])


def _straighten(B, V, F, iters=8):
    """Smooth the open edges along themselves after the decimation (shell() straightens them before it, and the
    collapse leaves them ragged again): the robe's edge zigzagged out past the trim's binding - a dark ring of
    robe between the binding and the neck. Each edge vertex moves toward its two edge neighbours and drags the row
    inside it half way, as shell() does. A move that would fold a face over (turn it against the body's normal under
    it) is not made: unguarded, eight passes folded 11 faces at the neckline, and the binding laid over them along
    their normals sank under the robe in slivers."""
    V = np.array(V, float)
    bn = [B.nearest(V[list(f)].mean(0))[1] for f in F]
    vf = [[] for _ in range(len(V))]
    for k, f in enumerate(F):
        for i in f:
            vf[i].append(k)
    edges = {}
    nb = [set() for _ in range(len(V))]
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
            nb[a].add(b)
            nb[b].add(a)
    bnb = {}
    for (a, b), c in edges.items():
        if c == 1:
            bnb.setdefault(a, []).append(b)
            bnb.setdefault(b, []).append(a)
    edge = [i for i, w in bnb.items() if len(w) == 2]
    inner = [i for i in range(len(V)) if i not in bnb and any(j in bnb for j in nb[i])]
    moved = edge + inner
    near = sorted({k for i in moved for k in vf[i]})
    for _ in range(iters):
        Q = V.copy()
        for i in edge:
            Q[i] = 0.5 * V[i] + 0.25 * (V[bnb[i][0]] + V[bnb[i][1]])
        for i in inner:
            Q[i] = 0.75 * V[i] + 0.25 * V[list(nb[i])].mean(0)
        for _guard in range(4):
            bad = [k for k in near if float(np.dot(_face_normal(Q, F[k]), bn[k])) < 0
                   and float(np.dot(_face_normal(V, F[k]), bn[k])) >= 0]
            if not bad:
                break
            for k in bad:
                for i in F[k]:
                    Q[i] = V[i]
        V = Q
    return V


def _robe_skirt(B):
    return C.loft_skirt(B, B.waist_z - 0.01, ROBE_HEM_Z, ROBE_SKIRT_OFF, segs=48, **ROBE_SKIRT)


def _robe(B):
    """No rim folded into the edges (add_rim): the trim's bindings wrap them and give them their thickness. With
    both, the robe's rim and the binding's wrap hung down from the same edge and the rim showed through in dashes."""
    V, F = _robe_shell(B)
    SV, SF, SU = _robe_skirt(B)
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


# ------------------------------------------------------------------ the trim

def _loops(F):
    """The open boundary loops of a surface, each a list of vertex indices in order."""
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
    nb = {}
    for (a, b), c in edges.items():
        if c == 1:
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
    loops, seen = [], set()
    for s in nb:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [w for w in nb[cur] if w != prev and w not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    return loops


def _orient(V, F, out):
    """Wind the whole strip so its faces point along the outward direction `out` (per vertex): one vote over the faces
    that lie across it. (Per face, the strips wrapping an edge stand edge-on to `out` and flipped at random: with
    smooth shading the binding broke into dark and bright shards.)"""
    vote = 0.0
    for f in F:
        p = [np.asarray(V[i]) for i in f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        ln = float(np.linalg.norm(n))
        if ln < 1e-12:
            continue
        o = np.mean([out[i] for i in f], axis=0)
        c = float(np.dot(n / ln, C.C_unit(o)))
        if abs(c) > 0.5:
            vote += c
    return [tuple(f) if vote >= 0 else tuple(f[::-1]) for f in F]


def _band(P, N, D, width, surface, lift=TRIM_LIFT, wrap=0.007, closed=True):
    """A binding over an open edge: P (m x 3) the edge in order (the garment's own edge vertices), N its outward
    normals, D the directions along the surface into the garment; surface(p) -> (point, normal) on the garment.
    Rows: wrapped round the edge (down along -N, over the robe's folded rim), on the edge, three across `width`
    (a flat 3 cm quad let the shoulder's curve poke through), tucked into the cloth. The wrap goes straight down,
    not out past the edge: pushed out per column, the rows crossed at the neckline's tight corners and the
    binding folded open there. Returns (verts, faces, per-vertex uv)."""
    m = len(P)
    rows = []
    fr = (1 / 3, 2 / 3, 1.0)
    for i in range(m):
        p, n, d = P[i], N[i], D[i]
        r = [p - n * wrap - d * 0.0015, p + n * lift - d * 0.0015]
        for f in fr:
            s2, n2 = surface(p + d * width * f)
            r.append(s2 + n2 * lift)
        s3, n3 = surface(p + d * (width + 0.004))
        r.append(s3 - n3 * 0.0012)
        rows.append(r)
    k = len(rows[0])
    V = np.array([q for r in rows for q in r])
    out = np.repeat(np.asarray(N), k, axis=0)
    F = []
    for i in range(m if closed else m - 1):
        j = (i + 1) % m
        for a in range(k - 1):
            F.append((k * i + a, k * i + a + 1, k * j + a + 1, k * j + a))
    F = _orient(V, F, out)
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(np.asarray(P), axis=0), axis=1))]
    vrow = np.array([-wrap, 0.0] + [width * f for f in fr] + [width + 0.004])
    U = np.array([(arc[i] / C.UV_TILE, vrow[a] / C.UV_TILE) for i in range(m) for a in range(k)])
    return V, F, U


def _smooth_loop(P, iters=10):
    P = np.asarray(P, float)
    for _ in range(iters):
        P = 0.5 * P + 0.25 * (np.roll(P, 1, 0) + np.roll(P, -1, 0))
    return P


def _surface(V, F, B=None):
    """(bvh, f(p) -> (nearest point, normal)) over a surface. The normal is the surface's own vertex normals
    (area-weighted; with B each face first turned to agree with the body's normal under it) blended over the
    nearest face's corners. The nearest face's flat normal, as it was, flipped between neighbours along the robe's
    neckline (an edge vertex took whichever of its faces came first, a folded sliver as often as not), and the
    binding laid along it sank under the robe in slivers. The sums are spread over two rings of neighbours before
    they are normalised: the decimated neckline has edge vertices whose only face is a 2 mm2 sliver standing on
    edge, and their own normals lay along the cloth."""
    V = np.asarray(V, float)
    bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in V], [tuple(f) for f in F])
    VN = np.zeros_like(V)
    E = set()
    for f in F:
        n = _face_normal(V, f)
        if B is not None and float(np.dot(n, B.nearest(V[list(f)].mean(0))[1])) < 0:
            n = -n
        for a, b in zip(f, f[1:] + f[:1]):
            VN[a] += n
            E.add((min(a, b), max(a, b)))
    E = np.array(sorted(E))
    for _ in range(2):
        S = VN.copy()
        np.add.at(S, E[:, 0], VN[E[:, 1]])
        np.add.at(S, E[:, 1], VN[E[:, 0]])
        VN = S
    VN /= np.maximum(np.linalg.norm(VN, axis=1), 1e-12)[:, None]

    def at(p):
        loc, _, fi, _ = bvh.find_nearest(Vector(tuple(map(float, p))))
        loc = np.array(loc)
        f = list(F[fi])
        w = 1.0 / (np.linalg.norm(V[f] - loc, axis=1) + 1e-4)
        return loc, C.C_unit((VN[f] * w[:, None]).sum(0))
    return bvh, at


def _hem_band(SV, rings, width):
    """The binding over the skirt's hem, from the loft's own columns (so it follows every fold)."""
    n = len(SV) // rings
    G = SV.reshape(rings, n, 3)
    k = rings - 1
    P, N, D = [], [], []
    for j in range(n):
        p = G[k, j]
        up = G[k - 1, j] - p
        d = up / np.linalg.norm(up)
        t = G[k, min(j + 1, n - 1)] - G[k, max(j - 1, 0)]
        nn = np.cross(-d, t)
        nn = nn / max(np.linalg.norm(nn), 1e-9)
        P.append(p)
        N.append(nn)
        D.append(d)

    def surface(q):                                       # the column's own surface at q's height
        z = float(q[2])
        col = G[:, int(np.argmin([np.linalg.norm(G[k, jj, :2] - q[:2]) for jj in range(n)]))]
        zs = col[:, 2]
        i = int(np.clip(np.searchsorted(-zs, -z), 1, len(zs) - 1))
        a, b = col[i - 1], col[i]
        t = (z - a[2]) / (b[2] - a[2]) if abs(b[2] - a[2]) > 1e-9 else 0.0
        pt = a + (b - a) * float(np.clip(t, 0.0, 1.0))
        jj = int(np.argmin([np.linalg.norm(G[k, j2, :2] - q[:2]) for j2 in range(n)]))
        return pt, N[jj]
    return _band(np.array(P), N, D, width, surface, closed=False)


def _shell_bands(B, V, F):
    """Bindings over the robe body's neckline and cuffs (not its bottom edge: that lies under the skirt)."""
    loops = [l for l in _loops(F) if len(l) > 8]
    bvh, at = _surface(V, F, B)
    mx = [np.asarray(V)[l].mean(0) for l in loops]
    centre = [i for i, c in enumerate(mx) if abs(c[0]) < 0.12]
    neck = max(centre, key=lambda i: mx[i][2])
    cuffs = sorted(range(len(loops)), key=lambda i: -abs(mx[i][0]))[:2]
    out = []
    for i in [neck] + cuffs:
        # the robe's own edge vertices, as they are (_straighten smoothed them already): smoothing the loop again pulled
        # it down into the cloth over the shoulders, and the robe's edge stood out past the binding there
        P = np.asarray(V, float)[loops[i]]
        N = [at(p)[1] for p in P]
        if i == neck:                                     # away from the neck and down (over the shoulders "down"
            nc = mx[i]                                    # alone lay edge-on to the cloth and the band flipped there)
            hint = lambda p, nc=nc: C.C_unit(np.array([p[0] - nc[0], p[1] - nc[1], 0.0])) + np.array([0.0, 0.0, -0.5])
            width = TRIM_WIDTH["neck"]
        else:
            side = "l" if mx[i][0] > 0 else "r"
            sh = B.j[f"upperarm_{side}"]
            hint = lambda p, sh=sh: C.C_unit(sh - p)
            width = TRIM_WIDTH["cuff"]
        D = []
        m = len(P)
        for k in range(m):
            t = P[(k + 1) % m] - P[k - 1]
            d = C.C_unit(np.cross(N[k], t))
            D.append(d if float(np.dot(d, hint(P[k]))) >= 0 else -d)
        out.append(_band(P, N, D, width, at))
    return out


def _sash(B, SV, SF):
    """A sash round the waist over the seam of body and skirt, knotted in front on the left, two ends hanging down the
    skirt's front. Returns parts."""
    z = B.waist_z - 0.035
    V, F, U = C.ring(B, z, 0.045, 0.026)
    parts = [(V, F, U, "skirt")]
    # the knot: on the sash's front, 5 cm to the character's left
    front = V[np.argmin(V[:, 1] + 10 * np.abs(V[:, 0] - 0.05) + 10 * np.abs(V[:, 2] - z))]
    kc = front + np.array([0.0, -0.014, 0.0])
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    rng = np.random.default_rng(11)
    KV = np.array([v.co[:] for v in bm.verts]) * np.array([0.03, 0.02, 0.024])
    KV = KV * (1 + 0.12 * rng.standard_normal((len(KV), 1)) * 0.5) + kc
    KF = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    KU = np.array([(p[0] / C.UV_TILE, p[2] / C.UV_TILE) for p in KV])
    parts.append((KV, KF, KU, "skirt"))
    # the two ends: strips lying on the skirt's front, 7 mm out
    sbvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in SV], [tuple(f) for f in SF])
    for x, drop, w in ((0.035, 0.30, 0.036), (0.072, 0.24, 0.034)):
        EV, EN = [], []
        steps = 9
        for k in range(steps + 1):
            zz = kc[2] - 0.015 - drop * k / steps
            hit = sbvh.ray_cast(Vector((x + 0.004 * k, -2.0, zz)), Vector((0.0, 1.0, 0.0)))
            if hit[0] is None:
                break
            p, n = np.array(hit[0]), np.array(hit[1])
            if n[1] > 0:
                n = -n
            tx = C.C_unit(np.cross(n, np.array([0.0, 0.0, 1.0])))
            sway = 0.004 * math.sin(k * 1.3)
            EV += [p + n * 0.007 - tx * w / 2 + np.array([sway, 0, 0]), p + n * 0.007 + tx * w / 2 + np.array([sway, 0, 0])]
            EN += [n, n]
        if len(EV) < 4:
            continue
        EV = np.array(EV)
        rows = len(EV) // 2
        EF = [(2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2) for k in range(rows - 1)]
        EF = _orient(EV, EF, EN)
        EU = np.array([((i % 2) * w / C.UV_TILE, -(EV[i][2] - EV[0][2]) / C.UV_TILE) for i in range(len(EV))])
        parts.append((EV, EF, EU, "skirt"))
    return parts


def _robe_weights():
    """f(V, sk) -> each vertex the weights of the built Robe's nearest vertex (this build's)."""
    import bpy
    import hum_builds
    name = C.cloth_name("Robe")
    ob = bpy.data.objects.get(name)
    if ob is None:
        raise RuntimeError(f"{name} is not built: build the Robe before its trim (same build)")
    cache = {}

    def f(V, sk):
        if "kd" not in cache:
            P = hum_builds.build_coords(ob, sk)
            kd = KDTree(len(P))
            for i, p in enumerate(P):
                kd.insert(Vector(tuple(p)), i)
            kd.balance()
            cache["kd"], cache["W"] = kd, C.hum_rig.weights_of(ob, sk)
        idx = [cache["kd"].find(Vector(tuple(map(float, p))))[1] for p in V]
        return cache["W"][idx]
    return f


def _robe_trim(B):
    V, F = _robe_shell(B)
    SV, SF, SU = _robe_skirt(B)
    w = _robe_weights()
    parts = []
    hV, hF, hU = _hem_band(SV, ROBE_SKIRT["rings"], TRIM_WIDTH["hem"])
    parts.append((hV, hF, hU, "skirt", None, w))
    for bV, bF, bU in _shell_bands(B, V, F):
        parts.append((bV, bF, bU, "shell", None, w))
    for (pV, pF, pU, kind) in _sash(B, SV, SF):
        parts.append((pV, pF, pU, kind, None, w))
    return parts


# ------------------------------------------------------------------ garments, sets, colours

ROBE = {
    "Robe": dict(slot="outer", layer=2, material="cloth", build=_robe, smooth_keys=10, group="Robe",
                 companions=["RobeTrim"],
                 excludes=["Dress", "Apron", "Belt", "Jerkin", "Cuirass"],
                 cover=[R_["chest"], R_["belly"], R_["upperarm"], R_["forearm"]],
                 hide=[R_["chest"], R_["belly"], R_["upperarm"], R_["forearm"]]),
    "RobeTrim": dict(slot="trim", layer=3, material="cloth", build=_robe_trim, group="Trim", companion=True,
                     hide=[], cover=[]),
}

# the wizard's robes in the game (MedievalSetting: Old Wren sells the apprentice's, Magister Vane the others)
ROBE_SETS = {
    "Apprentice Robe": ["Trousers", "Robe", "RobeTrim", "Shoes"],
    "Journeyman Robe": ["Trousers", "Robe", "RobeTrim", "Boots"],
    "Magister Robe": ["Trousers", "Robe", "RobeTrim", "Boots"],
}
SET_COLOURS = {                                          # sRGB, per colour group
    "Apprentice Robe": {"Robe": "#6e6150", "Trim": "#4a3e32", "Cloth": "#3b342c", "Leather": "#3b2a1c"},
    "Journeyman Robe": {"Robe": "#2e4c80", "Trim": "#d4c9a6", "Cloth": "#2b2c33", "Boots": "#2b1b10"},
    "Magister Robe": {"Robe": "#47235e", "Trim": "#d4a83a", "Cloth": "#221c27", "Boots": "#1e1712"},
}
NO_RANDOM = set(ROBE_SETS)                               # a wizard's, not a militia look: never on random people
