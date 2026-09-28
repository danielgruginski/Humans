"""Our own animation clips for the humans (Unity Humanoid, in place), made procedurally on HumanRig.

Clips (30 fps; `CLIPS` has lengths, loops and Unity root settings):
    Idle, Idle_Look, Idle_Shift      loops: breathing, looking around, shifting weight
    Walk (1.35 m/s), Run (3.6 m/s)    in-place loops: move the character at that speed and the feet don't slide
    Turn_L90, Turn_R90                stepping turns; the hips' yaw becomes Unity root rotation (root motion)
    Chop, Hammer                      work loops (axe two-handed at a log, hammer at an anvil; tool in the right hand)
    Sit_Down, Sit_Idle, Stand_Up      onto / on / off a 46 cm seat
    Death                             falls backward, ends lying (hold the last frame)

Method. A pose is a world-space rotation per bone relative to its rest orientation (armature space) plus the
pelvis' offset. Positions follow by forward kinematics from the rest offsets; legs (and hands holding tools)
are placed by analytic two-bone IK with a pole direction. Every clip is a function of time, keyed every frame
as local quaternions: q_b = R_b^-1 D_parent^-1 D_b R_b (R = rest rotation, D = world delta). Only rotations
(and the pelvis location) are keyed: the rig's bone translations belong to the body builds, and Unity's
Humanoid retargeting uses rotations only - so one clip set serves every build and both sexes.
Axes: +Z up, front -Y, the character's left +X.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

RIG = "HumanRig"
FPS = 30
UP, FWD, LEFT = Vector((0, 0, 1)), Vector((0, -1, 0)), Vector((1, 0, 0))
FINGERS = ("thumb", "index", "middle", "ring", "pinky")

# Hand poses, degrees of flexion per joint (knuckle, middle, tip) on top of the rest curl. Relaxed: a soft
# cascade, the pinky curled most (an open hand hanging at the side); fist: knuckles near 90, the tips tucked.
# A single flex per segment (the old way) left the knuckles flat and hooked the tips: a claw.
HAND_RELAXED = {"index": (10, 20, 10), "middle": (14, 26, 12), "ring": (18, 30, 14), "pinky": (22, 34, 16),
                "thumb": (0, 6, 10)}
HAND_FIST = {"index": (72, 90, 42), "middle": (78, 92, 44), "ring": (80, 92, 42), "pinky": (82, 90, 40),
             "thumb": (18, 34, 40)}              # (tighter drives the fingertips out through the back of the hand)
# the thumb's root (thumb_01) also swings toward the index in the palm plane and in or out of the palm: the rest
# thumb is already opposed, so a relaxed thumb comes back out of the palm and lies alongside the index
THUMB_ROOT = {"relaxed": (14.0, -14.0), "fist": (4.0, 6.0)}       # (toward the index, into the palm)
HAND_SPREAD = {"index": 4.0, "middle": 0.0, "ring": 3.0, "pinky": 7.0}    # relaxed fan, away from the middle finger

# name: (frames, loop, root rotation baked into the pose?)   (turns keep their yaw as root motion)
CLIPS = {
    "Idle": (120, True, True), "Idle_Look": (150, True, True), "Idle_Shift": (180, True, True),
    "Walk": (30, True, True), "Run": (22, True, True),
    "Turn_L90": (30, False, False), "Turn_R90": (30, False, False),
    "Chop": (48, True, True), "Hammer": (30, True, True),
    "Sit_Down": (36, False, True), "Sit_Idle": (120, True, True), "Stand_Up": (36, False, True),
    "Death": (54, False, True),
}
SPEED = {"Walk": 1.35, "Run": 3.6}


def ss(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0) if b != a else float(x >= a)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def spline(K, t):
    """Evaluate key poses K = [(time, values, kind), ...] at t (a loop: the last key repeats the first, t in
    [0, 1]) by cubic Hermite segments, so the motion flows through keys instead of stopping at each one.
    kind sets the velocity at the key: "flow" passes through (Catmull-Rom tangent over the neighbours), "stop"
    eases in and out (a reversal, the top of a swing), "hit" arrives at full speed and stops dead (an impact)."""
    n = len(K) - 1                                              # K[n] repeats K[0]
    T = [k[0] for k in K]
    P = [np.asarray(k[1], float) for k in K]

    def tangents(i):
        """(incoming, outgoing) velocity at key i, per unit t."""
        kind = K[i][2]
        if kind == "stop":
            z = np.zeros_like(P[i])
            return z, z
        ip = (i - 1) % n if i != 0 else n - 1                   # neighbours round the loop
        inx = (i + 1) if i < n else 1
        tp = T[ip] - (1.0 if ip >= i else 0.0)
        tn = T[inx] + (1.0 if inx <= i and i == n else 0.0)
        if kind == "hit":
            m = 2.0 * (P[i] - P[ip]) / (T[i] - tp)              # accelerating all the way in
            return m, np.zeros_like(P[i])
        m = (P[inx] - P[ip]) / (tn - tp)
        return m, m

    for i in range(n):
        if T[i] <= t <= T[i + 1]:
            h = T[i + 1] - T[i]
            u = (t - T[i]) / h
            m0 = tangents(i)[1]
            m1 = tangents(i + 1)[0]
            h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
            h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
            return h00 * P[i] + h10 * h * m0 + h01 * P[i + 1] + h11 * h * m1
    return P[0]


def eul(pitch=0.0, roll=0.0, yaw=0.0):
    """World rotation from degrees: pitch about +X (positive leans forward), roll about -Y (positive tips toward
    the character's left), yaw about +Z (positive turns to the character's left)."""
    q = Quaternion(UP, math.radians(yaw))
    q = q @ Quaternion(Vector((0, -1, 0)), math.radians(roll))
    return q @ Quaternion(LEFT, math.radians(pitch))


def frame(x, y):
    """Rotation whose columns are x, y (made orthogonal) and x cross y."""
    x = x.normalized()
    y = (y - x * x.dot(y)).normalized()
    return Matrix((x, y, x.cross(y))).transposed().to_quaternion()


# ------------------------------------------------------------------------------------------ rig and pose
class Rig:
    def __init__(self):
        self.ob = bpy.data.objects[RIG]
        bones = self.ob.data.bones
        depth = lambda b: 0 if b.parent is None else 1 + depth(b.parent)
        self.order = [b.name for b in sorted(bones, key=depth)]
        self.parent = {b.name: b.parent.name if b.parent else None for b in bones}
        self.head = {b.name: b.head_local.copy() for b in bones}
        self.tail = {b.name: b.tail_local.copy() for b in bones}
        self.rot = {b.name: b.matrix_local.to_quaternion() for b in bones}
        # the back of each hand: palm plane from the finger roots, pointing away from the body
        self.dorsal = {}
        for s, sx in (("l", 1.0), ("r", -1.0)):
            h = self.head[f"hand_{s}"]
            n = (self.head[f"index_01_{s}"] - h).cross(self.head[f"pinky_01_{s}"] - h).normalized()
            self.dorsal[s] = n if n.x * sx > 0 else -n
        # a held handle: it runs through the fist from the little finger's side out past the index/thumb
        # (grip axis) through the hole the curled fingers make: fitted as the circle through the middle finger's
        # knuckle, last joint and tip at GRIP_CURL (2.6 cm round - a 3.2 cm handle plus the finger), whose centre
        # is 1.6 cm back from the middle knuckle and 1.6 cm into the palm (fist centre, from the wrist)
        self.arm_len = (self.head["lowerarm_l"] - self.head["upperarm_l"]).length +             (self.head["hand_l"] - self.head["lowerarm_l"]).length
        self.grip_axis, self.fist, self.strike_axis = {}, {}, {}
        for s in "lr":
            self.grip_axis[s] = (self.head[f"index_01_{s}"] - self.head[f"pinky_01_{s}"]).normalized()
            self.fist[s] = (self.head[f"middle_01_{s}"] - self.head[f"hand_{s}"])                 - self.dir(f"middle_01_{s}") * 0.016 - self.dorsal[s] * 0.016
            # a tool's striking face points where the knuckles do (wrist -> middle knuckle, square to the handle)
            self.strike_axis[s] = self.head[f"middle_01_{s}"] - self.head[f"hand_{s}"]
        # per-segment flex axes (rest space). Fingers fold toward the palm; the thumb folds across it, toward
        # the index's middle joint (where a fist's thumb ends up)
        self.flex, self.fan = {}, {}
        for s in "lr":
            palm = -self.dorsal[s]
            aim = self.head[f"index_02_{s}"]
            mid = self.head[f"middle_01_{s}"]
            for f in FINGERS:
                for i in (1, 2, 3):
                    b = f"{f}_0{i}_{s}"
                    if b not in self.head:
                        continue
                    d = self.dir(b)
                    if f == "thumb":
                        to = aim - self.head[b]
                        to = (to - d * d.dot(to)).normalized()
                        to = (to + palm * 0.6).normalized()
                    else:
                        to = palm
                    self.flex[b] = d.cross(to).normalized()
                if f == "thumb":
                    b = f"thumb_01_{s}"
                    d = self.dir(b)
                    side = aim - self.head[b]
                    side = side - self.dorsal[s] * self.dorsal[s].dot(side)
                    side = (side - d * d.dot(side)).normalized()
                    self.thumb_add = getattr(self, "thumb_add", {})
                    self.thumb_opp = getattr(self, "thumb_opp", {})
                    self.thumb_add[s] = d.cross(side).normalized()
                    self.thumb_opp[s] = d.cross(palm).normalized()
                if f not in ("thumb", "middle"):
                    b = f"{f}_01_{s}"
                    side = self.head[b] - mid
                    side = side - self.dorsal[s] * self.dorsal[s].dot(side)
                    self.fan[b] = self.dir(b).cross(side.normalized()).normalized()

    def dir(self, b):
        return (self.tail[b] - self.head[b]).normalized()


class Pose:
    def __init__(self, rig):
        self.rig = rig
        self.D = {b: Quaternion() for b in rig.order}
        self.pelvis = Vector()
        self.elbow = {}                          # elbow angles the grip solver chose (_handle_hands)

    def pos(self, b):
        """World position of bone b's head under this pose (FK)."""
        r = self.rig
        p = r.parent[b]
        if b == "pelvis":
            return r.head[b] + self.pelvis
        if p is None:
            return r.head[b].copy()
        return self.pos(p) + self.D[p] @ (r.head[b] - r.head[p])

    # -- torso
    def torso(self, pelvis=Quaternion(), spine=(Quaternion(), Quaternion(), Quaternion()), neck=Quaternion(),
              head=Quaternion()):
        """Chain rotations, each relative to the one below: pelvis, spine_01..03, neck, head."""
        q = pelvis
        self.D["pelvis"] = q
        for b, s in zip(("spine_01", "spine_02", "spine_03"), spine):
            q = q @ s
            self.D[b] = q
        self.D["neck_01"] = q @ neck
        self.D["head"] = q @ neck @ head
        for s in "lr":
            self.D[f"clavicle_{s}"] = self.D["spine_03"]

    # -- legs
    def leg(self, s, ankle, knee_dir=FWD, foot=Quaternion(), toe=0.0):
        """Two-bone IK: the ankle (foot head) at `ankle`, the knee toward knee_dir; the foot turned by `foot`
        (world rotation relative to rest), the toes bent up by `toe` degrees at the ball."""
        r = self.rig
        t, c, f, bl = f"thigh_{s}", f"calf_{s}", f"foot_{s}", f"ball_{s}"
        hip = self.pos(t)
        L1 = (r.head[c] - r.head[t]).length
        L2 = (r.head[f] - r.head[c]).length
        d = ankle - hip
        dist = min(max(d.length, 0.05), (L1 + L2) * 0.9995)
        dn = d.normalized()
        pole = (knee_dir - dn * dn.dot(knee_dir)).normalized()
        ca = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
        sa = math.sqrt(max(0.0, 1 - ca * ca))
        knee = hip + dn * L1 * ca + pole * L1 * sa
        foot_pos = hip + dn * dist
        rpole = (FWD - r.dir(t) * r.dir(t).dot(FWD))
        self.D[t] = frame((knee - hip), pole) @ frame(r.head[c] - r.head[t], rpole).inverted()
        rpole2 = (FWD - r.dir(c) * r.dir(c).dot(FWD))
        self.D[c] = frame((foot_pos - knee), pole) @ frame(r.head[f] - r.head[c], rpole2).inverted()
        self.D[f] = foot
        lat = (foot @ LEFT)
        self.D[bl] = Quaternion(lat, math.radians(-toe)) @ foot

    # -- arms
    def arm(self, s, down=75.0, out=10.0, swing=0.0, elbow=15.0, twist=0.0, wrist=0.0, clav=0.0):
        """FK in the chest's frame: the upper arm `down` degrees below horizontal (rest: 49), `out` from the
        body side, swung forward by `swing`; the elbow flexed to `elbow` degrees; `clav` lifts the shoulder."""
        r = self.rig
        sx = 1.0 if s == "l" else -1.0
        chest = self.D["spine_03"]
        cl = Quaternion(Vector((0, -1, 0)), math.radians(sx * clav))
        self.D[f"clavicle_{s}"] = chest @ cl
        sw = math.radians(swing)
        o = math.radians(out)
        # hanging direction: `down` below horizontal (out to the side by its cosine), `out` adds a little more,
        # swung forward/back
        dirv = Vector((sx * (math.cos(math.radians(down)) + 0.35 * math.sin(o)),
                       -math.sin(sw) * math.sin(math.radians(down)),
                       -math.cos(sw) * math.sin(math.radians(down))))
        ua = f"upperarm_{s}"
        q = r.dir(ua).rotation_difference(dirv.normalized())
        q = Quaternion(dirv.normalized(), math.radians(sx * twist)) @ q
        self.D[ua] = chest @ cl @ q
        la = f"lowerarm_{s}"
        rest_flex = math.degrees(r.dir(ua).angle(r.dir(la)))
        hinge = r.dir(ua).cross(r.dir(la)).normalized()
        self.D[la] = self.D[ua] @ Quaternion(hinge, math.radians(elbow - rest_flex))
        hd = f"hand_{s}"
        self.D[hd] = self.D[la] @ Quaternion(r.dorsal[s].cross(r.dir(hd)).normalized(), math.radians(wrist))

    def arm_ik(self, s, target, elbow_dir, hand=None, clav=0.0):
        """Two-bone IK for the arm: the wrist (hand head) at `target`, the elbow toward elbow_dir; the hand
        turned by `hand` (world rotation relative to rest) or following the forearm; `clav` shrugs the shoulder
        up first (degrees; reaching overhead lifts the collarbone)."""
        r = self.rig
        ua, la, hd = f"upperarm_{s}", f"lowerarm_{s}", f"hand_{s}"
        if clav:
            sx = 1.0 if s == "l" else -1.0
            self.D[f"clavicle_{s}"] = self.D["spine_03"] @ Quaternion(Vector((0, -1, 0)), math.radians(sx * clav))
        sh = self.pos(ua)
        L1 = (r.head[la] - r.head[ua]).length
        L2 = (r.head[hd] - r.head[la]).length
        d = target - sh
        dist = min(max(d.length, 0.05), (L1 + L2) * 0.999)
        dn = d.normalized()
        pole = (elbow_dir - dn * dn.dot(elbow_dir)).normalized()
        ca = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
        sa = math.sqrt(max(0.0, 1 - ca * ca))
        el = sh + dn * L1 * ca + pole * L1 * sa
        wr = sh + dn * dist
        rest_pole = r.dir(la) - r.dir(ua) * r.dir(ua).dot(r.dir(la))      # the rest elbow bend direction
        rest_pole = -rest_pole
        self.D[ua] = frame(el - sh, pole) @ frame(r.head[la] - r.head[ua], rest_pole).inverted()
        self.D[la] = frame(wr - el, pole) @ frame(r.head[hd] - r.head[la], rest_pole).inverted()
        self.D[hd] = hand if hand is not None else self.D[la]

    # -- hands
    def fingers(self, s, fist=0.0, spread=1.0):
        """Blend the hand from relaxed (0) to a clenched fist (1); `spread` scales the relaxed fan."""
        r = self.rig
        base = self.D[f"hand_{s}"]
        fan = spread * (1.0 - fist)
        for f in FINGERS:
            q = base
            for i in (1, 2, 3):
                b = f"{f}_0{i}_{s}"
                if b not in r.head:
                    continue
                ang = lerp(HAND_RELAXED[f][i - 1], HAND_FIST[f][i - 1], fist)
                if b in r.fan:
                    q = q @ Quaternion(r.fan[b], math.radians(HAND_SPREAD[f] * fan))
                if f == "thumb" and i == 1:
                    add = lerp(THUMB_ROOT["relaxed"][0], THUMB_ROOT["fist"][0], fist)
                    opp = lerp(THUMB_ROOT["relaxed"][1], THUMB_ROOT["fist"][1], fist)
                    q = q @ Quaternion(r.thumb_add[s], math.radians(add)) @ Quaternion(r.thumb_opp[s], math.radians(opp))
                q = q @ Quaternion(r.flex[b], math.radians(ang))
                self.D[b] = q


# ------------------------------------------------------------------------------------------ keying
def _action(name):
    ob = bpy.data.objects[RIG]
    act = bpy.data.actions.get("Hum_" + name) or bpy.data.actions.new("Hum_" + name)
    act.fcurves.clear()
    act.use_fake_user = True
    if ob.animation_data is None:
        ob.animation_data_create()
    ob.animation_data.action = act
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    return act


def key_pose(rig, pose, frame_no, prev):
    ob = rig.ob
    for b in rig.order:
        pb = ob.pose.bones[b]
        p = rig.parent[b]
        Dp = pose.D[p] if p else Quaternion()
        R = rig.rot[b]
        q = R.inverted() @ Dp.inverted() @ pose.D[b] @ R
        if b in prev and prev[b].dot(q) < 0:
            q = -q
        prev[b] = q
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame_no, group=b)
    pp = ob.pose.bones["pelvis"]
    pp.location = rig.rot["pelvis"].inverted() @ pose.pelvis
    pp.keyframe_insert("location", frame=frame_no, group="pelvis")


def author(name, fn):
    """Key clip `name`: fn(rig, t) -> Pose for t in [0, 1] over CLIPS[name] frames (loops close on frame 0)."""
    rig = Rig()
    n, loop, _ = CLIPS[name]
    act = _action(name)
    prev = {}
    import hum_helpers
    for f in range(n + 1):
        pose = fn(rig, (f % n) / n if loop else f / n)
        hum_helpers.drive(pose.D, rig.parent, rig)       # previews only: Unity drives them at runtime
        key_pose(rig, pose, f, prev)
    act.frame_range = (0, n)
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    return act


# ------------------------------------------------------------------------------------------ building blocks
STANCE_X = 0.10          # feet 20 cm apart


def _rest_ankle(rig, s):
    return rig.head[f"foot_{s}"].copy()


def _stand(rig, t, breathe=1.0, sway=0.0, bend=0.012, arms=(83, 5, 0, 14), look=0.0, nod=0.0):
    """A relaxed standing pose (feet planted, soft knees, arms hanging) with breathing and sway."""
    p = Pose(rig)
    b = math.sin(2 * math.pi * t) * breathe
    p.pelvis = Vector((sway, 0.0, -bend + 0.002 * b))
    p.torso(pelvis=eul(roll=-sway * 60), spine=(eul(pitch=1 - 0.4 * b), eul(pitch=0.5 * b), eul(pitch=-1.2 * b, roll=sway * 40)),
            neck=eul(pitch=2), head=eul(pitch=-2 + nod, yaw=look))
    for s, sx in (("l", 1), ("r", -1)):
        a = _rest_ankle(rig, s)
        p.leg(s, Vector((sx * STANCE_X, a.y, a.z)), knee_dir=FWD + LEFT * sx * 0.15,
              foot=eul(yaw=sx * 8))
        down, out, swing, elbow = arms
        p.arm(s, down=down, out=out + 1.5 * b, swing=swing, elbow=elbow + 2 * b, clav=0.8 * b)
        p.fingers(s, 0.0)
    return p


def _gait(rig, t, speed, period, stance, lift, bob, lean, arm_swing, elbow, run=False):
    """In-place locomotion: each foot slides back under the body at `speed` during `stance` of the cycle and
    swings forward otherwise; the pelvis bobs, sways and twists, the arms swing against the legs."""
    p = Pose(rig)
    D = speed * stance * period                               # distance a foot travels on the ground
    phase = t
    tw = 7 if not run else 10
    yaw = tw * math.sin(2 * math.pi * phase)                  # left hip forward while the left foot leads
    sway = (0.022 if not run else 0.012) * math.sin(2 * math.pi * phase)
    if run:
        dz = -0.035 + bob * math.cos(4 * math.pi * (phase - stance / 2 + 0.25))
    else:
        dz = -0.02 + bob * math.cos(4 * math.pi * (phase - stance / 2))
    p.pelvis = Vector((sway, 0.0, dz))
    p.torso(pelvis=eul(yaw=yaw, roll=-sway * 90, pitch=lean * 0.3),
            spine=(eul(yaw=-yaw * 0.5, pitch=lean * 0.25), eul(yaw=-yaw * 0.45, pitch=lean * 0.25),
                   eul(yaw=-yaw * 0.45, pitch=lean * 0.2, roll=sway * 60)),
            neck=eul(pitch=-lean * 0.35), head=eul(pitch=-lean * 0.35))
    for s, sx, off in (("l", 1, 0.0), ("r", -1, 0.5)):
        ph = (phase + off) % 1.0
        a = _rest_ankle(rig, s)
        y_front, y_back = a.y - D / 2 - (0.02 if run else 0.0), a.y + D / 2
        if ph < stance:                                        # on the ground, sliding back
            u = ph / stance
            y = lerp(y_front, y_back, u)
            z = a.z
            pitch = lerp(-12 if not run else -4, 0, ss(0.0, 0.25, u)) + lerp(0, 35 if not run else 45, ss(0.6, 1.0, u))
            toe = lerp(0, 35 if not run else 45, ss(0.6, 1.0, u))
            z += 0.13 * math.sin(math.radians(max(pitch, 0))) * 0.9
        else:                                                  # swinging forward
            u = (ph - stance) / (1 - stance)
            e = u * u * (3 - 2 * u)
            y = lerp(y_back, y_front, e)
            z = a.z + lift * math.sin(math.pi * u) ** (0.8 if run else 1.0)
            pitch = lerp(35 if not run else 45, -12 if not run else -8, ss(0.0, 0.8, u))
            toe = lerp(35, 0, ss(0.0, 0.5, u))
            if run:
                y -= 0.06 * math.sin(math.pi * u)             # the knee drives forward
        p.leg(s, Vector((sx * (STANCE_X - 0.01), y, z)), knee_dir=FWD + LEFT * sx * 0.1,
              foot=eul(pitch=pitch, yaw=sx * 6), toe=toe)
    # arms swing against the legs (right arm forward with the left foot)
    for s, sx in (("l", 1), ("r", -1)):
        ph = (phase + (0.5 if s == "l" else 0.0)) % 1.0
        sw = arm_swing * math.cos(2 * math.pi * ph)
        p.arm(s, down=84 if not run else 76, out=4, swing=sw, elbow=elbow + (8 if sw > 0 else 0) * (sw / max(arm_swing, 1)),
              wrist=-6)
        p.fingers(s, 0.12 if not run else 1.0, spread=0.6 if not run else 0.0)   # clenched when running
    return p


# ------------------------------------------------------------------------------------------ the clips
def clip_idle(rig, t):
    return _stand(rig, t, breathe=1.0, sway=0.004 * math.sin(2 * math.pi * t))


def clip_idle_look(rig, t):
    look = 35 * math.sin(2 * math.pi * t) * ss(0.05, 0.25, math.sin(math.pi * t) ** 0.5)
    return _stand(rig, t * 1.25 % 1.0, breathe=1.0, look=look, nod=3 * math.sin(4 * math.pi * t))


def clip_idle_shift(rig, t):
    """Weight onto the left leg, then the right; the free knee bends, the hip drops on its side."""
    w = math.sin(2 * math.pi * t)                              # +1 on the left leg
    p = _stand(rig, t * 1.5 % 1.0, breathe=1.0, sway=0.035 * w, bend=0.018)
    for s, sx in (("l", 1), ("r", -1)):
        a = _rest_ankle(rig, s)
        free = max(0.0, -w * sx)                               # this leg is unweighted
        p.leg(s, Vector((sx * STANCE_X, a.y - 0.03 * free, a.z + 0.015 * free)),
              knee_dir=FWD + LEFT * sx * 0.3, foot=eul(yaw=sx * 12, pitch=12 * free), toe=12 * free)
    return p


def clip_walk(rig, t):
    return _gait(rig, t, SPEED["Walk"], CLIPS["Walk"][0] / FPS, 0.6, 0.11, 0.018, 4, 22, 20)


def clip_run(rig, t):
    return _gait(rig, t, SPEED["Run"], CLIPS["Run"][0] / FPS, 0.38, 0.22, 0.03, 12, 38, 85, run=True)


def _turn(sign):
    def fn(rig, t):
        yaw = sign * 90 * ss(0.05, 0.9, t)
        p = Pose(rig)
        p.pelvis = Vector((0, 0, -0.02 - 0.012 * math.sin(math.pi * t)))
        q = eul(yaw=yaw)
        p.torso(pelvis=q, spine=(eul(yaw=sign * 6 * math.sin(math.pi * t)), Quaternion(), Quaternion()),
                head=eul(yaw=sign * 12 * math.sin(math.pi * min(t * 1.5, 1.0))))
        # the inside foot pivots with the body, the outside foot steps round in two lifts
        for s, sx in (("l", 1), ("r", -1)):
            a = _rest_ankle(rig, s)
            inside = (sign > 0) == (s == "l")
            t0, t1 = (0.1, 0.55) if not inside else (0.45, 0.9)
            u = ss(t0, t1, t)
            fy = sign * 90 * u
            qf = eul(yaw=fy)
            base = Vector((sx * STANCE_X, a.y, 0.0))
            pos = qf @ base
            lift = 0.07 * math.sin(math.pi * min(max((t - t0) / (t1 - t0), 0), 1))
            p.leg(s, Vector((pos.x, pos.y, a.z + lift)), knee_dir=qf @ (FWD + LEFT * sx * 0.15),
                  foot=eul(yaw=fy + sx * 8), toe=10 * (lift > 0.005))
            p.arm(s, down=76, out=10, swing=4 * math.sin(math.pi * t) * sx * sign, elbow=16)
            p.fingers(s, 0.05)
        return p
    return fn


HANDLE_GAP = 0.16         # right fist this far up the handle from the left
GRIP_CURL = 0.7           # fingers round a ~3.2 cm handle (0.82 closed them into a fist past it)
AXE_ROLL = -42.0          # the axe blade, degrees round the handle (grip axis) from the right hand's knuckles:
                          # fitted so the blade leads within 20 degrees all down the swing (socket roll)


def _hold(rig, p, s, dirv, strike=None):
    """The hand's rotation that lays its grip axis along dirv: first a forearm twist (pronation/supination)
    lining the thumb side up with dirv round the forearm, then a wrist bend for the rest. (The least rotation
    from the forearm straight away flips when the handle points back past the head - the axe cocked.)"""
    if strike is not None:                    # the whole grip frame: handle along dirv, knuckles toward strike
        return frame(dirv, strike) @ frame(rig.grip_axis[s], rig.strike_axis[s]).inverted()
    fore = p.D[f"lowerarm_{s}"]
    axis = (fore @ rig.dir(f"hand_{s}")).normalized()
    ga = fore @ rig.grip_axis[s]
    a = ga - axis * axis.dot(ga)
    b = dirv - axis * axis.dot(dirv)
    q = fore
    if a.length > 1e-4 and b.length > 1e-4:
        a, b = a.normalized(), b.normalized()
        tw = math.atan2(axis.dot(a.cross(b)), a.dot(b))
        q = Quaternion(axis, tw) @ fore
    return (q @ rig.grip_axis[s]).rotation_difference(dirv) @ q


def wrist_strain(rig, p, s):
    """(twist, flex, deviation) of hand s against its forearm, degrees. Twist round the forearm is pronation /
    supination (Humanoid "Forearm Twist", +-90 by default); flex bends the wrist toward the palm or back
    ("Hand Down-Up", +-80); deviation tips it toward the thumb or little finger ("Hand In-Out", only +-40 -
    past it Unity clamps the wrist and a two-handed grip comes apart)."""
    rel = p.D[f"lowerarm_{s}"].inverted() @ p.D[f"hand_{s}"]
    ax = rig.dir(f"hand_{s}")
    v = Vector((rel.x, rel.y, rel.z))
    along = v.dot(ax)
    twist = math.degrees(2.0 * math.atan2(along, rel.w))
    twist = (twist + 180.0) % 360.0 - 180.0
    swing = rel @ Quaternion((rel.w, *(ax * along))).normalized().inverted()
    ang = swing.angle
    if ang > math.pi:
        ang -= 2 * math.pi
    across = ax.cross(rig.dorsal[s]).normalized()                  # the wrist's flex hinge
    flex = math.degrees(ang) * swing.axis.dot(across)
    dev = math.degrees(ang) * swing.axis.dot(rig.dorsal[s])
    return twist, flex, dev


ARM_RAISE = 130.0         # upper arm past this many degrees from hanging folds the armpit skin (garments tear)


def _over_head(rig, p, s):
    """Degrees the upper arm is raised past ARM_RAISE (0 when below it)."""
    d = (p.pos(f"lowerarm_{s}") - p.pos(f"upperarm_{s}")).normalized()
    return max(0.0, math.degrees(d.angle(-UP)) - ARM_RAISE)


def _handle_hands(rig, p, grip, dirv, pivot=None, strike=None, hands=(("l", 0.0), ("r", HANDLE_GAP)), elbow=None):
    """Fists round one handle: by default the left at `grip`, the right HANDLE_GAP up it (dirv, toward the head;
    `hands` = (side, distance up the handle) pairs - one pair for a one-handed tool),
    knuckles toward `strike` (the tool's face; else the least turn from the forearm). The fist centre, not the
    wrist, sits on the handle, so a prop in the right hand's socket stays in both hands all the way through.
    Each elbow is chosen round its shoulder-wrist line to keep the forearm twist and wrist bend within what an
    arm does (and Humanoid retargeting keeps); with `pivot`, a handle out of reach slides in toward it (keeping
    its direction) until both arms reach: one rigid handle, never stretched apart. `elbow` {side: degrees}
    (splined between keys by the clip) narrows the elbow search round it, so it can't hop between two equally
    good elbows from one frame to the next; the angles chosen are left in p.elbow."""
    dirv = dirv.normalized()
    el0 = {"l": Vector((0.6, 0.2, -0.8)), "r": Vector((-0.6, 0.2, -0.8))}
    reach = rig.arm_len * 0.985

    def place(s, pos, pole, clav):
        wrist = pos.copy()
        for _ in range(12):                                            # wrist target <-> hand turn (damped:
            p.arm_ik(s, wrist, pole, clav=clav)                        # overhead the forearm swings a lot
            q = _hold(rig, p, s, dirv, strike)                         # for a small wrist move)
            wrist = wrist.lerp(pos - q @ rig.fist[s], 0.6)
        p.arm_ik(s, wrist, pole, clav=clav)
        p.D[f"hand_{s}"] = _hold(rig, p, s, dirv, strike)
        return wrist

    def solve(g):
        need = 0.0
        for s, up in hands:
            pos = g + dirv * up
            sh = p.pos(f"upperarm_{s}")
            clav = 30.0 * ss(0.05, 0.40, pos.z - sh.z)                 # shrug as the hands go overhead
            line = (pos - sh).normalized()
            best = None
            hint = None if elbow is None else elbow.get(s)
            first = range(-90, 91, 15) if hint is None else [hint + d for d in range(-12, 13, 4)]
            for a in first:                                            # elbow round the shoulder-wrist line
                pole = Quaternion(line, math.radians(a)) @ el0[s]
                place(s, pos, pole, clav)
                tw, fl, dv = wrist_strain(rig, p, s)
                miss = (p.pos(f"hand_{s}") + p.D[f"hand_{s}"] @ rig.fist[s] - pos).length   # fist off the handle
                cost = (tw * tw + 0.5 * fl * fl + 2.0 * dv * dv + (0.25 if hint is None else 4.0) * (a - (hint or 0.0)) ** 2
                        + 3.0 * _over_head(rig, p, s) ** 2 + 1e6 * miss * miss)
                if best is None or cost < best[0]:
                    best = (cost, a)
            for a in (best[1] - 6, best[1] - 3, best[1] + 3, best[1] + 6):
                pole = Quaternion(line, math.radians(a)) @ el0[s]
                place(s, pos, pole, clav)
                tw, fl, dv = wrist_strain(rig, p, s)
                miss = (p.pos(f"hand_{s}") + p.D[f"hand_{s}"] @ rig.fist[s] - pos).length   # fist off the handle
                cost = (tw * tw + 0.5 * fl * fl + 2.0 * dv * dv + (0.25 if hint is None else 4.0) * (a - (hint or 0.0)) ** 2
                        + 3.0 * _over_head(rig, p, s) ** 2 + 1e6 * miss * miss)
                if cost < best[0]:
                    best = (cost, a)
            wrist = place(s, pos, Quaternion(line, math.radians(best[1])) @ el0[s], clav)
            p.elbow[s] = best[1]
            need = max(need, (wrist - p.pos(f"upperarm_{s}")).length / reach)
        return need

    for _ in range(8):
        need = solve(grip)
        if pivot is None or need <= 1.0005:
            break
        grip = pivot + (grip - pivot) * (1.0 - 0.9 * (1.0 - 1.0 / need))
    for s, _ in hands:
        p.fingers(s, GRIP_CURL)                   # round the handle
    return grip


def clip_chop(rig, t):
    """Two-handed axe at a log in front: wind up over the right shoulder, chop down, recover."""
    # Keys in polar form around the shoulders' midpoint (the swing is an arc, and interpolating the grip in a
    # straight line dragged the hands past the face and slowed them mid-swing): lateral offset x, radius r,
    # arc angle th from straight up toward the front, handle's sideways lean dx and its arc angle psi, then torso
    # pitch, twist, knee bend. The wind-up flows up without stopping, elbows bent (radii inside the arm's
    # reach: past it, every key locked the arms straight), hangs at the top with the hands just over the head
    # and the axe head dropped behind the shoulders, extends the arms down into the log and stops dead there.
    K = [(0.00, (0.00, 0.53, 146, 0.00, 37, 18, 0, 0.03), "flow"),
         (0.22, (-0.10, 0.42, 80, -0.20, -25, 6, -8, 0.02), "flow"),       # rising in front, elbows bent (off
                                                                            # to the right, the left forearm had
                                                                            # to cross the face)
         (0.44, (-0.02, 0.46, 15, -0.05, -100, -8, -10, 0.02), "stop"),     # top: hands at the crown, elbows
                                                                            # forward (upper arms <=135 degrees:
                                                                            # higher folded the armpits), axe head
                                                                            # dropped behind the shoulders
         (0.62, (-0.01, 0.50, 150, 0.00, 90, 44, 4, 0.10), "hit"),         # into the log, handle level (steeper,
                                                                            # the wrists deviated past Humanoid's
                                                                            # 40 degrees and the grip came apart)
         (0.74, (-0.01, 0.51, 153, 0.00, 93, 46, 4, 0.11), "stop"),        # settles, the axe stuck
         (1.00, (0.00, 0.53, 146, 0.00, 37, 18, 0, 0.03), "flow")]
    x, r, th, dx, psi, pitch, tw, bend = spline(K, t)
    p = Pose(rig)
    p.pelvis = Vector((0, 0.03, -bend))
    p.torso(pelvis=eul(yaw=tw * 0.3, pitch=pitch * 0.2), spine=(eul(pitch=pitch * 0.3, yaw=tw * 0.25),
            eul(pitch=pitch * 0.3, yaw=tw * 0.25), eul(pitch=pitch * 0.2, yaw=tw * 0.2)),
            neck=eul(pitch=-pitch * 0.3), head=eul(pitch=-pitch * 0.2 + 8, yaw=-tw * 0.4))
    for s, sx, fy in (("l", 1, -0.10), ("r", -1, 0.10)):
        a = _rest_ankle(rig, s)
        p.leg(s, Vector((sx * 0.16, a.y + fy, a.z)), knee_dir=FWD + LEFT * sx * 0.3, foot=eul(yaw=sx * 15))
    piv = (p.pos("upperarm_l") + p.pos("upperarm_r")) / 2
    th, psi = math.radians(th), math.radians(psi)
    g = piv + Vector((x, -r * math.sin(th), r * math.cos(th)))
    d = Vector((dx, -math.sin(psi), math.cos(psi)))
    # the hands take their natural turn on the handle (least forearm twist, then wrist bend); the axe sits
    # in the grip rolled so its blade faces the log at impact (AXE_ROLL, the socket's roll - forcing the
    # knuckles to face the swing instead folded the wrists 75-100 degrees)
    _handle_hands(rig, p, g, d, pivot=piv)
    return p


HAMMER_HEAD = 0.28        # the hammer's head, this far up the handle from the fist
HAMMER_ROLL = -12.0       # its face, degrees round the handle from the right hand's knuckles (socket roll):
                          # the face meets the anvil square to the head's travel
HAMMER_PSI = {"rest": 10.0, "top": -85.0, "mid": -10.0, "hit": 80.0}   # handle angles (0 up, 90 forward, negative back):
                                                         # searched for the least wrist strain (the first keys
                                                         # ran the handle along the forearm: 105 deg of twist)


def _ham_dir(psi, dx=0.06):
    a = math.radians(psi)
    return Vector((dx, -math.sin(a), math.cos(a))).normalized()


# elbow angle per key: the free search's pick at each key (clip_hammer(rig, t, free=True).elbow), splined between
HAMMER_ELBOW = {"rest": 30.0, "top": 66.0, "mid": 33.0, "hit": 27.0}


def hammer_keys(psi=None, elbow=None):
    """The hammer's keys: fist xyz and handle direction; the fist at the hit is placed so the head lands on
    the anvil."""
    psi = dict(HAMMER_PSI, **(psi or {}))
    anvil = Vector((-0.12, -0.60, 0.80))
    hd = _ham_dir(psi["hit"])
    hit = anvil - hd * HAMMER_HEAD
    rb = _ham_dir(psi["hit"] - 12)
    rest = (-0.17, -0.38, 0.97, *_ham_dir(psi["rest"]))
    el = dict(HAMMER_ELBOW, **(elbow or {}))
    return [(0.00, (*rest, el["rest"]), "flow"),                                # recovered, head up in front
            (0.40, (-0.26, -0.18, 1.28, *_ham_dir(psi["top"]), el["top"]), "stop"),   # raised, head back
            # mid-swing: the handle kept square to the forearm as the wrist uncocks (a straight turn of the
            # handle angle in time ran it along the forearm on the way down)
            (0.52, (-0.21, -0.24, 1.10, *_ham_dir(psi["mid"]), el["mid"]), "flow"),
            (0.60, (*hit, *hd, el["hit"]), "hit"),                              # onto the anvil
            (0.70, (hit.x, hit.y + 0.01, hit.z + 0.04, *rb, el["hit"]), "stop"),   # rebound
            (1.00, (*rest, el["rest"]), "flow")]


def clip_hammer(rig, t, keys=None, free=False):
    """A one-handed hammer at an anvil in front (the face lands 12 cm right of centre, 0.8 m up); the left
    hand steadies the work. The fist closes round a rigid handle (the chop's grip solver): raised by the
    shoulder with the head back, a hang, then accelerating down onto the anvil, a small rebound. Handle angles
    (HAMMER_PSI) searched for the least wrist strain."""
    v = spline(keys or hammer_keys(), t)
    fist, d = Vector(v[0:3]), Vector(v[3:6]).normalized()
    hint = None if free else {"r": float(v[6])}
    raise_ = ss(0.0, 0.4, t) * (1 - ss(0.45, 0.6, t))
    p = Pose(rig)
    p.pelvis = Vector((0, 0.02, -0.02))
    p.torso(pelvis=eul(pitch=4), spine=(eul(pitch=5, yaw=-4 * raise_), eul(pitch=5, yaw=-6 * raise_), eul(pitch=4)),
            neck=eul(pitch=8), head=eul(pitch=12))
    for s, sx, fy in (("l", 1, -0.06), ("r", -1, 0.06)):
        a = _rest_ankle(rig, s)
        p.leg(s, Vector((sx * 0.13, a.y + fy, a.z)), knee_dir=FWD + LEFT * sx * 0.2, foot=eul(yaw=sx * 12))
    _handle_hands(rig, p, fist, d, pivot=p.pos("upperarm_r"), hands=(("r", 0.0),), elbow=hint)
    # the free hand steadies the work on the anvil, well left of where the hammer lands (at x 0.04 the handle
    # swung through it)
    p.arm_ik("l", Vector((0.14, -0.52, 0.84)), Vector((0.8, 0.3, -0.5)))
    p.fingers("l", 0.12, spread=0.4)
    return p


SEAT = 0.46
SEAT_HAND = 0.12          # palm off the thigh bone line when seated (the fingers went into the thighs at 0.07)


def _sit_pose(rig, t, k, lean=0.0, look=0.0):
    """k = 0 standing .. 1 seated (hips on a SEAT-high seat behind), lean = extra forward pitch."""
    p = Pose(rig)
    hip_rest = rig.head["thigh_l"].z
    down = (SEAT + 0.07) - hip_rest
    p.pelvis = Vector((0, 0.19 * k, down * k))
    b = math.sin(2 * math.pi * t)
    p.torso(pelvis=eul(pitch=lean * 0.4 + 6 * k), spine=(eul(pitch=lean * 0.25 - 4 * k), eul(pitch=lean * 0.2 - 2 * k + 0.5 * b),
            eul(pitch=lean * 0.15 - 1.0 * b)), neck=eul(pitch=-lean * 0.3 + 2), head=eul(pitch=-lean * 0.2, yaw=look))
    for s, sx in (("l", 1), ("r", -1)):
        a = _rest_ankle(rig, s)
        p.leg(s, Vector((sx * (STANCE_X + 0.02 * k), a.y - 0.08 * k, a.z)), knee_dir=FWD + LEFT * sx * 0.15,
              foot=eul(yaw=sx * 8))
        # the arm hangs, then (blending in, no pop) the palm comes to rest flat on the thigh
        p.arm(s, down=74, out=12 + 10 * k, swing=-10 * k, elbow=18 + 30 * k)
        w = ss(0.35, 0.9, k)
        if w > 0:
            hang, hang_q = p.pos(f"hand_{s}"), p.D[f"hand_{s}"]
            hip, knee = p.pos(f"thigh_{s}"), p.pos(f"calf_{s}")
            along = (knee - hip).normalized()
            top = p.D[f"thigh_{s}"] @ FWD                      # the thigh's front face: up when seated
            top = (top - along * top.dot(along)).normalized()
            # palm down, fingers toward the knee (a little inward), the back of the hand up
            fingers = (along - LEFT * sx * 0.15).normalized()
            q = frame(fingers, top) @ frame(rig.dir(f"hand_{s}"), rig.dorsal[s]).inverted()
            # the palm on the thigh's surface (8.6-9.9 cm off the bone across the builds, + cloth + palm)
            palm = hip.lerp(knee, 0.62) + top * SEAT_HAND + LEFT * sx * 0.01
            palm_off = (rig.head[f"middle_01_{s}"] - rig.head[f"hand_{s}"]) * 0.55 - rig.dorsal[s] * 0.012
            wrist = hang.lerp(palm - q @ palm_off, w)
            p.arm_ik(s, wrist, Vector((sx * 0.9, 0.3, -0.3)), hand=hang_q.slerp(q, w))
        p.fingers(s, 0.05 * (1 - w))
    return p


def clip_sit_down(rig, t):
    return _sit_pose(rig, 0.0, ss(0.1, 0.85, t), lean=28 * math.sin(math.pi * ss(0.0, 1.0, t)))


def clip_stand_up(rig, t):
    return _sit_pose(rig, 0.0, 1 - ss(0.15, 0.9, t), lean=32 * math.sin(math.pi * ss(0.0, 0.95, t)))


def clip_sit_idle(rig, t):
    return _sit_pose(rig, t, 1.0, look=18 * math.sin(2 * math.pi * t) * math.sin(math.pi * t))


def clip_death(rig, t):
    """Hit, knees buckle, falls onto the back, arms flop out, settles."""
    p = Pose(rig)
    hit = math.sin(math.pi * min(t / 0.15, 1.0)) * (t < 0.15)
    buckle = ss(0.1, 0.45, t)
    fall = ss(0.35, 0.78, t)
    settle = ss(0.78, 1.0, t)
    hip_rest = rig.head["pelvis"].z
    tilt = -85 * fall                                           # the whole body tips back
    p.pelvis = Vector((0, 0.05 * buckle + 0.42 * fall, -0.30 * buckle - (hip_rest - 0.12 - 0.30) * fall
                       + 0.015 * math.sin(math.pi * settle)))
    p.torso(pelvis=eul(pitch=tilt + 10 * buckle * (1 - fall)),
            spine=(eul(pitch=-12 * hit + 8 * buckle * (1 - fall)), eul(pitch=-10 * hit), eul(pitch=-8 * hit - 6 * fall)),
            neck=eul(pitch=-20 * hit + 10 * fall), head=eul(pitch=-15 * hit + 12 * fall, yaw=25 * settle))
    for s, sx in (("l", 1), ("r", -1)):
        a = _rest_ankle(rig, s)
        hip = p.pos(f"thigh_{s}")
        stand_ankle = Vector((sx * STANCE_X, a.y - 0.05 * buckle, a.z))
        lie_ankle = Vector((sx * (STANCE_X + 0.05), hip.y - 0.72, 0.07))
        ank = stand_ankle.lerp(lie_ankle, fall)
        kd = (FWD + UP * 0.6 * fall).normalized()
        p.leg(s, ank, knee_dir=kd + LEFT * sx * (0.2 + 0.5 * fall), foot=eul(pitch=-50 * fall, yaw=sx * (8 + 25 * fall)))
        p.arm(s, down=lerp(75, 20, fall), out=lerp(10, 35, settle), swing=lerp(0, -20, buckle) + 30 * hit,
              elbow=lerp(15, 40, fall))
        p.fingers(s, lerp(0.0, 0.15, fall), spread=lerp(1.0, 1.4, settle))
    return p


BUILD = {
    "Idle": clip_idle, "Idle_Look": clip_idle_look, "Idle_Shift": clip_idle_shift,
    "Walk": clip_walk, "Run": clip_run, "Turn_L90": _turn(1), "Turn_R90": _turn(-1),
    "Chop": clip_chop, "Hammer": clip_hammer,
    "Sit_Down": clip_sit_down, "Sit_Idle": clip_sit_idle, "Stand_Up": clip_stand_up, "Death": clip_death,
}


def build_clips(names=None):
    return {n: author(n, BUILD[n]) for n in (names or BUILD)}


def use(name, frame=0):
    ob = bpy.data.objects[RIG]
    if ob.animation_data is None:
        ob.animation_data_create()
    ob.animation_data.action = bpy.data.actions["Hum_" + name]
    bpy.context.scene.frame_set(frame)


def clear():
    ob = bpy.data.objects[RIG]
    if ob.animation_data:
        ob.animation_data.action = None
    for pb in ob.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)


def export_clips(names=None):
    """export/Anims/Human@<clip>.fbx: the deform skeleton with one baked take each."""
    import hum_export
    out = os.path.join(hum_export.EXPORT, "Anims")
    os.makedirs(out, exist_ok=True)
    ob = bpy.data.objects[RIG]
    scn = bpy.context.scene
    keep = (scn.frame_start, scn.frame_end, scn.render.fps)
    written = []
    # a sibling empty keeps the armature a child of the file root: with a lone armature Unity collapses
    # HumanRig into the root and the body's copied avatar no longer matches the hierarchy
    pin = bpy.data.objects.new("HumanClip", None)
    scn.collection.objects.link(pin)
    # the rest skeleton: a preview may have moved the bones for a build (hum_faces.apply_face), and the bake
    # would carry those offsets into every clip (Unity: "Copied Avatar Rig Configuration mis-match")
    for pb in ob.pose.bones:
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    ob.scale = (1, 1, 1)
    try:
        for name in (names or BUILD):
            use(name)
            n = CLIPS[name][0]
            scn.frame_start, scn.frame_end, scn.render.fps = 0, n, FPS
            for o in bpy.context.view_layer.objects:
                o.select_set(o == ob or o == pin)
            ob.hide_set(False)
            bpy.context.view_layer.objects.active = ob
            path = os.path.join(out, f"Human@{name}.fbx")
            bpy.ops.export_scene.fbx(
                filepath=path, use_selection=True, object_types={'ARMATURE', 'EMPTY'}, use_armature_deform_only=True,
                armature_nodetype='NULL', apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
                add_leaf_bones=False, bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
                bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                bake_anim_simplify_factor=0.0, use_custom_props=False, path_mode='STRIP')
            written.append(path)
    finally:
        scn.frame_start, scn.frame_end, scn.render.fps = keep
        bpy.data.objects.remove(pin)
        clear()
    import json
    table = dict(clips=[dict(name=n, frames=CLIPS[n][0], loop=CLIPS[n][1], bakeRootRotation=CLIPS[n][2],
                             speed=SPEED.get(n, 0.0)) for n in BUILD], fps=FPS)   # every clip, even on a partial export
    with open(os.path.join(hum_export.EXPORT, "human_clips.json"), "w") as fh:
        json.dump(table, fh, indent=1)
    return written
