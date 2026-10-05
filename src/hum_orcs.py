"""Orcs: the human made orcish with what the face already has (no new body geometry). A preset over a rolled face:

- the face sliders an orc's look needs (pointed ears, heavy brow ridge, broad flat nose, wide jaw and mouth, small
  hooded eyes), each a mean and a spread rolled round it;
- green and grey-green skin, yellow / orange / red eyes, dark or grey hair, bushy brows;
- the "Tusks" beard style (hum_styles: two tusks from the corners of the lower lip, ivory);
- tall (the height slider high; the game makes them taller still with the creature's scale) and the strong or
  heavy builds (the body keys, and so the clothes and armour, are the builds' own).

The preset is exported into the config (`hum_export.export_config` -> "presets"), so Unity's HumanFaceGenerator
applies the same values (`ApplyPreset`) and the game names it per creature.

    import hum_orcs; hum_orcs.lineup(head, [1, 2, 3, 4])
"""
import os
import random
import bpy

import hum_faces, hum_scene

ORC = dict(
    name="Orc",
    # slider: (mean, spread); a woman's means are scaled by fem_scale (but the ears)
    sliders={
        "EarPointed": (1.0, 0.0), "EarSize": (0.45, 0.15), "EarOut": (0.35, 0.2), "EarLobe": (-0.4, 0.15),
        "BrowRidge": (0.85, 0.1), "BrowHeight": (-0.45, 0.15), "BrowAngle": (-0.35, 0.2),
        "EyeSize": (-0.4, 0.1), "EyeHooded": (0.45, 0.15), "EyeSpacing": (0.15, 0.1), "EyeOpen": (-0.2, 0.1),
        "NoseWidth": (0.8, 0.12), "NoseLength": (-0.4, 0.15), "NoseTipUp": (0.5, 0.2), "NoseFlare": (0.75, 0.15),
        "NoseDepth": (-0.25, 0.15), "NoseCurve": (-0.35, 0.2), "NoseHump": (-0.3, 0.2), "NoseTipWidth": (0.5, 0.15),
        "MouthWidth": (0.6, 0.12), "LipLower": (0.5, 0.15), "LipUpper": (-0.25, 0.15), "MouthCorners": (-0.4, 0.15),
        "ChinWidth": (0.65, 0.12), "ChinForward": (0.45, 0.15), "ChinHeight": (0.15, 0.15),
        "CheekBones": (0.55, 0.15), "CheekFull": (-0.2, 0.15), "FaceSquare": (0.6, 0.15), "FaceRound": (0.0, 0.0),
        "FaceOval": (0.0, 0.0), "FaceTriangle": (0.0, 0.0), "FaceInvTriangle": (0.0, 0.0), "FaceDiamond": (0.0, 0.0),
        "HeadWidth": (0.3, 0.1), "ForeheadSlope": (0.6, 0.15), "ForeheadHeight": (-0.35, 0.15),
    },
    fem_scale=0.7,
    tones=["#5f7a43", "#56703c", "#6d8148", "#4c6238", "#647357", "#71864e", "#5a6b47", "#4f5d3f"],
    irises=["#c9a227", "#b5651d", "#9a2a1a", "#d0b84a", "#8a6a1a"],
    hair_styles=["Mohawk", "Mohawk", "Crop", "Buzz", "", "Ponytail", "Long"],
    hair_colors=["black", "black", "dark_brown", "grey"],
    beard="Tusks", beard_color="#ded3b5",
    brows=["Bushy", "Bushy", "Straight"],
    height=(0.55, 1.0),
    sex_min=0.85,
    blush=(0.0, 0.12),
)


def build_tusks(head=None):
    """Beard_Tusks and its LODs (like hum_build.build_hair / hum_lod.piece_lods for this one style), bound to the
    head keys, rigid on the head bone, with the CapCut / HoodCut UVs. Returns (name, tris, keys) per object."""
    import hum_styles, hum_hair, hum_paint, hum_lod, hum_material, hum_armor
    head = head or bpy.data.objects["Head"]
    arm = bpy.data.objects["HumanRig"]
    keys = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in keys}
    for k in keys[1:]:
        k.value = 0.0
    sc = bpy.data.scenes["Faces"]
    mat = bpy.data.materials["M_HumanHair"]
    made = []
    try:
        for lod in (0, 1, 2):
            H = hum_hair.HeadFrame(head)
            ob = hum_styles.build(sc, H, "beard", "Tusks", lod=lod)
            hum_paint.set_materials(ob, [mat])
            if lod:
                hum_lod._place(sc, ob, lod)
            nk, _ = hum_hair.bind_keys(ob, head)
            hum_material.set_hair_props(ob, (0.62, 0.55, 0.40))
            for vg in list(ob.vertex_groups):              # rigid on the head, as hum_build.skin_all does beards
                ob.vertex_groups.remove(vg)
            vg = ob.vertex_groups.new(name="head")
            vg.add(list(range(len(ob.data.vertices))), 1.0, 'REPLACE')
            for m in list(ob.modifiers):
                if m.type == 'ARMATURE':
                    ob.modifiers.remove(m)
            ob.modifiers.new("Armature", 'ARMATURE').object = arm
            ob.parent = arm
            ob["rebound_v2"] = ob["rebound_v3"] = True     # the stamps the other pieces carry (passes already done)
            ob["hum_helpers"] = "ring_v2"
            ob.hide_set(True)
            ob.hide_render = True
            made.append((ob.name, hum_hair.tris(ob), nk))
        hum_armor.write_cap_coords(head, only={m[0] for m in made})
    finally:
        for k, v in saved.items():
            keys[k].value = v
    return made


def _hex_lin(h):
    return hum_faces.srgb(h)


def orc_face(seed, preset=ORC):
    """A rolled face (hum_faces.random_face) made orcish, for the Blender preview."""
    f = hum_faces.random_face(seed)
    rng = random.Random(seed * 31 + 7)
    w = f["keys"]
    masc = f["masc"]
    sexk = "Masculine" if masc else "Feminine"
    w[sexk] = max(w.get(sexk, 0.0), preset["sex_min"])
    for name, (mean, spread) in preset["sliders"].items():
        m = mean if (masc or name.startswith("Ear")) else mean * preset["fem_scale"]
        v = max(-1.0, min(1.0, rng.gauss(m, spread))) if spread else m
        w.pop(name + "_Pos", None)
        w.pop(name + "_Neg", None)
        if v > 0:
            w[name + "_Pos"] = v
        elif v < 0:
            w[name + "_Neg"] = -v
    p = f["props"]
    p["tone"] = _hex_lin(rng.choice(preset["tones"]))
    p["iris"] = _hex_lin(rng.choice(preset["irises"]))
    p["blush"] = rng.uniform(*preset["blush"])
    p["freckles"] = 0.0
    p["stubble"] = 0.0
    hair = rng.choice(preset["hair_colors"])
    root = _hex_lin(hum_faces.HAIR[hair])
    f["style"] = rng.choice(preset["hair_styles"]) or None
    f["hair_colors"] = dict(root=root)
    f["beard"] = preset["beard"]
    f["beard_colors"] = dict(root=_hex_lin(preset["beard_color"]))
    f["brow_style"] = rng.choice(preset["brows"])
    f["brow_colors"] = dict(root=tuple(c * 0.8 for c in root))
    p["hair"] = root
    p["scalp"] = 0.0 if f["style"] in (None, "Mohawk") else 1.0
    p["beard_shadow"] = 0.0
    f["height"] = rng.uniform(*preset["height"])
    return f


def export(preset=ORC):
    """The preset as the config writes it (Unity: HumanFaceConfig.Preset)."""
    return dict(name=preset["name"],
                sliders=[dict(name=k, mean=float(m), jitter=float(s)) for k, (m, s) in preset["sliders"].items()],
                femScale=preset["fem_scale"], tones=preset["tones"], irises=preset["irises"],
                hairStyles=preset["hair_styles"], hairColors=preset["hair_colors"], beard=preset["beard"],
                beardColor=preset["beard_color"], brows=preset["brows"], heightMin=preset["height"][0],
                heightMax=preset["height"][1], sexMin=preset["sex_min"], blushMin=preset["blush"][0],
                blushMax=preset["blush"][1])


PRESETS = [ORC]


def lineup(ob, seeds, views=("Front", "34"), size=420, out="orc_lineup.png"):
    sc = bpy.context.window_manager.windows[0].scene
    paths = []
    for s in seeds:
        hum_faces.apply_face(ob, orc_face(s))
        for v in views:
            paths.append(hum_scene.render(sc, bpy.data.objects["Cam_" + v],
                                          os.path.join(hum_scene.RENDERS, "_tmp", f"orc{s}_{v}.png"), size))
    return hum_scene.sheet(paths, len(views) * 4 if len(seeds) >= 4 else len(paths),
                           os.path.join(hum_scene.RENDERS, out))
