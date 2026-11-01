"""The Curves body key (2026-11-01, Daniel: "the default female body is kind of stale, can you make it curvier? Like a
prettier silluette?"). Waist and Hips (MPFB's measure-*-circ) can't do it: Waist_Neg mostly flattens the belly and the
back (11 mm in depth against 3 mm from the side), Hips_Pos keeps the widest point down at the crotch and the seat's
shelf, and pushed further they make the shelf worse.

So this draws the outline itself, by height: `PROFILE` holds what the silhouette of the FSlim build should gain at each
height (from a measured outline against a drawn one), relative to the hip and chest bones so that it fits the neutral
basis the key is stored on:

- from the front: the flanks taper in from under the ribs to the waist, and the hips' corner fills out, so the widest
  point rises from the crotch to the hip and the upper thigh comes in a little;
- from the side: the shelf on top of the seat and the fold under it fill out into one round line, the small of the back
  and the belly go in;
- the bust gets a fuller, higher upper half (Bust_Pos alone is a cone).

Arms stay out of it, bones don't move (no joint deltas), the head doesn't change. The female Slim, Strong and Heavy
builds use it (hum_builds); orcs, undead, dwarves and the rest keep their bodies.
"""
import numpy as np

import hum_faces as F

# hip (thigh bones) = 0, chest (spine_03) = 1 on the build the table was measured on
HIP_Z, CHEST_Z = 0.7584, 0.9746
# FSlim height (m), then cm gained: at the outer side, at the back (+) and at the front (+ = into the belly)
PROFILE = [
    (0.46, 0.0, 0.0, 0.0),
    (0.52, -0.1, 0.1, 0.0),
    (0.55, -0.2, 0.1, 0.0),
    (0.58, -0.3, 0.2, 0.0),
    (0.61, -0.3, 0.4, 0.0),
    (0.64, -0.3, 0.6, 0.0),
    (0.67, -0.2, 0.7, 0.0),
    (0.70, 0.0, 0.8, 0.0),
    (0.73, 0.3, 0.6, 0.0),
    (0.76, 0.8, 0.5, 0.0),
    (0.79, 1.2, 0.2, 0.0),
    (0.82, 1.15, 0.2, 0.0),
    (0.85, 0.85, 1.5, 0.1),
    (0.88, 0.4, 0.4, 0.3),
    (0.91, -0.1, -0.2, 0.5),
    (0.94, -0.7, -0.1, 0.6),
    (0.97, -1.1, -0.2, 0.6),
    (1.00, -1.1, -0.4, 0.4),
    (1.03, -0.7, -0.2, 0.2),
    (1.06, -0.4, 0.0, 0.0),
    (1.09, -0.1, 0.0, 0.0),
    (1.12, 0.0, 0.0, 0.0),
]
APEX = (0.064, -0.14, 0.1052)                   # the breast's apex on the basis, height over the chest bone
ARM_BONES = ("clavicle", "upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky")


def _bin_smooth(a, n):
    k = np.exp(-0.5 * (np.arange(-3 * n, 3 * n + 1) / n) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(a, 3 * n, mode="edge"), k, "valid")


def outline_delta(B, arm, hip, chest, side=1.0, back=1.0, front=1.0, sigma=0.012):
    """Deltas for skin coords B (n x 3); arm 0..1 per vertex; hip and chest bone heights in this space."""
    z = (B[:, 2] - hip) / (chest - hip) * (CHEST_Z - HIP_Z) + HIP_Z       # height on the measured build
    keep = arm < 0.15
    zs = np.linspace(0.3, 1.3, 201)
    hw, y0, y1 = [], [], []
    for q in zs:
        m = keep & (np.abs(z - q) < 0.012)
        hw.append(np.abs(B[m, 0]).max() if m.any() else 0.05)
        y0.append(B[m, 1].min() if m.any() else -0.05)
        y1.append(B[m, 1].max() if m.any() else 0.05)
    n = max(1, int(round(sigma / (zs[1] - zs[0]))))
    hw, y0, y1 = (_bin_smooth(np.array(a), n) for a in (hw, y0, y1))
    t = np.array(PROFILE)
    dX, dB, dF = (_bin_smooth(np.interp(zs, t[:, 0], t[:, c]) * 0.01, n) for c in (1, 2, 3))

    W = np.interp(z, zs, hw)
    yc = 0.5 * (np.interp(z, zs, y0) + np.interp(z, zs, y1))
    hd = np.maximum(0.5 * (np.interp(z, zs, y1) - np.interp(z, zs, y0)), 0.02)
    u = np.clip(np.abs(B[:, 0]) / np.maximum(W, 0.02), 0, 1)
    v = np.clip((B[:, 1] - yc) / hd, -1, 1)
    D = np.zeros_like(B)
    D[:, 0] = side * np.sign(B[:, 0]) * np.interp(z, zs, dX) * u ** 2
    D[:, 1] = back * np.interp(z, zs, dB) * F._smooth(0.05, 0.85, v) + front * np.interp(z, zs, dF) * F._smooth(0.05, 0.85, -v)
    return D * (1.0 - np.clip(arm, 0, 1))[:, None]


def bust_delta(B, arm, chest, fill=0.008, lift=0.004, sigma=0.042, swell=0.011):
    """A fuller, higher upper half centred above each breast's apex (basis coords), front only; `swell` adds volume
    all round from a point inside the breast, so a larger bust stays round where Bust_Pos alone makes a longer cone."""
    D = np.zeros_like(B)
    apex_z = chest + APEX[2]             # relative: a deform runs before full_coords grounds the body
    for s in (-1.0, 1.0):
        q = ((B[:, 0] - s * APEX[0]) ** 2 + (B[:, 1] - APEX[1]) ** 2 + (B[:, 2] - apex_z - 0.02) ** 2) / sigma ** 2
        front = F._smooth(-0.02, -0.07, B[:, 1])
        g = np.exp(-0.5 * q) * front
        D[:, 1] -= fill * g
        D[:, 2] += lift * g
        c = np.array((s * (APEX[0] + 0.004), APEX[1] + 0.035, apex_z - 0.004))
        r = B - c
        d = np.maximum(np.linalg.norm(r, axis=1), 1e-6)
        reach = np.exp(-0.5 * (d / 0.058) ** 2) * F._smooth(0.2, 0.14, d)     # ends before the neck: no key on the head
        out = r / d[:, None] * (swell * reach * front * (np.sign(B[:, 0]) == s))[:, None]
        out[:, 0] *= F._smooth(0.0, 0.035, np.abs(B[:, 0]))   # the two sides meet at the breastbone without a crease
        D += out
    return D * (1.0 - np.clip(arm, 0, 1))[:, None]


def _deform_curves(C, rig, sk):
    """The Curves key: full MPFB coords -> full coords, skin only."""
    C = C.copy()
    skin = F._skin(len(C))
    W = F._weights(sk, len(C))
    arm = W[:, [i for b, i in sk.index.items() if any(t in b for t in ARM_BONES)]].sum(1)
    j = sk.ends(C)[0]
    idx = np.where(skin)[0]
    B, a = C[idx], arm[idx]
    hip, chest = j[sk.index["thigh_l"], 2], j[sk.index["spine_03"], 2]
    C[idx] += outline_delta(B, a, hip, chest) + bust_delta(B, a, chest)
    return C


DEFORMS = {"curves": _deform_curves}
