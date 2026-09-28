"""Head paint as masks, combined with per-character colours by the skin shader.

T_Head_MaskA  R blush zones (cheeks, nose, ears, knuckle-warm spots)
              G lips
              B shading (AO, cavities, painted top light), stored /SHADE_MAX so 1.0 = SHADE_MAX
              A lash line + lid crease (dark)
T_Head_MaskB  R stubble / beard shadow
              G age lines (forehead, crow's feet, nasolabial, under-eye)
              B freckles
              A brows (painted; geometry brows may cover them later)
T_Eye         front-projected eyeball, iris as a radial mask (iris colour is a shader parameter)

Masks are painted per texel from baked object-space positions of the *neutral* head, so they
follow the lids, lips and nose through every face shape key.
"""
import math
import os
import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree

ROOT = r"E:\Unity\Projects\GameArtGeneration\Humans"
TEX_DIR = os.path.join(ROOT, "export", "Textures")
SHADE_MAX = 1.25
SIZE = 1024


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(d2, r):
    return np.exp(-d2 / (2 * r * r))


# ------------------------------------------------------------------ per-vertex data

def mesh_arrays(me):
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    no = np.empty(n * 3)
    me.vertex_normals.foreach_get('vector', no)
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get('vertices', e)
    return co.reshape(-1, 3), no.reshape(-1, 3), e.reshape(-1, 2)


def smooth_vals(vals, e, n, it=2, f=0.5):
    deg = np.maximum(np.bincount(e.ravel(), minlength=n), 1).astype(float)
    for _ in range(it):
        acc = np.zeros_like(vals)
        np.add.at(acc, e[:, 0], vals[e[:, 1]])
        np.add.at(acc, e[:, 1], vals[e[:, 0]])
        vals = (1 - f) * vals + f * acc / deg
    return vals


def ray_ao(ob, co, no, rays=24, dist=0.05):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    rng = np.random.default_rng(7)
    u1, u2 = rng.random(rays), rng.random(rays)
    r, phi = np.sqrt(u1), 2 * math.pi * u2
    H = np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - u1)], 1)
    ao = np.empty(len(co))
    for i in range(len(co)):
        n = Vector(no[i])
        t = n.orthogonal().normalized()
        b = n.cross(t)
        o = Vector(co[i]) + n * 0.0004
        hit = 0
        for h in H:
            if bvh.ray_cast(o, t * h[0] + b * h[1] + n * h[2], dist)[0] is not None:
                hit += 1
        ao[i] = 1.0 - hit / rays
    return ao


def curvature(co, no, e):
    n = len(co)
    d = co[e[:, 1]] - co[e[:, 0]]
    l2 = np.maximum((d * d).sum(1), 1e-12)
    acc = np.zeros(n)
    np.add.at(acc, e[:, 0], (no[e[:, 0]] * d).sum(1) / l2)
    np.add.at(acc, e[:, 1], (no[e[:, 1]] * -d).sum(1) / l2)
    deg = np.maximum(np.bincount(e.ravel(), minlength=n), 1)
    return acc / deg          # > 0 concave, < 0 convex


def group_weights(ob, name):
    n = len(ob.data.vertices)
    w = np.zeros(n)
    vg = ob.vertex_groups.get(name)
    if vg is None:
        return w
    gi = vg.index
    for v in ob.data.vertices:
        for g in v.groups:
            if g.group == gi:
                w[v.index] = g.weight
    return w


def set_materials(ob, mats):
    """Replace material slots in place. (materials.clear() would reset every face to slot 0.)"""
    me = ob.data
    for i, m in enumerate(mats):
        if i < len(me.materials):
            me.materials[i] = m
        else:
            me.materials.append(m)


def write_attr(me, name, rgb):
    if name in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[name])
    att = me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    rgba = np.hstack([rgb, np.ones((len(rgb), 1))]).astype(np.float32).ravel()
    att.data.foreach_set('color', rgba)


# ------------------------------------------------------------------ bakes into UV space

def _bake_material(kind, image, attr=None):
    """Emission material writing object position (+1), normal (*0.5+0.5) or a colour attribute."""
    name = f"_HUM_Bake_{kind}"
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    if kind == "pos":
        tc = nt.nodes.new('ShaderNodeTexCoord')
        add = nt.nodes.new('ShaderNodeVectorMath'); add.operation = 'ADD'
        add.inputs[1].default_value = (1, 1, 1)
        nt.links.new(tc.outputs['Object'], add.inputs[0])
        nt.links.new(add.outputs['Vector'], em.inputs['Color'])
    elif kind == "nrm":
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        mul = nt.nodes.new('ShaderNodeVectorMath'); mul.operation = 'MULTIPLY_ADD'
        mul.inputs[1].default_value = (0.5, 0.5, 0.5)
        mul.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(geo.outputs['Normal'], mul.inputs[0])
        nt.links.new(mul.outputs['Vector'], em.inputs['Color'])
    else:
        att = nt.nodes.new('ShaderNodeVertexColor')
        att.layer_name = attr
        nt.links.new(att.outputs['Color'], em.inputs['Color'])
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    nt.nodes.active = tex
    return m


def _dummy_material():
    m = bpy.data.materials.get("_HUM_Bake_Skip") or bpy.data.materials.new("_HUM_Bake_Skip")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    nt.nodes.new('ShaderNodeOutputMaterial')
    img = bpy.data.images.get("_HUM_Skip") or bpy.data.images.new("_HUM_Skip", 16, 16)
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.nodes.active = tex
    return m


def bake_map(ob, kind, size=SIZE, attr=None):
    """Bake one map of the head faces (material 0) into a float array (H, W, 3) + coverage."""
    img_name = f"_HUM_{kind}_{attr or ''}"
    img = bpy.data.images.get(img_name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(img_name, size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    old = list(ob.data.materials)
    set_materials(ob, [_bake_material(kind, img, attr), _dummy_material()])
    scn = bpy.context.window_manager.windows[0].scene
    prev = scn.render.engine
    scn.render.engine = 'CYCLES'
    scn.cycles.samples = 1
    scn.cycles.device = 'CPU'
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    img.pixels.foreach_set(np.zeros(size * size * 4, np.float32))
    bpy.ops.object.bake(type='EMIT', margin=0, use_clear=False)
    scn.render.engine = prev
    set_materials(ob, old)
    buf = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(size, size, 4)
    bpy.data.images.remove(img)
    rgb = buf[..., :3].astype(np.float64)
    valid = buf[..., 3] > 0.5
    if kind == "pos":
        valid &= rgb.sum(-1) > 0.5
        rgb = rgb - 1.0
    elif kind == "nrm":
        rgb = rgb * 2 - 1
    return rgb, valid


# ------------------------------------------------------------------ landmarks

class Face:
    """Landmarks of the neutral head (object space, metres)."""

    def __init__(self, ob):
        me = ob.data
        nh, ne = ob["n_head_verts"], ob["n_eye_verts"]
        co, _, _ = mesh_arrays(me)
        H = co[:nh]
        self.eye = {}
        for k, side in enumerate("lr"):
            E = co[nh + k * ne: nh + (k + 1) * ne]
            c = E.mean(0)
            self.eye[side] = (c, float(np.linalg.norm(E - c, axis=1).mean()), E[0] - c)
        lips = group_weights(ob, "lips")[:nh] > 0.5
        L = H[lips]
        self.mouth = L.mean(0)
        self.mouth_w = float(L[:, 0].max() - L[:, 0].min())
        mid = H[np.abs(H[:, 0]) < 0.002]
        band = mid[(mid[:, 2] > self.mouth[2] + 0.01) & (mid[:, 2] < self.eye['l'][0][2])]
        self.nose_tip = band[np.argmin(band[:, 1])]
        chin = mid[(mid[:, 2] < self.mouth[2] - 0.02) & (mid[:, 2] > self.mouth[2] - 0.07)]
        self.chin = chin[np.argmin(chin[:, 1])]            # most forward point below the lips
        self.top = H[np.argmax(H[:, 2])]
        self.ear_y = float(H[group_weights(ob, "ears")[:nh] > 0.5][:, 1].mean())


# ------------------------------------------------------------------ masks

def _noise3(P, scale, seed=0, valid=None):
    out = np.zeros(P.shape[:2])
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    idx = np.argwhere(valid) if valid is not None else np.argwhere(np.ones(P.shape[:2], bool))
    vals = [noise.noise(Vector(P[i, j]) * scale + off) for i, j in idx]
    out[idx[:, 0], idx[:, 1]] = vals
    return out


def paint_masks(ob, size=SIZE):
    """Compute MaskA and MaskB (H, W, 4 each, 0..1) for the head object in its neutral shape."""
    me = ob.data
    nh = ob["n_head_verts"]
    F = Face(ob)
    # per-vertex data -> attributes -> UV space
    co, no, e = mesh_arrays(me)
    ao = smooth_vals(ray_ao(ob, co, no), e, len(co), it=2)
    cav = smooth_vals(curvature(co, no, e), e, len(co), it=3)
    lips = smooth_vals(group_weights(ob, "lips"), e, len(co), it=1)
    scalp = smooth_vals(group_weights(ob, "scalp"), e, len(co), it=4)
    ears = smooth_vals(group_weights(ob, "ears"), e, len(co), it=3)
    write_attr(me, "_hum_a", np.stack([ao, np.clip(cav / 400.0 + 0.5, 0, 1), lips], 1))
    write_attr(me, "_hum_b", np.stack([scalp, ears, np.zeros(len(co))], 1))
    P, valid = bake_map(ob, "pos", size)
    N, _ = bake_map(ob, "nrm", size)
    A, _ = bake_map(ob, "attr", size, "_hum_a")
    B, _ = bake_map(ob, "attr", size, "_hum_b")
    AO, CAV, LIPS = A[..., 0], (A[..., 1] - 0.5) * 400.0, A[..., 2]
    SCALP, EARS = B[..., 0], B[..., 1]
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ax = np.abs(x)
    side = np.where(x >= 0, 'l', 'r')

    def per_eye(fn):
        out = np.zeros(x.shape)
        for s in "lr":
            c, r, f = F.eye[s]
            m = (x >= 0) if s == 'l' else (x < 0)
            out = np.where(m, fn(c, r), out)
        return out

    # --- blush: cheeks, nose tip, ears, a little on the chin
    def cheek(c, r):
        cc = c + np.array([np.sign(c[0]) * 0.006, -0.012, -0.030])
        return gauss(((P - cc) ** 2 * [1, 1.6, 1.3]).sum(-1), 0.017)
    blush = 0.75 * per_eye(cheek)
    blush += 0.8 * gauss(((P - F.nose_tip) ** 2).sum(-1), 0.011)
    blush += 0.6 * EARS
    blush += 0.25 * gauss(((P - F.chin) ** 2).sum(-1), 0.012)
    blush = np.clip(blush, 0, 1)

    # --- lips (group, sharpened) and the lip line
    lipm = smoothstep(0.35, 0.95, LIPS) ** 1.5

    # --- eyes: lash line on the upper lid margin, crease shadow, soft lower lid
    def lash(c, r):
        d = np.linalg.norm(P - c, axis=-1) / r
        front = smoothstep(-0.2, -0.55, (y - c[1]) / r)
        up = smoothstep(-0.25, 0.15, (z - c[2]) / r)
        outer = 1 + 0.6 * smoothstep(0.0, 0.8, (np.abs(x) - abs(c[0])) / r)
        return smoothstep(1.28, 1.05, d) * front * up * np.clip(outer, 0, 1.4)

    def crease(c, r):
        d = np.linalg.norm((P - c) * [1, 1, 1.25], axis=-1) / r
        front = smoothstep(-0.1, -0.5, (y - c[1]) / r)
        up = smoothstep(0.2, 0.6, (z - c[2]) / r)
        return gauss((d - 1.42) ** 2, 0.07) * front * up

    def lower(c, r):
        d = np.linalg.norm(P - c, axis=-1) / r
        down = smoothstep(0.0, -0.5, (z - c[2]) / r)
        front = smoothstep(-0.2, -0.55, (y - c[1]) / r)
        return smoothstep(1.35, 1.1, d) * down * front

    lashm = np.clip(per_eye(lash), 0, 1)
    crem = per_eye(crease)
    lowm = per_eye(lower)
    darkA = np.clip(lashm * 0.95 + crem * 0.22 + lowm * 0.08, 0, 1)

    # --- brows (painted arc over each eye)
    def brow(c, r):
        cx = abs(c[0])
        inner, outer = cx - 0.85 * r, cx + 1.45 * r
        t = (np.abs(x) - inner) / (outer - inner)                  # 0 inner end .. 1 outer end
        arch = np.sin(np.clip(t, 0, 1) ** 0.8 * np.pi)              # peak ~2/3 outward
        zc = c[2] + r * (1.12 + 0.22 * arch - 0.10 * t)
        thick = r * (0.20 - 0.09 * np.clip(t, 0, 1))
        front = smoothstep(-0.1, -0.5, (y - c[1]) / r)
        along = smoothstep(-0.06, 0.06, t) * smoothstep(1.05, 0.9, t)
        return gauss((z - zc) ** 2, thick) * front * along
    browm = np.clip(per_eye(brow) * 1.1, 0, 1)

    # --- shading: AO, cavities, painted top light, jaw underside
    light = 0.92 + 0.12 * N[..., 2]
    aot = 0.55 + 0.45 * np.clip(AO, 0, 1)
    c = np.clip(CAV / 60.0, -1, 1)
    shade = light * aot * (1 - 0.30 * np.clip(c, 0, 1)) * (1 + 0.06 * np.clip(-c, 0, 1))
    under = smoothstep(-0.1, -0.7, N[..., 2]) * smoothstep(F.mouth[2] - 0.02, F.mouth[2] - 0.07, z)
    shade *= 1 - 0.18 * under
    shade = np.clip(shade / SHADE_MAX, 0, 1)

    # --- stubble / beard shadow: jaw, chin, upper lip, cheeks below the cheekbone, neck front
    cheek_line = F.eye['l'][0][2] - 0.035 - 0.25 * (ax - 0.03)
    jaw = smoothstep(cheek_line + 0.004, cheek_line - 0.012, z) * smoothstep(F.ear_y - 0.005, F.ear_y - 0.025, y)
    # stop just under the jawline (no "neckbeard"): a little below the chin, and not back down the throat
    neck_cut = smoothstep(F.chin[2] - 0.032, F.chin[2] - 0.018, z) \
        + smoothstep(F.chin[1] + 0.035, F.chin[1] + 0.015, y) * smoothstep(F.chin[2] - 0.04, F.chin[2] - 0.025, z)
    neck_cut = np.clip(neck_cut, 0, 1)
    upper_lip = gauss(((P - (F.mouth + [0, -0.004, 0.013])) ** 2 * [0.35, 1, 3.0]).sum(-1), 0.008)
    stub = np.clip(jaw * neck_cut + upper_lip, 0, 1) * (1 - lipm)
    stub *= 1 - 0.8 * gauss(((P - F.nose_tip) ** 2).sum(-1), 0.01)

    # --- age lines (stylised strokes)
    fh_z0 = F.eye['l'][0][2] + 0.035
    fore = (0.5 + 0.5 * np.cos((z - fh_z0) / 0.0085 * 2 * np.pi)) ** 6 \
        * smoothstep(fh_z0 - 0.004, fh_z0 + 0.004, z) * smoothstep(fh_z0 + 0.04, fh_z0 + 0.025, z) \
        * smoothstep(0.055, 0.03, ax) * smoothstep(-0.1, -0.6, N[..., 1])

    def crow(c, r):
        o = c + np.array([np.sign(c[0]) * r * 1.35, 0.004, -0.001])
        d = P - o
        ang = np.arctan2(d[..., 2], np.abs(d[..., 0]))
        dist = np.linalg.norm(d, axis=-1)
        rays = (0.5 + 0.5 * np.cos(ang * 9)) ** 8
        return rays * smoothstep(0.003, 0.007, dist) * smoothstep(0.02, 0.012, dist) * (np.abs(x) > abs(c[0]))
    crows = per_eye(crow)

    def naso(c, r):
        # line from beside the nose wing to beside the mouth corner
        a = np.array([np.sign(c[0]) * 0.017, F.nose_tip[1] + 0.022, F.nose_tip[2] - 0.004])
        b = np.array([np.sign(c[0]) * (F.mouth_w / 2 + 0.008), F.mouth[1] + 0.008, F.mouth[2] - 0.012])
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)
        return gauss(d * d, 0.0022) * smoothstep(0.0, 0.15, t) * smoothstep(1.0, 0.8, t)
    nasom = per_eye(naso)
    under_eye = per_eye(lambda c, r: gauss(((np.linalg.norm(P - c, axis=-1) / r - 1.45) ** 2), 0.12)
                        * smoothstep(-0.2, -0.6, (z - c[2]) / r) * smoothstep(-0.2, -0.6, (y - c[1]) / r))
    age = np.clip(0.8 * fore + 0.7 * crows + 0.8 * nasom + 0.4 * under_eye, 0, 1)

    # --- freckles: sparse spots over nose and cheeks
    zone = np.clip(per_eye(cheek) * 1.5 + gauss(((P - F.nose_tip - [0, 0.01, 0.012]) ** 2).sum(-1), 0.016), 0, 1)
    spots = _noise3(P, 900.0, 3, valid & (zone > 0.05))
    frk = smoothstep(0.35, 0.55, spots) * zone

    # --- scalp hair shadow (for shaved heads / under hair)
    scalpm = smoothstep(0.2, 0.8, SCALP)

    A_ = np.stack([blush, lipm, shade, darkA], -1)
    B_ = np.stack([stub, age, frk, browm], -1)
    for M in (A_, B_):
        M[~valid] = 0
    return A_, B_, valid, scalpm


# ------------------------------------------------------------------ images

def dilate(M, valid, px=8):
    """Grow island colours into the gutter so mips and bilinear taps don't pick up black."""
    M = M.copy()
    v = valid.copy()
    for _ in range(px):
        acc = np.zeros_like(M)
        cnt = np.zeros(v.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sv = np.roll(v, (dy, dx), (0, 1))
            acc += np.roll(M, (dy, dx), (0, 1)) * sv[..., None]
            cnt += sv
        grow = (~v) & (cnt > 0)
        M[grow] = acc[grow] / cnt[grow][:, None]
        v |= grow
    return M


def save_image(name, M, path=None, colorspace='Non-Color'):
    h, w = M.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=True)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.clip(M, 0, 1).astype(np.float32).ravel())
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def bake_head_masks(ob, size=SIZE):
    A, B, valid, scalp = paint_masks(ob, size)
    A = dilate(A, valid)
    B = dilate(B, valid)
    ia = save_image("T_Head_MaskA", A, os.path.join(TEX_DIR, "T_Head_MaskA.png"))
    ib = save_image("T_Head_MaskB", B, os.path.join(TEX_DIR, "T_Head_MaskB.png"))
    return ia, ib


def eye_mask(size=256):
    """Front-projected eyeball: R iris coverage, G pupil, B iris darkening (limbal ring + fibres),
    A sclera brightness (darker toward the back)."""
    u = (np.arange(size) + 0.5) / size
    U, V = np.meshgrid(u, u)
    r = np.hypot(U - 0.5, V - 0.5) * 2          # 0 front pole .. 1 equator (in projected x/z)
    iris = smoothstep(0.645, 0.61, r)
    pupil = smoothstep(0.265, 0.235, r)
    limbal = smoothstep(0.50, 0.63, r)
    ang = np.arctan2(V - 0.5, U - 0.5)
    fib = (0.5 + 0.5 * np.cos(ang * 37 + 3 * np.sin(ang * 5))) ** 2 * smoothstep(0.26, 0.45, r)
    collar = gauss((r - 0.33) ** 2, 0.03)       # a lighter ring around the pupil
    dark = np.clip(0.75 * limbal + 0.3 * fib - 0.35 * collar, 0, 1)
    sclera = 1 - 0.35 * smoothstep(0.7, 1.0, r)
    M = np.stack([iris, pupil, dark, sclera], -1)
    return save_image("T_Eye_Mask", M, os.path.join(TEX_DIR, "T_Eye_Mask.png"))


def strand_texture(size=256, seed=4):
    """Tileable strand texture: R brightness (strands and grooves across u, slow variation along v)."""
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    U, V = np.meshgrid(u, u)
    s = np.zeros_like(U)
    for f in (6, 11, 17, 29, 43):
        s += np.sin(2 * np.pi * (U * f + rng.random() + 0.08 * np.sin(2 * np.pi * (V * 2 + rng.random())))) / f ** 0.6
    s = (s - s.min()) / (s.max() - s.min())
    along = 0.5 + 0.5 * np.sin(2 * np.pi * (V * 3 + U * 0.5))
    R = 0.62 + 0.38 * s ** 1.3 - 0.05 * along
    M = np.stack([R, R, R, np.ones_like(R)], -1)
    return save_image("T_Hair_Strands", M, os.path.join(TEX_DIR, "T_Hair_Strands.png"))


def cloth_textures(size=256, seed=11):
    """Tileable grey patterns: T_Cloth_Weave (plain weave + slubs), T_Cloth_Leather (grain + scuffs)."""
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    U, V = np.meshgrid(u, u)
    n = 48                                             # threads per tile
    wu = 0.5 + 0.5 * np.cos(2 * np.pi * U * n)
    wv = 0.5 + 0.5 * np.cos(2 * np.pi * V * n)
    over = (np.floor(U * n) + np.floor(V * n)) % 2
    weave = np.where(over > 0.5, wu, wv) ** 0.6
    slub = np.zeros_like(U)
    for f in (3, 5, 9):
        slub += np.sin(2 * np.pi * (V * f + rng.random()) + 0.7 * np.sin(2 * np.pi * U * 2)) / f
    W = np.clip(0.78 + 0.18 * weave + 0.06 * slub, 0, 1)
    save_image("T_Cloth_Weave", np.stack([W, W, W, np.ones_like(W)], -1), os.path.join(TEX_DIR, "T_Cloth_Weave.png"))
    g = np.zeros_like(U)
    for f in (7, 13, 23, 41):
        g += np.sin(2 * np.pi * (U * f + rng.random())) * np.sin(2 * np.pi * (V * f + rng.random())) / f ** 0.7
    g = (g - g.min()) / (g.max() - g.min())
    L = np.clip(0.72 + 0.28 * g ** 1.5, 0, 1)
    save_image("T_Cloth_Leather", np.stack([L, L, L, np.ones_like(L)], -1), os.path.join(TEX_DIR, "T_Cloth_Leather.png"))
    return bpy.data.images["T_Cloth_Weave"], bpy.data.images["T_Cloth_Leather"]


def armour_textures(size=256, seed=13):
    """T_Cloth_Quilt (padded cloth: vertical channels, stitch lines, weave) and T_Cloth_Mail (riveted rings in
    staggered rows, 24 per tile) - grey, tiling, used by the Padded and Mail armour sets."""
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    U, V = np.meshgrid(u, u)
    # quilt: 4 channels per tile across U, a stitched seam between them, a fine weave on top
    ch = (U * 4) % 1.0
    cushion = np.sin(np.pi * ch) ** 0.6
    seam = np.exp(-(np.minimum(ch, 1 - ch) / 0.035) ** 2)
    dash = ((V * 40) % 1.0) < 0.6
    n = 48
    weave = 0.5 + 0.25 * (np.cos(2 * np.pi * U * n) + np.cos(2 * np.pi * V * n))
    Q = np.clip(0.55 + 0.4 * cushion + 0.05 * weave - 0.3 * seam * dash, 0, 1)
    save_image("T_Cloth_Quilt", np.stack([Q, Q, Q, np.ones_like(Q)], -1), os.path.join(TEX_DIR, "T_Cloth_Quilt.png"))
    # mail: rings on a staggered grid (odd rows shifted half a ring)
    k = 24
    best = np.full(U.shape, 9.0)
    ring = np.zeros_like(U)
    for dy in (-1, 0, 1):
        row = np.floor(V * k) + dy
        shift = 0.5 * (row % 2)
        for dx in (-1, 0, 1):
            cx = (np.floor(U * k - shift) + dx + 0.5 + shift) / k
            cy = (row + 0.5) / k
            d = np.hypot((U - cx) * k, (V - cy) * k * 1.15)
            r = np.exp(-((d - 0.42) / 0.11) ** 2)
            ring = np.maximum(ring, r * (0.75 + 0.25 * (dy >= 0)))
    M = np.clip(0.2 + 0.8 * ring + 0.04 * rng.standard_normal(U.shape), 0, 1)
    save_image("T_Cloth_Mail", np.stack([M, M, M, np.ones_like(M)], -1), os.path.join(TEX_DIR, "T_Cloth_Mail.png"))
    return bpy.data.images["T_Cloth_Quilt"], bpy.data.images["T_Cloth_Mail"]


def plate_texture(size=256, seed=17):
    """T_Plate_Steel: hammered, brushed steel (grey, tiling; the plate shader projects it in 3D from the rest
    position): soft dents from the planishing hammer, faint brushing streaks, a little mottling."""
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    U, V = np.meshgrid(u, u)
    dent = np.zeros_like(U)
    for _ in range(90):                                    # hammer marks, wrapped so the tile repeats
        cx, cy, r = rng.random(), rng.random(), 0.03 + 0.05 * rng.random()
        dx = (U - cx + 0.5) % 1.0 - 0.5
        dy = (V - cy + 0.5) % 1.0 - 0.5
        d2 = (dx * dx + dy * dy) / (r * r)
        dent += (0.5 + 0.5 * rng.random()) * np.exp(-d2) * (1 - 0.6 * np.exp(-d2 * 4))
    dent /= dent.max()
    streak = np.zeros(size)
    for k in range(1, 40):                                 # brushing along U
        streak += rng.standard_normal() * np.cos(2 * np.pi * k * u + rng.random() * 6.3) / k ** 0.8
    streak = (streak - streak.min()) / (np.ptp(streak) + 1e-9)
    mott = np.zeros_like(U)
    for k in (2, 3, 5):
        mott += np.cos(2 * np.pi * (k * U + rng.random())) * np.cos(2 * np.pi * (k * V + rng.random())) / k
    M = np.clip(0.86 + 0.07 * dent + 0.05 * (streak[None, :] - 0.5) + 0.04 * mott, 0, 1)
    save_image("T_Plate_Steel", np.stack([M, M, M, np.ones_like(M)], -1), os.path.join(TEX_DIR, "T_Plate_Steel.png"))
    return bpy.data.images["T_Plate_Steel"]

