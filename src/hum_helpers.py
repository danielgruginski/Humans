"""Helper bones: extra deform bones driven from the main skeleton, never keyed by a clip.

Linear skinning collapses where a joint turns far (the armpit with the arms overhead, the hip crease when
sitting) and long skirts weighted to the thighs swing out level with them. A helper sits on a main joint and
takes part of the weights around it:

    xh_deltoid_l/r  at the shoulder joint, child of the clavicle, turns HALF as far as the upper arm
    xh_glute_l/r    at the hip joint, child of the pelvis, turns half as far as the thigh (tassets too)
    xh_skirtNN_hip  the skirt ring: 12 columns round the hips, each a link from the hips to just outside the
    xh_skirtNN_knee knees and one on down toward the hem. Unity's HumanSkirt simulates them (they hang, the legs
                    push them, they swing and trail); here they hang, or follow the thighs seated. (Rigid panels
                    turning with the thighs lifted whole quarters of a skirt when running - Daniel: "a weird
                    movement that does not exist in real life")

Runtime: Unity's HumanHelperBones drives them after the Animator (any Humanoid clip works - Humanoid never
touches bones outside the avatar); hum_anim drives them the same way for our Blender previews.

A helper copies its host bone's joint (head, tail, roll) and so its per-key joint deltas: the residual body
keys (key = shape - skinning of the joint deltas) stay valid. Names avoid Unity's Humanoid auto-mapping words
(shoulder, arm, hip, leg, knee...).
"""
import math

import numpy as np
from mathutils import Quaternion, Vector

# name: parent (hierarchy: where it rides), host (joint and rest orientation copied), source, f: the helper's world
# rotation turns f of the way its source turns past the source's parent ("share"); "spring" and "ring" bones are
# simulated in Unity (HumanSpringChain, HumanSkirt)
HELPERS = {
    "xh_deltoid_l": dict(parent="clavicle_l", host="upperarm_l", drive="share", source="upperarm_l", f=0.5),
    "xh_deltoid_r": dict(parent="clavicle_r", host="upperarm_r", drive="share", source="upperarm_r", f=0.5),
    "xh_glute_l": dict(parent="pelvis", host="thigh_l", drive="share", source="thigh_l", f=0.5),
    "xh_glute_r": dict(parent="pelvis", host="thigh_r", drive="share", source="thigh_r", f=0.5),
    # the cape chain: down the back of a cloak / cape, from between the shoulder blades to the hem; simulated
    # at runtime (Unity HumanSpringChain), rigid on the spine in Blender. Each node rides a spine joint plus a
    # fixed offset (so it moves with that joint's per-build offset); head -> the next node.
    "xh_cape_0": dict(parent="spine_03", host="spine_03", head_off=(0.0, 0.123, 0.112),
                      tail=("spine_01", (0.0, 0.237, -0.018)), drive="spring"),
    "xh_cape_1": dict(parent="xh_cape_0", host="spine_01", head_off=(0.0, 0.237, -0.018),
                      tail=("pelvis", (0.0, 0.343, -0.224)), drive="spring"),
    "xh_cape_2": dict(parent="xh_cape_1", host="pelvis", head_off=(0.0, 0.343, -0.224),
                      tail=("pelvis", (0.0, 0.363, -0.504)), drive="spring"),
}
CAPE = ["xh_cape_0", "xh_cape_1", "xh_cape_2"]

# the skirt ring, measured on the neutral body: per column (azimuth deg: 0 front, + toward the character's
# left), the hip pivot as an offset from the pelvis (on the body at hip height + 1 cm; 5 cm lower behind, under
# the buttocks - a pivot higher up swung the cloth above it back out, a bulge behind), the host of the lower
# joints (the calf on that side) and the knee point (3 cm outside the legs' hull at knee height: a knee reaches
# it where it would reach tight cloth) and the hem point (32 cm below) as offsets from it
RING = [
    (0, (0.0, -0.1109, -0.0074), "calf_l", (-0.1311, -0.0814, 0.0), (-0.1311, -0.1014, -0.32)),
    (30, (0.0653, -0.1055, -0.0108), "calf_l", (-0.0864, -0.0774, 0.0), (-0.0764, -0.0947, -0.32)),
    (60, (0.1435, -0.0753, -0.0199), "calf_l", (-0.0161, -0.0664, 0.0), (0.0013, -0.0764, -0.32)),
    (90, (0.1653, 0.0076, -0.0324), "calf_l", (0.0747, 0.0, 0.0), (0.0947, 0.0, -0.32)),
    (120, (0.123, 0.0786, -0.0449), "calf_l", (-0.0048, 0.0729, 0.0), (0.0125, 0.0829, -0.32)),
    (150, (0.0526, 0.0987, -0.0541), "calf_l", (-0.0827, 0.0839, 0.0), (-0.0727, 0.1012, -0.32)),
    (180, (0.0, 0.1, -0.0574), "calf_l", (-0.1311, 0.0879, 0.0), (-0.1311, 0.1079, -0.32)),
    (210, (-0.0526, 0.0987, -0.0541), "calf_r", (0.0827, 0.0839, 0.0), (0.0727, 0.1012, -0.32)),
    (240, (-0.123, 0.0786, -0.0449), "calf_r", (0.0048, 0.0729, 0.0), (-0.0125, 0.0829, -0.32)),
    (270, (-0.1653, 0.0076, -0.0324), "calf_r", (-0.0747, 0.0, 0.0), (-0.0947, 0.0, -0.32)),
    (300, (-0.1435, -0.0753, -0.0199), "calf_r", (0.0161, -0.0664, 0.0), (-0.0013, -0.0764, -0.32)),
    (330, (-0.0653, -0.1055, -0.0108), "calf_r", (0.0864, -0.0774, 0.0), (0.0764, -0.0947, -0.32)),
]
RING_RAISE = (45.0, 70.0)            # both thighs raised this far (deg, the less raised one): seated - the ring
                                     # follows the thighs (over the lap, the back tucked under them)
SKIRT_RING = [(f"xh_skirt{k:02d}_hip", f"xh_skirt{k:02d}_knee") for k in range(len(RING))]
SKIRT_HEM = [f"xh_skirt{k:02d}_hem" for k in range(len(RING))]     # weightless leaf: the knee link's tip for Unity
for _k, (_deg, _piv, _host, _knee, _hem) in enumerate(RING):
    _a, _b = SKIRT_RING[_k]
    HELPERS[_a] = dict(parent="pelvis", host="pelvis", head_off=_piv, tail=(_host, _knee), drive="ring",
                       source="pelvis", f=0.0, column=_k)
    HELPERS[_b] = dict(parent=_a, host=_host, head_off=_knee, tail=(_host, _hem), drive="ring",
                       source="pelvis", f=0.0, column=_k)
    HELPERS[SKIRT_HEM[_k]] = dict(parent=_b, host=_host, head_off=_hem,
                                  tail=(_host, (_hem[0], _hem[1], _hem[2] - 0.05)), drive="ring", source="pelvis",
                                  f=0.0, column=_k)


def ring_slack(ob, joints):
    """How far a garment's hanging cloth stands outside each ring column (m, rest space), for the hip link (at
    knee height, or just above the cloth's hem if it's shorter) and the knee link (at the hem point's height):
    HumanSkirt lets a leg push a column only once it reaches the cloth itself (pushed from 3 cm off the legs, a
    wide dress swung out long before a knee reached it, and further). 1.0 where no cloth hangs there."""
    import math
    P = np.array([v.co[:] for v in ob.data.vertices])
    Q = P[hanging_mask(ob)]
    out = ([], [])
    if not len(Q):
        return [1.0] * len(RING), [1.0] * len(RING)
    knee_y = 0.5 * (joints["calf_l"][1] + joints["calf_r"][1])
    knee_z = 0.5 * (joints["calf_l"][2] + joints["calf_r"][2])
    zmin = Q[:, 2].min()
    az = np.degrees(np.arctan2(Q[:, 0], -(Q[:, 1] - knee_y)))
    for k, (hip, knee) in enumerate(SKIRT_RING):
        piv, kp, hp = (np.asarray(joints[n], float) for n in (hip, knee, SKIRT_HEM[k]))
        a = math.radians(RING[k][0])
        u = np.array([math.sin(a), -math.cos(a)])
        near = np.abs((az - RING[k][0] + 180.0) % 360.0 - 180.0) < 20.0
        for j, (A, B, lo) in enumerate(((piv, kp, knee_z), (kp, hp, hp[2]))):
            z = max(lo, zmin + 0.03)
            band = near & (np.abs(Q[:, 2] - z) < 0.03)
            if z > A[2] - 0.05 or not band.any():                # no cloth along this link
                out[j].append(1.0)
                continue
            c = A + (B - A) * min((A[2] - z) / (A[2] - B[2]), 1.0)  # the link at that height
            centre = np.array([0.0, knee_y])
            out[j].append(round(float(((Q[band, :2] - centre) @ u).max() - (c[:2] - centre) @ u), 3))
    return out


def sync_bones(arm):
    """Add the helper bones missing from the armature (rest joints from its own bones), remove xh_ bones no
    longer in HELPERS. Edit mode on the armature; returns (added, removed)."""
    import bpy
    joints = {b.name: np.array(b.head_local) for b in arm.data.bones}
    add = [n for n in HELPERS if n not in joints]
    rem = [b.name for b in arm.data.bones if b.name.startswith("xh_") and b.name not in HELPERS]
    if not add and not rem:
        return [], []
    vl = bpy.context.view_layer
    vl.objects.active = arm
    with bpy.context.temp_override(active_object=arm, object=arm):
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones
        for n in rem:
            eb.remove(eb[n])
        for n in add:                                   # parents first: HELPERS lists them in order
            h = HELPERS[n]
            b = eb.new(n)
            b.head = Vector(node(joints, h, "head"))
            b.tail = Vector(node(joints, h, "tail"))
            b.roll = 0.0
            b.parent = eb[h["parent"]]
            b.use_connect = False
            joints[n] = np.array(b.head)
        bpy.ops.object.mode_set(mode='OBJECT')
    return add, rem


def ss(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def inject(rig):
    """Add the helpers to a game_engine rig dict (hum_rig.Skeleton): same ends and roll as their host."""
    for name, h in HELPERS.items():
        host = rig[h["host"]]
        if "head_off" in h:                        # off the joint: host head + a fixed offset
            rig[name] = {"parent": h["parent"], "roll": 0.0,
                         "head": {"strategy": "OFFSET", "bone": h["host"], "offset": list(h["head_off"])},
                         "tail": {"strategy": "OFFSET", "bone": h["tail"][0], "offset": list(h["tail"][1])}}
        else:
            rig[name] = {"parent": h["parent"], "head": host["head"], "tail": host["tail"],
                         "roll": host.get("roll", 0.0)}


def node(joints, h, end="head"):
    """A helper's head (or tail) from rest joint heads {bone: xyz}."""
    if end == "head":
        return np.asarray(joints[h["host"]], float) + np.asarray(h.get("head_off", (0, 0, 0)), float)
    b, off = h["tail"]
    return np.asarray(joints[b], float) + np.asarray(off, float)


# ------------------------------------------------------------------ weights

def _islands(me):
    """Connected-component id per vertex."""
    n = len(me.vertices)
    e = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in e.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n)])


def hanging_mask(ob):
    """Vertices of a garment's hanging parts (skirts, belts, capes): faces with Region 0 (hum_cloth writes
    shells with the body region under them). All False for anything else (the body, hair) - a shirt tail
    under trousers is a shell, not a skirt."""
    me = ob.data
    lay = me.uv_layers.get("Region")
    if not ob.name.startswith("Cloth_") or lay is None or not len(me.polygons):
        return np.zeros(len(me.vertices), bool)
    uv = np.zeros(len(me.loops) * 2, np.float32)
    lay.data.foreach_get("uv", uv)
    reg = np.rint(uv[0::2]).astype(int)
    vi = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    out = np.zeros(len(me.vertices), bool)
    out[vi[reg == 0]] = True
    return out


def redistribute(W, P, sk, joints, me=None, hanging=None):
    """Split weights onto the helpers. W: (n x bones), P: (n x 3) rest positions, joints: {bone: head}.
    Idempotent (a second pass undoes the first split before redoing it), so it can run inside every skin().
    Stiff pieces (a mesh island whose rows were all equal - plates, studs) keep one row, the island's mean."""
    if "xh_deltoid_l" not in sk.index:
        return W
    W = np.array(W, float)
    before = W.copy()
    ix = sk.index
    islands = None
    rigid = np.zeros(len(W), bool)                  # rows of stiff pieces (every row of their island equal)
    if me is not None and len(W):
        isl = _islands(me)
        order = np.argsort(isl, kind="stable")
        islands = np.split(order, np.flatnonzero(np.diff(isl[order])) + 1)
        for grp in islands:
            if len(grp) > 1 and np.abs(before[grp] - before[grp[0]]).max() < 1e-4:
                rigid[grp] = True
    for s in "lr":
        # upper arm -> deltoid: half the arm's turn at the shoulder, fading out by mid upper arm
        a, e = joints[f"upperarm_{s}"], joints[f"lowerarm_{s}"]
        T = W[:, ix[f"upperarm_{s}"]] + W[:, ix[f"xh_deltoid_{s}"]]
        t = (P - a) @ (e - a) / max(float((e - a) @ (e - a)), 1e-9)
        g = 0.5 * (1.0 - ss(0.0, 0.5, t))
        W[:, ix[f"xh_deltoid_{s}"]] = T * g
        W[:, ix[f"upperarm_{s}"]] = T * (1 - g)
    # skirts: the hanging part of a garment from the hips down goes onto the ring (see RING) - the two columns
    # either side of the vertex by azimuth round the hips, the hip link down to the knee, the knee link below.
    # The ring takes c of the row (0 at the waist .. 1 from just below the hips), the other bones share the
    # rest in their proportions, only the biggest two kept (Unity skins with 4: it had dropped up to 14% of a
    # dress row's weight, so the Blender preview moved differently). Idempotent: a second pass finds the same c
    # and at most two other bones
    ring_hip = [ix[a] for a, b in SKIRT_RING]
    ring_knee = [ix[b] for a, b in SKIRT_RING]
    cols = ring_hip + ring_knee
    is_col = np.zeros(W.shape[1], bool)
    is_col[cols] = True
    Hs = W[:, cols].sum(1)
    thighs = sum(W[:, ix[f"{b}_{s}"]] for b in ("thigh", "calf", "xh_glute") for s in "lr")
    # any hanging row the legs carry (capes - spine only - stay). Not only rows with some pelvis weight: a
    # `skirt_shell` skirt (tunic, coat, jerkin, hauberk, gambeson) is weighted like trousers away from the centre -
    # its sides stayed on the legs while the centre hung from the ring, and the skirt tore apart
    skirt = (thighs > 0.02) | (Hs > 1e-4)
    if hanging is not None:
        skirt &= hanging                   # only hanging parts are skirts (a shirt tail under trousers is a shell)
    hip_z = 0.5 * (joints["thigh_l"][2] + joints["thigh_r"][2])
    hip_y = 0.5 * (joints["thigh_l"][1] + joints["thigh_r"][1])
    knee_z = 0.5 * (joints["calf_l"][2] + joints["calf_r"][2])
    fb = ss(hip_y - 0.02, hip_y + 0.10, P[:, 1])                  # 0 in front of the hips .. 1 behind (+y)
    # in front from the hips down; behind only from the back pivots down (cloth above a pivot swings backward
    # when the thigh pitches forward: a bulge behind the hips when running)
    pivot_z = hip_z - 0.05
    c_front = ss(hip_z + 0.08, hip_z - 0.12, P[:, 2])
    c_back = ss(hip_z + 0.08, pivot_z - 0.05, P[:, 2])
    c = np.where(skirt & ~rigid, c_front * (1 - fb) + c_back * fb, 0.0)
    off = (c <= 0) & (Hs > 1e-4)                                  # ring weight where there's no skirt: pelvis
    W[off, ix["pelvis"]] += Hs[off]
    W[np.ix_(off, cols)] = 0.0
    rows = np.flatnonzero(c > 0)
    if len(rows):
        S = W[rows].sum(1)
        N = S - Hs[rows]
        Wr = W[rows]
        Wr[:, is_col] = 0.0
        Wr *= np.where(N > 1e-9, (1 - c[rows]) * S / np.maximum(N, 1e-9), 0.0)[:, None]
        # the biggest two of the other bones, their total kept
        tot = Wr.sum(1)
        drop = np.argsort(-Wr, 1)[:, 2:]
        np.put_along_axis(Wr, drop, 0.0, 1)
        kept = Wr.sum(1)
        Wr *= np.where(kept > 1e-9, tot / np.maximum(kept, 1e-9), 0.0)[:, None]
        n_col = len(SKIRT_RING)
        az = np.degrees(np.arctan2(P[rows, 0], -(P[rows, 1] - hip_y))) % 360.0
        u = az / (360.0 / n_col)
        k0 = np.floor(u).astype(int) % n_col
        t = u - np.floor(u)
        g = ss(knee_z + 0.05, knee_z - 0.10, P[rows, 2])          # hip link -> knee link
        share = c[rows] * S
        # the knee band (0 < g < 1) is below the hips: c = 1 there, so no other bones - 4 ring links at most
        idx = np.arange(len(rows))
        for kk, wt in ((k0, 1 - t), ((k0 + 1) % n_col, t)):
            np.add.at(Wr, (idx, np.array(ring_hip)[kk]), share * wt * (1 - g))
            np.add.at(Wr, (idx, np.array(ring_knee)[kk]), share * wt * g)
        W[rows] = Wr
    ringed = (W[:, ring_hip + ring_knee] > 1e-6).any(1)
    for s in "lr":
        # thigh -> glute: half the thigh's turn at the hip, fading out by 40% down the thigh (not on skirt rows:
        # a third bone there would break the 4)
        hip, knee = joints[f"thigh_{s}"], joints[f"calf_{s}"]
        T = W[:, ix[f"thigh_{s}"]] + W[:, ix[f"xh_glute_{s}"]]
        t = (P - hip) @ (knee - hip) / max(float((knee - hip) @ (knee - hip)), 1e-9)
        gg = np.where(ringed, 0.0, 0.5 * (1.0 - ss(0.0, 0.4, t)))
        W[:, ix[f"xh_glute_{s}"]] = np.where(ringed, W[:, ix[f"xh_glute_{s}"]], T * gg)
        W[:, ix[f"thigh_{s}"]] = np.where(ringed, W[:, ix[f"thigh_{s}"]], T * (1 - gg))
    if islands is not None and len(rows):
        # a stiff piece on a skirt (a stud, a rivet) rides the cloth under it: the nearest ring row (it kept the
        # legs' weights and floated off the hanging cloth)
        ring_rows = rows[c[rows] > 0.5]
        for grp in islands:
            if len(grp) > 1 and rigid[grp[0]] and hanging is not None and hanging[grp].any() and len(ring_rows):
                d = np.linalg.norm(P[ring_rows] - P[grp].mean(0), axis=1)
                if d.min() < 0.06:
                    W[grp] = W[ring_rows[int(np.argmin(d))]]
    if islands is not None:
        for grp in islands:
            if len(grp) > 1 and rigid[grp[0]]:
                W[grp] = W[grp].mean(0)
                # a big stiff piece on the shoulder (a pauldron's shell, not a stud): its arm weight onto the
                # deltoid helper, graded down the arm - the shell turns a quarter as far as the arm (it rode up
                # round the helm overhead), the lames below follow the arm as before
                if np.linalg.norm(P[grp].max(0) - P[grp].min(0)) > 0.06:
                    c = P[grp].mean(0)
                    for s in "lr":
                        ua, dl = ix[f"upperarm_{s}"], ix[f"xh_deltoid_{s}"]
                        T = W[grp[0], ua] + W[grp[0], dl]
                        if T < 1e-6:
                            continue
                        a, e = joints[f"upperarm_{s}"], joints[f"lowerarm_{s}"]
                        tc = float((c - a) @ (e - a) / max(float((e - a) @ (e - a)), 1e-9))
                        q = max(float(1.0 - ss(0.1, 0.6, tc)), W[grp[0], dl] / T)
                        W[grp, dl] = T * q
                        W[grp, ua] = T * (1 - q)
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


def apply_to_object(ob, arm, sk):
    """Re-split an already skinned object's weights in place (only the host and helper groups change)."""
    import hum_rig
    me = ob.data
    n = len(me.vertices)
    if n == 0:
        return 0
    W = hum_rig.weights_of(ob, sk)
    hosts = [f"{b}_{s}" for b in ("upperarm", "thigh") for s in "lr"] + list(HELPERS)
    if not W[:, [sk.index[h] for h in hosts]].any():
        return 0
    P = np.zeros(n * 3)
    me.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    joints = {b.name: np.array(b.head_local) for b in arm.data.bones}
    W2 = redistribute(W, P, sk, joints, me, hanging_mask(ob))
    rest_shift(ob, W, W2, sk)                       # the skirt hem's dJ is the calf's: keep the build fit
    changed = np.flatnonzero(np.abs(W2 - W).max(0) > 1e-5)
    for j in changed:
        name = sk.bones[j]
        col = W2[:, j]
        vg = ob.vertex_groups.get(name)
        if vg is None:
            if not (col > 1e-4).any():
                continue
            vg = ob.vertex_groups.new(name=name)
        vg.remove(list(range(n)))
        nz = np.flatnonzero(col > 1e-4)
        # batch equal weights (stiff pieces share values) - one add per distinct value
        vals = np.round(col[nz], 5)
        for v in np.unique(vals):
            vg.add(nz[vals == v].tolist(), float(v), 'REPLACE')
    return int((W2[:, [sk.index[h] for h in HELPERS]] > 1e-4).any(1).sum())


# ------------------------------------------------------------------ driving (Blender previews: hum_anim)

def _ring(D, parent, rig, name, h):
    """The skirt ring in the Blender preview (no simulation): the links hang in the character's frame (the
    armature's: a world delta of identity); seated (both thighs raised) the hip links turn toward their knee
    point carried by the thighs - over the lap, the back tucked under them. Unity HumanSkirt uses the same
    targets and simulates round them."""
    hip, knee = SKIRT_RING[h["column"]]
    if name != hip or rig is None:                                # the knee link and its tip hang
        return Quaternion()
    raised = []
    for b in ("thigh_l", "thigh_r"):
        d0 = rig.dir(b)
        raised.append(math.degrees((D[b] @ d0).angle(D[parent[b]] @ d0)))
    k = float(ss(RING_RAISE[0], RING_RAISE[1], min(raised)))
    if k <= 0.0:
        return Quaternion()
    side = float(ss(-0.11, 0.11, rig.head[knee].x))               # the left thigh's share

    def carried(sd):
        th = f"thigh_{sd}"
        return D["pelvis"] @ (rig.head[th] - rig.head[hip]) + D[th] @ (rig.head[knee] - rig.head[th])
    rest = (rig.head[knee] - rig.head[hip]).normalized()
    seat = (carried("l") * side + carried("r") * (1 - side)).normalized()
    return rest.rotation_difference(rest.lerp(seat, k).normalized())


def drive(D, parent, rig=None):
    """Set the helpers' world deltas in a hum_anim Pose.D dict from the main bones - the Unity component's one
    formula: slerp(I, the source's turn past its parent, f) on that parent; ring links from _ring.
    parent: {bone: parent bone}."""
    def part(q, f):
        if q.w < 0:
            q = -q
        return Quaternion().slerp(q, f)
    for name, h in HELPERS.items():
        if name not in D or h["drive"] == "spring":          # springs: rigid on their parent here
            continue
        if h["drive"] == "ring":
            D[name] = _ring(D, parent, rig, name, h)
            continue
        src, sp = D[h["source"]], D[parent[h["source"]]]
        base = D[h["base"]] if h.get("base") else sp          # turned on top of the source's parent (or a base)
        D[name] = part(src @ sp.inverted(), h["f"]) @ base    # f of the source's turn, in world space
    return D


# ------------------------------------------------------------------ in-place edits keep the build fit

def rest_shift(ob, W_old, W_new, sk):
    """Garments are stored at rest: built shape - W @ dJ(build). An in-place weight change must move the rest
    coords by (W_old - W_new) @ dJ, or the garment lands off its build (helpers that copy their host's joint
    need nothing: their dJ is the host's). Shifts the vertices and every shape key. Returns the max shift (m)."""
    import hum_builds, hum_cloth
    if not ob.get("at_rest"):
        return 0.0
    _, tag, _ = hum_cloth.parse_cloth(ob.name)
    if tag not in hum_builds.BUILDS:
        return 0.0
    dJ = hum_builds.joint_offsets(hum_builds.BUILDS[tag]["keys"], sk)
    D = (np.asarray(W_old) - np.asarray(W_new)) @ dJ
    if not np.abs(D).max() > 1e-6:
        return 0.0
    me = ob.data
    for kb in (me.shape_keys.key_blocks if me.shape_keys else []):
        c = np.zeros(len(kb.data) * 3, np.float32)
        kb.data.foreach_get("co", c)
        kb.data.foreach_set("co", (c.reshape(-1, 3) + D).astype(np.float32).ravel())
    c = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", c)
    me.vertices.foreach_set("co", (c.reshape(-1, 3) + D).astype(np.float32).ravel())
    me.update()
    return float(np.linalg.norm(D, axis=1).max())
