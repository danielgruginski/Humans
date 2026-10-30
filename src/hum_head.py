"""The shipped head: MPFB head topology cut at the neck, our own eyeballs, a stylisation
warp, and every face slider as a shape key.

Coordinates flow:  MPFB state -> coords(source) -> stylize() -> head verts (+ eyes fitted
to the helper eye spheres).  A slider's shape key is that pipeline with the slider on,
minus the same pipeline at the neutral face.
"""
import math
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

import hum_mpfb

NECK_CUT_Z = 1.40
PAINT_GROUPS = ("lips", "ears", "scalp")          # faces fully above this plane (neutral face) make the head
HEAD = "Head"
EYE_SEGMENTS = 20
EYE_THETAS = tuple(180 * i / 14 for i in range(1, 14))      # ring angles from the front pole (deg), evenly spaced

# Stylisation (applied to every captured state, so it is baked into the basis and the keys):
# MPFB's own sculpted targets for nose/mouth/jaw, plus smooth warps for eyes and cranium.
STYLE = dict(
    eye_scale=1.28,        # eye region grows around each eye centre (smooth falloff) ...
    eye_radius=0.055,      # ... to nothing at this radius (m)
    cranium=1.05,          # skull above the brows grows a little
    targets={
        # MPFB's own nose, a little shorter (2026-10-30; was also nose-volume-decr 0.55, nose-point-width-decr 0.45, which
        # took the tip to a point and the flanks to a triangle); the wings are NOSE_FORM
        "nose-scale-vert-decr": 0.25,
        # wider, flatter lips with a bow (2026-10-30; was 41.5 mm wide, the upper lip 3.8 mm over the lower, the seam 7.3 mm deep)
        "mouth-scale-horiz-incr": 0.3, "mouth-scale-depth-decr": 0.8, "mouth-scale-vert-decr": 0.3,
        "mouth-lowerlip-volume-decr": 0.45, "mouth-upperlip-volume-decr": 0.7, "mouth-upperlip-height-decr": 0.4,
        "mouth-angles-up": 0.2, "mouth-cupidsbow-incr": 0.5, "mouth-philtrum-volume-incr": 0.5,
        "chin-width-decr": 0.3,
        "l-cheek-volume-incr": 0.3, "r-cheek-volume-incr": 0.3,
        # a wider, taller opening (2026-10-30; was eye-height2-decr 0.7, a 7.8 mm slit that hid half the iris)
        "l-eye-scale-incr": 0.5, "r-eye-scale-incr": 0.5, "l-eye-height2-incr": 0.1, "r-eye-height2-incr": 0.1,
    },
)
# The eyeball against MPFB's helper sphere: 31 mm across (was 36), its iris where the lids want it and clear of the
# lids' depth (the helper sits 2.7 mm behind them, low and toward the nose in the opening). Metres; x outward.
EYE_BALL = 0.852
EYE_SHIFT = (0.0016, -0.0020, -0.0012)
NO_STYLE = dict(eye_scale=1.0, eye_radius=0.05, cranium=1.0, targets={})
# The lips meet (mouth pass, 2026-10-30): MPFB leaves a 0.5 mm slit from x 18 mm to the corner, and the corner vertex
# spikes down past the line; through the slit the dark inside of the mouth read as black hooks. Head vertex numbers on
# +x, the mesh is mirrored: the lower rim lifted onto the upper (mm), the corner raised to the line with a falloff.
LIP_LIFT = {493: 0.3, 494: 0.1, 2656: 0.4, 2634: 0.1, 2622: 0.2, 2658: 0.2, 2590: 0.2, 2589: 0.4, 2598: 0.4, 2595: 0.3, 2596: 0.8,
            2597: 0.8, 3417: 0.3, 3418: 0.5, 3419: 0.5, 2584: 0.3}
LIP_RIM = (2617, 2571, 2570, 2585, 2583, 2584)         # the upper rim from x 16 mm out; the last one is the corner
LIP_RAISE, LIP_RAISE_R = 0.0003, 0.004
# The nose's wings (nose pass, 2026-10-30): MPFB's nose is one bulb, its flanks run straight down from the bridge. A lobe
# on each side, an ellipsoid around the wing (metres from the tip vertex; x outward), pushed out inside and creased along
# its edge, the underside left alone. Moves along the skin's normal.
NOSE_TIP = 1431
NOSE_FORM = dict(centre=(0.013, 0.012, -0.0015), radii=(0.0065, 0.008, 0.0075), lobe=0.0018, crease=0.0014, width=0.3)
# The nostrils: MPFB's is a folded pouch; it shows lit tongues and black slits (walls edge-on to the view, facing away from
# the light). Rings of vertices outward from its deepest vertex (+x; mirrored): the inner rings relaxed into a skin over
# the opening (ring NOSTRIL_RIM stays), then pushed up into a pit shallow enough to keep its walls out of that: the
# paint makes the dark (hum_paint). A deep pit brings the slits back.
NOSTRIL_SEED, NOSTRIL_RIM, NOSTRIL_PIT = 2548, 5, 0.001
_MIRROR = {}
_QUADS = {}
_NOSTRIL = {}

# Mild body stylisation (applied after the face stylisation, never touches the head or the neck ring)
BODY_STYLE = dict(
    body_scale=0.92,       # everything below the shoulders, about the neck joint: the head reads bigger
    hand_scale=1.12,       # about the wrists
    foot_scale=1.06,       # about the ankles
)


def _members(src, name):
    return hum_mpfb.group_members(src, name)


class Rig:
    """Vertex index sets on the MPFB source, computed once."""

    def __init__(self, src):
        C = hum_mpfb.capture(src)
        body = _members(src, "body")
        me = src.data
        keep_face, cut = head_faces(me, C, body)
        self.neck_ring = np.array(sorted({v for e in cut for v in e}), dtype=np.int64)
        keep = np.zeros(len(C), bool)
        for p in me.polygons:
            if keep_face[p.index]:
                keep[list(p.vertices)] = True
        faces = [tuple(p.vertices) for p in me.polygons if keep_face[p.index]]
        used = np.array(sorted({v for f in faces for v in f}), dtype=np.int64)
        self.head_idx = used
        remap = {v: i for i, v in enumerate(used)}
        self.faces = [tuple(remap[v] for v in f) for f in faces]
        uv = me.uv_layers[0].data
        loop_uv = {}
        for p in me.polygons:
            if keep_face[p.index]:
                loop_uv[p.index] = [tuple(uv[li].uv) for li in p.loop_indices]
        self.face_uvs = list(loop_uv.values())
        self.groups = {g: _members(src, g) for g in (
            "helper-l-eye", "helper-r-eye", "joint-l-eye-target", "joint-r-eye-target",
            "joint-mouth", "joint-jaw", "joint-head", "joint-head-2", "joint-neck", "lips",
            "joint-l-upperlid", "joint-r-upperlid", "joint-l-lowerlid", "joint-r-lowerlid",
            "joint-l-hand", "joint-r-hand", "joint-l-ankle", "joint-r-ankle", "joint-ground")}
        # MPFB paint regions carried onto the head as vertex groups
        pos = {v: i for i, v in enumerate(used)}
        self.regions = {g: np.array([pos[v] for v in _members(src, g) if v in pos], dtype=np.int64)
                        for g in PAINT_GROUPS}

    def centre(self, C, g):
        return C[self.groups[g]].mean(0)


def neck_loop(me, C, body_set, z=NECK_CUT_Z):
    """Edge loop around the neck nearest height z, walked from the front midline."""
    edge_faces = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_faces.setdefault(ek, []).append(p.index)
    vert_edges = {}
    for ek in edge_faces:
        for v in ek:
            vert_edges.setdefault(v, []).append(ek)
    cand = [v for v in body_set if abs(C[v, 0]) < 1e-4 and abs(C[v, 2] - z) < 0.03]
    v0 = min(cand, key=lambda v: C[v, 1] + 5 * abs(C[v, 2] - z))     # front of the neck
    e0 = max(vert_edges[v0], key=lambda e: abs(C[e[0], 0] - C[e[1], 0]))
    loop, v, e = [e0], v0, e0
    while True:
        v = e[0] if e[1] == v else e[1]
        faces_e = set(edge_faces[e])
        nxt = [f for f in vert_edges[v] if f != e and not faces_e & set(edge_faces[f])]
        if len(nxt) != 1:
            raise RuntimeError(f"neck loop hit a pole at vertex {v}")
        e = nxt[0]
        if e == e0:
            return set(loop)
        loop.append(e)
        if len(loop) > 500:
            raise RuntimeError("neck loop did not close")


def head_faces(me, C, body):
    """Faces of the body above the neck loop (flood fill from the crown, not crossing the loop)."""
    body_set = set(int(i) for i in body)
    cut = neck_loop(me, C, body_set)
    edge_faces = {}
    for p in me.polygons:
        if all(v in body_set for v in p.vertices):
            for ek in p.edge_keys:
                edge_faces.setdefault(ek, []).append(p.index)
    top = max(body_set, key=lambda v: C[v, 2])
    start = next(p.index for p in me.polygons if top in p.vertices)
    keep = np.zeros(len(me.polygons), bool)
    stack = [start]
    keep[start] = True
    while stack:
        f = stack.pop()
        for ek in me.polygons[f].edge_keys:
            if ek in cut:
                continue
            for g in edge_faces.get(ek, ()):
                if not keep[g]:
                    keep[g] = True
                    stack.append(g)
    return keep, cut


def _smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _bump(C, c, scale, R):
    """Scale about c by `scale` at the centre, easing to 1 at radius R (C1-smooth)."""
    d = C - c
    t = np.linalg.norm(d, axis=1) / R
    f = np.where(t < 1, (1 - t * t) ** 2, 0.0)
    return C + d * ((scale - 1.0) * f)[:, None]


def stylize(C, rig, style=STYLE):
    """Stylisation warp on full MPFB coords (landmarks taken from the same coords)."""
    s = style
    hc = rig.centre(C, "joint-head")
    brow = rig.centre(C, "helper-l-eye")[2] + 0.01
    w = _smoothstep((C[:, 2] - brow) / 0.08)
    C = C + (C - hc) * ((s["cranium"] - 1.0) * w)[:, None]
    for side in ("l", "r"):
        C = _bump(C, rig.centre(C, f"helper-{side}-eye"), s["eye_scale"], s["eye_radius"])
    return C


def eye_fit(C, rig, side):
    P = C[rig.groups[f"helper-{side}-eye"]]
    c = P.mean(0)
    r = float(np.linalg.norm(P - c, axis=1).mean())
    t = rig.centre(C, f"joint-{side}-eye-target")
    fwd = t - c
    fwd /= np.linalg.norm(fwd)
    return c, r, fwd


def _eye_unit():
    """Unit eyeball looking down -Y: verts, faces, and a front-projected UV (iris centre = 0.5,0.5)."""
    verts, faces = [], []
    verts.append((0, -1, 0))                                  # front pole
    for deg in EYE_THETAS:
        th = math.radians(deg)                                # 0 = front
        for j in range(EYE_SEGMENTS):
            ph = 2 * math.pi * j / EYE_SEGMENTS
            verts.append((math.sin(th) * math.cos(ph), -math.cos(th), math.sin(th) * math.sin(ph)))
    verts.append((0, 1, 0))
    nr = len(EYE_THETAS)
    ring = lambda i, j: 1 + (i - 1) * EYE_SEGMENTS + (j % EYE_SEGMENTS)
    for j in range(EYE_SEGMENTS):
        faces.append((0, ring(1, j + 1), ring(1, j)))
    for i in range(1, nr):
        for j in range(EYE_SEGMENTS):
            faces.append((ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)))
    last = len(verts) - 1
    for j in range(EYE_SEGMENTS):
        faces.append((ring(nr, j), ring(nr, j + 1), last))
    # the loops above wind inward; reversed, the normals point out of the eyeball. Inward eyes look right in
    # Blender (it draws both sides) but Unity culls their front half and shows the inside of the back half,
    # whose front-projected UVs repeat the iris: a hollow eye that follows the camera.
    faces = [tuple(reversed(f)) for f in faces]
    V = np.array(verts)
    return V, faces


_EYE = _eye_unit()


def eye_centre(C, rig, side, shrink=0.96):
    """The eyeball's centre and radius: the helper's front pole kept, then EYE_SHIFT."""
    c, r, _ = eye_fit(C, rig, side)
    R = r * shrink
    Rn = R * EYE_BALL
    sign = 1.0 if c[0] >= 0 else -1.0
    cn = c + np.array((sign * EYE_SHIFT[0], (R - Rn) * -1 + EYE_SHIFT[1], EYE_SHIFT[2]))
    return cn, Rn


def eye_verts(C, rig, side):
    """The ball looks straight ahead (the helper's own axis looks 4.6 deg down and 2.4 deg out: a vacant stare)."""
    cn, Rn = eye_centre(C, rig, side)
    return _EYE[0] * Rn + cn


def retemplate_eyes(ob, old_template):
    """Swap the eyeballs of an existing head (basis and every shape key) for the current _EYE template.

    In every key each eye is an affine image of the template (fitted spheres, and correctives / residuals are
    linear combinations of those), so the affine map is fitted per key and eye from the old template and
    applied to the new one: the blend shapes still sum exactly as before. Head verts are untouched; the eyes
    stay the last verts (left, then right), on material 1, rigid on the 'head' group, front-projected UVs."""
    import bmesh
    me = ob.data
    nh, ne_old = ob["n_head_verts"], ob["n_eye_verts"]
    U_old = np.c_[old_template, np.ones(len(old_template))]
    U_new = _EYE[0]
    ne = len(U_new)
    keys = me.shape_keys.key_blocks
    new_co, worst = {}, 0.0
    for k in keys:
        a = np.zeros(len(me.vertices) * 3)
        k.data.foreach_get("co", a)
        a = a.reshape(-1, 3)
        eyes = []
        for s in range(2):
            P = a[nh + s * ne_old: nh + (s + 1) * ne_old]
            M, *_ = np.linalg.lstsq(U_old, P, rcond=None)      # P = [u 1] @ M
            worst = max(worst, float(np.abs(U_old @ M - P).max()))
            eyes.append(U_new @ M[:3] + M[3])
        new_co[k.name] = np.vstack(eyes)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    old = [bm.verts[i] for i in range(nh, nh + 2 * ne_old)]
    # new eyes first, old ones deleted after: deleting first lets bmesh reuse the freed slots, which scrambles
    # the new verts' order (it must stay left eye, right eye, template order)
    shape = {k.name: bm.verts.layers.shape[k.name] for k in keys}
    deform = bm.verts.layers.deform.verify()
    uv = bm.loops.layers.uv.active
    head_g = ob.vertex_groups["head"].index
    basis = keys[0].name
    added = []
    for i in range(2 * ne):
        v = bm.verts.new(new_co[basis][i])
        for name, lay in shape.items():
            v[lay] = new_co[name][i]
        v[deform][head_g] = 1.0
        added.append(v)
    for s in range(2):
        for f in _EYE[1]:
            face = bm.faces.new([added[s * ne + i] for i in f])
            face.material_index = 1
            face.smooth = True
            for loop, ti in zip(face.loops, f):                # loops keep the order the face was made in
                u = U_new[ti]
                loop[uv].uv = (0.5 + 0.5 * u[0], 0.5 + 0.5 * u[2])
    bmesh.ops.delete(bm, geom=old, context='VERTS')
    bm.verts.index_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    ob["n_eye_verts"] = ne
    return worst


def stylize_body(C, rig, s=BODY_STYLE):
    neck = rig.centre(C, "joint-neck")
    w = _smoothstep((neck[2] - 0.05 - C[:, 2]) / 0.10)            # 0 at the neck ring .. 1 below the shoulders
    C = C + (C - neck) * ((s["body_scale"] - 1.0) * w)[:, None]
    for side in ("l", "r"):
        C = _bump(C, rig.centre(C, f"joint-{side}-hand"), s["hand_scale"], 0.13)
        C = _bump(C, rig.centre(C, f"joint-{side}-ankle"), s["foot_scale"], 0.16)
    return C


def mirrored(H):
    """Head vertex numbers: i -> its twin across x."""
    if len(H) not in _MIRROR:
        kd = KDTree(len(H))
        for i, v in enumerate(H):
            kd.insert((-v[0], v[1], v[2]), i)
        kd.balance()
        _MIRROR[len(H)] = np.array([kd.find(v)[1] for v in H])
    return _MIRROR[len(H)]


def lip_seal(H):
    """The move that closes the lips (metres), for a head's skin in any state."""
    D = np.zeros(H.shape)
    mir = mirrored(H)
    for v in (LIP_RIM[-1], mir[LIP_RIM[-1]]):
        t = np.clip(1.0 - np.linalg.norm(H - H[v], axis=1) / LIP_RAISE_R, 0.0, 1.0)
        D[:, 2] += LIP_RAISE * t * t * (3 - 2 * t)
    for v, mm in LIP_LIFT.items():
        D[list({v, mir[v]}), 2] += mm / 1000
    return D


def _vertex_normals(H, faces):
    if len(faces) not in _QUADS:
        _QUADS[len(faces)] = np.array([f if len(f) == 4 else (f[0], f[1], f[2], f[2]) for f in faces])
    Q = _QUADS[len(faces)]
    fn = np.cross(H[Q[:, 2]] - H[Q[:, 0]], H[Q[:, 3]] - H[Q[:, 1]])
    N = np.zeros(H.shape)
    for c in range(4):
        np.add.at(N, Q[:, c], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def nostril_rings(H, faces):
    """Per side: the rings of head vertices from the nostril's deepest one out to its rim."""
    if len(faces) not in _NOSTRIL:
        adj = {}
        for f in faces:
            for a, b in zip(f, f[1:] + f[:1]):
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
        mir = mirrored(H)
        sides = []
        for seed in (NOSTRIL_SEED, int(mir[NOSTRIL_SEED])):
            rings, seen = [[seed]], {seed}
            for _ in range(NOSTRIL_RIM):
                nxt = sorted({w for v in rings[-1] for w in adj[v]} - seen)
                seen.update(nxt)
                rings.append(nxt)
            sides.append(rings)
        _NOSTRIL[len(faces)] = (sides, adj)
    return _NOSTRIL[len(faces)]


def _nostril_pits(H, faces):
    """H with the nostrils' inner rings replaced."""
    sides, adj = nostril_rings(H, faces)
    H = H.copy()
    for rings in sides:
        inner = [v for r in rings[:-1] for v in r]
        at = {v: i for i, v in enumerate(inner)}
        A = np.eye(len(inner))
        b = np.zeros((len(inner), 3))
        for v, i in at.items():
            for w in adj[v]:
                if w in at:
                    A[i, at[w]] -= 1.0 / len(adj[v])
                else:
                    b[i] += H[w] / len(adj[v])
        X = np.linalg.solve(A, b)
        k = np.array([n for n, r in enumerate(rings[:-1]) for _ in r], dtype=float)
        X[:, 2] += NOSTRIL_PIT * (1.0 - (k / NOSTRIL_RIM) ** 2)
        H[inner] = X
    return H


def nose_form(H, faces):
    """The wings' move (metres), for a head's skin in any state."""
    f = NOSE_FORM
    P = H - H[NOSE_TIP]
    e = np.sqrt(((np.abs(P[:, 0]) - f["centre"][0]) / f["radii"][0]) ** 2 + ((P[:, 1] - f["centre"][1]) / f["radii"][1]) ** 2
                + ((P[:, 2] - f["centre"][2]) / f["radii"][2]) ** 2)
    near = e < 2.5
    N = _vertex_normals(H, faces)
    up = np.clip((N[:, 2] + 0.55) / 0.45, 0.0, 1.0)
    under = np.clip((N[:, 2] + 0.95) / 0.5, 0.0, 1.0)      # the lobe wraps under the wing further than the crease does
    t = np.clip((1.0 - e) / 0.5, 0.0, 1.0)
    # the crease fades on the low front arc, where the wing runs into the tip's underside
    low = np.clip((P[:, 2] - f["centre"][2]) / (0.6 * f["radii"][2]) + 1.0, 0.0, 1.0)
    low = np.where(P[:, 1] < f["centre"][1], low * low * (3 - 2 * low), 1.0)
    d = f["lobe"] * t * t * (3 - 2 * t) * under * under * (3 - 2 * under) \
        - f["crease"] * low * np.exp(-((e - 1.0) / f["width"]) ** 2) * up * up * (3 - 2 * up)
    D = N * (d * near)[:, None]
    # two rounds of averaging over the mesh: its quads are 3 mm here, about the crease's width
    Q = _QUADS[len(faces)]
    a, b = np.hstack([Q[:, c] for c in range(4)]), np.hstack([Q[:, (c + 1) % 4] for c in range(4)])
    for _ in range(2):
        S, W = np.zeros(D.shape), np.zeros(len(D))
        np.add.at(S, a, D[b])
        np.add.at(W, a, 1.0)
        D = 0.5 * D + 0.5 * S / np.maximum(W, 1.0)[:, None]
    return _nostril_pits(H + D, faces) - H


def full_coords(src, rig, macros=None, race=None, targets=None, style=STYLE, body_style=BODY_STYLE, deform=None):
    """All MPFB vertices (incl. joint helpers) for one state: face stylisation, body stylisation,
    feet on the ground (the skeleton carries height changes; keys are residuals, see hum_rig).
    deform: C -> C, a shape of our own on top (hum_faces.DEFORMS: the orcs' forearms and hands); the joint
    helpers move with it, so the skeleton follows."""
    t = dict(style["targets"])
    for k, v in (targets or {}).items():
        t[k] = t.get(k, 0.0) + v
    C = stylize(hum_mpfb.capture(src, macros, race, t), rig, style)
    if style is not NO_STYLE:
        C[rig.head_idx] += lip_seal(C[rig.head_idx]) + nose_form(C[rig.head_idx], rig.faces)
    C = stylize_body(C, rig, body_style)
    if deform is not None:
        C = deform(C)
    C[:, 2] -= rig.centre(C, "joint-ground")[2]
    return C


def head_coords(src, rig, macros=None, race=None, targets=None, style=STYLE, C=None):
    """(head verts, left eye verts, right eye verts) for one MPFB state."""
    if C is None:
        C = full_coords(src, rig, macros, race, targets, style)
    return C[rig.head_idx], eye_verts(C, rig, "l"), eye_verts(C, rig, "r")


def all_coords(src, rig, C=None, **state):
    h, l, r = head_coords(src, rig, C=C, **state)
    return np.vstack([h, l, r])


# ------------------------------------------------------------------ mesh

def build(scene, src, rig, name=HEAD, materials=(), **state):
    """Create/replace the head object (head + both eyes in one mesh, eyes on material 1)."""
    h, l, r = head_coords(src, rig, **state)
    nh = len(h)
    ne = len(_EYE[0])
    verts = np.vstack([h, l, r])
    faces = list(rig.faces)
    eye_faces = [tuple(v + nh + k * ne for v in f) for k in range(2) for f in _EYE[1]]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces + eye_faces)
    me.update()
    for m in materials:
        me.materials.append(m)
    # UVs: MPFB's for the head (re-laid out later), front projection for the eyes
    uvl = me.uv_layers.new(name="UVMap")
    li = 0
    for fi, p in enumerate(me.polygons):
        if fi < len(faces):
            for k, l_ in enumerate(p.loop_indices):
                uvl.data[l_].uv = rig.face_uvs[fi][k]
        else:
            for l_ in p.loop_indices:
                vi = me.loops[l_].vertex_index - nh
                v = _EYE[0][vi % ne]
                mx = 1 if vi < ne else -1                     # mirrored on the right: u < 0.5 is the inner corner
                uvl.data[l_].uv = (0.5 + 0.5 * mx * v[0], 0.5 + 0.5 * v[2])
            p.material_index = 1
    for p in me.polygons:
        p.use_smooth = True
    old = bpy.data.objects.get(name)
    if old is not None:
        old_me = old.data
        old.data = me
        bpy.data.meshes.remove(old_me)
        ob = old
    else:
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
    for g, idx in rig.regions.items():
        vg = ob.vertex_groups.get(g) or ob.vertex_groups.new(name=g)
        vg.add(idx.tolist(), 1.0, 'REPLACE')
    ob["n_head_verts"] = nh
    ob["n_eye_verts"] = ne
    return ob


def add_key(ob, name, coords, basis):
    if ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    kb = ob.data.shape_keys.key_blocks.get(name) or ob.shape_key_add(name=name, from_mix=False)
    kb.data.foreach_set("co", coords.astype(np.float32).ravel())
    kb.slider_min, kb.slider_max = 0.0, 1.0
    return kb
