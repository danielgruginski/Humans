"""Strand-card hair (the hair spike, 2026-10-29): cards with a strand texture in place of solid clumps.

Daniel wasn't happy with the solid clumps (they read as ribbed tubes / carved wood: lumpy outline, blunt ends, no
highlight band) and asked for a new hair system with a different material and hair that moves like the cloth does.

The style recipes stay (hum_styles.HAIR: flow, length, lift, stiffness...): their clump spines become the cards'
guides. A style is the old cap shell (no skin between the cards) plus layers of cards along spines grown from
blue-noise roots:
  inner  wide cards, dense strands (atlas columns 0-2), lying on the cap
  outer  narrower cards a little farther out, strands gathered into locks (columns 3-5)
  wisps  a few thin cards with loose strands (columns 6-7): the soft outline

The strand atlas T_Hair_Cards (1024 x 1024, linear): 8 columns of 128 px, v = root (0) -> tip (1)
  R  shade: per strand brightness, darker for strands deeper in the card and toward the root
  G  strand id (0..1): per strand colour jitter, highlight shift
  B  unused (0.5)
  A  coverage (the shader cuts at 0.5; Unity keeps the coverage over the mips)

Per loop data, the same UVs as the clumps plus one (the Unity shader is Humans/HairCards):
  UVMap   atlas UVs (cards); the old tiling strand UVs (cap)
  Clump   x = coherent id per card, y = root -> tip
  CapCut / HoodCut  written by hum_armor.write_cap_coords, as for every hair piece
  Guide   x = the card row's particle (the strand sim's point; -1 on the cap), y = root -> tip (on the cap: how
          far its border dissolves, cap_guides)
HairData colour: R = 0 (cards need no edge darkening), G = layer (0 inner, 0.5 outer, 1 wisps).
"""
import math
import os

import bpy
import numpy as np

import hum_hair
import hum_paint
import hum_styles
from hum_hair import Part, _unit, cap_part, sample_roots

ss = hum_paint.smoothstep
ATLAS = "T_Hair_Cards"
COLS = 8
STYLES = {"LongStrands": "Long", "LongThinStrands": "Long", "PonytailStrands": "Ponytail",   # spike pieces -> the
          "CropStrands": "Crop", "SweptStrands": "Swept", "BunStrands": "Bun",                   # recipe they grow from
          "SidePartStrands": "SidePart", "CurlyStrands": "Curly", "MohawkStrands": "Mohawk"}

# draped styles (hum_drape: hung under gravity, not grown along the recipe's flow; the recipe gives the cap and mask).
# Daniel 2026-10-29: Long's mesh was bad too, and "one with thick hair and another with thin hair":
#   volume   head clearance (m) near the part .. at the sides: how full the hair stands over the head
#   spacing  the inner layer's roots; layers: (roots spacing x, extra volume, card width x, atlas columns)
#   width    a card's width (m); clump: how far strands gather into locks toward the tips, lock: a lock's size
#   hem      the cut below the shoulder joints (m): front locks (over the chest), the back (shoulder blades; the
#            middle of the back `hem_u` lower: a U)
#   fringe   fine short hair over the front hairline (_fringe): cards a side, length (m), card width (m)
#   layers   (roots spacing x, extra volume, card width x, atlas columns); the first, under the rest (negative
#            volume), is the fill: few wide dense cards, not gathered into locks, so a gap between the cards above
#            shows hair, not skin (thin hair showed slivers of neck and ear between them, more so swinging)
FILL = (2.2, -0.002, 2.0, (0, 1, 2))
DRAPED = {
    "LongStrands": dict(volume=(0.006, 0.016), spacing=0.015, width=0.032, clump=0.35, lock=0.03, ragged=0.03,
                        fringe=(12, 0.05, 0.012),
                        hem=(-0.12, -0.17), hem_u=0.04, layers=[FILL, (1.0, 0.0, 1.0, (0, 1, 2)),
                                                                (1.4, 0.005, 0.85, (3, 4, 5)), (3.2, 0.009, 0.6, (6, 7))]),
    # thin: flatter and less dense, not stringy (clumped 0.6 on the locks' columns it read as wet strings over skin)
    # (cards 2.4 cm wide let the ear's skin show between them over the ear: 3 cm)
    "LongThinStrands": dict(volume=(0.0025, 0.006), spacing=0.019, width=0.03, clump=0.25, lock=0.022, ragged=0.04,
                            fringe=(10, 0.05, 0.011),
                            hem=(-0.12, -0.17), hem_u=0.04, layers=[FILL, (1.0, 0.0, 1.0, (0, 1, 2)),
                                                                    (1.8, 0.003, 0.8, (3, 4, 5)), (3.4, 0.005, 0.6, (6, 7))]),
    # a men's side parting (2026-10-30, the next style): Long's drape with the parting `part_x` off the middle and short:
    # no hem, each root's own length by where it grows (`length` as SHORT's - top, front, sides, back, nape - and
    # `ragged` a fraction of it, as there): the top falls over the ears to the lobes, the back to the collar
    "SidePartStrands": dict(volume=(0.004, 0.009), spacing=0.014, width=0.026, clump=0.25, lock=0.022, ragged=0.2,
                            length=(0.12, 0.10, 0.075, 0.085, 0.045), part_x=0.028, fringe=(8, 0.04, 0.011),
                            cap_light=0.4,
                            layers=[FILL, (1.0, 0.0, 1.0, (0, 1, 2)), (1.4, 0.003, 0.85, (3, 4, 5)),
                                    (3.2, 0.005, 0.6, (6, 7))]),
}


# ------------------------------------------------------------------ the strand atlas

def _column(kind, seed, h=1024, w=128, ss_k=2):
    """One column of the atlas at ss_k x supersampling: RGBA float (h, w, 4), row 0 = v 0 (the root)."""
    rng = np.random.default_rng(seed)
    H2, W2 = h * ss_k, w * ss_k
    v = (np.arange(H2) + 0.5) / H2
    x = np.arange(W2) + 0.5
    n, wid, wave, lens, clumps = {
        "base": (90, (2.2, 3.6), 0.012, (0.72, 1.0), 0),
        "mid": (60, (2.0, 3.2), 0.018, (0.70, 1.0), 4),
        "wisp": (22, (1.6, 2.6), 0.035, (0.50, 0.97), 0),
    }[kind]
    # strands start a little apart (their own stream: the rest of the column unchanged): a card's root is no hard edge
    # (along the hairline the card roots drew a line across the brow)
    stagger = {"base": 0.035, "mid": 0.045, "wisp": 0.06}[kind]
    rng_start = np.random.default_rng(seed + 1000)
    shade = np.zeros((H2, W2))
    sid = np.full((H2, W2), 0.5)
    cov = np.zeros((H2, W2))
    margin = W2 * 0.06
    centres = rng.uniform(margin * 2, W2 - margin * 2, clumps) if clumps else None
    order = rng.permutation(n)                     # drawn back to front: the first ones are the deepest
    for k, si in enumerate(order):
        depth = k / max(n - 1, 1)                  # 0 deepest .. 1 frontmost
        # roots spread over the card, thinning toward its edges (no hard card edge)
        x0 = margin + (W2 - 2 * margin) * (0.5 + 0.5 * np.sign(rng.random() - 0.5) * rng.random() ** 1.6)
        L = rng.uniform(*lens)
        a1, a2 = rng.uniform(0.3, 1.0) * wave * W2, rng.uniform(0.2, 0.6) * wave * W2
        f1, f2 = rng.uniform(1.0, 2.5), rng.uniform(3.0, 6.0)
        p1, p2 = rng.uniform(0, 6.28, 2)
        cx = x0 + a1 * np.sin(2 * np.pi * f1 * v + p1) * v + a2 * np.sin(2 * np.pi * f2 * v + p2) * v ** 2
        if clumps:                                 # strands gathered into locks toward the tip
            c = centres[np.argmin(np.abs(centres - x0))]
            cx = cx + (c - x0) * ss(0.15, 0.9, v) * rng.uniform(0.35, 0.75)
        drift = rng.normal(0, 0.03) * W2           # a slight lean, so strands cross
        cx = cx + drift * v
        hw = rng.uniform(*wid) * 0.5 * ss_k * 0.5 * (1.0 - 0.75 * ss(L - 0.22, L, v))
        a = np.clip(hw[:, None] + 0.5 - np.abs(x[None, :] - cx[:, None]), 0.0, 1.0)
        a *= (v <= L)[:, None] * (1.0 - ss(L - 0.04, L, v))[:, None]
        v0 = rng_start.random() ** 2 * stagger
        a *= ss(v0, v0 + 0.012, v)[:, None]
        bright = rng.uniform(0.62, 1.0) * (0.55 + 0.45 * depth) * (0.75 + 0.25 * ss(0.0, 0.35, v))
        shade = shade * (1 - a) + bright[:, None] * a if np.ndim(bright) else shade * (1 - a) + bright * a
        sid = sid * (1 - a) + rng.random() * a
        cov = cov + a * (1 - cov)
    M = np.stack([shade, sid, np.full_like(shade, 0.5), cov], -1)
    M = M.reshape(h, ss_k, w, ss_k, 4).mean((1, 3))
    # shade was laid over black (premultiplied): divide by the coverage; the id is already a straight value. Empty
    # pixels take their neighbours' values (no dark fringe in the mips)
    a = M[..., 3:4]
    rgb = M[..., :3].copy()
    rgb[..., 0] = np.where(a[..., 0] > 1e-4, M[..., 0] / np.maximum(a[..., 0], 1e-4), 0.0)
    filled = a[..., 0] > 0.02
    for _ in range(24):
        if filled.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(filled.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            f = np.roll(filled, (dy, dx), (0, 1))
            acc += np.roll(rgb, (dy, dx), (0, 1)) * f[..., None]
            cnt += f
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    rgb[~filled] = (0.7, 0.5, 0.5)
    rgb[..., 2] = 0.5
    return np.concatenate([rgb, a], -1)


def build_atlas(size=1024, seed=7):
    kinds = ["base", "base", "base", "mid", "mid", "mid", "wisp", "wisp"]
    w = size // COLS
    cols = [_column(k, seed * 31 + i, h=size, w=w) for i, k in enumerate(kinds)]
    M = np.concatenate(cols, 1)
    return hum_paint.save_image(ATLAS, M, os.path.join(hum_paint.TEX_DIR, ATLAS + ".png"))


def atlas_preview(path=None):
    """The atlas on grey for looking at: coverage over a mid grey, shade as brightness."""
    img = bpy.data.images[ATLAS]
    w, h = img.size
    M = np.array(img.pixels[:]).reshape(h, w, 4)
    g = np.full((h, w), 0.35)
    c = g * (1 - M[..., 3]) + M[..., 0] * 0.9 * M[..., 3]
    P = np.stack([c, c, c, np.ones_like(c)], -1)
    path = path or os.path.join(hum_paint.ROOT, "renders", "hair_cards_atlas.png")
    return hum_paint.save_image("_atlas_preview", P, path, colorspace='sRGB')


# ------------------------------------------------------------------ cards

def _bent_length(S, bend):
    """Per point of S: arc length (m) and that plus `bend` m per radian the strand turns (rows spread by the second
    crowd into the bends)."""
    d = np.diff(S, axis=0)
    seg = np.linalg.norm(d, axis=1)
    arc = np.r_[0, np.cumsum(seg)]
    if bend <= 0 or len(S) < 3:
        return arc, arc
    u = d / np.maximum(seg[:, None], 1e-9)
    turn = np.arccos(np.clip((u[1:] * u[:-1]).sum(1), -1.0, 1.0))
    turn *= np.minimum(seg[1:], seg[:-1]) > 0.003              # a stub's direction is noise, not a bend
    m = seg.copy()
    m[:-1] += bend * turn * 0.5
    m[1:] += bend * turn * 0.5
    return arc, np.r_[0, np.cumsum(m)]


def _resample(S, rows, bend=0.0):
    """`rows` points along S, evenly by arc length (or by bent length: closer in the bends). Returns the points, the
    length and each row's fraction of the arc length (the atlas v)."""
    arc, m = _bent_length(S, bend)
    L = max(arc[-1], 1e-6)
    at = np.interp(np.linspace(0, m[-1], rows), m, arc)
    return np.stack([np.interp(at, arc, S[:, c]) for c in range(3)], 1), L, at / L


def cards_part(H, spines, widths, ids, cols, layer, guide0=0, row_len=0.018, curve=0.14, root_sink=0.002,
               normal_fns=None, bend=0.0, max_rows=24, dip_len=0.0, v0=0.0, min_rows=4, spread=0.35):
    """A card along each spine: 3 vertices a row (edges dipped toward the head, so a card is a shallow trough
    over the hair under it), quads between rows, the atlas column's strands root (v 0) -> tip (v 1).
    A width may be a function of s (0 root .. 1 tip); normal_fns: per spine, p -> the card's facing (default: off
    the head, as the clumps); bend > 0: rows closer where the spine bends (m of extra length per radian), so a card
    curving over the crown has no visible facets. Returns the part and its per-loop Guide UVs (the row's particle:
    guide0 + running row index)."""
    part = Part()
    V, NV, guide = [], [], []
    loops_guide = []
    p_index = guide0
    for k, (S, w0, rid, col) in enumerate(zip(spines, widths, ids, cols)):
        S = np.asarray(S, float)
        nfn = normal_fns[k] if normal_fns is not None else None
        if len(S) < 2:
            continue
        rows = int(np.clip(round(_bent_length(S, bend)[1][-1] / row_len) + 1, min_rows, max_rows))
        P, L, sv = _resample(S, rows, bend)
        T = _unit(np.gradient(P, axis=0))
        Ns = []
        for i in range(rows):
            if nfn is not None:
                Ns.append(_unit(nfn(P[i])))
                continue
            loc, n, _ = H.nearest(P[i])
            far = ss(0.008, 0.03, float(np.linalg.norm(P[i] - loc)))
            radial = _unit(np.array([P[i][0], P[i][1] - H.cy, 0.0]))
            Ns.append(_unit(n * (1 - far) + radial * far))
        Ns = np.array(Ns)
        for _ in range(2):
            Ns[1:-1] = _unit(Ns[1:-1] * 0.5 + (Ns[:-2] + Ns[2:]) * 0.25)
        u0, u1 = (col + 0.03) / COLS, (col + 0.97) / COLS
        base = len(V)
        b_prev = None
        for i in range(rows):
            s = sv[i]
            n = Ns[i]
            b = _unit(np.cross(T[i], n))
            if b_prev is not None and np.dot(b, b_prev) < 0:
                b = -b
            b_prev = b
            n = _unit(np.cross(b, T[i]))
            w = w0(s) if callable(w0) else w0 * (0.8 + 0.2 * ss(0.0, 0.15, s)) * (1 - 0.3 * ss(0.6, 1.0, s))
            c = P[i] - (n * root_sink if i == 0 else 0)
            # dip_len > 0: flat at the root, the trough growing in over that length (m) - dipped from the root, a card's
            # first centimetre sank under the cap: the part showed a band of bare cap and the hairline the cap's edge
            dip = n * w * curve * (ss(0.0, dip_len, s * L) if dip_len > 0 else 1.0)
            for side in (-1.0, 0.0, 1.0):
                V.append(c + b * side * w * 0.5 - dip * abs(side))
                NV.append(_unit(n + b * side * spread))     # (how round it lights across; low: no leaves on short cards)
            guide.append(p_index + i)
        for i in range(rows - 1):
            r0, r1 = base + i * 3, base + (i + 1) * 3
            s0, s1 = sv[i], sv[i + 1]
            for a, b_ in ((0, 1), (1, 2)):
                part.faces.append((r0 + a, r0 + b_, r1 + b_, r1 + a))
                for (rr, cc, s) in ((r0, a, s0), (r0, b_, s0), (r1, b_, s1), (r1, a, s1)):
                    # v0 > 0: the root shadow starts that far along (short hair: in rows of short cards the dark
                    # roots read as fish scales; the atlas's own soft starts stay - skipped too, the root edges cut
                    # hard)
                    part.uv0.append((u0 + (u1 - u0) * cc / 2.0, s))
                    part.uv1.append((rid, v0 + (1.0 - v0) * s))
                    loops_guide.append((float(p_index + (rr - base) // 3), s))
        p_index += rows
    part.verts = np.array(V) if V else np.zeros((0, 3))
    part.normals = NV
    part.edge = [0.0] * len(V)
    part.layer = [layer] * len(V)
    return part, loops_guide, p_index


PART_HALF = 0.0017      # the parting's half width at the front (m; 2.5 mm read as a ruled stripe)
PART_CLEAR = 0.004      # card roots at least this far off it (m)


def part_along(H, P):
    """0..1 along a centre parting: 1 from the front hairline to just short of the crown, 0 past it (it tapers out
    behind the top of the head) and below the top."""
    P = np.asarray(P)
    return ss(H.cy + 0.03, H.cy - 0.005, P[..., 1]) * ss(H.eye_z + 0.03, H.eye_z + 0.06, P[..., 2])


def parting(H, cap, part_x=0.0):
    """The cap shell of a draped style: `cap.parting` per vertex, its signed distance across the parting in the
    parting's half widths (the shader cuts the shell where it is under 1: the scalp shows; signed, so it interpolates
    exactly over the shell's centimetre triangles; 99 off the parting) - Daniel: "Shouldn't we have a line in the
    middle of the head that divides the hair for each side?". And its strand texture turned to run away from the
    parting over the top (its tiling ran front to back there: across the hair)."""
    V = np.asarray(cap.verts)
    k = part_along(H, V)
    # not ruled straight: it wanders a little from front to back
    x = V[:, 0] - part_x - 0.0012 * np.sin(V[:, 1] * 90.0 + 1.3) - 0.0006 * np.sin(V[:, 1] * 230.0)
    cap.parting = np.where(k > 0.02, x / (PART_HALF * np.maximum(k, 0.02)), 99.0 * np.sign(x + 1e-9))
    top = ss(H.eye_z + 0.03, H.eye_z + 0.085, V[:, 2])
    # a side parting ends at the crown: behind it the texture runs down the back, as the hair (hum_drape.comb_dir)
    back = 1.0 - ss(H.cy + 0.045, H.cy + 0.01, V[:, 1]) if part_x != 0.0 else np.zeros(len(V))
    loops = [v for f in cap.faces for v in f]
    uv = []
    for (u0, v0), vi in zip(cap.uv0, loops):
        p = V[vi]
        t = float(top[vi])
        b = float(back[vi])
        # over the top: across = front to back, along = away from the parting (falling outward as the sides' tiling
        # falls downward, and meeting it where they blend); the sides keep the shell's own tiling
        u1, v1 = (p[1] - H.cy) * 40.0, (H.eye_z + 0.11 - abs(p[0] - part_x)) * 40.0
        u1, v1 = u1 * (1 - b) + p[0] * 40.0 * b, v1 * (1 - b) + (H.eye_z + 0.11 - (p[1] - H.cy)) * 40.0 * b
        uv.append((u0 * (1 - t) + u1 * t, v0 * (1 - t) + v1 * t))
    cap.uv0 = uv


def tie_uv(H, cap, tie):
    """The cap shell of a tied style: its strand texture turned to run to the tie (its tiling fell down the sides,
    across the hair pulled back over it: stripes between the cards). Polar round the tie: u by the angle (a whole
    number of tiles round, unwrapped per face: no seam), v by the distance."""
    V = np.asarray(cap.verts)
    loc, n, _ = H.nearest(tie)
    e1 = _unit(np.array([1.0, 0.0, 0.0]) - n * n[0])
    e2 = np.cross(n, e1)
    D = V - loc
    th = np.arctan2(D @ e2, D @ e1)
    rho = np.linalg.norm(D, axis=1)
    k = 25.0 / (2 * math.pi)
    uv = []
    for f in cap.faces:
        a0 = th[f[0]]
        for vi in f:
            a = a0 + (th[vi] - a0 + math.pi) % (2 * math.pi) - math.pi
            uv.append((a * k, rho[vi] * 40.0))
    cap.uv0 = uv


def cap_guides(cap, width=0.012):
    """The cap shell's per-loop Guide UVs: x -1 (the cap, not simulated), y how far its edge dissolves there (1 on its
    border .. 0 from `width` m in; Humans/HairCards cuts the shell along its strand texture by it). The shell's hard
    border read as a wig line across the brow."""
    from collections import Counter
    V = np.asarray(cap.verts)
    edges = Counter(tuple(sorted((f[i], f[(i + 1) % len(f)]))) for f in cap.faces for i in range(len(f)))
    border = sorted({v for e, c in edges.items() if c == 1 for v in e})
    if not border:
        return [(-1.0, 0.0)] * len(cap.uv0)
    B = V[border]
    d = np.array([np.min(np.linalg.norm(B - p, axis=1)) for p in V])
    k = 1.0 - ss(0.0, width, d)
    out = [(-1.0, float(k[v])) for f in cap.faces for v in f]
    assert len(out) == len(cap.uv0), (len(out), len(cap.uv0))
    return out


def _layer_spines(H, st, seed, spacing_k=1.0, floor_add=0.0, length_k=1.0, lift_add=0.0):
    st = dict(st)
    st["spacing"] = st["spacing"] * spacing_k
    st["cap"] = st["cap"] + floor_add                 # hair_spines grows from floor = cap + 1.5 mm
    if "length" in st:
        lo, hi = st["length"]
        st["length"] = (lo * length_k * 0.82, hi * length_k * 1.06)     # a ragged hem, not a straight cut
    st["lift"] = st.get("lift", 0.0) + lift_add
    st.pop("tail", None)                              # the ponytail is tail_parts' (a round, hanging bundle)
    return hum_styles.hair_spines(H, st, seed)


# a layer: name, atlas columns, roots spacing x, floor (m), length x, lift +, card width x the clump width
LAYERS = [
    ("inner", (0, 1, 2), 1.0, 0.0, 0.94, 0.0, 1.7),
    ("outer", (3, 4, 5), 1.3, 0.0035, 1.0, 0.02, 1.35),
    ("wisps", (6, 7), 2.6, 0.006, 1.08, 0.01, 0.9),
]


def style_parts(H, recipe, seed=0, lod=0):
    """The cap, then every layer's cards. Returns (parts, per-loop guide UVs, particle count)."""
    st = hum_styles.HAIR[recipe]
    mask = hum_styles.hair_mask_fn(H, st)
    cap = cap_part(H, mask, st["cap"], subdiv=1 if lod == 0 else 0, ratio=1.0 if lod == 0 else 0.5)
    cap.layer = [0.0] * len(cap.verts)
    parts = [cap]
    guides = cap_guides(cap)
    npart = 0
    layers = LAYERS if lod == 0 else [LAYERS[0], LAYERS[1]]
    for li, (name, cols, sk, fl, lk, la, wk) in enumerate(layers):
        sk = sk * (1.0 if lod == 0 else 1.7)
        if st.get("flow") == "tie":                    # pulled back sleek: the outer layers lie close, no lift
            fl, la = fl * 0.4, 0.0
        spines, W, T, R = _layer_spines(H, st, seed * 10 + li, sk, fl, lk, la)
        if not spines:
            continue
        rng = np.random.default_rng(seed * 100 + li)
        ids = hum_styles.coherent_ids(np.array(R), seed)
        cc = [cols[int(rng.integers(len(cols)))] for _ in spines]
        # beside the face the cards stay as narrow as the clumps were (wide ones covered the eye corners)
        face = [ss(40.0, 70.0, float(H.theta(np.asarray(r)))) for r in R]
        Wc = [w * wk * (1.0 if lod == 0 else 1.5) * (0.6 + 0.4 * f) for w, f in zip(W, face)]
        p, g, npart = cards_part(H, spines, Wc, ids, cc, li / 2.0, guide0=npart,
                                 row_len=0.018 if lod == 0 else 0.04)
        parts.append(p)
        guides += g
    if "tail" in st:
        tparts, tg, npart = tail_parts(H, st, seed, lod, guide0=npart)
        parts += tparts
        guides += tg
    return parts, guides, npart


# a ponytail's rings of cards round its axis: count, radius (x the bundle's), atlas columns, length (x the tail's)
TAIL_RINGS = [(6, 0.40, (0, 1, 2), (0.86, 1.0)), (8, 0.75, (3, 4, 5), (0.78, 1.0)),
              (9, 1.00, (3, 4, 5, 6), (0.66, 0.98)), (3, 1.12, (6, 7), (0.55, 0.92))]


def tail_parts(H, st, seed=0, lod=0, guide0=0, length=0.26, r_tie=0.008, r_mid=0.031, r_tip=0.013):
    """Daniel 2026-10-29: "That ponytail mesh is horrible" (the old tail: a flat fan of blades sticking straight back).
    A ponytail is a bundle gathered at a tie: round in section, out from the head a little and then hanging down the
    back of the neck (kept off the head and the body), fuller below the tie and tapering to the tips. Its cards stand
    in rings round the axis facing out (they light as a cylinder), twisting a little along it; a hair-wrapped band
    hides the gather. Returns (parts: cards, band; per-loop Guide UVs; particle count)."""
    rng = np.random.default_rng(seed * 7 + 3)
    tie = np.array(st["tie"]) + np.array([0, H.cy, H.eye_z])
    loc, n, _ = H.nearest(tie)
    A = [loc + n * 0.006]                             # the gather sits on the hair, no gap
    d = _unit(n * 0.7 + np.array([0, 0, -1.0]) * 0.3)
    steps = 30
    guard = H.face_guard(radial=False, front=False, clearance=r_mid + 0.012)
    R = lambda s: r_tie + (r_mid - r_tie) * ss(0.0, 0.28, s) - (r_mid - r_tip) * ss(0.55, 1.0, s)
    for i in range(steps):
        s = (i + 1) / steps
        d = _unit(d + np.array([0, 0, -1.0]) * 0.16)
        p = A[-1] + d * length / steps
        l2, n2, _ = H.nearest(p)
        h = float(np.dot(p - l2, n2))
        want = min(R(s) + 0.006, 0.006 + 0.08 * s)      # the root may tuck into the hair it gathers
        if h < want:                                    # off the back of the head and the neck
            p = p + n2 * (want - h)
        p = guard(A[-1], p)
        d = _unit(p - A[-1])
        A.append(p)
    A = np.array(A)
    for _ in range(3):
        A[1:-1] = A[1:-1] * 0.5 + (A[:-2] + A[2:]) * 0.25
    T = _unit(np.gradient(A, axis=0))
    e1 = [_unit(np.array([1.0, 0, 0]) - T[0] * T[0][0])]          # a frame carried along the axis (no flips)
    for i in range(1, len(A)):
        e = e1[-1] - T[i] * np.dot(e1[-1], T[i])
        e1.append(_unit(e))
    e1 = np.array(e1)
    e2 = np.cross(T, e1)

    def at(s):
        i = min(int(s * (len(A) - 1)), len(A) - 2)
        f = s * (len(A) - 1) - i
        return (A[i] * (1 - f) + A[i + 1] * f, _unit(e1[i] * (1 - f) + e1[i + 1] * f),
                _unit(e2[i] * (1 - f) + e2[i + 1] * f))

    def facing(p):
        j = int(np.argmin(np.linalg.norm(A - p, axis=1)))
        return _unit(p - A[j])

    spines, widths, ids, cols, nfns = [], [], [], [], []
    rings = TAIL_RINGS if lod == 0 else [(4, 0.45, (0, 1, 2), (0.86, 1.0)), (6, 0.9, (3, 4, 5), (0.75, 1.0))]
    for ring, (cnt, rf, cl, lr) in enumerate(rings):
        a0 = rng.uniform(0, 6.28)
        for k in range(cnt):
            a = a0 + 2 * math.pi * k / cnt + rng.normal(0, 0.15)
            twist = rng.uniform(0.3, 0.8)
            Lk = rng.uniform(*lr)
            rk = rf * rng.uniform(0.92, 1.08)
            sp = []
            for s in np.linspace(0.0, Lk, 24):
                c, u, v = at(s)
                ang = a + twist * s
                spread = 1.0 + 0.25 * ss(0.75, 1.0, s / max(Lk, 1e-6)) * (ring >= 2)    # tips loosen a little
                sp.append(c + (u * math.cos(ang) + v * math.sin(ang)) * R(s) * rk * spread)
            spines.append(np.array(sp))
            circ = 2 * math.pi * rf
            widths.append(lambda s, Lk=Lk, circ=circ, cnt=cnt: R(s * Lk) * circ / cnt * 1.45
                          * (1 - 0.35 * ss(0.7, 1.0, s)))
            ids.append(float(rng.random()))
            cols.append(cl[int(rng.integers(len(cl)))])
            nfns.append(facing)
    cards, g, npart = cards_part(H, spines, widths, ids, cols, 1.0, guide0=guide0,
                                 row_len=0.018 if lod == 0 else 0.04, curve=0.0, root_sink=0.0, normal_fns=nfns)
    # the band: a hair-wrapped tie round the gather (drawn like the cap: guide -1, the old strand texture)
    band = Part()
    c, u, v = at(0.03)
    tn = _unit(T[1])
    rmaj, rmin = R(0.03) + 0.0015, 0.0032
    NU, NV = 14, 6
    for i in range(NU):
        a = 2 * math.pi * i / NU
        radial = u * math.cos(a) + v * math.sin(a)
        for j in range(NV):
            b = 2 * math.pi * j / NV
            nn = radial * math.cos(b) + tn * math.sin(b)
            band.verts.append(c + radial * rmaj + nn * rmin)
            band.normals.append(nn)
            band.edge.append(0.0)
    for i in range(NU):
        for j in range(NV):
            q = [i * NV + j, ((i + 1) % NU) * NV + j, ((i + 1) % NU) * NV + (j + 1) % NV, i * NV + (j + 1) % NV]
            band.faces.append(tuple(q))
            for (ii, jj) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                band.uv0.append((ii / NU * 3.0, jj / NV * 0.4))
                band.uv1.append((1.0, 0.35))
    band.verts = np.array(band.verts)
    band.layer = [1.0] * len(band.verts)
    return [cards, band], g + [(-1.0, 0.0)] * len(band.uv0), npart


def draped_strands(H, name, seed=0, lod=0):
    """Each layer's draped strands (hum_drape): a list of (strands, roots, layer recipe)."""
    import bpy
    import hum_drape
    dv = DRAPED[name]
    st = hum_styles.HAIR[STYLES[name]]
    mask = hum_styles.hair_mask_fn(H, st)
    arm = bpy.data.objects.get("HumanRig")
    shoulder_z = float(arm.data.bones["upperarm_l"].head_local[2]) if arm else H.eye_z - 0.33
    if "hem" in dv:
        hem_f = shoulder_z + dv["hem"][0]
        hem_b = shoulder_z + dv["hem"][1]
    H.domes = True
    out = []
    layers = dv["layers"] if lod == 0 else dv["layers"][:3]      # LOD1: fill, inner, locks
    for li, (sk, fl, wk, cols) in enumerate(layers):
        sk = sk * (1.0 if lod == 0 else 1.8)
        roots = sample_roots(H, mask, dv["spacing"] * sk, seed * 10 + li)
        roots = np.array([r for r in roots if float(H.ear_dist(r)) > 0.016])
        # below the eyes only the sides and the nape grow hair (the mask let a point under the jaw through: a strand
        # from inside the throat across the neck)
        roots = np.array([r for r in roots if r[2] > H.eye_z or abs(r[0]) > 0.05 or r[1] - H.cy > 0.02])
        # none on the parting itself: a root there laid its card across the line
        px = dv.get("part_x", 0.0)
        on = (np.abs(roots[:, 0] - px) < PART_CLEAR) & (part_along(H, roots) > 0.0)
        roots[on, 0] = px + np.where(roots[on, 0] >= px, 1.0, -1.0) * PART_CLEAR
        if 6 in cols:                                  # wisps: not on top (they stood up off the crown as strays)
            roots = np.array([r for r in roots if r[2] < H.eye_z + 0.075])
        if fl < 0:                                     # the fill: sides and back (its wide cards hung over the face)
            roots = roots[hum_drape.front_of(H, roots) < 0.25]
        vol = (max(dv["volume"][0] + fl, 0.0), max(dv["volume"][1] + fl, 0.0))
        root_clear = st["cap"] + 0.0015                # on the cap shell
        vol_k = 1.0 - 0.5 * hum_drape.front_of(H, roots)   # the front lies flatter (it puffed and rolled at the temples)
        if "length" in dv:                             # short: hung only its own length
            lens = short_lengths(H, dv, roots, seed * 10 + li)
            P, s = hum_drape.drape(H, roots, float(lens.max()) + 0.02, vol, root_clear=root_clear, vol_k=vol_k,
                                   seed=seed * 10 + li, lengths=lens, part_x=px,
                                   stiff_len=dv.get("stiff_len", 0.05))
            k = np.searchsorted(s, lens, side="right") - 1
            strands = [P[i, :max(int(k[i]), 3) + 1] for i in range(len(P))]
            front = (roots[:, 0] > px).astype(int)     # locks don't mix across the parting
        else:
            # twice: the first finds each strand's hem, the second hangs it only that long (+3 cm; the rest piled up)
            P, s = hum_drape.drape(H, roots, 0.6, vol, root_clear=root_clear, vol_k=vol_k, seed=seed * 10 + li,
                                   part_x=px)
            _, lens = hum_drape.hem_cut(H, P, s, hem_f, hem_b, dv["hem_u"], dv["ragged"], seed=seed * 10 + li)
            P, s = hum_drape.drape(H, roots, 0.6, vol, root_clear=root_clear, vol_k=vol_k, seed=seed * 10 + li,
                                   lengths=lens + 0.03, part_x=px)
            strands, _ = hum_drape.hem_cut(H, P, s, hem_f, hem_b, dv["hem_u"], dv["ragged"], seed=seed * 10 + li,
                                           lengths=lens + 0.03)
            front = P[:, -1, 1] < hum_drape.SHOULDER_Y  # over the shoulder in front: locks don't mix the two
        if fl >= 0:                                    # the fill stays spread
            strands = hum_drape.clump(strands, P[:, 0], dv["clump"], dv["lock"], seed=seed * 10 + li, groups=front)
        strands = hum_drape.settle(H, strands, vol, root_clear=root_clear, vol_k=vol_k)
        out.append((strands, P[:, 0], (sk, fl, wk, cols)))
    if dv.get("fringe") and lod == 0:
        out.append(_fringe(H, dv, seed))
    return out


def _fringe(H, dv, seed=0):
    """Fine short hair along the front hairline (forehead to temples): roots a little in front of it, combed back over
    it on sparse wisp cards. Card roots alone left the cap's front edge as a hard line across the brow."""
    import hum_drape
    from mathutils import Vector
    n, length, width = dv["fringe"]
    px = dv.get("part_x", 0.0)
    th, dz = zip(*H.HAIRLINE)
    rng = np.random.default_rng(seed + 77)
    roots = []
    for side in (-1.0, 1.0):
        # off the parting (a side parting: the middle has hair, the parting's few mm don't)
        for t in np.linspace(7.0 if px == 0.0 else 2.0, 70.0, n) + rng.uniform(-2.0, 2.0, n):
            z = H.eye_z + float(np.interp(t, th, dz)) - 0.003
            d = np.array([side * math.sin(math.radians(t)), -math.cos(math.radians(t)), 0.0])
            q = np.array([0.0, H.cy, z]) + d * 0.2           # in along a level ray (the nearest point slid down the brow)
            hit = H.bvh.ray_cast(Vector(q), Vector(-d))[0]
            if hit is not None and abs(hit[0] - px) > PART_CLEAR + 0.002:
                roots.append(np.array(hit))
    roots = np.array(roots)
    lens = rng.uniform(0.6, 1.0, len(roots)) * length
    P, s = hum_drape.drape(H, roots, length, (0.003, 0.003), root_clear=0.002, lengths=lens, seed=seed + 78,
                           part_x=px)
    k = [int(np.searchsorted(s, L, side="right")) for L in lens]
    strands = [P[i, :max(k[i], 3)] for i in range(len(P))]
    return strands, roots, (1.0, 0.0, width / dv["width"], (6, 7))


# ------------------------------------------------------------------ short styles (Crop)
# Short hair lies on the scalp along the recipe's flow (no gravity, no drape), at a clearance growing from the cap to
# the style's volume, its length by where it grows - Daniel 2026-10-30, the next style after Long: "Crop" (the most
# worn: 37 named NPCs, 16 % of random men). The clump Crop was spiky feathers with a jagged fringe over the eyes.
#   length   (top, front fringe, sides, back, nape) in m: longer on top, short and tapering down the sides and back
#   volume   (sides, top) clearance over the cap (m); layers as DRAPED's (spacing x, extra volume, width x, columns)
#   fringe_z the front stops this far above the eyes (m), give or take a few mm a strand (a straight line: a bowl cut)
#   whorl    extra short cards spiralling over the whorl's middle: count, radii (m), length (m) - the cards round it
#            all start at their roots and run outward, leaving its middle bare cap
#   cap_light how much lighter than _CapShade the cap shell is (more of it shows under short hair; below 0 darker
#             close up, lit as the hair from afar)
#   spacing0 LOD0's layer spacings x this (LOD1 keeps the recipe's: more of it close up only)
#            (with `fill`, LOD0's coil layers root anywhere on the scalp, not only on head vertices: scalp_points)
#   fill     LOD0, coils: more curls, as the inner layer's, wherever the cap is further than this (m) from one
#            (`fill_gaps`)
#   crown    the whorl it is brushed from: (back of the top of the head, below it) m; fan: how far it spreads sideways
#            over the top (the head's own crown, 3.5 cm behind the top, fanned the top every which way: patchy, curly
#            from the game camera)
SHORT = {
    # (cards 2.2 cm wide on 1.2 cm read as petals round the whorl - from the game camera a bun. Every flow over a
    # head has a whorl somewhere: lower down the back it stared out of the back view; it sits at the top of the back
    # and spirals (`swirl`), so short cards wrap over its middle instead of leaving a disc of bare cap)
    "CropStrands": dict(length=(0.055, 0.045, 0.02, 0.03, 0.012), volume=(0.0025, 0.006), spacing=0.01,
                        width=0.016, fringe_z=0.05, ragged=0.3, crown=(0.055, 0.025), fan=0.6, swirl=0.9, v0=0.35,
                        whorl=(10, 0.006, 0.02, 0.025), cap_light=0.5,
                        layers=[(2.2, -0.001, 2.0, (0, 1, 2)), (1.0, 0.0, 1.0, (0, 1, 2)),
                                (1.4, 0.002, 0.85, (3, 4, 5)), (3.0, 0.0035, 0.6, (6, 7))]),
    # combed back from the forehead (the recipe's "back" flow: its whorl lies on the face, none in the hair); the
    # front's hair, longest, rides back over the top. `down`: behind the ears it turns straight down (theta from..to,
    # degrees) - a constant "back" wrapped the sides round the back of the head into a knot at the nape; `hem`: it
    # stops this far under the hairline (m) instead of hanging on down the neck
    "SweptStrands": dict(length=(0.085, 0.10, 0.045, 0.055, 0.02), volume=(0.003, 0.007), spacing=0.011,
                         width=0.018, fringe_z=0.05, ragged=0.25, v0=0.3, cap_light=0.4, down=(100.0, 140.0),
                         hem=0.006,
                         layers=[(2.2, -0.001, 2.0, (0, 1, 2)), (1.0, 0.0, 1.0, (0, 1, 2)),
                                 (1.4, 0.002, 0.85, (3, 4, 5)), (3.0, 0.0035, 0.6, (6, 7))]),
    # pulled back to the tie (the recipe's "tie" flow), sleek, then the round tail (`tail_parts`); its scalp was the
    # clump recipe's guides until 2026-10-30. `gather`: strands stop this close to the tie (m), under the band;
    # `over_ears`: they lift over the ears on the way back (the ear stop cut the temples short). Its cards narrow to
    # the tie (full width all the way, converging cards crossed in a patchwork) and it has no sparse outer layer
    # (lone light cards over sleek hair read as patches); its shell nearly as light as the cards (`tie_uv` runs its
    # texture with them; at 0.4 the shell between the long cards read as dark camouflage blotches) and flat cards
    # (`curve`: a trough as deep as the short styles' dipped the edges of cards lying this close through the shell -
    # wiggly cut lines, a wood-grain look)
    "PonytailStrands": dict(length=(0.3, 0.3, 0.3, 0.3, 0.3), volume=(0.002, 0.0035), spacing=0.011, width=0.016,
                            fringe_z=-1.0, ragged=0.0, v0=0.3, cap_light=0.85, gather=0.009, over_ears=1.2, curve=0.02,
                            layers=[(2.2, -0.001, 2.0, (0, 1, 2)), (1.0, 0.0, 1.0, (0, 1, 2)),
                                    (1.4, 0.0015, 0.7, (3, 4, 5))]),
    # ringlets (2026-10-30, Daniel: "Curly next"; the clump Curly was a mass of blobby leaves): layers whose strands
    # are wound into coils round their path (a layer's 5th item: the coil's radius, m) - `coil` (pitch: one turn every
    # that many m of the path, then card rows a turn at LOD0, LOD1) - each turned up to `turn` degrees off the flow (curls lie
    # every which way, not combed). No flat fill: its straight strands showed between the curls as slicked patches
    # and a smooth band along the hairline. `cap_light` below 0: close up the cap reads as the shadow between curls
    # (at plain _CapShade its straight strands showed under blonde and grey curls as a combed base); from the game
    # camera (and at LOD1, where the curls are few) the shader lights it as the hair's mass (dark, the curls read as
    # specks on a dark head). Coils 1.1-1.2 cm across (9 mm left the cap showing between them). No fringe line
    # (`fringe_z` off): it stopped every strand in front of the ears 5.5 cm over the eyes, so the temples' curls were
    # 5 mm stubs - bare cap from the brow to the ear; they stop at the hairline (`hem`) instead. Denser at LOD0
    # (`spacing0`, then `fill` over what is still bare; Daniel: "some areas are unpopulated"; from the game camera
    # LOD1 was fine as it is). `fill` also roots LOD0's coils anywhere on the scalp (`scalp_points`): on the head's
    # vertices, sparse over the skull, no density reached the crown (back + top stayed 18-20% bare, now 7-10%). `turn` 75: at 45 the curls still ran in lines from the whorl, bare channels between
    "CurlyStrands": dict(length=(0.04, 0.035, 0.028, 0.035, 0.02), volume=(0.002, 0.004), spacing=0.011,
                         width=0.016, fringe_z=-1.0, hem=0.006, ragged=0.3, crown=(0.05, 0.025), fan=0.8, swirl=0.3,
                         v0=0.3, whorl=(16, 0.004, 0.03, 0.03), cap_light=-0.45, coil=(0.016, 5, 3), turn=75.0,
                         curve=0.0, spacing0=0.9, fill=0.005,
                         layers=[(1.1, 0.0, 0.85, (0, 1, 2), 0.0055), (1.7, 0.004, 0.85, (3, 4, 5), 0.006)]),
    # the ponytail's scalp pulled up to the crown, its gather the bun's foot (`bun_parts` coils the bun)
    "BunStrands": dict(length=(0.3, 0.3, 0.3, 0.3, 0.3), volume=(0.002, 0.0035), spacing=0.011, width=0.016,
                       fringe_z=-1.0, ragged=0.0, v0=0.3, cap_light=0.85, gather=0.028, over_ears=1.2, curve=0.02,
                       layers=[(2.2, -0.001, 2.0, (0, 1, 2)), (1.0, 0.0, 1.0, (0, 1, 2)),
                               (1.4, 0.0015, 0.7, (3, 4, 5))]),
}


# hair standing off the scalp (the recipe's band for the cap and roots), not lying on it. Out of the sim, as the bun: a
# gelled crest doesn't swing.
#   length   how far it stands (m) along the crest, by the angle round the skull: (front, top, back, nape)
#   lock     the locks' spacing along the crest (m); gather: how far a strand's tip goes to its lock's tip
#   lean     how far the tips lean back (x the length); flank: how much shorter it stands at the band's edges (a
#            wedge from the front; even lengths read as a slab)
#   layers   (roots spacing x, length x, card width x, atlas columns, "side" | "cross" | "mat"): "side" cards face out
#            of the crest's flanks, turning to face forward and back at its ends; "cross" cards span it, seen from the
#            front; "mat" cards lie on the scalp, brushed back along the crest (length x 6 cm): from behind and above the
#            standing strands point at the camera, and these are what reads as hair there
STAND = {
    "MohawkStrands": dict(length=(0.055, 0.08, 0.065, 0.03), spacing=0.008, width=0.015, lock=0.024, gather=0.85,
                          lean=0.12, ragged=0.15, v0=0.35, cap_light=0.85, flank=0.35,
                          layers=[(3.0, 1.0, 1.4, (0, 1, 2), "mat"), (1.6, 0.85, 2.0, (0, 1, 2), "side"),
                                  (1.0, 1.0, 1.0, (0, 1, 2), "side"), (1.2, 0.95, 1.6, (3, 4, 5), "cross"),
                                  (2.6, 1.1, 0.6, (6, 7), "side")]),
}


def stand_parts(H, name, seed=0, lod=0):
    """The recipe's cap, then each layer's cards along strands standing off the scalp, their tips gathered into locks
    along the crest. Returns (parts, guides, particles: none)."""
    sv = STAND[name]
    st = hum_styles.HAIR[STYLES[name]]
    mask = hum_styles.hair_mask_fn(H, st)
    band = st["band"]
    cap = cap_part(H, mask, st["cap"], subdiv=1 if lod == 0 else 0, ratio=1.0 if lod == 0 else 0.5)
    cap.layer = [0.0] * len(cap.verts)
    cap.uv1 = [(u, 1.0 + sv["cap_light"]) for u, _ in cap.uv1]
    parts = [cap]
    k_space, k_width = ((1.0, 1.0), (1.5, 1.6), (2.4, 2.2))[lod]
    guides = cap_guides(cap)
    zc = H.eye_z + 0.03

    def along(P):                                       # degrees round the skull: 0 on top, forward negative
        P = np.asarray(P)
        return np.degrees(np.arctan2(P[..., 1] - H.cy, P[..., 2] - zc))

    def standing(P):                                    # how far it stands there (m)
        return np.interp(along(P), (-70.0, -35.0, 0.0, 60.0, 115.0), (sv["length"][0], sv["length"][0], sv["length"][1],
                                                                      sv["length"][2], sv["length"][3]))

    def out(r):                                         # off the scalp, a little upward (at the nape, not at the neck)
        _, n, _ = H.nearest(r)
        return n, _unit(n * 0.6 + np.array([0.0, 0.1, 0.5]))

    locks = scalp_points(H, mask, sv["lock"], seed * 10 + 9)
    rng_l = np.random.default_rng(seed + 61)
    lock_tip = []
    for r, k in zip(locks, rng_l.uniform(0.85, 1.15, len(locks))):
        lock_tip.append(r * np.array([0.1, 1.0, 1.0]) + out(r)[1] * float(standing(r)) * k
                        + np.array([0.0, sv["lean"] * float(standing(r)), 0.0]))
    lock_tip = np.array(lock_tip)
    a0, a1 = float(along(locks).min()), float(along(locks).max())
    layers = sv["layers"] if lod == 0 else sv["layers"][:-1] if lod == 1 else sv["layers"][:2]
    for li, (sk, lk, wk, cols, kind) in enumerate(layers):
        rng = np.random.default_rng(seed * 100 + li)
        mat_k = min(k_space, 1.5)                       # (the mat stays closed at every LOD)
        roots = scalp_points(H, mask, sv["spacing"] * sk * (mat_k if kind == "mat" else k_space), seed * 10 + li)
        roots = np.array([r for r in roots if float(H.ear_dist(r)) > 0.016])
        if len(roots) == 0:
            continue
        spines, W, nfns = [], [], []
        for r in roots:
            n, d = out(r)
            if kind == "mat":
                L = 0.06 * lk * rng.uniform(0.8, 1.15) * (1.0 if lod == 0 else 1.3)
                L *= float(np.interp(along(r), (75.0, 110.0), (1.0, 0.3)))   # not a rat-tail down the nape
                S, q = [], np.array(r, float)
                for t in np.linspace(0.0, 1.0, 9):
                    loc, nq, _ = H.nearest(q)
                    S.append(loc + nq * (st["cap"] + 0.0012 + 0.004 * t * t))
                    q = loc - _unit(np.cross(np.array([1.0, 0.0, 0.0]), nq)) * L / 8.0
                spines.append(np.array(S))
                nfns.append(lambda p: H.nearest(p)[1])
                w = sv["width"] * wk * rng.uniform(0.85, 1.15) * mat_k
                W.append(lambda t, w=w: w * (0.85 + 0.15 * ss(0.0, 0.1, t)) * (1.0 - 0.7 * ss(0.4, 1.0, t)))
                continue
            L = float(standing(r)) * lk * rng.uniform(1.0 - sv["ragged"], 1.0 + sv["ragged"] * 0.5)
            L *= 1.0 - sv["flank"] * min(abs(float(r[0])) / band, 1.0)
            tip = lock_tip[int(np.argmin(((locks - r) ** 2).sum(1)))]
            free = r + d * L + np.array([0.0, sv["lean"] * L, 0.0])
            pull = (tip - free) * sv["gather"]
            ts = np.linspace(0.0, 1.0, 9)
            spines.append(np.array([r + n * (st["cap"] + 0.0005) + d * L * t
                                    + np.array([0.0, sv["lean"] * L * t * t, 0.0]) + pull * t * t for t in ts]))
            e = (float(along(r)) - a0) / max(a1 - a0, 1e-6) * 2.0 - 1.0
            run = _unit(np.cross(np.array([1.0, 0.0, 0.0]), n))             # along the crest, toward the front
            sx = float(r[0]) / band
            sx = sx if abs(sx) > 0.1 else float(rng.choice([-0.1, 0.1]))
            if kind == "cross":
                f = run * float(rng.choice([-1.0, 1.0])) + np.array([sx, 0.0, 0.0]) * 0.5
            else:
                f = np.array([sx, 0.0, 0.0]) * 1.5 + run * e ** 3 * 2.0
                f = f + run * rng.uniform(-0.3, 0.3)
            nfns.append(lambda p, f=_unit(f): f)
            w = sv["width"] * wk * rng.uniform(0.85, 1.15) * k_width
            W.append(lambda t, w=w: w * (0.85 + 0.15 * ss(0.0, 0.1, t)) * (1.0 - 0.9 * ss(0.25, 1.0, t)))
        ids = hum_styles.coherent_ids(roots, seed)
        cc = [cols[int(rng.integers(len(cols)))] for _ in spines]
        p, g, _ = cards_part(H, spines, W, ids, cc, li / max(len(layers) - 1, 1), guide0=0,
                             row_len=0.012 if lod == 0 else 0.025, max_rows=(10, 5, 4)[lod], root_sink=0.0,
                             curve=0.05, v0=sv["v0"], normal_fns=nfns)
        parts.append(p)
        guides += [(-2.0, gy) for _, gy in g]
    return parts, guides, 0


# beards (Beard_<name>), redone 2026-10-30 (Daniel: "the current beards are weird"). The clump recipes' stencil (a block on
# the cheek, cut straight at the back and across the top) and hanging flow (a flat curtain from the side) aren't used:
# the outline is drawn to this head's jaw (`beard_outline`), and strands are combed along the jaw toward a point under
# the chin, standing off the skin where the beard has mass and gathering into locks. Kept from his notes of 2026-09-27: the
# sideburn is a smooth rise of the top edge, nothing over the mouth, the chin strap a jawline band, no neckbeard.
# Out of the sim, rigid on the head, exact keys, as the clump beards. beardShadow's skin tint is painted to the old stencil:
# these names get 0 from HumanFaceGenerator.
#   shape    "full" | "short" (no sideburns: the top edge comes down to the jaw) | "goatee" | "mustache" | "strap"
#   spacing  the second layer's roots (m), width: a card's width (m), at most half its length (a short card as wide as long
#            reads as a leaf)
#   drop     how far the longest strands reach below the chin (m), cv: how far their tips close in sideways (x the root's
#            x: 0 a point, 1 a curtain), cheek_L: the longest strand away from the chin (m)
#   bulge    how far strands stand off the skin at the chin (m); lock, gather: the locks' spacing, how far tips go to them
#   hug      short styles: the tip stays on the skin, under the chin too
BEARD_LAYERS = [(1.8, 0.0, 1.8, (0, 1, 2), 0.0), (1.0, 0.0008, 1.0, (0, 1, 2), 0.4), (1.3, 0.0016, 0.8, (3, 4, 5), 0.8),
                (2.5, 0.0024, 0.5, (6, 7), 1.1)]
_LONG = dict(shape="full", v0=0.5, cap_light=0.8, cap=0.002)
_TRIM = dict(v0=0.5, cap_light=1.0, cap=0.0015, drop=0.006, cv=0.75, cheek_L=0.018, bulge=0.0015, lock=0.014, gather=0.3,
             hug=True, spacing=0.006, width=0.007)
BEARD_CARDS = {
    "FullStrands": dict(_LONG, spacing=0.0075, width=0.012, drop=0.055, cv=0.5, cheek_L=0.04, bulge=0.008, lock=0.018,
                        gather=0.6),
    "WizardStrands": dict(_LONG, spacing=0.008, width=0.013, drop=0.16, cv=0.28, cheek_L=0.05, bulge=0.01, lock=0.02,
                          gather=0.65),
    "DwarfStrands": dict(_LONG, spacing=0.008, width=0.016, drop=0.19, cv=0.72, cheek_L=0.06, bulge=0.012, lock=0.022,
                         gather=0.6, cap=0.0025),
    "GoateeStrands": dict(_LONG, shape="goatee", spacing=0.005, width=0.0075, drop=0.022, cv=0.35, cheek_L=0.06, bulge=0.004,
                          lock=0.014, gather=0.6, cap=0.0015),
    "MustacheStrands": dict(_LONG, shape="mustache", spacing=0.003, width=0.0035, drop=0.0, cv=1.0, cheek_L=0.03,
                            bulge=0.002, lock=0.0, gather=0.0, cap=0.0012),
    "ShortStrands": dict(_TRIM, shape="short"),
    "ShortSideburnsStrands": dict(_TRIM, shape="full"),
    "ChinStrapStrands": dict(_TRIM, shape="strap", spacing=0.0055),
}


def beard_outline(H, shape):
    """The beard's area, 0..1 per point. Drawn in profile on this head (y from the chin, z from the mouth): the top edge dips
    to a notch beside the mouth's corner, where the mustache meets the cheek, and rises to the sideburn, a band about 2 cm
    wide in front of the ear that runs up into the hair (a beard stopping on the cheek reads as a patch); the bottom edge
    follows the jaw up to its corner and stops under the chin at the throat."""
    F = H.F
    yc, zm = float(F.chin[1]), float(F.mouth[2])
    dy = (-0.018, -0.008, -0.0006, 0.0074, 0.0224, 0.0374, 0.0524, 0.0614, 0.0684, 0.0764)
    top = (0.019, 0.017, 0.009, 0.006, 0.013, 0.022, 0.032, 0.046, 0.066, 0.076)
    top_short = (0.019, 0.017, 0.009, 0.006, 0.010, 0.012, 0.016, 0.032, 0.064, 0.076)     # the cheek clean, the same sideburn
    low_y = (-0.018, 0.0424, 0.0474, 0.0574, 0.0624, 0.0724, 0.0764)
    low = (-0.053, -0.053, -0.045, -0.04, -0.03, -0.01, 0.01)
    jaw_y = (0.0764, 0.0624, 0.0474, 0.0324, 0.0174, 0.0024, -0.0076)         # the jaw's edge, for the strap
    jaw = (0.01, -0.013, -0.03, -0.037, -0.04, -0.04, -0.035)
    y_back = float(H.ear_y_front) - 0.002

    def area(P):
        x, y, z = P[..., 0], P[..., 1] - yc, P[..., 2] - zm
        ax = np.abs(x)
        low_z = np.interp(y, low_y, low)
        below = ss(low_z - 0.002, low_z + 0.003, z) * ss(y_back - yc + 0.001, y_back - yc - 0.003, y)
        d_lip = H.lip_dist(P)
        lips = np.where(z < -0.002, ss(0.003, 0.008, d_lip), ss(0.0015, 0.004, d_lip))
        top_z = np.interp(y, dy, top)
        lip_x = float(F.lip_x)
        # the mustache: under the nose to the mouth's corners, its ends drooping past them
        droop = ss(lip_x + 0.014, lip_x + 0.009, ax) * ss(lip_x - 0.002, lip_x + 0.002, ax) * ss(-0.009, -0.005, z)
        over = ss(0.002, 0.004, z) * ss(lip_x + 0.014, lip_x + 0.009, ax)
        tache = np.maximum(over, droop) * ss(top_z + 0.002, top_z - 0.003, z) * ss(0.02, 0.012, y)   # (the face only)
        if shape == "mustache":
            return tache * lips
        if shape == "goatee":                                               # + a chin patch, narrow under the lip
            wide = np.interp(z, (-0.04, -0.012), (0.021, 0.010))
            chin = ss(-0.006, -0.012, z) * ss(wide + 0.003, wide - 0.003, ax) * ss(0.0424, 0.0324, y) * below
            return np.maximum(tache, chin) * lips
        if shape == "strap":                                                # a band on the jaw, rising to the sideburn
            band = np.interp(y, jaw_y[::-1], jaw[::-1]) + np.interp(y, (0.0, 0.05), (0.012, 0.018))
            rise = ss(0.0474, 0.0724, y)
            edge = band + (top_z - band) * rise
            return ss(edge + 0.002, edge - 0.003, z) * below * lips
        if shape == "short":
            top_z = np.interp(y, dy, top_short)
        return ss(top_z + 0.002, top_z - 0.003, z) * below * lips
    return area


def beard_tip(H, sv, r, rng, layer_k):
    """Where a strand from r is combed to, and how much of it there is around the chin (0..1)."""
    F = H.F
    zm = float(F.mouth[2])
    corner = r[1] < F.chin[1] + 0.012 and zm - 0.016 < r[2] and abs(r[0]) > float(F.lip_x) - 0.002
    if sv["shape"] == "mustache" or corner or (r[2] > zm + 0.002 and r[1] < F.chin[1] + 0.012):    # the mustache: out and drooping
        over = r[2] > zm + 0.002
        d = _unit(np.array([np.sign(r[0] + 1e-6) * (1.0 if over else 0.3), -0.15, -0.38 if over else -1.0]))
        return r + d * (rng.uniform(0.02, 0.03) if over else rng.uniform(0.008, 0.012)), 0.0
    w = float(np.exp(-0.5 * ((abs(r[0]) / 0.042) ** 2 + ((r[1] - F.chin[1] - 0.008) / 0.05) ** 2)))
    z0 = zm - 0.043                                                       # the chin's underside
    burn = ss(0.045, 0.068, r[1] - F.chin[1])
    T = np.array([r[0] + (r[0] * sv["cv"] - r[0]) * (1.0 - burn),
                  r[1] + (F.chin[1] + 0.012 + 0.006 - 0.01 * layer_k - r[1]) * 0.7 * (1.0 - 0.85 * burn),
                  min(z0 - sv["drop"] * (0.15 + 0.85 * w ** 1.2) * rng.uniform(0.85, 1.1), r[2] - 0.015)])
    L = float(np.linalg.norm(T - r))
    far = sv["cheek_L"] * rng.uniform(0.85, 1.1)
    reach = far + (L - far) * w ** 2
    return (r + (T - r) * min(reach / max(L, 1e-6), 1.0)), w


def beard_normal(H, p):
    """A beard card's facing: off the skin, leaning out from the head and a little up."""
    _, n, _ = H.nearest(p)
    return n + _unit(np.array([p[0], p[1] - H.cy, 0.0])) * 0.9 + np.array([0.0, 0.0, 0.3])


def beard_card_parts(H, name, seed=0, lod=0):
    """The outline's cap (its border dissolving), then each layer's cards along strands combed to their tips."""
    sv = BEARD_CARDS[name]
    H.domes = False
    mask = beard_outline(H, sv["shape"])
    cap = cap_part(H, mask, sv["cap"], subdiv=1 if lod == 0 else 0, uv_scale=60.0, ratio=(1.0, 0.5, 0.25)[lod])
    cap.layer = [0.0] * len(cap.verts)
    cap.uv1 = [(u, 1.0 + sv["cap_light"]) for u, _ in cap.uv1]
    parts = [cap]
    guides = cap_guides(cap)
    k_space, k_width = ((1.0, 1.0), (1.8, 1.6), (3.0, 2.6))[lod]
    layers = BEARD_LAYERS if lod == 0 else BEARD_LAYERS[:3] if lod == 1 else BEARD_LAYERS[:1]
    rng_l = np.random.default_rng(seed + 83)
    locks = locks_tip = None
    if sv["lock"]:
        locks = scalp_points(H, mask, sv["lock"], seed * 10 + 9, thresh=0.5)
        locks = np.array([H.nearest(q)[0] for q in locks])
        locks_tip = np.array([beard_tip(H, sv, q, rng_l, 0.5)[0] for q in locks])

    def settle(q, floor):                                 # at least `floor` off the skin
        loc, n, _ = H.nearest(q)
        h = float(np.dot(q - loc, n))
        return q + n * (floor - h) if h < floor else q

    for li, (sk, fl, wk, cols, bk) in enumerate(layers):
        rng = np.random.default_rng(seed * 100 + li)
        layer_k = li / max(len(layers) - 1, 1)
        floor = sv["cap"] + 0.0008 + fl
        roots, spines, W = [], [], []
        for r0 in scalp_points(H, mask, sv["spacing"] * sk * k_space, seed * 10 + li, thresh=0.5):
            if float(H.ear_dist(r0)) < 0.005:
                continue
            loc, n, _ = H.nearest(r0)
            tip, w_chin = beard_tip(H, sv, loc, rng, layer_k)
            if locks is not None and w_chin > 0.0:        # (not the mustache)
                tip = tip + (locks_tip[int(np.argmin(((locks - loc) ** 2).sum(1)))] - tip) * sv["gather"]
            if sv.get("hug") or w_chin == 0.0:
                t_loc, t_n, _ = H.nearest(tip)
                tip = t_loc + t_n * (floor + 0.001)
            bulge = sv["bulge"] * bk * (0.3 + 0.7 * w_chin)
            start = loc + n * (sv["cap"] + 0.0005)
            mid = start + n * bulge * 2.0 + (tip - start) * 0.4     # (a quadratic's middle reaches half its control)
            S = []
            for t in np.linspace(0.0, 1.0, 9):
                S.append(settle(start * (1 - t) ** 2 + mid * 2 * t * (1 - t) + tip * t * t, floor if t > 0.0 else 0.0))
            S = np.array(S)
            S[1:-1] = S[1:-1] * 0.5 + (S[:-2] + S[2:]) * 0.25
            L = float(np.linalg.norm(np.diff(S, axis=0), axis=1).sum())
            if L < 0.004:
                continue
            roots.append(loc)
            spines.append(S)
            v = min(sv["width"] * wk * rng.uniform(0.85, 1.15), L * 0.5) * k_width
            W.append(lambda t, v=v: v * (0.45 + 0.55 * ss(0.0, 0.18, t)) * (1.0 - 0.75 * ss(0.4, 1.0, t)))
        if not roots:
            continue
        ids = hum_styles.coherent_ids(np.array(roots), seed)
        cc = [cols[int(rng.integers(len(cols)))] for _ in spines]
        p, g, _ = cards_part(H, spines, W, ids, cc, layer_k, guide0=0, row_len=(0.008, 0.018, 0.03)[lod],
                             max_rows=(14, 7, 4)[lod], min_rows=(4, 3, 2)[lod], root_sink=0.0, curve=0.03, v0=sv["v0"],
                             spread=0.2, normal_fns=[lambda q: beard_normal(H, q)] * len(spines))
        parts.append(p)
        guides += [(-2.0, gy) for _, gy in g]
    return parts, guides, 0


def short_lengths(H, sv, roots, seed=0):
    """Each root's hair length by where it grows (sv["length"]), a little ragged."""
    import hum_drape
    top, front, side, back, nape = sv["length"]
    R = np.asarray(roots)
    rng = np.random.default_rng(seed + 31)
    th = H.theta(R)
    t_top = ss(H.eye_z + 0.03, H.eye_z + 0.085, R[:, 2])
    low = side + (back - side) * ss(100.0, 150.0, th)               # sides -> back
    low = low * (0.4 + 0.6 * ss(H.eye_z - 0.06, H.eye_z, R[:, 2]))    # the back tapers down to the nape
    low = np.maximum(low, nape)
    L = low + (top - low) * t_top
    L = L + (front - L) * hum_drape.front_of(H, R) * t_top           # the fringe
    return L * rng.uniform(1.0 - sv["ragged"] * 0.5, 1.0 + sv["ragged"] * 0.5, len(R))


def short_flow(H, sv, st=None):
    """Brushed from the whorl (sv["crown"]) outward and a little forward and down, spreading less sideways over the
    top (sv["fan"]); without a "crown", the recipe's own flow."""
    if "crown" not in sv:
        fl = hum_styles.flow_fn(H, st)
        if "over_ears" in sv:
            lift = sv["over_ears"]

            def g(p, n):
                d = fl(p, n)
                return (d / max(np.linalg.norm(d), 1e-9)
                        + np.array([0.0, 0.0, lift]) * ss(0.04, 0.015, float(H.ear_dist(p))))
            return g
        if "down" not in sv:
            return fl
        a, b = sv["down"]

        def f(p, n):
            k = ss(a, b, float(H.theta(p)))
            return fl(p, n) * (1.0 - k) + np.array([0.0, 0.25, -1.0]) * k
        return f
    top = float(H.co[:, 2].max())
    c = np.array([0.0, H.cy + sv["crown"][0], top - sv["crown"][1]])
    fan = sv["fan"]

    swirl = sv.get("swirl", 0.0)

    def f(p, n):
        r = p - c
        d = r + np.array([0.0, -0.02, -0.03])
        k = ss(H.eye_z + 0.04, H.eye_z + 0.09, p[2])
        d[0] *= 1.0 - (1.0 - fan) * k
        # round the whorl (1.6 over 7 cm read as a cinnamon roll from the game camera)
        d = d + swirl * np.cross(n, r) * ss(0.05, 0.01, float(np.linalg.norm(r)))
        return d
    return f


def grow_short(H, roots, lengths, volume, flow, root_clear, step=0.005, fringe_z=0.05, seed=0, hem=None,
               gather=None, turn=None):
    """Strands lying on the head: each step along the flow, tangent to the scalp, then set back at its clearance
    (root_clear growing to the volume - top or sides - over the first 2 cm). Stops at the fringe line (in front of
    the ears, `fringe_z` above the eyes), short of the ears, given `hem` that far under the hairline and given
    `gather` (point, radius) that close to a tie. `turn`: per strand, radians off the flow (round the scalp's
    normal)."""
    out = []
    v_side, v_top = volume
    rng = np.random.default_rng(seed + 41)
    fz = fringe_z + rng.uniform(-0.006, 0.004, len(roots))
    hz = (hem if hem is not None else 1.0) + rng.uniform(-0.004, 0.008, len(roots))   # ragged (one line: a helmet)
    for i, (r, L, f_z, h_z) in enumerate(zip(roots, lengths, fz, hz)):
        loc, n, _ = H.nearest(r)
        P = [loc + n * root_clear]
        s = 0.0
        while s < L:
            p = P[-1]
            loc, n, _ = H.nearest(p)
            d = flow(p, n)
            d = d - n * np.dot(d, n)
            if turn is not None:
                d = d * math.cos(turn[i]) + np.cross(n, d) * math.sin(turn[i])
            d = d / max(np.linalg.norm(d), 1e-9)
            q = p + d * step
            loc, n, _ = H.nearest(q)
            vol = v_side + (v_top - v_side) * ss(H.eye_z + 0.03, H.eye_z + 0.085, q[2])
            q = loc + n * (root_clear + vol * ss(0.0, 0.02, s + step))
            if q[1] < H.ear_y_front and q[2] < H.eye_z + f_z and len(P) > 1:
                break
            if float(H.ear_dist(q)) < 0.012 and len(P) > 1:
                break
            if hem is not None and q[2] < float(H.hairline_z(q)) - h_z and len(P) > 2:
                break
            if gather is not None and len(P) > 1:
                dq = np.linalg.norm(q - gather[0])
                if dq < gather[1] or (dq < 0.025 and dq > np.linalg.norm(p - gather[0])):   # there, or past it
                    break
            P.append(q)
            s += step
        if len(P) >= 2:
            out.append(np.array(P))
        else:
            out.append(np.array([P[0], P[0] + n * 0.002]))
    return out


def short_parts(H, name, seed=0, lod=0):
    """The recipe's cap (its border dissolving), then each layer's cards along strands lying on the head."""
    import hum_drape
    sv = SHORT[name]
    st = hum_styles.HAIR[STYLES[name]]
    mask = hum_styles.hair_mask_fn(H, st)
    cap = cap_part(H, mask, st["cap"], subdiv=1 if lod == 0 else 0, ratio=1.0 if lod == 0 else 0.5)
    cap.layer = [0.0] * len(cap.verts)
    cl = sv.get("cap_light", 0.0)
    # past 1 the shader lightens the shell; below 0 it darkens it close up (to (1 + uv1.y) of _CapShade)
    cap.uv1 = [(u, 1.0 + cl if cl >= 0.0 else cl) for u, _ in cap.uv1]
    if "gather" in sv:
        tie_uv(H, cap, np.array(st["tie"]) + np.array([0, H.cy, H.eye_z]))
    parts = [cap]
    guides = cap_guides(cap)
    npart = 0
    flow = short_flow(H, sv, st)
    H.domes = bool(st.get("cover_ears"))
    root_clear = st["cap"] + 0.0015
    gather = None
    if "gather" in sv:          # on the hair, as the tail's gather (on the skin, under strands lying 5-7 mm out, it
        # was out of reach: they circled it to their full length)
        loc, n, _ = H.nearest(np.array(st["tie"]) + np.array([0, H.cy, H.eye_z]))
        gather = (loc + n * 0.006, sv["gather"])
    def keep(roots):                                    # off the ears, out of the face
        roots = np.array([r for r in roots if float(H.ear_dist(r)) > 0.016])
        return np.array([r for r in roots if r[2] > H.eye_z or abs(r[0]) > 0.05 or r[1] - H.cy > 0.02])

    layers = sv["layers"] if lod == 0 else sv["layers"][:3]
    fill = lod == 0 and sv.get("fill")
    laid = []                                           # the coil layers' paths dropped on the scalp (for `fill`)
    for li in range(len(layers) + (1 if fill else 0)):
        if li < len(layers):
            sk, fl, wk, cols, *rc = layers[li]
            r_coil = rc[0] if rc else 0.0
            sk = sk * (sv.get("spacing0", 1.0) if lod == 0 else 1.8)
            sampler = scalp_points if fill and r_coil else sample_roots
            roots = keep(sampler(H, mask, sv["spacing"] * sk, seed * 10 + li))
            if len(roots) == 0:
                continue
            lens = short_lengths(H, sv, roots, seed * 10 + li)
            if fl == 0.0 and sv.get("whorl"):              # the inner layer: a few short ones over the whorl's middle
                n_w, r0, r1, L_w = sv["whorl"]
                top = float(H.co[:, 2].max())
                c = H.nearest_skin(np.array([0.0, H.cy + sv["crown"][0], top - sv["crown"][1]]))[0]
                rng_w = np.random.default_rng(seed + 57)
                pts = []
                for k in range(n_w):
                    a = 2 * math.pi * k / n_w + rng_w.uniform(-0.3, 0.3)
                    q = c + np.array([math.cos(a), math.sin(a), 0.0]) * rng_w.uniform(r0, r1)
                    pts.append(H.nearest_skin(q)[0])
                roots = np.vstack([roots, pts])
                lens = np.r_[lens, rng_w.uniform(0.6, 1.0, n_w) * L_w]
            vol = (max(sv["volume"][0] + fl, 0.0) + r_coil, max(sv["volume"][1] + fl, 0.0) + r_coil)
            turn = None
            if r_coil:
                turn = np.radians(np.random.default_rng(seed * 10 + li + 3).uniform(-1, 1, len(roots)) * sv["turn"])
            strands = grow_short(H, roots, lens, vol, flow, root_clear, fringe_z=sv["fringe_z"], seed=seed * 10 + li,
                                 hem=sv.get("hem"), gather=gather, turn=turn)
            if fill and r_coil:
                laid += [_on_scalp(H, S) for S in strands]
            layer_k = li / max(len(layers) - 1, 1)
        else:                                           # `fill`: curls where the layers left the cap bare, as the
            sk, fl, wk, cols, r_coil = layers[0]        # inner layer's
            vol = (sv["volume"][0] + r_coil, sv["volume"][1] + r_coil)
            turns = np.radians(np.random.default_rng(seed * 10 + li + 3).uniform(-1, 1, 1000) * sv["turn"])

            def grow1(r, k):
                L = short_lengths(H, sv, r[None], seed * 1000 + k)[0]
                return grow_short(H, r[None], [L], vol, flow, root_clear, fringe_z=sv["fringe_z"], seed=seed + k,
                                  hem=sv.get("hem"), turn=turns[k:k + 1])[0]
            cand = keep(scalp_points(H, mask, 0.004, seed * 10 + li))
            roots, strands = fill_gaps(H, cand, np.vstack(laid), grow1, sv["fill"])
            if len(roots) == 0:
                continue
            layer_k = 0.0
        rng = np.random.default_rng(seed * 100 + li)
        ids = hum_styles.coherent_ids(roots, seed)
        cc = [cols[int(rng.integers(len(cols)))] for _ in strands]
        face = hum_drape.front_of(H, roots) * ss(H.eye_z + 0.08, H.eye_z + 0.03, roots[:, 2])
        W = [sv["width"] * wk * rng.uniform(0.85, 1.15) * (1.0 if lod == 0 else 1.6) * (1.0 - 0.4 * f) for f in face]
        if gather is not None:                          # pressed together on the way to the tie
            W = [lambda t, w=w: w * (0.8 + 0.2 * ss(0.0, 0.15, t)) * (1.0 - 0.6 * t) for w in W]
        if r_coil:
            pitch, per0, per1 = sv["coil"]
            per_turn = per0 if lod == 0 else per1
            wound = [coil(H, S, r_coil, pitch, seed=seed * 1000 + li * 100 + k, flat=0.0 if lod == 0 else 0.6)
                     for k, S in enumerate(strands)]
            strands = [c for c, _ in wound]
            W = [pitch * wk * rng.uniform(0.85, 1.15) * (1.0 - 0.3 * f) for f in face]
            # not simulated (guides -2, as a bun's): a curl reaches 4 cm, but wound its path is 15 cm - past the
            # sim's short-hair cut, 4k particles that never swung visibly (and one curl strayed 5 cm)
            p, g, _ = cards_part(H, strands, W, ids, cc, layer_k, guide0=npart,
                                 row_len=2 * math.pi * r_coil / per_turn, max_rows=40 if lod == 0 else 20,
                                 root_sink=0.0, curve=sv.get("curve", 0.08), v0=sv.get("v0", 0.0),
                                 normal_fns=[_facing(c, f) for c, f in wound])
            parts.append(p)
            guides += [(-3.0, gy) for _, gy in g]       # out of the sim, and the shader lights them as a curl
            continue
        p, g, npart = cards_part(H, strands, W, ids, cc, layer_k, guide0=npart,
                                 row_len=0.008 if lod == 0 else 0.02, bend=0.02, max_rows=12 if lod == 0 else 6,
                                 root_sink=0.0, dip_len=0.02, curve=sv.get("curve", 0.08), v0=sv.get("v0", 0.0))
        parts.append(p)
        guides += g
    if "tail" in st:
        tparts, tg, npart = tail_parts(H, st, seed, lod, guide0=npart)
        parts += tparts
        guides += tg
    if "bun" in st:
        bparts, bg = bun_parts(H, st, seed, lod)
        parts += bparts
        guides += bg
    return parts, guides, npart


def scalp_points(H, mask, spacing, seed=0, thresh=0.6):
    """Blue-noise points anywhere on the scalp. `sample_roots` picks among the head's vertices, sparse over the skull:
    no spacing, however small, roots a curl between them."""
    tris = np.array([(q.vertices[0], q.vertices[k], q.vertices[k + 1]) for q in H.head.data.polygons
                     if q.material_index == 0 for k in range(1, len(q.vertices) - 1)])
    A, B, C = H.co[tris[:, 0]], H.co[tris[:, 1]], H.co[tris[:, 2]]
    area = np.linalg.norm(np.cross(B - A, C - A), axis=1)
    rng = np.random.default_rng(seed)
    n = int(area.sum() / 2 / spacing ** 2 * 6)
    pick = rng.choice(len(tris), n, p=area / area.sum())
    u, v = rng.random(n), rng.random(n)
    over = u + v > 1.0
    u[over], v[over] = 1.0 - u[over], 1.0 - v[over]
    P = A[pick] + (B - A)[pick] * u[:, None] + (C - A)[pick] * v[:, None]
    P = P[mask(P) > thresh]
    out = np.empty((len(P), 3))
    m = 0
    for q in P:
        if m == 0 or ((out[:m] - q) ** 2).sum(1).min() >= spacing ** 2:
            out[m] = q
            m += 1
    return out[:m]


def _on_scalp(H, P, step=0.002):
    """A path's points dropped onto the scalp, `step` m apart."""
    P = np.asarray(P, float)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t = np.r_[np.arange(0.0, arc[-1], step), arc[-1]]
    A = np.stack([np.interp(t, arc, P[:, c]) for c in range(3)], 1)
    return np.array([H.nearest(a)[0] for a in A])


def fill_gaps(H, cand, laid, grow1, gap, most=400):
    """Curls for the cap the layers left bare: of the candidate roots `cand` (on the scalp), the one farthest from
    every laid path (`laid`: points on the scalp) roots a curl - `grow1(root, k)` lays its path, which counts from
    then on - until none is `gap` m from one (or `most` curls). Coils along flow lines fan apart from the whorl and
    leave channels between them that more of the same, evenly spread, only narrowed. Returns (roots, paths)."""
    d = np.empty(len(cand))
    for i in range(0, len(cand), 64):
        d[i:i + 64] = np.sqrt(((cand[i:i + 64, None, :] - laid[None]) ** 2).sum(-1).min(1))
    roots, paths = [], []
    while len(roots) < most:
        i = int(np.argmax(d))
        if d[i] < gap:
            break
        P = grow1(cand[i], len(roots))
        S = _on_scalp(H, P)
        d = np.minimum(d, np.sqrt(((cand[:, None, :] - S[None]) ** 2).sum(-1)).min(1))
        d[i] = 0.0
        roots.append(cand[i])
        paths.append(P)
    return np.array(roots), paths


def coil(H, S, r, pitch, seed=0, grow=0.008, flat=0.0):
    """A strand wound into a ringlet round its path S (lying on the head): radius r (m), a turn every `pitch` m of the
    path, either hand, the radius growing in over the first `grow` m (it leaves the scalp from its root). Returns the
    coil (1 mm steps along the path) and each point's facing: out from the path - its card wraps the ringlet, a
    spiral band with its strands running round it. `flat` bends the facing toward the scalp's normal (LOD1: a coil
    of few, big facets lit round its path showed its underside as a dark speck)."""
    S = np.asarray(S, float)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))]
    t = np.r_[np.arange(0.0, arc[-1], 0.001), arc[-1]]
    A = np.stack([np.interp(t, arc, S[:, c]) for c in range(3)], 1)
    T = _unit(np.gradient(A, axis=0))
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0.0, 2 * math.pi)
    hand = rng.choice([-1.0, 1.0])
    C, F = [], []
    for a, tt, s in zip(A, T, t):
        _, n, _ = H.nearest(a)
        n = _unit(n - tt * np.dot(n, tt))
        out = n * math.cos(ph + hand * 2 * math.pi * s / pitch) + np.cross(tt, n) * math.sin(
            ph + hand * 2 * math.pi * s / pitch)
        C.append(a + out * r * ss(0.0, grow, s))
        F.append(_unit(out * (1.0 - flat) + n * flat))
    return np.array(C), np.array(F)


def _facing(C, F):
    """p -> the facing of the coil C's point nearest p (cards_part resamples the spine)."""
    return lambda p: F[int(np.argmin(((C - p) ** 2).sum(1)))]


def bun_parts(H, st, seed=0, lod=0, turns=3.0, phi=(-0.25, 1.3)):
    """A bun: the hair coiled round on itself at the tie - cards wound in interleaved spirals over a squat dome, from
    its foot (on the scalp's hair, which stops under it) up to its top, where they close in a rosette; under them a
    core shell (drawn like the cap) so nothing shows through. The old clump bun was a ball of random great circles.
    It doesn't swing: its cards' guides are -2 (skinned to the head, not simulated, drawn as cards - Humans/HairCards).
    `phi`: the dome's latitude at the foot and the top (rad). Returns (parts, per-loop guides)."""
    bv = st["bun"]
    r = bv["radius"]
    h = r * bv.get("height", 0.75)
    rng = np.random.default_rng(seed * 7 + 5)
    loc, n, _ = H.nearest(np.array(st["tie"]) + np.array([0, H.cy, H.eye_z]))
    c = loc + n * 0.005
    e1 = _unit(np.cross(n, [0.0, 0.0, 1.0]))
    e2 = np.cross(n, e1)
    p0, p1 = phi

    def at(t, ph, k=1.0):
        a = ph + 2 * math.pi * turns * t
        f = p0 + (p1 - p0) * t
        return c + n * (h * (math.sin(f) - math.sin(p0)) * k) + (e1 * math.cos(a) + e2 * math.sin(a)) * r * math.cos(f) * k

    mid = c + n * h * 0.4
    facing = lambda q: _unit(q - mid)
    spirals = 3 if lod == 0 else 2
    per = 0.7 if lod == 0 else 1.0                    # turns a card
    pitch = (p1 - p0) / turns * math.hypot(r, h)      # between one spiral's passes, over the dome (m)
    spines, widths, ids, cols, nfns = [], [], [], [], []
    for k in range(spirals):
        ph = 2 * math.pi * k / spirals
        t = -rng.uniform(0.0, per) / turns            # staggered card ends
        while t < 1.0:
            t1 = min(t + per / turns * rng.uniform(0.9, 1.1), 1.0)
            ts = np.linspace(max(t, 0.0), t1, 24)
            if ts[-1] - ts[0] > 0.05 / turns:
                spines.append(np.array([at(x, ph) for x in ts]))
                widths.append(pitch / spirals * 2.6 * rng.uniform(0.9, 1.1))
                ids.append(float(rng.random()))
                cols.append((0, 1, 2, 3, 4, 5)[int(rng.integers(6))])
                nfns.append(facing)
            t = t1
    cards, g, _ = cards_part(H, spines, widths, ids, cols, 1.0, guide0=0, row_len=0.012 if lod == 0 else 0.03,
                             curve=0.05, root_sink=0.0, normal_fns=nfns, max_rows=16 if lod == 0 else 8)
    g = [(-2.0, sv) for _, sv in g]
    # the core: the dome a little inside the coil, open at its very top (the rosette covers it)
    core = Part()
    NU, NV = (16, 6) if lod == 0 else (10, 4)
    for i in range(NU):
        for j in range(NV):
            f = p0 + (min(p1 + 0.15, 1.45) - p0) * j / (NV - 1)
            a = 2 * math.pi * i / NU
            radial = e1 * math.cos(a) + e2 * math.sin(a)
            core.verts.append(c + n * h * (math.sin(f) - math.sin(p0)) * 0.9 + radial * r * math.cos(f) * 0.9)
            core.normals.append(_unit(radial * math.cos(f) + n * math.sin(f)))
            core.edge.append(0.0)
    for i in range(NU):
        for j in range(NV - 1):
            q = [i * NV + j, ((i + 1) % NU) * NV + j, ((i + 1) % NU) * NV + j + 1, i * NV + j + 1]
            core.faces.append(tuple(q))
            for (ii, jj) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                core.uv0.append((ii / NU * 6.0, jj / NV * 1.5))
                core.uv1.append((1.0, 1.7))             # past 1: a light shell (as a short style's)
    core.verts = np.array(core.verts)
    core.layer = [0.5] * len(core.verts)
    return [cards, core], g + [(-1.0, 0.0)] * len(core.uv0)


def draped_parts(H, name, seed=0, lod=0):
    """The recipe's cap, then each layer's cards along draped strands (hum_drape). Returns (parts, guides, particles)."""
    import hum_drape
    dv = DRAPED[name]
    st = hum_styles.HAIR[STYLES[name]]
    mask = hum_styles.hair_mask_fn(H, st)
    cap = cap_part(H, mask, st["cap"], subdiv=1 if lod == 0 else 0, ratio=1.0 if lod == 0 else 0.5)
    cap.layer = [0.0] * len(cap.verts)
    if dv.get("cap_light"):                         # past 1: the shader lightens the shell (as a short style's)
        cap.uv1 = [(u, 1.0 + dv["cap_light"]) for u, _ in cap.uv1]
    parting(H, cap, dv.get("part_x", 0.0))
    parts = [cap]
    guides = cap_guides(cap)
    npart = 0
    facing = hum_drape.card_normal_fn(H)
    layers = draped_strands(H, name, seed, lod)
    for li, (strands, roots, (sk, fl, wk, cols)) in enumerate(layers):
        rng = np.random.default_rng(seed * 100 + li)
        ids = hum_styles.coherent_ids(roots, seed)
        cc = [cols[int(rng.integers(len(cols)))] for _ in strands]
        # narrower beside the face (low and ahead on the head; by angle round the head the crown's widths came out
        # at random)
        face = hum_drape.front_of(H, roots) * ss(H.eye_z + 0.08, H.eye_z + 0.03, roots[:, 2])
        W = [dv["width"] * wk * rng.uniform(0.85, 1.15) * (1.0 if lod == 0 else 1.6) * (1.0 - 0.4 * f) for f in face]
        p, g, npart = cards_part(H, strands, W, ids, cc, li / max(len(layers) - 1, 1), guide0=npart,
                                 row_len=0.015 if lod == 0 else 0.04, bend=0.03, max_rows=30 if lod == 0 else 16,
                                 normal_fns=[facing] * len(strands), root_sink=0.0, dip_len=0.05)
        parts.append(p)
        guides += g
    return parts, guides, npart


def build(scene, H, name, seed=0, lod=0):
    """One spike piece (Hair_<name>[_L<lod>]) in HUM_Hair: the mesh, its HairData layer colour and Guide UVs are
    kept aside for write_guides (CapCut/HoodCut must come first: UV channels 2 and 3)."""
    parts, guides, npart = (draped_parts(H, name, seed, lod) if name in DRAPED
                            else short_parts(H, name, seed, lod) if name in SHORT
                            else stand_parts(H, name, seed, lod) if name in STAND
                            else beard_card_parts(H, name, seed, lod) if name in BEARD_CARDS
                            else style_parts(H, STYLES[name], seed, lod))
    obname = ("Beard_" if name in BEARD_CARDS else "Hair_") + name + ("" if lod == 0 else f"_L{lod}")
    me = hum_hair.mesh_from_parts(obname, parts)
    lay = np.concatenate([np.asarray(p.layer, np.float32) for p in parts if len(p.verts)])
    col = me.color_attributes["HairData"]
    c = np.empty(len(me.vertices) * 4, np.float32)
    col.data.foreach_get("color", c)
    c = c.reshape(-1, 4)
    c[:, 1] = lay
    col.data.foreach_set("color", c.ravel())
    g = np.array(guides, np.float32)
    assert len(g) == len(me.loops), (len(g), len(me.loops))
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    gv = np.zeros((len(me.vertices), 2), np.float32)
    gv[vi] = g                                        # a vertex's loops all carry its row's particle
    at = me.attributes.new("hair_guide", 'FLOAT2', 'POINT')     # a corner FLOAT2 would be a UV map (channel order)
    at.data.foreach_set("vector", gv.ravel())
    pa = np.concatenate([np.asarray(getattr(p, "parting", None) if getattr(p, "parting", None) is not None
                                    else np.full(len(p.verts), 99.0), np.float32) for p in parts if len(p.verts)])
    me.attributes.new("hair_part", 'FLOAT', 'POINT').data.foreach_set("value", pa)
    ob = hum_hair.replace_object(scene, obname, me)
    ob["hum_kind"] = "hair"
    ob["hum_lod"] = lod
    ob["hum_particles"] = npart
    return ob


def write_guides(ob):
    """The Guide UV (channel 4) from the hair_guide corner attribute, after CapCut and HoodCut."""
    me = ob.data
    at = me.attributes.get("hair_guide")
    if at is None:
        return
    g = np.empty(len(me.vertices) * 2, np.float32)
    at.data.foreach_get("vector", g)
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    lay = me.uv_layers.get("Guide") or me.uv_layers.new(name="Guide")
    lay.data.foreach_set("uv", g.reshape(-1, 2)[vi].ravel())
    pa = me.attributes.get("hair_part")
    if pa is not None and "HoodCut" in me.uv_layers:           # HoodCut.y: the parting (Humans/HairCards)
        v = np.empty(len(me.vertices), np.float32)
        pa.data.foreach_get("value", v)
        hc = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers["HoodCut"].data.foreach_get("uv", hc)
        hc = hc.reshape(-1, 2)
        hc[:, 1] = v[vi]
        me.uv_layers["HoodCut"].data.foreach_set("uv", hc.ravel())
    me.uv_layers.active = me.uv_layers["UVMap"]
    names = [u.name for u in me.uv_layers]
    assert names[:5] == ["UVMap", "Clump", "CapCut", "HoodCut", "Guide"], names


def material(name="M_HumanHairCards"):
    """Blender preview of Humans/HairCards: root/tip/streak colour x atlas shade, atlas coverage as alpha (the cap
    opaque, on the old strand texture), an anisotropic sheen along the strands (tangent from the atlas UVs)."""
    import hum_material
    atlas = bpy.data.images.get(ATLAS) or build_atlas()
    strands = bpy.data.images.get("T_Hair_Strands") or hum_paint.strand_texture()
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = hum_material._NT(mat)
    uv0 = T.node('ShaderNodeUVMap'); uv0.uv_map = "UVMap"
    tex = T.node('ShaderNodeTexImage'); tex.image = atlas
    tex.image.colorspace_settings.name = 'Non-Color'
    T.link(uv0.outputs['UV'], tex.inputs['Vector'])
    old = T.node('ShaderNodeTexImage'); old.image = strands
    T.link(uv0.outputs['UV'], old.inputs['Vector'])
    guv = T.node('ShaderNodeUVMap'); guv.uv_map = "Guide"
    gx, _, _ = T.split(guv.outputs['UV'])
    cap = T.math('LESS_THAN', gx, -0.5)                       # the cap shell
    sep = T.node('ShaderNodeSeparateColor')
    T.link(tex.outputs['Color'], sep.inputs[0])
    shade = T.mix(sep.outputs[0], old.outputs['Color'], cap)
    uvc = T.node('ShaderNodeUVMap'); uvc.uv_map = "Clump"
    rid, t, _ = T.split(uvc.outputs['UV'])
    root, tip, streak = (T.attr(k) for k in ("hum_hair_root", "hum_hair_tip", "hum_hair_streak"))
    streaks, ombre = T.attr("hum_streaks", False), T.attr("hum_ombre", False)
    cuv = T.node('ShaderNodeUVMap'); cuv.uv_map = "CapCut"
    cc, olen, _ = T.split(cuv.outputs['UV'])
    mr = T.node('ShaderNodeMapRange'); mr.interpolation_type = 'SMOOTHSTEP'
    mr.inputs['From Min'].default_value = 0.25
    T.link(olen, mr.inputs['Value'])
    c = T.mix(root, tip, T.math('MULTIPLY', mr.outputs['Result'], ombre))
    c = T.mix(c, streak, T.math('LESS_THAN', rid, streaks))
    c = T.mul(c, shade)
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.42
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    if 'Anisotropic' in bsdf.inputs:
        bsdf.inputs['Anisotropic'].default_value = 0.85
        tg = T.node('ShaderNodeTangent'); tg.direction_type = 'UV_MAP'; tg.uv_map = "UVMap"
        T.link(tg.outputs['Tangent'], bsdf.inputs['Tangent'])
        bsdf.inputs['Anisotropic Rotation'].default_value = 0.25    # along v (the strands), not u
    T.link(c, bsdf.inputs['Base Color'])
    alpha = T.math('MAXIMUM', T.math('GREATER_THAN', tex.outputs['Alpha'], 0.5), cap)
    cut = T.attr("hum_capcut", False)
    hidden = T.math('MULTIPLY', T.math('GREATER_THAN', cut, 0.0), T.math('GREATER_THAN', cc, cut))
    huv = T.node('ShaderNodeUVMap'); huv.uv_map = "HoodCut"
    hc, _, _ = T.split(huv.outputs['UV'])
    hood = T.math('MULTIPLY', T.attr("hum_hoodcut", False), T.math('GREATER_THAN', hc, 0.0))
    hidden = T.math('MAXIMUM', hidden, hood)
    T.link(T.math('MULTIPLY', alpha, T.math('SUBTRACT', 1.0, hidden)), bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


# ------------------------------------------------------------------ the spike's gallery (Blender side)

GALLERY_SCENE = "HairCards"
VIEWS = {"front": (0, -1, 0.1), "34": (0.75, -0.75, 0.15), "side": (1, 0, 0.05), "back": (0, 1, 0.1),
         "back34": (-0.7, 0.7, 0.3), "below": (0.3, -0.6, -0.75), "top": (0.25, 0.35, 1.0)}


def gallery_scene(pairs):
    """Scene HairCards: per piece, a collection with the Head, the Body and the piece, as a collection instance at the
    origin under the Faces scene's lights (the gallery shows one at a time: the same light for old and new)."""
    faces = bpy.data.scenes["Faces"]
    sc = bpy.data.scenes.get(GALLERY_SCENE) or bpy.data.scenes.new(GALLERY_SCENE)
    sc.world = faces.world
    sc.render.engine = faces.render.engine
    for n in ("Key", "Fill", "Rim"):
        o = bpy.data.objects.get(n)
        if o is not None and o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
    for o in list(sc.collection.objects):
        if o.type == 'EMPTY' and o.name.startswith("HC_"):
            bpy.data.objects.remove(o)
    for c in [c for c in bpy.data.collections if c.name.startswith("HC_")]:
        bpy.data.collections.remove(c)
    for old, new in pairs:
        for k, piece in enumerate((old, new)):
            col = bpy.data.collections.new("HC_" + piece)
            for n in ("Head", "Body", piece):
                col.objects.link(bpy.data.objects[n])
            e = bpy.data.objects.new("HC_" + piece, None)
            e.instance_type = 'COLLECTION'
            e.instance_collection = col
            e.hide_render = True
            sc.collection.objects.link(e)
            bpy.data.objects[piece].hide_set(False)
            bpy.data.objects[piece].hide_render = False
            bpy.data.objects[piece].hide_viewport = False
    cam = bpy.data.objects.get("HC_Cam_Obj")
    if cam is None:
        cam = bpy.data.objects.new("HC_Cam_Obj", bpy.data.cameras.new("HC_Cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    return sc


def gallery(pairs=(("Hair_Long", "Hair_LongStrands"),), views=("front", "34", "side", "back", "below"), res=420,
            path=None, dist=0.62):
    """Renders every view of each pair (old | new) into one sheet: renders/hair_cards_gallery.png."""
    import mathutils
    sc = gallery_scene(pairs)
    head = bpy.data.objects["Head"]
    body = bpy.data.objects["Body"]
    hide = body.get("hum_hide", 0.0)
    body["hum_hide"] = 0.0                            # the bare body (the Faces scene keeps its clothes test)
    for old, new in pairs:
        for k in ("hum_hair_root", "hum_hair_tip", "hum_hair_streak", "hum_streaks", "hum_ombre"):
            bpy.data.objects[new][k] = bpy.data.objects[old][k]
    V = np.array([v.co[:] for v in head.data.vertices])
    c0 = np.array(((V[:, 0].min() + V[:, 0].max()) / 2, V[:, 1].mean() + 0.02, V[:, 2].mean() - 0.02))
    cam = sc.camera
    cam.data.lens = 50
    sc.render.resolution_x = res
    sc.render.resolution_y = res
    sc.render.film_transparent = False
    rows = []
    tmp = os.path.join(hum_paint.ROOT, "renders", "_tmp", "hc_view.png")
    for pi, pair in enumerate(pairs):
        for k, piece in enumerate(pair):
            for e in sc.collection.objects:
                if e.name.startswith("HC_") and e.type == 'EMPTY':
                    e.hide_render = e.name != "HC_" + piece
            row = []
            for v in views:
                d = _unit(np.array(VIEWS[v], float))
                c = c0
                cam.location = mathutils.Vector(c + d * dist)
                cam.rotation_euler = mathutils.Vector(-d).to_track_quat('-Z', 'Y').to_euler()
                sc.render.filepath = tmp
                bpy.ops.render.render(write_still=True, scene=sc.name)
                img = bpy.data.images.load(tmp, check_existing=False)
                P = np.array(img.pixels[:]).reshape(res, res, 4)
                bpy.data.images.remove(img)
                row.append(P)
            rows.append(np.concatenate(row, 1))
    body["hum_hide"] = hide
    S = np.concatenate(rows[::-1], 0)                 # first pair's old row on top
    path = path or os.path.join(hum_paint.ROOT, "renders", "hair_cards_gallery.png")
    hum_paint.save_image("_hc_gallery", S, path, colorspace='sRGB')
    return path


BODY_BONES = ("neck_01", "spine_03", "spine_02", "clavicle_l", "clavicle_r")


def draped_weights(ob, sk, arm):
    """hum_hair.hair_weights, then where the hair lies on the body below the neck it takes the body's own weights there
    (neck, upper spine, clavicles - not the arms; at most 4 bones), faded in by how close it lies. Rigid on spine_03,
    hair down the back let the shoulder blade push the shirt through it on the side the arm swung back (skinned, no
    sim: the colony camera sees backs)."""
    import bpy
    from mathutils.kdtree import KDTree
    W = hum_hair.hair_weights(ob, sk, arm)
    body = bpy.data.objects.get("Body")
    if body is None:
        return W
    me = ob.data
    kb = me.shape_keys.key_blocks[0] if me.shape_keys else None
    co = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in me.vertices])
    bm = body.data
    bkb = bm.shape_keys.key_blocks[0] if bm.shape_keys else None
    bco = np.array([d.co[:] for d in bkb.data]) if bkb else np.array([v.co[:] for v in bm.vertices])
    names = {g.index: g.name for g in body.vertex_groups}
    cols = {n: sk.index[n] for n in BODY_BONES if n in sk.index}
    BW = np.zeros((len(bco), len(sk.bones)))
    for v in bm.vertices:
        for g in v.groups:
            n = names.get(g.group)
            if n in cols:
                BW[v.index, cols[n]] += g.weight
    tot = BW.sum(1)
    kd = KDTree(len(bco))
    for k, p in enumerate(bco):
        if tot[k] > 0.2:                                    # a vertex these bones mostly carry (not the arm's)
            kd.insert(p, k)
    kd.balance()
    z_neck = float(arm.data.bones["neck_01"].head_local[2])
    for i, p in enumerate(co):
        below = hum_paint.smoothstep(z_neck, z_neck - 0.06, p[2])
        if below <= 0:
            continue
        _, k, d = kd.find(p)
        if k is None:
            continue
        f = below * hum_paint.smoothstep(0.08, 0.045, d)      # a wider fade (0.15 m, 0.12 m down) let more shirt through
        if f <= 0:
            continue
        bw = BW[k] / max(BW[k].sum(), 1e-9)
        W[i] = W[i] * (1 - f) + bw * f
    # a card row moves as one (its edges took different bones - up to 0.8 apart - and sheared the card)
    at = me.attributes.get("hair_guide")
    if at is not None:
        g = np.empty(len(co) * 2, np.float32)
        at.data.foreach_get("vector", g)
        pid = np.round(g[0::2]).astype(int)
        rows = pid >= 0
        if rows.any():
            n = pid.max() + 1
            cnt = np.maximum(np.bincount(pid[rows], minlength=n), 1)
            M = np.stack([np.bincount(pid[rows], weights=W[rows, b], minlength=n) for b in range(W.shape[1])], 1)
            W[rows] = (M / cnt[:, None])[pid[rows]]
    keep = np.argsort(-W, axis=1)[:, :4]                     # Unity skins with 4 bones
    W4 = np.zeros_like(W)
    np.put_along_axis(W4, keep, np.take_along_axis(W, keep, 1), 1)
    return W4 / np.maximum(W4.sum(1, keepdims=True), 1e-9)


def draped_keys(ob, H, near_head=(0.015, 0.04), near_body=(0.025, 0.06), eps=5e-4):
    """The shape keys of draped hair, after hum_hair.bind_keys (the head's keys by Surface Deform). That bind holds
    near the head only: 20 cm down, the head's Feminine / Thin / Slight carried the front locks 3 cm back into the
    chest (inside it on every female build). Per card row (its Guide particle), root -> tip:
      on the head   its own bound delta;
      hanging free  the last on-head row's delta carried on (the hair hangs from the head as it moves);
      on the body   the body's own key delta at the nearest point (shoulders, chest, back; keys the head lacks -
                    Bust, Traps, ChestMuscle... - are added for that), face keys none.
    Blends by the row's distance from the head (`near_head`: full .. none, m) and from the body (`near_body`)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    me = ob.data
    if not me.shape_keys:
        return 0
    body = bpy.data.objects["Body"]
    bkb = body.data.shape_keys.key_blocks
    bbase = np.array([d.co[:] for d in bkb[0].data])
    bpolys = [tuple(p.vertices) for p in body.data.polygons]
    bvh = BVHTree.FromPolygons([tuple(p) for p in bbase], bpolys)
    kb = me.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kb[0].data])
    g = np.empty(len(base) * 2, np.float32)
    me.attributes["hair_guide"].data.foreach_get("vector", g)
    g = g.reshape(-1, 2)
    npart = int(g[:, 0].max()) + 1
    if npart <= 0:
        return 0
    pid = np.round(g[:, 0]).astype(int)
    rows = pid >= 0
    cnt = np.bincount(pid[rows], minlength=npart).astype(float)
    centre = np.stack([np.bincount(pid[rows], weights=base[rows, c], minlength=npart) for c in range(3)], 1)
    centre /= np.maximum(cnt, 1)[:, None]
    s = np.zeros(npart)
    s[pid[rows]] = g[rows, 1]
    root = np.r_[True, s[1:] <= s[:-1] + 1e-6]                 # a card's first row (rows run root -> tip)
    wh = np.empty(npart)
    wb = np.empty(npart)
    corners, cw = [], []
    for p in range(npart):
        _, _, dh = H.nearest_skin(centre[p])
        wh[p] = 1.0 - ss(near_head[0], near_head[1], dh)
        loc, _, fi, db = bvh.find_nearest(Vector(centre[p]))
        wb[p] = 1.0 - ss(near_body[0], near_body[1], db)
        ids = bpolys[fi]
        dist = np.linalg.norm(bbase[list(ids)] - np.array(loc), axis=1) + 1e-6
        corners.append(ids)
        cw.append((1.0 / dist) / (1.0 / dist).sum())
    wb *= 1.0 - wh                                             # the head wins where both are near (the nape)

    def body_delta(name):
        if name not in bkb:
            return None
        D = np.array([d.co[:] for d in bkb[name].data]) - bbase
        return np.array([(D[list(c)] * w[:, None]).sum(0) for c, w in zip(corners, cw)])

    names = [k.name for k in kb[1:]]
    for k in bkb[1:]:                                          # body keys the head lacks
        if k.name not in names:
            bd = body_delta(k.name)
            if np.abs(bd * wb[:, None]).max() > eps:
                ob.shape_key_add(name=k.name, from_mix=False).slider_min = -1.0
                names.append(k.name)
    kb = me.shape_keys.key_blocks
    for name in names:
        k = kb[name]
        D = np.array([d.co[:] for d in k.data]) - base
        hd = np.stack([np.bincount(pid[rows], weights=D[rows, c], minlength=npart) for c in range(3)], 1)
        hd /= np.maximum(cnt, 1)[:, None]
        bd = body_delta(name)
        bd = np.zeros_like(hd) if bd is None else bd
        free = np.empty_like(hd)
        carried = hd[0]
        for p in range(npart):
            carried = hd[p] if root[p] else wh[p] * hd[p] + (1 - wh[p]) * carried
            free[p] = wb[p] * bd[p] + (1 - wb[p]) * carried
        out = D.copy()
        r = np.where(rows)[0]
        whv = wh[pid[r]][:, None]
        out[r] = whv * D[r] + (1 - whv) * free[pid[r]]
        k.data.foreach_set("co", (base + out).astype(np.float32).ravel())
    return len(names)


# tag -> (body, shirt) distance grids in that build's space (slow: kept over a module reload)
_BUILD_FIELDS = globals().get("_BUILD_FIELDS", {})


def _build_fields(H, tag, sk):
    import hum_builds
    import hum_drape
    import hum_rig
    if tag in _BUILD_FIELDS:
        return _BUILD_FIELDS[tag]
    from mathutils.bvhtree import BVHTree
    keys = hum_builds.BUILDS[tag]["keys"]
    dJ = hum_builds.joint_offsets(keys, sk)
    top = H.co[:, 2].max()
    lo = (-0.3, H.cy - 0.2, top - 0.72)
    hi = (0.3, H.cy + 0.3, top + 0.02)
    body = bpy.data.objects["Body"]
    kbs = body.data.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kbs[0].data])
    S = base.copy()
    for k, w in keys.items():
        if k in kbs:
            S += w * (np.array([d.co[:] for d in kbs[k].data]) - base)
    S += hum_rig.weights_of(body, sk) @ dJ
    polys = [tuple(p.vertices) for p in body.data.polygons]
    fb = hum_drape.Field(BVHTree.FromPolygons([tuple(p) for p in S], polys), lo, hi)
    fs = None
    sh = bpy.data.objects.get("Cloth_Shirt_" + tag)
    if sh is not None:
        P = np.array([v.co[:] for v in sh.data.vertices])
        if sh.get("at_rest"):
            P = P + hum_rig.weights_of(sh, sk) @ dJ
        fs = hum_drape.Field(BVHTree.FromPolygons([tuple(p) for p in P], [tuple(p.vertices) for p in sh.data.polygons]),
                             lo, hi)
    _BUILD_FIELDS[tag] = (fb, fs)
    return _BUILD_FIELDS[tag]


def build_fit(ob, H, sk, body_gap=0.012, shirt_gap=0.005, iters=10, lam=1e-3, near_head=(0.015, 0.04), blur=0.025):
    """Draped hair fitted to every build (hum_builds.BUILDS), as the garments are, but through the body keys: per
    build its card rows (key offsets + bone moves) are pushed out of that build's body and shirt (lengths kept, rows
    on the head pinned), and the body keys' row offsets corrected (least squares, the smallest change) so each
    build's key mix puts the hair there. (By the nearest skin point alone, hair over the upper chest stayed on the
    skin, while a woman's shirt bridges collarbone to bust 2-3 cm out: the front locks hid under it.) The body keys
    are then blurred over `blur` m: each row pushed out of the shirt's folds on its own crumpled the tips.
    After skinning (the rows' bone weights). Returns the worst build's mean refit (m)."""
    import hum_builds
    import hum_drape
    import hum_rig
    me = ob.data
    kb = me.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kb[0].data])
    g = np.empty(len(base) * 2, np.float32)
    me.attributes["hair_guide"].data.foreach_get("vector", g)
    g = g.reshape(-1, 2)
    pid = np.round(g[:, 0]).astype(int)
    rows = pid >= 0
    npart = int(pid.max()) + 1
    if npart <= 0:
        return 0.0
    r_idx = np.where(rows)[0]
    cnt = np.maximum(np.bincount(pid[rows], minlength=npart), 1).astype(float)

    def row_mean(A):
        return np.stack([np.bincount(pid[rows], weights=A[rows, c], minlength=npart) for c in range(A.shape[1])], 1) \
            / cnt[:, None]
    C = row_mean(base)
    Wv = hum_rig.weights_of(ob, sk)
    Wr = row_mean(Wv)
    s = np.zeros(npart)
    s[pid[rows]] = g[rows, 1]
    root = np.r_[True, s[1:] <= s[:-1] + 1e-6]
    seg = np.r_[0.0, np.linalg.norm(np.diff(C, axis=0), axis=1)]
    seg[root] = 0.0
    wh = np.array([1.0 - ss(near_head[0], near_head[1], H.nearest_skin(c)[2]) for c in C])
    pinned = wh > 0.5
    tags = list(hum_builds.BUILDS)
    used = sorted({k for t in tags for k in hum_builds.BUILDS[t]["keys"]})
    have = {k.name for k in kb}
    for k in used:
        if k not in have:
            ob.shape_key_add(name=k, from_mix=False).slider_min = -1.0
    kb = me.shape_keys.key_blocks
    Dk = {k: row_mean(np.array([d.co[:] for d in kb[k].data]) - base) for k in used}
    Wb = np.array([[hum_builds.BUILDS[t]["keys"].get(k, 0.0) for k in used] for t in tags])     # builds x keys
    R = np.zeros((len(tags), npart, 3))
    worst = 0.0
    for bi, t in enumerate(tags):
        keys = hum_builds.BUILDS[t]["keys"]
        dJ = hum_builds.joint_offsets(keys, sk)
        move = Wr @ dJ
        pred = sum(w * Dk[k] for k, w in keys.items() if k in Dk)
        X = C + pred + move
        fb, fs = _build_fields(H, t, sk)
        union = hum_drape._Union(fb, body_gap, fs, shirt_gap) if fs is not None else hum_drape._Union(fb, body_gap, fb, body_gap)
        for _ in range(iters):
            d, nrm = union.sample(X)
            push = np.maximum(-d, 0.0) * (d > -0.08) * ~pinned
            X = X + nrm * push[:, None]
            for p in range(npart):                      # lengths, root -> tip (pinned rows stay)
                if root[p] or pinned[p]:
                    continue
                v = X[p] - X[p - 1]
                X[p] = X[p - 1] + v / max(np.linalg.norm(v), 1e-9) * seg[p]
        R[bi] = X - move - C - pred
        worst = max(worst, float(np.linalg.norm(R[bi], axis=1)[~pinned].mean()))
    # the smallest key corrections that give every build its residual: dK = Wb^T (Wb Wb^T + lam I)^-1 R
    A = Wb.T @ np.linalg.inv(Wb @ Wb.T + lam * np.eye(len(tags)))
    dK = np.einsum("kb,bpc->kpc", A, R)
    for ki, k in enumerate(used):
        if np.abs(dK[ki]).max() < 1e-5:
            continue
        D = np.array([d.co[:] for d in kb[k].data]) - base
        D[r_idx] += dK[ki][pid[r_idx]]
        kb[k].data.foreach_set("co", (base + D).astype(np.float32).ravel())
    hum_hair.smooth_keys_spatial(ob, radius=blur, names=set(used))
    for k in [k for k in kb[1:] if k.name in used]:          # keys added above that still move nothing
        if np.abs(np.array([d.co[:] for d in k.data]) - base).max() < 1e-5:
            ob.shape_key_remove(k)
    return worst


def lod2_copy(sc, name):
    """LOD2 (the colony camera): a copy of the clump style's own LOD2 (cap + a few big clumps; strands don't read at
    40 m), drawn by the cards shader as cap (Guide x = -1: opaque, the old strand texture)."""
    src = bpy.data.objects["Hair_" + STYLES[name] + "_L2"]
    obname = f"Hair_{name}_L2"
    for stale in [o for o in bpy.data.objects if o.name == obname or o.name.startswith(obname + ".")]:
        bpy.data.objects.remove(stale)
    for stale in [m for m in bpy.data.meshes if (m.name == obname or m.name.startswith(obname + ".")) and m.users == 0]:
        bpy.data.meshes.remove(stale)                  # an orphan keeping the name pushed the copy to "_L2.001"
    tmp = src.copy()                                   # with its vertex groups, so clearing them clears the weights
    tmp.data = src.data.copy()
    tmp.vertex_groups.clear()
    me = tmp.data
    me.name = obname
    bpy.data.objects.remove(tmp)
    for lay in [u for u in me.uv_layers if u.name == "Guide"]:
        me.uv_layers.remove(lay)
    at = me.attributes.get("hair_guide") or me.attributes.new("hair_guide", 'FLOAT2', 'POINT')
    g = np.zeros(len(me.vertices) * 2, np.float32)
    g[0::2] = -1.0
    at.data.foreach_set("vector", g)
    # off any parting (HoodCut.y left at 0 reads as on it: the shader cut the whole shell away, a bald head at 40 m)
    me.attributes.new("hair_part", 'FLOAT', 'POINT').data.foreach_set("value", np.full(len(me.vertices), 99.0, np.float32))
    ob = hum_hair.replace_object(sc, obname, me)
    ob["hum_kind"] = "hair"
    ob["hum_lod"] = 2
    ob["hum_particles"] = 0
    return ob


def build_all(head=None, lods=(0, 1, 2), names=None):
    """Every spike piece: built, bound to the head keys (as the clump styles), CapCut/HoodCut, Guide, material,
    skinned (hum_hair.hair_weights: head -> neck_01 -> spine_03 by height, as the clump styles)."""
    import hum_build, hum_armor, hum_material, hum_rig
    head = head or bpy.data.objects["Head"]
    arm = bpy.data.objects["HumanRig"]
    hum_rig.rest(arm)
    sk = hum_rig.Skeleton(bpy.data.objects["MPFB_Source"])
    saved = {k.name: k.value for k in head.data.shape_keys.key_blocks}
    for k in head.data.shape_keys.key_blocks[1:]:
        k.value = 0.0
    H = hum_hair.HeadFrame(head)
    mat = material()
    sc = hum_build.scene()
    made = []
    for name in (names or list(STYLES) + list(BEARD_CARDS)):
        for lod in lods:
            own_l2 = name in STAND or name in BEARD_CARDS   # (a clump beard's LOD2 is its shell: a long beard gone)
            ob = lod2_copy(sc, name) if lod == 2 and not own_l2 else build(sc, H, name, lod=lod)
            hum_paint.set_materials(ob, [mat])
            nk, err = hum_hair.bind_keys(ob, head)
            if name not in BEARD_CARDS:                 # (beards keep exact keys, as the clump ones)
                hum_hair.smooth_keys_spatial(ob)
            if name in DRAPED and lod != 2:
                nk = draped_keys(ob, H)
            hum_material.set_hair_props(ob, (0.08, 0.05, 0.03))
            made.append(ob.name)
            print(f"{ob.name}: {hum_hair.tris(ob)} tris, {len(ob.data.vertices)} verts, "
                  f"{ob['hum_particles']} particles, {nk} keys")
    hum_armor.write_cap_coords(head, only=made)
    for n in made:
        ob = bpy.data.objects[n]
        write_guides(ob)
        base = n.split("_", 1)[1]
        base = base[:-3] if base[-3:-1] == "_L" else base      # (split("_L") cut "LongStrands" at "_Long")
        if base in BEARD_CARDS:
            hum_rig.rigid(ob, arm, sk, "head")
        else:
            hum_rig.skin(ob, arm, sk, (draped_weights if base in DRAPED else hum_hair.hair_weights)(ob, sk, arm))
        if base in DRAPED and ob.get("hum_lod", 0) != 2:
            print(f"{n}: fitted to the builds, mean refit {build_fit(ob, H, sk) * 100:.2f} cm (worst build)")
        ob.hide_set(True)
        ob.hide_render = True
    for k, v in saved.items():
        head.data.shape_keys.key_blocks[k].value = v
    return made


def export(path=None):
    """export/Human_HairCards.fbx: HumanRig + the spike pieces (kept apart from Human_Hair.fbx while it's a spike)."""
    import hum_export
    head = bpy.data.objects["Head"]
    keys = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in keys}
    for k in keys:
        k.value = 0.0
    arm = bpy.data.objects["HumanRig"]
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
    saved_scale = tuple(arm.scale)
    arm.scale = (1, 1, 1)
    names = tuple("Hair_" + n for n in STYLES) + tuple("Beard_" + n for n in BEARD_CARDS)
    pieces = sorted((o for o in bpy.data.objects if o.name.startswith(names)),
                    key=lambda o: o.name)
    for o in pieces:
        for k in (o.data.shape_keys.key_blocks if o.data.shape_keys else []):
            k.value = 0.0
    try:
        return hum_export._export([arm] + pieces, path or os.path.join(hum_export.EXPORT, "Human_HairCards.fbx"))
    finally:
        for k in keys:
            k.value = saved[k.name]
        arm.scale = saved_scale
