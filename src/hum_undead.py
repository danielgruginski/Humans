"""The undead (2026-10-10, Daniel: "You know those orc models made from the humanoid shapes? Now we are going to do the
same, but with zombies and skeletons"; his picks: rotting villagers, models + the Unity install).

Like the orcs (hum_orcs), the human made into something else:

- the **Undead builds** (hum_builds `MUndead` / `FUndead`, odds 0): starved and hunched - the thin and slight macros at
  full, wasted muscles, a scrawny neck carried forward, and shapes of our own (`DEFORMS`, preset-only sliders in
  hum_faces): **Hunch** (shoulders rolled forward and down, the head carried low and forward, a rounded upper back),
  **Ribs** (the ribs standing out over the chest and flanks), **Sunken** (the belly sunk under the ribcage's edge),
  **Bony** (collarbones and their hollows); face keys **EyeSunken** (the eye sockets' rims sunk round the lids) and
  **Gaunt** (hollow cheeks and temples). Every garment is built for the Undead builds like for any build, and the
  skeleton (hum_skeleton) is built on them too, so a skeleton wears the same clothes and armour.
- the **Zombie** preset: grey-green / livid skin, milky eyes, thin dark or grey hair, rot painted into the skin
  (`rot`, hum_paint rot masks), torn clothes (`tatter`: the cloth shader paints holes with the skin under them).
- the **Skeleton** preset: the same build, wearing the skeleton piece (hum_skeleton: bones rigged to the human
  skeleton, body and head hidden), its clothes torn open (`tatter_cut`: real holes, the bones show through).

    import hum_undead, hum_faces; hum_faces.apply_face(bpy.data.objects["Head"], hum_undead.undead_face(11))
    (hum_undead.SKELETON for a skeleton; refresh_materials() after a Blender restart)
"""
import numpy as np

import hum_faces as F

_smooth = F._smooth


# ------------------------------------------------------------------ body shapes (full MPFB coords -> full coords)

def _torso_frame(C, sk):
    H, _ = sk.ends(C)
    j = {b: H[sk.index[b]] for b in ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head",
                                     "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r")}
    cy = float(np.mean([j[b][1] for b in ("spine_01", "spine_02", "spine_03")]))
    return H, j, cy


def _around(C, cy):
    """(a, radial unit) per vertex: a = 0 at the front .. 1 at the back (MPFB: +Y is the back), the horizontal
    direction away from the torso's axis."""
    dx, dy = C[:, 0], C[:, 1] - cy
    th = np.arctan2(dx, -dy)
    r = np.maximum(np.hypot(dx, dy), 1e-9)
    rad = np.stack([dx / r, dy / r, np.zeros(len(C))], 1)
    return np.abs(th) / np.pi, rad


def _deform_hunch(C, rig, sk, fwd=0.04, drop=0.022, head_fwd=0.035, head_drop=0.02, hump=0.026):
    """Slumped: the shoulders rolled forward and down (each arm's bones and half for the clavicle, by the skin
    weights, so the joints follow like the orcs' ArmsOut), the neck and head carried low and forward, and the
    upper back rounded into a hump between the shoulder blades (skin only). Bone moves are translations: a
    Humanoid clip turns the bones, the offsets stay."""
    W = F._weights(sk, len(C))
    skin = F._skin(len(C))
    H, j, cy = _torso_frame(C, sk)
    D = np.zeros((len(sk.bones), 3))
    for side in ("l", "r"):
        s = np.sign(j["upperarm_" + side][0])
        D[sk.index["clavicle_" + side]] = (-s * 0.004, -fwd * 0.5, -drop * 0.5)
        for b in F._limb(sk, "upperarm_" + side):
            D[sk.index[b]] = (-s * 0.008, -fwd, -drop)
    D[sk.index["neck_01"]] = (0.0, -head_fwd * 0.6, -head_drop * 0.6)
    D[sk.index["head"]] = (0.0, -head_fwd, -head_drop)
    C = C + W @ D
    a, rad = _around(C, cy)
    z = C[:, 2]
    zc = j["spine_03"][2] + 0.62 * (j["neck_01"][2] - j["spine_03"][2])
    back = _smooth(0.55, 0.85, a)
    m = np.exp(-0.5 * ((z - zc) / 0.075) ** 2) * back * skin
    m *= _smooth(0.26, 0.17, np.abs(C[:, 0]))                       # the back, not the arms
    C[:, 1] += hump * m
    C[:, 2] -= 0.25 * hump * m
    front = _smooth(0.4, 0.15, a) * np.exp(-0.5 * ((z - (zc + 0.02)) / 0.06) ** 2) * skin
    C[:, 1] += 0.008 * front * _smooth(0.2, 0.12, np.abs(C[:, 0]))  # a caved chest
    return C


def _rib_cage(j, cy):
    """Ribs as height lines round the torso: the top rib at the back just under the collarbones, spacing,
    each rib dropping toward the front (the lower ones more)."""
    top = j["clavicle_l"][2] - 0.035
    bottom = j["spine_02"][2] + 0.01
    n = 9
    sp = (top - bottom) / (n - 0.5)
    return top, sp, n, 0.035, 0.055


def rib_phase(P, j, cy):
    """Continuous rib number at points P (0 = the top rib's line, integers on the ribs) and a (0 front .. 1 back):
    the painted ribs (hum_paint rot masks) use the same lines."""
    a, _ = _around(P, cy)
    top, sp, n, d0, d1 = _rib_cage(j, cy)
    f = (1.0 - a) ** 1.3
    return (top - P[:, 2] - d0 * f) / (sp + d1 * f / (n - 1)), a, n


def _deform_ribs(C, rig, sk, amp=0.004):
    """The ribcage standing out of a starved body: the lower ribs' barrel pushed out over the flanks and below the
    chest (the belly sinks under it: Sunken), none over the spine, faint under the pectorals. The ribs themselves
    are painted (hum_paint rot masks): at ~1.5 cm edges the body mesh can't carry 2.6 cm ridges (they aliased into
    ripples). Along the torso's horizontal radial direction, skin only."""
    C = C.copy()
    skin = F._skin(len(C))
    W = F._weights(sk, len(C))
    H, j, cy = _torso_frame(C, sk)
    torso = W[:, [sk.index[b] for b in ("spine_02", "spine_03", "spine_01")]].sum(1)
    a, rad = _around(C, cy)
    p, a, n = rib_phase(C, j, cy)
    rel = _smooth(2.0, 5.5, p)                                       # the lower cage most
    m = _smooth(0.25, 0.9, p) * _smooth(n - 0.2, n - 0.9, p)
    m *= _smooth(0.92, 0.72, a)                                      # back muscles cover them
    m *= _smooth(0.012, 0.035, np.abs(C[:, 0]))                      # the sternum: flat
    m *= _smooth(0.35, 0.75, torso) * skin
    nip = j["clavicle_l"][2] - 0.085                                 # under the pectorals: faint
    m *= 1.0 - 0.75 * _smooth(nip - 0.04, nip, C[:, 2]) * _smooth(0.45, 0.2, a)
    C += rad * (amp * rel * m)[:, None]
    return C


def _costal_z(j, x):
    """Height of the ribcage's lower edge at the front: an inverted V from the sternum's tip down to the sides."""
    tip = j["spine_03"][2] + 0.045
    return tip - 0.55 * np.abs(x)


def _deform_sunken(C, rig, sk, depth=0.022):
    """The belly sunk in under the ribcage: the front between the ribcage's lower edge and the pelvis pushed back
    toward the spine, deepest just under the edge (so the edge stands out), easing out toward the hips; the waist's
    sides drawn in a little."""
    C = C.copy()
    skin = F._skin(len(C))
    H, j, cy = _torso_frame(C, sk)
    a, rad = _around(C, cy)
    zc = _costal_z(j, C[:, 0])
    zp = j["spine_01"][2] + 0.01
    z = C[:, 2]
    below = _smooth(zc + 0.004, zc - 0.012, z) * _smooth(zp - 0.03, zp + 0.03, z)
    prof = below * (0.55 + 0.45 * _smooth(zp + 0.02, zc - 0.01, z))
    front = _smooth(0.5, 0.22, a) * _smooth(0.16, 0.11, np.abs(C[:, 0]))
    m = prof * front * skin
    C[:, 1] += depth * m
    side = below * _smooth(0.22, 0.4, a) * _smooth(0.75, 0.55, a) * skin * _smooth(0.2, 0.14, np.abs(C[:, 0]))
    C -= rad * (0.008 * side)[:, None]
    return C


def _deform_bony(C, rig, sk, ridge=0.005, pit=0.009):
    """Collarbones standing out: a ridge along each clavicle (from the throat's notch to the shoulder) with a
    hollow above it and a shallower one below. Skin only."""
    C = C.copy()
    skin = F._skin(len(C))
    H, j, cy = _torso_frame(C, sk)
    for side in ("l", "r"):
        a0 = j["clavicle_" + side].copy()
        b0 = j["upperarm_" + side].copy()
        s = np.sign(b0[0])
        a0[0] = s * 0.018
        # the bone lies under the skin's front: its line is the front surface near those heights
        e = b0 - a0
        L = float(np.linalg.norm(e[[0, 2]]))
        t = np.clip(((C[:, 0] - a0[0]) * e[0] + (C[:, 2] - a0[2]) * e[2]) / (L * L), -0.2, 1.2)
        zl = a0[2] + t * e[2] + 0.004 * np.sin(np.pi * np.clip(t, 0, 1))
        dz = C[:, 2] - zl
        along = _smooth(-0.05, 0.08, t) * _smooth(0.95, 0.75, t) * (np.sign(C[:, 0]) == s)
        front = C[:, 1] < cy - 0.02
        r = np.exp(-0.5 * (dz / 0.006) ** 2)
        above = np.exp(-0.5 * ((dz - 0.018) / 0.008) ** 2)
        below = np.exp(-0.5 * ((dz + 0.02) / 0.009) ** 2)
        w = along * front * skin
        C[:, 1] -= (ridge * r - pit * above - 0.35 * pit * below) * w
    return C


# ------------------------------------------------------------------ face shapes

def _deform_eye_sunken(C, rig, sk, depth=0.0045):
    """The eye sockets' rims sunk round the lids: a ring from just outside the lids to the socket's edge pushed
    back (deepest under the brow and below the eye), the lids and the eyes stay. Skin only."""
    C = C.copy()
    skin = F._skin(len(C))
    for h in ("helper-l-eye", "helper-r-eye"):
        e = rig.centre(C, h)
        dx, dz = C[:, 0] - e[0], (C[:, 2] - e[2]) * 1.15
        r = np.hypot(dx, dz)
        ring = _smooth(0.0135, 0.019, r) * _smooth(0.036, 0.024, r)
        front = _smooth(e[1] + 0.022, e[1] + 0.008, C[:, 1])
        w = ring * front * skin * (np.sign(C[:, 0]) == np.sign(e[0]))
        w *= 0.75 + 0.25 * np.abs(dz) / np.maximum(r, 1e-6)          # more above and below than at the corners
        C[:, 1] += depth * w
    return C


def _deform_gaunt(C, rig, sk, cheek=0.0075, temple=0.004):
    """Hollow cheeks under the cheekbones (between them and the jaw, toward the back teeth) and hollow temples:
    pushed in toward the face's middle and a little back. Skin only."""
    C = C.copy()
    skin = F._skin(len(C))
    el, er = rig.centre(C, "helper-l-eye"), rig.centre(C, "helper-r-eye")
    for e in (el, er):
        s = np.sign(e[0])
        ax = np.abs(C[:, 0])
        side = np.sign(C[:, 0]) == s
        # cheek hollow: below the cheekbone, out from the mouth's corner, in front of the ear
        cz = e[2] - 0.048
        cx = abs(e[0]) + 0.012
        w = (np.exp(-0.5 * ((C[:, 2] - cz) / 0.014) ** 2) * np.exp(-0.5 * ((ax - cx) / 0.016) ** 2)
             * _smooth(e[1] + 0.06, e[1] + 0.025, C[:, 1]) * side * skin)
        C[:, 0] -= s * cheek * w
        C[:, 1] += 0.4 * cheek * w
        # temple: behind the eye's outer corner, above it
        tz = e[2] + 0.018
        w = (np.exp(-0.5 * ((C[:, 2] - tz) / 0.014) ** 2) * _smooth(abs(e[0]) + 0.025, abs(e[0]) + 0.04, ax)
             * np.exp(-0.5 * ((C[:, 1] - (e[1] + 0.035)) / 0.016) ** 2) * side * skin)
        C[:, 0] -= s * temple * w
    return C


# ------------------------------------------------------------------ the ghoul's body (2026-10-23: a zombie type with
# big claws and an arched posture; the Ghoul builds, hum_ghoul for its claws). The arch itself is a runtime bend
# (Unity HumanPosture: the spine turned forward after the Animator); these shapes give the body it bends.

def _stretch(C, sk, ext):
    """Bones lengthened along themselves, `ext` {bone: metres}: a vertex on a stretched bone moves by how far along
    the bone it lies (0 at its head .. ext at its tail), by its skin weights; every bone below moves with the point
    of its parent it hangs from. Joint cubes included, so the skeleton follows."""
    W = F._weights(sk, len(C))
    H, T = sk.ends(C)
    U = T - H
    L = np.maximum(np.linalg.norm(U, axis=1), 1e-9)
    U = U / L[:, None]
    t_of = lambda P, i: np.clip(((P - H[i]) @ U[i]) / L[i], 0.0, 1.0)
    D = np.zeros((len(sk.bones), 3))
    for i, b in enumerate(sk.bones):                     # parents first
        p = sk.rig[b].get("parent")
        if p in sk.index:
            ip = sk.index[p]
            D[i] = D[ip] + U[ip] * ext.get(p, 0.0) * float(t_of(H[i][None], ip)[0])
    disp = W @ D
    for b, e in ext.items():
        i = sk.index[b]
        disp += (W[:, i] * t_of(C, i) * e)[:, None] * U[i]
    return C + disp


FINGERS = ("index", "middle", "ring", "pinky")


def _deform_claws(C, rig, sk, grow=(0.3, 0.45, 0.55), thumb=(0.0, 0.25, 0.35), thin=0.25):
    """Long, thin fingers (the claws themselves are a garment, hum_ghoul): each phalanx lengthened by `grow` of its
    length (the thumb's by `thumb`), the finger's skin drawn in toward its bones by `thin`."""
    H, T = sk.ends(C)
    ext = {}
    for side in ("l", "r"):
        for f in FINGERS + ("thumb",):
            g = thumb if f == "thumb" else grow
            for k in range(3):
                b = f"{f}_0{k + 1}_{side}"
                if g[k] and b in sk.index:
                    i = sk.index[b]
                    ext[b] = g[k] * float(np.linalg.norm(T[i] - H[i]))
    W = F._weights(sk, len(C))
    skin = F._skin(len(C))
    # thin first, about the unstretched bones (the radial pull then rides along with the stretch)
    S = C.copy()
    for b in sk.bones:
        if not b.startswith(FINGERS + ("thumb_02", "thumb_03")):
            continue
        i = sk.index[b]
        u = T[i] - H[i]
        Lb = float(np.linalg.norm(u))
        u = u / Lb
        d = C - H[i]
        t = np.clip(d @ u, 0.0, Lb)
        rad = d - t[:, None] * u
        near = _smooth(0.022, 0.014, np.linalg.norm(rad, axis=1))
        S -= rad * (thin * W[:, i] * skin * near)[:, None]
    return _stretch(S, sk, ext)


def _deform_long_arms(C, rig, sk, upper=0.025, fore=0.04):
    """Longer arms: the upper arm by `upper`, the forearm by `fore` (metres), stretched evenly along each."""
    ext = {}
    for side in ("l", "r"):
        ext["upperarm_" + side] = upper
        ext["lowerarm_" + side] = fore
    return _stretch(C, sk, ext)


def _deform_short_legs(C, rig, sk, thigh=0.10, calf=0.09):
    """Shorter legs (the imps): the thigh by `thigh`, the calf by `calf` (metres, evenly along each), then everything
    lowered by how far the ankles rose, so the feet stay on the floor and the pelvis carries the drop (Unity lowers
    the model by the hips' delta)."""
    ext = {}
    for side in ("l", "r"):
        ext["thigh_" + side] = -thigh
        ext["calf_" + side] = -calf
    rise = np.mean([sk.ends(_stretch(C, sk, ext))[0][sk.index["foot_" + s], 2] - sk.ends(C)[0][sk.index["foot_" + s], 2]
                    for s in ("l", "r")])
    ground = rig.groups["joint-ground"]                        # full_coords re-grounds by this helper: it stays put
    keep = C[ground].copy()
    C = _stretch(C, sk, ext)
    C[:, 2] -= rise
    C[ground] = keep
    return C


def _deform_arch(C, rig, sk, shrug=0.022, fwd=0.012, head_fwd=0.03, head_drop=0.012, hump=0.028, blade=0.011):
    """More than the Hunch, for a back the runtime bend arches: the shoulders hunched up and forward (bone offsets,
    like Hunch), the head carried further forward, a broad hump from mid-back to the neck and the shoulder blades
    standing out (skin only)."""
    W = F._weights(sk, len(C))
    skin = F._skin(len(C))
    H, j, cy = _torso_frame(C, sk)
    D = np.zeros((len(sk.bones), 3))
    for side in ("l", "r"):
        D[sk.index["clavicle_" + side]] = (0.0, -fwd * 0.5, shrug * 0.6)
        for b in F._limb(sk, "upperarm_" + side):
            D[sk.index[b]] = (0.0, -fwd, shrug)
    D[sk.index["neck_01"]] = (0.0, -head_fwd * 0.6, -head_drop * 0.5)
    D[sk.index["head"]] = (0.0, -head_fwd, -head_drop)
    C = C + W @ D
    a, rad = _around(C, cy)
    z, ax = C[:, 2], np.abs(C[:, 0])
    back = _smooth(0.55, 0.85, a) * skin
    zc = j["spine_02"][2] + 0.6 * (j["neck_01"][2] - j["spine_02"][2])
    m = np.exp(-0.5 * ((z - zc) / 0.11) ** 2) * back * _smooth(0.24, 0.15, ax)
    C[:, 1] += hump * m
    C[:, 2] -= 0.15 * hump * m
    zb = j["spine_03"][2] + 0.01                              # the blades: below the shoulders' top, either side
    for s in (-1.0, 1.0):
        q = np.exp(-0.5 * (((C[:, 0] - s * 0.08) / 0.032) ** 2 + ((z - zb) / 0.05) ** 2))
        C[:, 1] += blade * q * back
    return C


def _deform_lipless(C, rig, sk, ahead=0.0025, reach=0.004):
    """Lips shrunk back onto the teeth (the ghoul's face): no lip may stand further forward than `ahead` in front of
    MPFB's upper-teeth helper, the skin within `reach` of the lips eased along. Skin only."""
    import bpy
    import hum_mpfb
    from mathutils.kdtree import KDTree
    C = C.copy()
    src = bpy.data.objects[hum_mpfb.SOURCE]
    skin = F._skin(len(C))
    lips = np.asarray(hum_mpfb.group_members(src, "lips"))
    teeth = np.asarray(hum_mpfb.group_members(src, "helper-upper-teeth"))
    front = float(C[teeth, 1].min()) - ahead                  # MPFB: -Y is the front
    kd = KDTree(len(lips))
    for k, i in enumerate(lips):
        kd.insert(C[i], k)
    kd.balance()
    mc = C[lips].mean(0)
    near = np.linalg.norm(C - mc, axis=1) < 0.08
    w = np.zeros(len(C))
    for i in np.where(near & skin)[0]:
        w[i] = _smooth(reach, 0.0, kd.find(C[i])[2])
    over = np.maximum(front - C[:, 1], 0.0)                   # how far in front of the line
    C[:, 1] += over * w
    return C


DEFORMS = {"hunch": _deform_hunch, "ribs": _deform_ribs, "sunken": _deform_sunken, "bony": _deform_bony,
           "eye_sunken": _deform_eye_sunken, "gaunt": _deform_gaunt,
           "claws": _deform_claws, "long_arms": _deform_long_arms, "arch": _deform_arch, "lipless": _deform_lipless,
           "short_legs": _deform_short_legs}


# ------------------------------------------------------------------ rot (painted: T_Head_Rot, T_Body_Rot)
#
# R blotches (decay patches), G wounds (first set), B wounds (second set), A hollows (dark: eye sockets, hollow
# cheeks and temples; on the body the painted ribs, the ribcage's edge, collarbone pits, the spine's knobs). The
# skin shaders take a per-character `rot` (0 for the living) and a weight per wound set (Humans/Skin, Humans/Body):
#     c = lerp(c, c * ROT_TINT, R * rot);  c *= 1 - HOLLOW * A * rot
#     w = max(G * woundsA, B * woundsB) * (rot > 0);  c = lerp(c, WOUND_RIM, ss(.12, .45, w)); lerp(.., WOUND_CORE, ss(.5, .85, w))

ROT_TINT = (0.55, 0.50, 0.52)        # blotches: darker, toward a bruised purple-brown (multiplies the tone)
HOLLOW = 0.6
WOUND_RIM = (0.30, 0.10, 0.08)       # linear: raw, dark red flesh
WOUND_CORE = (0.06, 0.012, 0.01)     # nearly black, clotted


def _seg_dist(P, pts):
    """Distance from points P (..., 3) to a polyline."""
    best = np.full(P.shape[:-1], np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
        d = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)
        best = np.minimum(best, d)
    return best


def _wound(P, pts, r, valid, seed):
    """A ragged wound along a polyline on the skin: 0 outside .. 1 at its middle (the shader thresholds a red rim
    and a dark core out of it)."""
    import hum_paint
    d = _seg_dist(P, pts)
    near = valid & (d < r * 2.2)
    jag = np.zeros(P.shape[:-1])
    if near.any():
        jag = hum_paint._noise3(P, 260.0, seed, near) * r * 0.55 + hum_paint._noise3(P, 900.0, seed + 1, near) * r * 0.2
    return np.clip(1.0 - (d + jag) / r, 0.0, 1.0) ** 0.8


def _rest_and_zero(ob):
    import hum_rig
    import bpy
    hum_rig.rest(bpy.data.objects["HumanRig"])
    saved = {}
    if ob.data.shape_keys:
        for kb in ob.data.shape_keys.key_blocks[1:]:
            saved[kb.name] = kb.value
            kb.value = 0.0
    return saved


def _restore_keys(ob, saved):
    for k, v in saved.items():
        ob.data.shape_keys.key_blocks[k].value = v


def paint_rot_head(size=1024):
    """T_Head_Rot for the neutral head (keys at 0, rest pose)."""
    import os
    import bpy
    import hum_paint
    ss = hum_paint.smoothstep
    ob = bpy.data.objects["Head"]
    saved = _rest_and_zero(ob)
    try:
        Fc = hum_paint.Face(ob)
        P, valid = hum_paint.bake_map(ob, "pos", size)
    finally:
        _restore_keys(ob, saved)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ax = np.abs(x)
    el, rl = Fc.eye["l"][0], Fc.eye["l"][1]
    er = Fc.eye["r"][0]
    blot = (hum_paint._noise3(P, 16.0, 31, valid) + 0.5 * hum_paint._noise3(P, 44.0, 32, valid))
    R = ss(0.12, 0.55, blot)
    # hollows
    A = np.zeros(x.shape)
    for e in (el, er):
        side = np.sign(x) == np.sign(e[0])
        d = np.hypot(x - e[0], (z - e[2]) * 1.15)
        front = ss(e[1] + 0.025, e[1] + 0.005, y)
        sock = np.maximum(ss(0.034, 0.02, d) * ss(0.009, 0.015, d), 0.55 * ss(0.03, 0.012, d))
        A = np.maximum(A, sock * front * side)
        ch = np.exp(-0.5 * (((z - (e[2] - 0.048)) / 0.015) ** 2 + ((ax - (abs(e[0]) + 0.014)) / 0.017) ** 2))
        A = np.maximum(A, 0.7 * ch * side * ss(e[1] + 0.06, e[1] + 0.02, y))
        tp = np.exp(-0.5 * (((z - (e[2] + 0.018)) / 0.016) ** 2 + ((y - (e[1] + 0.035)) / 0.018) ** 2))
        A = np.maximum(A, 0.45 * tp * side * ss(abs(e[0]) + 0.02, abs(e[0]) + 0.04, ax))
    m = Fc.mouth
    A = np.maximum(A, 0.5 * np.exp(-0.5 * (((ax - (Fc.mouth_w / 2 + 0.004)) / 0.006) ** 2
                                          + ((z - m[2]) / 0.008) ** 2)) * ss(m[1] + 0.03, m[1], y))
    # wounds: set A - a gash down the left cheek and a scrape over the right brow; set B - a bite torn out of
    # the right jaw and a split in the scalp
    def surf(p):
        from mathutils import Vector
        import bmesh
        from mathutils.bvhtree import BVHTree
        if not hasattr(surf, "bvh"):
            bm = bmesh.new(); bm.from_mesh(ob.data)
            surf.bvh = BVHTree.FromBMesh(bm); bm.free()
        return np.array(surf.bvh.find_nearest(Vector(p))[0])
    c = np.array([0.0, el[1] + 0.03, el[2]])
    s = np.sign(el[0])
    gA = [surf(el + np.array([s * 0.004, -0.01, -0.022])), surf(el + np.array([s * 0.02, 0.0, -0.045])),
          surf(el + np.array([s * 0.03, 0.012, -0.07]))]
    brow = [surf(er + np.array([np.sign(er[0]) * -0.006, -0.02, 0.03])),
            surf(er + np.array([np.sign(er[0]) * 0.02, -0.005, 0.042]))]
    G = np.maximum(_wound(P, gA, 0.012, valid, 41), 0.7 * _wound(P, brow, 0.008, valid, 42))
    jaw = [surf(np.array([er[0] * 1.6, er[1] + 0.05, m[2] - 0.012])),
           surf(np.array([er[0] * 1.5, er[1] + 0.06, m[2] - 0.035]))]
    top = Fc.top
    scalp = [surf(top + np.array([0.02, 0.03, 0.0])), surf(top + np.array([0.045, 0.06, -0.03]))]
    B = np.maximum(_wound(P, jaw, 0.019, valid, 43), 0.8 * _wound(P, scalp, 0.01, valid, 44))
    R = np.clip(R + 0.6 * ss(0.0, 0.6, np.maximum(G, B) * 3), 0, 1)       # bruised round the wounds
    M = np.stack([R, G, B, A], -1)
    M[~valid] = 0
    M = hum_paint.dilate(M, valid)
    return hum_paint.save_image("T_Head_Rot", M, os.path.join(hum_paint.TEX_DIR, "T_Head_Rot.png"))


def paint_rot_body(size=1024):
    """T_Body_Rot for the neutral body (keys at 0, rest pose): the ribs and the ribcage's edge painted where the
    Undead build's shapes put them (rib_phase / _costal_z, the same lines), collarbone pits, the spine's knobs,
    blotches heavier on the hands, feet and shins, two wound sets."""
    import os
    import bpy
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import hum_paint
    import hum_rig
    ss = hum_paint.smoothstep
    ob = bpy.data.objects["Body"]
    arm = bpy.data.objects["HumanRig"]
    sk = hum_rig.SK
    saved = _rest_and_zero(ob)
    try:
        me = ob.data
        co, no, e = hum_paint.mesh_arrays(me)
        W = hum_rig.weights_of(ob, sk)
        grp = lambda names: W[:, [sk.index[n] for n in names if n in sk.index]].sum(1)
        torso = grp(["pelvis", "spine_01", "spine_02", "spine_03"])
        ext = grp([b for b in sk.bones if b.startswith(("hand", "thumb", "index", "middle", "ring", "pinky",
                                                         "foot", "ball", "calf"))])
        hum_paint.write_attr(me, "_hu_a", np.stack([torso, ext, np.zeros(len(co))], 1))
        P, valid = hum_paint.bake_map(ob, "pos", size)
        Aat, _ = hum_paint.bake_map(ob, "attr", size, "_hu_a")
        bm = bmesh.new(); bm.from_mesh(me); bvh = BVHTree.FromBMesh(bm); bm.free()
    finally:
        _restore_keys(ob, saved)
    TORSO, EXT = Aat[..., 0], Aat[..., 1]
    j = {b.name: np.array(b.head_local) for b in arm.data.bones}
    jt = {b.name: np.array(b.tail_local) for b in arm.data.bones}
    cy = float(np.mean([j[b][1] for b in ("spine_01", "spine_02", "spine_03")]))
    flat = P.reshape(-1, 3)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]

    def skin_pt(bone, t, ang, out=0.0):
        """The skin over a bone: t along it, ang (degrees) round it from the front toward the body's outside."""
        a, b = j[bone], jt[bone]
        u = (b - a) / np.linalg.norm(b - a)
        f = np.array([0.0, -1.0, 0.0]); f -= u * (f @ u); f /= np.linalg.norm(f)
        side = np.cross(u, f)
        s = np.sign(a[0]) if abs(a[0]) > 0.01 else 1.0
        if side[0] * s < 0:
            side = -side
        r = np.radians(ang)
        d = f * np.cos(r) + side * np.sin(r)
        o = a + (b - a) * t
        hit = bvh.ray_cast(Vector(o + d * 0.4), Vector(-d), 0.5)[0]
        return np.array(hit) if hit is not None else o

    # blotches: everywhere, heavier toward the hands, feet and shins (the blood settles)
    blot = (hum_paint._noise3(P, 9.0, 51, valid) + 0.5 * hum_paint._noise3(P, 26.0, 52, valid))
    R = ss(0.18 - 0.25 * EXT, 0.6 - 0.2 * EXT, blot)
    # hollows: between the ribs, under the ribcage's edge, the collarbones' pits, between the spine's knobs
    p, a, n = rib_phase(flat, j, cy)
    p, a = p.reshape(x.shape), a.reshape(x.shape)
    groove = (0.5 - 0.5 * np.cos(2 * np.pi * p)) ** 1.6
    m = ss(0.3, 1.0, p) * ss(n + 0.3, n - 0.6, p) * ss(0.93, 0.75, a) * ss(0.012, 0.03, np.abs(x)) * ss(0.4, 0.8, TORSO)
    nip = j["clavicle_l"][2] - 0.085
    m *= 1.0 - 0.7 * ss(nip - 0.04, nip, z) * ss(0.45, 0.2, a)
    A = 0.75 * groove * m
    zc = _costal_z(j, x)
    edge = ss(zc + 0.002, zc - 0.01, z) * ss(zc - 0.06, zc - 0.015, z) * ss(0.5, 0.25, a) * ss(0.4, 0.8, TORSO)
    A = np.maximum(A, 0.8 * edge)
    for side in ("l", "r"):
        c0, c1 = j["clavicle_" + side].copy(), j["upperarm_" + side]
        c0[0] = np.sign(c1[0]) * 0.02
        dz = z - (c0[2] + (np.clip((x - c0[0]) / (c1[0] - c0[0]), 0, 1)) * (c1[2] - c0[2]))
        along = ss(-0.1, 0.1, (x - c0[0]) / (c1[0] - c0[0])) * ss(1.0, 0.75, (x - c0[0]) / (c1[0] - c0[0]))
        front = ss(cy - 0.01, cy - 0.04, y)
        A = np.maximum(A, 0.8 * np.exp(-0.5 * ((dz - 0.018) / 0.008) ** 2) * along * front)
        A = np.maximum(A, 0.45 * np.exp(-0.5 * ((dz + 0.02) / 0.009) ** 2) * along * front)
    knobs = (0.5 - 0.5 * np.cos(2 * np.pi * (z - j["spine_02"][2]) / 0.024)) ** 2
    back = ss(cy + 0.03, cy + 0.06, y) * ss(0.02, 0.006, np.abs(x)) * ss(j["spine_01"][2], j["spine_02"][2], z) \
        * ss(j["neck_01"][2], j["neck_01"][2] - 0.04, z)
    A = np.maximum(A, 0.6 * knobs * back)
    # wounds. Set A: a bite out of the left forearm, a gash across the belly, the left shoulder bitten to the
    # collarbone. Set B: the right thigh torn open, the left flank's ribs, a bite in the right upper arm, the
    # right calf.
    gA = [skin_pt("lowerarm_l", t, 80) for t in (0.45, 0.6)]
    belly = [skin_pt("spine_03", 0.1, -40), skin_pt("spine_02", 0.3, -10), skin_pt("spine_01", 0.4, 20)]
    sh = [skin_pt("clavicle_l", t, -20) for t in (0.45, 0.8)]
    G = np.maximum.reduce([_wound(P, gA, 0.032, valid, 61), _wound(P, belly, 0.02, valid, 62),
                           _wound(P, sh, 0.03, valid, 63)])
    th = [skin_pt("thigh_r", t, 10) for t in (0.3, 0.45, 0.6)]
    flank = [skin_pt("spine_02", t, 115) for t in (0.4, 1.0)]
    flank = [np.array([abs(q[0]), q[1], q[2]]) for q in flank]          # the left side
    ua = [skin_pt("upperarm_r", t, 60) for t in (0.4, 0.55)]
    cf = [skin_pt("calf_r", t, 160) for t in (0.3, 0.42)]
    B = np.maximum.reduce([_wound(P, th, 0.026, valid, 64), _wound(P, flank, 0.04, valid, 65),
                           _wound(P, ua, 0.028, valid, 66), _wound(P, cf, 0.024, valid, 67)])
    R = np.clip(R + 0.6 * ss(0.0, 0.6, np.maximum(G, B) * 3), 0, 1)
    M = np.stack([R, G, B, np.clip(A, 0, 1)], -1)
    M[~valid] = 0
    M = hum_paint.dilate(M, valid)
    return hum_paint.save_image("T_Body_Rot", M, os.path.join(hum_paint.TEX_DIR, "T_Body_Rot.png"))


# ------------------------------------------------------------------ torn clothes (T_Cloth_Tatter)

def tatter_texture(size=512, seed=23):
    """T_Cloth_Tatter (tiling, projected in 3D from each garment's rest position, hum_material.TATTER_TILE): R the
    hole field, equalised (so `tatter * TATTER_HOLES` is the torn area), G dirt and stains, B fine fray noise for
    ragged edges. Periodic by construction: a sum of waves with whole numbers of periods across the tile."""
    import os
    import hum_paint
    rng = np.random.default_rng(seed)
    u = np.arange(size) / size
    X, Y = np.meshgrid(u, u)

    def waves(lo, hi, count, fall=1.0):
        """`count` waves, every direction alike: whole-number wave vectors with lo <= |k| <= hi (a first version
        drew each component from lo..hi, so no wave ran along an axis and the holes came out as diagonal
        stripes)."""
        ks = [(a, b) for a in range(-hi, hi + 1) for b in range(-hi, hi + 1) if lo <= np.hypot(a, b) <= hi]
        out = np.zeros((size, size))
        for i in rng.choice(len(ks), size=min(count, len(ks)), replace=False):
            k = ks[i]
            amp = 1.0 / (np.hypot(*k) ** fall)
            out += amp * np.cos(2 * np.pi * (k[0] * X + k[1] * Y) + rng.uniform(0, 2 * np.pi))
        return out

    hole = waves(5, 9, 50) + 0.5 * waves(10, 18, 70)
    order = np.argsort(hole.ravel())
    eq = np.empty(size * size)
    eq[order] = np.linspace(0, 1, size * size)
    dirt = waves(1, 4, 24)
    dirt = hum_paint.smoothstep(-0.2, 0.8, dirt / np.abs(dirt).max())
    fray = waves(20, 48, 80, 0.5)
    fray = 0.5 + 0.5 * fray / np.abs(fray).max()
    M = np.stack([eq.reshape(size, size), dirt, fray, np.ones((size, size))], -1)
    return hum_paint.save_image("T_Cloth_Tatter", M, os.path.join(hum_paint.TEX_DIR, "T_Cloth_Tatter.png"))


# ------------------------------------------------------------------ the presets

ZOMBIE = dict(
    name="Zombie",
    sliders={"CheekFull": (-0.6, 0.15), "FaceFat": (-0.7, 0.1), "CheekBones": (0.45, 0.15),
             "EyeSunken": (0.85, 0.12), "Gaunt": (0.85, 0.12), "MouthCorners": (-0.5, 0.15),
             "LipUpper": (-0.45, 0.15), "LipLower": (-0.3, 0.15), "EyeOpen": (0.2, 0.2), "BrowHeight": (-0.15, 0.15)},
    build="Undead",
    fem_scale=1.0,
    # livid, grey-green, bloodless; a few yellowed
    tones=["#8e9680", "#7f8b72", "#9a9c86", "#848b8a", "#8b8f84", "#a19c7c", "#737c66", "#959f93"],
    lip_from_tone=(0.58, 0.5, 0.58),          # dark, bluish lips
    irises=["#c8cec6", "#b7c1c3", "#d4d1bd", "#aab4b2", "#c3c7b6"],
    milk=(0.7, 1.0),                          # clouded: the pupil fades into a pale iris
    hair_styles=["Long", "Long", "Crop", "Buzz", "", "Ponytail", "Swept"],
    hair_colors=["grey", "ash", "dark_brown", "black", "brown", "white"],
    beard="", beard_color="",                 # a villager's beard stays
    brows=["Thin", "Normal", "Straight"],
    height=(-0.4, 0.4),
    sex_min=0.0,
    blush=(0.0, 0.0),
    rot=(0.65, 1.0),
    wound_chance=(0.7, 0.55),                 # wound set A, set B (at least one)
    tatter=(0.35, 0.75), tatter_cut=False,    # torn and dirty; the holes show the skin
)

SKELETON = dict(
    name="Skeleton",
    sliders={},
    build="Undead",
    fem_scale=1.0,
    tones=[], irises=[], hair_styles=[""], hair_colors=[], beard="", beard_color="", brows=[],
    height=(-0.3, 0.5),
    sex_min=0.0,
    blush=(0.0, 0.0),
    wear=["Skeleton"],                        # the bones (hum_skeleton): body and head hidden
    tatter=(0.5, 0.9), tatter_cut=True,       # rags: real holes, the bones show through
    glow=["#7ee0d4", "#8fd0ff"],              # the eye sockets' light
)

GHOUL = dict(
    # a zombie type (2026-10-23): hairless, ashen, white-eyed, long clawed fingers, the back arched at runtime
    name="Ghoul",
    sliders={"CheekFull": (-0.9, 0.1), "FaceFat": (-0.9, 0.1), "CheekBones": (0.7, 0.15), "EyeSunken": (1.0, 0.0),
             "Gaunt": (1.0, 0.0), "EarPointed": (0.7, 0.2), "EarSize": (0.3, 0.2), "MouthCorners": (-0.9, 0.1),
             "MouthWidth": (0.4, 0.15), "Lipless": (1.0, 0.0), "EyeOpen": (0.3, 0.15), "BrowHeight": (-0.6, 0.15),
             "BrowHeavy": (0.8, 0.15), "BrowRidge": (0.8, 0.15), "NoseDepth": (-0.8, 0.15), "HeadLength": (0.35, 0.2),
             "ChinForward": (0.3, 0.2), "Underbite": (0.25, 0.2)},
    build="Ghoul",
    fem_scale=1.0,
    # ashen, grey to bluish, a few the yellow of old bone
    tones=["#8a8c8f", "#7d8188", "#9a9590", "#868079", "#75797a", "#a09a8e", "#6f7378"],
    lip_from_tone=(0.5, 0.45, 0.5),
    irises=["#e0d9b0", "#d8d2c0", "#e6e1cf", "#cfd4cf"],
    milk=(0.9, 1.0),                          # white eyes
    hair_styles=[""], hair_colors=["grey", "white", "black"],
    beard="", beard_color="", no_beard=True,  # hairless: no beard (a villager's beard does not stay), no brows
    brows=[""],
    height=(0.0, 0.6),
    sex_min=0.0,
    blush=(0.0, 0.0),
    rot=(0.45, 0.8),                          # drier than a zombie
    wound_chance=(0.45, 0.35),
    tatter=(0.5, 0.9), tatter_cut=False,
    wear=["GhoulClaws"],                      # dark horn (colour group "Horn", hum_ghoul.HORN)
    outfit=dict(M=["RagTrousers"], F=["RagShirt", "RagTrousers"]),   # Blender preview only: rags (the game dresses its own)
)

LICH = dict(
    # 2026-10-23 (a card-game unit; Daniel: "build the creatures"): a skeleton king-sorcerer - the Skeleton and an iron
    # crown (hum_lich), a cold light in the orbits, the magister's robe torn and cut so the bones show
    name="Lich",
    sliders={},
    build="Undead",
    fem_scale=1.0,
    tones=[], irises=[], hair_styles=[""], hair_colors=[], beard="", beard_color="", brows=[],
    height=(0.2, 0.6),
    sex_min=0.0,
    blush=(0.0, 0.0),
    wear=["Skeleton", "LichCrown"],
    tatter=(0.15, 0.35), tatter_cut=True,     # an old robe, holes cut out (more read as speckles at the game camera)
    glow=["#8cff6a", "#b98cff", "#6affd8"],   # sickly green, violet, cold cyan
    # the magister's violet and old gold (a darker violet read as black in Unity); Blender preview only
    outfit=dict(M=["Trousers:#1c1820", "Robe:#47235e", "RobeTrim:#b08a34", "Boots:#18141a"],
                F=["Trousers:#1c1820", "Robe:#47235e", "RobeTrim:#b08a34", "Boots:#18141a"]),
)

VAMPIRE = dict(
    # DEPRECATED (2026-10-23, Daniel on seeing the first preview: "wow, let's give up on the vampire, make it
    # deprecated"): kept for reference, not in PRESETS (never exported); its Fangs beard style and VampireCape are
    # unregistered too (hum_styles.DEPRECATED_BEARD, hum_cloak.DEPRECATED).
    # 2026-10-23 (a card-game unit; Daniel: "build the creatures"): a pale aristocrat - bloodless white skin, red
    # eyes, dark red lips, sharp cheekbones and nose, a little pointed at the ears, fangs (a beard style, like the
    # orcs' tusks: a woman's too), dark slicked hair. No rot. Dressed as a noble in black (VampireCape: hum_vampire)
    name="Vampire",
    sliders={"CheekBones": (0.7, 0.15), "CheekFull": (-0.6, 0.15), "FaceFat": (-0.6, 0.15), "ChinForward": (0.25, 0.15),
             "NoseLength": (0.25, 0.2), "NoseHump": (0.3, 0.25), "BrowAngle": (0.5, 0.2), "EyeSunken": (0.35, 0.1),
             "Gaunt": (0.35, 0.1), "EarPointed": (0.45, 0.15), "HeadLength": (0.2, 0.15), "MouthCorners": (-0.2, 0.15),
             "EyeTilt": (0.25, 0.2)},
    build="Slim",
    fem_scale=0.7,
    tones=["#e9e2e4", "#ddd6db", "#e6dfd6", "#d6d2d8", "#ece6e2"],
    lip_from_tone=(0.3, 0.04, 0.06),          # dark red (0.62 / 0.22 / 0.26 read pink on the white skin)
    irises=["#c41a1a", "#a8121a", "#d8302a", "#8e0f14"],
    hair_styles=["Swept", "Swept", "SidePart", "Long", "Ponytail"],
    hair_colors=["black", "black", "dark_brown", "white"],
    beard="Fangs", beard_color="#ece6d6",
    brows=["Thin", "Straight"],
    height=(0.2, 0.7),
    sex_min=0.0,
    blush=(0.0, 0.0),
    outfit=dict(M=["Shirt:#d8d0c0", "Trousers:#1c1a1e", "Boots:#141214", "Coat:#1a1616", "VampireCape:#1a1014"],
                F=["Dress:#4a0e16", "Shoes:#141214", "VampireCape:#1a1014"]),   # Blender preview only
)

PRESETS = [ZOMBIE, SKELETON, GHOUL, LICH]                    # not VAMPIRE (deprecated)
BONE = ["#d8cfb4", "#cfc4a2", "#bfb495", "#e0d8c0", "#b3a685", "#c8bb98"]     # colour group "Bone" (sRGB)


def export(p):
    """The preset as the config writes it (Unity: HumanFaceConfig.Preset)."""
    import hum_orcs
    d = hum_orcs.export(dict(p, beard_color=p.get("beard_color") or "#000000"))
    d.update(lipFromTone=list(p.get("lip_from_tone", ())), rotMin=p.get("rot", (0, 0))[0],
             rotMax=p.get("rot", (0, 0))[1], woundChance=list(p.get("wound_chance", (0.0, 0.0))),
             tatterMin=p.get("tatter", (0, 0))[0], tatterMax=p.get("tatter", (0, 0))[1],
             tatterCut=bool(p.get("tatter_cut", False)), milkMin=p.get("milk", (0, 0))[0],
             milkMax=p.get("milk", (0, 0))[1], wear=list(p.get("wear", [])), glow=list(p.get("glow", [])),
             noBeard=bool(p.get("no_beard", False)), ageMin=p.get("age", (0, 0))[0], ageMax=p.get("age", (0, 0))[1],
             headScaleMin=p.get("head_scale", (0, 0))[0], headScaleMax=p.get("head_scale", (0, 0))[1],
             beardMascOnly=bool(p.get("beard_masc_only", False)), beardFromHair=bool(p.get("beard_from_hair", False)))
    if not p.get("beard"):
        d["beard"] = ""
    return d


def undead_face(seed, preset=ZOMBIE, outfit=True):
    """A rolled face (hum_faces.random_face) made undead, for the Blender preview (Unity: HumanFaceGenerator.
    ApplyPreset): sliders, tone + lips, eyes, hair, the build, rot and wounds, torn clothes, the worn bones."""
    import random
    import hum_builds
    srgb = F.srgb
    f = F.random_face(seed)
    rng = random.Random(seed * 31 + 7)
    w = f["keys"]
    masc = f["masc"]
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
    if preset["tones"]:
        p["tone"] = srgb(rng.choice(preset["tones"]))
        k = preset.get("lip_from_tone")
        if k:
            p["lip"] = tuple(a * b for a, b in zip(p["tone"], k))
    if preset["irises"]:
        p["iris"] = srgb(rng.choice(preset["irises"]))
    p["blush"] = rng.uniform(*preset["blush"])
    p["freckles"] = 0.0
    p["stubble"] = 0.0
    if preset["hair_colors"]:
        root = srgb(F.HAIR[rng.choice(preset["hair_colors"])])
        f["hair_colors"] = dict(root=root)
        f["brow_colors"] = dict(root=tuple(c * 0.8 for c in root))
        p["hair"] = root
    if preset["hair_styles"]:
        f["style"] = rng.choice(preset["hair_styles"]) or None
    if preset["brows"]:
        f["brow_style"] = rng.choice(preset["brows"])
    if preset.get("beard") and (masc or not preset.get("beard_masc_only")):
        f["beard"] = preset["beard"]
        if preset.get("beard_color"):
            f["beard_colors"] = dict(root=srgb(preset["beard_color"]))
        elif preset.get("beard_from_hair") and f.get("hair_colors"):      # the dwarves: the beard in the hair's colour
            f["beard_colors"] = dict(f["hair_colors"])
    if preset.get("no_beard"):
        f["beard"] = None
        p["beard_shadow"] = 0.0
    p["scalp"] = 0.0 if f.get("style") in (None, "Mohawk") else p.get("scalp", 1.0)
    f["height"] = rng.uniform(*preset["height"])
    tag = hum_builds.tag_of(masc, preset["build"])
    w2 = {k: v for k, v in w.items() if k not in hum_builds.BODY_KEYS}
    w2.update(hum_builds.BUILDS[tag]["keys"])
    g = w2.get("Masculine", 0.0) - w2.get("Feminine", 0.0)
    for k, (a, b) in F.CORRECTIVES.items():
        w2[k] = g * w2.get(b, 0.0) if (a == "Masculine" and b.startswith("Anc")) else w2.get(a, 0.0) * w2.get(b, 0.0)
    f["keys"] = w2
    f["build"] = tag
    if "rot" in preset:
        ca, cb = preset["wound_chance"]
        wa, wb = float(rng.random() < ca), float(rng.random() < cb)
        if not (wa or wb):
            wa = 1.0
        f["rot"] = (rng.uniform(*preset["rot"]), wa, wb)
    if "milk" in preset:
        f["milk"] = rng.uniform(*preset["milk"])
    f["tatter"] = rng.uniform(*preset.get("tatter", (0.0, 0.0)))
    f["tatter_cut"] = 1.0 if preset.get("tatter_cut") else 0.0
    o = F.random_outfit(rng, masc) if outfit else {}
    if outfit and preset.get("outfit"):                     # "Garment" (a random cloth colour) or "Garment:#hex"
        o = {}
        for g in preset["outfit"]["M" if masc else "F"]:
            name, _, hexc = g.partition(":")
            o[name] = srgb(hexc or rng.choice(F.CLOTHS))
    import hum_cloth
    import hum_ghoul
    import hum_elemental
    import hum_wings
    palettes = {"Horn": hum_ghoul.HORN, "Blackened": F.BLACKENED, "Stone": hum_elemental.STONE,      # as GroupPalette
                "Feather": hum_wings.FEATHER}
    for gname in preset.get("wear", []):
        o[gname] = srgb(rng.choice(palettes.get(hum_cloth.GARMENTS.get(gname, {}).get("group"), BONE)))
    if preset.get("glow"):
        f["glow"] = srgb(rng.choice(preset["glow"]))
    f["outfit"] = o
    if preset.get("age"):                                   # drawn last, as ApplyPreset does (the elves: ageless)
        age = rng.uniform(*preset["age"])
        w2 = f["keys"]
        w2.pop("Young", None)
        w2.pop("Old", None)
        if age < 0.12:
            w2["Young"] = (0.12 - age) / 0.12 * 0.8
        else:
            w2["Old"] = (age - 0.12) * 0.75
        g = w2.get("Masculine", 0.0) - w2.get("Feminine", 0.0)
        for k, (a, b) in F.CORRECTIVES.items():
            w2[k] = g * w2.get(b, 0.0) if (a == "Masculine" and b.startswith("Anc")) else w2.get(a, 0.0) * w2.get(b, 0.0)
        p["age"] = max(0.0, (age - 0.4) / 0.6) * 1.1          # the painted age lines
        f["age"] = age
    return f


def refresh_materials():
    """Rebuild the shared Blender materials in place with the undead's inputs (rot, milk, tatter): skin, eye, body
    and every fabric (hum_cloth.garment_material's settings)."""
    import bpy
    import hum_material as M
    img = bpy.data.images.get
    M.skin_material(img("T_Head_MaskA"), img("T_Head_MaskB"), img("T_Head_MaskC"))
    M.eye_material(img("T_Eye_Mask"))
    M.body_material(img("T_Body_MaskA"), img("T_Body_MaskB"))
    for name, tex, rough in (("M_HumanCloth", "T_Cloth_Weave", 0.85), ("M_HumanLeather", "T_Cloth_Leather", 0.6),
                             ("M_HumanQuilt", "T_Cloth_Quilt", 0.9), ("M_HumanMail", "T_Cloth_Mail", 0.5),
                             ("M_HumanFur", "T_Cloth_Fur", 0.95)):
        if bpy.data.materials.get(name) is not None:
            M.cloth_material(img(tex), name, roughness=rough)
