"""Wings for the humanoids (2026-10-23, the card game's demons, imps and angels; Daniel: "Keep moving on the
creatures / humanoids"). Garments with their own maker (like the Skeleton): rigid on spine_03, held half raised behind
the shoulders - up, out and back, clear of the arms' swing - so they read from above. They don't move yet: flapping
needs wing bones (helper bones off spine_03, driven at runtime like the cape chain); that comes later.

DemonWings  a bat's: an arm (shoulder -> elbow -> wrist, the wrist above the head), four finger spars fanning from
            the wrist, a membrane between them with a scalloped trailing edge, down the back to the waist; a thumb
            claw at the wrist. Material `leather` (Humans/Cloth, double-sided), colour group Blackened.
AngelWings  a bird's: the same arm with a hand, primaries fanning from the hand, secondaries hanging from the
            forearm, tertials from the upper arm, short coverts over their roots - flat tapered blades in layers.
            Material `bone` (pale, the bone pattern), colour group Bone.

Built per build in build space; sized from the build's torso.
"""
import math

import numpy as np

import hum_cloth as C

LODS = {0: dict(sides=6, coverts=True, every=1, thumb=True), 1: dict(sides=4, coverts=False, every=1, thumb=True),
        2: dict(sides=3, coverts=False, every=2, thumb=False)}
UP, BACK = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])     # MPFB: +Y is the back


def _unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-9)


def arm_chain(B, s):
    """(root, elbow, wrist, size k) of the wing on side s (+1 left / -1 right): the root on the upper back over the
    shoulder blade, just under the skin."""
    j = B.j
    s3, nk, pv = j["spine_03"], j["neck_01"], j["pelvis"]
    zr = float(s3[2] + 0.55 * (nk[2] - s3[2]))
    P = B.co_raw[(B.part == "torso") & (np.abs(B.co_raw[:, 0] - s * 0.075) < 0.025) & (np.abs(B.co_raw[:, 2] - zr) < 0.03)]
    yb = float(P[:, 1].max()) if len(P) else float(s3[1]) + 0.1
    k = float(nk[2] - pv[2]) / 0.48
    out = np.array([s, 0.0, 0.0])
    S = np.array([s * 0.075, yb - 0.012, zr])
    E = S + k * (out * 0.22 + BACK * 0.13 + UP * 0.10)
    W = E + k * (out * 0.12 + BACK * 0.07 + UP * 0.28)
    return S, E, W, k, out


def _tube(pts, r0, r1, sides):
    import hum_skeleton
    return hum_skeleton.loft(pts, np.linspace(r0, r1, len(pts)), None, sides, cap=0.5)


def demon_parts(B, lod=0):
    """[(V, faces, bone, t)]: spars, membrane and claws of both wings."""
    L = LODS[lod]
    out_parts = []
    for s in (1.0, -1.0):
        S, E, W, k, out = arm_chain(B, s)
        # finger tips: the leading one up and out, the last down toward the hip
        tips = [W + k * (out * 0.30 + UP * 0.22 + BACK * 0.02), W + k * (out * 0.46 + BACK * 0.05),
                W + k * (out * 0.38 - UP * 0.30 + BACK * 0.08), W + k * (out * 0.18 - UP * 0.56 + BACK * 0.10)]
        T = S + k * (-UP * 0.36 + BACK * 0.03 + out * 0.03)                  # the membrane's foot on the back
        V, F = _tube([S, (S + E) / 2 + UP * 0.01 * k, E], 0.022 * k, 0.016 * k, L["sides"])
        out_parts.append((V, F, "spine_03", np.full(len(V), 0.5)))
        V, F = _tube([E, (E + W) / 2, W], 0.016 * k, 0.012 * k, L["sides"])
        out_parts.append((V, F, "spine_03", np.full(len(V), 0.5)))
        for tp in tips:
            mid = W + (tp - W) * 0.5 + BACK * 0.012 * k
            V, F = _tube([W, mid, tp], 0.009 * k, 0.003 * k, max(3, L["sides"] - 2))
            out_parts.append((V, F, "spine_03", np.full(len(V), 0.6)))
        if L["thumb"]:
            V, F = _tube([W, W + k * (UP * 0.06 - BACK * 0.03 + out * 0.01)], 0.008 * k, 0.001, 4)
            out_parts.append((V, F, "spine_03", np.full(len(V), 0.3)))
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
        out_parts.append((np.array(Vm), Fm, "spine_03", tv))
    return out_parts


def _blade(root, d, side, length, width, nw, segs=3):
    """A feather: a flat tapered blade from root along d (curving a little toward -nw at the tip), `side` across."""
    V = []
    for i in range(segs + 1):
        t = i / segs
        c = root + d * length * t - nw * 0.06 * length * t * t
        w = width * (math.sin(math.pi * min(1.0, 0.15 + t * 0.85)) * 0.8 + 0.2 * (1 - t))
        V += [c - side * w * 0.5, c + side * w * 0.5]
    F = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(segs)]
    return np.array(V), F


def angel_parts(B, lod=0):
    L = LODS[lod]
    parts = []
    for s in (1.0, -1.0):
        S, E, W, k, out = arm_chain(B, s)
        Hd = W + k * (out * 0.16 + UP * 0.12 + BACK * 0.01)                   # the hand
        nw = _unit(np.cross(E - S, W - E)) * s                                # the wing's plane normal, toward the back
        if nw @ BACK < 0:
            nw = -nw
        for a, b, r0, r1 in ((S, E, 0.026, 0.02), (E, W, 0.02, 0.015), (W, Hd, 0.015, 0.008)):
            V, F = _tube([a, (a + b) / 2, b], r0 * k, r1 * k, L["sides"])
            parts.append((V, F, "spine_03", np.full(len(V), 0.7)))

        def row(a, b, count, dir0, dir1, len0, len1, width, layer, t_lit):
            for i in range(0, count, L["every"]):
                u = i / max(count - 1, 1)
                root = a + (b - a) * u
                d = _unit(dir0 * (1 - u) + dir1 * u)
                side = _unit(np.cross(d, nw))
                V, F = _blade(root + nw * 0.004 * layer * k, d, side, k * (len0 + (len1 - len0) * u), k * width, nw)
                parts.append((V, F, "spine_03", np.full(len(V), t_lit)))

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
            mat = C.garment_material(material) if material != "bone" else None
            ob = hum_ghoul.make_object(scene, nm, maker(B, lod), arm, sk, lod, material=mat, slot="wings")
            ob.hide_set(True)
            ob.hide_render = True
            if lod == 0:
                out = ob
            else:
                hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
        return out
    return build


WINGS = {
    "DemonWings": dict(slot="wings", layer=0, material="leather", group="Blackened", make=_build(demon_parts, "leather"),
                       builds=("Orc", "Slim"), hide=[], cover=[]),
    "AngelWings": dict(slot="wings", layer=0, material="bone", group="Bone", make=_build(angel_parts, "bone"),
                       builds=("Slim", "Strong"), hide=[], cover=[]),
}
