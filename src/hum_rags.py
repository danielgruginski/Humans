"""Rags (Daniel, 2026-10-12: "another clothing option for humans - rags. This will also be used to improve the zombie
clothing"): clothes worn to tatters, cut ragged in the geometry rather than only painted torn.

RagShirt     a loose shirt (1 cm off the body, the plain shirt's 4 mm; standing out to 2.6 cm at the hips, so it hangs
             over the trousers rather than tucked in) whose hem is torn into uneven teeth (some hang up to 10 cm lower
             than the cut between them), each sleeve torn off at its own length (the left at the elbow, the right high
             on the upper arm) and the neckline torn wider. Hides the chest and the belly.
RagTunic     longer: the shirt's torso without sleeves (torn-out armholes), and a skirt from the hips to above the
             knee cut into strips of uneven length with slits between them, hanging on the skirt ring (HumanSkirt) so
             they sway. Hides the chest and the belly only: the slits show what is under them.
RagTrousers  torn off at mid-calf, the left leg shorter than the right, both hems jagged.

Every rag is torn on the living too: its recipe's `rag` goes into ClothData's alpha (1 - rag), and the cloth shader
(Humans/Cloth, hum_material._tatter) tears at least that much with a coarser hole field (fewer, bigger rips than the
undead's speckles); a zombie's or a skeleton's own torn amount adds on top, and holes show the skin as before.
The cuts are fixed shapes (seeded), the same on every build, so a rag is one cut in every size. Each garment is first
built whole to its longest tooth (hum_cloth.shell, which smooths and decimates its border), then cut: every face whose
body point (the nearest body vertex: its part, height, angle round the body or the limb, limb param) lies past the
torn edge goes, and the new border is eased a little along itself (stair steps soften, teeth stay).
"""
import math

import numpy as np

import hum_cloth as C

R_ = C.REGIONS

RAG = 0.32                                  # how torn a rag is on the living (the undead's tatter runs 0.35-0.9)
SHIRT_OFF = 0.010                           # loose: 1 cm off the torso (the plain shirt: 4 mm)
SHIRT_HANG = 0.016                          # and this much more by the hem: over the trousers (their 10.5 mm), not in
SHIRT_HEM = 0.0                             # the hem's cut sits this far above the plain shirt's (hip_z - 0.05)
HEM_TEETH = 11                              # teeth round the hem
HEM_DEPTH = 0.10                            # the longest tooth hangs this far below the cut
SLEEVE = dict(l=0.50, r=0.20)               # where each sleeve is torn off (0 shoulder .. 0.5 elbow .. 1 wrist)
SLEEVE_TEETH, SLEEVE_DEPTH = 5, 0.14        # teeth round a sleeve's end (limb units: 0.1 is about 5 cm)
NECK = 0.022                                # the neckline torn this far further from the neck, plus teeth
NECK_TEETH, NECK_DEPTH = 7, 0.02
LEG = dict(l=0.66, r=0.80)                  # where each trouser leg is torn off (0.5 knee .. 1 ankle)
LEG_TEETH, LEG_DEPTH = 5, 0.17
DECIMATE = 0.65                             # the rags keep more of the body's faces than a plain shell (0.4): the cut
                                            # follows faces, and big ones swallowed the teeth
TUNIC_STRIPS = 13                           # strips round the tunic's skirt
TUNIC_SLIT = 0.45                           # the slits run up this share of the skirt from its hem


def teeth(phi, n, depth, seed):
    """A torn edge round a loop: n teeth of random width (0.4-1.6 of the even share), depth (0.35-1 of `depth`) and
    lean, each with a small notch of its own, as a function of the angle phi (radians). 0 at the cut between teeth,
    up to depth at a tooth's tip."""
    rng = np.random.default_rng(seed)
    amp = rng.uniform(0.35, 1.0, n)
    apex = rng.uniform(0.25, 0.75, n)
    w = rng.uniform(0.4, 1.6, n)
    edges = np.r_[0.0, np.cumsum(w) / w.sum()]                  # the teeth's bounds round the loop (0..1)
    notch_at = rng.uniform(0.15, 0.85, n)
    notch = rng.uniform(0.0, 0.35, n)
    u = (np.asarray(phi) / (2 * math.pi) + rng.uniform(0, 1)) % 1.0
    k = np.clip(np.searchsorted(edges, u, side="right") - 1, 0, n - 1)
    f = (u - edges[k]) / (edges[k + 1] - edges[k])
    tri = np.where(f < apex[k], f / apex[k], (1 - f) / (1 - apex[k]))
    tri = tri * (1 - notch[k] * np.maximum(0, 1 - np.abs(f - notch_at[k]) / 0.12))   # a nick torn into the tooth
    return depth * amp[k] * tri


def _torso_angle(B, P):
    """angle round the body's long axis: 0 at the front (-y), growing toward +x"""
    return np.arctan2(P[:, 0], -P[:, 1])


def _limb_angle(B, P, side, kind):
    """angle round a limb's upper bone (shoulder -> elbow, hip -> knee)"""
    a, b = (B.j[f"upperarm_{side}"], B.j[f"lowerarm_{side}"]) if kind == "arm" else (B.j[f"thigh_{side}"], B.j[f"calf_{side}"])
    ax = C._unit(b - a)
    e1 = C._unit(np.cross(ax, [0.0, 0.0, 1.0]) if abs(ax[2]) < 0.9 else np.cross(ax, [1.0, 0.0, 0.0]))
    e2 = np.cross(ax, e1)
    Q = P - a
    return np.arctan2(Q @ e2, Q @ e1)


def _torso_keep(B, idx, hem_z, seed, neck=True):
    """kept torso points (body vertex indices): above the toothed hem, and away from the torn-wide neckline"""
    co = B.co[idx]
    th = _torso_angle(B, co)
    k = co[:, 2] >= hem_z - teeth(th, HEM_TEETH, HEM_DEPTH, seed)
    if neck:
        k &= B.neck_dist()[idx] >= NECK + teeth(th, NECK_TEETH, NECK_DEPTH, seed + 1)
    return k


def _limb_keep(B, idx, kind, ends, n, depth, seed):
    """kept limb points: each arm (or leg) down to its own torn end"""
    keep = np.ones(len(idx), bool)
    for i, side in enumerate("lr"):
        on = np.isin(B.part[idx], [f"{kind}_{side}", f"{'hand' if kind == 'arm' else 'foot'}_{side}"])
        if not on.any():
            continue
        phi = _limb_angle(B, B.co[idx[on]], side, kind)
        keep[on] = B.s[idx[on]] < ends[side] + teeth(phi, n, depth, seed + 10 * i) - depth * 0.5
    return keep


def rag_cut(B, V, F, keep_of, ease=3):
    """cut a built shell: every face whose corners' body points (nearest body vertices) are not all kept goes, the
    loose vertices too; the new border is eased `ease` times along itself (each border vertex toward its two border
    neighbours' middle, halfway) so the stair steps of the face-by-face cut soften while the teeth stay"""
    from mathutils import Vector
    from mathutils.kdtree import KDTree
    if not hasattr(B, "_kd"):
        B._kd = KDTree(len(B.co))
        for i, c in enumerate(B.co):
            B._kd.insert(Vector(c), i)
        B._kd.balance()
    V = np.asarray(V, float)
    near = np.array([B._kd.find(Vector(p))[1] for p in V])
    kv = keep_of(near)
    F = [f for f in F if kv[list(f)].mean() > 0.5]
    used = sorted({i for f in F for i in f})
    remap = {v: t for t, v in enumerate(used)}
    V = V[used]
    F = [tuple(remap[i] for i in f) for f in F]
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
    bnb = {}
    for (a, b), c in edges.items():
        if c == 1:
            bnb.setdefault(a, []).append(b)
            bnb.setdefault(b, []).append(a)
    ring = [i for i, nb in bnb.items() if len(nb) == 2]
    for _ in range(ease):
        Q = V.copy()
        for i in ring:
            Q[i] = 0.5 * V[i] + 0.25 * (V[bnb[i][0]] + V[bnb[i][1]])
        V = Q
    return V, F


def _shirt_keep(B, seed_t, seed_a):
    def keep(idx):
        torso = B.part[idx] == "torso"
        k = np.ones(len(idx), bool)
        k[torso] = _torso_keep(B, idx[torso], -1.0, seed_t)      # the neckline only: the hem is the skirt's
        return k & _limb_keep(B, idx, "arm", SLEEVE, SLEEVE_TEETH, SLEEVE_DEPTH, seed_a)
    return keep


def _tear_hem(V, UV, rings, n, share, from_ring=0):
    """a lofted skirt's hem torn: vertex column j is drawn up along itself to the share share[j] of its length (its
    rings spaced evenly over what is left; positions and UVs follow the column), so the hem runs along the torn line
    in pointed teeth rather than in steps of whole faces. Rings above from_ring stay where they are (the tunic's
    strips move only below their slits' tops)"""
    P = np.asarray(V, float).reshape(rings, n, 3).copy()
    T = np.asarray(UV, float).reshape(rings, n, 2).copy()
    src = np.arange(rings, dtype=float)
    low = from_ring / max(rings - 1, 1) + 0.05
    for j in range(n):
        end = (rings - 1) * float(np.clip(share[j], low, 1.0))
        t = src.copy()
        t[from_ring:] = from_ring + (src[from_ring:] - from_ring) / max(rings - 1 - from_ring, 1) * (end - from_ring)
        for c in range(3):
            P[:, j, c] = np.interp(t, src, P[:, j, c])
        for c in range(2):
            T[:, j, c] = np.interp(t, src, T[:, j, c])
    return P.reshape(-1, 3), T.reshape(-1, 2)


def _rag_shirt(B):
    """the torso down to the hips (loose), the torn sleeves and neckline cut from it; below the hips a short skirt
    over the trousers (a shirt's tail hangs, it does not follow the body into the crotch), its hem torn into teeth"""
    top = B.hip_z + 0.02
    m = (C._torso_mask(B, top - 0.05) & (B.neck_dist() >= NECK * 0.5)) | C._arm_mask(B, max(SLEEVE.values()) + SLEEVE_DEPTH)

    def off(p, i):
        if B.part[i].startswith("arm"):
            return SHIRT_OFF + 0.006 * B.s[i]
        return SHIRT_OFF + SHIRT_HANG * C.ss(B.waist_z + 0.04, top - 0.03, B.co[i][2])  # loose by the hips: over the trousers
    V, F = C.shell(B, m.astype(float), off, decimate=DECIMATE)
    V, F = rag_cut(B, V, F, _shirt_keep(B, 41, 43))
    V, F = C.add_rim(V, F, 0.003, B)
    rings, segs = 9, 56
    hem = B.hip_z - 0.05 + SHIRT_HEM - HEM_DEPTH                # down to the longest tooth
    SV, SF, SU = C.loft_skirt(B, top, hem, 0.016, flare=0.05, folds=6, fold_amp=0.004, rings=rings, segs=segs)
    th = np.linspace(-math.pi, math.pi, segs + 1)                # the vertex columns' angles (loft_skirt's)
    span = top - hem
    share = 1.0 - (HEM_DEPTH - teeth(th, HEM_TEETH, HEM_DEPTH, 41)) / span
    SV, SU = _tear_hem(SV, SU, rings, segs + 1, share)
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


def _rag_trousers(B):
    m = C._torso_mask(B, -1, B.waist_z + 0.005) | C._leg_mask(B, -1, max(LEG.values()) + LEG_DEPTH)
    V, F = C.shell(B, m.astype(float), lambda p, i: C.trouser_offset(B, i) + 0.003, decimate=DECIMATE)
    V, F = rag_cut(B, V, F, lambda idx: _limb_keep(B, idx, "leg", LEG, LEG_TEETH, LEG_DEPTH, 47))
    V, F = C.add_rim(V, F, 0.003, B)
    return [(V, F, None, "shell")]


def _strip_skirt(V, F, UV, rings, n, seed):
    """cut a lofted skirt (rings x n columns, faces in ring order) into strips: a slit (one column of faces left
    out) runs up between neighbouring strips over the lower TUNIC_SLIT, and each strip is torn off at its own length,
    its end slanting (its columns drawn up along themselves, _tear_hem)"""
    rng = np.random.default_rng(seed)
    cols = n - 1
    bounds = np.sort(rng.choice(np.arange(2, cols - 1), TUNIC_STRIPS - 1, replace=False))
    strip = np.searchsorted(bounds, np.arange(cols), side="right")
    length = rng.uniform(0.6, 1.0, TUNIC_STRIPS)               # share of the skirt each strip keeps
    slant = rng.uniform(-0.18, 0.18, TUNIC_STRIPS)             # its end torn at a slant
    starts = np.r_[0, bounds]
    ends = np.r_[bounds, cols]
    share = np.ones(n)
    for j in range(n):                                          # vertex columns: a slit's two edges both belong
        si = min(np.searchsorted(bounds, j, side="left"), TUNIC_STRIPS - 1)   # a slit's left edge: the left strip
        u = (j - starts[si]) / max(ends[si] - starts[si], 1)
        share[j] = np.clip(length[si] + slant[si] * (u - 0.5), 0.35, 1.0)
    slit_from = int(round((rings - 1) * (1 - TUNIC_SLIT)))
    V, UV = _tear_hem(V, UV, rings, n, share, from_ring=slit_from)
    keep = []
    for fi, f in enumerate(F):
        k, j = divmod(fi, cols)                                  # loft_skirt lists faces ring by ring
        if k >= slit_from and j in bounds:                       # the slit between two strips
            continue
        keep.append(f)
    used = sorted({i for f in keep for i in f})
    remap = {v: t for t, v in enumerate(used)}
    return V[used], [tuple(remap[i] for i in f) for f in keep], UV[used]


def _rag_tunic(B):
    # the torso as the plain tunic's, down under the skirt's top (no torn hem of its own: the skirt's strips are it);
    # 4 cm below the hips: the shell's eased border rises ~2 cm, and at hip_z - 0.01 it ended just above the skirt's
    # top, a ring of the shirt and trousers showing between them
    m = C._torso_mask(B, B.hip_z - 0.04) & (B.neck_dist() >= NECK * 0.5)
    V, F = C.shell(B, m.astype(float), lambda p, i: SHIRT_OFF + 0.002)
    V, F = rag_cut(B, V, F, lambda idx: _torso_keep(B, idx, -1.0, 51))      # the torn-wide neckline
    V, F = C.add_rim(V, F, 0.004, B)
    rings, segs = 14, 52
    SV, SF, SU = C.loft_skirt(B, B.hip_z + 0.01, B.crotch_z - 0.2, 0.02, flare=0.2, folds=7, fold_amp=0.006,
                              rings=rings, segs=segs)
    SV, SF, SU = _strip_skirt(SV, SF, SU, rings, segs + 1, 53)
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


RAGS = {
    "RagShirt": dict(slot="top", layer=1, material="cloth", build=_rag_shirt, smooth_keys=10, rag=RAG,
                     skirt_follow=0.9, skirt_shell=1.0,
                     hide=[R_["chest"], R_["belly"]]),
    "RagTunic": dict(slot="outer", layer=2, material="cloth", build=_rag_tunic, skirt_follow=0.9, smooth_keys=10,
                     rag=RAG, excludes=["Dress", "Robe"],
                     cover=[R_["chest"], R_["belly"]],
                     hide=[R_["chest"], R_["belly"]]),
    "RagTrousers": dict(slot="legs", layer=1, material="cloth", build=_rag_trousers, rag=RAG,
                        hide=[R_["pelvis"], R_["thigh_up"], R_["thigh_low"]]),
}
