"""LODs of the head and of every hair/beard/brow piece: LOD1 (mid distance), LOD2 (colony camera).

Head_L1: the head decimated (symmetric collapse) and bound to the full head with Surface Deform, so it
carries the same 98 face keys. Pieces: the same recipes built coarser (fewer, wider clumps, 4 sides, fewer
steps, no cap subdivision), named <piece>_L1, bound to the full head like LOD0.
"""
import bmesh
import bpy
import mathutils
import numpy as np

import hum_hair, hum_styles, hum_paint

LOD_COLS = {1: "HUM_LOD1", 2: "HUM_LOD2"}
HEAD_RATIO = {1: 0.2, 2: 0.07}      # ~9.5k -> ~1.9k / ~650 tris
NECK_FLAP = dict(down=0.008, inward=0.003)
REGION_NECK = 15                    # hum_cloth.REGIONS["neck"]
NECK_SINK = 0.005


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
    neck_flap(ob)
    ob.hide_set(True)
    ob.hide_render = True
    return ob, nk


def _key_arrays(me):
    n = len(me.vertices)
    out = []
    for k in me.shape_keys.key_blocks:
        a = np.empty(n * 3)
        k.data.foreach_get("co", a)
        out.append(a.reshape(-1, 3))
    return out


def neck_flap(ob):
    """Head and body LODs are decimated apart, so their neck rims are two different polylines (up to 2 mm apart)
    and background showed through between them. A short flap under the head's rim, tucked inside the neck: a ray
    through the gap hits skin. It takes its rim vertex's keys and weights, so it follows every face and pose."""
    if ob.get("neck_flap"):
        return 0
    me = ob.data
    keys = _key_arrays(me)
    n_old = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    rim = [e for e in bm.edges if e.is_boundary]
    rim_verts = {v for e in rim for v in e.verts}
    centre = sum((v.co for v in rim_verts), mathutils.Vector()) / len(rim_verts)
    made = bmesh.ops.extrude_edge_only(bm, edges=rim)["geom"]
    new_faces = [g for g in made if isinstance(g, bmesh.types.BMFace)]
    source = {}
    for v in (g for g in made if isinstance(g, bmesh.types.BMVert)):
        source[v] = next(e.other_vert(v) for e in v.link_edges if e.other_vert(v) in rim_verts)
    layers = [lay for group in (bm.loops.layers.uv, bm.loops.layers.float_color, bm.loops.layers.color)
              for lay in group.values()]
    for f in new_faces:
        f.material_index = 0
        f.smooth = True
        edge = next(e for e in f.edges if e in rim)
        old_face = next(x for x in edge.link_faces if x is not f)
        by_vert = {l.vert: l for l in old_face.loops}
        for l in f.loops:
            src = by_vert[source.get(l.vert, l.vert)]
            for lay in layers:
                l[lay] = src[lay]
    offsets = {}
    for v, s in source.items():
        side = s.co - centre
        side.z = 0.0
        d = mathutils.Vector((0, 0, -NECK_FLAP["down"])) - side.normalized() * NECK_FLAP["inward"]
        v.co = s.co + d
        offsets[v] = d
    bm.normal_update()
    wrong = [f for f in new_faces if f.normal.dot(f.calc_center_median() - centre) < 0]
    if wrong:
        bmesh.ops.reverse_faces(bm, faces=wrong)
    bmesh.ops.triangulate(bm, faces=new_faces)
    bm.verts.index_update()
    rows = [(v.index, s.index, offsets[v]) for v, s in source.items()]
    bm.to_mesh(me)
    bm.free()
    # bmesh's own shape key handling moves a copied vertex twice: the keys are written here
    rows.sort()
    assert rows[0][0] == n_old and rows[-1][0] == len(me.vertices) - 1
    src = [r[1] for r in rows]
    dd = np.array([r[2] for r in rows])
    for k, old in zip(me.shape_keys.key_blocks, keys):
        k.data.foreach_set("co", np.vstack([old, old[src] + dd]).ravel())
    me.update()
    ob["neck_flap"] = 1
    return len(rows)


def neck_regions(lo, body):
    """A body LOD's long faces reach from the neck down the chest or back, and a face's region is the majority of its
    vertices: "chest" faces touching the neck vanished under a shirt and cut a V out of the neck. A face touching the
    neck region is neck, and now never hidden, so its far corners sink under the cloth (_sink)."""
    me = body.data
    uv = me.uv_layers["Region"].data
    neck = np.zeros(len(me.vertices), bool)
    for p in me.polygons:
        if round(uv[p.loop_start].uv[0]) == REGION_NECK:
            neck[list(p.vertices)] = True
    b0 = _key_arrays(me)[0] if me.shape_keys else np.array([v.co for v in me.vertices])
    kd = mathutils.kdtree.KDTree(len(b0))
    for i, co in enumerate(b0):
        kd.insert(co, i)
    kd.balance()
    lm = lo.data
    b = _key_arrays(lm)[0] if lm.shape_keys else np.array([v.co for v in lm.vertices])
    near = np.array([neck[kd.find(co)[1]] for co in b])
    luv = lm.uv_layers["Region"].data
    import hum_cloth
    changed = []
    for p in lm.polygons:
        if round(luv[p.loop_start].uv[0]) in hum_cloth.MARGIN or not near[list(p.vertices)].any():
            continue
        for li in p.loop_indices:
            luv[li].uv = (REGION_NECK, 0.0)
        changed.append(p.index)
    _sink(lm, changed, near)
    return len(changed)


def _sink(me, faces, near):
    """The corners of these faces away from the neck go NECK_SINK along the inward normal, on the basis and every key."""
    corners = sorted({v for f in faces for v in me.polygons[f].vertices if not near[v]})
    if not corners:
        return 0
    keys = _key_arrays(me)
    b = keys[0]
    normal = np.zeros_like(b)
    for p in me.polygons:
        i = list(p.vertices)
        n = np.cross(b[i[1]] - b[i[0]], b[i[2]] - b[i[0]])
        normal[i] += n
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    d = -normal[corners] * NECK_SINK
    for k, a in zip(me.shape_keys.key_blocks, keys):
        a[corners] += d
        k.data.foreach_set("co", a.ravel())
    me.update()
    return len(corners)


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
        neck_regions(ob, body)
        ob.hide_set(True)
        ob.hide_render = True
        out[name] = (tris(ob), nk)
    return out
