"""Head UV layout: MPFB's small islands (mouth, sockets) kept as seams, plus a face island,
ear islands and a back-of-head seam; unwrap, then give the face more texels and pack."""
import bpy
import bmesh
import numpy as np
from mathutils import Vector

FACE_SCALE = 1.8     # texel density of the face island relative to the scalp/neck
EAR_SCALE = 1.2


def _landmarks(ob, rig_centres):
    return rig_centres


def mark_seams(ob, ear_y, chin_z, face_back_y):
    """Seams on the head faces (material 0). Returns the face-island face indices."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    head = [f for f in bm.faces if f.material_index == 0]
    head_set = set(f.index for f in head)
    ears_vg = ob.vertex_groups["ears"].index
    dl = bm.verts.layers.deform.active
    is_ear_v = [ears_vg in v[dl] and v[dl][ears_vg] > 0.5 for v in bm.verts]

    def is_face(f):
        c = f.calc_center_median()
        return c.y < face_back_y and c.z > chin_z

    def is_ear(f):
        return all(is_ear_v[v.index] for v in f.verts)

    region = {}
    for f in head:
        region[f.index] = 'ear' if is_ear(f) else ('face' if is_face(f) else 'rest')
    for e in bm.edges:
        fs = [f for f in e.link_faces if f.index in head_set]
        if len(fs) != 2:
            continue
        a, b = fs
        seam = region[a.index] != region[b.index]
        # MPFB island borders (mouth bag, socket rims): UVs differ across the edge
        la = [l for l in a.loops if l.vert in e.verts]
        lb = [l for l in b.loops if l.vert in e.verts]
        for l1 in la:
            l2 = next(l for l in lb if l.vert == l1.vert)
            if (l1[uv].uv - l2[uv].uv).length > 1e-5:
                seam = True
        # back of the head, centre line, behind the ears
        mid = (e.verts[0].co + e.verts[1].co) / 2
        if abs(e.verts[0].co.x) < 1e-4 and abs(e.verts[1].co.x) < 1e-4 and mid.y > ear_y:
            seam = True
        e.seam = seam
    bm.to_mesh(me)
    bm.free()
    return [i for i, r in region.items() if r == 'face'], [i for i, r in region.items() if r == 'ear']


def unwrap(ob, face_idx, ear_idx, margin=0.006):
    me = ob.data
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for p in me.polygons:
        p.select = p.material_index == 0
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', margin=margin)
    except TypeError:
        bpy.ops.uv.unwrap(method='CONFORMAL', margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    # scale islands about their own centres
    uvd = me.uv_layers.active.data
    for idx, k in ((face_idx, FACE_SCALE), (ear_idx, EAR_SCALE)):
        loops = [l for i in idx for l in me.polygons[i].loop_indices]
        if not loops:
            continue
        P = np.array([uvd[l].uv[:] for l in loops])
        c = P.mean(0)
        for l, p in zip(loops, P):
            uvd[l].uv = tuple(c + (p - c) * k)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, margin=margin, shape_method='CONCAVE')
    bpy.ops.object.mode_set(mode='OBJECT')


def export_layout(ob, path, size=1024):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for p in ob.data.polygons:
        p.select = p.material_index == 0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.export_layout(filepath=path, size=(size, size), opacity=0.4, export_all=False)
    bpy.ops.object.mode_set(mode='OBJECT')
