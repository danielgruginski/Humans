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


def skin_material(mask_a, mask_b, mask_c=None, name="M_HumanSkin"):
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
    c = T.mix(c, iris_c, ir)
    c = T.mix(c, (0.005, 0.005, 0.005, 1), pu)
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


def region_clip(T, mat, bsdf):
    """Hide the regions an outer layer covers: bit (Region UV id) of the object's hum_hide."""
    ruv = T.node('ShaderNodeUVMap'); ruv.uv_map = "Region"
    rid, _, _ = T.split(ruv.outputs['UV'])
    rid = T.math('ROUND', rid, 0.0)
    bit = T.math('MODULO', T.math('FLOOR', T.math('DIVIDE', T.attr("hum_hide", False), T.math('POWER', 2.0, rid)), 0.0), 2.0)
    T.link(T.math('SUBTRACT', 1.0, bit), bsdf.inputs['Alpha'])
    mat.surface_render_method = 'DITHERED'


def body_material(mask_a, mask_b, name="M_HumanBody"):
    """Body skin + painted underclothes (same maths as Unity's Humans/Body):
        c = tone
        c = lerp(c, c * BLUSH_TINT, A.r * blush)
        c = lerp(c, c * FRECKLE_TINT, B.r * freckles)
        c = lerp(c, cloth, saturate(A.g + A.a * top))
        c = c * A.b * SHADE_MAX
    """
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
    bsdf = T.node('ShaderNodeBsdfPrincipled')
    T.link(T.math('ADD', roughness, T.math('MULTIPLY', metal, 0.4 - roughness)), bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.25
    T.link(c, bsdf.inputs['Base Color'])
    region_clip(T, mat, bsdf)
    out = T.node('ShaderNodeOutputMaterial')
    T.link(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat
