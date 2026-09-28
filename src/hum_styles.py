"""Hairstyle, beard and eyebrow recipes -> hum_hair parts -> objects.

Each recipe is a dict; build_* turn it into one mesh object named Hair_<style>, Beard_<style>, Brows_<style>.
Lengths/widths in metres.
"""
import math
import numpy as np

import hum_hair
from hum_hair import grow, cap_part, clumps_part, sample_roots, _unit

HAIR = {
    "Buzz": dict(cap=0.0015),
    "Crop": dict(cap=0.004, spacing=0.017, length=(0.04, 0.06), flow="crown", lift=0.02, stiff=0.7,
                 width=0.02, thick=0.004, gravity=0.05, hug=0.002),
    "Curly": dict(cap=0.004, spacing=0.015, length=(0.030, 0.042), flow="crown", lift=0.45, stiff=0.3,
                  width=0.017, thick=0.007, curl=1.1, gravity=0.0),
    "Swept": dict(cap=0.004, spacing=0.02, length=(0.075, 0.11), flow="back", lift=0.15, stiff=0.55,
                  width=0.034, thick=0.007, gravity=0.35, hug=0.006),
    "SidePart": dict(cap=0.004, spacing=0.02, length=(0.085, 0.12), flow="part", part_x=0.028, lift=0.12,
                     stiff=0.5, width=0.034, thick=0.007, gravity=0.9, hug=0.006, cover_ears=True),
    "Long": dict(cap=0.004, spacing=0.019, length=(0.20, 0.26), flow="part", part_x=0.0, lift=0.06,
                 stiff=0.45, width=0.034, thick=0.007, gravity=2.2, steps=16, hug=0.006, cover_ears=True),
    "Ponytail": dict(cap=0.003, spacing=0.018, flow="tie", tie=(0.0, 0.075, 0.03), lift=0.05, stiff=0.35,
                     width=0.03, thick=0.006, hug=0.003, tail=dict(n=14, length=(0.16, 0.22), width=0.022)),
    "Bun": dict(cap=0.003, spacing=0.018, flow="tie", tie=(0.0, 0.055, 0.075), lift=0.05, stiff=0.35,
                width=0.03, thick=0.006, hug=0.003, bun=dict(radius=0.034)),
    "Mohawk": dict(cap=0.0012, spacing=0.012, length=(0.06, 0.09), flow="up", lift=0.9, stiff=0.85,
                   width=0.022, thick=0.006, gravity=0.0, band=0.022),
}

BEARD = {
    "Short": dict(cap=0.0035, cheeks=0.5),
    "ShortSideburns": dict(cap=0.0035, cheeks=0.5, sideburns=True),
    "Full": dict(cap=0.005, spacing=0.0095, length=(0.02, 0.03), chin_extra=0.07, chin_r=0.035,
                 converge=1.4, lift=0.02, width=0.019, thick=0.006, gravity=0.7, cheeks=0.7, hug=0.003,
                 sideburns=True),
    "Wizard": dict(cap=0.005, spacing=0.011, length=(0.02, 0.03), chin_extra=0.15, chin_r=0.04,
                   converge=1.8, lift=0.02, width=0.024, thick=0.007, gravity=1.0, cheeks=0.8, hug=0.003,
                   steps=12, sideburns=True),
    "Goatee": dict(cap=0.003, spacing=0.010, length=(0.014, 0.02), chin_extra=0.035, chin_r=0.022,
                   converge=2.0, lift=0.0, width=0.018, thick=0.005, gravity=0.8, chin_only=True, hug=0.003),
    "ChinStrap": dict(cap=0.0035, cheeks=0.3, no_mustache=True, sideburns=True, jaw_band=0.02),
    "Mustache": dict(cap=0.0025, spacing=0.007, length=(0.026, 0.036), lift=0.0, width=0.011, thick=0.004,
                     gravity=0.15, mustache_only=True, hug=0.003),
}

BROWS = {
    "Normal": dict(n=9, length=(0.013, 0.017), width=0.0065, thick=0.0012, height=1.12, arch=0.22, spread=0.14),
    "Thin": dict(n=8, length=(0.012, 0.016), width=0.0042, thick=0.0010, height=1.14, arch=0.30, spread=0.06),
    "Bushy": dict(n=12, length=(0.015, 0.02), width=0.0085, thick=0.0020, height=1.10, arch=0.16, spread=0.24),
    "Straight": dict(n=9, length=(0.013, 0.017), width=0.0068, thick=0.0013, height=1.10, arch=0.05, spread=0.14),
}


# ------------------------------------------------------------------ flows

def flow_fn(H, st):
    kind = st["flow"]
    if kind == "crown":
        c = H.crown
        return lambda p, n: (p - c) + np.array([0, -0.02, -0.03])
    if kind == "back":
        return lambda p, n: np.array([0.35 * p[0] / 0.08, 1.0, -0.25])
    if kind == "part":
        # combed sideways off the part near the top of the head, then falling
        x0 = st.get("part_x", 0.0)
        z0, z1 = H.eye_z + 0.03, H.eye_z + 0.08
        face_x = abs(H.F.eye['l'][0][0]) + H.F.eye['l'][1] * 1.8          # just past the outer eye corner

        def f(p, n):
            side = hum_hair.ss(z0, z1, p[2])
            # in front of the face: keep combing sideways until clear of the eyes, so hair frames the face
            front = hum_hair.ss(55.0, 25.0, float(H.theta(p))) * hum_hair.ss(face_x, face_x - 0.02, abs(p[0]))
            side = max(side, 1.6 * front)
            return np.array([np.sign(p[0] - x0 + 1e-6) * side, 0.3 + 0.3 * front, -0.7 * (1 - 0.6 * front)])
        return f
    if kind == "tie":
        t = np.array(st["tie"]) + np.array([0, H.cy, H.eye_z])
        return lambda p, n: t - p
    if kind == "up":
        return lambda p, n: np.array([0, 0.25, 1.0])
    raise KeyError(kind)


# ------------------------------------------------------------------ builders

def hair_parts(H, st, seed=0):
    rng = np.random.default_rng(seed)
    mask = lambda P: H.hair_mask(P, st.get("recede", 0.0))
    if st.get("band"):
        band = st["band"]
        mask = lambda P, m0=mask: m0(P) * hum_hair.ss(band, band * 0.6, np.abs(P[..., 0]))
    parts = [cap_part(H, mask, st["cap"], subdiv=st.get("cap_subdiv", 1), ratio=st.get("cap_ratio", 1.0))]
    if "flow" not in st:
        return parts
    fl = flow_fn(H, st)
    floor = st["cap"] + 0.0015
    H.domes = bool(st.get("cover_ears"))
    ear_top = float(H.ear_co[:, 2].max())
    stop = None if H.domes else (lambda p: float(H.ear_dist(p)) < 0.012 and p[2] < ear_top + 0.004)
    spines, W, T, R = [], [], [], []
    roots = sample_roots(H, mask, st["spacing"], seed)
    # no clumps right beside the ears (they bend over the ear and stick out); the cap covers there
    roots = np.array([r for r in roots if float(H.ear_dist(r)) > 0.016])
    for i, r in enumerate(roots):
        if st["flow"] == "tie":
            t = np.array(st["tie"]) + np.array([0, H.cy, H.eye_z])
            length = np.linalg.norm(t - r) * 1.05
        else:
            lo, hi = st["length"]
            length = rng.uniform(lo, hi)
            # roots beside the ears stay short (long ones bend over the ear and stick out)
            length *= 0.3 + 0.7 * hum_hair.ss(0.012, 0.035, float(H.ear_dist(r)))
        spines.append(grow(H, r, fl, length, lift=st.get("lift", 0.0), gravity=st.get("gravity", 0.0),
                           stiff=st.get("stiff", 0.5), floor=floor + rng.uniform(0, 0.003),
                           steps=st.get("steps", 10), curl=st.get("curl", 0.0), seed=seed * 1000 + i,
                           hug=st.get("hug"), stop=stop, guard=H.face_guard(),
                           release=lambda p: (p[2] < H.hairline_z(p) - 0.005 and H.theta(p) > 112)
                           or p[2] < float(H.F.chin[2])))
        W.append(st["width"] * rng.uniform(0.8, 1.2))
        T.append(st["thick"] * rng.uniform(0.8, 1.2))
        R.append(r)
    if "tail" in st:
        tl = st["tail"]
        tail_guard = H.face_guard(radial=False, front=False)
        t = np.array(st["tie"]) + np.array([0, H.cy, H.eye_z])
        for k in range(tl["n"]):
            a = 2 * math.pi * k / tl["n"] + 0.3
            r0 = t + np.array([math.cos(a) * 0.008, 0.004, math.sin(a) * 0.008])
            sp = [r0]
            d = _unit(np.array([math.cos(a) * 0.25, 0.6, -0.4]))
            L = rng.uniform(*tl["length"])
            for s in range(1, 13):
                d = _unit(d + np.array([0, 0.02, -0.35]) * (s / 12))
                p = sp[-1] + d * L / 12
                # keep clear of the back of the head/neck by pushing straight back (smooth, no kinks)
                loc, n, _ = H.nearest(p)
                h = float(np.dot(p - loc, n))
                if h < 0.012 and n[1] > 0.2:
                    p = p + np.array([0.0, (0.012 - h) / n[1], 0.0])
                p = tail_guard(sp[-1], p)                  # and off the back and shoulders
                sp.append(p)
            spines.append(np.array(sp))
            W.append(tl["width"] * rng.uniform(0.8, 1.2))
            T.append(st["thick"] * 1.3)
            R.append(sp[0])                       # position; turned into a coherent id below
    if "bun" in st:
        rad = st["bun"]["radius"]
        c = np.array(st["tie"]) + np.array([0, H.cy, H.eye_z])
        loc, n, _ = H.nearest(c)
        c = loc + n * rad * 0.85
        for k in range(st["bun"].get("n", 10)):
            ax = _unit(rng.normal(size=3))
            b1 = _unit(np.cross(ax, [0.3, 0.2, 1.0]))
            b2 = np.cross(ax, b1)
            sp = [c + rad * (math.cos(u) * b1 + math.sin(u) * b2) for u in np.linspace(0, 1.6 * math.pi, 12)]
            spines.append(np.array(sp))
            W.append(st["bun"].get("width", 0.03) * rng.uniform(0.8, 1.1))
            T.append(0.012)
            R.append(sp[0])
    parts.append(clumps_part(H, spines, W, T, coherent_ids(np.array(R), seed), sides=st.get("sides", 6)))
    return parts


def coherent_ids(P, seed=0, scale=22.0):
    """Per-clump ids in 0..1 (uniformly distributed) that vary smoothly with position, so
    'id < streaks' picks whole neighbouring sections (dyed streaks/panels), not confetti."""
    from mathutils import noise, Vector
    off = Vector((seed * 3.1, seed * 1.7, 0.5))
    v = np.array([noise.noise(Vector(p) * scale + off) for p in P])
    return (np.argsort(np.argsort(v)) + 0.5) / len(v)


def beard_parts(H, st, seed=0):
    rng = np.random.default_rng(seed + 77)
    H.domes = False
    mask = lambda P: H.beard_mask(P, **st)
    parts = [cap_part(H, mask, st["cap"], subdiv=st.get("cap_subdiv", 2), uv_scale=60.0,
                      ratio=st.get("cap_ratio", 1.0))]
    if "length" not in st:                       # shell-only styles
        return parts
    F = H.F
    chin = F.chin

    conv = st.get("converge", 0.0)

    def flow(p, n):
        # above the mouth: sweep outward and droop like a mustache (nothing hangs over the lips)
        above = hum_hair.ss(F.mouth[2] - 0.004, F.mouth[2] + 0.006, p[2]) * hum_hair.ss(F.mouth_w * 1.4, F.mouth_w * 0.9, abs(p[0]))
        if st.get("mustache_only"):
            above = 1.0
        # below the jaw: draw toward the beard's point
        below = hum_hair.ss(chin[2], chin[2] - 0.03, p[2])
        down = np.array([-p[0] * conv * 12.0 * below, -0.15 - 0.6 * below, -1.0])
        side = np.array([np.sign(p[0] + 1e-6) * 1.0, -0.3, -0.45])
        return down * (1 - above) + side * above
    chin_pt = np.array([0.0, chin[1], chin[2] - 0.01])
    floor = st["cap"] + 0.001
    spines, W, T, R = [], [], [], []
    roots = sample_roots(H, mask, st["spacing"], seed + 5, thresh=0.5)
    if st.get("sideburns"):                          # the sideburn strip is shell only (clumps there are blobs)
        base = lambda P: H.beard_mask(P, **dict(st, sideburns=False))
        roots = np.array([r for r in roots if float(base(r)) > 0.5])
    for i, r in enumerate(roots):
        lo, hi = st["length"]
        L = rng.uniform(lo, hi)
        # the beard's length lives around the chin; cheeks and jaw stay short and hug the face
        chin_w = 0.0
        if st.get("chin_extra"):
            d = np.linalg.norm((r - chin_pt) * [1.0, 0.6, 1.3])
            chin_w = float(np.exp(-0.5 * (d / st["chin_r"]) ** 2))
            L += st["chin_extra"] * chin_w * rng.uniform(0.85, 1.1)
        if r[2] < chin[2] - 0.008:                   # under the jaw: short unless it is the chin itself
            L *= 0.35 + 0.65 * chin_w
        # the profile runs from in front of the ear down to the chin: shorter toward the ear
        front = hum_hair.ss(H.ear_y_front - 0.005, chin[1] + 0.03, r[1])
        L *= 0.35 + 0.65 * front
        above_mouth = r[2] > F.mouth[2] + 0.004
        if float(H.lip_dist(r)) < (0.006 if above_mouth else 0.005):
            continue                                 # nothing rooted right at the lips (it would droop over them)
        if above_mouth:
            L = min(L, 0.03)                         # mustache part stays short: it must not curtain the mouth
        spines.append(grow(H, r, flow, L, lift=st.get("lift", 0.0),
                           gravity=0.15 if above_mouth else st.get("gravity", 0.0),
                           stiff=0.55, floor=floor + rng.uniform(0, 0.002), steps=st.get("steps", 8),
                           seed=seed * 1000 + i, hug=st.get("hug"), release=lambda p: p[2] < chin[2] - 0.006))
        W.append(st["width"] * rng.uniform(0.8, 1.2))
        T.append(st["thick"] * rng.uniform(0.8, 1.2))
        R.append(rng.random())
    parts.append(clumps_part(H, spines, W, T, R, sides=st.get("sides", 5), tex_len=0.03))
    return parts


def brow_parts(H, st, seed=0):
    """Short flat clumps along the painted brow arc (same curve as hum_paint's brows)."""
    rng = np.random.default_rng(seed + 31)
    H.domes = False
    spines, W, T, R = [], [], [], []
    for side in "lr":
        c, r, _ = H.F.eye[side]
        sx = 1.0 if side == 'l' else -1.0
        cx = abs(c[0])
        inner, outer = cx - 0.85 * r, cx + 1.45 * r
        n = st["n"]
        for k in range(n):
            for row in (-1, 1):
                t = (k + rng.uniform(0.0, 0.8)) / n
                arch = math.sin(t ** 0.8 * math.pi)
                x = inner + (outer - inner) * t
                z = c[2] + r * (st["height"] + st["arch"] * arch - 0.10 * t) + row * r * st["spread"] * 0.5 * (1 - t)
                p0 = np.array([sx * x, c[1] - 0.03, z])
                loc, nrm, _ = H.nearest(p0)
                # comb: inner hairs point up-and-out, the rest along the brow toward the temple
                t2 = min(t + 0.08, 1.0)
                x2 = inner + (outer - inner) * t2
                z2 = c[2] + r * (st["height"] + st["arch"] * math.sin(t2 ** 0.8 * math.pi) - 0.10 * t2)
                along = np.array([sx * (x2 - x), 0, z2 - z])
                up = np.array([sx * 0.3, 0, 1.0])
                w_up = 0.5 * max(0.0, 0.25 - t) / 0.25
                d = _unit(_unit(along) * (1 - w_up) + up * w_up)
                L = rng.uniform(*st["length"]) * (1 - 0.35 * t)
                spines.append(grow(H, loc, lambda p, nn, d=d: d, L, floor=0.0007, steps=5, stiff=0.8,
                                   seed=seed * 100 + k))
                W.append(st["width"] * rng.uniform(0.8, 1.2) * (1 - 0.4 * t))
                T.append(st["thick"])
                R.append(1.0)
    return [clumps_part(H, spines, W, T, R, sides=st.get("sides", 4), tex_len=0.015)]


def lod_recipe(kind, st, lod=1):
    """LOD1 (mid distance): fewer, wider clumps, 4 sides, fewer steps, unsubdivided caps.
    LOD2 (colony camera, ~40 m): even fewer/wider 3-sided clumps; beards are caps only."""
    st = dict(st)
    k = 1.9 if lod == 1 else 3.0
    if kind == "brows":
        st.update(n=max(4, st["n"] // (2 if lod == 1 else 3)), width=st["width"] * (1.8 if lod == 1 else 2.6), sides=3)
        return st
    st["cap_subdiv"] = 0
    st["cap_ratio"] = 0.5 if lod == 1 else 0.25
    if kind == "beard" and lod >= 2:
        st.pop("length", None)                    # shell only
        return st
    if "spacing" in st:
        kb = k * (1.25 if kind == "beard" else 1.0)
        st.update(spacing=st["spacing"] * kb, width=st["width"] * kb * 0.9, thick=st["thick"] * 1.3,
                  steps=max(4, int(st.get("steps", 10 if kind == "hair" else 8) * (0.6 if lod == 1 else 0.45))),
                  sides=4 if lod == 1 else 3)
    if "tail" in st:
        st["tail"] = dict(st["tail"], n=max(4, st["tail"]["n"] // (2 if lod == 1 else 3)),
                          width=st["tail"]["width"] * (1.7 if lod == 1 else 2.4))
    if "bun" in st:
        st["bun"] = dict(st["bun"], n=5 if lod == 1 else 3, width=0.045 if lod == 1 else 0.06)
    return st


def build(scene, H, kind, name, seed=0, lod=0):
    table, fn, prefix = {"hair": (HAIR, hair_parts, "Hair_"), "beard": (BEARD, beard_parts, "Beard_"),
                         "brows": (BROWS, brow_parts, "Brows_")}[kind]
    st = table[name] if lod == 0 else lod_recipe(kind, table[name], lod)
    obname = prefix + name + ("" if lod == 0 else f"_L{lod}")   # not "_LOD": Unity auto-detects that
    parts = fn(H, st, seed)
    me = hum_hair.mesh_from_parts(obname, parts)
    ob = hum_hair.replace_object(scene, obname, me)
    ob["hum_kind"] = kind
    ob["hum_lod"] = lod
    return ob
