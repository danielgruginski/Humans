"""Export the humans for Unity.

export/Human_Body.fbx   HumanRig (game_engine skeleton) + Body, Body_L1/L2 + Head, Head_L1/L2 (eyes on material 1),
                        skinned, with the keys as residual blend shapes
export/Human_Hair.fbx   HumanRig + every Hair_*, Beard_*, Brows_* piece and its _L1/_L2 versions (rigid on "head")
export/Human_Cloth.fbx  HumanRig + every Cloth_* garment and its _L1/_L2 versions, skinned, with the body keys
                        (ClothData colour: r = AO, g = hem; UVMap tiles the weave/leather pattern)
export/human_rig.json   rest bone heads and each key's bone deltas (Blender space), height scales
export/human_face_config.json
                        what the C# generator needs: sliders, macros, correctives, spreads/biases,
                        palettes (sRGB hex), style weights, shader constants
export/Textures/        T_Head_MaskA/B/C, T_Eye_Mask, T_Hair_Strands (written by the paint steps)

FBX axes/scale as the goblins: -Z forward, Y up, FBX_SCALE_ALL (Blender +X = Unity -X).
"""
import json
import os
import bpy

import hum_faces, hum_hair, hum_material, hum_paint, hum_styles, hum_rig, hum_cloth, hum_builds

ROOT = r"E:\Unity\Projects\GameArtGeneration\Humans"
EXPORT = os.path.join(ROOT, "export")


def _export(objs, path):
    vl = bpy.context.view_layer
    state = {o.name: (o.hide_get(), o.hide_viewport, o.hide_select) for o in objs}
    for o in objs:
        o.hide_viewport = False
        o.hide_select = False
        o.hide_set(False)
    for o in vl.objects:
        o.select_set(o in objs)
    vl.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={'MESH', 'ARMATURE'}, use_mesh_modifiers=False,
        use_armature_deform_only=True, armature_nodetype='NULL',
        apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', mesh_smooth_type='OFF',
        use_custom_props=False, add_leaf_bones=False, bake_anim=False, use_tspace=False,
        path_mode='STRIP', embed_textures=False, colors_type='LINEAR')   # HairData.r is data, not a colour
    for o in objs:
        h, hv, hs = state[o.name]
        o.hide_viewport, o.hide_select = hv, hs
        o.hide_set(h)
    return path


def cloth_family(garment):
    """Which Human_Cloth_<family>.fbx a garment ships in: one file per outfit family keeps imports quick and
    lets a project leave out what it doesn't use."""
    import hum_armor
    import hum_cloak
    import hum_plate
    if garment in hum_cloak.CLOAK:
        return "Cloak"
    if garment in hum_armor.ARMOR:
        return "Leather" if hum_armor.ARMOR[garment]["material"] == "leather" else "PaddedMail"
    if garment in hum_plate.PLATE:
        for pre, fam in (("Knight", "BlackKnight"), ("Ornate", "Ornate"), ("Gothic", "Gothic")):
            if garment.startswith(pre):
                return fam
        return "Plate"
    return "Clothes"


def export_models():
    os.makedirs(EXPORT, exist_ok=True)
    head = bpy.data.objects["Head"]
    keys = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in keys}
    for k in keys:
        k.value = 0.0
    arm = bpy.data.objects["HumanRig"]
    for pb in arm.pose.bones:                                  # rest pose, unit scale
        pb.location = (0, 0, 0)
    saved_scale = tuple(arm.scale)
    arm.scale = (1, 1, 1)
    body_parts = [o for o in (bpy.data.objects.get(n) for n in ("Body", "Body_L1", "Body_L2", "Head_L1", "Head_L2"))
                  if o is not None]
    pieces = []
    for cname in (hum_hair.HAIR_COL, "HUM_LOD1", "HUM_LOD2"):
        col = bpy.data.collections.get(cname)
        if col:
            pieces += [o for o in col.objects if not o.name.startswith(("Head", "Body", "Cloth_"))]
    pieces.sort(key=lambda o: o.name)
    cloth = sorted((o for o in bpy.data.objects if o.name.startswith("Cloth_") and o.type == 'MESH'),
                   key=lambda o: o.name)
    for o in pieces + body_parts + cloth:
        for k in (o.data.shape_keys.key_blocks if o.data.shape_keys else []):
            k.value = 0.0
    a = _export([arm, head] + body_parts, os.path.join(EXPORT, "Human_Body.fbx"))
    b = _export([arm] + pieces, os.path.join(EXPORT, "Human_Hair.fbx"))
    import hum_cloth
    fams = {}
    for o in cloth:
        fams.setdefault(cloth_family(hum_cloth.parse_cloth(o.name)[0]), []).append(o)
    for f in os.listdir(EXPORT):                               # the single file (and dropped families) go
        if f.startswith("Human_Cloth") and f.endswith(".fbx"):
            os.remove(os.path.join(EXPORT, f))
    c = [_export([arm] + objs, os.path.join(EXPORT, f"Human_Cloth_{fam}.fbx")) for fam, objs in sorted(fams.items())]
    for k in keys:
        k.value = saved[k.name]
    arm.scale = saved_scale
    old = os.path.join(EXPORT, "Human_Head.fbx")                # superseded by Human_Body.fbx
    if os.path.exists(old):
        os.remove(old)
    return a, b, c


def export_hair():
    """Only Human_Hair.fbx (every hair, beard and brow piece and their LODs), as export_models writes it: for a new
    style without re-exporting the body and the clothes."""
    head = bpy.data.objects["Head"]
    keys = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in keys}
    for k in keys:
        k.value = 0.0
    arm = bpy.data.objects["HumanRig"]
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
    saved_scale = tuple(arm.scale)
    arm.scale = (1, 1, 1)
    pieces = []
    for cname in (hum_hair.HAIR_COL, "HUM_LOD1", "HUM_LOD2"):
        col = bpy.data.collections.get(cname)
        if col:
            pieces += [o for o in col.objects if not o.name.startswith(("Head", "Body", "Cloth_"))]
    pieces.sort(key=lambda o: o.name)
    for o in pieces:
        for k in (o.data.shape_keys.key_blocks if o.data.shape_keys else []):
            k.value = 0.0
    try:
        return _export([arm] + pieces, os.path.join(EXPORT, "Human_Hair.fbx"))
    finally:
        for k in keys:
            k.value = saved[k.name]
        arm.scale = saved_scale


def export_rig():
    """Rest bone heads and per-key bone deltas (Blender armature space) for the runtime skeleton."""
    sk = hum_rig.SK
    arm = bpy.data.objects["HumanRig"]
    rest = {b.name: list(b.head_local) for b in arm.data.bones}
    deltas = []
    for key, d in hum_rig.JOINT_DELTAS.items():
        rows = [dict(bone=sk.bones[i], d=[float(x) for x in d[i]]) for i in range(len(sk.bones))
                if abs(d[i]).max() > 1e-5]
        if rows:
            deltas.append(dict(key=key, bones=rows))
    import hum_helpers
    out = dict(bones=[dict(name=b, parent=sk.rig[b].get("parent") or "", rest=rest[b]) for b in sk.bones],
               keys=deltas, heightRatios=hum_rig.HEIGHT_RATIOS, hipsBone="pelvis",
               # helper bones, driven at runtime by HumanHelperBones (hum_helpers)
               helpers=[dict(name=n, parent=h["parent"], source=h["source"], drive=h["drive"], f=h["f"],
                             fBack=h.get("f_back", h["f"]),
                             fRaised=h.get("f_raised", h["f"]), raiseFrom=h.get("raise_", (0.0, 0.0))[0],
                             raiseTo=h.get("raise_", (0.0, 0.0))[1], mate=h.get("mate", ""),
                             baseBone=h.get("base", ""), raiseOf=h.get("raise_of", ""),
                             hang=h.get("side", "") if h["drive"] == "hang" else "")
                        for n, h in hum_helpers.HELPERS.items() if h["drive"] not in ("spring", "ring")],
               # spring chains, simulated by HumanSpringChain
               springs=[dict(bones=list(hum_helpers.CAPE))],
               # the skirt ring, simulated by HumanSkirt: per column the hip link, the knee link, its tip, and
               # the left thigh's share (seated it follows the thighs)
               skirts=[dict(columns=[dict(hip=a, knee=k, hem=e,
                                          side=float(hum_helpers.ss(-0.11, 0.11, arm.data.bones[k].head_local.x)))
                                     for (a, k), e in zip(hum_helpers.SKIRT_RING, hum_helpers.SKIRT_HEM)],
                            raiseFrom=hum_helpers.RING_RAISE[0], raiseTo=hum_helpers.RING_RAISE[1])])
    path = os.path.join(EXPORT, "human_rig.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return path


def _hex(c):
    return c if isinstance(c, str) else "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def _hangs(garment):
    """A garment with a skirt on the ring (HumanFace runs HumanSkirt only while one is worn)."""
    for tag in hum_builds.BUILDS:
        ob = bpy.data.objects.get(f"Cloth_{garment}_{tag}")
        if ob is not None:
            return any(vg.name.startswith("xh_skirt") for vg in ob.vertex_groups)
    return False


def _skirt_slack(garment):
    """Per build: how far the garment's skirt stands outside each ring column (hum_helpers.ring_slack)."""
    import hum_helpers
    if not _hangs(garment):
        return []
    arm = bpy.data.objects["HumanRig"]
    joints = {b.name: list(b.head_local) for b in arm.data.bones}
    out = []
    for tag in hum_builds.BUILDS:
        ob = bpy.data.objects.get(f"Cloth_{garment}_{tag}")
        if ob is not None:
            hip, knee = hum_helpers.ring_slack(ob, joints)
            out.append(dict(build=tag, hip=hip, knee=knee))
    return out


def export_config():
    import hum_cloak, hum_orcs
    F = hum_faces
    cfg = dict(
        sliders=[dict(name=n, hasNeg=neg is not None,
                      spread=F.SPREAD.get(n, 1.0), femBias=F.FEM_BIAS.get(n, 0.0), mascBias=F.MASC_BIAS.get(n, 0.0))
                 for n, pos, neg in F.SLIDERS],
        macros=list(F.MACROS.keys()),
        correctives=[dict(name=k, a=a, b=b) for k, (a, b) in F.CORRECTIVES.items()],
        skinTones=F.SKIN_TONES,
        hairColors=[dict(name=k, hex=v) for k, v in F.HAIR.items()],
        irisColors=[dict(name=k, hex=v) for k, v in F.IRIS.items()],
        dyes=[dict(name=k, hex=v) for k, v in F.DYES.items()],
        cloths=F.CLOTHS,
        bodySliders=F.BODY_SLIDERS,
        muscleSliders=F.MUSCLE_SLIDERS,
        garments=[dict(name=k, slot=g["slot"], layer=g["layer"], material=g["material"], hide=list(g["hide"]),
                       cover=list(hum_cloth.cover_of(k)),
                       # no cloak over pauldrons, gorgets or plate: it fits clothes (hum_cloak.bulky)
                       excludes=list(g.get("excludes", [])) + (hum_cloak.cloak_excludes() if k == "Cloak" else []),
                       capCut=float(g.get("capcut", 0.0)), hidesHair=bool(g.get("hides_hair", False)),
                       hoodCut=bool(g.get("hoodcut", False)), group=g.get("group", ""),
                       hidesFaceHair=bool(g.get("hides_face_hair", False)),
                       hidesHead=bool(g.get("hides_head", False)),
                       companions=list(g.get("companions", [])), companion=bool(g.get("companion", False)),
                       hangs=_hangs(k), skirtSlack=_skirt_slack(k))
                  for k, g in hum_cloth.GARMENTS.items()],
        regions=hum_cloth.REGIONS,
        linen=F.LINEN, wool=F.WOOL, leather=F.LEATHER, armorLeather=F.ARMOR_LEATHER,
        cloaks=F.CLOAKS, padding=F.PADDING, steel=F.STEEL, blackened=F.BLACKENED, suit=F.SUIT,
        builds=[dict(tag=t, sex=b["sex"], name=b["name"], odds=hum_builds.BUILD_ODDS[b["name"]],
                     keys=[dict(key=k, w=float(v)) for k, v in b["keys"].items()])
                for t, b in hum_builds.BUILDS.items()],
        bodyKeys=sorted(hum_builds.BODY_KEYS),
        armorSets=[dict(name=k, pieces=v) for k, v in hum_cloth.hum_armor.ARMOR_SETS.items()],
        metal=list(hum_material.METAL[:3]),
        hairStyles=[dict(name=k or "", masc=v[0], fem=v[1]) for k, v in F.HAIR_W.items()],
        beardStyles=[dict(name=k or "", w=v) for k, v in F.BEARD_W.items()],
        browStyles=[dict(name=k, masc=v[0], fem=v[1]) for k, v in F.BROW_W.items()],
        presets=[hum_orcs.export(p) for p in hum_orcs.PRESETS],          # face presets over a rolled face (orcs)
        shader=dict(shadeMax=hum_paint.SHADE_MAX, blushTint=list(hum_material.BLUSH_TINT[:3]),
                    freckleTint=list(hum_material.FRECKLE_TINT[:3]), lipFromTone=list(hum_material.LIP_FROM_TONE),
                    edgeDark=hum_material.EDGE_DARK),
    )
    path = os.path.join(EXPORT, "human_face_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return path


def export_all():
    a, b, cl = export_models()
    c = export_config()
    r = export_rig()
    print("exported", a, b, cl, c, r)
    return a, b, cl, c, r
