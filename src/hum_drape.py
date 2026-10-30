"""Draped hair guides (the hair spike, 2026-10-29): long hair hung under gravity instead of grown along a flow field.

Daniel: "our current hair styles don't look very good, it is not just the material, the mesh is also bad. Improve the
mesh of the Long style" (+ "one with thick hair and another with thin hair"). The flow-grown Long hugged the skull from
the part down (a wet helmet), narrowed into a V below the occiput (a tube, not a curtain) and hung stringy locks from
the temples. Here a strand is a chain of points that
  - leaves its root on the cap shell along the comb direction (off the part, back and down; swept back at the front
    hairline), stiff for its first few centimetres,
  - falls under gravity over the head inflated by the hair's volume (`volume`: thin near the part, fuller at the
    sides - the hair under it; flatter over the top, combed down onto it), so it leaves the skull where the skull
    turns under and hangs as a curtain,
  - stays behind the face line below the hairline (sloping back from the temple to the jaw: the profile shows),
  - rests on the body a little off it, over a shirt; landing on a shoulder it slides off in front (roots in the
    front third of the scalp: locks over the chest) or behind,
  - is cut at a hem (front locks over the chest, the back at the shoulder blades in a U, ragged),
  - and is gathered with its neighbours into locks toward the tip (`clump`, never across the shoulder split).
Collisions use signed distance grids of the head (ears domed over), the body and a shirt, sampled once per head.
Round 2 (Daniel, 2026-10-29: "something feels off"): the first cut hung a box from the forehead's hairline, cut the
sides at the neck while the back went on (a mullet), stood 1.5 cm off the crown (a halo of dark wires) and floated 2 cm
off the body. The hair is draped on the base body; hum_cards.draped_keys / build_fit put it on every build.
"""
import math

import numpy as np
from mathutils import Vector

import hum_paint
from hum_hair import _unit

ss = hum_paint.smoothstep
CELL = 0.006


class Field:
    """Signed distance (m, + outside) of a BVH on a grid, trilinear lookups with gradients."""

    def __init__(self, bvh, lo, hi, cell=CELL):
        self.lo = np.asarray(lo, float)
        self.cell = cell
        n = np.ceil((np.asarray(hi) - self.lo) / cell).astype(int) + 1
        self.n = n
        xs = [self.lo[i] + np.arange(n[i]) * cell for i in range(3)]
        G = np.stack(np.meshgrid(*xs, indexing="ij"), -1).reshape(-1, 3)
        D = np.empty(len(G))
        for k, p in enumerate(G):
            loc, nrm, _, d = bvh.find_nearest(Vector(p))
            if loc is None:
                D[k] = 1.0
                continue
            s = (p[0] - loc[0]) * nrm[0] + (p[1] - loc[1]) * nrm[1] + (p[2] - loc[2]) * nrm[2]
            D[k] = d if s >= 0 else -d
        self.D = D.reshape(n)
        self.grad = np.stack(np.gradient(self.D, cell), -1)

    def outside_above(self, z):
        """Nothing above `z` is inside (an open mesh's top: past its rim the sign is anyone's)."""
        k = self.lo[2] + np.arange(self.n[2]) * self.cell > z
        self.D[:, :, k] = np.abs(self.D[:, :, k])
        self.grad = np.stack(np.gradient(self.D, self.cell), -1)

    def sample(self, P):
        f = (np.asarray(P) - self.lo) / self.cell
        f = np.clip(f, 0, self.n - 1.001)
        i = np.floor(f).astype(int)
        t = f - i
        d = 0.0
        g = 0.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (t[..., 0] if dx else 1 - t[..., 0]) * (t[..., 1] if dy else 1 - t[..., 1]) \
                        * (t[..., 2] if dz else 1 - t[..., 2])
                    ii = (i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz)
                    d = d + w * self.D[ii]
                    g = g + w[..., None] * self.grad[ii]
        n = g / np.maximum(np.linalg.norm(g, axis=-1, keepdims=True), 1e-9)
        return d, n


SHIRT = ("Cloth_Shirt_FSlim", "F", "Slim")   # the hair lies on a shirt (taken back to the base body); thicker clothes: the sim
SHOULDER_Y = -0.02            # a strand whose tip hangs ahead of this went over the shoulder in front


class _Union:
    """The body and the shirt over it, each with its own gap folded into the distance: the nearer one. The shirt is an
    open mesh (its sign flips past the neck, sleeve and hem openings), so it counts only just over the body: between
    the skin and 4 cm out, and no deeper than 3 cm inside it (first cut: strands shot out sideways at the shoulders
    and stood out of the back)."""

    def __init__(self, a, ga, b, gb):
        self.a, self.ga, self.b, self.gb = a, ga, b, gb

    def sample(self, P):
        da, na = self.a.sample(P)
        if self.b is self.a:
            return da - self.ga, na
        db, nb = self.b.sample(P)
        valid = (da > -0.005) & (da < 0.04) & (db > -0.03)
        da = da - self.ga
        db = db - self.gb
        use_b = valid & (db < da)
        return np.where(use_b, db, da), np.where(use_b[..., None], nb, na)


def fields(H):
    """The head (ears domed), body and shirt distance grids, once per HeadFrame."""
    if getattr(H, "_drape_fields", None) is None or len(H._drape_fields) < 3:
        import bpy
        from mathutils.bvhtree import BVHTree
        top = H.co[:, 2].max()
        lo = (-0.27, H.cy - 0.17, top - 0.60)
        hi = (0.27, H.cy + 0.28, top + 0.05)
        head = Field(H.bvh_hair, lo, hi)
        bb = H.body_bvh()
        body = Field(bb, lo, hi) if bb is not None else None
        if body is not None:
            # the body is open at the neck (the head is its own mesh): a node over the head nearest that rim took the
            # rim's sign at random - an "inside" speck on top of the head threw a strand 3 cm sideways into a tuft
            kb = bpy.data.objects["Body"].data.shape_keys
            co = kb.key_blocks[0].data if kb else bpy.data.objects["Body"].data.vertices
            body.outside_above(max(d.co[2] for d in co) + CELL)
        sh = bpy.data.objects.get(SHIRT[0])
        shirt = None
        if sh is not None:
            me = sh.data
            co = np.array([v.co[:] for v in me.vertices]) - unbuild(SHIRT[1], SHIRT[2], np.array([v.co[:] for v in me.vertices]))
            shirt = Field(BVHTree.FromPolygons([tuple(p) for p in co], [tuple(p.vertices) for p in me.polygons]), lo, hi)
        H._drape_fields = (head, body, shirt)
    return H._drape_fields


def unbuild(sex, build, P):
    """The body's residual shape-key offset of a build (hum_builds) at each point's nearest body point: a garment
    built for that build, less this, sits on the base body - which the hair is draped on (draped hair takes the
    body's keys itself: hum_cards.draped_keys)."""
    import bpy
    import hum_builds
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    body = bpy.data.objects["Body"]
    kb = body.data.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kb[0].data])
    W = dict(hum_builds._BASE[sex])
    W.update(hum_builds._SHAPE[(sex, build)])
    D = np.zeros_like(base)
    for k, w in W.items():
        if k in kb:
            D += w * (np.array([d.co[:] for d in kb[k].data]) - base)
    polys = [tuple(p.vertices) for p in body.data.polygons]
    shaped = base + D
    bvh = BVHTree.FromPolygons([tuple(p) for p in shaped], polys)
    out = np.zeros((len(P), 3))
    for i, p in enumerate(P):
        loc, _, fi, _ = bvh.find_nearest(Vector(p))
        ids = list(polys[fi])
        dist = np.linalg.norm(shaped[ids] - np.array(loc), axis=1) + 1e-6
        w = (1.0 / dist) / (1.0 / dist).sum()
        out[i] = (D[ids] * w[:, None]).sum(0)
    return out


def body_field(H, body_gap, shirt_gap):
    """What hair rests on below the head: `body_gap` off the skin, `shirt_gap` off the shirt (where a shirt bridges a
    hollow - the back between the shoulder blades - the hair lies on it). sample(P) -> (distance past the gap, normal)."""
    _, body, shirt = fields(H)
    if body is None:
        return None
    return _Union(body, body_gap, shirt, shirt_gap) if shirt is not None else _Union(body, body_gap, body, body_gap)


def front_of(H, P):
    """1 toward the front hairline (forehead, temples), 0 from the crown back: by how far ahead of the top of the head
    a point is, not by its angle round the head - near the top that angle swings wildly between neighbours, and the
    crown's cards combed every which way (a chevron patchwork)."""
    return ss(H.cy - 0.015, H.cy - 0.065, np.asarray(P)[..., 1])


def card_normal_fn(H):
    """p -> the facing of a draped card there: off the head near it, off the body where the hair lies on it (front locks
    on the chest, the back), out from the head's axis in between. (Off the head or its axis only, the front locks on
    the chest faced sideways: the sun lit them edge-on - no brown, all highlight: they read mauve.)"""
    _, body, _ = fields(H)

    def fn(p):
        loc, n, _ = H.nearest(p)
        far = ss(0.008, 0.03, float(np.linalg.norm(p - loc)))
        radial = _unit(np.array([p[0], p[1] - H.cy, 0.0]))
        out = radial
        if body is not None:
            d, nb = body.sample(np.asarray(p)[None])
            on = 1.0 - ss(0.02, 0.06, float(d[0]))
            out = _unit(radial * (1 - on) + nb[0] * on)
        return _unit(n * (1 - far) + out * far)
    return fn


def comb_dir(H, r, n, part_x=0.0):
    """Off the part sideways near the top, back and down lower, swept back at the front hairline; tangent to the
    scalp."""
    side = np.sign(r[0] - part_x + 1e-6)
    top = ss(H.eye_z + 0.03, H.eye_z + 0.09, r[2])          # 1 near the top of the head
    front = float(front_of(H, r))                           # 1 at the front hairline
    # at the front "back" leans up the brow's slope: down there, projected onto the forehead, would point sideways and
    # up, and the free ends fell back down in front of the hairline (loops over the forehead)
    # at the sides hardly back at all: the hair over the ears falls over them (first cut, 0.35: it drifted 2 cm back
    # and left a thin patch behind the ear)
    x = side * (0.25 + 1.1 * top + 0.45 * front)
    if part_x != 0.0:
        # a side parting ends at the crown: behind it the hair falls down the back (split along the line all the way
        # back, it left a dark seam down the back and a tuft where the two sides met at the crown)
        k = ss(H.cy + 0.045, H.cy + 0.01, r[1])
        x = x * k + np.sign(r[0]) * 0.25 * (1 - top) * (1 - k)
    v = np.array([x, 0.15 + 0.6 * front, (-1.0 + 0.5 * top) * (1 - front) + 0.3 * front])
    v = v - n * np.dot(v, n)
    return _unit(v)


def face_line(H):
    """The face's edge for hair below the hairline: a strand may not lie in front of y(z), a line sloping back from
    the temple's hairline corner (brow height) to just behind the ear's front at the jaw, so the hair is swept back
    off the face and its profile shows (first cut: the curtain hung straight down from the forehead's hairline and
    hid all but the nose tip from the side). Returns (z_top, z_jaw, y_top, y_jaw)."""
    z_top = H.eye_z + 0.05
    z_jaw = float(H.F.chin[2]) + 0.01
    return z_top, z_jaw, H.ear_y_front - 0.032, H.ear_y_front + 0.006


def drape(H, roots, length, volume, root_clear=0.0055, body_gap=0.012, shirt_gap=0.005, seg=0.011, iters=160,
          stiff_len=0.05, part_x=0.0, front_y=None, crown_k=0.5, slide_z=None, lengths=None, vol_k=None, seed=0):
    """Strands (N x M x 3) hung from `roots`: comb, gravity, head volume, body, lengths (follow the leader).
    lengths: per strand (m; the rest of its points sit on its last one) - hair longer than its hem piled up on the
    hips in zigzags (hem_cut's lengths from a first pass, plus a little). vol_k: per strand, its share of the volume.
    root_clear: where a root sits off the skin (on the cap shell: the style's cap + 1.5 mm); the clearance grows from it
    to the layer's `volume` over the first centimetres, `crown_k` of it over the top of the head. Roots ahead of
    `front_y` (default: the top of the head, about the front third of the scalp) fall over the shoulder in front, the
    rest behind it."""
    head, _, _ = fields(H)
    body = body_field(H, body_gap, shirt_gap)
    rng = np.random.default_rng(seed)
    N = len(roots)
    M = int(math.ceil(length / seg)) + 1
    s = np.arange(M) * seg                                  # distance from the root
    R, Nn, C = [], [], []
    for r in roots:
        loc, n, _ = H.nearest_skin(r)
        R.append(loc)
        Nn.append(n)
        C.append(comb_dir(H, loc, n, part_x))
    R, Nn, C = np.array(R), np.array(Nn), np.array(C)
    # the head clearance along a strand: the root sits on the cap, the hair over it fills out to the volume (first cut:
    # roots 1 cm off the scalp - a stiff root segment then rose off the crown in arcs that read as dark wires)
    v0, v1 = volume
    vol = (v0 + (v1 - v0) * ss(0.0, 0.07, s)) * ss(0.0, 0.045, s)
    jitter = rng.uniform(0.85, 1.15, N)[:, None]
    if vol_k is not None:
        jitter = jitter * np.asarray(vol_k)[:, None]
    clear = root_clear + vol[None, :] * jitter              # N x M
    top = ss(H.eye_z + 0.02, H.eye_z + 0.08, R[:, 2])[:, None]
    lift = 0.3 - 0.22 * top                                 # combed flat over the top, a little body lower down
    P = R[:, None, :] + C[:, None, :] * s[None, :, None] + Nn[:, None, :] * clear[..., None]
    stiff = np.clip(1 - s / stiff_len, 0, 1) ** 2           # the first centimetres keep the comb direction
    target = R[:, None, :] + (C[:, None, :] + Nn[:, None, :] * lift[..., None]) * s[None, :, None]
    g = np.array([0, 0, -0.004])
    # the face: below the hairline nothing in front of the face line, and in front of the ears nothing nearer the
    # middle than just past the eye's outer corner (first cut: strands from the front hairline fell over the eyes)
    F = H.F
    face_x = abs(F.eye['l'][0][0]) + F.eye['l'][1] * 1.8 + 0.006
    face_y = H.ear_y_front + 0.004
    z_top, z_jaw, y_top, y_jaw = face_line(H)
    chin_z = float(F.chin[2]) - 0.03
    # hair landing on a shoulder slides off it: in front (roots ahead of front_y, framing the face onto the chest) or
    # behind; in toward the neck either way (not out along the shoulder like a broom)
    front_y = H.cy if front_y is None else front_y
    slide_z = H.eye_z - 0.26 if slide_z is None else slide_z      # about the armpits
    slide = np.where(R[:, 1] < front_y, -1.0, 1.0)[:, None]  # y: -1 forward, +1 back (by angle round the head the
                                                              # crown's roots went either way at random)
    last = None
    if lengths is not None:
        last = np.minimum(np.searchsorted(s, np.asarray(lengths), side="right") - 1, M - 1)
        active = np.arange(M)[None, :] <= last[:, None]
    for it in range(iters):
        P[:, 1:] += g
        w = (stiff * 0.6)[None, 1:, None]
        P[:, 1:] = P[:, 1:] * (1 - w) + target[:, 1:] * w
        for _ in range(2):
            d, nrm = head.sample(P)
            # over the top of the head the hair lies flatter (`crown_k` of the volume; first cut: the outer cards stood
            # 1.5 cm off the crown and its outline read as a halo of wires) and is combed down onto it (tension), not
            # standing off it
            cl = root_clear + (clear - root_clear) * (1 - (1 - crown_k) * ss(0.4, 0.85, nrm[..., 2]))
            push = np.maximum(cl - d, 0.0)
            hug = np.maximum(d - cl, 0.0) * (d < cl + 0.025) * ss(0.15, 0.45, nrm[..., 2]) * 0.5
            push = push - hug
            push[:, 0] = 0
            P += nrm * push[..., None]
            if body is not None:
                d, nrm = body.sample(P)
                push = np.maximum(-d, 0.0) * (d > -0.08)     # far inside: another part (the neck's hole)
                push[:, 0] = 0
                P += nrm * push[..., None]
                # resting on top of a shoulder (only up there: at the small of the back, which faces up and back too,
                # it kicked the tips back every pass and they hung in kinks)
                on = (push > 0) & (nrm[..., 2] > 0.35) & (P[..., 2] > slide_z)
                P[..., 1] += on * slide * 0.005
                P[..., 0] -= on * np.sign(P[..., 0]) * 0.0012
            z = P[..., 2]
            t = np.clip((z_top - z) / (z_top - z_jaw), 0.0, 1.0)
            ylim = y_top + (y_jaw - y_top) * t
            below = (z < z_top) & (s[None, :] > 0.02)
            release = ss(z_jaw - 0.045, z_jaw, z)           # under the jaw the front locks may come forward again
            P[..., 1] = np.where(below & (P[..., 1] < ylim), P[..., 1] + (ylim - P[..., 1]) * release, P[..., 1])
            fz = (P[..., 1] < face_y) & (z < z_top) & (z > chin_z - 0.06) & (s[None, :] > 0.025)
            ax = np.abs(P[..., 0])
            P[..., 0] = np.where(fz & (ax < face_x), np.sign(P[..., 0] + 1e-9) * face_x, P[..., 0])
        for k in range(1, M):                                # follow the leader: exact lengths, root fixed
            d = P[:, k] - P[:, k - 1]
            L = np.linalg.norm(d, axis=-1, keepdims=True)
            P[:, k] = P[:, k - 1] + d / np.maximum(L, 1e-9) * seg
        if last is not None:
            P = np.where(active[..., None], P, P[np.arange(N), last][:, None, :])
    return P, s


def hem_cut(H, P, s, hem_front, hem_back, hem_u=0.04, ragged=0.025, seed=0, lengths=None):
    """Each strand cut where it first drops below its hem: `hem_front` for a strand that falls in front of the shoulder
    (its tip ahead of SHOULDER_Y), `hem_back` behind, `hem_u` lower down the middle of the back than at the sides (a
    U, by where its tip hangs). Returns a list of strands, and their lengths. (First cut: hems by the angle round the
    head plus a cut where a strand ran 20 cm out over a shoulder - the sides stopped at the neck while the back went
    on: a mullet.) lengths: the strands' own (drape's), not cut past."""
    rng = np.random.default_rng(seed + 11)
    out, lens = [], []
    for i in range(len(P)):
        front = P[i, -1, 1] < SHOULDER_Y
        z = hem_front if front else hem_back - hem_u * (1.0 - ss(0.0, 0.13, abs(float(P[i, -1, 0]))))
        z += rng.uniform(-1, 1) * ragged
        below = np.where(P[i, :, 2] < z)[0]
        k = int(below[0]) if len(below) else len(s) - 1
        # or where, past the head, it turns back up or folds: it landed on the hips (in the rest pose they reach the
        # hem) and piled up - the tips hung in zigzags
        d = np.diff(P[i], axis=0)
        u = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        turn = np.r_[1.0, (u[1:] * u[:-1]).sum(1)]          # cos of the turn at each point after the root
        bad = np.where(((d[:, 2] > 0.003) | (turn < 0.5)) & (s[1:] > 0.12))[0]
        if len(bad):
            k = min(k, int(bad[0]))
        if lengths is not None:
            k = min(k, int(np.searchsorted(s, lengths[i], side="right")) - 1)
        k = max(k, 3)
        out.append(P[i, :k + 1].copy())
        lens.append(s[k])
    return out, np.array(lens)


def clump(strands, roots, amount, size=0.03, seed=0, groups=None):
    """Neighbouring strands (roots within ~size, the same `groups` label: in front of the shoulder or behind it) drawn
    toward their lock's centre line, more toward the tip. Mates are matched by distance from the root, a point only to
    the mates as long as it (first cut: matched by the fraction of their length, mates of other lengths - or ones
    gone the other way round the shoulder - pulled strands sideways into kinks)."""
    if amount <= 0:
        return strands
    rng = np.random.default_rng(seed + 5)
    roots = np.asarray(roots)
    groups = np.zeros(len(roots), int) if groups is None else np.asarray(groups)
    order = rng.permutation(len(roots))
    centres = []
    for i in order:                                          # lock centres: a blue-noise subset of each group's roots
        near = [c for c in centres if groups[c] == groups[i]]
        if not near or np.min(np.linalg.norm(roots[near] - roots[i], axis=1)) > size:
            centres.append(i)
    centres = np.array(centres)
    lock = np.empty(len(roots), int)
    for i, r in enumerate(roots):
        cand = centres[groups[centres] == groups[i]]
        lock[i] = cand[int(np.argmin(np.linalg.norm(roots[cand] - r, axis=1)))]
    # every strand by arc length at one spacing
    step = 0.01
    res, L = [], []
    for S in strands:
        seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))]
        t = np.arange(0.0, seg[-1] + 1e-9, step)
        if t[-1] < seg[-1] - 0.5 * step:
            t = np.r_[t, seg[-1]]
        else:                                                # no stub of a last step (its direction is anyone's)
            t[-1] = seg[-1]
        res.append(np.stack([np.interp(t, seg, S[:, c]) for c in range(3)], 1))
        L.append(seg[-1])
    out = []
    for i, S in enumerate(res):
        mates = np.where(lock == lock[i])[0]
        # the pull toward each mate, held at its last value past the mate's end (a mean over the mates still that long
        # jumped where one ended: the tips zigzagged)
        off = np.zeros_like(S)
        for m in mates:
            k = min(len(res[m]), len(S))
            d = res[m][:k] - S[:k]
            off[:k] += d
            off[k:] += d[-1]
        off /= len(mates)
        t = np.linspace(0, 1, len(S))
        w = amount * ss(0.35, 1.0, t)[:, None]
        out.append(S + off * w)
    return out


def settle(H, strands, volume, root_clear=0.0055, body_gap=0.012, shirt_gap=0.005, crown_k=0.5, iters=6,
           smooth=0.3, vol_k=None):
    """A few collision passes after the clumping (no gravity): the locks back out of the head and body, each pass
    smoothed along the strand first (`smooth`: a kink left by the clumping or a collision shows as a card twisting)."""
    head, _, _ = fields(H)
    body = body_field(H, body_gap, shirt_gap)
    out = []
    for si, S in enumerate(strands):
        S = S.copy()
        seg = np.linalg.norm(np.diff(S, axis=0), axis=1)
        s = np.r_[0, np.cumsum(seg)]
        k = 1.0 if vol_k is None else float(vol_k[si])
        clear = root_clear + (volume[0] + (volume[1] - volume[0]) * ss(0.0, 0.07, s)) * ss(0.0, 0.045, s) * k
        for _ in range(iters):
            if len(S) > 2:
                S[1:-1] = S[1:-1] * (1 - smooth) + (S[:-2] + S[2:]) * (0.5 * smooth)
            d, nrm = head.sample(S)
            cl = root_clear + (clear - root_clear) * (1 - (1 - crown_k) * ss(0.4, 0.85, nrm[:, 2]))
            push = np.maximum(cl - d, 0.0)
            push[0] = 0
            S += nrm * push[:, None]
            if body is not None:
                d, nrm = body.sample(S)
                push = np.maximum(-d, 0.0) * (d > -0.08)
                push[0] = 0
                S += nrm * push[:, None]
            for k in range(1, len(S)):
                dv = S[k] - S[k - 1]
                S[k] = S[k - 1] + dv / max(np.linalg.norm(dv), 1e-9) * seg[k - 1]
        out.append(S)
    return out
