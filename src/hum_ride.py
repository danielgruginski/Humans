"""The orc mammoth driver (2026-10-18): an orc on the war mammoth's neck, one clip per mammoth clip plus its own.

Daniel: "We should have goblin warg riders and orc mammoth riders, complete with animations"; his picks: one driver on
the neck (mammoth_tack in the Beasts repo: a rug in the dip behind the head's dome, a foot rope behind the ears, a
rope grip, the Socket_Driver bone), every clip made here, art and a test scene first. The goblin side is
Goblins/src/gob_ride.py; this is the same method on the Humans rig and hum_anim's pose maths.

Scene **Orc_Mammoth** (setup()): MammothRig, MammothBody, MammothTack and the Mammoth_* actions appended from the
Beasts file, and `OrcRider`, a copy of HumanRig (same armature) parented to Socket_Driver at an orc's mean height
(SCALE, the preset's x1.11-1.2), its bones moved to the MOrc build's joints (hum_rig.pose_from_deltas), wearing copies
of the body (MOrc keys), the head (an orc face), the Orc Hide garments and the weapon kit's IronSpear.

Poses are hum_anim Poses on OrcRig: the base rig with the MOrc build's joint offsets (from export/human_rig.json), so
legs and arms reach with an orc's proportions. Everything is in the rider's armature space = the driver's seat; the
pelvis is keyed against the base rest (Unity's Animator places the hips at the base avatar's height), rotations as
hum_anim keys them. Exported from HumanRig through hum_anim.export_clips (Human@MammothDriver_*.fbx); in Unity the
orc's root is a child of Socket_Driver and plays MammothDriver_<mammoth clip> at the mammoth's clip time.

Synced clips (every frame keyed, the mammoth's length): a damped rider driven by the seat's accelerations (the torso
lags and keeps part of its world uprightness, the head stays level), feet tucked under the foot rope and the left
fist on the grip where the tack mesh has them in that frame, and per-clip accents (spear up and a roar with the
trumpet, levelled like a lance in the charge, clinging in the stomp); in Death it rides the mammoth down and slides
off the high (left) side as it slumps to its right.
Own clips (upper-body overlays in Unity, the mammoth standing; Fall is played detached from the seat):
    MammothDriver_Thrust   overhand spear jab down at a man by the mammoth's right shoulder (event 'Hit')
    MammothDriver_Flinch
    MammothDriver_Fall     killed on the neck: slumps, slides off the left side, falls to the ground and lies
"""
import json, math, os
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
import hum_anim as A
from hum_anim import Pose, Rig, frame, eul, ss, UP, FWD, LEFT

SCENE = "Orc_Mammoth"
RIDER = "OrcRider"
MOUNT, MBODY, TACK = "MammothRig", "MammothBody", "MammothTack"
SEAT_BONE = "Socket_Driver"
BEASTS_FILE = r"E:\Unity\Projects\GameArtGeneration\Beasts\blender\beasts.blend"
RIG_JSON = r"E:\Unity\Projects\GameArtGeneration\Humans\export\human_rig.json"
SPEAR_FBX = r"E:\Unity\Projects\GameArtGeneration\Weapons\export\Models\Wpn_IronSpear.fbx"
PREFIX = "MammothDriver_"
BUILD_TAG = "MOrc"
SCALE = 1.155                                 # the orc preset's mean height scale
FPS = 30
DT = 1.0 / FPS
RT, BACK = -LEFT, -FWD
SIDES = (("l", 1.0), ("r", -1.0))
LOOK = ("Body", "Head", "Beard_Tusks", "Brows_Bushy", "Hair_Mohawk", "Cloth_OrcKilt_MOrc", "Cloth_OrcMantle_MOrc",
        "Cloth_Trousers_MOrc", "Cloth_Boots_MOrc", "Cloth_Bracers_MOrc")

FOOT_Y = -1.65                                # mammoth_tack.FOOT_Y (world)
SIT = 0.105                                   # the pelvis joint above the rug (rider units)
PELVIS_TILT = -4.0
SPINE = (2.0, 3.0, 2.0)


# ----------------------------------------------------------------------------------------- the orc's rig
def build_deltas(tag=BUILD_TAG):
    """Bone -> head offset (armature space) for a build: its keys' joint deltas from the last rig export."""
    import hum_builds
    keys = hum_builds.BUILDS[tag]["keys"]
    with open(RIG_JSON, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for k in d["keys"]:
        w = keys.get(k["key"], 0.0)
        if not w:
            continue
        for row in k["bones"]:
            out[row["bone"]] = out.get(row["bone"], Vector()) + Vector(row["d"]) * w
    return out


class OrcRig(Rig):
    """hum_anim.Rig with the build's joints: heads and tails moved by the deltas (a tail is its child's head, or
    moves with its own head), and the hand measures that depend on them redone."""
    def __init__(self, deltas=None, ob_name=None):
        super().__init__()
        if ob_name:
            self.ob = bpy.data.objects[ob_name]
        self.base_head = {b: h.copy() for b, h in self.head.items()}
        dJ = deltas if deltas is not None else build_deltas()
        kids = {}
        for b, p in self.parent.items():
            if p:
                kids.setdefault(p, []).append(b)
        for b in self.head:
            self.head[b] = self.base_head[b] + dJ.get(b, Vector())
        for b in self.tail:
            # the tail follows the child on its line, or the bone's own head
            self.tail[b] = self.tail[b] + dJ.get(b, Vector())
            for c in kids.get(b, []):
                if (self.base_head[c] - (self.tail[b] - dJ.get(b, Vector()))).length < 1e-4:
                    self.tail[b] = self.head[c].copy()
        for s, sx in (("l", 1.0), ("r", -1.0)):
            h = self.head[f"hand_{s}"]
            n = (self.head[f"index_01_{s}"] - h).cross(self.head[f"pinky_01_{s}"] - h).normalized()
            self.dorsal[s] = n if n.x * sx > 0 else -n
            self.grip_axis[s] = (self.head[f"index_01_{s}"] - self.head[f"pinky_01_{s}"]).normalized()
            self.fist[s] = (self.head[f"middle_01_{s}"] - self.head[f"hand_{s}"]) \
                - self.dir(f"middle_01_{s}") * 0.016 * 1.3 - self.dorsal[s] * 0.016 * 1.3
            self.strike_axis[s] = self.head[f"middle_01_{s}"] - self.head[f"hand_{s}"]
        self.arm_len = (self.head["lowerarm_l"] - self.head["upperarm_l"]).length + \
            (self.head["hand_l"] - self.head["lowerarm_l"]).length


def hand_turn(rig, s, grip, knuckles):
    """World rotation (relative to rest) turning hand s so the handle runs along `grip` (little finger -> index)
    and the knuckles face `knuckles`."""
    return frame(Vector(grip), Vector(knuckles)) @ frame(rig.grip_axis[s], rig.strike_axis[s]).inverted()


GRIP_DIRS = [(RT * math.cos(math.radians(a)) + FWD * math.sin(math.radians(a)) * c + UP * math.sin(math.radians(a)) * (1 - c)).normalized()
             for a in (0, 25, 50, 75) for c in (1.0, 0.5, 0.0)] + [(RT - FWD * 0.5).normalized(), (RT - UP * 0.5).normalized()]
HINT = {}       # side -> the elbow angle round the shoulder-wrist line chosen the frame before (reset per clip/key)


def hold(p, s, fist_at, grip, knuckles=None, elbow_dir=None, curl=0.8, hint=None, cone=0.0):
    """Hand s closed round a handle through fist_at (rider space), the handle along `grip`. The elbow and the hand's
    roll come from hum_anim._handle_hands (cap): forearm twist and wrist bend kept where a wrist goes and Humanoid
    keeps them -- a hand turned freely (the first pass) put the rope-grip arm past Unity's limits and it came out
    twisted (2026-10-18). The elbow carries over from the frame before (HINT) so it can't hop."""
    k = hint or s                                         # (a second pose of the same arm keeps its own)
    if k in CHAIN:                                        # follow on from the frame before
        _hold_near(p, s, Vector(fist_at), Vector(grip).normalized(), k)
        if not _over(p, s, margin=-6.0):                 # (a few degrees over: Unity clamps that unseen; a fresh
                                                          # solve would hop)
            p.fingers(s, curl, spread=0.3)
            return p.D[f"hand_{s}"]
        del CHAIN[k]                                      # following on breaks the wrist: solve afresh
    p.elbow = {}
    A._handle_hands(p.rig, p, Vector(fist_at), Vector(grip), hands=((s, 0.0),), cap=True,
                    elbow={s: HINT[k]} if k in HINT else None)
    if k in HINT and _over(p, s, margin=-3.0):           # the hint drifted past the limits: search all again
        p.elbow = {}
        A._handle_hands(p.rig, p, Vector(fist_at), Vector(grip), hands=((s, 0.0),), cap=True, elbow=None)
    if cone and _over(p, s, margin=-1.0):
        _tilt(p, s, Vector(fist_at), Vector(grip).normalized(), k, cone)
    elif cone:
        HINT[k + "_dir"] = Vector(grip).normalized()
    if s in p.elbow:
        HINT[k] = p.elbow[s]
        CHAIN[k] = (_elbow_dir(p, s, Vector(fist_at)), A.wrist_strain(p.rig, p, s)[0])
    p.fingers(s, curl, spread=0.3)
    return p.D[f"hand_{s}"]


CHAIN = {}      # key -> (elbow direction, forearm twist) the frame before chose: the next frame searches near them
EL0 = {"l": Vector((0.6, 0.2, -0.8)), "r": Vector((-0.6, 0.2, -0.8))}     # hum_anim._handle_hands' elbow zero


def _elbow_dir(p, s, fist):
    """Where the elbow points, square to the shoulder-fist line."""
    sh, el = p.pos(f"upperarm_{s}"), p.pos(f"lowerarm_{s}")
    line = (fist - sh).normalized()
    v = el - sh
    return (v - line * line.dot(v)).normalized()


def hold_fixed(p, s, fist, dirv, pole, tw):
    """hum_anim._handle_hands' placement with the elbow toward `pole` and the forearm twist searched near `tw`: the fist
    on the handle, the handle along dirv."""
    rig = p.rig
    sh = p.pos(f"upperarm_{s}")
    clav = 30.0 * ss(0.05, 0.40, fist.z - sh.z)
    wrist = fist.copy()
    for _ in range(24):                                   # (12 left the fist up to 9 cm off the rope grip)
        p.arm_ik(s, wrist, pole, clav=clav)
        q = A._hold(rig, p, s, dirv, None, tw)
        wrist = wrist.lerp(fist - q @ rig.fist[s], 0.6)
    p.arm_ik(s, wrist, pole, clav=clav)
    p.D[f"hand_{s}"] = A._hold(rig, p, s, dirv, None, tw)


def _hold_near(p, s, fist, dirv, k):
    """The frame before's elbow direction and forearm twist, moved only as far as comfort and reach ask (each step
    away costs): a hand can't flip to another, equally good answer from one frame to the next (the spear and the
    rope-grip arm swirled, 2026-10-18). The elbow is kept as a direction, not an angle from a fixed zero (that zero
    lay along the cocked thrust's reach, and the angle flipped)."""
    pole0, tw0 = CHAIN[k]
    line = (fist - p.pos(f"upperarm_{s}")).normalized()
    base = pole0 - line * line.dot(pole0)
    base = base.normalized() if base.length > 1e-4 else line.orthogonal().normalized()
    best = None
    for da in (0, -4, 4, -8, 8, -12, 12, -18, 18, -26, 26):
        pole = Quaternion(line, math.radians(da)) @ base
        hold_fixed(p, s, fist, dirv, pole, tw0)
        tw, fl, dv = A.wrist_strain(p.rig, p, s)
        miss = (p.pos(f"hand_{s}") + p.D[f"hand_{s}"] @ p.rig.fist[s] - fist).length
        cost = A.wrist_comfort(s, tw, fl, dv) + 1e8 * miss * miss + 25.0 * da * da + 6.0 * (tw - tw0) ** 2
        if best is None or cost < best[0]:
            best = (cost, pole)
    hold_fixed(p, s, fist, dirv, best[1], tw0)
    CHAIN[k] = (_elbow_dir(p, s, fist), A.wrist_strain(p.rig, p, s)[0])


def two_pass(n, pose_at, key, loop):
    """pose_at(i) -> Pose for every frame, keyed by key(i, pose). The hands follow on frame to frame (CHAIN); a loop
    runs a lap first, unkeyed, so its last frame leads into its first."""
    if loop:
        for i in range(n):
            pose_at(i)
    for i in range(n):
        key(i, pose_at(i))


def _tilt(p, s, fist, base, k, cone):
    """No wrist can hold the weapon on that line from there (a fist's grip runs across the forearm, give or take
    40 degrees): the weapon tilts within `cone` degrees to where the wrist is most comfortable, near the frame
    before's tilt so it doesn't hop."""
    perp = base.orthogonal().normalized()
    prev = HINT.get(k + "_dir")
    hint = {s: HINT[k]} if k in HINT else None            # keep the elbow near the frame before's
    best = None
    for ang in (8.0, 16.0, 24.0, 32.0, cone):
        for az in range(0, 360, 30):
            dv = Quaternion(base, math.radians(az)) @ (Quaternion(perp, math.radians(ang)) @ base)
            p.elbow = {}
            A._handle_hands(p.rig, p, fist, dv, hands=((s, 0.0),), cap=True, elbow=hint)
            cost = A.wrist_comfort(s, *A.wrist_strain(p.rig, p, s)) + 15.0 * ang * ang
            if prev is not None:
                cost += 20000.0 * (dv - prev).length ** 2
            if best is None or cost < best[0]:
                best = (cost, dv)
    p.elbow = {}
    A._handle_hands(p.rig, p, fist, best[1], hands=((s, 0.0),), cap=True, elbow=hint)
    HINT[k + "_dir"] = best[1]


def _over(p, s, margin=3.0):
    """The wrist past Humanoid's limits (twist 90, flex 80, deviation 40), less a margin."""
    tw, fl, dv = A.wrist_strain(p.rig, p, s)
    return abs(tw) > 90 - margin or abs(fl) > 80 - margin or abs(dv) > 40 - margin


# ----------------------------------------------------------------------------------------- scene
def _scene():
    return bpy.data.scenes[SCENE]


def _rider():
    return bpy.data.objects[RIDER]


def _mount():
    return bpy.data.objects[MOUNT]


def setup(seed=3):
    """Orc_Mammoth: the mammoth (appended from the Beasts file when missing) and OrcRider on Socket_Driver."""
    scn = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    if MOUNT not in bpy.data.objects:
        with bpy.data.libraries.load(BEASTS_FILE, link=False) as (src, dst):
            dst.objects = [MOUNT, MBODY, TACK]
            dst.actions = [a for a in src.actions if a.startswith("Mammoth_")]
        for a in dst.actions:
            a.use_fake_user = True
    mc = bpy.data.collections.get("MAM_Mount") or bpy.data.collections.new("MAM_Mount")
    if mc.name not in scn.collection.children:
        scn.collection.children.link(mc)
    for n in (MOUNT, MBODY, TACK):
        o = bpy.data.objects[n]
        if o.name not in mc.objects:
            mc.objects.link(o)
    rc = bpy.data.collections.get("ORC_Rider") or bpy.data.collections.new("ORC_Rider")
    if rc.name not in scn.collection.children:
        scn.collection.children.link(rc)
    for o in list(rc.objects):
        bpy.data.objects.remove(o)
    src = bpy.data.objects[A.RIG]
    rider = src.copy()
    rider.name = RIDER
    rider.animation_data_clear()
    rc.objects.link(rider)
    mount = _mount()
    b = mount.data.bones[SEAT_BONE]
    rider.parent = mount
    rider.parent_type = 'BONE'
    rider.parent_bone = SEAT_BONE
    rider.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted() @ \
        Matrix.Translation(b.head_local) @ Matrix.Scale(SCALE, 4)
    rider.matrix_basis = Matrix.Identity(4)
    import hum_builds
    keys = hum_builds.BUILDS[BUILD_TAG]["keys"]
    for n in LOOK:
        o = bpy.data.objects.get(n)
        if o is None:
            continue
        c = o.copy()
        if n in ("Body", "Head"):
            c.data = o.data.copy()                      # own shape-key values
        c.name = "R_" + n
        rc.objects.link(c)
        c.parent = rider
        c.matrix_parent_inverse = Matrix.Identity(4)
        c.matrix_basis = Matrix.Identity(4)
        for m in c.modifiers:
            if m.type == 'ARMATURE':
                m.object = rider
            elif hasattr(m, "target") and m.target is not None and m.target.name in ("Head", "Body"):
                m.target = bpy.data.objects.get("R_" + m.target.name, m.target)
        c.hide_set(False, view_layer=scn.view_layers[0])
        c.hide_render = False
    body = bpy.data.objects["R_Body"]
    for kb in body.data.shape_keys.key_blocks[1:]:
        kb.value = keys.get(kb.name, 0.0)
    _orc_face(seed)
    _paint_preview()
    pose_build(rider)
    _spear(rider)
    return rider


def _orc_face(seed):
    head = bpy.data.objects.get("R_Head")
    if head is None:
        return
    import hum_orcs
    f = hum_orcs.orc_face(seed)
    kb = head.data.shape_keys.key_blocks
    for k in kb[1:]:
        k.value = f["keys"].get(k.name, 0.0)


def _paint_preview():
    """Plain green skin for the previews (Workbench object colours); Unity's shader does the real orc."""
    for o in bpy.data.collections["ORC_Rider"].objects:
        if o.type != 'MESH':
            continue
        o.color = (0.30, 0.42, 0.20, 1) if o.name in ("R_Body", "R_Head") else (0.25, 0.18, 0.12, 1)
        if "Tusks" in o.name:
            o.color = (0.85, 0.8, 0.65, 1)
        if "Spear" in o.name:
            o.color = (0.35, 0.3, 0.25, 1)


def pose_build(rider):
    """The rider's bones at the build's joints (hum_rig.pose_from_deltas), so the MOrc garments fit."""
    dJ = build_deltas()
    r = rider
    for pb in r.pose.bones:
        b = pb.bone
        d = dJ.get(b.name, Vector()) - (dJ.get(b.parent.name, Vector()) if b.parent else Vector())
        pb.location = b.matrix_local.to_3x3().inverted() @ d


def _spear(rider):
    """The weapon kit's IronSpear in the right fist (socket frame: +Y to the point, +X the knuckles)."""
    old = bpy.data.objects.get("R_Spear")
    if old is not None:
        bpy.data.objects.remove(old)
    if not os.path.exists(SPEAR_FBX):
        return None
    keep = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=SPEAR_FBX)
    new = [o for o in bpy.data.objects if o not in keep]
    mesh = next(o for o in new if o.type == 'MESH')
    for o in new:
        if o is not mesh:
            bpy.data.objects.remove(o)
    mesh.name = "R_Spear"
    for c in mesh.users_collection:
        c.objects.unlink(mesh)
    bpy.data.collections["ORC_Rider"].objects.link(mesh)
    mesh.parent = None
    mesh.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    # bake the import's axis turn into the mesh so it is in socket space
    me = mesh.data
    me.transform(mesh.matrix_basis)
    mesh.matrix_basis = Matrix.Identity(4)
    rig = OrcRig(ob_name=RIDER)
    s = "r"
    x = rig.strike_axis[s].normalized()
    y = rig.grip_axis[s]
    x = (x - y * y.dot(x)).normalized()
    M = Matrix((x, y, x.cross(y))).transposed().to_4x4()
    M.translation = rig.base_head["hand_r"] + rig.fist[s]         # (pose_build moves the bone by the build)
    mesh.parent = rider
    mesh.parent_type = 'BONE'
    mesh.parent_bone = "hand_r"
    bone = rider.data.bones["hand_r"]
    mesh.matrix_parent_inverse = (bone.matrix_local @ Matrix.Translation((0, bone.length, 0))).inverted()
    mesh.matrix_basis = M
    return mesh


# ----------------------------------------------------------------------------------------- mount sampling
class Track:
    """Tack vertices followed through a mammoth clip: the foot rope where each foot tucks under it, the grip."""
    def __init__(self):
        tack = bpy.data.objects[TACK]
        me = tack.data
        a = me.color_attributes["info"]
        buf = np.empty(len(me.vertices) * 4, np.float32)
        a.data.foreach_get('color', buf)
        part = np.rint(buf.reshape(-1, 4)[:, 0] * 255).astype(int)
        co = np.array([v.co[:] for v in me.vertices])
        rope = (part == 6) & (np.abs(co[:, 1] - FOOT_Y) < 0.1)
        self.foot = {}
        for s, sx in SIDES:
            m = np.where(rope & (co[:, 0] * sx > 0.2) & (np.abs(co[:, 2] - 2.50) < 0.12))[0]
            self.foot[s] = m
        m = np.where((part == 6) & (np.abs(co[:, 0]) < 0.05) & (co[:, 1] > FOOT_Y - 0.05) & (co[:, 1] < FOOT_Y + 0.15))[0]
        top = co[m, 2].max()
        self.grip = m[co[m, 2] > top - 0.03]

    def sample(self):
        dg = bpy.context.evaluated_depsgraph_get()
        tack = bpy.data.objects[TACK]
        ev = tack.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        co = co.reshape(-1, 3)
        Mw = tack.matrix_world
        out = {s: Mw @ Vector(co[idx].mean(0)) for s, idx in self.foot.items()}
        out["grip"] = Mw @ Vector(co[self.grip].mean(0))
        return out


def mount_clip(clip):
    act = bpy.data.actions["Mammoth_" + clip]
    m = _mount()
    if m.animation_data is None:
        m.animation_data_create()
    m.animation_data.action = act
    return int(act.frame_range[0]), int(act.frame_range[1])


def sample_clip(clip, track):
    f0, f1 = mount_clip(clip)
    scn = bpy.context.scene
    out = []
    for f in range(f0, f1 + 1):
        scn.frame_set(f)
        bpy.context.view_layer.update()
        out.append(dict(S=_rider().matrix_world.copy(), **track.sample()))
    return out


LOOPS = {"Idle", "Walk", "Run", "Charge", "Graze", "Sleep"}


def simulate(samples, loop):
    """Torso lag (pitch, roll; deg) and seat float (m) behind the seat's motion, as gob_ride.simulate: a damped
    spring driven by the seat's acceleration in its own frame, half its tilt taken back."""
    n = len(samples)
    P = np.array([s["S"].translation[:] for s in samples])
    R = [s["S"].to_3x3().normalized() for s in samples]
    idx = (lambda i: i % (n - 1)) if loop else (lambda i: min(max(i, 0), n - 1))
    acc, tilt = [], []
    for i in range(n):
        a = (P[idx(i + 1)] - 2 * P[idx(i)] + P[idx(i - 1)]) / (DT * DT)
        loc = R[i].transposed() @ Vector(a)
        up = R[i].transposed() @ UP
        acc.append((loc, up))
        tilt.append((math.degrees(math.atan2(up.y, up.z)), math.degrees(math.atan2(up.x, up.z))))
    w0, zeta = 2 * math.pi * 1.8, 0.6
    wh, zh = 2 * math.pi * 2.6, 0.7
    th = ph = h = dth = dph = dh = 0.0
    out = [None] * n
    for rep in range(3 if loop else 1):
        for i in range(n - 1 if loop else n):
            a, up = acc[i]
            t_pitch, t_roll = tilt[i]
            tgt_th = -0.55 * t_pitch - 0.8 * (-a.y)
            tgt_ph = -0.55 * t_roll - 0.8 * (-a.x)
            dth += (w0 * w0 * (tgt_th - th) - 2 * zeta * w0 * dth) * DT
            dph += (w0 * w0 * (tgt_ph - ph) - 2 * zeta * w0 * dph) * DT
            dh += (wh * wh * (0 - h) - 2 * zh * wh * dh - 0.010 * a.z) * DT
            th += dth * DT
            ph += dph * DT
            h = min(max(h + dh * DT, -0.004), 0.03)
            out[i] = (max(min(th, 30), -25), max(min(ph, 18), -18), h, Vector(up))
    if loop:
        out[n - 1] = out[0]
    return out


# ----------------------------------------------------------------------------------------- posing
def _env(t, a, b, ramp=0.15):
    if t <= a - ramp or t >= b + ramp:
        return 0.0
    if t < a:
        return ss(0, 1, (t - (a - ramp)) / ramp)
    if t > b:
        return ss(0, 1, ((b + ramp) - t) / ramp)
    return 1.0


def _rot_only(S):
    return S.to_3x3().normalized()


def _A(S, p):
    return S.inverted() @ Vector(p)


def _look_rot(d, up):
    """World delta rotation for the head facing d with up `up` (rest: faces -Y, up +Z)."""
    d = Vector(d).normalized()
    u = (Vector(up) - d * d.dot(up)).normalized()
    y = -d
    x = y.cross(u)
    return frame(x, y)


def seat_torso(p, lean=0.0, roll=0.0, float_=0.0, twist=0.0, crouch=0.0, look=None, up=UP, pitch=0.0, yaw=0.0,
               slump=0.0):
    """Pelvis on the rug (the seat is the rider's origin), spine carrying lean/roll/twist, head level in the world
    (up = world up in rider space) turned by pitch (+ up) / yaw (+ right)."""
    rig = p.rig
    p.pelvis = Vector((0, 0.02, SIT + float_)) - rig.head["pelvis"] + FWD * 0.03 * crouch / 20
    q_p = eul(pitch=PELVIS_TILT + 0.3 * lean + 0.4 * crouch, roll=-0.3 * roll)
    rest = lean * 0.7 + crouch + slump
    sp = tuple(eul(pitch=base + rest * sh, roll=-roll * 0.7 * sh, yaw=twist * sh)
               for base, sh in zip(SPINE, (0.35, 0.35, 0.3)))
    chest = q_p @ sp[0] @ sp[1] @ sp[2]
    lvl = FWD - up * FWD.dot(up)
    lvl = lvl.normalized() if lvl.length > 1e-4 else FWD
    side = lvl.cross(up).normalized()
    d = Quaternion(side, math.radians(pitch)) @ lvl
    d = Quaternion(up, math.radians(-yaw)) @ d
    target = _look_rot(d if look is None else look, up)
    rel = chest.inverted() @ target
    neck = Quaternion().slerp(rel, 0.4)
    head = neck.inverted() @ rel
    p.torso(pelvis=q_p, spine=sp, neck=neck, head=head)


def feet(p, S, smp, out_of=0.0):
    """Feet tucked under the foot rope behind the ears: ankles just behind and outside it, toes down along the
    neck, soles turned in against it, knees forward and out round the head."""
    for s, sx in SIDES:
        rope = _A(S, smp[s])
        ankle = rope + BACK * 0.05 + LEFT * sx * 0.06 + UP * 0.04 + LEFT * sx * out_of * 0.2
        p.leg(s, ankle, knee_dir=FWD * 0.6 + LEFT * sx * 0.7 + UP * 0.25,
              foot=eul(pitch=38, roll=sx * 55, yaw=-sx * 10))


def grip_hand(p, S, smp, lift=0.0):
    """Left fist on the rope grip, knuckles forward and up."""
    if GRIP_LOCAL:                                       # the fist where the grip is at rest, carried by the torso
        g = p.pos("pelvis") + _torso(p) @ GRIP_LOCAL[0] + UP * lift
    else:
        g = _A(S, smp["grip"]) + UP * (0.01 + lift) + LEFT * 0.03
    if "l_dir" not in HINT:                              # the rope bends: the fist may take it at an angle; the
        best = None                                      # most comfortable once per clip (held after, no jitter)
        for cand in GRIP_DIRS:
            q = Pose(p.rig)
            q.D, q.pelvis = dict(p.D), p.pelvis.copy()
            HINT.pop("l", None)
            CHAIN.pop("l", None)
            hold(q, "l", g, cand, curl=0.85)
            cost = A.wrist_comfort("l", *A.wrist_strain(p.rig, q, "l"))
            if best is None or cost < best[0]:
                best = (cost, cand)
        HINT["l_dir"] = best[1]
        HINT.pop("l", None)
        CHAIN.pop("l", None)
    hold(p, "l", g, HINT["l_dir"], curl=0.85)


GRIP_LOCAL = []     # the rope grip in the torso's frame at rest (set by grip_rest): tracking the rope through the
                    # mammoth's head swings asked the arm for poses no wrist could give, and it flipped frame to frame


def _torso(p):
    return p.D["pelvis"].slerp(p.D["spine_03"], 0.5)


def grip_rest(rig, track):
    """GRIP_LOCAL from the mammoth standing (Idle, frame 0)."""
    GRIP_LOCAL.clear()
    smp = _still(track)
    S = smp["S"]
    p = Pose(rig)
    seat_torso(p, up=_rot_only(S).inverted() @ UP, pitch=-6)
    g = _A(S, smp["grip"]) + UP * 0.01 + LEFT * 0.03
    GRIP_LOCAL.append(_torso(p).inverted() @ (g - p.pos("pelvis")))


def spear_rest_target(p, bob=0.0):
    """Spear upright by the right thigh, point up and a little forward: (fist, spear direction), both carried by the
    torso (a leaning rider leans its spear; held upright in the seat's frame the wrist hit its limit in the Stomp
    and the elbow flipped from frame to frame)."""
    pel = p.pos("pelvis")
    q = _torso(p)
    return pel + q @ (RT * 0.24 + FWD * 0.20 + UP * (0.12 + bob)), q @ (UP + FWD * 0.25 + RT * 0.08).normalized()


RAISE = 55.0        # degrees the resting spear arm swings up for the roar


def spear_raised_target(p, shake=0.0, k=1.0):
    """The roar: the resting spear arm swung up about the shoulder (k of RAISE, pumped by `shake`), the fist forward
    at face height, the shaft leaning back over the shoulder. The wrist stays as at rest all the way: a spear held
    upright or forward overhead needs the forearm turned to Humanoid's twist limit, and the solver hopped between
    bad answers -- the spear swirled (2026-10-18)."""
    fist, d = spear_rest_target(p)
    sh = p.pos("upperarm_r")
    q = Quaternion(FWD.cross(UP).normalized(), math.radians(k * (RAISE + 10.0 * shake)))
    return sh + q @ (fist - sh), q @ d


LEVEL_ARM = (RT * 0.3 + BACK * 0.3 - UP * 0.9).normalized()       # the charge's reach (searched)


def spear_level_target(p, reach=1.0):
    """Levelled forward like a lowered lance from the hip (searched for the wrist: twist ~47, no bend; under the
    arm with the forearm along the shaft sat at the limits and cycled between answers every frame)."""
    sh = p.pos("upperarm_r")
    return sh + LEVEL_ARM * 0.46 * reach, (FWD - UP * 0.1 + LEFT * 0.05).normalized()


def spear(p, target):
    hold(p, "r", target[0], target[1], curl=0.75, cone=45.0)


def spear_rest(p, bob=0.0):
    spear(p, spear_rest_target(p, bob))


def _mix_target(a, b, t):
    """Fist positions along, directions slerped: hands are blended by their targets and solved once (blending two
    solved arms bone by bone twisted the wrist past its limits)."""
    da, db = a[1], b[1]
    q = da.rotation_difference(db)
    return a[0].lerp(b[0], t), Quaternion().slerp(q, t) @ da


def accents(clip, t, T):
    a = dict(lean=0.0, crouch=0.0, pitch=0.0, yaw=0.0, roll=0.0, arm='rest', shake=0.0, blend=0.0, twist=0.0,
             slump=0.0, lift=0.0)
    w = 2 * math.pi * t / T
    if clip == "Idle":
        a.update(yaw=16 * math.sin(w), pitch=-6 + 2 * math.sin(2 * w))
    elif clip == "Walk":
        a.update(yaw=5 * math.sin(w), pitch=-6)
    elif clip == "Run":
        a.update(pitch=-5, lean=8, crouch=4)
    elif clip == "Charge":
        a.update(pitch=-2, lean=16, crouch=8, arm='level', blend=1.0)
    elif clip == "Trumpet":
        e = _env(t, 0.45, 1.5, 0.3)
        a.update(lean=-6 * e, pitch=24 * e, arm='raised', blend=e, shake=math.sin(2 * math.pi * 3 * t) * e)
    elif clip == "TuskSwipe":
        e = _env(t, 0.3, 0.7, 0.2)
        a.update(lean=6 * e, crouch=4 * e, pitch=-10, yaw=-25 * e)
    elif clip == "Stomp":
        e = _env(t, 0.35, 1.1, 0.2)
        a.update(lean=14 * e, crouch=10 * e, pitch=-12 * e, lift=-0.01 * e)
    elif clip == "Graze":
        a.update(pitch=-12, yaw=10 * math.sin(w), slump=4)
    elif clip == "Hit":
        e = _env(t, 0.05, 0.2, 0.1)
        a.update(lean=-10 * e, pitch=-8 * e, yaw=-14 * e)
    elif clip == "Sleep":
        a.update(pitch=-30, slump=18 + 2 * math.sin(w), lean=4)
    elif clip == "Wake":
        e = 1 - ss(0.0, 0.6, t / T)
        a.update(pitch=-30 * e + 4 * (1 - e) * math.sin(4 * w), slump=18 * e)
    return a


def pose_frame(rig, smp, st, ac):
    S = smp["S"]
    th, ph, h, up = st
    up = _rot_only(S).inverted() @ UP
    p = Pose(rig)
    seat_torso(p, lean=th + ac['lean'], roll=ph + ac['roll'], float_=h + ac['lift'], crouch=ac['crouch'],
               twist=ac['twist'], up=up, pitch=ac['pitch'], yaw=ac['yaw'], slump=ac['slump'])
    feet(p, S, smp)
    grip_hand(p, S, smp)
    target = spear_rest_target(p)
    if ac['arm'] == 'raised' and ac['blend'] > 1e-3:
        target = spear_raised_target(p, ac['shake'], ac['blend'])      # along the arc, not a straight blend
    elif ac['arm'] != 'rest' and ac['blend'] > 1e-3:
        target = _mix_target(target, spear_level_target(p, 1.0), ac['blend'])
    spear(p, target)
    return p


# ----------------------------------------------------------------------------------------- keying
def _action(name):
    ob = _rider()
    act = bpy.data.actions.get("Hum_" + name) or bpy.data.actions.new("Hum_" + name)
    act.fcurves.clear()
    act.use_fake_user = True
    if ob.animation_data is None:
        ob.animation_data_create()
    ob.animation_data.action = act
    return act


def key_pose(rig, pose, f, prev):
    """hum_anim.key_pose on the rider, the pelvis keyed against the base rest (the Animator's hips)."""
    import hum_helpers
    hum_helpers.drive(pose.D, rig.parent, rig)
    ob = _rider()
    for b in rig.order:
        pb = ob.pose.bones[b]
        pb.rotation_mode = 'QUATERNION'
        par = rig.parent[b]
        Dp = pose.D[par] if par else Quaternion()
        R = rig.rot[b]
        q = R.inverted() @ Dp.inverted() @ pose.D[b] @ R
        if b in prev and prev[b].dot(q) < 0:
            q = -q
        prev[b] = q
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=f, group=b)
    pp = ob.pose.bones["pelvis"]
    pp.location = rig.rot["pelvis"].inverted() @ (rig.head["pelvis"] + pose.pelvis - rig.base_head["pelvis"])
    pp.keyframe_insert("location", frame=f, group="pelvis")


def _linear(act):
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


def build_synced(clip, track, rig):
    if not GRIP_LOCAL:
        grip_rest(rig, track)
    samples = sample_clip(clip, track)
    loop = clip in LOOPS
    states = simulate(samples, loop)
    f0 = int(bpy.data.actions["Mammoth_" + clip].frame_range[0])
    T = (len(samples) - 1) / FPS
    name = PREFIX + clip
    act = _action(name)
    prev = {}
    HINT.clear()
    CHAIN.clear()
    scn = bpy.context.scene
    def pose_at(i):
        t = i / FPS
        smp, st = samples[i], states[i]
        return pose_death(rig, smp, st, t, samples) if clip == "Death" else pose_frame(rig, smp, st, accents(clip, t, T))
    two_pass(len(samples), pose_at, lambda i, p: key_pose(rig, p, f0 + i, prev), loop)
    act.frame_range = (f0, f0 + len(samples) - 1)
    act.use_frame_range = True
    _linear(act)
    A.CLIPS[name] = (len(samples) - 1, loop, True)
    return act


# ----------------------------------------------------------------------------------------- off the mammoth
def _lying(head, e):
    head = Vector(head).normalized()
    y = -UP
    R1 = Matrix((y.cross(head), y, head)).transposed()
    return Quaternion().slerp(R1.to_quaternion(), e)


def pose_off(rig, S, hip_w, Rw, tuck, k_lie, sprawl=1.0):
    """A pose off the seat, given in the world: the pelvis at hip_w (world) turned by Rw (world delta), limbs
    flung (tuck 0..1 knees drawn up) or lying (k_lie)."""
    Sr = _rot_only(S)
    Si = S.inverted()
    sc = S.to_scale()[0]
    p = Pose(rig)
    Ra = (Sr.inverted() @ Rw.to_matrix()).to_quaternion()       # rider-space delta
    pel_a = Si @ hip_w
    p.pelvis = pel_a - rig.head["pelvis"]
    bend = 10 * (1 - k_lie)
    p.torso(pelvis=Ra, spine=(eul(pitch=bend), eul(pitch=bend * 0.8), eul(pitch=bend * 0.6)),
            neck=eul(pitch=-8 * k_lie), head=eul(pitch=-10 * k_lie))
    for s, sx in SIDES:
        hip = p.pos(f"thigh_{s}")
        down = Ra @ Vector((sx * 0.20, -0.10 - 0.25 * tuck, -0.85 + 0.40 * tuck))
        ankle = hip + down
        ground_z = (Si @ Vector((0, 0, 0.09))).z
        ankle.z = max(ankle.z, ground_z) if k_lie > 0.5 else ankle.z
        p.leg(s, ankle, knee_dir=Ra @ (FWD * 0.8 + UP * 0.2 * (1 - k_lie)), foot=Ra)
        sh = p.pos(f"upperarm_{s}")
        # arms bent and flailing in the air, flopped out beside the body once down (never a straight T)
        fist = sh + Ra @ Vector((sx * (0.30 + 0.12 * k_lie), -0.16 * (1 - k_lie) - 0.05, -0.30 + 0.12 * (1 - k_lie)))
        grip = Ra @ (LEFT * sx * 0.6 + UP * 0.8 + FWD * 0.6 * (1 - k_lie)) if s == "r" else Ra @ FWD
        hold(p, s, fist, grip, Ra @ (UP * 0.2 + LEFT * sx), Ra @ Vector((sx * 0.6, 0.4, -0.3)),
             curl=0.75 if s == "r" else 0.35, hint=s + "_off")               # the spear swings down flat with the arm
    return p


def pose_death(rig, smp, st, t, samples):
    """The mammoth sinks onto its belly and slumps to its right: the driver clings while it goes down, then slides
    off the high left side and lands on its back beside the mammoth."""
    S = smp["S"]
    t0, t1 = 1.55, 2.25
    def cling(k):
        ac = dict(lean=10 * k, crouch=8 * k, pitch=-14 * k, yaw=10 * k, roll=-6 * k, arm='rest', shake=0.0, blend=0.0,
                  twist=0.0, slump=0.0, lift=0.0)
        return pose_frame(rig, smp, st, ac)
    if t <= t0:
        return cling(ss(0.0, 1.0, t / t0))
    i0 = int(round(t0 * FPS))
    S0 = samples[i0]["S"]
    hip0 = S0 @ (Vector((0, 0.02, SIT)))
    land = Vector((1.95, -1.15, 0.14))
    u = min((t - t0) / (t1 - t0), 1.0)
    e = ss(0.0, 1.0, u)
    pos = hip0.lerp(land, e)
    pos.z = hip0.z + (land.z - hip0.z) * (u * u) + 0.15 * math.sin(math.pi * u)   # falling, accelerating
    Rw = _lying(LEFT + FWD * 0.3, e)
    off = pose_off(rig, S, pos, Rw, tuck=math.sin(math.pi * u), k_lie=e)
    w = ss(0.0, 1.0, (t - t0) / BLEND_OFF)
    return off if w >= 1.0 else _blend_pose(rig, cling(1.0), off, w)     # letting go, not a snap


BLEND_OFF = 0.2        # seconds the clinging pose fades into the fall (the arms snapped from grip and spear)


def _blend_pose(rig, a, b, w):
    """A pose between two: every bone's world turn slerped, the pelvis along."""
    p = Pose(rig)
    for n in a.D:
        q1 = b.D[n] if a.D[n].dot(b.D[n]) >= 0 else -b.D[n]
        p.D[n] = a.D[n].slerp(q1, w)
    p.pelvis = a.pelvis.lerp(b.pelvis, w)
    return p


# ----------------------------------------------------------------------------------------- own clips
OWN_EVENTS = {"Thrust": {"hit": 16, "end": 40}, "Flinch": {"end": 15}, "Fall": {"ground": 44, "end": 72}}


def _still(track):
    mount_clip("Idle")
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    return dict(S=_rider().matrix_world.copy(), **track.sample())


def _base(rig, smp, **kw):
    S = smp["S"]
    up = _rot_only(S).inverted() @ UP
    p = Pose(rig)
    seat_torso(p, up=up, **kw)
    feet(p, S, smp)
    grip_hand(p, S, smp)
    return p


THRUST_DIR = (FWD * 0.80 + RT * 0.40 - UP * 0.45).normalized()     # forward and down at a man off the right shoulder
JAB_ARM = (FWD * 0.25 + RT * 0.55 - UP * 0.60).normalized()        # the arm's reach: the shaft crosses it at ~50 deg
BODY0 = dict(lean=0.0, twist=0.0, roll=0.0, crouch=0.0, pitch=-6.0, yaw=0.0)


COCK_ARM = (RT * 0.41 + BACK * 0.41 - UP * 0.82).normalized()     # searched: the comfiest reach with the spear on
                                                                    # THRUST_DIR (wrist twist ~82, no bend)


def thrust_key(stage):
    """Underhand jab, a straight push along the shaft (the hand keeps its turn all the way: no swirl): cocked low by
    the right hip with the point already on the man below, driven 24 cm along the line, pulled back with the point
    lifting, the spear up. -> (body, target(p))"""
    d = THRUST_DIR
    def cock(p):
        return p.pos("upperarm_r") + COCK_ARM * 0.42
    if stage == 'ready':
        return dict(BODY0), spear_rest_target
    if stage == 'cock':
        return dict(lean=4, twist=-10, roll=8, crouch=2, pitch=-26, yaw=30), lambda p: (cock(p), d)
    if stage in ('jab', 'hold'):
        k = 1.0 if stage == 'hold' else 0.0
        return dict(lean=14 + 2 * k, twist=18, roll=16, crouch=4, pitch=-35, yaw=30),             lambda p: (cock(p) + d * (0.24 - 0.02 * k), d)
    return dict(lean=4, twist=-4, roll=6, crouch=0, pitch=-16, yaw=22),         lambda p: (cock(p) + UP * 0.08, (d + UP * 0.8).normalized())


def flinch_key(k):
    return dict(lean=-12 * k, twist=-10 * k, roll=-8 * k, crouch=0, pitch=-6 - 12 * k, yaw=-20 * k),         lambda p: spear_rest_target(p, 0.05 * k)


def _keyed(name, keys, rig, track):
    """Own clips: every frame between the keys has its body settings and its hand's target (fist, spear line)
    blended (eased), then solved: keys alone left Blender's curves to turn the hand between them (the spear swirled
    before the jab), and blending solved arms bone by bone bent the wrist past Humanoid's limits."""
    if not GRIP_LOCAL:
        grip_rest(rig, track)
    smp = _still(track)
    act = _action(PREFIX + name)
    HINT.clear()
    CHAIN.clear()
    data = []
    for f, kfn, arg in keys:
        body, tfn = kfn(arg)
        p = _base(rig, smp, **body)
        data.append((f, body, tfn(p)))
    prev = {}
    frames = []
    for i in range(len(data) - 1):
        (f0, b0, t0), (f1, b1, t1) = data[i], data[i + 1]
        last = i == len(data) - 2
        for f in range(f0, f1 + (1 if last else 0)):
            frames.append((f, b0, b1, t0, t1, ss(0.0, 1.0, (f - f0) / (f1 - f0))))

    def pose_at(i):
        f, b0, b1, t0, t1, u = frames[i]
        p = _base(rig, smp, **{k: b0[k] + (b1[k] - b0[k]) * u for k in b0})
        spear(p, _mix_target(t0, t1, u))
        return p
    two_pass(len(frames), pose_at, lambda i, p: key_pose(rig, p, frames[i][0], prev), False)
    act.frame_range = (keys[0][0], keys[-1][0])
    act.use_frame_range = True
    _linear(act)
    A.CLIPS[PREFIX + name] = (keys[-1][0], False, True)
    return act


def build_thrust(rig, track):
    e = OWN_EVENTS["Thrust"]
    return _keyed("Thrust", [(0, thrust_key, 'ready'), (10, thrust_key, 'cock'), (e['hit'], thrust_key, 'jab'),
                             (e['hit'] + 5, thrust_key, 'hold'), (e['hit'] + 13, thrust_key, 'pull'),
                             (e['end'], thrust_key, 'ready')], rig, track)


def build_flinch(rig, track):
    return _keyed("Flinch", [(0, flinch_key, 0.0), (3, flinch_key, 1.0), (7, flinch_key, 0.7), (15, flinch_key, 0.0)],
                  rig, track)


def build_fall(rig, track):
    """Killed on the neck (the mammoth standing): jerks back, slumps, slides off the left side, falls ~3 m, lies."""
    smp = _still(track)
    S = smp["S"]
    g, end = OWN_EVENTS["Fall"]["ground"], OWN_EVENTS["Fall"]["end"]
    hip0 = S @ Vector((0, 0.02, SIT))
    edge = S @ Vector((0.55, 0.0, -0.30))                # off the side of the neck
    land = Vector((1.45, -1.30, 0.14))
    act = _action(PREFIX + "Fall")
    prev = {}
    HINT.clear()
    CHAIN.clear()

    def pose_at(f):
        if f <= 12:
            k = ss(0, 1, f / 12)
            p = _base(rig, smp, lean=-12 + 40 * k, roll=6 * k, pitch=-30 * k)
            spear_rest(p, bob=-0.06 * k)
        elif f <= 22:                                    # sliding off the left side
            u = (f - 12) / 10
            pos = hip0.lerp(edge, ss(0, 1, u))
            p = pose_off(rig, S, pos, _lying(LEFT, 0.35 * u), tuck=0.4 * u, k_lie=0.0)
            w = ss(0.0, 1.0, (f - 12) / (BLEND_OFF * FPS))
            if w < 1.0:                                  # letting go of grip and spear, not a snap
                slump = _base(rig, smp, lean=28, roll=6, pitch=-30)
                spear_rest(slump, bob=-0.06)
                p = _blend_pose(rig, slump, p, w)
        else:                                            # the drop: free fall to the ground, rolling onto the back
            u = min((f - 22) / (g - 22), 1.0)
            pos = edge.lerp(land, u)
            pos.z = edge.z + (land.z - edge.z) * u * u
            p = pose_off(rig, S, pos, _lying(LEFT + FWD * 0.3, 0.35 + 0.65 * ss(0, 1, u)), tuck=math.sin(math.pi * u) * 0.6,
                         k_lie=ss(0.6, 1.0, u))
        return p
    two_pass(end + 1, pose_at, lambda f, p: key_pose(rig, p, f, prev), False)
    act.frame_range = (0, end)
    act.use_frame_range = True
    _linear(act)
    A.CLIPS[PREFIX + "Fall"] = (end, False, True)
    return act


# ----------------------------------------------------------------------------------------- all, view, export
SYNCED = ("Idle", "Walk", "Run", "Charge", "Trumpet", "TuskSwipe", "Stomp", "Graze", "Hit", "Death", "Sleep", "Wake")


def build_all():
    track = Track()
    rig = OrcRig(ob_name=RIDER)
    out = [build_synced(c, track, rig).name for c in SYNCED]
    out += [build_thrust(rig, track).name, build_flinch(rig, track).name, build_fall(rig, track).name]
    return out


def names():
    return [a.name[4:] for a in bpy.data.actions if a.name.startswith("Hum_" + PREFIX)]


def use(name, frame=None):
    act = bpy.data.actions["Hum_" + name]
    r = _rider()
    if r.animation_data is None:
        r.animation_data_create()
    r.animation_data.action = act
    clip = name[len(PREFIX):]
    mount_clip(clip if ("Mammoth_" + clip) in bpy.data.actions else "Idle")
    scn = _scene()
    scn.frame_start, scn.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    scn.frame_set(int(act.frame_range[0]) if frame is None else frame)


def export_clips():
    """Human@MammothDriver_*.fbx through hum_anim.export_clips (from HumanRig: same bones, rest skeleton)."""
    for n in names():
        act = bpy.data.actions["Hum_" + n]
        A.CLIPS[n] = (int(act.frame_range[1] - act.frame_range[0]), n[len(PREFIX):] in LOOPS, True)
    return A.export_clips(names=names())


# ----------------------------------------------------------------------------------------- review renders
VIEWS = {"side": Vector((-5.0, -0.2, 0.6)), "front34": Vector((-3.4, -4.2, 1.0)), "close": Vector((-2.2, -1.2, 0.8)),
         "front": Vector((-0.4, -5.5, 0.6)), "wide": Vector((1.0, -9.0, 2.5))}


def _cam(view):
    name = "CAM_Drv_" + view
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        _scene().collection.objects.link(cam)
    cam.data.lens = 50
    return cam


def render_sheet(name, frames, views=("side", "front34"), res=380, follow=True, height=2.9):
    import hum_scene
    scn = _scene()
    scn.render.engine = 'BLENDER_WORKBENCH'
    sh = scn.display.shading
    sh.light, sh.color_type = 'STUDIO', 'OBJECT'
    paths = []
    for v in views:
        cam = _cam(v)
        for f in frames:
            scn.frame_set(f)
            bpy.context.view_layer.update()
            tgt = _rider().matrix_world.translation.copy() if follow else Vector((0, -1.4, 2.0))
            tgt.z = height
            cam.location = tgt + VIEWS[v]
            cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
            paths.append(hum_scene.render(scn, cam, os.path.join(hum_scene.RENDERS, "_tmp", f"drv_{name}_{v}_{f}.png"), res))
    return hum_scene.sheet(paths, len(frames), os.path.join(hum_scene.RENDERS, "ride", name + ".png"))
