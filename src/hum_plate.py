"""Plate armour: a harness built from a few primitives, so new pieces and better-looking styles are cheap.

Layout
  PlateStyle   the look shared by every piece of a harness: standoff, medial ridge, fluting, rolled edges,
               rivets, brass trim, leather straps. A new look = a new style + one plate_garments() call.
  Frame        a cylindrical frame (origin, axis, reference direction) around a bone or the spine.
  Support      R(t, th): the convex support radius around the frame axis of the body and of everything worn
               under it, per slice. Plates follow it plus a standoff: they bridge hollows (between the
               breasts, the spine groove) and never dip into what they cover.
  Grid         one plate as rows x columns over (t along the axis, th around it): shaped outlines (every
               column has its own t range), ridges/flutes/domes as radial offsets, rolled edges as extra rows
               curling outward, rivets and straps placed on it. `part()` turns it into a garment part.
  pieces       cuirass (breastplate, backplate, fauld lames, tassets), pauldrons (cop + lames), arms
               (rerebrace, couter, vambrace), gauntlets (cuff + hand plate over leather gloves), legs (cuisse,
               poleyn, greave), sabatons (lames + toe cap over boots), helm (a bascinet over a mail coif).

Every plate is stiff: uniform weights, blended between two bones for lames. Articulation comes from
overlapping lames, as on real armour (a plate never bends).
Vertex data (ClothData): r AO, g polish (edges, rivets: brighter and smoother), b LOD detail (rivets,
buckles; dropped at L1/L2), a material (1 steel, 0.5 trim, 0 leather). Shader: Humans/Plate.
"""
import math
from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Vector

import hum_armor as A
import hum_cloth as C

ss = C.ss
STEEL, TRIM, LEATHER = 1.0, 0.5, 0.0


@dataclass(frozen=True)
class PlateStyle:
    name: str
    gap: float = 0.010             # standoff over whatever is worn under (m)
    ridge: float = 0.005           # medial ridge: breastplate, greaves, helm crest
    flutes: int = 0                # fluting ridges across a plate (0 = plain)
    flute_depth: float = 0.0
    roll: float = 0.004            # rolled edge radius (0 = a plain cut edge)
    rivet_r: float = 0.0038
    rivet_step: float = 0.05
    trim: bool = False             # rolled edges and rivets in trim metal (brass)
    straps: bool = True            # leather straps and buckles
    thickness: float = 0.0025
    helm: str = "bascinet"         # "bascinet" (rim to the nape), "sallet" (tail over the nape), "closed"
    helm_tail: float = 0.0         # how far a sallet's tail flares out (m)
    horns: float = 0.0             # horn length on the helm (m); 0 = none
    under_torso: tuple = ("ArmingDoublet", "Gambeson")   # garments the plates stand off (by name)
    under_legs: tuple = ("PaddedLeggings", "Leggings")
    point: float = 0.0             # pointed lower edges: breastplate plackart, fauld, tassets, pauldron lames (m)
    spikes: float = 0.0            # spike length on pauldrons, vambraces, poleyns (m); 0 = none
    pauldron_lames: int = 3
    cuisses: bool = True
    ornament: float = 0.0          # etched, inlaid ornament inside each plate (0..1; Humans/Plate ornament mask)
    group: str = ""                # colour group override ("" = by material: Steel)
    under_hands: tuple = ("Gloves",)
    claws: bool = False            # finger plates on every segment, pointed claws at the tips
    ornament_pattern: int = 0      # slice of T_Plate_Ornament (0 acanthus scrollwork, 1 damask)
    ornament_mode: int = 0         # 0 gold inlay, 1 etched (bright raised lines on a darkened ground)
    ornament_band: tuple = (0.012, 0.065)   # ornament from .. to metres in from each plate's edge
    pauldron_flare: float = 0.0    # extra flare of the pauldron lames' lower edges (m)


STYLES = {
    "Munition": PlateStyle("Munition"),
    # late 15th c.: fluted plates, brass-trimmed rolled edges and rivets, a sallet
    "Gothic": PlateStyle("Gothic", ridge=0.007, flutes=9, flute_depth=0.0055, roll=0.0045, trim=True,
                         rivet_r=0.0042, helm="sallet", helm_tail=0.05),
    # fantasy: blackened steel close over a bodysuit, gold-inlaid ornament, pointed edges, spikes, a closed
    # horned helm; a long skirt instead of cuisses
    # fantasy: bright steel close over a bodysuit, every large plate filled with gold-inlaid damask inside a
    # plain rim, gold beads, flaring pauldrons, an open bascinet
    "Ornate": PlateStyle("Ornate", gap=0.006, ridge=0.006, roll=0.004, straps=False, trim=True,
                         under_torso=(), under_legs=(), under_hands=(), point=0.035, pauldron_lames=3,
                         pauldron_flare=0.015, ornament=1.0, ornament_pattern=1, ornament_mode=1,
                         ornament_band=(0.018, 1.0)),
    "BlackKnight": PlateStyle("BlackKnight", gap=0.006, ridge=0.009, roll=0.0035, straps=False, trim=True,
                              helm="closed", horns=0.18, under_torso=(), under_legs=(), under_hands=(),
                              point=0.07, spikes=0.1, pauldron_lames=4, cuisses=True, ornament=1.0,
                              claws=True, pauldron_flare=0.022,
                              group="Blackened"),
}


def _cols(n, st, per=6):
    """Columns for a plate: enough for the style's flutes (`per` per flute) or n."""
    return max(n, st.flutes * per + 1) if st.flutes else n


# ------------------------------------------------------------------ frame and support

class Frame:
    """o + a*t + (c cos th + b sin th) * r."""

    def __init__(self, o, a, c):
        self.o = np.asarray(o, float)
        self.a = C._unit(np.asarray(a, float))
        c = np.asarray(c, float)
        self.c = C._unit(c - self.a * (c @ self.a))
        self.b = np.cross(self.a, self.c)

    def dirs(self, th):
        th = np.asarray(th, float)[..., None]
        return np.cos(th) * self.c + np.sin(th) * self.b

    def point(self, t, th, r):
        t, r = np.asarray(t, float), np.asarray(r, float)
        return self.o + self.a * t[..., None] + self.dirs(th) * r[..., None]


class Support:
    """Convex support radius of points P around a frame's axis, on a (t, th) lattice (slices +-band), lightly
    smoothed; called with (t, th) arrays it interpolates (th periodic)."""

    def __init__(self, fr, P, t0, t1, band=0.02, step=0.01, nth=96, smooth=2):
        Q = np.asarray(P, float) - fr.o
        t = Q @ fr.a
        X = np.stack([Q @ fr.c, Q @ fr.b], 1)
        self.T = np.arange(min(t0, t1) - 0.03, max(t0, t1) + 0.03 + 1e-9, step)
        self.TH = np.linspace(-math.pi, math.pi, nth, endpoint=False)
        D = np.stack([np.cos(self.TH), np.sin(self.TH)], 1)
        R = np.full((len(self.T), nth), np.nan)
        for k, tk in enumerate(self.T):
            sel = np.abs(t - tk) < band
            if sel.sum() >= 6:
                R[k] = (X[sel] @ D.T).max(0)
        ok = ~np.isnan(R[:, 0])
        if not ok.any():
            raise ValueError("plate support: no points near the axis")
        good = np.where(ok)[0]
        for k in np.where(~ok)[0]:
            R[k] = R[good[np.argmin(np.abs(good - k))]]
        for _ in range(smooth):
            R = 0.5 * R + 0.25 * (np.roll(R, 1, 1) + np.roll(R, -1, 1))
            R[1:-1] = 0.5 * R[1:-1] + 0.25 * (R[:-2] + R[2:])
        self.R = R

    def __call__(self, t, th):
        t, th = np.asarray(t, float), np.asarray(th, float)
        ft = np.clip((t - self.T[0]) / (self.T[1] - self.T[0]), 0, len(self.T) - 1.0001)
        k = np.floor(ft).astype(int)
        a = ft - k
        n = len(self.TH)
        fh = ((th + math.pi) / (2 * math.pi) * n) % n
        j = np.floor(fh).astype(int)
        b = fh - j
        j1 = (j + 1) % n
        R = self.R
        return (1 - a) * ((1 - b) * R[k, j] + b * R[k, j1]) + a * ((1 - b) * R[k + 1, j] + b * R[k + 1, j1])


# ------------------------------------------------------------------ one plate

class Grid:
    """A plate on rows x columns over (t, th): T, TH, R arrays of shape (rows, cols). Rows run along the
    axis (t grows with the row index), columns around it."""

    def __init__(self, fr, T, TH, R, closed=False, rfun=None):
        self.fr = fr
        self.T, self.TH, self.R = (np.array(x, float) for x in (T, TH, R))
        self.closed = closed
        self.rfun = rfun                                   # (t, th) -> R of the plate surface (for straps)
        self.polish = np.zeros(self.T.shape)
        self.mat = np.full(self.T.shape, STEEL)
        self.extra = []                                    # (V, F, detail, polish, mat) riding on the plate

    @classmethod
    def sweep(cls, fr, sup, th, t0, t1, rows, off, closed=False):
        """Columns at angles th (radians); column j spans t0[j]..t1[j] in `rows` rows. off(t, th, u, v) ->
        radial offset over the support (u 0..1 across the columns, v 0..1 along the rows)."""
        th = np.asarray(th, float)
        cols = len(th)
        t0 = np.broadcast_to(np.asarray(t0, float), (cols,))
        t1 = np.broadcast_to(np.asarray(t1, float), (cols,))
        v = np.linspace(0, 1, rows)[:, None]
        u = (np.arange(cols) / (cols if closed else max(cols - 1, 1)))[None, :]
        T = t0[None, :] + (t1 - t0)[None, :] * v
        TH = np.broadcast_to(th[None, :], T.shape)
        U = np.broadcast_to(u, T.shape)
        V = np.broadcast_to(v, T.shape)
        R = sup(T, TH) + off(T, TH, U, V)

        def rfun(t, h):                                    # the same surface anywhere (grid coords recovered)
            t, h = np.asarray(t, float), np.asarray(h, float)
            if closed:
                uu = ((h + math.pi) % (2 * math.pi)) / (2 * math.pi)
                a, b = np.interp(uu, u[0], t0), np.interp(uu, u[0], t1)
            else:
                uu = (h - th[0]) / (th[-1] - th[0])
                a, b = np.interp(h, th, t0), np.interp(h, th, t1)
            vv = (t - a) / np.where(np.abs(b - a) > 1e-6, b - a, 1.0)
            return sup(t, h) + off(t, h, uu, vv)
        return cls(fr, T, TH, R, closed=closed, rfun=rfun)

    # -- edges
    def roll(self, side, r, mat=STEEL):
        """Curl an edge outward into a bead of radius r: three more rows (or columns) on a half circle in
        the (t, R) (or (th, R)) plane. side: 'top' (last row), 'bottom', 'left' (first column), 'right'."""
        if r <= 0:
            return self
        # round the edge and almost back onto the plate (a bead, not a hoop standing off it)
        phis = (0.35 * math.pi, 0.7 * math.pi, math.pi, 1.35 * math.pi, 1.8 * math.pi)
        if side in ("top", "bottom"):
            k, s = (-1, 1.0) if side == "top" else (0, -1.0)
            T0, TH0, R0 = self.T[k], self.TH[k], self.R[k]
            rows = [(T0 + s * r * math.sin(p), TH0, R0 + r * (1 - math.cos(p))) for p in phis]
            nT, nTH, nR = (np.array([x[i] for x in rows]) for i in range(3))
            nP = np.ones_like(nT)
            nM = np.full_like(nT, mat)
            self.polish[k] = np.maximum(self.polish[k], 0.6)
            if side == "top":
                self.T, self.TH, self.R = (np.vstack([a, b]) for a, b in ((self.T, nT), (self.TH, nTH), (self.R, nR)))
                self.polish, self.mat = np.vstack([self.polish, nP]), np.vstack([self.mat, nM])
            else:
                rev = lambda a: a[::-1]
                self.T, self.TH, self.R = (np.vstack([rev(b), a]) for a, b in ((self.T, nT), (self.TH, nTH), (self.R, nR)))
                self.polish, self.mat = np.vstack([nP, self.polish]), np.vstack([nM, self.mat])
        else:
            if self.closed:
                return self
            k, s = (-1, 1.0) if side == "right" else (0, -1.0)
            T0, TH0, R0 = self.T[:, k], self.TH[:, k], self.R[:, k]
            cols = [(T0, TH0 + s * r * math.sin(p) / np.maximum(R0, 0.02), R0 + r * (1 - math.cos(p))) for p in phis]
            nT, nTH, nR = (np.stack([x[i] for x in cols], 1) for i in range(3))
            nP = np.ones_like(nT)
            nM = np.full_like(nT, mat)
            self.polish[:, k] = np.maximum(self.polish[:, k], 0.6)
            if side == "right":
                self.T, self.TH, self.R = (np.hstack([a, b]) for a, b in ((self.T, nT), (self.TH, nTH), (self.R, nR)))
                self.polish, self.mat = np.hstack([self.polish, nP]), np.hstack([self.mat, nM])
            else:
                rev = lambda a: a[:, ::-1]
                self.T, self.TH, self.R = (np.hstack([rev(b), a]) for a, b in ((self.T, nT), (self.TH, nTH), (self.R, nR)))
                self.polish, self.mat = np.hstack([nP, self.polish]), np.hstack([nM, self.mat])
        return self

    # -- sampling the surface
    def P(self):
        return self.fr.point(self.T, self.TH, self.R)

    def at(self, t, th, lift=0.0):
        """Point and outward normal on the plate surface at (t, th) (via rfun), lifted by `lift`."""
        t, th = np.atleast_1d(t).astype(float), np.atleast_1d(th).astype(float)
        e = 0.002
        r = self.rfun(t, th)
        p = self.fr.point(t, th, r + lift)
        pt = self.fr.point(t + e, th, self.rfun(t + e, th))
        ph = self.fr.point(t, th + e / np.maximum(r, 0.02), self.rfun(t, th + e / np.maximum(r, 0.02)))
        n = C._unit(np.cross(pt - self.fr.point(t, th, r), ph - self.fr.point(t, th, r)))
        radial = self.fr.dirs(th)
        n = np.where(((n * radial).sum(-1) < 0)[:, None], -n, n)
        return p, n

    def rivets(self, t, th, st, lift=0.0):
        """Round rivet heads at (t, th) (arrays): LOD detail, polished; brass if the style trims."""
        if len(np.atleast_1d(t)) == 0:
            return self
        P, N = self.at(t, th, lift)
        V, F = A.studs(P, N, r=st.rivet_r, h=st.rivet_r * 0.7)
        n = len(V)
        self.extra.append((V, F, np.ones(n), np.ones(n), np.full(n, TRIM if st.trim else STEEL)))
        return self

    def strap(self, t0, t1, th0, th1, st, buckle=True, rows=4, cols=4):
        """A leather strap lying on the plate over t0..t1 x th0..th1, with a steel buckle boss."""
        if not st.straps:
            return self
        T = np.linspace(t0, t1, rows)[:, None] * np.ones((1, cols))
        TH = np.ones((rows, 1)) * np.linspace(th0, th1, cols)[None, :]
        R = self.rfun(T, TH) + 0.0018
        g = Grid(self.fr, T, TH, R)
        V, F = g._faces()
        n = len(V)
        V, F, src = _rim(V, F, 0.0015, self.fr)
        m = len(V)
        self.extra.append((V, F, np.zeros(m), np.zeros(m), np.full(m, LEATHER)))
        if buckle:
            tm, hm = (t0 + t1) / 2, (th0 + th1) / 2
            P, N = self.at([tm], [hm], 0.0018)
            BV, BF = A.studs(P, N, r=0.008, h=0.004)
            k = len(BV)
            self.extra.append((BV, BF, np.ones(k), np.full(k, 0.5), np.full(k, STEEL)))
        return self

    # -- mesh
    def _faces(self):
        rows, cols = self.T.shape
        V = self.P().reshape(-1, 3)
        idx = lambda k, j: k * cols + (j % cols)
        jmax = cols if self.closed else cols - 1
        F = [(idx(k, j), idx(k, j + 1), idx(k + 1, j + 1), idx(k + 1, j)) for k in range(rows - 1) for j in range(jmax)]
        f = F[len(F) // 2]
        a, b, c = V[f[0]], V[f[1]], V[f[2]]
        n = np.cross(b - a, c - a)
        q = (a + b + c) / 3 - self.fr.o
        radial = q - self.fr.a * (q @ self.fr.a)
        if n @ radial < 0:
            F = [tuple(reversed(f)) for f in F]
        return V, F

    def panel(self, inner=0.012, outer=0.065):
        """Where a plate's ornament goes: an etched band following its edges, from `inner` to `outer` metres in
        from them (as etched borders were laid out); 0 on the beads, in the plain middle and near the edge."""
        T, TH, R = self.T, self.TH, self.R
        d = np.minimum(np.abs(T - T[:1]), np.abs(T[-1:] - T))
        if not self.closed:
            arc = np.minimum(np.abs(TH - TH[:, :1]), np.abs(TH[:, -1:] - TH)) * np.maximum(R, 0.02)
            d = np.minimum(d, arc)
        w = ss(inner * 0.5, inner, d) * ss(outer, outer * 0.7, d)
        # only big plates carry ornament: on a narrow lame the band filled the whole plate (solid gold)
        height = float(np.max(np.abs(T[-1] - T[0])))
        width = float(np.mean(R)) * (2 * math.pi if self.closed else float(np.mean(np.abs(TH[:, -1] - TH[:, 0]))))
        w = w * ss(0.09, 0.14, min(height, width))
        return np.where(self.polish > 0.55, 0.0, w)

    def spikes(self, t, th, st, length, lean=0.0, r=0.009):
        """Cone spikes standing out of the plate at (t, th), leaning along the axis by `lean` (-1..1)."""
        if length <= 0 or len(np.atleast_1d(t)) == 0:
            return self
        P, N = self.at(t, th)
        D = C._unit(N + self.fr.a * lean)
        V, F = spike_mesh(P - N * 0.002, D, np.broadcast_to(length, (len(P),)), r)
        n = len(V)
        self.extra.append((V, F, np.zeros(n), np.full(n, 0.6), np.full(n, STEEL)))
        return self

    def part(self, st, weights, kind="shell"):
        """(V, F, U, kind, channels, weights) for hum_cloth.build_garment: the plate with a folded-in rim for
        thickness, plus rivets and straps."""
        orn = self.panel(*st.ornament_band).ravel() * st.ornament
        V, F = self._faces()
        pol, mat = self.polish.ravel(), self.mat.ravel().copy()
        if st.trim:                                        # trimmed styles: every rolled bead in brass
            mat[(pol > 0.9) & (mat > 0.75)] = TRIM
        V, F, src = _rim(V, F, st.thickness, self.fr)
        pol = np.r_[pol, np.ones(len(src))]
        mat = np.r_[mat, mat[src]]
        orn = np.r_[orn, np.zeros(len(src))]
        U = np.stack([self.TH.ravel() * float(np.mean(self.R)), self.T.ravel()], 1) / 0.25
        U = np.vstack([U, U[src]])
        det = np.zeros(len(V))
        for EV, EF, ed, ep, em in self.extra:
            n = len(V)
            V = np.vstack([V, EV])
            F = list(F) + [tuple(i + n for i in f) for f in EF]
            det, pol, mat = np.r_[det, ed], np.r_[pol, ep], np.r_[mat, em]
            orn = np.r_[orn, np.zeros(len(EV))]
            U = np.vstack([U, np.zeros((len(EV), 2))])
        return V, F, U, kind, dict(detail=det, polish=pol, mat=mat, orn=orn,
                                   orn_pat=np.full(len(V), float(st.ornament_pattern + 10 * st.ornament_mode))), weights


def spike_mesh(P, D, L, r, seg=8):
    """Cones: base ring of radius r at each P, tip at P + D * L. Faces wind outward."""
    V, F = [], []
    for p, d, l in zip(P, D, L):
        d = C._unit(np.asarray(d, float))
        t1 = C._unit(np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0, 0]))
        t2 = np.cross(d, t1)
        k = len(V)
        for rr, hh in ((1.0, 0.0), (0.55, 0.45)):
            for a in range(seg):
                ang = a * 2 * math.pi / seg
                V.append(p + (t1 * math.cos(ang) + t2 * math.sin(ang)) * r * rr + d * l * hh)
        V.append(p + d * l)
        tip = k + 2 * seg
        for a in range(seg):
            b = (a + 1) % seg
            F.append((k + a, k + b, k + seg + b, k + seg + a))
            F.append((k + seg + a, k + seg + b, tip))
    return np.array(V).reshape(-1, 3), F


def _rim(V, F, depth, fr):
    """hum_cloth.add_rim for a plate: a band folded inward (toward the frame axis) along open edges.
    Returns (V, F, src): src[i] = the edge vertex new vertex i was made from."""
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            edges.setdefault((min(a, b), max(a, b)), []).append((a, b))
    bnd = [ab[0] for e, ab in edges.items() if len(ab) == 1]
    V = [tuple(p) for p in V]
    F = list(F)
    inner, src = {}, []
    for a, b in bnd:
        for v in (a, b):
            if v not in inner:
                p = np.array(V[v])
                q = p - fr.o
                radial = C._unit(q - fr.a * (q @ fr.a))
                inner[v] = len(V)
                src.append(v)
                V.append(tuple(p - radial * depth))
        F.append((b, a, inner[a], inner[b]))
    return np.array(V), F, np.array(src, int)


# ------------------------------------------------------------------ what's under

def _under(names, B=None, parts=None, step=2):
    """LOD0 coordinates of garments already built for this build, optionally only where the nearest body
    part is one of `parts`: plates stand off whatever is worn under them."""
    import hum_builds
    import hum_rig
    pts = [np.zeros((0, 3))]
    for n in names:
        if not n:
            continue
        ob = bpy.data.objects.get(C.cloth_name(n))
        if ob is None:
            continue
        P = hum_builds.build_coords(ob, hum_rig.SK)[::step]
        if parts is not None and B is not None:
            P = P[_near_part(B, P, parts)]
        pts.append(P)
    return np.vstack(pts)


def _near_part(B, P, parts):
    out = np.zeros(len(P), bool)
    for i, p in enumerate(P):
        loc, n, fi, d = B.bvh.find_nearest(Vector(p))
        out[i] = fi is not None and B.part[B.faces[fi][0]] in parts
    return out


def _body(B, parts):
    return B.co_raw[np.isin(B.part, parts)]


def _span(a, b, n):
    return np.linspace(math.radians(a), math.radians(b), n)


def _dome(u, v, h):
    return h * np.sin(math.pi * np.clip(u, 0, 1)) * np.sin(math.pi * np.clip(v, 0, 1))


def _ridge(th, h, width=math.radians(30), center=0.0):
    d = np.abs((np.asarray(th) - center + math.pi) % (2 * math.pi) - math.pi)
    return h * np.clip(1 - d / width, 0, 1) ** 1.5


def _flutes(u, st, fade=1.0, n=None):
    """Fluting: crisp ridges across a plate (u 0..1), `n` of them (default the style's), times fade. The
    profile is (1 - |sin|)^2: narrow ridges between broad hollows, as hammered flutes read; rounded cos^2
    waves of the same depth vanished in the reflections."""
    if not st.flutes:
        return 0.0
    return st.flute_depth * np.asarray(fade) * (1 - np.abs(np.sin(math.pi * (n or st.flutes) * np.asarray(u)))) ** 2


UNDER_TORSO = ("ArmingDoublet", "Gambeson")
UNDER_LEGS = ("PaddedLeggings", "Leggings")


# ------------------------------------------------------------------ cuirass

def _torso_frame(B):
    P = _body(B, ["torso"])
    chest = P[(P[:, 2] > B.waist_z) & (P[:, 2] < B.neck_z - 0.05)]
    yc = float((chest[:, 1].min() + chest[:, 1].max()) / 2)
    return Frame([0.0, yc, 0.0], [0, 0, 1.0], [0, -1.0, 0])


def _torso_levels(B):
    ua = min(B.j["upperarm_l"][2], B.j["upperarm_r"][2])
    return dict(waist=B.waist_z, armpit=ua - 0.075, notch=B.neck_z - 0.03, shoulder=ua + 0.015)


def _interp_deg(th, table):
    d = np.degrees(np.abs(np.asarray(th)))
    xs, ys = zip(*table)
    return np.interp(d, xs, ys)


def _cuirass(B, st, coif="PlateCoif"):
    fr = _torso_frame(B)
    L = _torso_levels(B)
    P = np.vstack([_body(B, ["torso"]), _under(st.under_torso + (coif,), B, ["torso"])])
    sup = Support(fr, P, L["waist"] - 0.2, L["shoulder"] + 0.05)
    parts = []
    tor = {"spine_03": 0.75, "spine_02": 0.25}
    # breastplate: front +-100 deg, waist to a scooped neckline and armholes
    th = _span(-100, 100, _cols(33, st))
    top = _interp_deg(th, [(0, L["notch"]), (22, L["notch"] + 0.012), (40, L["shoulder"] - 0.02),
                           (58, L["armpit"] + 0.035), (75, L["armpit"]), (100, L["armpit"] - 0.005)])
    bot = L["waist"] - 0.02 - 0.012 * np.cos(th) ** 2          # dips a little in front
    bot = bot - st.point * np.clip(1 - np.abs(th) / math.radians(38), 0, 1) ** 1.2   # a pointed plackart
    off = lambda t, h, u, v: (st.gap + 0.006 + _ridge(h, st.ridge) + _flutes(u, st, ss(1.0, 0.55, v))
                              + 0.012 * np.sin(math.pi * np.clip((t - L["waist"]) / 0.25, 0, 1)) * np.cos(h) ** 4)
    g = Grid.sweep(fr, sup, th, bot, top, 14, off)
    g.roll("top", st.roll, TRIM if st.trim else STEEL).roll("bottom", st.roll * 0.6)
    for s in (1, -1):                                        # side straps to the backplate
        g.strap(L["waist"] + 0.05, L["waist"] + 0.085, s * math.radians(84), s * math.radians(99), st)
    parts.append(g.part(st, tor))
    # backplate: +-84 deg from the back, under the breastplate at the sides
    thb = _span(-90, 90, _cols(31, st)) + math.pi
    rel = thb - math.pi
    topb = _interp_deg(rel, [(0, L["notch"] + 0.045), (25, L["shoulder"] + 0.005), (50, L["armpit"] + 0.05),
                              (68, L["armpit"]), (90, L["armpit"] - 0.005)])
    offb = lambda t, h, u, v: st.gap + 0.002 + _flutes(u, st, ss(1.0, 0.55, v))
    gb = Grid.sweep(fr, sup, thb, L["waist"] - 0.03, topb, 12, offb)
    gb.roll("top", st.roll, TRIM if st.trim else STEEL).roll("bottom", st.roll * 0.6)
    parts.append(gb.part(st, tor))
    parts += _fauld(B, st, fr)
    parts += _tassets(B, st)
    return parts


def _fauld(B, st, fr):
    """Three hoops of lames below the breastplate, each tucked under the one above."""
    L = _torso_levels(B)
    P = np.vstack([_body(B, ["torso", "leg_l", "leg_r"]), _under(st.under_torso + st.under_legs, B, ["torso"])])
    P = P[P[:, 2] > L["waist"] - 0.25]
    sup = Support(fr, P, L["waist"] - 0.2, L["waist"] + 0.03)
    parts = []
    weights = ({"spine_02": 0.4, "spine_01": 0.6}, {"spine_01": 0.5, "pelvis": 0.5}, {"pelvis": 1.0})
    th = np.linspace(-math.pi, math.pi, 48, endpoint=False)
    for k in range(3):
        zt = L["waist"] - 0.005 - k * 0.042
        off = lambda t, h, u, v, k=k: st.gap + 0.003 - 0.0018 * k + 0.004 * v
        chev = st.point * 0.6 * np.clip(1 - np.abs(th) / math.radians(55), 0, 1)   # chevron lames
        g = Grid.sweep(fr, sup, th, zt - 0.052 - chev, zt - chev, 4, off, closed=True)
        g.roll("bottom", st.roll * 0.8, TRIM if st.trim else STEEL)
        front = th[np.abs(th) < math.radians(70)][::3]
        g.rivets(zt - 0.012 - st.point * 0.6 * np.clip(1 - np.abs(front) / math.radians(55), 0, 1), front, st)
        parts.append(g.part(st, weights[k]))
    return parts


def _tassets(B, st):
    """Two lames per side hanging from the fauld over the front of each thigh."""
    L = _torso_levels(B)
    parts = []
    for side in "lr":
        hip = B.j[f"thigh_{side}"]
        sign = 1.0 if hip[0] > 0 else -1.0
        fr = Frame([hip[0], hip[1], L["waist"] - 0.13], [0, 0, -1.0], [sign * 0.35, -1.0, 0])
        P = np.vstack([_body(B, [f"leg_{side}", "torso"]), _under(st.under_legs + st.under_torso, B, [f"leg_{side}"])])
        P = P[(np.abs(P[:, 0] - hip[0]) < 0.14) & (P[:, 2] < L["waist"] - 0.08)]
        sup = Support(fr, P, 0.0, 0.2)
        th = _span(-52, 52, 13)
        for k, (t0, t1) in enumerate(((0.0, 0.10), (0.085, 0.19))):
            off = lambda t, h, u, v, k=k: st.gap + 0.014 - 0.003 * k + 0.012 * v
            tip = st.point * 0.8 * np.clip(1 - np.abs(th) / math.radians(52), 0, 1) if k else 0.0
            g = Grid.sweep(fr, sup, th, t0, t1 + tip, 4, off)
            g.roll("top", st.roll, TRIM if st.trim else STEEL)                  # the lower edge
            g.rivets([t0 + 0.012] * 2, [math.radians(-35), math.radians(35)], st)
            parts.append(g.part(st, {"pelvis": 0.45, f"thigh_{side}": 0.55}))
    return parts


# ------------------------------------------------------------------ gorget

def _top_z(Q, rho, th, drho=0.012, dth=math.radians(9)):
    """Height field: highest z of points Q (in axis coordinates: rho, th, z) near each (rho, th)."""
    out = np.full(np.shape(rho), np.nan)
    for idx in np.ndindex(np.shape(rho)):
        d = np.abs((Q[:, 1] - th[idx] + math.pi) % (2 * math.pi) - math.pi)
        sel = (np.abs(Q[:, 0] - rho[idx]) < drho) & (d < dth)
        if sel.any():
            out[idx] = Q[sel, 2].max()
    return out


def _gorget(B, st, pre="Plate", coif="PlateCoif"):
    """A steel collar: an upright ring around the neck over the coif, then two lames draped over the top of
    the chest, back and shoulders (a height field of everything under it), each over the next. Covers the
    ring of padding between breastplate, coif and pauldrons."""
    nk = B.j["neck_01"]
    fr = Frame([0.0, nk[1] + 0.01, 0.0], [0, 0, 1.0], [0, -1.0, 0])
    P = np.vstack([B.co_raw[np.isin(B.part, ["torso", "neck"])],
                   _under(st.under_torso + (coif, pre + "Cuirass"), B, ["torso", "neck"])])
    q = P - fr.o
    Q = np.stack([np.hypot(q @ fr.c, q @ fr.b), np.arctan2(q @ fr.b, q @ fr.c), q[:, 2]], 1)
    Q = Q[np.abs(Q[:, 2] - nk[2]) < 0.2]
    cols = 48
    th = np.linspace(-math.pi, math.pi, cols, endpoint=False)
    parts = []
    # collar: upright, around the neck and coif
    z0, z1 = nk[2] - 0.035, nk[2] + 0.03
    near = P[(np.abs(P[:, 2] - nk[2]) < 0.12) & (np.hypot(P[:, 0] - fr.o[0], P[:, 1] - fr.o[1]) < 0.11)]
    sup = Support(fr, near, z0, z1)
    g = Grid.sweep(fr, sup, th, z0, z1, 4, lambda t, h, u, v: st.gap + 0.004 + 0.006 * (1 - v), closed=True)
    g.roll("top", st.roll, TRIM if st.trim else STEEL)
    parts.append(g.part(st, {"neck_01": 0.4, "spine_03": 0.6}))
    rho0 = sup(np.full(cols, z0), th) + st.gap + 0.01          # where the collar meets the lames
    # lames: from the collar outward; reach 7 cm in front and back, 9 cm over the shoulders
    reach = 0.07 + 0.02 * np.abs(np.sin(th))
    for k, (a, b) in enumerate(((0.0, 0.62), (0.52, 1.0))):
        f = np.linspace(a, b, 4)[:, None]
        R = rho0[None, :] + reach[None, :] * f
        Z = _top_z(Q, R, np.broadcast_to(th, R.shape))
        Z = np.where(np.isnan(Z), np.nanmin(Z), Z)
        raw = Z.copy()
        for _ in range(8):                  # smooth around, never below what's under it (the backplate's peak
            Z = 0.5 * Z + 0.25 * (np.roll(Z, 1, 1) + np.roll(Z, -1, 1))       # poked through), then never
            Z[1:-1] = 0.5 * Z[1:-1] + 0.25 * (Z[:-2] + Z[2:])                 # rising outward
            Z = np.maximum(Z, raw)
        Z = np.minimum.accumulate(Z, axis=0)
        Z = np.minimum(Z + st.gap + 0.006 - 0.003 * k, z0 + 0.005 - 0.004 * k)
        T = Z[::-1]                                               # rows by rising t: outer edge first
        g = Grid(fr, T, np.broadcast_to(th, T.shape), R[::-1], closed=True)
        g.polish[0] = 0.6
        parts.append(g.part(st, {"spine_03": 1.0, "neck_01": 0.0} if k else {"spine_03": 0.85, "neck_01": 0.15}))
    return parts


# ------------------------------------------------------------------ shoulders and arms

def _arm_points(B, side, under):
    P = np.vstack([_body(B, [f"arm_{side}", "torso"]), _under(under, B, [f"arm_{side}", "torso"])])
    return P


def _pauldrons(B, st, pre="Plate", coif="PlateCoif"):
    """A domed cop over the shoulder and three lames down the upper arm, each over the one below."""
    parts = []
    for side in "lr":
        a0, a1 = B.j[f"upperarm_{side}"], B.j[f"lowerarm_{side}"]
        sign = 1.0 if a0[0] > 0 else -1.0
        fr = Frame(a0, a1 - a0, [sign * 0.35, 0.0, 1.0])
        P = _arm_points(B, side, (pre + "Cuirass", coif, pre + "Gorget") + st.under_torso)
        P = P[np.linalg.norm(P - a0, axis=1) < 0.22]
        sup = Support(fr, P, -0.12, 0.2)
        plates = [(-0.10, 0.065, 105, 0.016, {f"clavicle_{side}": 0.5, f"upperarm_{side}": 0.5})]
        for k in range(st.pauldron_lames):
            t0 = 0.05 + k * 0.034
            plates.append((t0, t0 + 0.046, 88 - 6 * k, 0.0, {f"clavicle_{side}": 0.2 if k == 0 else 0.0,
                                                               f"upperarm_{side}": 0.8 if k == 0 else 1.0}))
        for k, (t0, t1, span, dome, w) in enumerate(plates):
            th = _span(-span, span, _cols(17 if k == 0 else 13, st))
            off = lambda t, h, u, v, k=k, dome=dome: (st.gap + 0.012 - 0.003 * k + _dome(u, v, dome) + _flutes(u, st)
                                                      + st.pauldron_flare * (1 + 0.3 * k) * np.asarray(v) ** 1.6
                                                      * (k > 0 or 0.6))
            tip = st.point * 0.45 * np.clip(1 - np.abs(th) / math.radians(span), 0, 1) if k else 0.0
            g = Grid.sweep(fr, sup, th, t0, t1 + tip, 8 if k == 0 else 4, off)
            g.roll("bottom" if k == 0 else "top", st.roll, TRIM if st.trim else STEEL)
            if k == 0:
                g.roll("top", st.roll * 0.5)
                if st.spikes:                                  # a crest of spikes along the cop, the middle longest
                    a = np.linspace(-0.9, 0.9, 5)
                    for j, x in enumerate(a):
                        g.spikes([t0 + 0.05], [x], st, st.spikes * (1.25 - 0.45 * abs(x)), lean=-0.35, r=0.018)
            else:
                g.rivets([(t0 + t1) / 2] * 2, [math.radians(-span + 10), math.radians(span - 10)], st)
            parts.append(g.part(st, {b: x for b, x in w.items() if x > 0}))
    return parts


def _cop(fr, sup, st, span, hl, dome, gap, outer):
    """A knee or elbow cop: an oval domed cup (+-span radians, +-hl metres along the limb) and a fan-shaped
    wing riveted over its outer side (outer = +1 / -1: the side of the frame's b axis). Returns grids."""
    th = np.linspace(-span, span, 15)
    e = np.clip(1 - np.abs(th / span) ** 2.5, 0, 1) ** 0.4
    e = np.maximum(e, 0.3)
    off = lambda t, h, u, v: gap + dome * np.clip(1 - (h / span) ** 2 - (t / hl) ** 2, 0, 1)
    cup = Grid.sweep(fr, sup, th, -hl * e, hl * e, 9, off)
    cup.roll("top", st.roll).roll("bottom", st.roll)
    # wing: from inside the cup's edge outward around the limb, widest in the middle, pointed at its end
    w0, w1 = 0.7 * span, span + math.radians(48)
    thw = outer * np.linspace(w0, w1, 9)
    sw = np.linspace(0, 1, 9)
    ew = 0.75 * hl * np.clip(np.sin(math.pi * (0.2 + 0.8 * sw)), 0.12, 1) ** 0.7
    offw = lambda t, h, u, v: gap + 0.004 + 0.004 * np.sin(math.pi * np.clip(u, 0, 1))
    wing = Grid.sweep(fr, sup, thw, -ew, ew, 5, offw)
    wing.roll("top", st.roll * 0.7).roll("bottom", st.roll * 0.7)
    wing.rivets([0.0], [outer * (w0 + 0.12)], st)
    return [cup, wing]


def _outer_side(fr, sign):
    """+1 if the frame's +b side (th = +90 deg) faces away from the body (x sign), else -1."""
    return 1.0 if fr.b[0] * sign > 0 else -1.0


def _arms(B, st, pre="Plate"):
    """Rerebrace (open on the inside), couter over the elbow, closed vambrace."""
    parts = []
    for side in "lr":
        a0, a1, a2 = B.j[f"upperarm_{side}"], B.j[f"lowerarm_{side}"], B.j[f"hand_{side}"]
        sign = 1.0 if a0[0] > 0 else -1.0
        L1, L2 = float(np.linalg.norm(a1 - a0)), float(np.linalg.norm(a2 - a1))
        P = np.vstack([_body(B, [f"arm_{side}"]), _under(st.under_torso, B, [f"arm_{side}"])])
        fr = Frame(a0, a1 - a0, [sign, 0.0, 0.0])
        sup = Support(fr, P, 0.3 * L1, 1.05 * L1)
        g = Grid.sweep(fr, sup, _span(-150, 150, 25), 0.52 * L1, 0.9 * L1, 5, lambda t, h, u, v: st.gap + 0.002)
        g.roll("top", st.roll).roll("bottom", st.roll * 0.6)
        parts.append(g.part(st, {f"upperarm_{side}": 1.0}))
        # couter: a cup over the point of the elbow (the back)
        fr = Frame(a1, a2 - a1, [0.0, 1.0, 0.0])
        sup = Support(fr, P, -0.08, 0.08)
        for g in _cop(fr, sup, st, math.radians(70), 0.055, 0.016, st.gap + 0.008, _outer_side(fr, sign)):
            parts.append(g.part(st, {f"upperarm_{side}": 0.5, f"lowerarm_{side}": 0.5}))
        # vambrace: a closed tube, flaring a little at the wrist
        fr = Frame(a1, a2 - a1, [sign, 0.0, 0.0])
        sup = Support(fr, P, 0.0, L2)
        g = Grid.sweep(fr, sup, np.linspace(-math.pi, math.pi, _cols(24, st, 4), endpoint=False), 0.14 * L2,
                       0.93 * L2, 6, lambda t, h, u, v: st.gap + 0.003 + 0.004 * v ** 2
                       + _flutes(u, st, 0.6, n=st.flutes and st.flutes + 3), closed=True)
        g.roll("top", st.roll).roll("bottom", st.roll)
        if st.spikes:                                          # a row of spikes down the outside, raked back
            g.spikes(np.linspace(0.35, 0.75, 3) * L2, [0.0] * 3, st, st.spikes * 0.6, lean=-0.7)
        parts.append(g.part(st, {f"lowerarm_{side}": 1.0}))
    return parts


def _gauntlets(B, st, pre="Plate"):
    """Over leather gloves: a flared cuff over the vambrace and a domed plate over the back of the hand."""
    parts = []
    for side in "lr":
        w, e = B.j[f"hand_{side}"], B.j[f"lowerarm_{side}"]
        sign = 1.0 if w[0] > 0 else -1.0
        P = np.vstack([_body(B, [f"arm_{side}", f"hand_{side}"]),
                       _under((pre + "Arms",) + st.under_hands + st.under_torso, B, [f"arm_{side}", f"hand_{side}"])])
        fr = Frame(w, e - w, [0.0, 0.0, 1.0])
        sup = Support(fr, P[np.linalg.norm(P - w, axis=1) < 0.14], -0.03, 0.09)
        g = Grid.sweep(fr, sup, np.linspace(-math.pi, math.pi, 24, endpoint=False), -0.015, 0.055, 4,
                       lambda t, h, u, v: st.gap * 0.6 + 0.002 + 0.007 * v ** 1.5, closed=True)
        g.roll("top", st.roll, TRIM if st.trim else STEEL)
        parts.append(g.part(st, {f"hand_{side}": 1.0}))
        # hand plate: from the wrist to the knuckles, over the back of the hand
        knuckle = B.j.get(f"middle_01_{side}", w + (w - e) * 0.4)
        Ph = B.co_raw[B.part == f"hand_{side}"]
        Ph = Ph[np.linalg.norm(Ph - w, axis=1) < float(np.linalg.norm(knuckle - w)) + 0.02]
        c = Ph - Ph.mean(0)
        n = np.linalg.svd(c, full_matrices=False)[2][2]           # thinnest direction: palm <-> back
        if n[0] * sign < 0:
            n = -n                                                 # the back of the hand faces out
        fr = Frame(w, knuckle - w, n)
        sup = Support(fr, np.vstack([Ph, _under(st.under_hands, B, [f"hand_{side}"])]), -0.02,
                      float(np.linalg.norm(knuckle - w)) + 0.02)
        Lk = float(np.linalg.norm(knuckle - w))
        g = Grid.sweep(fr, sup, _span(-55, 55, 11), 0.01, Lk + 0.008, 5,
                       lambda t, h, u, v: st.gap * 0.5 + 0.002 + _dome(u, v, 0.006))
        g.roll("top", st.roll * 0.8)
        parts.append(g.part(st, {f"hand_{side}": 1.0}))
        if st.claws:
            parts += _finger_plates(B, st, side, n)
    return parts


def _finger_plates(B, st, side, dorsal):
    """A small plate over the back of every finger segment, rigid on that segment's bone (so the gauntlet
    articulates with the fingers), the last one drawn out into a pointed claw."""
    parts = []
    Ph = B.co_raw[B.part == f"hand_{side}"]
    for f in ("thumb", "index", "middle", "ring", "pinky"):
        for i in (1, 2, 3):
            b = f"{f}_0{i}_{side}"
            if b not in B.j:
                continue
            h, tl = B.j[b], B.jt[b]
            ax = tl - h
            L = float(np.linalg.norm(ax))
            q = Ph - h
            tt = q @ (ax / L)
            near = (tt > -0.006) & (tt < L + 0.006) & (np.linalg.norm(q - np.outer(tt, ax / L), axis=1) < 0.02)
            if near.sum() < 12:
                continue
            fr = Frame(h, ax, dorsal)
            try:
                sup = Support(fr, Ph[near], -0.006, L + 0.006, band=0.01, step=0.004, nth=48, smooth=1)
            except ValueError:
                continue
            span = 95 if f == "thumb" else 80
            th = _span(-span, span, 9)
            claw = 0.024 * np.clip(1 - np.abs(th) / math.radians(span), 0, 1) ** 1.4 if i == 3 else 0.003
            off = lambda t, hh, u, v: st.gap * 0.4 + 0.0016 + _dome(u, v, 0.0025) - (0.004 * ss(L, L + 0.024, t) if i == 3 else 0.0)
            g = Grid.sweep(fr, sup, th, 0.001, L + claw, 3, off)
            parts.append(g.part(replace_style(st, thickness=0.0015), {b: 1.0}))
    return parts


def replace_style(st, **kw):
    import dataclasses
    return dataclasses.replace(st, **kw)


# ------------------------------------------------------------------ legs and feet

def _legs(B, st):
    """Cuisse over the front and sides of the thigh, poleyn over the knee, closed greave."""
    parts = []
    for side in "lr":
        h0, k0, a0 = B.j[f"thigh_{side}"], B.j[f"calf_{side}"], B.j[f"foot_{side}"]
        sign = 1.0 if h0[0] > 0 else -1.0
        Lt, Lc = float(np.linalg.norm(k0 - h0)), float(np.linalg.norm(a0 - k0))
        P = np.vstack([_body(B, [f"leg_{side}"]), _under(st.under_legs + ("Boots",), B, [f"leg_{side}"])])
        if st.cuisses:
            fr = Frame(h0, k0 - h0, [sign * 0.3, -1.0, 0.0])
            sup = Support(fr, P, 0.2 * Lt, 1.05 * Lt)
            g = Grid.sweep(fr, sup, _span(-110, 110, _cols(23, st)), 0.36 * Lt, 0.87 * Lt, 7,
                           lambda t, h, u, v: st.gap + 0.003 + _ridge(h, st.ridge * 0.6) + _flutes(u, st))
            g.roll("top", st.roll).roll("bottom", st.roll * 0.6)
            g.strap(0.55 * Lt, 0.6 * Lt, math.radians(96), math.radians(112), st, buckle=False)
            parts.append(g.part(st, {f"thigh_{side}": 1.0}))
        # poleyn
        fr = Frame(k0, a0 - k0, [0.0, -1.0, 0.0])
        sup = Support(fr, P, -0.1, 0.1)
        for i, g in enumerate(_cop(fr, sup, st, math.radians(78), 0.062, 0.018, st.gap + 0.01, _outer_side(fr, sign))):
            if i == 0 and st.spikes:
                g.spikes([0.0], [0.0], st, st.spikes * 0.55, lean=0.35)
            parts.append(g.part(st, {f"thigh_{side}": 0.5, f"calf_{side}": 0.5}))
        # greave: closed, a ridge down the shin
        fr = Frame(k0, a0 - k0, [0.0, -1.0, 0.0])
        sup = Support(fr, P, 0.0, Lc)
        g = Grid.sweep(fr, sup, np.linspace(-math.pi, math.pi, _cols(28, st, 4), endpoint=False), 0.1 * Lc,
                       0.9 * Lc, 9, lambda t, h, u, v: st.gap + 0.004 + _ridge(h, st.ridge * 0.8, math.radians(25))
                       + _flutes(u, st, ss(0.0, 0.3, v) * ss(1.0, 0.7, v), n=st.flutes and st.flutes + 3),
                       closed=True)
        g.roll("top", st.roll).roll("bottom", st.roll)
        parts.append(g.part(st, {f"calf_{side}": 1.0}))
    return parts


def _sabatons(B, st):
    """Lames over the top of the foot (over the boot) and a toe cap."""
    parts = []
    for side in "lr":
        a, ball = B.j[f"foot_{side}"], B.j[f"ball_{side}"]
        P = np.vstack([_body(B, [f"foot_{side}"]), _under(("Boots",), B, [f"foot_{side}"])])
        fr = Frame(a, ball - a, [0.0, 0.0, 1.0])
        Lb = float(np.linalg.norm(ball - a))
        sup = Support(fr, P, -0.02, Lb + 0.08)
        plates = [(0.0 + k * 0.026, 0.034 + k * 0.026, {f"foot_{side}": 1.0}) for k in range(4)]
        plates[-1] = plates[-1][:2] + ({f"foot_{side}": 0.5, f"ball_{side}": 0.5},)
        plates.append((Lb - 0.012, Lb + 0.062, {f"ball_{side}": 1.0}))
        for k, (t0, t1, w) in enumerate(plates):
            span = 78 if k < len(plates) - 1 else 70
            off = lambda t, h, u, v, k=k: st.gap * 0.6 + 0.002 + 0.0015 * k
            g = Grid.sweep(fr, sup, _span(-span, span, 13), t0, t1, 3, off)
            g.roll("bottom", st.roll * 0.6)
            parts.append(g.part(st, w))
    return parts


# ------------------------------------------------------------------ helm

def _helm(Hs, st, coif_name="PlateCoif"):
    """A bascinet over the mail coif: a dome from the crown down to a rim over the brow in front, down past
    the ears at the sides and to the nape at the back (open face), with a crest, a rolled rim and a row of
    rivets for the aventail line. Built as rings of polar angle around a centre above the eyes."""
    coif = _under((coif_name,))
    P = np.vstack([Hs.co, coif[coif[:, 2] > Hs.eye_z - 0.08]]) if len(coif) else Hs.co
    c = np.array([Hs.cx, Hs.cy + 0.005, Hs.eye_z + 0.02])
    Q = P - c
    closed = st.helm == "closed"
    cols, rows = (96 if st.flutes else 48), (20 if closed else 13)
    brow_al = math.pi / 2 - 0.04                # polar angle of the brow ridge, just above the eye slit
    th = np.linspace(-math.pi, math.pi, cols, endpoint=False)          # 0 = front (-y)

    def dirs(t, al):
        t, al = np.asarray(t, float), np.asarray(al, float)
        return np.stack([np.sin(al) * np.sin(t), -np.sin(al) * np.cos(t), np.cos(al)], -1)

    def R(t, al):
        D = dirs(t, al).reshape(-1, 3)
        s = (Q @ D.T).max(0).reshape(np.shape(al))
        fade = ss(1.3, 0.2, al)
        crest = (_ridge(t, st.ridge, math.radians(14)) * (1.0 if closed else fade)
                 + _ridge(t, st.ridge, math.radians(14), math.pi) * fade)
        # a closed visor comes to a keel in front of the face
        snout = 0.0
        if closed:                              # a keeled visor below the slit, a brow ridge over it
            fr_ = np.clip(np.cos(t), 0, 1)
            snout = (0.04 * fr_ ** 8 * ss(1.3, 2.15, al)                     # the keel, forward to a point
                     + 0.008 * fr_ ** 2 * np.exp(-((al - brow_al) / 0.07) ** 2))
            # a narrow jaw: the lower sides pinch in (the head is hidden under a closed helm, so the helm may
            # cut into it)
            snout = snout - s * 0.14 * np.abs(np.sin(t)) ** 1.5 * ss(1.55, 2.3, al)
        fl = _flutes((np.asarray(t) + math.pi) / (2 * math.pi), st, ss(0.25, 0.7, al) * ss(1.7, 1.2, al),
                     n=2 * st.flutes + 2) if st.flutes else 0.0
        # a sallet's tail: the back flares out over the nape, more toward the rim
        tail = st.helm_tail * np.clip(-np.cos(t), 0, 1) ** 1.5 * ss(1.1, 2.0, al) ** 2
        return s + st.gap + 0.004 + crest + fl + tail + snout

    # rim over the brow in front (the cap's is 4.75 cm above the eyes), dropping past the temples to the jaw
    if closed:                                  # down to the chin all round (an eye slit is cut below)
        zr = Hs.eye_z + _interp_deg(th, [(0, -0.155), (40, -0.14), (90, -0.1), (180, -0.078)])
    elif st.helm == "sallet":                    # open face, cheeks cut higher, a long tail at the back
        zr = Hs.eye_z + _interp_deg(th, [(0, 0.052), (30, 0.048), (50, 0.02), (65, -0.015), (100, -0.035),
                                         (140, -0.07), (180, -0.085)])
    else:
        zr = Hs.eye_z + _interp_deg(th, [(0, 0.052), (30, 0.048), (48, 0.025), (60, -0.030), (90, -0.048),
                                         (180, -0.062)])
    alf = np.linspace(0.0, 2.4, 121)
    arim = np.zeros(cols)
    for j in range(cols):
        z = c[2] + np.cos(alf) * R(np.full_like(alf, th[j]), alf)
        k = np.argmax(z <= zr[j]) if (z <= zr[j]).any() else len(alf) - 1
        arim[j] = alf[max(k, 1)]
    for _ in range(3):                                                   # a smooth rim line
        arim = 0.5 * arim + 0.25 * (np.roll(arim, 1) + np.roll(arim, -1))
    AL = np.linspace(0, 1, rows)[1:, None] * arim[None, :]              # rows below the pole
    TH = np.broadcast_to(th[None, :], AL.shape)
    RR = R(TH, AL)
    # rolled rim: a bead below the last ring, curling outward
    r = st.roll * 1.2
    beads = []
    BEAD = (0.35 * math.pi, 0.7 * math.pi, math.pi, 1.35 * math.pi, 1.8 * math.pi)
    for p in BEAD:
        al = arim + r * math.sin(p) / RR[-1]
        beads.append((al, RR[-1] + r * (1 - math.cos(p))))
    AL = np.vstack([AL] + [b[0][None] for b in beads])
    RR = np.vstack([RR] + [b[1][None] for b in beads])
    TH = np.broadcast_to(th[None, :], AL.shape)
    pts = c + dirs(TH, AL) * RR[..., None]
    pole = c + np.array([0, 0, 1.0]) * float(R(np.array([0.0]), np.array([0.0]))[0])
    V = np.vstack([pole[None], pts.reshape(-1, 3)])
    nr = AL.shape[0]
    idx = lambda k, j: 1 + k * cols + (j % cols)
    F = [(0, idx(0, j + 1), idx(0, j)) for j in range(cols)]
    F += [(idx(k, j), idx(k, j + 1), idx(k + 1, j + 1), idx(k + 1, j)) for k in range(nr - 1) for j in range(cols)]
    F = A._outward(V, F, c)
    if closed:                                  # the eye slit: a band across the front at eye height
        Va = np.asarray(V)
        keep = []
        for f in F:
            q = Va[list(f)].mean(0)
            ang = math.atan2(q[0] - c[0], -(q[1] - c[1]))
            if abs(ang) < math.radians(58) and Hs.eye_z - 0.007 < q[2] < Hs.eye_z + 0.013:
                continue
            keep.append(f)
        F = keep
    nb = len(BEAD)
    pol = np.r_[0.0, np.zeros((nr - nb) * cols), np.ones(nb * cols)]
    pol[1 + (nr - nb - 1) * cols:1 + (nr - nb) * cols] = 0.6
    mat = np.r_[STEEL, np.full((nr - nb) * cols, STEEL), np.full(nb * cols, TRIM if st.trim else STEEL)]
    fr = Frame(c, [0, 0, 1.0], [0, -1.0, 0])
    ratio = AL / np.maximum(arim[None, :], 1e-6)          # 0 crown .. 1 rim (beads beyond)
    band = ss(0.3, 0.38, ratio) * ss(0.56, 0.48, ratio)       # a band round the skull
    orn = np.r_[0.0, (band * st.ornament).ravel()]
    V, F, src = _rim(V, F, st.thickness, fr)
    pol = np.r_[pol, np.ones(len(src))]
    mat = np.r_[mat, mat[src]]
    orn = np.r_[orn, np.zeros(len(src))]
    det = np.zeros(len(V))
    # rivets for the aventail: a ring 1.8 cm above the rim, back and sides
    sel = np.abs(th) > math.radians(70)
    ar = arim[sel] - 0.018 / RR[nr - nb - 1, sel]
    rp = c + dirs(th[sel], ar) * (R(th[sel], ar) + 0.0005)[:, None]
    rn = C._unit(rp - c)
    SV, SF = A.studs(rp[::2], rn[::2], r=st.rivet_r, h=st.rivet_r * 0.7)
    n = len(V)
    V = np.vstack([V, SV])
    F = list(F) + [tuple(i + n for i in f) for f in SF]
    det = np.r_[det, np.ones(len(SV))]
    pol = np.r_[pol, np.ones(len(SV))]
    mat = np.r_[mat, np.full(len(SV), TRIM if st.trim else STEEL)]
    orn = np.r_[orn, np.zeros(len(SV))]
    if closed:                                  # a dark liner behind the eye slit: it reads as a black gap
        fcols = th[np.abs(th) < math.radians(72)]
        rows_l = []
        for tj in fcols:
            zc = c[2] + np.cos(alf) * R(np.full_like(alf, tj), alf)
            k = int(np.argmax(zc <= Hs.eye_z + 0.002)) if (zc <= Hs.eye_z + 0.002).any() else len(alf) // 2
            rows_l.append(alf[k] + np.linspace(-0.32, 0.32, 5))
        ALl = np.array(rows_l).T                                  # (5, n)
        THl = np.broadcast_to(fcols[None, :], ALl.shape)
        LP = c + dirs(THl, ALl) * (R(THl, ALl) - 0.009)[..., None]
        nrl, ncl = ALl.shape
        LV = LP.reshape(-1, 3)
        LF = [(k * ncl + j, k * ncl + j + 1, (k + 1) * ncl + j + 1, (k + 1) * ncl + j)
              for k in range(nrl - 1) for j in range(ncl - 1)]
        LF = A._outward(LV, LF, c)
        n = len(V)
        V = np.vstack([V, LV])
        F = list(F) + [tuple(i + n for i in f) for f in LF]
        det = np.r_[det, np.zeros(len(LV))]
        pol = np.r_[pol, np.zeros(len(LV))]
        mat = np.r_[mat, np.full(len(LV), STEEL)]
        orn = np.r_[orn, np.zeros(len(LV))]
    if st.horns:                                # two horns from the temples, up and back
        for sgn in (1.0, -1.0):
            t0h, a0h = sgn * math.radians(46), 0.62
            d0 = dirs(np.array([t0h]), np.array([a0h]))[0]
            base = c + d0 * float(R(np.array([t0h]), np.array([a0h]))[0])
            side, up, back = np.array([sgn, 0, 0.0]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0])
            Lh = st.horns
            HV, HF = horn_mesh(base - d0 * 0.012, base + d0 * Lh * 0.35 + side * Lh * 0.12,
                               base + (up * 0.8 + side * 0.3 + back * 0.5) * Lh, r0=0.028)
            n = len(V)
            V = np.vstack([V, HV])
            F = list(F) + [tuple(i + n for i in f) for f in HF]
            det = np.r_[det, np.zeros(len(HV))]
            pol = np.r_[pol, np.full(len(HV), 0.3)]
            mat = np.r_[mat, np.full(len(HV), STEEL)]
            orn = np.r_[orn, np.zeros(len(HV))]
    return [(V, F, None, "shell", dict(detail=det, polish=pol, mat=mat, orn=orn,
                                       orn_pat=np.full(len(V), float(st.ornament_pattern + 10 * st.ornament_mode))))]


def horn_mesh(P0, P1, P2, r0=0.022, rings=14, seg=8):
    """A tapering, ridged horn along a quadratic Bezier P0 -> P2 (control P1), closed at the tip."""
    V, F = [], []
    ref = np.array([0.0, 0.0, 1.0])
    for k in range(rings):
        s_ = k / (rings - 1)
        p = (1 - s_) ** 2 * P0 + 2 * (1 - s_) * s_ * P1 + s_ ** 2 * P2
        tg = C._unit(2 * (1 - s_) * (P1 - P0) + 2 * s_ * (P2 - P1))
        e1 = C._unit(np.cross(tg, ref) if abs(tg @ ref) < 0.95 else np.cross(tg, [1.0, 0, 0]))
        e2 = np.cross(tg, e1)
        r = r0 * (1 - s_) ** 0.85 + 0.0008
        r *= 1 + 0.07 * math.sin(34 * s_) * (s_ < 0.8)
        for a in range(seg):
            ang = a * 2 * math.pi / seg
            V.append(p + (e1 * math.cos(ang) + e2 * math.sin(ang)) * r)
    V.append(P2 + C._unit(P2 - P1) * 0.004)
    tip = len(V) - 1
    for k in range(rings - 1):
        for a in range(seg):
            b = (a + 1) % seg
            F.append((k * seg + a, k * seg + b, (k + 1) * seg + b, (k + 1) * seg + a))
    k = rings - 1
    for a in range(seg):
        F.append((k * seg + a, k * seg + (a + 1) % seg, tip))
    V = np.array(V)
    # wind outward: check a side face against the axis
    f = F[seg // 2]
    n = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
    ctr = (1 - 0.0) ** 2 * P0
    if n @ (V[f[0]] - ctr) < 0 and n @ (V[f[0]] - V[:seg].mean(0)) < 0:
        F = [tuple(reversed(x)) for x in F]
    return V, F


# ------------------------------------------------------------------ garments and sets

def _back_cape(B, under, span_deg=62, hem_drop=0.06, flare=0.12):
    """A cape hung from the backplate under the pauldrons (fantasy knights): from the shoulder blades to below
    the knees, +-span around the back, clearing what's worn under it and the arms as they swing; skinned like
    the cloak (spine, then pelvis and thighs by height)."""
    import hum_cloak as K
    fr = _torso_frame(B)
    L = _torso_levels(B)
    z_top = L["armpit"] + 0.06
    z_hem = float(min(B.j["calf_l"][2], B.j["calf_r"][2])) - hem_drop
    arm = []
    Lr = float(np.linalg.norm(B.j["hand_l"] - B.j["upperarm_l"])) + 0.06
    for sd in "lr":
        a = B.j[f"upperarm_{sd}"]
        for swing in (0.0, math.radians(20), math.radians(38)):         # hanging, swung back when walking
            d = np.array([0.0, math.sin(swing), -math.cos(swing)])
            for u in np.linspace(0.1, 1.0, 12):
                c = a + d * Lr * u
                for ang in np.linspace(0, 2 * math.pi, 10, endpoint=False):
                    arm.append(c + 0.055 * np.array([math.cos(ang), math.sin(ang), 0.0]))
    P = np.vstack([_body(B, ["torso", "leg_l", "leg_r"]), np.array(arm), _under(under, B)])
    sup = Support(fr, P, z_hem - 0.05, z_top + 0.05, band=0.03)
    th = math.pi + _span(-span_deg, span_deg, 67)          # 6 columns per fold
    zz = np.linspace(z_hem, z_top, 16)
    T = np.broadcast_to(zz[:, None], (16, len(th))).copy()
    TH = np.broadcast_to(th[None, :], T.shape)
    down = (z_top - T) / (z_top - z_hem)
    Rr = sup(T, TH)
    for k in range(len(zz) - 2, -1, -1):                                  # never narrower going down
        Rr[k] = np.maximum(Rr[k], Rr[k + 1])
    # gathered at the top (pleats from the start), deeper folds and flare toward the hem
    Rr = Rr + 0.02 + flare * down ** 1.3 + (0.008 + 0.022 * down) * np.sin(11 * (TH - math.pi))
    g = Grid(fr, T, TH, Rr)
    V, F = g._faces()
    V, F = C.add_rim(V, F, 0.004, B)
    return [(V, F, None, "skirt", np.zeros(len(V)), K.cloak_weights(B))]


def plate_garments(style="Munition", prefix="Plate", coif=None):
    """GARMENTS entries for one plate style, in build order (each reads the ones before it): <prefix>Coif (mail,
    under the plates), Cuirass, Pauldrons, Arms, Gauntlets, Legs, Sabatons, Helm (over the coif).
    Registered in hum_cloth after the cloak. coif: reuse another style's coif (the mail is the same); False =
    no coif (a closed helm over a bodysuit)."""
    import hum_cloak as K
    st = STYLES[style]
    R = C.REGIONS
    p = prefix
    cf = None if coif is False else (coif or p + "Coif")
    g = {
        # the mail coif first: its cape is worn under the plates (they stand off it), so its hem never
        # fights a plate edge
        p + "Coif": dict(slot="head", layer=3, material="mail", headgear=True, hoodcut=True, cover=[],
                         hide=[R["neck"], R["collar"]],
                         build=lambda Hs: K._cloak_hood(Hs, peak=False, off=0.022, drop=0.06, flare=0.012,
                                                        over=("ArmingDoublet",))),
        p + "Cuirass": dict(slot="armor", layer=4, material="plate", build=lambda B: _cuirass(B, st, cf),
                            hide=[R["chest"], R["belly"]], cover=[],
                            # nothing under it is clipped: the chest region reaches past the breastplate's top
                            # and the belly past the flanks, where breast and back plates only overlap.
                            # The pelvis stays: it runs down the back of the thigh, which a running or sitting
                            # stride pulls out from under the fauld (a hole over a bodysuit; leggings hide it
                            # themselves)
                            excludes=["Belt", "Apron", "Cloak", "CloakHood"]),
        p + "Gorget": dict(slot="gorget", layer=5, material="plate", build=lambda B: _gorget(B, st, p, cf),
                           hide=[], cover=[]),
        p + "Pauldrons": dict(slot="shoulders", layer=5, material="plate", build=lambda B: _pauldrons(B, st, p, cf),
                              hide=[], cover=[]),
        p + "Arms": dict(slot="bracers", layer=4, material="plate", build=lambda B: _arms(B, st, p),
                         hide=[], cover=[]),               # the forearm region starts above the vambrace
        p + "Gauntlets": dict(slot="gauntlets", layer=5, material="plate", build=lambda B: _gauntlets(B, st, p),
                              hide=[], cover=[]),
        p + "Legs": dict(slot="shins", layer=4, material="plate", build=lambda B: _legs(B, st),
                         hide=[R["shin_low"]], cover=[R["shin_low"]]),   # shin_up reaches behind the knee
        p + "Sabatons": dict(slot="sabatons", layer=4, material="plate", build=lambda B: _sabatons(B, st),
                             hide=[], cover=[]),
        p + "Helm": dict(slot="helm", layer=5, material="plate", headgear=True, build=lambda Hs: _helm(Hs, st, cf),
                         hide=[], cover=[]),
    }
    if coif is not None:                          # another style's coif, or none
        del g[p + "Coif"]
    for rec in g.values():
        if st.group and rec["material"] == "plate":
            rec["group"] = st.group
    if st.helm == "closed":                       # nothing of the hair, beard or brows shows
        g[p + "Helm"].update(hides_hair=True, hides_face_hair=True, hides_head=True)
    return g


PLATE = {
    # the arming doublet: the gambeson without its skirt (tassets and cuisses cover the thighs)
    "ArmingDoublet": dict(A.ARMOR["Gambeson"], build=lambda B: A._coat(B, off0=0.02, closure=False, collar=False,
                                                                        skirt=False, hem_z=B.waist_z - 0.07)),
    # (its hem ends under the fauld: without the gambeson's skirt panels the shell's cut edge showed)
}
PLATE.update(plate_garments("Munition", "Plate"))
PLATE.update(plate_garments("Gothic", "Gothic", coif="PlateCoif"))
PLATE.update({
    # the body as the under-layer: the body shader paints it as dark cloth (no geometry, nothing to clip)
    "Bodysuit": dict(slot="suit", layer=0, material="suit", bodysuit=True, group="Suit", hide=[], cover=[]),
})
PLATE.update(plate_garments("BlackKnight", "Knight", coif=False))
PLATE.update(plate_garments("Ornate", "Ornate", coif=False))
PLATE["KnightCape"] = dict(slot="cloak", layer=5, material="cloth", group="Suit", hide=[], cover=[],
                           build=lambda B: _back_cape(B, ("KnightCuirass", "KnightGorget", "KnightLegs")))

PLATE_SETS = {
    "Plate": ["PaddedLeggings", "ArmingDoublet", "Gloves", "Boots", "PlateCoif", "PlateCuirass", "PlateGorget",
              "PlatePauldrons",
              "PlateArms", "PlateGauntlets", "PlateLegs", "PlateSabatons", "PlateHelm"],
    "Gothic Plate": ["PaddedLeggings", "ArmingDoublet", "Gloves", "Boots", "PlateCoif", "GothicCuirass",
                     "GothicGorget", "GothicPauldrons", "GothicArms", "GothicGauntlets", "GothicLegs",
                     "GothicSabatons", "GothicHelm"],
    "Ornate Plate": ["Bodysuit", "Boots", "OrnateCuirass", "OrnateGorget", "OrnatePauldrons", "OrnateArms",
                     "OrnateGauntlets", "OrnateLegs", "OrnateSabatons", "OrnateHelm"],
    "Black Knight": ["Bodysuit", "Boots", "KnightCuirass", "KnightGorget", "KnightPauldrons",
                     "KnightArms", "KnightGauntlets", "KnightLegs", "KnightSabatons", "KnightHelm", "KnightCape"],
}
