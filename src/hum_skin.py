"""Painted skin detail (2026-10-31): T_Head_MaskD, on top of hum_paint's masks. Stylised, not pores in a photo.

T_Head_MaskD  R warm: the band across cheeks, nose and ears, thin skin round the eyes, broken veins on the cheeks
              G cool: below the nose (the jaw's blue-grey), the eye sockets
              B gold: forehead, nose bridge, tops of the cheekbones
              A grain, 0.5 = none: mottling, pores (none on lids and lips), the fine lines across the lips

The painter's three zones of a face: yellow above the brows, red across the middle, cool below the nose. All of it is
evaluated at object-space positions of the neutral head, so the noise has no UV seams, and it fades out down the neck,
where the body's own skin starts. Every channel is a tint on the character's tone (hum_material / HumanSkin.shader).
`age_spots` goes into MaskB's age lines instead, so it grows with a character's age.
"""
import numpy as np

NECK_LOW, NECK_HIGH = 1.300, 1.335     # head z: nothing at the rim, all of it above the jaw


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(d2, r):
    return np.exp(-d2 / (2 * r * r))


def _hash(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h &= 0xffffffff
    h ^= h >> 13
    h = (h * 1274126177) & 0xffffffff
    h ^= h >> 16
    return (h & 0xffffff) / 0xffffff


def value_noise(P, cell, seed):
    """0..1, one value per cell (metres), P (N, 3)."""
    Q = P / cell
    I = np.floor(Q).astype(np.int64)
    f = Q - I
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        wx = f[:, 0] if dx else 1 - f[:, 0]
        for dy in (0, 1):
            wy = f[:, 1] if dy else 1 - f[:, 1]
            for dz in (0, 1):
                wz = f[:, 2] if dz else 1 - f[:, 2]
                out = out + wx * wy * wz * _hash(I[:, 0] + dx, I[:, 1] + dy, I[:, 2] + dz, seed)
    return out


def fbm(P, cell, seed, octaves=3):
    """About -1..1."""
    out, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        out = out + amp * value_noise(P, cell / 2 ** o, seed + o * 17)
        tot += amp
        amp *= 0.5
    return (out / tot - 0.5) * 2.8


def dots(P, cell, seed):
    """Distance to the nearest jittered point (in cells) + that point's random value, Worley style."""
    Q = P / cell
    I = np.floor(Q).astype(np.int64)
    best = np.full(len(P), 9.0)
    pick = np.zeros(len(P))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                C = I + (dx, dy, dz)
                J = np.stack([_hash(C[:, 0], C[:, 1], C[:, 2], seed + k) for k in range(3)], 1)
                d = np.linalg.norm(C + J - Q, axis=1)
                m = d < best
                best[m] = d[m]
                pick[m] = _hash(C[:, 0][m], C[:, 1][m], C[:, 2][m], seed + 3)
    return best, pick


def _eye_zones(P, lm):
    """Per side: above / below the lid margin, along the opening, near the eye."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    above, below, t, front = (np.zeros(len(P)) for _ in range(4))
    for s, sign in (("l", 1), ("r", -1)):
        m = x >= 0 if sign > 0 else x < 0
        xs, top, bot = lm["lid"][s]
        c = lm["eye"][s]
        above[m] = z[m] - np.interp(ax[m], xs, top)
        below[m] = np.interp(ax[m], xs, bot) - z[m]
        t[m] = (ax[m] - xs[0]) / (xs[-1] - xs[0])
        front[m] = (smoothstep(c[1] + 0.012, c[1] - 0.006, y[m]) * smoothstep(0.05, 0.035, np.linalg.norm(P[m] - c, axis=1)))
    return above, below, t, front


def paint_detail(P, N, lips, ears, valid, lm):
    """MaskD (H, W, 4). P, N (H, W, 3); lips, ears (H, W); lm: eye, lid, nose_tip, mouth, chin (hum_paint.Face)."""
    D = np.zeros(P.shape[:2] + (4,))
    D[..., 3] = 0.5
    Pv, Nv = P[valid].astype(np.float64), N[valid].astype(np.float64)
    x, y, z = Pv[:, 0], Pv[:, 1], Pv[:, 2]
    ax = np.abs(x)
    nose, mouth = lm["nose_tip"], lm["mouth"]
    eye_z = lm["eye"]["l"][2]
    eye_x = abs(lm["eye"]["l"][0])
    eye_y = lm["eye"]["l"][1]
    face = smoothstep(eye_y + 0.075, eye_y + 0.03, y)          # the front of the head, ears and scalp out
    neck = smoothstep(NECK_LOW, NECK_HIGH, z)
    lipv = smoothstep(0.35, 0.95, lips[valid])
    above, below, t, ef = _eye_zones(Pv, lm)
    along = smoothstep(-0.2, 0.05, t) * smoothstep(1.3, 1.0, t)

    cheek_d2 = (ax - (eye_x + 0.006)) ** 2 + 0.6 * (y - (eye_y - 0.012)) ** 2 + 0.8 * (z - (eye_z - 0.030)) ** 2
    cheek = gauss(cheek_d2, 0.024)
    wing = gauss((ax - 0.017) ** 2 + (y - (nose[1] + 0.022)) ** 2 + (z - (nose[2] - 0.004)) ** 2, 0.008)
    low = fbm(Pv, 0.030, 11)                                   # big slow patches of colour
    mid = fbm(Pv, 0.009, 23)
    veins = np.clip(fbm(Pv * (1, 1, 2.4), 0.0030, 31, 2) - 0.1, 0, 1)   # stringy, along the cheek

    # --- warm
    band = gauss((z - (eye_z - 0.030)) ** 2, 0.020) * face
    lid_rim = np.clip(smoothstep(0.009, 0.002, above) * smoothstep(-0.002, 0.0, above)
                      + smoothstep(0.007, 0.002, below) * smoothstep(-0.002, 0.0, below), 0, 1) * along * ef
    warm = 0.42 * band + 0.75 * ears[valid] + 0.45 * wing + 0.32 * lid_rim + 0.55 * veins * (cheek + 0.7 * wing)
    warm += 0.14 * low + 0.06 * mid

    # --- cool
    lower = smoothstep(nose[2] - 0.006, nose[2] - 0.022, z) * smoothstep(eye_y + 0.085, eye_y + 0.04, y)
    under = smoothstep(0.001, 0.004, below) * smoothstep(0.020, 0.010, below) * along * ef
    upper = smoothstep(0.0, 0.003, above) * smoothstep(0.013, 0.006, above) * along * ef
    cool = 0.75 * lower + 0.8 * under + 0.45 * upper - 0.12 * low

    # --- gold
    fore = smoothstep(eye_z + 0.006, eye_z + 0.032, z) * smoothstep(eye_z + 0.085, eye_z + 0.055, z) \
        * smoothstep(eye_y + 0.06, eye_y + 0.025, y)           # the forehead only: gold over the scalp made a bald head a yellow cap
    bridge = gauss(ax ** 2, 0.008) * smoothstep(nose[2] + 0.002, nose[2] + 0.018, z) * smoothstep(eye_z + 0.03, eye_z + 0.01, z)
    bone = gauss((ax - (eye_x + 0.018)) ** 2 + (z - (eye_z - 0.018)) ** 2, 0.012) * face
    gold = 0.55 * fore + 0.5 * bridge + 0.4 * bone + 0.10 * mid

    # --- grain
    dist, pick = dots(Pv, 0.0019, 41)
    lids = np.clip(smoothstep(0.012, 0.004, above) + smoothstep(0.012, 0.004, below), 0, 1) * ef
    pore_zone = np.clip(0.30 + 1.1 * cheek + 1.1 * gauss(ax ** 2 + (z - nose[2]) ** 2, 0.016) + 0.25 * fore, 0, 1)
    pore_zone *= (1 - lids) * (1 - lipv)
    pores = smoothstep(0.34, 0.12, dist) * (0.45 + 0.55 * pick) * pore_zone
    fine = fbm(Pv, 0.0016, 53, 2)
    # a few uneven lines across the lips: evenly spaced ones read as corduroy
    wob = 0.0024 * fbm(Pv * (1, 1, 0.35), 0.005, 61, 2)
    gaps = smoothstep(-0.05, 0.35, fbm(Pv * (1, 1, 0.25), 0.0045, 67, 2))
    creases = (0.5 + 0.5 * np.cos((ax + wob) / 0.0037 * 2 * np.pi)) ** 7 * lipv * gaps
    grain = -0.17 * pores + 0.035 * fine * (1 - lipv) + 0.055 * mid + 0.04 * low - 0.07 * creases

    fade = neck
    out = np.stack([warm * fade, cool * fade, gold * fade, 0.5 + np.clip(grain, -0.5, 0.5) * fade], 1)
    D[valid] = np.clip(out, 0, 1)
    return D


def age_spots(P, valid, lm):
    """For MaskB's age channel (H, W): a few brown marks where the sun lands: forehead, temples, cheekbones."""
    out = np.zeros(P.shape[:2])
    Pv = P[valid].astype(np.float64)
    x, y, z = Pv[:, 0], Pv[:, 1], Pv[:, 2]
    eye_z = lm["eye"]["l"][2]
    eye_x = abs(lm["eye"]["l"][0])
    eye_y = lm["eye"]["l"][1]
    d, r = dots(Pv, 0.011, 71)
    zone = np.clip(smoothstep(eye_z + 0.012, eye_z + 0.035, z)
                   + gauss((np.abs(x) - (eye_x + 0.028)) ** 2 + (z - (eye_z - 0.006)) ** 2, 0.020), 0, 1)
    zone *= smoothstep(eye_y + 0.09, eye_y + 0.05, y)
    size = 0.10 + 0.13 * (r - 0.62) / 0.38
    m = smoothstep(size, size * 0.45, d) * (r > 0.62) * zone
    m = m * (0.7 + 0.3 * fbm(Pv, 0.0035, 77, 2))
    out[valid] = np.clip(m, 0, 1)
    return out


def landmarks(F):
    return {"eye": {s: F.eye[s][0] for s in "lr"}, "lid": F.lid, "nose_tip": F.nose_tip, "mouth": F.mouth, "chin": F.chin}


def bake_detail(ob, size=1024):
    """T_Head_MaskD of the neutral head (hum_paint's bakes; the head's _hum_a / _hum_b attributes come from paint_masks)."""
    import os
    import hum_paint
    F = hum_paint.Face(ob)
    P, valid = hum_paint.bake_map(ob, "pos", size)
    N, _ = hum_paint.bake_map(ob, "nrm", size)
    A, _ = hum_paint.bake_map(ob, "attr", size, "_hum_a")
    B, _ = hum_paint.bake_map(ob, "attr", size, "_hum_b")
    D = paint_detail(P, N, A[..., 2], B[..., 1], valid, landmarks(F))
    D = hum_paint.dilate(D, valid)
    return hum_paint.save_image("T_Head_MaskD", D, os.path.join(hum_paint.TEX_DIR, "T_Head_MaskD.png"))
