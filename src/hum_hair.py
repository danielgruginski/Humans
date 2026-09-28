"""Hair, beards and eyebrows as solid stylised clumps, bound to the head so they follow every face key.

Pieces:
  cap     an offset shell of the skin inside the hair/beard region, so no skin shows between clumps
  clumps  tapered, flattened tubes grown from roots along a style's comb direction, kept outside the head

Per-loop data for the hair shader:
  UV "UVMap"  u around the clump, v along it (strand texture, tiles)
  UV "Clump"  x = random per clump (0..1; the cap uses 1.0), y = root -> tip (0..1)
"""
import math
import os
import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import hum_paint

HAIR_COL = "HUM_Hair"
ss = hum_paint.smoothstep


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def _tangent(d, n):
    return _unit(d - n * float(np.dot(d, n)))


# ------------------------------------------------------------------ head frame

class HeadFrame:
    """Neutral-head landmarks and a BVH for keeping hair outside the skin."""

    # hairline height above the eye centres, by angle around the head (0 front, 180 back)
    HAIRLINE = [(0, 0.062), (30, 0.058), (52, 0.046), (66, 0.034), (72, 0.010), (78, -0.018), (84, -0.018),
                (88, 0.004), (96, 0.006), (106, 0.0), (118, -0.025), (145, -0.052), (180, -0.062)]

    def __init__(self, head):
        self.head = head
        me = head.data
        nh = head["n_head_verts"]
        B = np.array([d.co[:] for d in me.shape_keys.key_blocks["Basis"].data]) if me.shape_keys \
            else np.array([v.co[:] for v in me.vertices])
        self.co = B[:nh]
        self.F = hum_paint.Face(head)
        self.eye_z = float(self.F.eye['l'][0][2])
        self.top = self.co[np.argmax(self.co[:, 2])]
        self.cy = float(self.top[1])
        ears = hum_paint.group_weights(head, "ears")[:nh] > 0.5
        self.ear_co = self.co[ears]
        lips = hum_paint.group_weights(head, "lips")[:nh] > 0.5
        self.lip_co = self.co[lips]
        self.ear_y_front = float(self.ear_co[:, 1].min())
        self.faces = [tuple(p.vertices) for p in me.polygons if p.material_index == 0]
        self.bvh = self._bvh(self.co)                 # the real skin: caps are projected onto it
        self.ear_verts = np.where(self.ear_dist(self.co) < 0.004)[0]
        self.lip_verts = np.where(self.lip_dist(self.co) < 0.0015)[0]
        self.proxy = self._ear_domes(self.co)
        self.bvh_hair = self._bvh(self.proxy)         # clumps collide with this (no ear folds)
        self.domes = True                             # False: collide with the real skin (styles above the ears)
        self.crown = np.array([0.0, self.cy + 0.035, self.top[2] - 0.012])

    def _bvh(self, P):
        bm = bmesh.new()
        verts = [bm.verts.new(p) for p in P]
        for f in self.faces:
            bm.faces.new([verts[i] for i in f])
        bm.normal_update()
        t = BVHTree.FromBMesh(bm)
        bm.free()
        return t

    def _ear_domes(self, P):
        """Head with each ear smoothed into a dome, so hair drapes over the ear instead of into it."""
        P = P.copy()
        for sgn in (1.0, -1.0):
            E = self.ear_co[self.ear_co[:, 0] * sgn > 0]
            c = E.mean(0)
            ry = (E[:, 1].max() - E[:, 1].min()) * 0.6 + 0.004
            rz = (E[:, 2].max() - E[:, 2].min()) * 0.6 + 0.004
            peak = np.abs(E[:, 0]).max() + 0.002
            side = P[:, 0] * sgn > 0.03
            dy, dz = (P[:, 1] - c[1]) / ry, (P[:, 2] - c[2]) / rz
            dome = peak * np.exp(-0.5 * (dy * dy + dz * dz) ** 1.5)
            ax = np.abs(P[:, 0])
            k = 0.006
            smax = (ax + dome + np.sqrt((ax - dome) ** 2 + k * k)) / 2      # smooth max
            P[:, 0] = np.where(side, sgn * smax, P[:, 0])
        # relax the crease where the domes meet the head
        nb = [[] for _ in range(len(P))]
        for f in self.faces:
            for a, b in zip(f, f[1:] + f[:1]):
                nb[a].append(b)
                nb[b].append(a)
        zone = np.where(self.ear_dist(P) < 0.04)[0]
        base_ax = np.abs(self.co[:, 0])
        for _ in range(12):
            Q = P.copy()
            for i in zone:
                if nb[i]:
                    Q[i] = P[i] * 0.4 + P[nb[i]].mean(0) * 0.6
            ax = np.maximum(np.abs(Q[zone, 0]), base_ax[zone])
            Q[zone, 0] = np.sign(self.co[zone, 0] + 1e-9) * ax
            P = Q
        return P

    def theta(self, P):
        return np.degrees(np.arctan2(np.abs(P[..., 0]), -(P[..., 1] - self.cy)))

    def hairline_z(self, P, recede=0.0):
        th, dz = zip(*self.HAIRLINE)
        z = np.interp(self.theta(P), th, dz) + self.eye_z
        return z + recede * np.interp(self.theta(P), [0, 40, 60, 80], [0.025, 0.03, 0.02, 0.0])

    def ear_dist(self, P):
        d = np.full(P.shape[:-1], 1.0)
        for e in self.ear_co[::3]:
            d = np.minimum(d, np.linalg.norm(P - e, axis=-1))
        return d

    def lip_dist(self, P):
        d = np.full(P.shape[:-1], 1.0)
        for e in self.lip_co:
            d = np.minimum(d, np.linalg.norm(P - e, axis=-1))
        return d

    def hair_mask(self, P, recede=0.0, soft=0.004):
        up = ss(-soft, soft, P[..., 2] - self.hairline_z(P, recede))
        return up * ss(0.004, 0.010, self.ear_dist(P))

    def beard_mask(self, P, cheeks=0.5, chin_only=False, no_mustache=False, mustache_only=False,
                   sideburns=False, jaw_band=0.0, **_):
        F = self.F
        x, y, z = P[..., 0], P[..., 1], P[..., 2]
        ax = np.abs(x)
        if mustache_only:
            return ss(F.mouth[2] + 0.004, F.mouth[2] + 0.008, z) \
                * ss(F.nose_tip[2] - 0.004, F.nose_tip[2] - 0.010, z) \
                * ss(F.mouth_w * 0.8, F.mouth_w * 0.6, ax) * ss(F.mouth[1] + 0.03, F.mouth[1] + 0.012, y)
        cheek_line = F.eye['l'][0][2] - 0.045 + 0.014 * cheeks - 0.22 * (ax - 0.03)
        rise = np.zeros_like(z)
        if sideburns:
            # the beard's upper edge curves smoothly up in front of the ear into the hair's sideburn
            # (no separate strip, no corner): rise = 0 on the cheek .. 1 at the ear
            yf = self.ear_y_front
            rise = ss(yf - 0.05, yf - 0.004, y) ** 1.2 * ss(0.035, 0.05, ax)
            cheek_line = cheek_line + (self.eye_z + 0.006 - cheek_line) * rise
        m = ss(cheek_line + 0.003, cheek_line - 0.006, z)
        if jaw_band:
            # chin strap: a band of this height along the jawline (from below the ear down to the chin)
            yf = self.ear_y_front
            t = np.clip((yf - y) / (yf - F.chin[1]), 0, 1)
            z0 = float(self.ear_co[:, 2].min()) - 0.012
            jaw_z = z0 + (F.chin[2] - 0.022 - z0) * t
            band = ss(jaw_z + jaw_band + 0.004, jaw_z + jaw_band - 0.004, z)
            m *= np.maximum(band, ss(0.3, 0.8, rise))
        m *= ss(self.ear_y_front + 0.004, self.ear_y_front - 0.008, y)
        # down the neck only a little under the jaw
        m *= ss(F.chin[2] - 0.036, F.chin[2] - 0.022, z) * ss(F.mouth[1] + 0.085, F.mouth[1] + 0.06, y)
        m *= ss(0.002, 0.005, self.lip_dist(P))                                 # hug the lips, no skin ring
        m *= 1 - ss(F.nose_tip[2] - 0.013, F.nose_tip[2] - 0.008, z) * ss(0.028, 0.018, ax)   # not up the nose
        if chin_only:
            m *= ss(0.036, 0.026, ax) * ss(F.chin[1] + 0.03, F.chin[1] + 0.015, y)   # front of the chin only
        if no_mustache:                               # only in front of the face (keeps the sideburns)
            m *= 1 - ss(F.mouth[2] + 0.002, F.mouth[2] + 0.007, z) * ss(0.05, 0.035, ax)
        return m

    def body_bvh(self):
        """The body (rest shape) for hair to lie on: long hair rests over clothes, not inside the torso."""
        if not hasattr(self, "_body_bvh"):
            import bpy
            body = bpy.data.objects.get("Body")
            if body is None:
                self._body_bvh = None
            else:
                me = body.data
                kb = me.shape_keys.key_blocks[0] if me.shape_keys else None
                co = [tuple(d.co) for d in kb.data] if kb else [tuple(v.co) for v in me.vertices]
                self._body_bvh = BVHTree.FromPolygons(co, [tuple(p.vertices) for p in me.polygons])
        return self._body_bvh

    def face_guard(self, radial=True, front=True, body=True, clearance=0.025):
        """For head hair, a last say over each growth step:
        radial  below the widest part of the back of the skull, a clump may not tuck in toward the head's
                vertical axis: long hair falls as a curtain instead of following the occiput in and wrapping
                the neck like a sleeve
        front   beside and below the face (in front of the ears) no moving toward the middle or forward:
                long hair hangs beside the jaw instead of being pulled onto the throat
        body    keep `clearance` off the body (over clothes up to a jerkin), pushed out along its normal"""
        mouth_z = float(self.F.mouth[2]) + 0.01
        # the widest level of the back of the skull (about 4 cm above the eyes): below it hair falls straight
        back = self.co[(self.co[:, 1] - self.cy) > 0.02]
        rr = np.hypot(back[:, 0], back[:, 1] - self.cy)
        zs = np.arange(self.eye_z - 0.04, self.eye_z + 0.1, 0.01)
        rz = [rr[np.abs(back[:, 2] - z) < 0.006].max(initial=0.0) for z in zs]
        wide_z = float(zs[int(np.argmax(rz))])
        front_y = self.ear_y_front + 0.01
        cy = self.cy
        bvh = self.body_bvh() if body else None

        def guard(prev, p):
            p = np.array(p, float)
            if radial and p[2] < wide_z and prev[2] < wide_z + 0.02:
                if True:
                    r0 = math.hypot(prev[0], prev[1] - cy)
                    r1 = math.hypot(p[0], p[1] - cy)
                    if 1e-6 < r1 < r0:
                        k = r0 / r1
                        p[0] *= k
                        p[1] = cy + (p[1] - cy) * k
            if p[2] < mouth_z:
                if front and p[1] < front_y:
                    if abs(p[0]) < abs(prev[0]):
                        p[0] = prev[0]
                    if p[1] < prev[1]:
                        p[1] = prev[1]
            if bvh is not None and p[2] < mouth_z:
                loc, n, i, d = bvh.find_nearest(Vector(p))
                if loc is not None:
                    n = np.array(n)
                    h = float(np.dot(p - np.array(loc), n))
                    if h < clearance:
                        p = p + n * (clearance - h)
            return p
        return guard

    def nearest(self, p):
        """Nearest point on the hair collision surface (skin with the ears domed over)."""
        loc, n, i, d = (self.bvh_hair if self.domes else self.bvh).find_nearest(Vector(p))
        return np.array(loc), np.array(n), d

    def nearest_skin(self, p):
        loc, n, i, d = self.bvh.find_nearest(Vector(p))
        return np.array(loc), np.array(n), d


# ------------------------------------------------------------------ parts (plain arrays)

class Part:
    def __init__(self):
        self.verts, self.faces, self.uv0, self.uv1 = [], [], [], []   # uv per face-loop
        self.normals = []                                              # per vertex (shading normals)
        self.edge = []                                                 # per vertex: 1 at a clump's side edges


def cap_part(H, mask_fn, offset, rim=-0.0008, subdiv=1, uv_scale=40.0, ratio=1.0):
    """Offset shell over the head where mask_fn(P) > 0; the rim sinks under the skin."""
    m = mask_fn(H.co)
    ear = set(H.ear_verts.tolist()) | set(H.lip_verts.tolist())
    faces = [p for p in H.head.data.polygons if p.material_index == 0 and max(m[i] for i in p.vertices) > 0.02
             and not any(i in ear for i in p.vertices)]
    used = sorted({i for p in faces for i in p.vertices})
    remap = {v: k for k, v in enumerate(used)}
    bm = bmesh.new()
    vs = [bm.verts.new(H.co[v]) for v in used]
    for p in faces:
        bm.faces.new([vs[remap[i]] for i in p.vertices])
    if subdiv:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
    bm.verts.index_update()
    P = np.array([v.co[:] for v in bm.verts])
    mv = mask_fn(P)
    kill = [f for f in bm.faces if max(mv[v.index] for v in f.verts) < 0.01]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.verts.index_update()
    P = np.array([v.co[:] for v in bm.verts])
    mv = mask_fn(P)
    V = []
    for p, k in zip(P, mv):
        loc, n, _ = H.nearest_skin(p)
        V.append(loc + n * (rim + (offset - rim) * ss(0.0, 1.0, k)))
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    if ratio < 1.0:
        V, faces = _decimate(np.array(V), faces, ratio)
    part = Part()
    for p in V:
        _, n, _ = H.nearest_skin(p)
        part.verts.append(p)
        part.normals.append(n)
        part.edge.append(0.0)
    for f in faces:
        part.faces.append(f)
        for i in f:
            p = V[i]
            part.uv0.append((float(H.theta(p)) / 180.0 * 6.0 * (1 if p[0] >= 0 else -1), p[2] * uv_scale))
            part.uv1.append((1.0, 0.35))
    part.verts = np.array(part.verts)
    return part


def _decimate(V, faces, ratio):
    """Collapse-decimate a loose surface (via a temporary object); returns (verts, faces)."""
    me = bpy.data.meshes.new("_dec")
    me.from_pydata(V.tolist(), [], faces)
    ob = bpy.data.objects.new("_dec", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("d", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    V2 = np.array([v.co[:] for v in ob.data.vertices])
    F2 = [tuple(p.vertices) for p in ob.data.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return V2, F2


def grow(H, root, flow, length, lift=0.0, gravity=0.0, stiff=0.5, floor=0.004, steps=10, curl=0.0, seed=0,
         hug=None, release=None, stop=None, guard=None):
    """Grow a spine from a root. flow(p, n) -> desired direction; the spine stays >= floor above the skin.
    hug: max height above floor while release(p) is False (keeps clumps lying on the head).
    guard(prev, p) -> p: a last say over each step (e.g. keep hair out from under the chin)."""
    loc, n, _ = H.nearest_skin(root)            # roots sit on the real skin (not on the ear domes)
    p = loc + n * floor * 0.5
    d = _unit(_tangent(np.asarray(flow(p, n), float), n) + n * lift)
    pts = [p.copy()]
    step = length / steps
    ph = np.random.default_rng(seed).random() * 6.28
    for i in range(steps):
        s = (i + 1) / steps
        want = _unit(np.asarray(flow(p, n), float))
        d = _unit(d * stiff + want * (1 - stiff) + np.array([0, 0, -1.0]) * gravity * s)
        if curl:
            d = _unit(d + _unit(np.cross(d, n)) * curl * math.sin(ph + s * 7.0))
        p = p + d * step
        loc, n, _ = H.nearest(p)
        h = float(np.dot(p - loc, n))
        if h < floor:
            p = p + n * (floor - h)
        elif hug is not None and h > floor + hug and not (release is not None and release(p)):
            p = p - n * (h - floor - hug) * 0.85
        if guard is not None:
            p = guard(pts[-1], p)
        if stop is not None and len(pts) >= 3 and stop(p):
            break                                        # e.g. reached the ear: end the clump here
        if np.linalg.norm(p - pts[-1]) > 1e-9:
            d = _unit(p - pts[-1])
        pts.append(p.copy())
    S = np.array(pts)
    for _ in range(3):                                   # remove zig-zags from push/pull
        S[1:-1] = S[1:-1] * 0.5 + (S[:-2] + S[2:]) * 0.25
        S[-1] = S[-1] * 0.5 + S[-2] * 0.5 + (S[-1] - S[-2]) * 0.5
    for i in range(1, len(S)):
        loc, n, _ = H.nearest(S[i])
        h = float(np.dot(S[i] - loc, n))
        if h < floor:
            S[i] = S[i] + n * (floor - h)
        if guard is not None:
            S[i] = guard(S[i - 1], S[i])
    return S


def clumps_part(H, spines, widths, thicks, rids, sides=6, tex_len=0.05, smooth=0.7, tip_w=0.3):
    """Flattened, tapered tubes along each spine: closed root sunk into the skin, single tip vertex.
    Shading normals are mostly the head's (smooth) so the hairdo lights as one mass; `smooth` is the
    share of the head normal (the rest is the tube's own normal)."""
    part = Part()
    V = []
    NV = []
    EV = []
    for S, w0, t0, rid in zip(spines, widths, thicks, rids):
        k = len(S)
        T = _unit(np.gradient(S, axis=0))
        seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))]
        L = max(seg[-1], 1e-6)
        sfrac = seg / L
        rings = []
        b_prev = None
        Ns = []
        for i in range(k - 1):
            loc, n, _ = H.nearest(S[i])
            # away from the skin the nearest normal is unreliable (it flips around the neck cut):
            # blend to the outward direction from the head's vertical axis
            far = ss(0.008, 0.03, float(np.linalg.norm(S[i] - loc)))
            radial = _unit(np.array([S[i][0], S[i][1] - H.cy, 0.0]))
            Ns.append(_unit(n * (1 - far) + radial * far))
        Ns = np.array(Ns)
        for _ in range(2):                               # no abrupt twists along a clump
            if len(Ns) > 2:
                Ns[1:-1] = _unit(Ns[1:-1] * 0.5 + (Ns[:-2] + Ns[2:]) * 0.25)
        for i in range(k - 1):
            s = sfrac[i]
            n = Ns[i]
            b = _unit(np.cross(T[i], n))
            if b_prev is not None and np.dot(b, b_prev) < 0:
                b = -b
            b_prev = b
            nn = _unit(np.cross(b, T[i]))
            w = w0 * (0.75 + 0.25 * ss(0.0, 0.2, s)) * (1 - ss(0.5, 1.0, s) * (1 - tip_w))
            th = t0 * (1 - 0.7 * ss(0.3, 1.0, s))
            ring = []
            for j in range(sides):
                a = 2 * math.pi * j / sides
                ring.append(len(V))
                V.append(S[i] + b * math.cos(a) * w * 0.5 + nn * math.sin(a) * th * 0.5)
                own = _unit(b * math.cos(a) * th + nn * math.sin(a) * w)      # ellipse normal
                NV.append(_unit(n * smooth + own * (1 - smooth)))
                EV.append(abs(math.cos(a)) ** 3)
            rings.append(ring)
            n_last = n
        tip = len(V)
        V.append(S[-1] + T[-1] * 0.25 * w0 * tip_w)                          # rounded end
        NV.append(_unit(n_last * smooth + T[-1] * (1 - smooth)))
        EV.append(0.3)
        # closed root: a point sunk into the skin, so root ends never show as open tubes
        loc0, n0, _ = H.nearest_skin(S[0])
        rootv = len(V)
        V.append(loc0 - n0 * 0.002 - T[0] * 0.004)
        NV.append(n0)
        EV.append(0.5)

        # winding: the quads must face away from the spine (else shading normals and faces disagree)
        f0 = len(part.faces)
        l0 = len(part.uv0)
        q = [np.asarray(V[i]) for i in (rings[0][0], rings[0][1], rings[1][1])]
        geo = np.cross(q[1] - q[0], q[2] - q[1])
        outward = (q[0] + q[1]) / 2 - S[0]
        flip = float(np.dot(geo, outward)) < 0

        def uv(ring_i, j):
            s = 1.0 if ring_i is None else sfrac[ring_i]
            u = 0.5 if ring_i is None else j / sides
            return (u + rid * 7.0, s * L / tex_len), (rid, s)

        for i in range(len(rings) - 1):
            for j in range(sides):
                j1 = (j + 1) % sides
                part.faces.append((rings[i][j], rings[i][j1], rings[i + 1][j1], rings[i + 1][j]))
                for (ri, jj) in ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)):
                    a, b = uv(ri, jj)
                    part.uv0.append(a)
                    part.uv1.append(b)
        for j in range(sides):
            part.faces.append((rings[0][(j + 1) % sides], rings[0][j], rootv))
            for (ri, jj) in ((0, j + 1), (0, j), (0, j)):
                a, b = uv(ri, jj)
                part.uv0.append(a)
                part.uv1.append(b)
        last = len(rings) - 1
        for j in range(sides):
            part.faces.append((rings[last][j], rings[last][(j + 1) % sides], tip))
            for (ri, jj) in ((last, j), (last, j + 1), (None, 0)):
                a, b = uv(ri, jj)
                part.uv0.append(a)
                part.uv1.append(b)
        if flip:
            _flip_faces(part, f0, l0)
    part.verts = np.array(V) if V else np.zeros((0, 3))
    part.normals = NV
    part.edge = EV
    return part


def _flip_faces(part, f0, l0):
    """Reverse winding of faces from index f0 (loops from l0) in place, keeping loop data aligned."""
    li = l0
    for fi in range(f0, len(part.faces)):
        f = part.faces[fi]
        n = len(f)
        part.faces[fi] = tuple(reversed(f))
        part.uv0[li:li + n] = list(reversed(part.uv0[li:li + n]))
        part.uv1[li:li + n] = list(reversed(part.uv1[li:li + n]))
        li += n


def sample_roots(H, mask_fn, spacing, seed=0, where=None, thresh=0.6):
    """Blue-noise roots over the head (candidates = head verts inside the mask)."""
    rng = np.random.default_rng(seed)
    P = H.co
    cand = np.where(mask_fn(P) > thresh)[0]
    if where is not None:
        cand = cand[where(P[cand])]
    rng.shuffle(cand)
    out = []
    for i in cand:
        p = P[i]
        if not out or np.min(np.linalg.norm(np.array(out) - p, axis=1)) >= spacing:
            out.append(p)
    return np.array(out)


# ------------------------------------------------------------------ objects

def mesh_from_parts(name, parts):
    verts, faces, uv0, uv1, nrm, edge = [], [], [], [], [], []
    off = 0
    for p in parts:
        if p is None or len(p.verts) == 0:
            continue
        verts.extend(np.asarray(p.verts).tolist())
        nrm.extend(np.asarray(p.normals).tolist() if len(p.normals) == len(p.verts) else [None] * len(p.verts))
        edge.extend(p.edge if len(p.edge) == len(p.verts) else [0.0] * len(p.verts))
        faces.extend(tuple(i + off for i in f) for f in p.faces)
        uv0.extend(p.uv0)
        uv1.extend(p.uv1)
        off += len(p.verts)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    a = me.uv_layers.new(name="UVMap")
    b = me.uv_layers.new(name="Clump")
    a.data.foreach_set("uv", np.array(uv0, np.float32).ravel())
    b.data.foreach_set("uv", np.array(uv1, np.float32).ravel())
    for p in me.polygons:
        p.use_smooth = True
    if all(n is not None for n in nrm):
        me.normals_split_custom_set_from_vertices(nrm)
    # vertex colour "HairData": R = clump edge (darkened by the shader), G/B/A reserved
    att = me.color_attributes.new("HairData", 'FLOAT_COLOR', 'POINT')
    e = np.array(edge, np.float32)
    att.data.foreach_set("color", np.stack([e, np.zeros_like(e), np.zeros_like(e), np.ones_like(e)], 1).ravel())
    return me


def replace_object(scene, name, me):
    old = bpy.data.objects.get(name)
    if old is not None:
        me_old = old.data
        old.data = me
        if me_old.users == 0:
            bpy.data.meshes.remove(me_old)
        ob = old
    else:
        ob = bpy.data.objects.new(name, me)
    col = bpy.data.collections.get(HAIR_COL) or bpy.data.collections.new(HAIR_COL)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    if col not in ob.users_collection:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        col.objects.link(ob)
    return ob


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ------------------------------------------------------------------ follow the face keys

def bind_keys(ob, head, eps=1e-5):
    """Give ob the head's shape keys: Surface Deform to the head, then capture each key.
    Keys that don't move the piece are skipped (look them up by name at runtime)."""
    kbs = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in kbs}
    for k in kbs:
        k.value = 0.0
    if ob.data.shape_keys:
        ob.shape_key_clear()
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    mod = ob.modifiers.new("HeadBind", 'SURFACE_DEFORM')
    mod.target = head
    mod.falloff = 4.0
    vl = bpy.context.view_layer
    hidden = ob.hide_get()
    ob.hide_set(False)
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.surfacedeform_bind(modifier=mod.name)
    if not mod.is_bound:
        raise RuntimeError(f"surface deform bind failed for {ob.name}")
    n = len(ob.data.vertices)
    base = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get("co", base)

    def evaluated():
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        out = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", out)
        ev.to_mesh_clear()
        return out

    rest = evaluated()                       # bound rest pose (should equal base)
    keys = {}
    for k in kbs[1:]:
        k.value = 1.0
        c = evaluated()
        k.value = 0.0
        d = c - rest
        if np.abs(d).max() > eps:
            keys[k.name] = base + d
    ob.modifiers.remove(mod)
    ob.shape_key_add(name="Basis", from_mix=False)
    for name, co in keys.items():
        kb = ob.shape_key_add(name=name, from_mix=False)
        kb.data.foreach_set("co", co)
        kb.slider_min = -1.0
    for k in kbs:
        k.value = saved[k.name]
    ob.hide_set(hidden)
    return len(keys), float(np.abs(rest - base).max())


# ------------------------------------------------------------------ skin mask for hair edges

def bake_skin_hair_mask(head, size=1024):
    """T_Head_MaskC: R = soft hair band (a little outside the cap edge, so hairlines fade into the skin),
    G = beard area (shadow under beards / stubble region), B/A reserved."""
    H = HeadFrame(head)
    P, valid = hum_paint.bake_map(head, "pos", size)
    flat = P.reshape(-1, 3)
    hl = H.hair_mask(flat + np.array([0, 0, 0.003]), soft=0.006).reshape(P.shape[:2])   # reaches 3 mm below the cap edge
    beard = H.beard_mask(flat, cheeks=0.6).reshape(P.shape[:2])
    # shadow only where the beard sits on the face, not down the neck
    F = H.F
    beard *= hum_paint.smoothstep(F.chin[2] - 0.03, F.chin[2] - 0.015, P[..., 2])
    M = np.zeros(P.shape[:2] + (4,))
    M[..., 0] = hl
    M[..., 1] = beard
    M[..., 3] = 1.0
    M[~valid] = 0
    M = hum_paint.dilate(M, valid)
    return hum_paint.save_image("T_Head_MaskC", M, os.path.join(hum_paint.TEX_DIR, "T_Head_MaskC.png"))


def bind_keys_nearest(ob, target, eps=1e-5, faces=None, verts=None, merge=False):
    """Nearest-point binding (Surface Deform can refuse some meshes): every vertex takes the key deltas of
    its nearest point on the target (inverse-distance over that face's corners), translation only.
    faces: only these target faces; verts + merge: rebind just these vertices, keeping the other keys."""
    tme = target.data
    kbs = tme.shape_keys.key_blocks
    basis = np.array([d.co[:] for d in kbs[0].data])
    faces = set(faces) if faces is not None else None
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in basis]
    for fi, p in enumerate(tme.polygons):
        if faces is not None and fi not in faces:
            continue
        try:
            bm.faces.new([vs[i] for i in p.vertices])
        except ValueError:
            pass
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    Vall = np.array([v.co[:] for v in ob.data.vertices])
    sel = np.arange(len(Vall)) if verts is None else np.asarray(verts)
    V = Vall[sel]
    idx, wts = [], []
    for p in V:
        loc, n, fi, d = bvh.find_nearest(Vector(p))
        f = bm.faces[fi]
        ids = [u.index for u in f.verts]
        dist = np.array([(u.co - loc).length for u in f.verts]) + 1e-6
        k = 1.0 / dist
        idx.append(ids)
        wts.append(k / k.sum())
    bm.free()
    if not merge:
        if ob.data.shape_keys:
            ob.shape_key_clear()
        ob.shape_key_add(name="Basis", from_mix=False)
    elif ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    okb = ob.data.shape_keys.key_blocks
    n = 0
    for kb in kbs[1:]:
        D = np.array([d.co[:] for d in kb.data]) - basis
        dv = np.array([(D[ids] * w[:, None]).sum(0) for ids, w in zip(idx, wts)]) if np.abs(D).max() >= eps             else np.zeros_like(V)
        k = okb.get(kb.name)
        if k is None:
            if np.abs(dv).max() < eps:
                continue
            k = ob.shape_key_add(name=kb.name, from_mix=False)
            k.slider_min = -1.0
        co = np.empty(len(Vall) * 3, np.float32)
        k.data.foreach_get("co", co)
        co = co.reshape(-1, 3)
        co[sel] = V + dv
        k.data.foreach_set("co", co.astype(np.float32).ravel())
        n += 1
    return len(okb) - 1, 0.0


def hair_weights(ob, sk, arm):
    """Head hair: rigid on the head down to the base of the skull, then blending into neck_01 and on the
    shoulders into spine_03, so long hair lying on the back moves with the back when the neck and spine bend
    (rigid on the head, it sank into the shoulders in the idle and walk animations)."""
    me = ob.data
    kb = me.shape_keys.key_blocks[0] if me.shape_keys else None
    co = np.array([d.co[:] for d in kb.data]) if kb else np.array([v.co[:] for v in me.vertices])
    bones = arm.data.bones
    z_head = float(bones["head"].head_local[2])
    z_neck = float(bones["neck_01"].head_local[2])
    z_sp = float(bones["spine_03"].head_local[2])
    z = co[:, 2]
    a = hum_paint.smoothstep(z_neck - 0.02, z_head + 0.05, z)    # 1 on the head; a long blend (no crease)
    b = hum_paint.smoothstep(z_sp + 0.02, z_neck, z)             # 1 at the neck and above
    W = np.zeros((len(co), len(sk.bones)))
    W[:, sk.index["head"]] = a
    W[:, sk.index["neck_01"]] = (1 - a) * b
    W[:, sk.index["spine_03"]] = (1 - a) * (1 - b)
    return W


def smooth_keys_spatial(ob, radius=0.02):
    """Blur every shape key's offsets over space (Gaussian, `radius`): neighbouring clumps move together.
    The keys come from a Surface Deform bind to the head; hair hanging below the skull binds to the neck
    edge of the head mesh, which some keys (neck width, feminine) move unlike the skull, tearing a gap
    between the clumps above and below."""
    from mathutils.kdtree import KDTree
    me = ob.data
    if not me.shape_keys:
        return
    kb = me.shape_keys.key_blocks
    base = np.array([d.co[:] for d in kb[0].data])
    kd = KDTree(len(base))
    for i, p in enumerate(base):
        kd.insert(Vector(p), i)
    kd.balance()
    rows, cols, ws = [], [], []
    for i, p in enumerate(base):
        for co, j, dist in kd.find_range(Vector(p), radius):
            rows.append(i)
            cols.append(j)
            ws.append(math.exp(-0.5 * (dist / (radius * 0.5)) ** 2))
    rows, cols, ws = np.array(rows), np.array(cols), np.array(ws)
    norm = np.bincount(rows, weights=ws, minlength=len(base))
    for k in kb[1:]:
        D = np.array([d.co[:] for d in k.data]) - base
        S = np.zeros_like(D)
        for c in range(3):
            S[:, c] = np.bincount(rows, weights=ws * D[cols, c], minlength=len(base))
        S /= np.maximum(norm, 1e-9)[:, None]
        k.data.foreach_set("co", (base + S).astype(np.float32).ravel())
