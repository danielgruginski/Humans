"""The zombies' clips (2026-10-11, Daniel: "can you give them animations like limping or having a hard time walking?
also, slam attacks for zombies, or bite attacks. Skeletons could use the human animations though").

Made with hum_anim's machinery (Pose, IK, spline keys; Unity Humanoid, in place, 30 fps), registered in hum_anim.CLIPS /
BUILD so export_clips writes them like any clip (Human@Zombie_*.fbx):

Zombie_Idle      hunched, weight sunk on the good (right) leg, the bad one resting on its toes; slow uneven breathing,
                 the head lolling, a twitch now and then; arms hanging forward, the right hand clawed
Zombie_Limp      0.75 m/s: the left leg is dead weight - a short, painful stance with the body dropping and lurching over
                 it, then dragged forward stiff, toe scraping the ground, swung out to the side; the good leg hurries
                 through a quick step; the right arm reaches, the left hangs and swings late
Zombie_Shamble   0.85 m/s: stiff-kneed shuffle, feet barely leaving the ground, the whole body rocking from leg to leg,
                 the steps uneven; both arms reaching forward (the left lower), head forward and up
Zombie_Slam      a two-fisted hammer: rise and arch back with both fists high over the head, hang, then the whole body
                 jackknifes down onto the target (impact 0.52), a bounce, and back to the idle pose
Zombie_Bite      lunge and grab at shoulder height (a step in), pull the victim close, the head darts in and down
                 (impact 0.46), two tearing shakes, shove off and back to the idle pose

Axes as hum_anim: +Z up, front -Y, the character's left +X; eul(pitch>0 leans forward, roll>0 tips to the left).
The Undead builds already carry the hunch as bone offsets; these clips add the posture and the motion.
"""
import math

import numpy as np
from mathutils import Quaternion, Vector

import hum_anim as A
from hum_anim import Pose, eul, lerp, ss, FWD, LEFT, UP

CLIPS = {"Zombie_Idle": (150, True, True), "Zombie_Limp": (40, True, True), "Zombie_Shamble": (40, True, True),
         "Zombie_Slam": (54, False, True), "Zombie_Bite": (54, False, True)}
SPEED = {"Zombie_Limp": 0.75, "Zombie_Shamble": 0.85}    # (the game moves zombies at these: 2026-10-11, first 0.5 / 0.6)
HITS = {"Zombie_Slam": 0.52, "Zombie_Bite": 0.46}        # normalized impact times (a game's hit events)

STANCE_X = 0.115


def wrap(t):
    return t % 1.0


def bump(t, c, w):
    """A smooth periodic bump: 1 at phase c, 0 beyond +-w (wrapping round the loop)."""
    d = abs(((t - c + 0.5) % 1.0) - 0.5)
    return ss(w, 0.0, d)


def twitch(t, t0, rise=0.012, fall=0.08):
    """A quick jerk at t0: up in `rise`, eased back over `fall` (0 outside)."""
    if t < t0 or t > t0 + rise + fall:
        return 0.0
    if t < t0 + rise:
        return ss(t0, t0 + rise, t)
    return 1.0 - ss(t0 + rise, t0 + rise + fall, t)


def loop_spline(K, t):
    """hum_anim.spline over a loop given as [(time, values, kind), ...] without the closing key."""
    return A.spline(K + [(1.0, K[0][1], K[0][2])], wrap(t))


def once_spline(K, t):
    """A one-shot: keys from 0 to 1 (both given)."""
    T = [k[0] for k in K]
    for i in range(len(K) - 1):
        if T[i] <= t <= T[i + 1]:
            P0, P1 = np.asarray(K[i][1], float), np.asarray(K[i + 1][1], float)
            h = T[i + 1] - T[i]
            u = (t - T[i]) / h

            def tan(j, side):
                kind = K[j][2]
                if kind == "stop" or j == 0 or j == len(K) - 1:
                    return np.zeros_like(P0)
                Pp, Pn = np.asarray(K[j - 1][1], float), np.asarray(K[j + 1][1], float)
                if kind == "hit":
                    return 2.0 * (np.asarray(K[j][1], float) - Pp) / (T[j] - T[j - 1]) if side == "in" else np.zeros_like(P0)
                return (Pn - Pp) / (T[j + 1] - T[j - 1])
            m0, m1 = tan(i, "out"), tan(i + 1, "in")
            h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
            h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
            return h00 * P0 + h10 * h * m0 + h01 * P1 + h11 * h * m1
    return np.asarray(K[-1][1], float)


def _ankle(rig, s):
    return A._rest_ankle(rig, s)


def _side(s):
    return 1.0 if s == "l" else -1.0


def _ch(v, s):
    """(out, forward, up) in the character's frame -> world, `out` away from the body on side s."""
    return Vector((_side(s) * v[0], -v[1], v[2]))


def reach(p, s, off, elbow=(0.6, 0.0, -1.0), fist=0.4, spread=1.6, clav=0.0):
    """One arm by IK: the wrist at the shoulder + `off` = (out, forward, up) in the character's frame (not the leaning
    chest's: an arm 'reaching forward' in a chest bent 40 degrees pointed at the knees), the elbow toward `elbow` (same
    frame)."""
    sh = p.pos(f"upperarm_{s}")
    p.arm_ik(s, sh + _ch(off, s), _ch(elbow, s).normalized(), clav=clav)
    p.fingers(s, fist, spread=spread)


# ------------------------------------------------------------------ idle

def idle_pose(rig, t, breathe=1.0):
    """The zombie's rest pose at loop time t (the attacks start and end on idle_pose(rig, 0))."""
    p = Pose(rig)
    b = math.sin(2 * math.pi * t) * 0.6 + math.sin(2 * math.pi * 3 * t + 1.3) * 0.4       # uneven breathing
    b *= breathe
    sway = -0.03 + 0.012 * math.sin(2 * math.pi * t + 0.4) + 0.006 * math.sin(2 * math.pi * 2 * t)
    tw = twitch(t, 0.58) - 0.6 * twitch(t, 0.86, 0.01, 0.05)
    p.pelvis = Vector((sway, 0.0, -0.035 + 0.004 * b))
    loll = 9 * math.sin(2 * math.pi * t + 2.0) + 4 * math.sin(2 * math.pi * 2 * t)
    p.torso(pelvis=eul(roll=-sway * 70, yaw=-4, pitch=4),
            spine=(eul(pitch=7 - 0.8 * b, yaw=3), eul(pitch=8 + 0.6 * b), eul(pitch=8 - 1.5 * b, roll=sway * 60 + 3)),
            neck=eul(pitch=-6 + 3 * b, roll=loll * 0.4),
            head=eul(pitch=-10 + 4 * math.sin(2 * math.pi * t + 0.7), roll=loll + 10 * tw, yaw=6 + 22 * tw))
    a_l, a_r = _ankle(rig, "l"), _ankle(rig, "r")
    p.leg("r", Vector((-STANCE_X - 0.01, a_r.y + 0.04, a_r.z)), knee_dir=FWD - LEFT * 0.2, foot=eul(yaw=-16))
    # the bad (left) leg forward a little, resting on the ball of its foot
    p.leg("l", Vector((STANCE_X, a_l.y - 0.07, a_l.z + 0.035)), knee_dir=FWD + LEFT * 0.35, foot=eul(pitch=18, yaw=10),
          toe=16)
    lag = math.sin(2 * math.pi * (t - 0.08))
    p.arm("l", down=84, out=5, swing=10 + 3 * lag, elbow=18 + 2 * b, twist=10, clav=-2)
    p.arm("r", down=80, out=4, swing=16 - 3 * lag, elbow=34 + 3 * b, twist=-6, clav=1)
    p.fingers("l", 0.15, spread=0.8)
    p.fingers("r", 0.38 + 0.05 * b, spread=1.6)              # clawed
    return p


def clip_idle(rig, t):
    return idle_pose(rig, t)


# ------------------------------------------------------------------ the limp

def _foot(t, start, length, y_front, y_back):
    """(in stance?, u) for a foot whose stance starts at `start` and lasts `length` (of the cycle)."""
    ph = wrap(t - start)
    if ph < length:
        return True, ph / length
    return False, (ph - length) / (1.0 - length)


def clip_limp(rig, t):
    n = CLIPS["Zombie_Limp"][0]
    period = n / A.FPS
    v = SPEED["Zombie_Limp"]
    p = Pose(rig)
    a_l, a_r = _ankle(rig, "l"), _ankle(rig, "r")
    # the good (right) leg: long stance, quick step; the bad (left): short stance, a slow drag
    R0, RL = 0.0, 0.66
    L0, LL = 0.58, 0.50
    DR, DL = v * RL * period, v * LL * period
    cR, cL = a_r.y + 0.03, a_l.y - 0.05
    # pelvis: drops and lurches over the bad leg while it bears the body alone (0.66-1.0), rides over the good one
    bad_alone = bump(t, 0.83, 0.18)
    good_mid = bump(t, 0.33, 0.25)
    sway = -0.03 * good_mid + 0.065 * bad_alone
    dz = -0.03 - 0.08 * bad_alone + 0.012 * good_mid
    hike = bump(t, 0.32, 0.2)                                 # the bad hip hitched up to clear the dragged foot
    yaw = 10 * math.sin(2 * math.pi * (t - 0.1))
    p.pelvis = Vector((sway, 0.0, dz))
    lurch = bad_alone
    p.torso(pelvis=eul(yaw=yaw, roll=-8 * hike + 9 * lurch, pitch=5 + 6 * lurch),
            spine=(eul(yaw=-yaw * 0.5, pitch=6 + 5 * lurch, roll=7 * lurch),
                   eul(yaw=-yaw * 0.4, pitch=7 + 5 * lurch, roll=8 * lurch),
                   eul(yaw=-yaw * 0.4, pitch=6 + 3 * lurch, roll=5 * lurch - 3 * good_mid)),
            neck=eul(pitch=-8 - 8 * lurch, roll=-8 * lurch),
            head=eul(pitch=-8 + 10 * bump(t, 0.92, 0.1), roll=-6 * lurch + 3 * good_mid, yaw=-yaw * 0.4))
    # right foot
    st, u = _foot(t, R0, RL, cR - DR / 2, cR + DR / 2)
    if st:
        y = lerp(cR - DR / 2, cR + DR / 2, u)
        pitch = lerp(-8, 0, ss(0, 0.2, u)) + 30 * ss(0.65, 1.0, u)
        toe = 30 * ss(0.65, 1.0, u)
        z = a_r.z + 0.13 * math.sin(math.radians(max(pitch, 0))) * 0.9
        p.leg("r", Vector((-STANCE_X, y, z)), knee_dir=FWD - LEFT * 0.15, foot=eul(pitch=pitch, yaw=-10), toe=toe)
    else:
        e = ss(0, 1, u)
        y = lerp(cR + DR / 2, cR - DR / 2, e)
        z = a_r.z + 0.085 * math.sin(math.pi * u)
        pitch = lerp(30, -10, ss(0, 0.85, u))
        p.leg("r", Vector((-STANCE_X, y, z)), knee_dir=FWD - LEFT * 0.15, foot=eul(pitch=pitch, yaw=-10),
              toe=lerp(30, 0, ss(0, 0.5, u)))
    # left (bad) foot: stance flat and brief; the swing a drag on its toes, out to the side
    st, u = _foot(t, L0, LL, cL - DL / 2, cL + DL / 2)
    if st:
        y = lerp(cL - DL / 2, cL + DL / 2, u)
        pitch = lerp(10, 0, ss(0, 0.25, u)) + 22 * ss(0.7, 1.0, u)
        z = a_l.z + 0.13 * math.sin(math.radians(max(pitch, 0))) * 0.9
        p.leg("l", Vector((STANCE_X + 0.01, y, z)), knee_dir=FWD + LEFT * 0.35, foot=eul(pitch=pitch, yaw=14),
              toe=22 * ss(0.7, 1.0, u))
    else:
        e = u * 0.75 + 0.25 * ss(0, 1, u)                     # a steady drag, not a step
        y = lerp(cL + DL / 2, cL - DL / 2, e)
        pitch = 24 + 4 * math.sin(math.pi * u)                 # toe down: the toes scrape
        z = a_l.z + 0.13 * math.sin(math.radians(pitch)) * 0.9 + 0.006 * math.sin(math.pi * u)
        x = STANCE_X + 0.01 + 0.05 * math.sin(math.pi * u)     # swung out round the hip
        p.leg("l", Vector((x, y, z)), knee_dir=FWD + LEFT * 0.5, foot=eul(pitch=pitch, yaw=18), toe=10)
    # arms: the right reaches forward (and drops with the lurch); the left hangs and swings late off the lurch
    reach(p, "r", (0.04, 0.40 + 0.04 * math.sin(2 * math.pi * (t - 0.2)), -0.17 - 0.08 * bad_alone),
          elbow=(0.7, 0.0, -1.0), fist=0.4, spread=1.7, clav=3)
    p.arm("l", down=86, out=7 + 6 * lurch, swing=6 + 18 * math.sin(2 * math.pi * (t - 0.25)), elbow=14, twist=12,
          clav=-3 + 3 * hike)
    p.fingers("l", 0.12, spread=0.8)
    return p


# ------------------------------------------------------------------ the shamble

def clip_shamble(rig, t):
    n = CLIPS["Zombie_Shamble"][0]
    period = n / A.FPS
    v = SPEED["Zombie_Shamble"]
    p = Pose(rig)
    a_l, a_r = _ankle(rig, "l"), _ankle(rig, "r")
    stance = 0.64
    rock = math.sin(2 * math.pi * (t - 0.06))                 # +1 over the left leg
    p.pelvis = Vector((0.05 * rock, 0.0, -0.025 - 0.012 * abs(math.sin(2 * math.pi * t))))
    yaw = 5 * math.sin(2 * math.pi * t)
    p.torso(pelvis=eul(roll=-8 * rock, yaw=yaw, pitch=6),
            spine=(eul(pitch=8, roll=5 * rock, yaw=-yaw * 0.5), eul(pitch=9, roll=6 * rock),
                   eul(pitch=8, roll=3 * rock, yaw=-yaw * 0.5)),
            neck=eul(pitch=-14, roll=-4 * rock),
            head=eul(pitch=-10 + 4 * math.sin(4 * math.pi * t + 0.5), roll=-5 * rock + 4, yaw=4))
    for s, sx, off, short in (("l", 1, 0.0, 0.8), ("r", -1, 0.5, 1.0)):
        a = _ankle(rig, s)
        D = v * stance * period * short                       # the left steps shorter: uneven
        c = a.y + (0.03 if s == "l" else 0.0)
        ph = wrap(t + off)
        if ph < stance:
            u = ph / stance
            y = lerp(c - D / 2, c + D / 2, u)
            pitch = 14 * ss(0.75, 1.0, u)
            z = a.z + 0.13 * math.sin(math.radians(pitch)) * 0.9
        else:
            u = (ph - stance) / (1 - stance)
            y = lerp(c + D / 2, c - D / 2, ss(0, 1, u))
            z = a.z + 0.04 * math.sin(math.pi * u)            # a shuffle
            pitch = lerp(14, 0, ss(0, 0.7, u))
        # stiff knees: the knee points forward but the ankle stays far from the hip (little bend)
        p.leg(s, Vector((sx * (STANCE_X + 0.015), y, z)), knee_dir=FWD + LEFT * sx * 0.25, foot=eul(pitch=pitch, yaw=sx * 12),
              toe=pitch * 0.6)
    bob = math.sin(4 * math.pi * t)
    # both arms reaching, the left lower and shorter; they bob with the steps and swing a little against the rock
    reach(p, "r", (0.0 - 0.02 * rock, 0.47, -0.06 + 0.03 * bob), elbow=(0.8, 0.0, -1.0), fist=0.42, spread=1.8, clav=5)
    reach(p, "l", (0.03 + 0.02 * rock, 0.38, -0.2 - 0.03 * bob), elbow=(0.8, 0.0, -1.0), fist=0.35, spread=1.5, clav=3)
    return p


# ------------------------------------------------------------------ attacks

def _attack_pose(rig, k):
    """A pose from a key vector: pelvis (x, y, z), pelvis pitch, spine pitch, spine roll, spine yaw, neck pitch,
    head pitch, head yaw, left foot (dy, dz), right foot (dy, dz), hands (l, r: out, forward, up from the shoulder),
    fists (l, r)."""
    (px, py, pz, ppit, spit, sroll, syaw, npit, hpit, hyaw, lfy, lfz, rfy, rfz,
     lx, ly, lz, rx, ry, rz, fl, fr) = k
    p = Pose(rig)
    p.pelvis = Vector((px, py, pz))
    p.torso(pelvis=eul(pitch=ppit, yaw=syaw * 0.3),
            spine=(eul(pitch=spit * 0.3, roll=sroll * 0.3, yaw=syaw * 0.25), eul(pitch=spit * 0.35, roll=sroll * 0.35,
                   yaw=syaw * 0.25), eul(pitch=spit * 0.35, roll=sroll * 0.35, yaw=syaw * 0.2)),
            neck=eul(pitch=npit * 0.6), head=eul(pitch=hpit + npit * 0.4, yaw=hyaw))
    a_l, a_r = _ankle(rig, "l"), _ankle(rig, "r")
    p.leg("l", Vector((STANCE_X, a_l.y - 0.07 + lfy, a_l.z + lfz)), knee_dir=FWD + LEFT * 0.3,
          foot=eul(yaw=10, pitch=40 * max(lfz, 0) / 0.05 if lfz > 0.002 else 0), toe=0)
    p.leg("r", Vector((-STANCE_X - 0.01, a_r.y + 0.04 + rfy, a_r.z + rfz)), knee_dir=FWD - LEFT * 0.25,
          foot=eul(yaw=-16, pitch=30 * max(rfz, 0) / 0.05 if rfz > 0.002 else 0),
          toe=25 * min(max(rfz, 0) / 0.05, 1.0))
    return p, (lx, ly, lz), (rx, ry, rz), (fl, fr)


# key vector order (see _attack_pose); hands: (out, forward, up) from each shoulder in the character's frame
#            px     py     pz    ppit  spit  sroll syaw  npit  hpit  hyaw  lfy   lfz   rfy   rfz
#            l out  l fwd  l up   r out  r fwd  r up  fl   fr
IDLE_K = (-0.03, 0.00, -0.035, 4, 23, 3, 0, -6, -10, 6, 0, 0.035, 0, 0,
          0.04, 0.08, -0.52, 0.03, 0.14, -0.48, 0.15, 0.4)
SLAM = [
    (0.00, IDLE_K, "stop"),
    (0.14, (-0.01, 0.03, -0.06, 0, 12, 0, 6, -4, -6, 0, 0, 0.0, 0.0, 0,
            0.02, 0.10, -0.42, 0.02, 0.12, -0.42, 0.5, 0.6), "flow"),             # gathering, weight back
    (0.34, (0.0, 0.05, 0.01, -6, -14, 0, 4, -14, -12, 0, -0.02, 0.0, 0.0, 0.03,
            -0.10, 0.04, 0.50, -0.10, 0.04, 0.50, 1.0, 1.0), "stop"),             # fists high, arched back
    (0.42, (0.0, 0.05, 0.015, -7, -17, 0, 4, -16, -12, 0, -0.02, 0.0, 0.0, 0.035,
            -0.10, 0.0, 0.53, -0.10, 0.0, 0.53, 1.0, 1.0), "stop"),               # the hang at the top
    (0.52, (0.0, -0.10, -0.15, 22, 48, 0, 0, 14, 8, 0, -0.06, 0.0, 0.0, 0.0,
            -0.12, 0.42, -0.30, -0.12, 0.42, -0.30, 1.0, 1.0), "hit"),            # the blow: whole body down
    (0.60, (0.0, -0.08, -0.12, 18, 42, 0, 0, 10, 6, 0, -0.06, 0.0, 0.0, 0.0,
            -0.11, 0.40, -0.24, -0.11, 0.40, -0.24, 1.0, 1.0), "flow"),           # bounce
    (0.78, (-0.02, -0.02, -0.06, 8, 30, 2, 0, 0, -8, 4, -0.02, 0.02, 0, 0,
            0.0, 0.20, -0.45, 0.0, 0.22, -0.43, 0.5, 0.6), "flow"),
    (1.00, IDLE_K, "stop"),
]
BITE = [
    (0.00, IDLE_K, "stop"),
    (0.20, (0.0, -0.14, -0.06, 14, 38, 0, 0, -18, -6, 0, -0.26, 0.0, -0.04, 0.03,
            0.0, 0.50, -0.02, 0.0, 0.50, -0.02, 0.0, 0.0), "flow"),              # lunge, a step in, claws out
    (0.34, (0.0, -0.17, -0.08, 16, 40, 0, 0, -16, -6, 0, -0.30, 0.0, -0.05, 0.03,
            -0.06, 0.42, 0.0, -0.06, 0.42, 0.0, 0.8, 0.8), "stop"),               # grabbed
    (0.46, (0.0, -0.20, -0.10, 18, 46, 0, 0, 20, 14, 0, -0.30, 0.0, -0.05, 0.03,
            -0.08, 0.28, -0.04, -0.08, 0.28, -0.04, 0.9, 0.9), "hit"),            # pulled in: the bite
    (0.55, (0.0, -0.19, -0.10, 18, 46, 0, 10, 20, 12, 22, -0.30, 0.0, -0.05, 0.03,
            -0.07, 0.28, -0.02, -0.09, 0.30, -0.06, 0.9, 0.9), "stop"),           # tearing: shake one way
    (0.63, (0.0, -0.19, -0.10, 18, 46, 0, -10, 18, 12, -22, -0.30, 0.0, -0.05, 0.03,
            -0.09, 0.30, -0.06, -0.07, 0.28, -0.02, 0.9, 0.9), "stop"),           # and the other
    (0.76, (0.0, -0.10, -0.07, 10, 34, 0, 0, -4, -6, 0, -0.18, 0.0, -0.02, 0.02,
            0.02, 0.40, -0.14, 0.02, 0.40, -0.14, 0.1, 0.1), "flow"),             # shoved off
    (1.00, IDLE_K, "stop"),
]
ELBOW_SLAM = (1.0, 0.25, -0.2)          # out to the side, a little forward
ELBOW_BITE = (1.0, 0.0, -0.7)           # out and down


def _attack(rig, t, K, elbow):
    k = once_spline(K, t)
    p, lh, rh, (fl, fr) = _attack_pose(rig, k)
    for s, h, fi in (("l", lh, fl), ("r", rh, fr)):
        reach(p, s, h, elbow=elbow, fist=fi, spread=1.6, clav=6.0 * ss(0.0, 0.5, h[2]))
    return p


def clip_slam(rig, t):
    return _attack(rig, t, SLAM, ELBOW_SLAM)


def clip_bite(rig, t):
    return _attack(rig, t, BITE, ELBOW_BITE)



BUILD = {"Zombie_Idle": clip_idle, "Zombie_Limp": clip_limp, "Zombie_Shamble": clip_shamble,
         "Zombie_Slam": clip_slam, "Zombie_Bite": clip_bite}
A.CLIPS.update(CLIPS)                                     # registered with hum_anim (export_clips, human_clips.json)
A.SPEED.update(SPEED)
A.BUILD.update(BUILD)
