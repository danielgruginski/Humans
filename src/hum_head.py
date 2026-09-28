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

import hum_mpfb

NECK_CUT_Z = 1.40
PAINT_GROUPS = ("lips", "ears", "scalp")          # faces fully above this plane (neutral face) make the head
HEAD = "Head"
EYE_SEGMENTS, EYE_RINGS = 20, 14

# Stylisation (applied to every captured state, so it is baked into the basis and the keys):
# MPFB's own sculpted targets for nose/mouth/jaw, plus smooth warps for eyes and cranium.
STYLE = dict(
    eye_scale=1.28,        # eye region grows around each eye centre (smooth falloff) ...
    eye_radius=0.055,      # ... to nothing at this radius (m)
    cranium=1.05,          # skull above the brows grows a little
    targets={
        "nose-volume-decr": 0.55, "nose-point-width-decr": 0.45, "nose-scale-vert-decr": 0.25,
        "mouth-scale-horiz-decr": 0.25, "mouth-scale-depth-decr": 0.35,
        "mouth-lowerlip-volume-decr": 0.3, "mouth-upperlip-volume-decr": 0.15, "chin-width-decr": 0.3,
        "l-cheek-volume-incr": 0.3, "r-cheek-volume-incr": 0.3,
        "l-eye-height2-decr": 0.7, "r-eye-height2-decr": 0.7,        # relaxed upper lids
    },
)
NO_STYLE = dict(eye_scale=1.0, eye_radius=0.05, cranium=1.0, targets={})

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
    for i in range(1, EYE_RINGS):
        th = math.pi * i / EYE_RINGS                          # 0 = front
        for j in range(EYE_SEGMENTS):
            ph = 2 * math.pi * j / EYE_SEGMENTS
            verts.append((math.sin(th) * math.cos(ph), -math.cos(th), math.sin(th) * math.sin(ph)))
    verts.append((0, 1, 0))
    ring = lambda i, j: 1 + (i - 1) * EYE_SEGMENTS + (j % EYE_SEGMENTS)
    for j in range(EYE_SEGMENTS):
        faces.append((0, ring(1, j + 1), ring(1, j)))
    for i in range(1, EYE_RINGS - 1):
        for j in range(EYE_SEGMENTS):
            faces.append((ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)))
    last = len(verts) - 1
    for j in range(EYE_SEGMENTS):
        faces.append((ring(EYE_RINGS - 1, j), ring(EYE_RINGS - 1, j + 1), last))
    V = np.array(verts)
    return V, faces


_EYE = _eye_unit()


def eye_verts(C, rig, side, shrink=0.96):
    c, r, fwd = eye_fit(C, rig, side)
    q = Vector((0, -1, 0)).rotation_difference(Vector(fwd)).to_matrix()
    M = np.array(q) * (r * shrink)
    return _EYE[0] @ M.T + c


def stylize_body(C, rig, s=BODY_STYLE):
    neck = rig.centre(C, "joint-neck")
    w = _smoothstep((neck[2] - 0.05 - C[:, 2]) / 0.10)            # 0 at the neck ring .. 1 below the shoulders
    C = C + (C - neck) * ((s["body_scale"] - 1.0) * w)[:, None]
    for side in ("l", "r"):
        C = _bump(C, rig.centre(C, f"joint-{side}-hand"), s["hand_scale"], 0.13)
        C = _bump(C, rig.centre(C, f"joint-{side}-ankle"), s["foot_scale"], 0.16)
    return C


def full_coords(src, rig, macros=None, race=None, targets=None, style=STYLE, body_style=BODY_STYLE):
    """All MPFB vertices (incl. joint helpers) for one state: face stylisation, body stylisation,
    feet on the ground (the skeleton carries height changes; keys are residuals, see hum_rig)."""
    t = dict(style["targets"])
    for k, v in (targets or {}).items():
        t[k] = t.get(k, 0.0) + v
    C = stylize(hum_mpfb.capture(src, macros, race, t), rig, style)
    C = stylize_body(C, rig, body_style)
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
                v = _EYE[0][(me.loops[l_].vertex_index - nh) % ne]
                uvl.data[l_].uv = (0.5 + 0.5 * v[0], 0.5 + 0.5 * v[2])
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
