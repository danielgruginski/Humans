"""Blender preview of the human skin/eye shaders. Same maths as the Unity shader (see README):
per-character colours are object custom properties read through Attribute(OBJECT) nodes.

Skin (linear colours, masks from hum_paint):
    c = tone
    c = lerp(c, c * BLUSH_TINT, A.r * blush)
    c = lerp(c, c * FRECKLE_TINT, B.b * freckles)
    c = lerp(c, lerp(c, hair, 0.6) * 0.75, B.r * stubble)
    c = lerp(c, lip, A.g * 0.8)
    c = c * (1 - B.g * age * 0.25)
    c = lerp(c, hair * 0.8, B.a * brows)
    c = lerp(c, lash, A.a)
    c = c * A.b * SHADE_MAX
    then hair edges (MaskC):
    c = lerp(c, lerp(c, hair * 0.9, 0.75), C.r * scalp)        # hairline fades into the skin
    c = lerp(c, lerp(c, hair * 0.8, 0.5), C.g * beard_shadow)  # skin under a beard
"""
import bpy

import hum_paint

BLUSH_TINT = (1.0, 0.55, 0.50, 1)
FRECKLE_TINT = (0.70, 0.48, 0.36, 1)

# object property -> default (linear RGB or scalar)
SKIN_PROPS = {
    "hum_tone": (0.62, 0.40, 0.30), "hum_lip": (0.45, 0.16, 0.14), "hum_hair": (0.08, 0.05, 0.03),
    "hum_lash": (0.03, 0.02, 0.015), "hum_blush": 0.6, "hum_freckles": 0.0, "hum_stubble": 0.0,
    "hum_age": 0.0, "hum_brows": 0.8, "hum_scalp": 0.0, "hum_beard_shadow": 0.0,
}
EYE_PROPS = {"hum_iris": (0.10, 0.22, 0.40)}


LIP_FROM_TONE = (0.82, 0.56, 0.54)


def set_props(ob, **kw):
    for k, v in {**SKIN_PROPS, **EYE_PROPS}.items():
        if k not in ob.keys():
            ob[k] = v
    for k, v in kw.items():
        ob["hum_" + k] = v
    if "lip" not in kw:                         # lips follow the skin tone unless given
        ob["hum_lip"] = tuple(a * b for a, b in zip(ob["hum_tone"], LIP_FROM_TONE))
    # scalars packed into vectors: EEVEE misreads object attributes when a material uses too many
    ob["hum_amt1"] = (float(ob["hum_blush"]), float(ob["hum_freckles"]), float(ob["hum_stubble"]))
    ob["hum_amt2"] = (float(ob["hum_age"]), float(ob["hum_brows"]), float(ob["hum_scalp"]))
    ob["hum_amt3"] = (float(ob["hum_beard_shadow"]), 0.0, 0.0)


class _NT:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def node(self, kind, **inputs):
        n = self.nt.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 180
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def attr(self, name, vector=True):
        n = self.node('ShaderNodeAttribute')
        n.attribute_type = 'OBJECT'
        n.attribute_name = name
        return n.outputs['Color' if vector else 'Fac']

    def split(self, vec):
        n = self.node('ShaderNodeSeparateXYZ')
        self.link(vec, n.inputs[0])
        return n.outputs['X'], n.outputs['Y'], n.outputs['Z']

    def mix(self, a, b, fac, blend='MIX'):
        n = self.node('ShaderNodeMix')
        n.data_type = 'RGBA'
        n.blend_type = blend
        n.clamp_result = False
        for sock, v in ((n.inputs['A'], a), (n.inputs['B'], b), (n.inputs['Factor'], fac)):
            if isinstance(v, (tuple, list, float, int)):
                sock.default_value = v
            else:
                self.link(v, sock)
        return n.outputs['Result']

    def mul(self, a, b):
        return self.mix(a, b, 1.0, 'MULTIPLY')

    def math(self, op, a, b):
        n = self.node('ShaderNodeMath')
        n.operation = op
        for sock, v in ((n.inputs[0], a), (n.inputs[1], b)):
            if isinstance(v, (float, int)):
                sock.default_value = v
            else:
                self.link(v, sock)
        return n.outputs[0]

    def tex(self, image):
        n = self.node('ShaderNodeTexImage')
        n.image = image
        n.interpolation = 'Linear'
        sep = self.node('ShaderNodeSeparateColor')
        self.link(n.outputs['Color'], sep.inputs[0])
        return sep.outputs, n.outputs['Alpha']


def _rot(T, c, rot_tex):
    """The undead's rot (hum_undead): blotches, hollows and two wound sets from the rot mask, scaled by the
    object's hum_rot = (rot, wounds A, wounds B); nothing while rot is 0 (the living)."""
    import hum_undead
    if rot_tex is None:
        return c
    (rr, rg, rb), ra = T.tex(rot_tex)
    rot, wa, wb = T.split(T.attr("hum_rot"))
    c = T.mix(c, T.mul(c, hum_undead.ROT_TINT + (1,)), T.math('MULTIPLY', rr, rot))
    c = T.mix(c, (0, 0, 0, 1), T.math('MULTIPLY', T.math('MULTIPLY', ra, rot), hum_undead.HOLLOW))
    w = T.math('MAXIMUM', T.math('MULTIPLY', rg, wa), T.math('MULTIPLY', rb, wb))
    w = T.math('MULTIPLY', w, T.math('GREATER_THAN', rot, 0.0))

    def ss(a, b, v):
        n = T.node('ShaderNodeMapRange'); n.interpolation_type = 'SMOOTHSTEP'
        n.inputs['From Min'].default_value, n.inputs['From Max'].default_value = a, b
        T.link(v, n.inputs['Value'])
        return n.outputs['Result']
    c = T.mix(c, hum_undead.WOUND_RIM + (1,), ss(0.12, 0.45, w))
    c = T.mix(c, hum_undead.WOUND_CORE + (1,), ss(0.5, 0.85, w))
    return c


def skin_material(mask_a, mask_b, mask_c=None, name="M_HumanSkin", rot=None):
    rot = rot or bpy.data.images.get("T_Head_Rot")
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    (ar, ag, ab), aa = T.tex(mask_a)
    (br, bg, bb), ba = T.tex(mask_b)
    tone, lip, hair, lash = (T.attr(k) for k in ("hum_tone", "hum_lip", "hum_hair", "hum_lash"))
    blush, frk, stub = T.split(T.attr("hum_amt1"))
    age, brows, scalp = T.split(T.attr("hum_amt2"))
    bsh, _, _ = T.split(T.attr("hum_amt3"))
    c = tone
    c = T.mix(c, T.mul(c, BLUSH_TINT), T.math('MULTIPLY', ar, blush))
    c = T.mix(c, T.mul(c, FRECKLE_TINT), T.math('MULTIPLY', bb, frk))
    stub_col = T.mul(T.mix(c, hair, 0.6), (0.75, 0.75, 0.75, 1))
    c = T.mix(c, stub_col, T.math('MULTIPLY', br, stub))
    c = T.mix(c, lip, T.math('MULTIPLY', ag, 0.8))
    agef = T.math('SUBTRACT', 1.0, T.math('MULTIPLY', T.math('MULTIPLY', bg, age), 0.25))
    c = T.mix(c, (0, 0, 0, 1), T.math('SUBTRACT', 1.0, agef))
    c = T.mix(c, T.mul(hair, (0.8, 0.8, 0.8, 1)), T.math('MULTIPLY', ba, brows))
    c = T.mix(c, lash, aa)
    c = _rot(T, c, rot)
    shade = T.math('MULTIPLY', ab, hum_paint.SHADE_MAX)
    c = T.mix(c, (0, 0, 0, 1), T.math('SUBTRACT', 1.0, shade))
    if mask_c is not None:
        (cr, cg, _cb), _ca = T.tex(mask_c)
        c = T.mix(c, T.mix(c, T.mul(hair, (0.9, 0.9, 0.9, 1)), 0.75), T.math('MULTIPLY', cr, scalp))
        c = T.mix(c, T.mix(c, T.mul(hair, (0.8, 0.8, 0.8, 1)), 0.5), T.math('MULTIPLY', cg, bsh))
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.55
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    T.link(c, bsdf.inputs['Base Color'])
    region_clip(T, mat, bsdf)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def eye_material(mask, name="M_HumanEye"):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    (ir, pu, dk), sc = T.tex(mask)
    iris = T.attr("hum_iris")
    c = T.mul((0.86, 0.84, 0.80, 1), T.mix((0, 0, 0, 1), (1, 1, 1, 1), sc))
    iris_c = T.mix(iris, T.mul(iris, (0.25, 0.25, 0.25, 1)), dk)
    milk = T.attr("hum_milk", False)                    # the undead's clouded eyes: pupil and iris fade out
    iris_c = T.mix(iris_c, (0.62, 0.64, 0.60, 1), T.math('MULTIPLY', milk, 0.55))
    c = T.mix(c, iris_c, ir)
    c = T.mix(c, (0.005, 0.005, 0.005, 1), T.math('MULTIPLY', pu, T.math('SUBTRACT', 1.0, T.math('MULTIPLY', milk, 0.85))))
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.12
    bsdf.inputs['Coat Weight'].default_value = 0.6
    bsdf.inputs['Coat Roughness'].default_value = 0.03
    T.link(c, bsdf.inputs['Base Color'])
    region_clip(T, mat, bsdf)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


EDGE_DARK = 0.35

HAIR_PROPS = {"hum_hair_root": (0.08, 0.05, 0.03), "hum_hair_tip": (0.08, 0.05, 0.03),
              "hum_hair_streak": (0.5, 0.1, 0.1), "hum_streaks": 0.0, "hum_ombre": 0.0}


def set_hair_props(ob, root, tip=None, streak=None, streaks=0.0, ombre=0.0):
    ob["hum_hair_root"] = tuple(root)
    ob["hum_hair_tip"] = tuple(tip if tip is not None else root)
    ob["hum_hair_streak"] = tuple(streak if streak is not None else root)
    ob["hum_streaks"] = float(streaks)
    ob["hum_ombre"] = float(ombre if tip is not None else 0.0)


def hair_material(strands, name="M_HumanHair"):
    """Hair: t = Clump.y (root->tip), id = Clump.x (per clump)
        c = lerp(root, tip, smoothstep(0.25, 1, o) * ombre)   o = CapCut.y: 0 top of the style .. 1 its lowest ends
        c = lerp(c, streak, id < streaks)
        c = c * strand.r * lerp(0.7, 1, smoothstep(0, 0.3, t))
        c = c * (1 - EDGE_DARK * HairData.r)          # vertex colour: soft lines along each clump's sides
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    uvc = T.node('ShaderNodeUVMap'); uvc.uv_map = "Clump"
    sep = T.node('ShaderNodeSeparateXYZ')
    T.link(uvc.outputs['UV'], sep.inputs[0])
    rid, t = sep.outputs['X'], sep.outputs['Y']
    uv0 = T.node('ShaderNodeUVMap'); uv0.uv_map = "UVMap"
    tex = T.node('ShaderNodeTexImage'); tex.image = strands
    T.link(uv0.outputs['UV'], tex.inputs['Vector'])
    root, tip, streak = (T.attr(k) for k in ("hum_hair_root", "hum_hair_tip", "hum_hair_streak"))
    streaks, ombre = T.attr("hum_streaks", False), T.attr("hum_ombre", False)
    mr = T.node('ShaderNodeMapRange'); mr.interpolation_type = 'SMOOTHSTEP'
    mr.inputs['From Min'].default_value = 0.25
    cuv = T.node('ShaderNodeUVMap'); cuv.uv_map = "CapCut"
    cc, olen, _ = T.split(cuv.outputs['UV'])              # x: height above a cap rim, y: ombre by real length
    T.link(olen, mr.inputs['Value'])
    c = T.mix(root, tip, T.math('MULTIPLY', mr.outputs['Result'], ombre))
    c = T.mix(c, streak, T.math('LESS_THAN', rid, streaks))
    c = T.mul(c, tex.outputs['Color'])
    vc = T.node('ShaderNodeVertexColor'); vc.layer_name = "HairData"
    sepc = T.node('ShaderNodeSeparateColor')
    T.link(vc.outputs['Color'], sepc.inputs[0])
    c = T.mix(c, (0, 0, 0, 1), T.math('MULTIPLY', sepc.outputs[0], EDGE_DARK))
    mr2 = T.node('ShaderNodeMapRange'); mr2.interpolation_type = 'SMOOTHSTEP'
    mr2.inputs['From Max'].default_value = 0.3
    mr2.inputs['To Min'].default_value = 0.7
    T.link(t, mr2.inputs['Value'])
    c = T.mix((0, 0, 0, 1), c, mr2.outputs['Result'])
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.55
    bsdf.inputs['Specular IOR Level'].default_value = 0.28
    T.link(c, bsdf.inputs['Base Color'])
    # under a cap: hide what's above the rim (CapCut.x > hum_capcut; hum_capcut 0 = no cap)
    cut = T.attr("hum_capcut", False)
    hidden = T.math('MULTIPLY', T.math('GREATER_THAN', cut, 0.0), T.math('GREATER_THAN', cc, cut))
    # under the cloak's hood: HoodCut.x > 0 hidden while hum_hoodcut is 1
    huv = T.node('ShaderNodeUVMap'); huv.uv_map = "HoodCut"
    hc, _, _ = T.split(huv.outputs['UV'])
    hood = T.math('MULTIPLY', T.attr("hum_hoodcut", False), T.math('GREATER_THAN', hc, 0.0))
    hidden = T.math('MAXIMUM', hidden, hood)
    T.link(T.math('SUBTRACT', 1.0, hidden), bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def set_body_props(ob, tone, blush=0.5, freckles=0.0, cloth=(0.55, 0.47, 0.38), top=0.0, hide=0):
    ob["hum_hide"] = float(hide)
    ob["hum_tone"] = tuple(tone)
    ob["hum_cloth"] = tuple(cloth)
    ob["hum_bamt"] = (float(blush), float(freckles), float(top))


def region_clip(T, mat, bsdf, keep=None):
    """Hide the regions an outer layer covers: bit (Region UV id) of the object's hum_hide. keep: another 0/1
    factor on the alpha (a torn garment's holes)."""
    ruv = T.node('ShaderNodeUVMap'); ruv.uv_map = "Region"
    rid, _, _ = T.split(ruv.outputs['UV'])
    rid = T.math('ROUND', rid, 0.0)
    bit = T.math('MODULO', T.math('FLOOR', T.math('DIVIDE', T.attr("hum_hide", False), T.math('POWER', 2.0, rid)), 0.0), 2.0)
    a = T.math('SUBTRACT', 1.0, bit)
    if keep is not None:
        a = T.math('MULTIPLY', a, keep)
    T.link(a, bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'


TATTER_TILE = 0.6          # m: the tatter texture's repeat over the garment's rest position (triplanar)
TATTER_HOLES = 0.17        # hole area at tatter 1 (the hems tear more)
TATTER_FRAY = 0.22         # ragged edges: the fine fray noise added to the hole field
TATTER_HEM = 0.6           # hems tear first (ClothData.g)
TATTER_RIM = 0.035         # the frayed, darker cloth round a hole (in hole-field units)
TATTER_RAG_TILE = 5.0      # rags (ClothData.a = 1 - rag, hum_rags): the field's tile this much larger at rag 1 (fewer,
                           # bigger rips than the undead's speckles)


def _tatter(T, c, hem, rag=None):
    """Torn, dirty clothes (the undead; hum_undead.tatter_texture): hum_tat = (tatter, cut, 0). Holes where the
    equalised hole field is under tatter * TATTER_HOLES (hems tear first); cut 1 cuts them out (a skeleton's rags:
    the bones show), cut 0 paints the skin under them (hum_skin, a zombie). Rags (rag: a socket, 1 - ClothData.a)
    tear at least that much on anyone, over a coarser field. Returns (colour, keep factor) or (colour, None)
    without the texture."""
    tex = bpy.data.images.get("T_Cloth_Tatter")
    if tex is None:
        return c, None
    rxy = T.node('ShaderNodeUVMap'); rxy.uv_map = "RestXY"
    rz = T.node('ShaderNodeUVMap'); rz.uv_map = "RestZ"
    x, y, _ = T.split(rxy.outputs['UV'])
    z, _, _ = T.split(rz.outputs['UV'])
    comb = T.node('ShaderNodeCombineXYZ')
    T.link(x, comb.inputs[0]); T.link(y, comb.inputs[1]); T.link(z, comb.inputs[2])
    sc = T.node('ShaderNodeVectorMath'); sc.operation = 'SCALE'
    T.link(comb.outputs[0], sc.inputs[0])
    if rag is None:
        sc.inputs['Scale'].default_value = 1.0 / TATTER_TILE
    else:                                                                  # rags: a coarser field
        T.link(T.math('DIVIDE', 1.0, T.math('MULTIPLY', TATTER_TILE, T.math('ADD', 1.0, T.math('MULTIPLY', rag, TATTER_RAG_TILE)))),
               sc.inputs['Scale'])
    n = T.node('ShaderNodeTexImage'); n.image = tex; n.projection = 'BOX'; n.projection_blend = 0.3
    T.link(sc.outputs[0], n.inputs['Vector'])
    sep = T.node('ShaderNodeSeparateColor')
    T.link(n.outputs['Color'], sep.inputs[0])
    hole_f, dirt, fray = sep.outputs
    tat, cut, _ = T.split(T.attr("hum_tat"))
    if rag is not None:                                                    # rags tear on the living too
        tat = T.math('MAXIMUM', tat, rag)
    on = T.math('GREATER_THAN', tat, 0.0)

    def ss(a, b, v):
        m = T.node('ShaderNodeMapRange'); m.interpolation_type = 'SMOOTHSTEP'
        m.inputs['From Min'].default_value, m.inputs['From Max'].default_value = a, b
        T.link(v, m.inputs['Value'])
        return m.outputs['Result']
    h = T.math('ADD', hole_f, T.math('MULTIPLY', T.math('SUBTRACT', fray, 0.5), TATTER_FRAY))
    h = T.math('SUBTRACT', h, T.math('MULTIPLY', T.math('MULTIPLY', hem, TATTER_HEM), tat))
    thr = T.math('MULTIPLY', T.math('MULTIPLY', tat, TATTER_HOLES), T.math('ADD', 1.0, cut))   # rags on bones: twice
    d = T.math('SUBTRACT', thr, h)                                        # > 0 inside a hole
    hole = T.math('MULTIPLY', T.math('GREATER_THAN', d, 0.0), on)
    rim = T.math('MULTIPLY', T.math('MULTIPLY', T.math('GREATER_THAN', d, -TATTER_RIM), T.math('SUBTRACT', 1.0, hole)), on)
    c = T.mix(c, T.mul(c, (0.5, 0.45, 0.36, 1)), T.math('MULTIPLY', ss(0.3, 0.9, dirt), T.math('MULTIPLY', tat, 0.9)))
    c = T.mix(c, (0, 0, 0, 1), T.math('MULTIPLY', rim, 0.55))
    inner = T.mix((0.2, 0.2, 0.2, 1), (0.6, 0.6, 0.6, 1), ss(0.0, 0.1, d))   # shadowed under the cloth's edge
    skin = T.mul(T.attr("hum_skin"), inner)
    c = T.mix(c, skin, T.math('MULTIPLY', hole, T.math('SUBTRACT', 1.0, cut)))
    keep = T.math('SUBTRACT', 1.0, T.math('MULTIPLY', hole, cut))
    return c, keep


def body_material(mask_a, mask_b, name="M_HumanBody", rot=None):
    """Body skin + painted underclothes (same maths as Unity's Humans/Body):
        c = tone
        c = lerp(c, c * BLUSH_TINT, A.r * blush)
        c = lerp(c, c * FRECKLE_TINT, B.r * freckles)
        (rot: _rot)
        c = lerp(c, cloth, saturate(A.g + A.a * top))
        c = c * A.b * SHADE_MAX
    """
    rot = rot or bpy.data.images.get("T_Body_Rot")
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    (ar, ag, ab), aa = T.tex(mask_a)
    (br, _bg, _bb), _ba = T.tex(mask_b)
    tone, cloth = T.attr("hum_tone"), T.attr("hum_cloth")
    blush, frk, top = T.split(T.attr("hum_bamt"))
    c = tone
    c = T.mix(c, T.mul(c, BLUSH_TINT), T.math('MULTIPLY', ar, blush))
    c = T.mix(c, T.mul(c, FRECKLE_TINT), T.math('MULTIPLY', br, frk))
    c = _rot(T, c, rot)
    cm = T.math('MINIMUM', T.math('ADD', ag, T.math('MULTIPLY', aa, top)), 1.0)
    c = T.mix(c, cloth, cm)
    shade = T.math('MULTIPLY', ab, hum_paint.SHADE_MAX)
    c = T.mix(c, (0, 0, 0, 1), T.math('SUBTRACT', 1.0, shade))
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.6
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    T.link(c, bsdf.inputs['Base Color'])
    region_clip(T, mat, bsdf)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


METAL = (0.42, 0.42, 0.44, 1.0)          # studs and buckles (linear)


PLATE_TRIM = (0.55, 0.36, 0.12, 1.0)      # brass (linear)
PLATE_STRAP = (0.06, 0.035, 0.02, 1.0)    # dark leather straps


def plate_material(pattern, name="M_HumanPlate"):
    """Plate armour (same maths as Unity's Humans/Plate): steel = colour * pattern * lerp(0.55, 1, AO),
    metallic, smoother and brighter where polished (ClothData.g: rolled edges, rivets); ClothData.a picks the
    material: 1 steel, 0.5 brass trim, 0 leather strap."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    uv = T.node('ShaderNodeUVMap'); uv.uv_map = "UVMap"
    tex = T.node('ShaderNodeTexImage'); tex.image = pattern
    T.link(uv.outputs['UV'], tex.inputs['Vector'])
    vc = T.node('ShaderNodeVertexColor'); vc.layer_name = "ClothData"
    ao, polish, detail = T.split(vc.outputs['Color'])
    kind = vc.outputs['Alpha']
    aof = T.math('ADD', 0.55, T.math('MULTIPLY', ao, 0.45))
    steel = T.mul(T.attr("hum_color"), tex.outputs['Color'])
    steel = T.mix(steel, (0.9, 0.9, 0.92, 1.0), T.math('MULTIPLY', polish, 0.25))
    trim = T.math('MULTIPLY', T.math('GREATER_THAN', kind, 0.25), T.math('LESS_THAN', kind, 0.75))
    leather = T.math('LESS_THAN', kind, 0.25)
    c = T.mix(steel, PLATE_TRIM, trim)
    c = T.mix(c, PLATE_STRAP, leather)
    c = T.mix((0, 0, 0, 1), c, aof)
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    T.link(c, bsdf.inputs['Base Color'])
    T.link(T.math('SUBTRACT', 1.0, leather), bsdf.inputs['Metallic'])
    rough = T.math('SUBTRACT', 0.36, T.math('MULTIPLY', polish, 0.16))
    T.link(T.math('ADD', rough, T.math('MULTIPLY', leather, 0.35)), bsdf.inputs['Roughness'])
    region_clip(T, mat, bsdf)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def cloth_material(pattern, name="M_HumanCloth", roughness=0.85):
    """Garments (same maths as Unity's Humans/Cloth):
        c = colour * pattern(uv) * lerp(0.5, 1, AO) * (1 - 0.18 * hem)     AO, hem = ClothData.r, .g
        c = lerp(c, METAL * lerp(0.5, 1, AO), ClothData.b)                     studs: iron, smoother
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    T = _NT(mat)
    uv = T.node('ShaderNodeUVMap'); uv.uv_map = "UVMap"
    tex = T.node('ShaderNodeTexImage'); tex.image = pattern
    T.link(uv.outputs['UV'], tex.inputs['Vector'])
    vc = T.node('ShaderNodeVertexColor'); vc.layer_name = "ClothData"
    ao, hem, metal = T.split(vc.outputs['Color'])
    colour = T.attr("hum_color")
    c = T.mul(colour, tex.outputs['Color'])
    aof = T.math('ADD', 0.5, T.math('MULTIPLY', ao, 0.5))
    c = T.mix((0, 0, 0, 1), c, aof)
    c = T.mix(c, (0, 0, 0, 1), T.math('MULTIPLY', hem, 0.18))
    c = T.mix(c, T.mix((0, 0, 0, 1), METAL, aof), metal)
    c, keep = _tatter(T, c, hem, rag=T.math('SUBTRACT', 1.0, vc.outputs['Alpha']))   # rags: ClothData.a = 1 - rag
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    T.link(T.math('ADD', roughness, T.math('MULTIPLY', metal, 0.4 - roughness)), bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.25
    T.link(c, bsdf.inputs['Base Color'])
    region_clip(T, mat, bsdf, keep)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat
