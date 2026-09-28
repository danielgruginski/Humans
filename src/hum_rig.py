"""The skeleton: MPFB's "game_engine" rig (Unreal-style names, Unity Humanoid maps them), rebuilt from
its JSON so bone positions can be computed for *any* captured MPFB state (the same joint helper cubes the
mesh carries).

Body/head keys are stored as residuals: key = (MPFB shape) - (what skinning already does when the bones
move by that key's joint deltas). At runtime the bones are moved by sum(w_k * joint_delta_k) and the
blend shapes add the rest, so shape and skeleton agree for every character (limbs bend at the right place).
"""
import gzip
import json
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import hum_mpfb

MPFB_DATA = None
JOINT_DELTAS = {}      # key -> (n_bones x 3) bone-head deltas in armature space (filled by hum_build.build_all)
SK = None              # the Skeleton used for them
HEIGHT_RATIOS = {}     # {"tall": s, "short": s} uniform scales for height +1 / -1


def _data_dir():
    from bl_ext.user_default.mpfb.services.locationservice import LocationService
    return LocationService.get_mpfb_data("rigs")


def load_rig(name="game_engine"):
    d = _data_dir()
    with open(os.path.join(d, "standard", f"rig.{name}.json")) as f:
        rig = json.load(f)
    with open(os.path.join(d, "standard", f"weights.{name}.json")) as f:
        weights = json.load(f)["weights"]
    return rig, weights


class Skeleton:
    """Bone order (parents before children), joint groups, and the weight matrix on source vertices."""

    def __init__(self, src, name="game_engine"):
        self.rig, self.weights = load_rig(name)
        import hum_helpers
        hum_helpers.inject(self.rig)                 # helper bones: same joints as their hosts (hum_helpers)
        order, seen = [], set()

        def visit(b):
            if b in seen:
                return
            p = self.rig[b].get("parent")
            if p:
                visit(p)
            seen.add(b)
            order.append(b)
        for b in self.rig:
            visit(b)
        self.bones = order
        self.index = {b: i for i, b in enumerate(order)}
        # joint cube vertex groups used by the rig
        cubes = set()
        for b, v in self.rig.items():
            for end in ("head", "tail"):
                if v[end]["strategy"] == "CUBE":
                    cubes.add(v[end]["cube_name"])
        self.cubes = {c: hum_mpfb.group_members(src, c) for c in cubes}
        self.n_src = len(src.data.vertices)

    def ends(self, C):
        """(heads, tails) arrays (n_bones x 3) for full MPFB coords C."""
        H = np.zeros((len(self.bones), 3))
        T = np.zeros((len(self.bones), 3))
        # the joints first, then the helper bones off them (hum_helpers: a skirt ring link hangs off a calf,
        # which isn't its ancestor, so bone order alone doesn't have it yet)
        for offsets in (False, True):
            for i, b in enumerate(self.bones):
                for end, out in (("head", H), ("tail", T)):
                    e = self.rig[b][end]
                    if (e["strategy"] == "OFFSET") != offsets:
                        continue
                    if e["strategy"] == "CUBE":
                        out[i] = C[self.cubes[e["cube_name"]]].mean(0)
                    elif e["strategy"] == "MEAN":
                        out[i] = C[e["vertex_indices"]].mean(0)
                    elif e["strategy"] == "OFFSET":
                        out[i] = H[self.index[e["bone"]]] + np.asarray(e["offset"], float)
                    else:
                        raise NotImplementedError(e["strategy"])
        return H, T

    def weight_matrix(self, src_idx):
        """Dense (len(src_idx) x n_bones) skin weights for the given source vertex indices (rows sum to 1)."""
        pos = {int(v): i for i, v in enumerate(src_idx)}
        W = np.zeros((len(src_idx), len(self.bones)))
        for b, lst in self.weights.items():
            if b not in self.index:
                continue
            j = self.index[b]
            for vi, w in lst:
                i = pos.get(vi)
                if i is not None:
                    W[i, j] += w
        s = W.sum(1)
        empty = s < 1e-6
        W[empty, self.index["head"]] = 1.0          # e.g. our eyeballs: rigid on the head
        s = W.sum(1, keepdims=True)
        return W / s


def residual(C_state, C_base, J_state, J_base, W):
    """Shape-key coords for a key whose bones move by (J_state - J_base): base + delta - skinning(delta)."""
    return C_base + (C_state - C_base) - W @ (J_state - J_base)


# ------------------------------------------------------------------ armature object

def build_armature(scene, sk, heads, tails, name="HumanRig"):
    old = bpy.data.objects.get(name)
    if old is not None:
        arm_data = old.data
        bpy.data.objects.remove(old)
        bpy.data.armatures.remove(arm_data)
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    scene.collection.objects.link(ob)
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    with bpy.context.temp_override(active_object=ob, object=ob):
        bpy.ops.object.mode_set(mode='EDIT')
        for i, b in enumerate(sk.bones):
            eb = arm.edit_bones.new(b)
            eb.head = Vector(heads[i])
            tail = Vector(tails[i])
            if (tail - eb.head).length < 1e-4:
                tail = eb.head + Vector((0, 0, 0.05))
            eb.tail = tail
            eb.roll = sk.rig[b].get("roll", 0.0)
        for b in sk.bones:
            p = sk.rig[b].get("parent")
            if p:
                arm.edit_bones[b].parent = arm.edit_bones[p]
                arm.edit_bones[b].use_connect = False
        bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def skin(ob, arm, sk, W):
    """Vertex groups from a dense weight matrix + an Armature modifier. The helper bones' share of the
    weights is split off here (hum_helpers.redistribute), so every skinned mesh gets it."""
    import hum_helpers
    if "xh_deltoid_l" in sk.index and len(ob.data.vertices):
        P = np.zeros(len(ob.data.vertices) * 3)
        ob.data.vertices.foreach_get("co", P)
        joints = {b.name: np.array(b.head_local) for b in arm.data.bones}
        if all(h in joints for h in ("upperarm_l", "lowerarm_l", "thigh_l", "calf_l", "calf_r")):
            W = hum_helpers.redistribute(W, P.reshape(-1, 3), sk, joints, ob.data, hum_helpers.hanging_mask(ob))
    for vg in list(ob.vertex_groups):
        if vg.name in sk.index:
            ob.vertex_groups.remove(vg)
    for j, b in enumerate(sk.bones):
        idx = np.where(W[:, j] > 1e-4)[0]
        if len(idx) == 0:
            continue
        vg = ob.vertex_groups.new(name=b)
        for i in idx:
            vg.add([int(i)], float(W[i, j]), 'REPLACE')
    for m in list(ob.modifiers):
        if m.type == 'ARMATURE':
            ob.modifiers.remove(m)
    mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    ob.parent = arm


def pose_from_deltas(arm, sk, dJ):
    """Preview in Blender: translate pose bones so their heads move by dJ (armature space, n_bones x 3)."""
    for i, b in enumerate(sk.bones):
        pb = arm.pose.bones[b]
        p = sk.rig[b].get("parent")
        d = Vector(dJ[i] - (dJ[sk.index[p]] if p else 0))
        rest = arm.data.bones[b].matrix_local.to_3x3()
        pb.location = rest.inverted() @ d


def weights_of(ob, sk):
    """Dense weight matrix from an object's bone vertex groups."""
    n = len(ob.data.vertices)
    W = np.zeros((n, len(sk.bones)))
    gi = {vg.index: sk.index[vg.name] for vg in ob.vertex_groups if vg.name in sk.index}
    for v in ob.data.vertices:
        for g in v.groups:
            j = gi.get(g.group)
            if j is not None:
                W[v.index, j] = g.weight
    return W


def transfer_weights(target, source, sk):
    """Weights for a decimated copy: interpolate the source's weights at each target vertex's nearest
    point on the source (barycentric over the nearest face's corners, inverse-distance)."""
    import bmesh
    from mathutils.bvhtree import BVHTree
    Ws = weights_of(source, sk)
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    Wt = np.zeros((len(target.data.vertices), len(sk.bones)))
    for v in target.data.vertices:
        loc, nrm, fi, d = bvh.find_nearest(v.co)
        f = bm.faces[fi]
        ids = [u.index for u in f.verts]
        dist = np.array([(u.co - loc).length for u in f.verts]) + 1e-6
        k = 1.0 / dist
        Wt[v.index] = (Ws[ids] * k[:, None]).sum(0) / k.sum()
    bm.free()
    Wt /= np.maximum(Wt.sum(1, keepdims=True), 1e-9)
    return Wt


def rigid(ob, arm, sk, bone="head"):
    W = np.zeros((len(ob.data.vertices), len(sk.bones)))
    W[:, sk.index[bone]] = 1.0
    skin(ob, arm, sk, W)


def pose_for_keys(arm, keys):
    """Blender preview: move the pose bones by the weighted joint deltas of these keys (0..1 weights)."""
    if SK is None or not JOINT_DELTAS or arm is None:
        return
    dJ = np.zeros((len(SK.bones), 3))
    for k, w in keys.items():
        d = JOINT_DELTAS.get(k)
        if d is not None:
            dJ += w * d
    pose_from_deltas(arm, SK, dJ)


def hips_lift(keys):
    """How far the character must be raised so animated (Humanoid) hips keep the feet on the ground:
    the pelvis' rest height change from the keys (the Animator places hips at the base avatar's height)."""
    if SK is None or not JOINT_DELTAS:
        return 0.0
    i = SK.index["pelvis"]
    return float(sum(w * JOINT_DELTAS[k][i][2] for k, w in keys.items() if k in JOINT_DELTAS))


def restore(src, path=r"E:\Unity\Projects\GameArtGeneration\Humans\export\human_rig.json"):
    """Rebuild SK, JOINT_DELTAS and HEIGHT_RATIOS from the last export (after a reload or a Blender restart)."""
    global SK
    SK = Skeleton(src)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    JOINT_DELTAS.clear()
    import hum_helpers
    for k in d["keys"]:
        a = np.zeros((len(SK.bones), 3))
        for row in k["bones"]:
            if row["bone"] in SK.index:                         # (a helper bone since removed)
                a[SK.index[row["bone"]]] = row["d"]
        for name, h in hum_helpers.HELPERS.items():            # a helper moves with its host's joint
            a[SK.index[name]] = a[SK.index[h["host"]]]
        JOINT_DELTAS[k["key"]] = a
    HEIGHT_RATIOS.clear()
    HEIGHT_RATIOS.update(d["heightRatios"])
    return SK


def rest(arm):
    """Rest pose, unit scale (bindings and bakes must never see a preview pose)."""
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
    arm.scale = (1, 1, 1)
    arm.location = (0, 0, 0)
    bpy.context.view_layer.update()
