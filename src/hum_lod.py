"""LODs of the head and of every hair/beard/brow piece: LOD1 (mid distance), LOD2 (colony camera).

Head_L1: the head decimated (symmetric collapse) and bound to the full head with Surface Deform, so it
carries the same 98 face keys. Pieces: the same recipes built coarser (fewer, wider clumps, 4 sides, fewer
steps, no cap subdivision), named <piece>_L1, bound to the full head like LOD0.
"""
import bpy
import numpy as np

import hum_hair, hum_styles, hum_paint

LOD_COLS = {1: "HUM_LOD1", 2: "HUM_LOD2"}
HEAD_RATIO = {1: 0.2, 2: 0.07}      # ~9.5k -> ~1.9k / ~650 tris


def _collection(scene, lod):
    name = LOD_COLS[lod]
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def _place(scene, ob, lod):
    col = _collection(scene, lod)
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    col.objects.link(ob)
    return ob


def head_lod(scene, head, lod=1):
    ratio = HEAD_RATIO[lod]
    name = head.name + f"_L{lod}"
    old = bpy.data.objects.get(name)
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old)
        bpy.data.meshes.remove(me)
    me = head.data.copy()
    me.name = name
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    if ob.data.shape_keys:
        ob.shape_key_clear()
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    mod = ob.modifiers.new("Decimate", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_symmetry = True
    mod.symmetry_axis = 'X'
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    _place(scene, ob, lod)
    nk, err = hum_hair.bind_keys(ob, head)
    ob.hide_set(True)
    ob.hide_render = True
    return ob, nk


def piece_lods(scene, head, lod=1):
    """Coarse versions of every style, bound to the head's keys."""
    for k in head.data.shape_keys.key_blocks[1:]:
        k.value = 0.0
    H = hum_hair.HeadFrame(head)
    mat = bpy.data.materials["M_HumanHair"]
    out = []
    for kind, table in (("hair", hum_styles.HAIR), ("beard", hum_styles.BEARD), ("brows", hum_styles.BROWS)):
        for name in table:
            if kind == "brows" and lod >= 2:
                continue                                  # painted brows only at the colony camera
            ob = hum_styles.build(scene, H, kind, name, lod=lod)
            hum_paint.set_materials(ob, [mat])
            _place(scene, ob, lod)
            nk, _ = hum_hair.bind_keys(ob, head)
            if kind == "hair":
                hum_hair.smooth_keys_spatial(ob)
            ob.hide_set(True)
            ob.hide_render = True
            out.append((ob.name, hum_hair.tris(ob), nk))
    return out


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_all(scene, head):
    out = {}
    for lod in (1, 2):
        ob, nk = head_lod(scene, head, lod)
        out[ob.name] = (tris(ob), nk)
        for name, t, k in piece_lods(scene, head, lod):
            out[name] = (t, k)
    return out


BODY_RATIO = {1: 0.3, 2: 0.14}


def body_lods(scene, body):
    """Decimated bodies bound to the full body's keys (Surface Deform), like the head LODs."""
    out = {}
    for lod in (1, 2):
        name = body.name + f"_L{lod}"
        old = bpy.data.objects.get(name)
        if old is not None:
            me = old.data
            bpy.data.objects.remove(old)
            bpy.data.meshes.remove(me)
        me = body.data.copy()
        me.name = name
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        if ob.data.shape_keys:
            ob.shape_key_clear()
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
        mod = ob.modifiers.new("Decimate", 'DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = BODY_RATIO[lod]
        mod.use_symmetry = True
        mod.symmetry_axis = 'X'
        mod.use_collapse_triangulate = True
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        for p in ob.data.polygons:
            p.use_smooth = True
        _place(scene, ob, lod)
        nk, _ = hum_hair.bind_keys(ob, body)
        ob.hide_set(True)
        ob.hide_render = True
        out[name] = (tris(ob), nk)
    return out
