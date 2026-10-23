"""The lich (2026-10-23, a card-game unit; Daniel: "build the creatures"): a skeleton (hum_skeleton) in the magister's
robe, torn and cut (the bones show through), a cold light in its orbits, and an iron crown.

LichCrown is a garment like the Skeleton (its own maker, the Undead builds only, slot `crown`, material `plate`,
colour group Blackened): a band of blackened iron fitted to that build's skull - lower over the brow, higher at the
back, as a crown sits - with jagged points rising from it, the front ones tallest. Rigid on the head bone. Built in
build space after the Skeleton (it measures the skull's cranium, which is the head's, capped).

    hum_builds.build_wardrobe(scene, arm, sk, tags=["MUndead", "FUndead"], names=["LichCrown"])
"""
import math

import numpy as np

import hum_cloth as C

BAND = dict(front=0.034, back=0.044, height=0.026, thick=0.005, clear=0.004)   # above the orbits' lights (m)
POINTS = 9                                       # jagged points round the band
POINT_H = (0.05, 0.032)                          # tallest (front) .. shortest (back)
LODS = {0: dict(segs=72, points=True), 1: dict(segs=36, points=True), 2: dict(segs=18, points=False)}


def skull(B):
    """(points of the cranium and face, the orbits' light centre z) of this build's skeleton, in build space."""
    import bpy
    import hum_builds
    import hum_rig
    sk = hum_rig.SK
    ob = bpy.data.objects[C.cloth_name("Skeleton")]
    P = hum_builds.build_coords(ob, sk)
    W = hum_rig.weights_of(ob, sk)
    on_head = W[:, sk.index["head"]] > 0.5
    glow = np.zeros(len(P), bool)
    for p in ob.data.polygons:
        if p.material_index == 1:
            glow[list(p.vertices)] = True
    z_eye = float(P[glow, 2].mean()) if glow.any() else float(B.j["head"][2]) + 0.06
    return P[on_head & ~glow], z_eye


def ring(P, c, z_eye, segs):
    """Per angle (0 = the front, MPFB -Y) the band's height and its inner radius: the cranium's support in that
    direction within a slice at that height, smoothed, plus a little clearance."""
    th = np.linspace(0.0, 2 * math.pi, segs, endpoint=False)
    zb = z_eye + BAND["front"] + (BAND["back"] - BAND["front"]) * (1 - np.cos(th)) / 2
    r = np.zeros(segs)
    for k in range(segs):
        d = np.array([math.sin(th[k]), -math.cos(th[k])])
        sl = np.abs(P[:, 2] - (zb[k] + BAND["height"] * 0.4)) < 0.012
        Q = P[sl][:, :2] - c
        r[k] = float((Q @ d).max()) if len(Q) else 0.08
    for _ in range(3):
        r = 0.5 * r + 0.25 * (np.roll(r, 1) + np.roll(r, -1))
    return th, zb, r + BAND["clear"]


def crown_parts(P, z_eye, lod=0):
    """[(V, faces, t)] of the crown: the band as a closed tube of quads (outer, top, inner, bottom), then each point a
    closed flat-sided wedge on the band's top, leaning out a little (separate pieces: each is wound outward on its own)."""
    L = LODS[lod]
    up = P[P[:, 2] > z_eye]
    c = up[:, :2].mean(0)
    th, zb, r = ring(P, c, z_eye, L["segs"])
    n = len(th)
    T, h = BAND["thick"], BAND["height"]
    rad = np.stack([np.sin(th), -np.cos(th)], 1)
    V, F, t = [], [], []

    def at(k, rr, z):
        return np.array([c[0] + rad[k, 0] * rr, c[1] + rad[k, 1] * rr, z])

    for k in range(n):                            # 4 per column: inner-bottom, outer-bottom, outer-top, inner-top
        V += [at(k, r[k], zb[k]), at(k, r[k] + T, zb[k]), at(k, r[k] + T, zb[k] + h), at(k, r[k], zb[k] + h)]
        t += [0.3, 0.6, 1.0, 0.8]
    for k in range(n):
        a, b = 4 * k, 4 * ((k + 1) % n)
        for i in range(4):
            j = (i + 1) % 4
            F.append((a + i, b + i, b + j, a + j))
    parts = [(np.array(V), F, np.array(t))]
    if L["points"]:
        rng = np.random.default_rng(41)
        for m in range(POINTS):
            ang = 2 * math.pi * m / POINTS
            k0 = int(round(ang / (2 * math.pi) * n)) % n
            half = max(1, int(n / POINTS * 0.32))
            ka, kb = (k0 - half) % n, (k0 + half) % n
            tall = POINT_H[1] + (POINT_H[0] - POINT_H[1]) * (1 + math.cos(ang)) / 2
            tall *= rng.uniform(0.85, 1.15)
            lean = 0.18 * tall                                        # out from the head
            V, t = [], []
            base = 0
            for kk, rr in ((ka, 0.0), (kb, 0.0)):
                V += [at(kk, r[kk], zb[kk] + h * 0.9), at(kk, r[kk] + T, zb[kk] + h * 0.9)]
                t += [0.8, 1.0]
            tip_r = r[k0] + T * 0.5 + lean
            tip_z = zb[k0] + h + tall
            V += [at(k0, tip_r - T * 0.4, tip_z), at(k0, tip_r + T * 0.4, tip_z)]
            t += [1.0, 1.0]
            ia, oa, ib, ob, it, ot = base, base + 1, base + 2, base + 3, base + 4, base + 5
            F = [(oa, ob, ot), (ib, ia, it), (ia, oa, ot, it), (ob, ib, it, ot), (ia, ib, ob, oa)]
            parts.append((np.array(V), F, np.array(t)))
    return parts


def build(scene, B, name, arm, sk, body=None):
    """Cloth_LichCrown_<tag> and its LODs in the current build space; returns the LOD0 object."""
    import hum_builds
    import hum_ghoul
    import hum_rig
    hum_rig.rest(arm)
    P, z_eye = skull(B)
    out = None
    for lod in (0, 1, 2):
        nm = C.cloth_name(name) + ("" if lod == 0 else f"_L{lod}")
        ob = hum_ghoul.make_object(scene, nm, [(V, F, "head", t) for V, F, t in crown_parts(P, z_eye, lod)], arm, sk, lod,
                                   material=C.garment_material("plate"), slot="crown")
        import math as _m
        for p in ob.data.polygons:                # smooth round the band, sharp at its corners and the points' edges
            p.use_smooth = True                   # (flat 5-degree facets read as stripes)
        ob.data.set_sharp_from_angle(angle=_m.radians(35))
        orn = ob.data.uv_layers.new(name="Ornament")    # Humans/Plate reads uv4 (0: no ornament); missing, plates
        orn.data.foreach_set("uv", np.zeros(len(ob.data.loops) * 2, np.float32))   # showed one (HANDOFF)
        ob.hide_set(True)
        ob.hide_render = True
        if lod == 0:
            out = ob
        else:
            hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
    return out


LICH_WEAR = {
    "LichCrown": dict(slot="crown", layer=0, material="plate", group="Blackened", make=build, builds=("Undead",),
                      hide=[], cover=[]),
}
