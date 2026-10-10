"""Orc-made gear (2026-10-10, Daniel: "go ahead with the orc armour"): built for every build like any garment
(the Orc builds first of all), worn by the game's orcs as two sets that random humans never roll.

OrcMantle   a fur mantle over the shoulders and the upper back (material "fur": T_Cloth_Fur): thick and lumpy, more
            on the tops of the shoulders, its hem cut into tufts; slot "shoulders" (a mantle or pauldrons)
OrcKilt     hide flaps from a wide studded belt: front, back and two shorter side flaps, ragged hems, the trousers
            showing between them; the flaps hang on the skirt ring like any skirt
Orc plate   PlateStyle "Orc" (hum_plate's machinery): dark iron with cut edges (no rolled rims), big rivets, no
            ridge; OrcCuirass (breast- and backplate and one hoop below them: the kilt hangs where tassets
            would), OrcPauldrons (a crest of spikes, flaring lames), OrcLegs (spiked poleyns and greaves, no
            cuisses), OrcHelm (an open bascinet with horns: the tusks show); colour group OrcIron

Sets: **Orc Hide** (trousers, boots, bracers, the kilt and the mantle: the green chest and arms bare) and **Orc Iron**
(the same kilt and bracers under the iron). Registered at the end of hum_cloth.
"""
import math

import numpy as np

import hum_cloth as C
import hum_armor as A
import hum_plate as PL

ss = C.ss
R = C.REGIONS


# ------------------------------------------------------------------ helpers

def _vertex_normals(V, F):
    N = np.zeros_like(V)
    for f in F:
        a, b, c = V[f[0]], V[f[1]], V[f[2]]
        n = np.cross(b - a, c - a)
        for i in f:
            N[i] += n
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)


def _lumps(P, wave=0.07, seed=3, octaves=3):
    """Smooth 3D noise in -1..1: summed sines in random directions (clumps of fur)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(P))
    norm = 0.0
    for o in range(octaves):
        k = 2 * math.pi / (wave / (2 ** o))
        for _ in range(4):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            out += np.sin(P @ d * k + rng.uniform(0, 2 * math.pi)) / (2 ** o)
            norm += 1.0 / (2 ** o)
    return out / norm * 1.6


def _boundary_loops(F):
    """Ordered boundary loops of a mesh (lists of vertex indices)."""
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges.setdefault(e, []).append((a, b))
    nxt = {}
    for e, ab in edges.items():
        if len(ab) == 1:
            a, b = ab[0]
            nxt[a] = b
    loops, seen = [], set()
    for s in list(nxt):
        if s in seen:
            continue
        loop, v = [], s
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if len(loop) > 2:
            loops.append(loop)
    return loops


# ------------------------------------------------------------------ the fur mantle

def _mantle(B, front_drop=0.13, back_drop=0.25):
    """A thick fur shell over the shoulders and the upper back, lumpy, its hem cut into hanging tufts."""
    co, no = B.co, B.no
    torso = B.part == "torso"
    arms = np.char.startswith(B.part, "arm")
    cy = float(B.j["spine_03"][1])
    back = ss(-0.05, 0.05, co[:, 1] - cy)                 # 0 in front .. 1 at the back (MPFB: +y is the back)
    zline = B.neck_z - front_drop - (back_drop - front_drop) * back
    m = (torso & (co[:, 2] >= zline)) | (arms & (B.s < 0.2))
    m &= B.neck_dist() >= 0.026

    def off(p, i):                                         # thicker on the tops of the shoulders and the back
        return 0.03 + 0.028 * max(0.0, float(no[i][2])) + 0.008 * float(back[i])

    V, F = C.shell(B, m.astype(float), off, smooth=30, edge_smooth=40, decimate=0.8)
    N = _vertex_normals(V, F)
    V = V + N * (0.011 * _lumps(V))[:, None] * ss(0.0, 0.02, np.array([B.nearest(p)[2] for p in V]))[:, None]
    N = _vertex_normals(V, F)
    # the tufts: the outer hem (every loop but the neck's) gets a fringe of points hanging off it
    loops = _boundary_loops(F)
    neck = max(range(len(loops)), key=lambda k: float(V[loops[k], 2].mean())) if len(loops) > 1 else -1
    V = list(map(tuple, V))
    F = list(F)
    rng = np.random.default_rng(11)
    for k, loop in enumerate(loops):
        if k == neck:
            continue
        P = np.array([V[i] for i in loop])
        seg = np.linalg.norm(np.roll(P, -1, 0) - P, axis=1)
        arc = np.r_[0, np.cumsum(seg)[:-1]]
        period = 0.042
        tips = []
        for j, i in enumerate(loop):
            n = N[i]
            d = np.array([0, 0, -1.0]) - n * (-n[2])          # down along the surface
            if np.linalg.norm(d) < 0.3:
                d = P[j] - P.mean(0)
                d -= n * (d @ n)
            d /= max(np.linalg.norm(d), 1e-9)
            x = (arc[j] / period) % 1.0
            tooth = max(0.0, 1.0 - abs(x - 0.5) * 2.6)         # a point every `period`, flat between
            L = 0.006 + (0.032 + 0.018 * rng.random()) * tooth
            tips.append(len(V))
            V.append(tuple(P[j] + d * L - n * 0.004 * tooth))
        n = len(loop)
        for j in range(n):
            a, b = loop[j], loop[(j + 1) % n]
            ta, tb = tips[j], tips[(j + 1) % n]
            F.append((b, a, ta, tb))                           # the loop runs with the shell's own winding
    V = np.array(V)
    V, F = C.add_rim(V, F, 0.014, B)                           # the fur's thickness at its edges
    return [(V, F, None, "shell")]


# ------------------------------------------------------------------ the hide kilt

def _kilt(B):
    """A wide studded belt and four hide flaps hanging from it (front and back to above the knee, the sides
    shorter), each with a ragged hem; the trousers show between them."""
    parts = []
    zb = B.hip_z + 0.025
    V, F, U = C.ring(B, zb, 0.06, 0.03)
    th = np.linspace(-math.pi, math.pi, 20, endpoint=False)
    cyb = float(np.mean(V[:, 1]))
    O = [np.array([0.0, cyb, zb])] * len(th)
    D = [np.array([math.sin(a), -math.cos(a), 0.0]) for a in th]
    P, N = A.cast(V, F, O, D)
    parts.append(A.with_studs(V, F, U, "skirt", P, N))
    knee = float(B.j["calf_l"][2])
    rng = np.random.default_rng(5)
    flaps = ((0.0, 30, knee + 0.06, 0.036), (math.pi, 38, knee + 0.04, 0.036),
             (math.pi / 2, 20, knee + 0.15, 0.040), (-math.pi / 2, 20, knee + 0.15, 0.040))
    for center, span, hem, off in flaps:
        segs, rings = 8, 9
        V, F, U = C.loft_skirt(B, zb - 0.015, hem, off, flare=0.5, folds=2, fold_amp=0.004, rings=rings,
                               segs=segs, front_only=span, center=center)
        V = V.reshape(rings, segs + 1, 3)
        cut = rng.uniform(0.0, 0.035, segs + 1)
        cut[1::2] -= 0.025                                    # every other strip shorter: a cut, tattered hem
        cut = np.maximum(cut, -0.02)
        for r in range(rings):                                # spread down the lower third of the flap
            V[r, :, 2] -= cut * ss(0.6, 1.0, r / (rings - 1))
        V = V.reshape(-1, 3)
        parts.append((V, F, U, "skirt"))
    return parts


# ------------------------------------------------------------------ crude iron

STYLE = PL.STYLES["Orc"] = PL.PlateStyle(
    "Orc", gap=0.012, ridge=0.0, flutes=0, roll=0.0, rivet_r=0.0068, rivet_step=0.042, trim=False, straps=True,
    thickness=0.004, helm="bascinet", horns=0.15, under_torso=("OrcKilt",), under_legs=("Trousers", "OrcKilt"),
    point=0.0, spikes=0.11, pauldron_lames=2, cuisses=False, group="OrcIron", pauldron_flare=0.03)


def _orc_cuirass(B, st):
    """Breast- and backplate and the first hoop below them (PL._cuirass less its lower hoops and tassets)."""
    return PL._cuirass(B, st, coif=None)[:3]


def _away_from(B):
    """Per vertex: the unit direction away from the nearest point of the body (a plate's outer and inner faces
    move together, so its thickness stays)."""
    from mathutils import Vector

    def f(V):
        D = np.array([np.asarray(v) - np.array(B.bvh.find_nearest(Vector(v))[0]) for v in V])
        return D / np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-9)
    return f


def _dent(parts, outward, amp=0.0035, wave=0.055):
    """Hammered, crude iron: every plate pushed in and out a few millimetres by a smooth noise (the rivets ride
    along), so it catches the light unevenly instead of like a smith's polished plate."""
    out = []
    for part in parts:
        V = np.asarray(part[0], float)
        ch = part[4] if len(part) > 4 else None
        detail = np.asarray(ch.get("detail", np.zeros(len(V))), float) if isinstance(ch, dict) else np.zeros(len(V))
        n = _lumps(V, wave, seed=17)
        V = V + outward(V) * (amp * n * (detail < 0.5) + amp * np.mean(n) * (detail >= 0.5))[:, None]
        out.append((V,) + tuple(part[1:]))
    return out


_iron = PL.plate_garments("Orc", "Orc", coif=False)
_build = {k: v["build"] for k, v in _iron.items()}
ORC = {
    # a fur mantle over a breastplate or the jerkin clipped (their top edges came through the fur): not with them
    "OrcMantle": dict(slot="shoulders", layer=5, material="fur", build=_mantle, hide=[], cover=[],
                      excludes=["Cloak", "CloakHood", "Jerkin", "Cuirass", "OrcCuirass", "PlateCuirass", "GothicCuirass",
                                "KnightCuirass", "OrnateCuirass"]),
    "OrcKilt": dict(slot="kilt", layer=3, material="leather", build=_kilt, hide=[], cover=[],
                    excludes=["Belt", "Apron"]),
    # no gorget or coif over the collar: the breastplate's neckline is below the chest region's top, so hiding the
    # chest opened a see-through band under the throat; the plates stand off the skin instead
    "OrcCuirass": dict(_iron["OrcCuirass"], build=lambda B: _dent(_orc_cuirass(B, STYLE), _away_from(B)), hide=[]),
    "OrcPauldrons": dict(_iron["OrcPauldrons"], build=lambda B: _dent(_build["OrcPauldrons"](B), _away_from(B))),
    "OrcLegs": dict(_iron["OrcLegs"], build=lambda B: _dent(_build["OrcLegs"](B), _away_from(B))),
    "OrcHelm": dict(_iron["OrcHelm"], hides_hair=True, build=lambda Hs: _dent(   # no coif: the hair goes under it
        _build["OrcHelm"](Hs), lambda V: (V - np.array([Hs.cx, Hs.cy, Hs.eye_z]))
        / np.maximum(np.linalg.norm(V - np.array([Hs.cx, Hs.cy, Hs.eye_z]), axis=1, keepdims=True), 1e-9))),
}
ORC_SETS = {
    "Orc Hide": ["Trousers", "Boots", "Bracers", "OrcKilt", "OrcMantle"],
    "Orc Iron": ["Trousers", "Boots", "Bracers", "OrcKilt", "OrcCuirass", "OrcPauldrons", "OrcLegs", "OrcHelm"],
}
# colours: hum_faces.FUR and ORC_IRON (groups Fur and OrcIron)
