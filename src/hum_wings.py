"""Wings for the humanoids (2026-10-23, the card game's demons, imps and angels; Daniel: "Keep moving on the
creatures / humanoids"). Garments with their own maker (like the Skeleton), held half raised behind the shoulders -
up, out and back, clear of the arms' swing - so they read from above.

They move (Daniel: "Do these tasks you mentioned" - the wings were rigid and swung with the chest): each wing is
skinned to a chain of helper bones off spine_03 (hum_helpers.WING: xh_wing_<side>_0 root -> elbow, _1 elbow -> wrist,
_2 wrist -> hand), which Unity's HumanWings turns at runtime (breathing, flapping, folding); rigid here in Blender.
The garments' joints are those bones' (built per build in build space, so the pivots match).

DemonWings  a bat's: an arm (shoulder -> elbow -> wrist, the wrist above the head), four finger spars fanning from
            the wrist, a membrane between them with a scalloped trailing edge, down the back to the waist; a thumb
            claw at the wrist. The membrane's foot stays on spine_03, so it stretches as the arm moves. Material
            `leather` (Humans/Cloth, double-sided), colour group Blackened.
AngelWings  a bird's: the same arm with a hand, primaries fanning from the hand, secondaries hanging from the
            forearm, tertials from the upper arm, short coverts over their roots - flat tapered blades in layers,
            each rigid on the bone its root is on. Material `bone` (pale, the bone pattern), colour group Bone.
"""
import math

import numpy as np

import hum_cloth as C

LODS = {0: dict(sides=6, coverts=True, every=1, thumb=True), 1: dict(sides=4, coverts=False, every=1, thumb=True),
        2: dict(sides=3, coverts=False, every=2, thumb=False)}
UP, BACK = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])     # MPFB: +Y is the back


def _unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-9)


def _ss(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def arm_chain(B, s):
    """(root, elbow, wrist, hand, size k, out) of the wing on side s (+1 left / -1 right): the wing bones' joints in
    the current build space (hum_helpers.WING; their rest joints + spine_03's build offset); k from the torso."""
    import hum_helpers
    sd = "l" if s > 0 else "r"
    names = hum_helpers.WING[sd]
    S, E, W = (np.asarray(B.j[n], float) for n in names)
    Hd = np.asarray(B.jt[names[2]], float)
    k = float(B.j["neck_01"][2] - B.j["pelvis"][2]) / 0.48
    return S, E, W, Hd, k, np.array([s, 0.0, 0.0])


def chain_weights(P, S, E, W, names):
    """{bone: w} per point along the chain: the root bone to the elbow, the forearm to the wrist, the hand past it,
    blended over 15% either side of each joint (by the nearest segment's parameter)."""
    out = []
    for p in np.atleast_2d(P):
        best = None
        for i, (a, b) in enumerate(((S, E), (E, W))):
            ab = b - a
            t = float(np.clip((p - a) @ ab / (ab @ ab), 0.0 if i else -1.0, 1.0 if i == 0 else 2.0))
            d = float(np.linalg.norm(p - (a + ab * min(max(t, 0.0), 1.0))))
            if best is None or d < best[0]:
                best = (d, i + t)
        u = best[1]
        w2 = float(_ss(1.85, 2.15, u))
        w1 = float(_ss(0.85, 1.15, u)) - w2
        w0 = 1.0 - w1 - w2
        out.append({n: w for n, w in zip(names, (w0, w1, w2)) if w > 1e-4})
    return out


def _tube(pts, r0, r1, sides):
    import hum_skeleton
    return hum_skeleton.loft(pts, np.linspace(r0, r1, len(pts)), None, sides, cap=0.5)


def demon_parts(B, lod=0):
    """[(V, faces, weights, t)]: spars, membrane and claws of both wings."""
    import hum_helpers
    L = LODS[lod]
    out_parts = []
    for s in (1.0, -1.0):
        names = hum_helpers.WING["l" if s > 0 else "r"]
        hand = names[2]
        S, E, W, Hd, k, out = arm_chain(B, s)
        # finger tips: the leading one up and out, the last down toward the hip
        tips = [W + k * (out * 0.30 + UP * 0.22 + BACK * 0.02), W + k * (out * 0.46 + BACK * 0.05),
                W + k * (out * 0.38 - UP * 0.30 + BACK * 0.08), W + k * (out * 0.18 - UP * 0.56 + BACK * 0.10)]
        T = S + k * (-UP * 0.36 + BACK * 0.03 + out * 0.03)                  # the membrane's foot on the back
        for a, b, r0, r1 in ((S, E, 0.022, 0.016), (E, W, 0.016, 0.012)):
            V, F = _tube([a, (a + b) / 2 + UP * 0.01 * k, b], r0 * k, r1 * k, L["sides"])
            out_parts.append((V, F, chain_weights(V, S, E, W, names), np.full(len(V), 0.5)))
        for tp in tips:
            mid = W + (tp - W) * 0.5 + BACK * 0.012 * k
            V, F = _tube([W, mid, tp], 0.009 * k, 0.003 * k, max(3, L["sides"] - 2))
            out_parts.append((V, F, hand, np.full(len(V), 0.6)))
        if L["thumb"]:
            V, F = _tube([W, W + k * (UP * 0.06 - BACK * 0.03 + out * 0.01)], 0.008 * k, 0.001, 4)
            out_parts.append((V, F, hand, np.full(len(V), 0.3)))
        # the membrane: a fan round the wrist through the finger tips and the scallops between them, then the arm's
        # panel from the wrist down to the back. Scallops pulled 28% toward the wrist; a slight billow backward.
        ring = [tips[0]]
        for a, b in zip(tips[:-1] + [tips[-1]], tips[1:] + [T]):
            m = (a + b) / 2
            ring.append(m + (W - m) * 0.28 + BACK * 0.03 * k)
            ring.append(b)
        Vm = [W] + ring + [E, S]
        n = len(ring)
        Fm = [(0, i + 1, i + 2) for i in range(n - 1)]
        iT, iE, iS = n, n + 1, n + 2                                          # T is ring's last
        Fm += [(0, iT, iE), (iE, iT, iS)]
        tv = np.r_[0.5, np.full(n, 1.0), 0.6, 0.5]
        wm = chain_weights([W], S, E, W, names) + [{hand: 1.0}] * (n - 2)
        wm += [{hand: 0.5, "spine_03": 0.5}, {"spine_03": 1.0}]               # the last scallop, the foot
        wm += chain_weights([E, S], S, E, W, names)
        out_parts.append((np.array(Vm), Fm, wm, tv))
    return out_parts


def _blade(root, d, side, length, width, nw, segs=3):
    """A feather: a flat tapered blade from root along d (curving a little toward -nw at the tip), `side` across;
    its UVs one T_Cloth_Feather each (u across the vane, v root to tip)."""
    V, uv = [], []
    for i in range(segs + 1):
        t = i / segs
        c = root + d * length * t - nw * 0.06 * length * t * t
        w = width * (math.sin(math.pi * min(1.0, 0.15 + t * 0.85)) * 0.8 + 0.2 * (1 - t))
        V += [c - side * w * 0.5, c + side * w * 0.5]
        uv += [(0.0, t), (1.0, t)]
    F = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(segs)]
    return np.array(V), F, np.array(uv)


def feather_texture(size=256, seed=31):
    """T_Cloth_Feather (grey, one feather in 0..1: u across the vane, v root to tip): a light shaft, barbs slanting
    toward the tip with a few splits, darker edges and a soft downy root; the colour comes from the group (Feather)."""
    import os
    import hum_paint
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    X, Y = np.meshgrid(u, u)                          # X = u (across), Y = v (root to tip): image rows go up in v
    d = np.abs(X - 0.5) * 2                           # 0 at the shaft, 1 at the vane's edge
    wob = np.zeros_like(X)
    for _ in range(6):                                # the barbs bend a little, unevenly
        k = rng.integers(1, 5, 2)
        wob += np.cos(2 * np.pi * (k[0] * X + k[1] * Y) + rng.uniform(0, 2 * np.pi)) / k.sum()
    phase = 46 * (Y - 0.32 * d ** 0.8) + 0.25 * wob
    barbs = 0.5 + 0.5 * np.cos(2 * np.pi * phase)
    v = 0.9 - 0.05 * hum_paint.smoothstep(0.4, 1.0, barbs)
    for _ in range(4):                                # splits: a gap between two barbs, open toward the edge
        p0 = rng.uniform(0.2, 0.85)
        side = rng.choice((-1.0, 1.0))
        gap = np.exp(-((Y - 0.32 * d ** 0.8 - p0) * 140) ** 2) * hum_paint.smoothstep(0.25, 0.7, d)
        v -= 0.16 * gap * ((X - 0.5) * side > 0)
    v -= 0.16 * hum_paint.smoothstep(0.72, 1.0, d)                              # the vane's edge
    v -= 0.07 * (1 - hum_paint.smoothstep(0.0, 0.22, Y))                        # the downy root, in the coverts' shade
    sw = 0.045 * (1 - 0.75 * Y)                                                  # the shaft, thinning to the tip
    shaft = 1 - hum_paint.smoothstep(sw * 0.6, sw, d)
    v = v * (1 - shaft) + 0.98 * shaft
    v -= 0.05 * np.exp(-((d - sw * 1.4) / 0.02) ** 2) * (1 - shaft)             # a groove beside the shaft
    M = np.stack([v, v, v * 0.99, np.ones_like(v)], -1)
    return hum_paint.save_image("T_Cloth_Feather", M, os.path.join(hum_paint.TEX_DIR, "T_Cloth_Feather.png"))


def angel_parts(B, lod=0):
    import hum_helpers
    L = LODS[lod]
    parts = []
    for s in (1.0, -1.0):
        names = hum_helpers.WING["l" if s > 0 else "r"]
        S, E, W, Hd, k, out = arm_chain(B, s)
        nw = _unit(np.cross(E - S, W - E)) * s                                # the wing's plane normal, toward the back
        if nw @ BACK < 0:
            nw = -nw
        for a, b, r0, r1 in ((S, E, 0.026, 0.02), (E, W, 0.02, 0.015), (W, Hd, 0.015, 0.008)):
            V, F = _tube([a, (a + b) / 2, b], r0 * k, r1 * k, L["sides"])
            parts.append((V, F, chain_weights(V, S, E, W, names), np.full(len(V), 0.7),
                          np.tile((0.3, 0.12), (len(V), 1))))                 # the bone under the coverts: vane, downy

        def row(a, b, count, dir0, dir1, len0, len1, width, layer, t_lit):
            for i in range(0, count, L["every"]):
                u = i / max(count - 1, 1)
                root = a + (b - a) * u
                d = _unit(dir0 * (1 - u) + dir1 * u)
                side = _unit(np.cross(d, nw))
                V, F, uv = _blade(root + nw * 0.004 * layer * k, d, side, k * (len0 + (len1 - len0) * u), k * width, nw)
                w = chain_weights([root], S, E, W, names)[0]
                bone = max(w, key=w.get)                                      # rigid on its root's bone
                parts.append((V, F, bone, np.full(len(V), t_lit), uv))

        down = -UP * 0.95 + out * 0.2 + BACK * 0.12
        # primaries from the hand: fanning from out-and-up at the tip to down at the wrist (longest at the tip)
        row(W, Hd, 9, down + out * 0.6, out * 0.85 + UP * 0.5, 0.36, 0.5, 0.11, 0, 1.0)      # overlapping (0.07: a comb)
        row(E, W, 10, down + out * 0.05, down + out * 0.45, 0.3, 0.34, 0.1, 0, 1.0)       # secondaries
        row(S, E, 4, down - out * 0.1, down, 0.24, 0.28, 0.1, 0, 0.9)                      # tertials
        if L["coverts"]:
            row(E, Hd, 12, down * 0.6 + out * 0.4, out * 0.7 + UP * 0.2, 0.13, 0.15, 0.08, 1, 1.0)
            row(S, E, 5, down, down + out * 0.2, 0.11, 0.13, 0.08, 1, 0.9)
    return parts


def _build(maker, material):
    def build(scene, B, name, arm, sk, body=None):
        import hum_builds
        import hum_ghoul
        import hum_rig
        hum_rig.rest(arm)
        out = None
        for lod in (0, 1, 2):
            nm = C.cloth_name(name) + ("" if lod == 0 else f"_L{lod}")
            mat = C.garment_material(material) if material != "bone" else None     # bone: hum_skeleton's
            ob = hum_ghoul.make_object(scene, nm, maker(B, lod), arm, sk, lod, material=mat, slot="wings")
            ob.hide_set(True)
            ob.hide_render = True
            if lod == 0:
                out = ob
            else:
                hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
        return out
    return build


FEATHER = ["#f4f1ea", "#ebe7dd", "#f7f5f0", "#e2ddd2", "#d9d6d0", "#eee8d8"]   # colour group "Feather" (sRGB)

WINGS = {
    "DemonWings": dict(slot="wings", layer=0, material="leather", group="Blackened", make=_build(demon_parts, "leather"),
                       builds=("Orc", "Slim", "Imp"), hide=[], cover=[]),
    "AngelWings": dict(slot="wings", layer=0, material="feather", group="Feather", make=_build(angel_parts, "feather"),
                       builds=("Slim", "Strong"), hide=[], cover=[]),
}
