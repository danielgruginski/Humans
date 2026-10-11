"""The skeleton (2026-10-10, the undead: hum_undead): bones rigged to the humans' own skeleton, shipped as a garment
("Skeleton", slot "skeleton") that hides the whole body and the head, so a skeleton walks with the same Humanoid
clips and wears the same clothes and armour (built on the Undead builds, the tightest fit to the bones).

Built per build in build space like any garment (hum_builds.BuildSpace), measured off that build's body, head and
joints, every piece rigid on one bone (no weight bleed; joints part a little when bent, as bones do):

skull      distance-field sculpt (openvdb): cranium fitted to the head, brow, cheekbones, zygomatic arches, maxilla;
           orbits, nasal opening and temples carved; teeth as small blocks; a separate mandible (on the head bone:
           there is no jaw bone), jaw a little open; a cold light deep in each orbit (material slot 1, "glow")
spine      24 vertebrae under the back's skin: bodies and spines, lumbar side processes (pelvis .. neck_01)
ribcage    9 rib pairs along the same lines hum_undead paints on the zombies (rib_phase), inset under the skin,
           running into a sternum; the upper ones on spine_03, the lower on spine_02
pelvis     distance-field sculpt: iliac wings and crests, sacrum, the pubic and ischial rings round the hips' sockets
shoulders  clavicles (lofted S-curves) and shoulder blades (a plate with its ridge, on the clavicle bones)
arms       humerus (head ball, flared condyles across the elbow's hinge), radius and ulna, carpal block, metacarpals,
           every phalanx on its own finger bone
legs       femur (ball, neck, trochanter, condyles), kneecap, tibia and fibula, heel block, metatarsals, toes (ball bone)

LODs are built from the same recipe at lower resolution (not decimated: small bones collapse). Material "bone" ->
Humans/Cloth with the bone pattern projected in 3D (M_HumanBone) and M_HumanGlow for the orbits' light.

    with hum_builds.BuildSpace("MUndead", sk): hum_skeleton.build(scene, arm, sk)   (or via build_wardrobe)
"""
import math

import numpy as np

import hum_cloth as C

ss = C.ss


# ------------------------------------------------------------------ distance fields (numpy) -> mesh (openvdb)

def sd_sphere(P, c, r):
    return np.linalg.norm(P - c, axis=-1) - r


def sd_capsule(P, a, b, ra, rb=None):
    """A capsule (a round cone when rb differs) from a to b."""
    rb = ra if rb is None else rb
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[..., None] * ab), axis=-1) - (ra + (rb - ra) * t)


def sd_ellipsoid(P, c, radii, R=None):
    """Ellipsoid (iq's bound); R's columns are its local axes (world)."""
    q = P - c
    if R is not None:
        q = q @ R
    r = np.asarray(radii, float)
    k0 = np.linalg.norm(q / r, axis=-1)
    k1 = np.linalg.norm(q / (r * r), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_box(P, c, half, R=None, rnd=0.0):
    q = P - c
    if R is not None:
        q = q @ R
    d = np.abs(q) - (np.asarray(half, float) - rnd)
    return np.linalg.norm(np.maximum(d, 0), axis=-1) + np.minimum(d.max(-1), 0) - rnd


def sd_triangle(P, a, b, c):
    """Unsigned distance to a triangle (iq)."""
    ba, pa = b - a, P - a
    cb, pb = c - b, P - b
    ac, pc = a - c, P - c
    nor = np.cross(ba, ac)
    s = (np.sign((np.cross(ba, nor) * pa).sum(-1)) + np.sign((np.cross(cb, nor) * pb).sum(-1))
         + np.sign((np.cross(ac, nor) * pc).sum(-1)))

    def seg(e, p):
        t = np.clip((p @ e) / float(e @ e), 0, 1)
        return ((e * t[..., None] - p) ** 2).sum(-1)
    edge = np.minimum(np.minimum(seg(ba, pa), seg(cb, pb)), seg(ac, pc))
    face = (pa @ nor) ** 2 / float(nor @ nor)
    return np.sqrt(np.where(s < 2.0, edge, face))


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def sub(a, b, k=0.0):
    """a minus b (smoothly with k)."""
    return smax(a, -b, k) if k > 0 else np.maximum(a, -b)


def frame(x, y_hint):
    """Rotation whose columns are x, a y orthogonal to it from the hint, and their cross."""
    x = x / np.linalg.norm(x)
    y = y_hint - x * (y_hint @ x)
    y /= np.linalg.norm(y)
    return np.stack([x, y, np.cross(x, y)], 1)


def sdf_mesh(fn, lo, hi, voxel, adapt=0.0):
    """Mesh the zero set of fn (P (nx, ny, nz, 3) -> distances) over the box lo..hi: openvdb's polygoniser,
    `adapt` merges flat regions. Returns (V, faces) wound outward."""
    import openvdb
    i0 = np.floor(np.asarray(lo) / voxel).astype(int) - 2
    i1 = np.ceil(np.asarray(hi) / voxel).astype(int) + 2
    idx = np.stack(np.meshgrid(*[np.arange(a, b + 1) for a, b in zip(i0, i1)], indexing="ij"), -1)
    P = idx.astype(np.float64) * voxel
    D = np.asarray(fn(P), np.float32)
    g = openvdb.FloatGrid(float(voxel * 3))
    g.copyFromArray(D, ijk=tuple(int(v) for v in i0), tolerance=0.0)
    g.transform = openvdb.createLinearTransform(voxelSize=voxel)
    pts, tris, quads = g.convertToPolygons(isovalue=0.0, adaptivity=adapt)
    V = np.asarray(pts, float)
    F = [tuple(int(i) for i in t) for t in tris] + [tuple(int(i) for i in q) for q in quads]
    return V, F


# ------------------------------------------------------------------ lofts

def loft(pts, rx, ry=None, sides=6, ups=None, cap=0.5, twist=0.0):
    """A closed tube through pts with elliptical sections (rx along `ups`, ry across), capped by a point `cap` x
    the end radius beyond each end (0: flat). Returns (V, faces)."""
    pts = np.asarray(pts, float)
    n = len(pts)
    rx = np.broadcast_to(np.asarray(rx, float), (n,))
    ry = rx if ry is None else np.broadcast_to(np.asarray(ry, float), (n,))
    T = np.gradient(pts, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    if ups is None:                                    # parallel transport from any perpendicular
        u = np.cross(T[0], [0, 0, 1.0] if abs(T[0][2]) < 0.9 else [1.0, 0, 0])
        U = []
        for k in range(n):
            u = u - T[k] * (u @ T[k])
            u /= np.linalg.norm(u)
            U.append(u.copy())
        U = np.array(U)
    else:
        U = np.broadcast_to(np.asarray(ups, float), (n, 3)).copy()
        U -= T * (U * T).sum(1, keepdims=True)
        U /= np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12)
    Vv = np.cross(T, U)
    ph = 2 * np.pi * (np.arange(sides) + 0.5) / sides + twist
    V = (pts[:, None, :] + U[:, None, :] * (rx[:, None, None] * np.cos(ph)[None, :, None])
         + Vv[:, None, :] * (ry[:, None, None] * np.sin(ph)[None, :, None])).reshape(-1, 3)
    F = []
    for k in range(n - 1):
        for j in range(sides):
            a, b = k * sides + j, k * sides + (j + 1) % sides
            F.append((a, b, b + sides, a + sides))
    V = list(V)
    s0 = len(V); V.append(pts[0] - T[0] * cap * max(rx[0], ry[0]))
    s1 = len(V); V.append(pts[-1] + T[-1] * cap * max(rx[-1], ry[-1]))
    last = (n - 1) * sides
    for j in range(sides):
        F.append((s0, (j + 1) % sides, j))
        F.append((s1, last + j, last + (j + 1) % sides))
    return np.array(V), F


def ball(c, r, seg=6, rings=4, scale=(1, 1, 1), R=None):
    """A low UV sphere (ellipsoid with `scale`, axes R)."""
    V = [np.array([0, 0, -1.0])]
    for i in range(1, rings):
        th = np.pi * i / rings - np.pi / 2
        for j in range(seg):
            ph = 2 * np.pi * j / seg
            V.append(np.array([np.cos(th) * np.cos(ph), np.cos(th) * np.sin(ph), np.sin(th)]))
    V.append(np.array([0, 0, 1.0]))
    V = np.array(V) * np.asarray(scale, float) * r
    if R is not None:
        V = V @ R.T
    V = V + c
    F = []
    for j in range(seg):
        F.append((0, 1 + (j + 1) % seg, 1 + j))
    for i in range(rings - 2):
        for j in range(seg):
            a, b = 1 + i * seg + j, 1 + i * seg + (j + 1) % seg
            F.append((a, b, b + seg, a + seg))
    top = len(V) - 1
    base = 1 + (rings - 2) * seg
    for j in range(seg):
        F.append((top, base + j, base + (j + 1) % seg))
    return V, F


def block(c, half, R=None):
    """A box (8 corners), axes R."""
    s = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                  [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float) * np.asarray(half, float)
    if R is not None:
        s = s @ R.T
    F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return s + c, F


def decimate(V, F, target):
    """Collapse-decimate a mesh to about `target` triangles (a throwaway object and Blender's modifier): the
    distance-field meshes come out of openvdb at voxel density, far over budget."""
    import bpy
    n = sum(len(f) - 2 for f in F)
    if n <= target:
        return V, F
    me = bpy.data.meshes.new("_skel_dec")
    me.from_pydata(np.asarray(V).tolist(), [], [list(f) for f in F])
    ob = bpy.data.objects.new("_skel_dec", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("D", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = target / n
    mod.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    m2 = ev.to_mesh()
    V2 = np.array([v.co[:] for v in m2.vertices])
    F2 = [tuple(p.vertices) for p in m2.polygons]
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return V2, F2


def _signed_volume(V, F):
    vol = 0.0
    for f in F:
        for k in range(1, len(f) - 1):
            vol += float(np.dot(V[f[0]], np.cross(V[f[k]], V[f[k + 1]])))
    return vol / 6.0


# ------------------------------------------------------------------ the builder

LODS = {      # dec: triangle budgets of the distance-field pieces (decimated); fr: rings per finger bone
    # (the humans' body + head: 27.8k / 7.4k / 3.2k triangles; the skeleton replaces both)
    0: dict(sides=6, small=4, vsides=5, rib_segs=10, rib_sides=4, voxel=0.0018, adapt=0.0, vox_skull=0.0016,
            teeth=True, processes=True, glow=(6, 4), fr=3, every_vert=1, simple=False, palm=False, extras=True,
            dec=dict(skull=1200, jaw=420, pelvis=700, scapula=110)),
    1: dict(sides=5, small=3, vsides=4, rib_segs=5, rib_sides=3, voxel=0.0026, adapt=0.0, vox_skull=0.002,
            teeth=False, processes=False, glow=(5, 3), fr=2, every_vert=2, simple=False, palm=True, extras=True,
            dec=dict(skull=520, jaw=140, pelvis=260, scapula=44)),
    2: dict(sides=4, small=3, vsides=3, rib_segs=3, rib_sides=3, voxel=0.0035, adapt=0.0, vox_skull=0.003,
            teeth=False, processes=False, glow=(4, 3), fr=2, every_vert=2, simple=True, palm=True, extras=False,
            dec=dict(skull=200, jaw=50, pelvis=100, scapula=20)),
}


class Skel:
    """Measures one build (in build space) and makes the pieces: (V, faces, bone, material slot)."""

    def __init__(self, B, head, lod=0):
        import bmesh
        from mathutils.bvhtree import BVHTree
        import hum_paint
        self.B, self.lod, self.L = B, lod, LODS[lod]
        self.j, self.jt = B.j, B.jt
        self.cy = float(np.mean([self.j[b][1] for b in ("spine_01", "spine_02", "spine_03")]))
        self.F = hum_paint.Face(head)
        nh = head["n_head_verts"]
        self.H = np.array([v.co[:] for v in head.data.vertices])[:nh]
        # the body and the head's skin together (the body ends at the neck; the cervical spine reaches past it)
        hf = [tuple(p.vertices) for p in head.data.polygons if p.material_index == 0 and max(p.vertices) < nh]
        n0 = len(B.co_raw)
        self.bvh = BVHTree.FromPolygons(B.co_raw.tolist() + self.H.tolist(),
                                        list(B.faces) + [tuple(i + n0 for i in f) for f in hf])
        self.pieces = []

    def add(self, V, F, bone, mat=0):
        V = np.asarray(V, float)
        if len(F) and _signed_volume(V, F) < 0:
            F = [tuple(reversed(f)) for f in F]
        self.pieces.append((V, F, bone, mat))

    def ray(self, o, d, far=0.6):
        """Distance from o (inside the body) along d to the skin: the first surface met going out (a cast back
        from outside met the arms first and the ribs reached out to them)."""
        from mathutils import Vector
        d = np.asarray(d, float) / np.linalg.norm(d)
        hit = self.bvh.ray_cast(Vector(o), Vector(d), far)
        return hit[3] if hit[0] is not None else None

    def axis_y(self, z):
        """The rig's centre line (inside the body) at height z: the spine's and neck's joints."""
        chain = [self.j[b] for b in ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head")]
        zs = [float(p[2]) for p in chain]
        return float(np.interp(z, zs, [float(p[1]) for p in chain]))

    def skin_y(self, z, sgn, x=0.0, cy=None):
        """The skin's y at height z (sgn +1 the back, -1 the front) on the line x."""
        cy = self.axis_y(z) if cy is None else cy
        o = np.array([x, cy, z])
        d = self.ray(o, np.array([0, sgn, 0.0]), 0.4)
        return cy + sgn * (d if d is not None else 0.03)

    # -------------------------------------------------------------- head

    def skull(self):
        F, Hm, L = self.F, self.H, self.L
        el, er = F.eye["l"][0], F.eye["r"][0]
        ex = abs(el[0])
        ey, ez = float((el[1] + er[1]) / 2), float((el[2] + er[2]) / 2)
        top = float(Hm[:, 2].max())
        back = float(Hm[:, 1].max())
        band = Hm[(Hm[:, 2] > ez + 0.02) & (Hm[:, 2] < ez + 0.06) & (Hm[:, 1] > ey + 0.03)]
        wh = float(np.abs(band[:, 0]).max())
        fb = Hm[(np.abs(Hm[:, 0]) < 0.012) & (Hm[:, 2] > ez + 0.03) & (Hm[:, 2] < ez + 0.05)]
        front = float(fb[:, 1].min())
        m = F.mouth
        self.sk_dims = dict(ex=ex, ey=ey, ez=ez, top=top, back=back, wh=wh, front=front)
        ax, ay = wh - 0.0045, (back - front) / 2 - 0.005
        cc = np.array([0.0, (front + back) / 2 + 0.002, ez + 0.017])
        az = min(top - 0.006 - cc[2], 1.12 * ax)      # the stylised head's tall crown made a skull like an egg
        cheek = [np.array([s * (ex + 0.009), ey + 0.006, ez - 0.022]) for s in (1, -1)]
        arch_end = [np.array([s * (ax - 0.003), ey + 0.058, ez - 0.022]) for s in (1, -1)]
        mtop = m[2] + 0.004                                  # the upper teeth's roots
        maxc = np.array([0.0, m[1] + 0.024, (ez - 0.03 + mtop) / 2])
        maxh = np.array([0.025, 0.021, (ez - 0.03 - mtop) / 2 + 0.006])

        def fn(P):
            d = sd_ellipsoid(P, cc, (ax, ay, az))
            d = smax(d, (ez - 0.047) - P[..., 2], 0.012)                 # the base of the skull
            face = sd_box(P, maxc, maxh, rnd=0.011)
            for c in cheek:
                face = smin(face, sd_sphere(P, c, 0.0135), 0.012)
            face = smin(face, sd_capsule(P, np.array([-(ex + 0.016), ey - 0.0015, ez + 0.017]),
                                         np.array([ex + 0.016, ey - 0.0015, ez + 0.017]), 0.0085), 0.01)
            face = smin(face, sd_capsule(P, np.array([0, ey - 0.006, ez + 0.012]),
                                         np.array([0, ey - 0.011, ez - 0.014]), 0.0055), 0.006)
            for c, e in zip(cheek, arch_end):
                face = smin(face, sd_capsule(P, c, e, 0.0052), 0.006)
            for s in (1, -1):
                face = smin(face, sd_sphere(P, np.array([s * (ax - 0.013), ey + 0.082, ez - 0.044]), 0.008), 0.01)
            d = smin(d, face, 0.014)
            for e in (el, er):                                             # the orbits
                d = sub(d, sd_ellipsoid(P, e + np.array([0, -0.006, 0.001]), (0.0185, 0.03, 0.0172)), 0.0025)
            d = sub(d, sd_ellipsoid(P, np.array([0, ey - 0.012, ez - 0.036]), (0.0095, 0.03, 0.0145)), 0.002)
            for s in (1, -1):                                             # temples
                d = sub(d, sd_ellipsoid(P, np.array([s * (ax + 0.007), ey + 0.046, ez + 0.003]),
                                        (0.012, 0.028, 0.022)), 0.008)
            return d
        lo = np.array([-ax - 0.01, front - 0.03, ez - 0.075])
        hi = np.array([ax + 0.01, back + 0.005, top + 0.004])
        V, Fc = decimate(*sdf_mesh(fn, lo, hi, L["vox_skull"], L["adapt"]), L["dec"]["skull"])
        self.add(V, Fc, "head")
        # the mandible: a U along the jaw, the ramus up to under the arch's end, the chin; a little open
        chin, cz = F.chin, float(F.chin[2])
        lowj = Hm[(np.abs(Hm[:, 0]) < 0.02) & (Hm[:, 1] < chin[1] + 0.03)]
        cbot = float(lowj[:, 2].min()) + 0.006
        jw = Hm[(Hm[:, 2] > cbot) & (Hm[:, 2] < cbot + 0.035) & (Hm[:, 1] > chin[1] + 0.03)]
        jx = float(np.abs(jw[:, 0]).max()) - 0.009
        jy = float(jw[np.argmax(np.abs(jw[:, 0])), 1])
        opn = 0.004
        lowz = lambda t: cbot + 0.006 + 0.012 * t - opn
        hiz = lambda t: m[2] - 0.006 - opn + (cbot + 0.026 - (m[2] - 0.006)) * ss(0.4, 1.0, t)
        ts = np.linspace(0, 1, 9)
        low, high = [], []
        for t in ts:                                          # the jaw's lower border and its upper (teeth) edge
            x = jx * t
            y = chin[1] + 0.006 + (jy - chin[1] - 0.006) * t ** 1.6
            low.append(np.array([x, y, lowz(t)]))
            high.append(np.array([x, y + 0.004, hiz(t)]))
        mir = lambda p, s: p * np.array([s, 1, 1])

        def fj(P):
            d = None
            for s in (1, -1):
                for i in range(len(ts) - 1):                 # a plate between the borders, a rounded lower rim
                    a, b, c, e = (mir(low[i], s), mir(low[i + 1], s), mir(high[i + 1], s), mir(high[i], s))
                    q = np.minimum(sd_triangle(P, a, b, c), sd_triangle(P, a, c, e)) - 0.0042
                    q = smin(q, sd_capsule(P, a, b, 0.0055 - 0.001 * ts[i]), 0.004)
                    d = q if d is None else smin(d, q, 0.003)
                ang = np.array([s * jx, jy, cbot + 0.014 - opn])
                cond = np.array([s * (ax - 0.012), ey + 0.068, ez - 0.034])
                cor = np.array([s * (ex + 0.018), ey + 0.046, ez - 0.038])
                ram = sd_triangle(P, ang, cond, cor) - 0.0035                 # the ramus: a plate
                notch = (cond + cor) / 2 + np.array([0, 0, 0.002])
                ram = sub(ram, sd_sphere(P, notch, np.linalg.norm(cond - cor) * 0.36), 0.002)
                ram = smin(ram, sd_capsule(P, ang, cond, 0.005, 0.0055), 0.004)
                d = smin(d, ram, 0.006)
            d = smin(d, sd_sphere(P, np.array([0, chin[1] + 0.007, cbot + 0.008 - opn]), 0.0075), 0.006)
            return d
        lo = np.array([-ax, chin[1] - 0.01, cbot - 0.012])
        hi = np.array([ax, ey + 0.085, ez - 0.02])
        V, Fj = decimate(*sdf_mesh(fj, lo, hi, L["vox_skull"], L["adapt"]), L["dec"]["jaw"])
        self.add(V, Fj, "head")
        # teeth: blocks along an arc behind the lips, upper and lower
        if L["teeth"]:
            for row, (z0, h) in enumerate(((mtop - 0.0005, 0.0085), (m[2] - 0.0035 - opn, 0.0075))):
                n = 10
                for i in range(n):
                    u = (i + 0.5) / n * 2 - 1
                    x = u * (0.021 if row == 0 else 0.018)
                    y = m[1] + 0.008 + 0.024 * u * u + (0.002 if row else 0.0)
                    w = 0.0024 if abs(u) < 0.45 else 0.0032
                    hh = h * (1.0 if abs(u) < 0.45 else 0.8)
                    dx = np.array([1.0, 0.048 * u * 2, 0.0])
                    R = frame(dx, np.array([0, 1.0, 0]))
                    zc = z0 - hh / 2 if row == 0 else z0 + hh / 2
                    V, Fb = block(np.array([x, y, zc]), (w, 0.0028, hh / 2), R)
                    self.add(V, Fb, "head")
        # the light deep in the orbits
        sg, rg = self.L["glow"]
        for e in (el, er):
            V, Fb = ball(e + np.array([0, 0.012, 0.0]), 0.0062, sg, rg)
            self.add(V, Fb, "head", mat=1)

    # -------------------------------------------------------------- spine and ribs

    def spine_y(self, z):
        """The vertebral bodies' line: under the back's skin, about 40 % of the way to the front."""
        b, f = self.skin_y(z, +1), self.skin_y(z, -1)
        neck = ss(self.j["neck_01"][2] - 0.04, self.j["neck_01"][2] + 0.01, z)
        return b - (0.4 + 0.08 * neck) * (b - f), b

    def spine(self):
        j, L = self.j, self.L
        zs = list(np.linspace(j["spine_01"][2] - 0.012, j["spine_03"][2] - 0.008, 5, endpoint=False))
        zs += list(np.linspace(j["spine_03"][2] - 0.008, j["neck_01"][2] - 0.004, 12, endpoint=False))
        zs += list(np.linspace(j["neck_01"][2] - 0.004, j["head"][2] - 0.012, 7))
        self.vert = []
        ev = L["every_vert"]
        for k, z in enumerate(zs):
            if k % ev:
                continue                                  # LOD2: every other vertebra, twice as tall
            kind = "L" if k < 5 else ("T" if k < 17 else "C")
            y, yb = self.spine_y(z)
            gap = (zs[min(k + 1, len(zs) - 1)] - zs[max(k - 1, 0)]) / 2 if 0 < k < len(zs) - 1 else 0.02
            r = {"L": 0.0145, "T": 0.0115, "C": 0.0085}[kind]
            h = gap * (0.72 if ev == 1 else 1.6)
            c = np.array([0.0, y, z])
            bone = ("pelvis" if z < j["spine_01"][2] else "spine_01" if z < j["spine_02"][2] else
                    "spine_02" if z < j["spine_03"][2] else "spine_03" if z < j["neck_01"][2] else "neck_01")
            self.vert.append((c, r, bone, kind))
            V, Fb = loft([c - [0, 0, h / 2], c + [0, 0, h / 2]], r, r * 0.85, L["vsides"], ups=[1.0, 0, 0], cap=0.0)
            self.add(V, Fb, bone)
            if L["processes"] or (kind != "C" and ev == 1):
                tip = np.array([0.0, yb - 0.011, z - gap * (0.5 if kind == "T" else 0.25)])
                base = c + np.array([0, r * 0.8, 0])
                reach = {"L": 0.024, "T": 0.026, "C": 0.011 if k < len(zs) - 1 else 0.008}[kind]
                if k == 16:
                    reach = 0.024                         # C7 / T1: the knob at the neck's base
                dv = tip - base
                tip = base + dv * min(1.0, reach / max(np.linalg.norm(dv), 1e-6))
                V, Fb = loft([base, tip], [0.0035, 0.0022], [0.0075, 0.004],
                             L["small"] if L["processes"] else 3, ups=[0, 0, 1.0], cap=0.3)
                self.add(V, Fb, bone)
            if L["processes"] and kind == "L":
                for s in (1, -1):
                    a = c + np.array([s * r * 0.7, r * 0.5, 0])
                    b = c + np.array([s * (r + 0.02), r * 0.9, 0.0])
                    V, Fb = loft([a, b], 0.003, 0.005, 4, ups=[0, 0, 1.0], cap=0.3)
                    self.add(V, Fb, bone)

    def ribs(self):
        import hum_undead
        j, L = self.j, self.L
        top, sp, n, d0, d1 = hum_undead._rib_cage(j, self.cy)
        self.rib_ends = []
        # the cage's barrel: the skin's distance at the 6th rib's height, per angle; the upper ribs are smaller loops
        # (at their height the skin is the shoulders', and the first ribs reached out to them)
        ref_z = top - 5 * sp
        prof = [0.5, 0.66, 0.78, 0.87, 0.93, 0.97, 1.0, 1.0, 0.98]

        def cage(th):
            d = np.array([np.sin(th), -np.cos(th), 0.0])
            return (self.ray(np.array([0.0, self.cy, ref_z]), d, 0.35) or 0.1)
        for k in range(n):
            z_back = top - k * sp
            yv, _ = self.spine_y(z_back)
            a_end = 0.07 if k < 6 else 0.07 + 0.06 * (k - 5)
            bone = "spine_03" if k < 5 else "spine_02"
            for s in (1, -1):
                pts, ups = [np.array([s * 0.014, yv + 0.004, z_back + 0.004])], [np.array([0, 0, 1.0])]
                for a in np.linspace(0.9, a_end, L["rib_segs"]):
                    z = top - k * sp - (d0 + d1 * k / (n - 1)) * (1 - a) ** 1.3
                    th = s * np.pi * a
                    d = np.array([np.sin(th), -np.cos(th), 0.0])
                    o = np.array([0.0, self.cy, z])
                    inset = 0.011 + 0.014 * ss(0.55, 0.85, a)
                    shrink = 1.0 - (1.0 - prof[min(k, len(prof) - 1)]) * abs(np.sin(th)) ** 1.5   # the sides only
                    R = min((self.ray(o, d, 0.35) or 0.1) - inset, (cage(th) - inset) * shrink)
                    pts.append(o + d * R)
                    ups.append(np.array([0, 0, 1.0]))
                pts = np.array(pts)
                w = np.full(len(pts), 0.0058)
                w[-3:] = [0.0055, 0.005, 0.0045]
                t = np.full(len(pts), 0.0024)
                V, Fb = loft(pts, w, t, L["rib_sides"], ups=ups, cap=0.4)
                self.add(V, Fb, bone)
                self.rib_ends.append(pts[-1])
        # the sternum: down the front from the throat's notch to the ribcage's tip
        zt, zb = j["clavicle_l"][2] - 0.012, hum_undead._costal_z(j, 0.0) + 0.005
        pts, ws = [], []
        for t in np.linspace(0, 1, 6):
            z = zt + (zb - zt) * t
            pts.append(np.array([0.0, self.skin_y(z, -1) + 0.009, z]))
            ws.append(0.016 - 0.004 * t if t < 0.8 else 0.012 - 0.03 * (t - 0.8))
        V, Fb = loft(pts, ws, 0.0035, L["sides"], ups=[1.0, 0, 0], cap=0.3)
        self.add(V, Fb, "spine_03")

    # -------------------------------------------------------------- pelvis

    def pelvis(self):
        j, L = self.j, self.L
        hl, hr = j["thigh_l"], j["thigh_r"]
        hz = float((hl[2] + hr[2]) / 2)
        zic = float(j["spine_01"][2]) + 0.012
        fz = self.skin_y(hz + 0.05, -1)
        bz = self.skin_y(hz + 0.05, +1)
        fp = self.skin_y(hz - 0.03, -1)
        ysym = max(fp + 0.03, float(hl[1]) - 0.062)          # the pubic symphysis: ~6 cm before the hips
        parts = []
        for H in (hl, hr):
            s = np.sign(H[0])
            ax_ = abs(H[0])
            asis = np.array([s * (ax_ + 0.008), max(fz + 0.03, H[1] - 0.05), hz + 0.06])
            crest = [asis,
                     np.array([s * (ax_ + 0.03), H[1] - 0.02, zic - 0.01]),
                     np.array([s * (ax_ + 0.032), H[1] + 0.02, zic]),
                     np.array([s * (ax_ - 0.012), bz - 0.04, zic - 0.006]),
                     np.array([s * 0.042, bz - 0.03, hz + 0.065])]                       # PSIS
            neck = [H + np.array([-s * 0.004, -0.018, 0.026]), H + np.array([-s * 0.014, 0.006, 0.03]),
                    H + np.array([-s * 0.03, 0.03, 0.034])]                               # the blade's foot
            parts.append((s, H, crest, neck))
        sac_l = np.array([0.045, bz - 0.036, zic - 0.012])
        sac_r = np.array([-0.045, bz - 0.036, zic - 0.012])
        coccyx = np.array([0.0, bz - 0.022, hz - 0.045])

        def fn(P):
            d = None
            for s, H, crest, neck in parts:
                # the blade: a fan from the crest down to above the socket, flaring out at the top
                tri = []
                for i in range(len(crest) - 1):
                    nb = neck[min(i * len(neck) // (len(crest) - 1), len(neck) - 1)]
                    tri.append(sd_triangle(P, crest[i], crest[i + 1], nb))
                for i in range(len(neck) - 1):
                    tri.append(sd_triangle(P, neck[i], neck[i + 1], crest[min(2 + i, len(crest) - 1)]))
                e = np.minimum.reduce(tri) - 0.0035
                for a, b in zip(crest[:-1], crest[1:]):                     # the crest's rolled rim
                    e = smin(e, sd_capsule(P, a, b, 0.0058), 0.005)
                cup = sub(sd_sphere(P, H, 0.025), sd_sphere(P, H + np.array([s * 0.009, 0, -0.004]), 0.0205), 0.002)
                e = smin(e, cup, 0.008)
                sym_a = np.array([s * 0.009, ysym, hz - 0.02])
                sym_b = np.array([s * 0.01, ysym + 0.006, hz - 0.052])
                tub = np.array([s * (abs(H[0]) - 0.026), H[1] + 0.022, hz - 0.062])
                e = smin(e, sd_capsule(P, H + np.array([-s * 0.016, -0.016, -0.004]), sym_a, 0.007, 0.0075), 0.006)
                e = smin(e, sd_capsule(P, sym_b, tub, 0.0062, 0.008), 0.006)
                e = smin(e, sd_capsule(P, tub, H + np.array([-s * 0.008, 0.018, -0.018]), 0.0095, 0.008), 0.006)
                e = smin(e, sd_capsule(P, sym_a, sym_b, 0.0075), 0.006)
                e = smin(e, sd_capsule(P, crest[-1], (sac_l if s > 0 else sac_r), 0.008), 0.008)
                d = e if d is None else smin(d, e, 0.004)
            sac = sd_triangle(P, sac_l, sac_r, coccyx) - 0.007                      # the sacrum: a curved wedge
            sac = smin(sac, sd_capsule(P, sac_l, sac_r, 0.009), 0.006)
            return smin(d, sac, 0.008)
        w = abs(hl[0]) + 0.06
        lo = np.array([-w, fp - 0.005, hz - 0.08])
        hi = np.array([w, bz, zic + 0.015])
        V, Fp = decimate(*sdf_mesh(fn, lo, hi, L["voxel"], L["adapt"]), L["dec"]["pelvis"])
        self.add(V, Fp, "pelvis")

    # -------------------------------------------------------------- shoulders and arms

    def shoulders(self):
        j, L = self.j, self.L
        for side in ("l", "r"):
            s = np.sign(j["upperarm_" + side][0])
            sh = j["upperarm_" + side]
            cz = j["clavicle_" + side][2]
            a = np.array([s * 0.02, self.skin_y(cz, -1) + 0.011, cz + 0.004])
            acr = sh + np.array([0, 0.006, 0.026])
            mid = (a + acr) / 2 + np.array([0, -0.01, 0.004])
            pts = [a, a * 0.7 + mid * 0.3, mid, mid * 0.5 + acr * 0.5, acr]
            V, Fb = loft(pts, [0.0068, 0.0058, 0.0055, 0.0058, 0.0072], None, L["sides"], cap=0.4)
            self.add(V, Fb, "clavicle_" + side)
            # the shoulder blade: a plate under the back's skin, its ridge up to the acromion
            S = np.array([s * 0.06, 0, cz - 0.01])
            I = np.array([s * 0.08, 0, cz - 0.15])
            G = sh + np.array([-s * 0.008, 0.022, -0.008])
            for q in (S, I):
                q[1] = self.skin_y(q[2], +1, x=q[0]) - 0.013
            M = S + (I - S) * 0.22

            def fn(P, S=S, I=I, G=G, M=M, acr=acr):
                d = sd_triangle(P, S, I, G) - 0.0028
                d = smin(d, sd_capsule(P, S, I, 0.0045), 0.004)
                d = smin(d, sd_capsule(P, I, G, 0.005), 0.004)
                d = smin(d, sd_capsule(P, M, acr, 0.0055, 0.007), 0.005)
                d = smin(d, sd_sphere(P, G, 0.011), 0.006)
                return d
            pts = np.array([S, I, G, acr])
            V, Fb = decimate(*sdf_mesh(fn, pts.min(0) - 0.015, pts.max(0) + 0.015, L["voxel"], L["adapt"]),
                             L["dec"]["scapula"])
            self.add(V, Fb, "clavicle_" + side)

    def arms(self):
        j, L = self.j, self.L
        for side in ("l", "r"):
            s0, e0, w0 = j["upperarm_" + side], j["lowerarm_" + side], j["hand_" + side]
            u1 = (e0 - s0) / np.linalg.norm(e0 - s0)
            u2 = (w0 - e0) / np.linalg.norm(w0 - e0)
            hinge = np.cross(u1, u2)
            hinge = hinge / np.linalg.norm(hinge) if np.linalg.norm(hinge) > 1e-6 else np.array([0, 1.0, 0])
            # humerus
            Lh = np.linalg.norm(e0 - s0)
            ts = [0.07, 0.16, 0.3, 0.6, 0.82, 0.93, 1.0]
            rx = [0.0125, 0.0092, 0.0085, 0.0085, 0.011, 0.019, 0.016]
            ry = [0.0125, 0.0092, 0.0085, 0.0085, 0.009, 0.0105, 0.0095]
            V, Fb = loft([s0 + u1 * Lh * t for t in ts], rx, ry, L["sides"], ups=hinge, cap=0.35)
            self.add(V, Fb, "upperarm_" + side)
            V, Fb = ball(s0 + u1 * 0.004, 0.0195, L["sides"] + 1, max(3, L["sides"] - 2))
            self.add(V, Fb, "upperarm_" + side)
            # radius and ulna: the ulna on the little finger's side, its hook behind the elbow
            pk = j["pinky_01_" + side] - j["index_01_" + side]
            pk -= u2 * (pk @ u2)
            pk /= np.linalg.norm(pk)
            Lf = np.linalg.norm(w0 - e0)
            back = np.cross(hinge, u2)
            ul = [e0 - u2 * 0.018 + back * 0.004, e0 + pk * 0.004, e0 + u2 * Lf * 0.5 + pk * 0.008,
                  w0 + pk * 0.011 - u2 * 0.006]
            V, Fb = loft(ul, [0.0085, 0.0075, 0.0052, 0.0058], None, L["small"] + 1, cap=0.4)
            self.add(V, Fb, "lowerarm_" + side)
            ra = [e0 - pk * 0.006 + u2 * 0.006, e0 + u2 * Lf * 0.5 - pk * 0.007, w0 - pk * 0.009 - u2 * 0.004]
            V, Fb = loft(ra, [0.0062, 0.005, 0.0092], [0.0062, 0.005, 0.0065], L["small"] + 1, ups=pk, cap=0.3)
            self.add(V, Fb, "lowerarm_" + side)
            self.hand(side)

    def tip(self, bone, along):
        """The skin's farthest point along `along` among the vertices this bone carries (finger and toe tips)."""
        B = self.B
        i = B.sk.index[bone]
        m = B.W[:, i] > 0.4
        if not m.any():
            return None
        P = B.co_raw[m]
        return P[np.argmax((P - self.j[bone]) @ along)]

    def hand(self, side):
        j, L = self.j, self.L
        h0 = j["hand_" + side]
        fingers = ("thumb", "index", "middle", "ring", "pinky")
        knuck = {f: j[f"{f}_01_{side}"] for f in fingers}
        mid = np.mean([knuck[f] for f in ("index", "middle", "ring", "pinky")], 0)
        uh = (mid - h0) / np.linalg.norm(mid - h0)
        pk = knuck["pinky"] - knuck["index"]
        pk -= uh * (pk @ uh)
        pk /= np.linalg.norm(pk)
        carp = h0 + uh * 0.016
        if L["palm"]:                                     # LOD1-2: a palm block to the knuckles (no metacarpals)
            V, Fb = loft([h0 + uh * 0.004, mid - uh * 0.006], [0.014, 0.017], [0.007, 0.006], 4, ups=pk, cap=0.3)
            self.add(V, Fb, "hand_" + side)
        else:
            V, Fb = loft([h0 + uh * 0.004, carp, h0 + uh * 0.028], [0.011, 0.016, 0.015], [0.007, 0.0085, 0.008],
                         L["sides"], ups=pk, cap=0.4)
            self.add(V, Fb, "hand_" + side)
            for f in ("index", "middle", "ring", "pinky"):
                base = h0 + uh * 0.03 + pk * ((knuck[f] - h0) @ pk) * 0.6
                k = knuck[f]
                V, Fb = self.knobbed(base, k - (k - base) / np.linalg.norm(k - base) * 0.004, 0.004)
                self.add(V, Fb, "hand_" + side)
        for f in fingers:
            chain = [j[f"{f}_0{i}_{side}"] for i in (1, 2, 3)]
            d3 = chain[2] - chain[1]
            d3 /= np.linalg.norm(d3)
            t = self.tip(f"{f}_03_{side}", d3)
            end = (t - d3 * 0.004) if t is not None else chain[2] + d3 * 0.018
            pts = chain + [end]
            r0 = 0.0058 if f == "thumb" else 0.0052 if f in ("index", "middle") else 0.0047
            if L["simple"]:
                V, Fb = loft([pts[0], pts[3]], [r0, r0 * 0.8], None, 3, cap=0.4)
                self.add(V, Fb, f"{f}_01_{side}")
                continue
            for i in range(3):
                a, b = pts[i], pts[i + 1]
                u = (b - a) / np.linalg.norm(b - a)
                V, Fb = self.knobbed(a + u * 0.0012, b - u * 0.0012, r0 * (1.0 - 0.15 * i))
                self.add(V, Fb, f"{f}_0{i + 1}_{side}")

    def knobbed(self, a, b, r):
        """A small bone (phalanx, metacarpal, metatarsal): knobby ends, a waist between (LOD0), or plain."""
        if self.L["fr"] >= 3:
            return loft([a, (a + b) / 2, b], [r * 1.05, r * 0.75, r * 0.95], None, self.L["small"], cap=0.5)
        return loft([a, b], [r, r * 0.9], None, self.L["small"], cap=0.5)

    # -------------------------------------------------------------- legs

    def legs(self):
        j, L = self.j, self.L
        for side in ("l", "r"):
            hp, kn, an = j["thigh_" + side], j["calf_" + side], j["foot_" + side]
            s = np.sign(hp[0])
            lat = np.array([s, 0, 0.0])
            V, Fb = ball(hp, 0.021, L["sides"] + 1, max(3, L["sides"] - 2))
            self.add(V, Fb, "thigh_" + side)
            tro = hp + lat * 0.045 + np.array([0, 0.004, -0.03])
            V, Fb = loft([hp, tro], 0.0115, None, L["sides"], cap=0.0)
            self.add(V, Fb, "thigh_" + side)
            if L["extras"]:
                V, Fb = ball(tro + np.array([0, 0.004, 0.006]), 0.0135, L["sides"], 3)
                self.add(V, Fb, "thigh_" + side)
            top = tro + np.array([0, 0, -0.012])
            knee = kn + np.array([0, 0.004, 0.012])
            sh = [top + (knee - top) * t + np.array([0, -0.008 * math.sin(math.pi * t), 0]) for t in
                  (0.0, 0.15, 0.5, 0.82, 0.95, 1.0)]
            V, Fb = loft(sh, [0.013, 0.0115, 0.011, 0.014, 0.024, 0.021], [0.013, 0.0115, 0.011, 0.013, 0.017, 0.015],
                         L["sides"], ups=lat, cap=0.35)
            self.add(V, Fb, "thigh_" + side)
            fwd = np.array([0, -1.0, 0])
            if L["extras"]:                                # the kneecap
                V, Fb = ball(kn + fwd * 0.03 + np.array([0, 0, 0.014]), 0.0135, L["sides"], 3, scale=(1.0, 0.45, 1.2))
                self.add(V, Fb, "thigh_" + side)
            # tibia and fibula
            ua = (an - kn) / np.linalg.norm(an - kn)
            tb = [kn - ua * 0.004 + fwd * 0.002, kn + ua * 0.03, kn + (an - kn) * 0.5 + fwd * 0.004, an - ua * 0.022,
                  an - ua * 0.004]
            V, Fb = loft(tb, [0.026, 0.016, 0.0105, 0.012, 0.0145], [0.02, 0.014, 0.011, 0.011, 0.012], L["sides"],
                         ups=lat, cap=0.25)
            self.add(V, Fb, "calf_" + side)
            if L["extras"]:                                # the inner ankle's knob
                V, Fb = ball(an - lat * 0.017 + np.array([0, 0, -0.004]), 0.0068, L["small"] + 1, 3)
                self.add(V, Fb, "calf_" + side)
            fb = [kn + lat * 0.022 + np.array([0, 0.01, -0.035]), kn + (an - kn) * 0.5 + lat * 0.02 + np.array([0, 0.008, 0]),
                  an + lat * 0.021 + np.array([0, 0.004, -0.008])]
            V, Fb = loft(fb, [0.0068, 0.0042, 0.0068], None, L["small"] + 1, cap=0.4)
            self.add(V, Fb, "calf_" + side)
            self.foot(side, lat)

    def foot(self, side, lat):
        j, L, B = self.j, self.L, self.B
        an, bl, bt = j["foot_" + side], j["ball_" + side], self.jt["ball_" + side]
        i_f, i_b = B.sk.index["foot_" + side], B.sk.index["ball_" + side]
        fm = B.W[:, i_f] > 0.4
        heel_p = B.co_raw[fm][np.argmax(B.co_raw[fm][:, 1])]
        heel = np.array([an[0], heel_p[1] - 0.012, max(heel_p[2], 0.0) + 0.02])
        midf = an + (bl - an) * 0.5
        midf = np.array([midf[0], midf[1], 0.032])
        V, Fb = loft([heel, an + np.array([0, 0.004, -0.02]), midf], [0.014, 0.017, 0.016], [0.016, 0.014, 0.011],
                     L["sides"], ups=lat, cap=0.45)
        self.add(V, Fb, "foot_" + side)
        V, Fb = ball(an + np.array([0, 0, -0.006]), 0.0145, L["sides"], 3)
        self.add(V, Fb, "foot_" + side)
        bm = B.W[:, i_b] > 0.4
        T = B.co_raw[bm]
        across = [-0.024, -0.009, 0.003, 0.013, 0.022]
        base_z = max(float(bl[2]), 0.0) + 0.013
        tips = []
        for k, off in enumerate(across):
            x = bl[0] + lat[0] * off
            near = T[np.abs(T[:, 0] - x) < 0.007]
            ty = float(near[:, 1].min()) + 0.006 if len(near) else bt[1]
            tips.append(np.array([x, ty, max(base_z - 0.004, 0.008)]))
        if L["palm"]:                                     # LOD1-2: the forefoot and the toes as two flat blocks
            c0 = np.array([bl[0], bl[1] + 0.004, base_z])
            V, Fb = loft([midf, c0], [0.02, 0.026], [0.008, 0.006], 4, ups=lat, cap=0.2)
            self.add(V, Fb, "foot_" + side)
            tc = np.mean(tips, 0)
            V, Fb = loft([c0, tc], [0.025, 0.02], [0.005, 0.004], 4, ups=lat, cap=0.2)
            self.add(V, Fb, "ball_" + side)
            return
        for k, off in enumerate(across):
            x = bl[0] + lat[0] * off
            mh = np.array([x, bl[1] + 0.004, base_z])
            st = np.array([an[0] + lat[0] * off * 0.5, midf[1] + 0.012, 0.03])
            V, Fb = self.knobbed(st, mh, 0.0055 if k == 0 else 0.0038)
            self.add(V, Fb, "foot_" + side)
            tipp = tips[k]
            m1 = mh + (tipp - mh) * 0.55
            rt = 0.0055 if k == 0 else 0.0036
            for a, b in ((mh, m1), (m1, tipp)):
                V, Fb = self.knobbed(a, b, rt)
                self.add(V, Fb, "ball_" + side)

    def build_all(self):
        self.skull()
        self.spine()
        self.ribs()
        self.pelvis()
        self.shoulders()
        self.arms()
        self.legs()
        return self.pieces


# ------------------------------------------------------------------ objects

def _self_ao(V, F, rays=10, dist=0.035):
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    for f in F:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bm.normal_update()
    bvh = BVHTree.FromBMesh(bm)
    no = np.array([v.normal[:] for v in bm.verts])
    bm.free()
    rng = np.random.default_rng(5)
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
        o = Vector(p) + n * 0.0008
        hit = sum(bvh.ray_cast(o, t * h[0] + b * h[1] + n * h[2], dist)[0] is not None for h in Hs)
        ao[i] = 1 - hit / rays
    return ao


def glow_material():
    """M_HumanGlow (Blender preview): emission in the object's hum_glow colour (Unity: Humans/Glow)."""
    import bpy
    import hum_material as M
    mat = bpy.data.materials.get("M_HumanGlow") or bpy.data.materials.new("M_HumanGlow")
    mat.use_nodes = True
    T = M._NT(mat)
    em = T.node('ShaderNodeEmission')
    T.link(T.attr("hum_glow"), em.inputs['Color'])
    em.inputs['Strength'].default_value = 6.0
    out = T.node('ShaderNodeOutputMaterial')
    T.link(em.outputs['Emission'], out.inputs['Surface'])
    return mat


def bone_material():
    """M_HumanBone: hum_material.cloth_material over the bone pattern (T_Cloth_Bone)."""
    import bpy
    import hum_material as M
    tex = bpy.data.images.get("T_Cloth_Bone") or bone_texture()
    return M.cloth_material(tex, "M_HumanBone", roughness=0.7)


def bone_texture(size=256, seed=29):
    """T_Cloth_Bone (tiling, grey): porous, faintly streaked old bone; projected in 3D (Unity _Triplanar)."""
    import os
    import hum_paint
    rng = np.random.default_rng(seed)
    u = np.arange(size) / size
    X, Y = np.meshgrid(u, u)
    out = np.zeros((size, size))
    for _ in range(40):
        k = rng.integers(-14, 15, 2)
        if not k.any():
            continue
        out += np.cos(2 * np.pi * (k[0] * X + k[1] * Y) + rng.uniform(0, 2 * np.pi)) / np.hypot(*k)
    streak = np.zeros((size, size))
    for _ in range(12):
        k = np.array([rng.integers(-2, 3), rng.integers(10, 30)])
        streak += np.cos(2 * np.pi * (k[0] * X + k[1] * Y) + rng.uniform(0, 2 * np.pi)) / k[1]
    pores = np.zeros((size, size))
    for _ in range(60):
        k = rng.integers(-60, 61, 2)
        pores += np.cos(2 * np.pi * (k[0] * X + k[1] * Y) + rng.uniform(0, 2 * np.pi))
    v = 0.86 + 0.07 * out / np.abs(out).max() + 0.04 * streak / np.abs(streak).max()
    v -= 0.1 * hum_paint.smoothstep(0.55, 0.9, pores / np.abs(pores).max())
    M = np.stack([v, v * 0.985, v * 0.96, np.ones_like(v)], -1)
    return hum_paint.save_image("T_Cloth_Bone", M, os.path.join(hum_paint.TEX_DIR, "T_Cloth_Bone.png"))


def make_object(scene, name, pieces, arm, sk, lod=0):
    """One mesh from the pieces: rigid weights, ClothData (self-AO), rest UVs, Region 0 (never covered), slots
    bone + glow; replaces an object of that name."""
    import bpy
    import hum_hair
    import hum_lod
    import hum_rig
    verts, faces, bones, mats = [], [], [], []
    off = 0
    for V, F, bone, mat in pieces:
        verts.append(V)
        faces.extend(tuple(i + off for i in f) for f in F)
        bones.extend([bone] * len(V))
        mats.extend([mat] * len(F))
        off += len(V)
    V = np.vstack(verts)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], faces)
    me.update()
    me.polygons.foreach_set("material_index", np.array(mats, np.int32))
    for p in me.polygons:
        p.use_smooth = True
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", np.full(len(me.loops) * 2, 0.5, np.float32))
    reg = me.uv_layers.new(name="Region")
    reg.data.foreach_set("uv", np.zeros(len(me.loops) * 2, np.float32))
    C.write_rest_uv(me, V)
    ao = _self_ao(V, faces) if lod < 2 else np.ones(len(V))
    att = me.color_attributes.new("ClothData", 'FLOAT_COLOR', 'POINT')
    data = np.stack([ao, np.zeros(len(V)), np.zeros(len(V)), np.ones(len(V))], 1)
    att.data.foreach_set("color", data.astype(np.float32).ravel())
    ob = hum_hair.replace_object(scene, name, me)
    if lod == 0:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        bpy.data.collections.get(C.CLOTH_COL).objects.link(ob)
    else:
        hum_lod._place(scene, ob, lod)
    ob.data.materials.append(bone_material())
    ob.data.materials.append(glow_material())
    ob["hum_slot"] = "skeleton"
    W = np.zeros((len(V), len(sk.bones)))
    W[np.arange(len(V)), [sk.index[b] for b in bones]] = 1.0
    hum_rig.skin(ob, arm, sk, W)
    return ob


def build(scene, B, name, arm, sk, body=None):
    """Cloth_Skeleton_<tag> and its LODs in the current build space (hum_cloth.BUILD); returns the LOD0 object
    (hum_builds.build_wardrobe stores it at rest with the others)."""
    import bpy
    head = bpy.data.objects["Head"]
    import hum_rig
    hum_rig.rest(arm)
    out = None
    for lod in (0, 1, 2):
        pieces = Skel(B, head, lod).build_all()
        nm = C.cloth_name(name) + ("" if lod == 0 else f"_L{lod}")
        ob = make_object(scene, nm, pieces, arm, sk, lod)
        ob.hide_set(True)
        ob.hide_render = True
        if lod == 0:
            out = ob
        else:
            import hum_builds
            hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
    return out


SKELETON = {
    "Skeleton": dict(slot="skeleton", layer=0, material="bone", make=build, builds=("Undead",),
                     hide=list(range(16)), cover=[], hides_head=True, hides_face_hair=True, hides_hair=True),
}
