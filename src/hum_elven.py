"""Elven clothes (2026-10-23, Daniel: "Do the number 4" - the elves wore the human coat and cloak in greens): the hems
cut into leaves, which is what reads from the top-down camera.

ElvenTunic  a long tunic: fitted torso, long sleeves widening toward the wrist, a skirt from the hips to the knee
            split up both sides (front and back panels, so the legs walk through the slits), its hem cut into
            leaf-shaped tabs (a pointed tip, full sides; the notches between them LEAF_DEPTH higher). Hangs on the
            skirt ring (HumanSkirt) like the Tunic.
ElvenCape   the Cloak's cape (hum_cloak._cloak: over the shoulders, behind the arms, the same skinning and spring
            chain in Unity - any `cloak` slot is a cape), to the knee rather than mid-calf, its hem cut into leaves;
            no hood (the elves' ears).
Both on the human builds (Slim, Strong, Heavy); colours from the cloth palette (the elves' preset: greens).
"""
import math

import numpy as np

import hum_cloth as C

R_ = C.REGIONS

LEAVES = 16                     # leaves round the tunic's hem (notches at the front, the sides and the back)
LEAF_DEPTH = 0.07               # a notch sits this far above the leaves' tips
SLIT = 0.6                      # the side slits run up this share of the skirt from its hem
SKIRT_RINGS, SKIRT_SEGS = 16, 64
CAPE_LEAVES = 9                 # leaves across the cape's hem
CAPE_LEAF_DEPTH = 0.08


def leaf_edge(u, depth):
    """A leaf's profile across its tab, u in 0..1 (0 and 1 the notches): 0 at a notch, depth at the tip; the sides
    full (convex) and the tip pointed."""
    x = np.abs(2.0 * (np.asarray(u, float) % 1.0) - 1.0)
    return depth * (1.0 - x) ** 0.45


def _elven_tunic(B):
    import hum_rags
    # the torso down 4 cm under the skirt's top (hum_rags' tunic: the shell's eased border rises ~2 cm, and ending at
    # hip_z - 0.01 left a ring of the shirt showing between it and the skirt)
    m = ((C._torso_mask(B, B.hip_z - 0.04) & (B.neck_dist() >= 0.015)) | C._arm_mask(B, 0.95)).astype(float)
    off = lambda p, i: 0.011 + (0.016 * B.s[i] ** 2 if B.part[i].startswith("arm") else 0.0)   # sleeves widen
    V, F = C.shell(B, m, off)
    V, F = C.add_rim(V, F, 0.004, B)
    knee = float(min(B.j["calf_l"][2], B.j["calf_r"][2]))
    rings, segs = SKIRT_RINGS, SKIRT_SEGS
    top, hem = B.hip_z + 0.01, knee - 0.03
    SV, SF, SU = C.loft_skirt(B, top, hem, 0.013, flare=0.24, folds=8, fold_amp=0.005, rings=rings, segs=segs)
    th = np.linspace(-math.pi, math.pi, segs + 1)               # loft_skirt's vertex columns (0 = the front)
    slit_from = int(round((rings - 1) * (1 - SLIT)))
    share = 1.0 - (LEAF_DEPTH - leaf_edge(th / (2 * math.pi) * LEAVES, LEAF_DEPTH)) / (top - hem)
    SV, SU = hum_rags._tear_hem(SV, SU, rings, segs + 1, share, from_ring=slit_from)
    # the side slits: the face columns either side of the notch at each side (th = -pi/2, +pi/2), from slit_from down
    cols = segs
    slits = {segs // 4 - 1, segs // 4, 3 * segs // 4 - 1, 3 * segs // 4}
    keep = [f for fi, f in enumerate(SF) if not (fi // cols >= slit_from and fi % cols in slits)]
    used = sorted({i for f in keep for i in f})
    remap = {v: t for t, v in enumerate(used)}
    SV, SU = np.asarray(SV)[used], np.asarray(SU)[used]
    SF = [tuple(remap[i] for i in f) for f in keep]
    return [(V, F, None, "shell"), (SV, SF, SU, "skirt")]


def _elven_cape(B):
    import hum_cloak
    knee = float(min(B.j["calf_l"][2], B.j["calf_r"][2]))
    return hum_cloak._cloak(B, hem=knee - 0.02, leaves=(CAPE_LEAVES, CAPE_LEAF_DEPTH))


BUILDS = ("Slim", "Strong", "Heavy")
ELVEN = {
    "ElvenTunic": dict(slot="outer", layer=2, material="cloth", build=_elven_tunic, skirt_follow=0.9, skirt_shell=1.0,
                       smooth_keys=10, builds=BUILDS, excludes=["Dress", "Robe", "Tunic", "RagTunic"],
                       cover=[R_["chest"], R_["belly"], R_["upperarm"]],
                       hide=[R_["chest"], R_["belly"], R_["pelvis"], R_["upperarm"], R_["forearm"], R_["thigh_up"]]),
    "ElvenCape": dict(slot="cloak", layer=5, material="cloth", build=_elven_cape, smooth_keys=10, builds=BUILDS,
                      hide=[], cover=[]),
}
