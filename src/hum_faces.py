"""Face sliders as shape keys on the Head, a random face generator and lineup renders.

Every key = pipeline(state with the slider) - pipeline(neutral), where the pipeline is
MPFB -> stylize -> head + fitted eyes (hum_head.all_coords). Two-sided sliders get two keys,
<Name>_Pos and <Name>_Neg; a runtime slider s in [-1, 1] drives one of them with |s|.
"""
import os
import random
import bpy
import numpy as np

import hum_mpfb, hum_head, hum_scene, hum_material, hum_rig, hum_body

# name, positive target(s), negative target(s). A target starting with "*" is loaded for
# both sides ("l-" and "r-" versions).
SLIDERS = [
    ("EyeSize", "*eye-scale-incr", "*eye-scale-decr"),
    ("EyeSpacing", "*eye-trans-out", "*eye-trans-in"),
    ("EyeHeight", "*eye-trans-up", "*eye-trans-down"),
    ("EyeTilt", "*eye-corner2-up", "*eye-corner2-down"),
    ("EyeOpen", "*eye-height2-incr", "*eye-height2-decr"),
    ("EyeHooded", "*eye-eyefold-down", "*eye-eyefold-up"),
    ("EyeFold", "*eye-epicanthus-in", "*eye-epicanthus-out"),
    ("BrowHeight", "eyebrows-trans-up", "eyebrows-trans-down"),
    ("BrowAngle", "eyebrows-angle-up", "eyebrows-angle-down"),
    ("BrowRidge", "eyebrows-trans-forward", "eyebrows-trans-backward"),
    ("NoseWidth", "nose-scale-horiz-incr", "nose-scale-horiz-decr"),
    ("NoseLength", "nose-scale-vert-incr", "nose-scale-vert-decr"),
    ("NoseDepth", "nose-scale-depth-incr", "nose-scale-depth-decr"),
    ("NoseHump", "nose-hump-incr", "nose-hump-decr"),
    ("NoseTipUp", "nose-point-up", "nose-point-down"),
    ("NoseTipWidth", "nose-point-width-incr", "nose-point-width-decr"),
    ("NoseFlare", "nose-flaring-incr", "nose-flaring-decr"),
    ("NoseCurve", "nose-curve-convex", "nose-curve-concave"),
    ("MouthWidth", "mouth-scale-horiz-incr", "mouth-scale-horiz-decr"),
    ("LipUpper", "mouth-upperlip-volume-incr", "mouth-upperlip-volume-decr"),
    ("LipLower", "mouth-lowerlip-volume-incr", "mouth-lowerlip-volume-decr"),
    ("MouthCorners", "mouth-angles-up", "mouth-angles-down"),
    ("MouthHeight", "mouth-trans-up", "mouth-trans-down"),
    ("ChinWidth", "chin-width-incr", "chin-width-decr"),
    ("ChinHeight", "chin-height-incr", "chin-height-decr"),
    ("ChinForward", "chin-prominent-incr", "chin-prominent-decr"),
    ("ChinCleft", "chin-cleft-incr", None),
    ("CheekBones", "*cheek-bones-incr", "*cheek-bones-decr"),
    ("CheekFull", "*cheek-volume-incr", "*cheek-volume-decr"),
    ("FaceFat", "head-fat-incr", "head-fat-decr"),
    ("FaceSquare", "head-square", None),
    ("FaceRound", "head-round", None),
    ("FaceOval", "head-oval", None),
    ("FaceTriangle", "head-triangular", None),
    ("FaceInvTriangle", "head-invertedtriangular", None),
    ("FaceDiamond", "head-diamond", None),
    ("HeadWidth", "head-scale-horiz-incr", "head-scale-horiz-decr"),
    ("HeadLength", "head-scale-vert-incr", "head-scale-vert-decr"),
    ("ForeheadHeight", "forehead-scale-vert-incr", "forehead-scale-vert-decr"),
    ("ForeheadSlope", "forehead-trans-backward", "forehead-trans-forward"),
    ("EarSize", "*ear-scale-incr", "*ear-scale-decr"),
    ("EarOut", "*ear-flap-incr", "*ear-flap-decr"),
    ("EarLobe", "*ear-lobe-incr", "*ear-lobe-decr"),
    ("EarPointed", "*ear-shape-pointed", None),
    ("NeckWidth", "neck-scale-horiz-incr", "neck-scale-horiz-decr"),
    # body (a list = several targets moved together)
    ("ArmMuscle", ["*upperarm-muscle-incr", "*lowerarm-muscle-incr"], ["*upperarm-muscle-decr", "*lowerarm-muscle-decr"]),
    ("ShoulderMuscle", "*upperarm-shoulder-muscle-incr", "*upperarm-shoulder-muscle-decr"),
    ("LegMuscle", ["*upperleg-muscle-incr", "*lowerleg-muscle-incr"], ["*upperleg-muscle-decr", "*lowerleg-muscle-decr"]),
    ("ChestMuscle", "torso-muscle-pectoral-incr", "torso-muscle-pectoral-decr"),
    ("BackMuscle", "torso-muscle-dorsi-incr", "torso-muscle-dorsi-decr"),
    ("VShape", "torso-vshape-incr", "torso-vshape-decr"),
    ("ShoulderWidth", "measure-shoulder-dist-incr", "measure-shoulder-dist-decr"),
    ("Waist", "measure-waist-circ-incr", "measure-waist-circ-decr"),
    ("Hips", "measure-hips-circ-incr", "measure-hips-circ-decr"),
    ("Bust", "measure-bust-circ-incr", "measure-bust-circ-decr"),
    ("Belly", "stomach-pregnant-incr", None),
]
BODY_SLIDERS = ["ArmMuscle", "ShoulderMuscle", "LegMuscle", "ChestMuscle", "BackMuscle", "VShape",
                "ShoulderWidth", "Waist", "Hips", "Bust", "Belly"]
MUSCLE_SLIDERS = ["ArmMuscle", "ShoulderMuscle", "LegMuscle", "ChestMuscle", "BackMuscle", "VShape"]

# macro keys: name -> (macros, race)
MACROS = {
    "Masculine": (dict(gender=1.0), None),
    "Feminine": (dict(gender=0.0), None),
    "Old": (dict(age=1.0), None),                 # MPFB age 1.0 = 90 years, 0.5 = 25
    "Young": (dict(age=0.375), None),             # ~18 years
    "Heavy": (dict(weight=1.0), None),
    "Thin": (dict(weight=0.0), None),
    "Muscular": (dict(muscle=1.0), None),
    "Slight": (dict(muscle=0.0), None),
    "AncAfrican": (None, dict(african=1.0, asian=0.0, caucasian=0.0)),
    "AncAsian": (None, dict(african=0.0, asian=1.0, caucasian=0.0)),
    "AncEuropean": (None, dict(african=0.0, asian=0.0, caucasian=1.0)),
}
# correctives for macro interactions: key = C(a+b) - C(a) - C(b) + C0, driven by w_a * w_b
CORRECTIVES = {
    "X_Masculine_AncAfrican": ("Masculine", "AncAfrican"),
    "X_Masculine_AncAsian": ("Masculine", "AncAsian"),
    "X_Masculine_AncEuropean": ("Masculine", "AncEuropean"),
    "X_Masculine_Old": ("Masculine", "Old"),
    "X_Feminine_Old": ("Feminine", "Old"),
}


def _targets(spec, w=1.0):
    if spec is None:
        return None
    if isinstance(spec, (list, tuple)):
        out = {}
        for s in spec:
            out.update(_targets(s, w))
        return out
    if spec.startswith("*"):
        return {"l-" + spec[1:]: w, "r-" + spec[1:]: w}
    return {spec: w}


# Height is a uniform scale of the whole character (Humanoid animation keeps the feet on the ground that way);
# the factors come from MPFB's height macro: height 0.75 / 0.25 against the neutral 0.5.
HEIGHT_STATES = {"tall": dict(macros=dict(height=0.75)), "short": dict(macros=dict(height=0.25))}


def height_ratios(src, rig):
    top = lambda **st: float(hum_head.full_coords(src, rig, **st)[:, 2].max())
    h0 = top()
    return {k: top(**st) / h0 for k, st in HEIGHT_STATES.items()}


def height_scale(height, ratios):
    """height in -1..1 -> uniform scale of the character."""
    return 1.0 + (ratios["tall"] - 1.0) * height if height >= 0 else 1.0 + (1.0 - ratios["short"]) * height


def key_states():
    """name -> state kwargs for hum_head.all_coords."""
    out = {}
    for name, pos, neg in SLIDERS:
        out[name + "_Pos"] = dict(targets=_targets(pos))
        if neg:
            out[name + "_Neg"] = dict(targets=_targets(neg))
    for name, (m, r) in MACROS.items():
        out[name] = dict(macros=m, race=r)
    return out


def _merge(a, b):
    m = dict(a.get("macros") or {}, **(b.get("macros") or {}))
    r = b.get("race") or a.get("race")
    return dict(macros=m or None, race=r)


def add_shape_keys(ob, src, rig, sk=None, body=None, bi=None, eps=1e-5):
    """(Re)create every key on the head (and the body). With a skeleton `sk`, keys are residuals
    (shape minus what the bones' movement already skins) and the per-key bone deltas are returned
    as {key: (n_bones x 3) array} for the runtime. Returns (key count, joint deltas)."""
    targets = [o for o in (ob, body) if o is not None]
    for o in targets:
        if o.data.shape_keys:
            o.shape_key_clear()
    nh = len(rig.head_idx)
    ne = ob["n_eye_verts"] * 2
    src_idx = np.concatenate([rig.head_idx, -1 - np.arange(ne)])        # eyes: rigid on the head bone
    W_head = sk.weight_matrix(src_idx) if sk else None
    W_body = sk.weight_matrix(bi.idx) if (sk and body is not None) else None

    def extract(C):
        h = hum_head.all_coords(src, rig, C=C)
        b = C[bi.idx] if body is not None else None
        j = sk.ends(C)[0] if sk else None
        return h, b, j

    C0 = hum_head.full_coords(src, rig)
    h0, b0, j0 = extract(C0)
    hum_head.add_key(ob, "Basis", h0, h0)
    if body is not None:
        hum_body.add_key(body, "Basis", b0)
    states = key_states()
    cache, joints = {}, {}

    def put(name, h, b, j):
        if sk is not None:
            h = hum_rig.residual(h, h0, j, j0, W_head)
            joints[name] = j - j0
        if np.abs(h - h0).max() > eps:                  # body sliders mostly don't touch the head
            hum_head.add_key(ob, name, h, h0)
        if body is not None:
            bb = hum_rig.residual(b, b0, j, j0, W_body) if sk is not None else b
            if np.abs(bb - b0).max() > eps:
                hum_body.add_key(body, name, bb)

    for name, st in states.items():
        h, b, j = extract(hum_head.full_coords(src, rig, **st))
        cache[name] = (h, b, j)
        put(name, h, b, j)
    for name, (a, b_) in CORRECTIVES.items():
        hb, bb, jb = extract(hum_head.full_coords(src, rig, **_merge(states[a], states[b_])))
        ha, ba, ja = cache[a]
        hc, bc, jc = cache[b_]
        # combined state = base + (ab - base) - (a - base) - (b - base)
        put(name, hb - ha - hc + 2 * h0, None if bb is None else bb - ba - bc + 2 * b0,
            None if jb is None else jb - ja - jc + 2 * j0)
    for o in targets:
        o.data.shape_keys.use_relative = True
    return len(ob.data.shape_keys.key_blocks) - 1, joints


# ------------------------------------------------------------------ faces

SKIN_TONES = [   # sRGB, light -> dark
    "#f3d3bf", "#eac0a6", "#e0ac8c", "#cf9670", "#b97d58", "#9c6445", "#7d4c33", "#603826", "#48291c",
]
HAIR = {"black": "#1b1512", "dark_brown": "#3a2518", "brown": "#5c3b22", "auburn": "#7a3a1c",
        "red": "#9a4a22", "blond": "#b08a52", "ash": "#7c6a58", "grey": "#8a8580", "white": "#c9c4be"}
IRIS = {"brown": "#4a2a14", "dark_brown": "#2c1a0e", "hazel": "#6a4c26", "green": "#4e6e3a",
        "blue": "#3d6e9e", "grey": "#6f7d86", "amber": "#9a6a22"}


FEM_BIAS = dict(Hips=0.35, Waist=-0.3, ShoulderWidth=-0.25, Bust=0.2, EyeSize=0.35, BrowRidge=-0.5, NoseWidth=-0.35, NoseLength=-0.2, NoseTipWidth=-0.3,
                ChinWidth=-0.4, FaceFat=-0.1, LipUpper=0.3, LipLower=0.2, CheekBones=0.3, EyeOpen=0.15)
# MPFB's nose/chin targets are strong at 1.0: random faces use less of them (sliders keep +-1)
SPREAD = dict(NoseHump=0.5, NoseCurve=0.5, NoseTipUp=0.6, NoseLength=0.6, NoseDepth=0.6, NoseFlare=0.6,
              ChinForward=0.6, ChinHeight=0.7, HeadLength=0.6, EyeTilt=0.7)
MASC_BIAS = dict(ChestMuscle=0.25, ShoulderWidth=0.3, BrowRidge=0.3, ChinWidth=0.25, NoseWidth=0.1)


# style weights (masculine, feminine); None = no geometry
HAIR_W = {"Buzz": (0.16, 0.03), "Crop": (0.16, 0.05), "Curly": (0.1, 0.1), "Swept": (0.15, 0.05),
          "SidePart": (0.1, 0.1), "Long": (0.07, 0.3), "Ponytail": (0.05, 0.16), "Bun": (0.02, 0.16),
          "Mohawk": (0.04, 0.02), None: (0.1, 0.0)}
BEARD_W = {None: 0.34, "Short": 0.1, "ShortSideburns": 0.1, "Full": 0.14, "Wizard": 0.04, "Goatee": 0.1,
           "ChinStrap": 0.08, "Mustache": 0.12, "Tusks": 0.0}     # Tusks: orcs only, never rolled for a human
BROW_W = {"Normal": (0.45, 0.4), "Bushy": (0.3, 0.0), "Straight": (0.25, 0.1), "Thin": (0.0, 0.5)}
DYES = {"crimson": "#8e1a22", "copper": "#b0532a", "blond": "#c9a064", "platinum": "#d8d2c4",
        "blue": "#2a4a9a", "violet": "#5e2a82", "teal": "#1f6a6a", "green": "#3c6a2a"}


CLOTHS = ["#d9cfb8", "#bfb39a", "#8c7a62", "#6b5a48", "#9aa0a6", "#7d6a55"]   # linen, undyed, brown, grey


# villager clothes: natural linen, undyed wool and cheap plant dyes; leather for shoes and belts
LINEN = ["#e3dcc8", "#d6ccb2", "#c9bda0"]
WOOL = ["#7a6a55", "#5e5344", "#6b4a33", "#4f5a3a", "#3f4d5c", "#7b3b2c", "#8a6a3a", "#5a5a5a"]
LEATHER = ["#3a2415", "#2b1b10", "#4a2e1a", "#22201e", "#553520"]


def random_outfit(rng, masc):
    """Garment -> sRGB colour (linearised on use). Men: shirt + trousers (+ tunic, belt), boots or shoes.
    Women: dress (+ apron, belt) or, sometimes, shirt + trousers."""
    lin = lambda h: srgb(h)
    o = {}
    if masc or rng.random() < 0.15:
        o["Shirt"] = lin(rng.choice(LINEN))
        o["Trousers"] = lin(rng.choice(WOOL))
        if rng.random() < 0.55:
            o["Tunic"] = lin(rng.choice(WOOL))
        if rng.random() < 0.6:
            o["Belt"] = lin(rng.choice(LEATHER))
    else:
        o["Dress"] = lin(rng.choice(WOOL + LINEN[:1]))
        if rng.random() < 0.5:
            o["Apron"] = lin(rng.choice(LINEN))
        if rng.random() < 0.4:
            o["Belt"] = lin(rng.choice(LEATHER))
    o["Boots" if rng.random() < 0.6 else "Shoes"] = lin(rng.choice(LEATHER))
    return o


CLOAKS = ["#4f5a3a", "#3f4d5c", "#5e5344", "#7b3b2c", "#3a3530", "#6b4a33"]


def random_cloak(rng, o, chance=0.2):
    """Now and then a hooded cloak over whatever is worn (clothes or armour)."""
    if rng.random() < chance:
        c = srgb(rng.choice(CLOAKS))
        o["Cloak"] = c
        o["CloakHood"] = c
        for g in ("Cap", "Hood"):
            o.pop(g, None)
    return o


ARMOR_LEATHER = ["#5a3a22", "#4a2e1a", "#3a2415", "#6b4428", "#2e2a26"]
PADDING = ["#d6ccb2", "#c9bda0", "#8c7a62", "#6b5a48", "#7b3b2c", "#3f4d5c"]
STEEL = ["#8d9095", "#74777c", "#9a9186", "#5f6266"]
BLACKENED = ["#2b2c30", "#232427", "#34302c", "#2a2e36"]      # blackened steel
SUIT = ["#1d1d20", "#26211e", "#1c2029", "#2a1c1c"]           # bodysuits and the black knight's skirt
PLATES = ("Jerkin", "Cuirass", "Pauldrons", "Bracers", "Greaves")


def armour_group(piece):
    """Colour group of an armour-set piece: one colour per group."""
    import hum_cloth
    if piece == "Boots":
        return "Boots"
    if hum_cloth.GARMENTS[piece].get("group"):
        return hum_cloth.GARMENTS[piece]["group"]
    if piece in PLATES:
        return "Plates"
    return {"leather": "Leather", "quilt": "Padding", "mail": "Steel", "plate": "Steel"}.get(
        hum_cloth.GARMENTS[piece]["material"], "Cloth")


ARMOUR_PALETTES = {"Leather": ARMOR_LEATHER, "Plates": ARMOR_LEATHER, "Padding": PADDING, "Steel": STEEL,
                   "Blackened": BLACKENED, "Suit": SUIT,
                   "Boots": LEATHER, "Cloth": WOOL}


def random_armor(rng, o, chance=0.25):
    """Now and then a militia look: a complete armour set (hum_armor.ARMOR_SETS)."""
    if rng.random() >= chance:
        return o
    # a complete set replaces the clothes: one leather colour, a second for the plates over it
    import hum_armor
    name = rng.choice(list(hum_armor.ARMOR_SETS))
    colours = {g: srgb(rng.choice(p)) for g, p in ARMOUR_PALETTES.items()}
    o.clear()
    for piece in hum_armor.ARMOR_SETS[name]:
        o[piece] = colours[armour_group(piece)]
    return o


def _pick(rng, table, idx=None):
    items = list(table.items())
    w = [(v[idx] if idx is not None else v) for _, v in items]
    return rng.choices([k for k, _ in items], weights=w)[0]


def _lighten(c, k):
    return tuple(a + (1 - a) * k for a in c)


def srgb(h):
    h = h.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def random_face(seed):
    """A character: a body build (hum_builds) + a free face. Body keys come from the build only."""
    import hum_builds
    f = _random_face(seed)
    rng = random.Random(seed * 7919 + 13)
    names, odds = zip(*hum_builds.BUILD_ODDS.items())
    name = rng.choices(names, weights=odds)[0]
    tag = hum_builds.tag_of(f["masc"], name)
    w = {k: v for k, v in f["keys"].items() if k not in hum_builds.BODY_KEYS}
    w.update(hum_builds.BUILDS[tag]["keys"])
    g = w.get("Masculine", 0.0) - w.get("Feminine", 0.0)
    for k, (a, b) in CORRECTIVES.items():
        w[k] = g * w.get(b, 0.0) if (a == "Masculine" and b.startswith("Anc")) else w.get(a, 0.0) * w.get(b, 0.0)
    f["keys"] = w
    f["build"] = tag
    return f


def _random_face(seed):
    """Shape key weights + skin/eye properties for one character."""
    rng = random.Random(seed)
    w = {}
    masc = rng.random() < 0.5
    sex = rng.uniform(0.55, 0.95)
    w["Masculine" if masc else "Feminine"] = sex
    age = rng.betavariate(1.6, 2.6)                     # 0 = young adult .. 1 = old
    if age < 0.12:
        w["Young"] = (0.12 - age) / 0.12 * 0.8
    else:
        w["Old"] = (age - 0.12) * 0.75
    for pos, neg, s in (("Heavy", "Thin", 0.45), ("Muscular", "Slight", 0.4)):
        v = rng.gauss(0, s)
        w[pos if v > 0 else neg] = min(abs(v), 1.0)
    anc = np.array([rng.gammavariate(0.6, 1) for _ in range(3)])
    anc /= anc.sum()
    for k, a in zip(("AncAfrican", "AncAsian", "AncEuropean"), anc):
        w[k] = float(a)
    # corrective products (feminine counts as negative masculine for the ancestry correctives)
    g = sex if masc else -sex
    for k, (a, b) in CORRECTIVES.items():
        if a == "Masculine" and b.startswith("Anc"):
            w[k] = g * w[b]
        else:
            w[k] = w.get(a, 0.0) * w.get(b, 0.0)
    # sex-linked means (stylised dimorphism on top of MPFB's macro), resting mouth slightly up
    bias = dict(FEM_BIAS if not masc else MASC_BIAS)
    bias["MouthCorners"] = bias.get("MouthCorners", 0.0) + 0.25
    for name, pos, neg in SLIDERS:
        v = rng.gauss(bias.get(name, 0.0) * sex, 0.3) * SPREAD.get(name, 1.0)
        if name.startswith("Face") and not neg:
            v = abs(rng.gauss(0, 0.25)) if rng.random() < 0.35 else 0.0
        if name in ("EarPointed", "ChinCleft", "Belly"):
            v = max(0.0, rng.gauss(-0.2, 0.4))
        v = 0.7 * np.tanh(v / 0.7)          # random faces stay off the extremes (players can go to +-1)
        if v > 0:
            w[name + "_Pos"] = v
        elif v < 0 and neg:
            w[name + "_Neg"] = -v
    # colours: tone leans on ancestry but keeps its own spread
    t = 0.15 * anc[2] + 0.45 * anc[1] + 0.85 * anc[0] + rng.gauss(0, 0.12)
    t = min(max(t, 0.0), 1.0) * (len(SKIN_TONES) - 1)
    i = int(t)
    tone = np.array(srgb(SKIN_TONES[i])) * (1 - (t - i)) + np.array(srgb(SKIN_TONES[min(i + 1, len(SKIN_TONES) - 1)])) * (t - i)
    dark = t / (len(SKIN_TONES) - 1)
    if age > 0.6 and rng.random() < 0.7:
        hair = rng.choice(["grey", "white", "ash"])
    elif dark > 0.45:
        hair = rng.choice(["black", "black", "dark_brown"])
    else:
        hair = rng.choice(["black", "dark_brown", "brown", "brown", "auburn", "red", "blond", "ash"])
    if dark > 0.5:
        iris = rng.choice(["dark_brown", "brown", "brown", "amber"])
    else:
        iris = rng.choice(["brown", "dark_brown", "hazel", "green", "blue", "blue", "grey"])
    props = dict(
        tone=tuple(tone), hair=srgb(HAIR[hair]), iris=srgb(IRIS[iris]),
        blush=rng.uniform(0.35, 0.8) * (1 - 0.5 * dark),
        freckles=(rng.uniform(0.4, 1.0) if (dark < 0.3 and (hair in ("red", "auburn") or rng.random() < 0.2)) else 0.0),
        stubble=(rng.uniform(0.2, 0.55) if masc and rng.random() < 0.6 else 0.0),
        age=max(0.0, (age - 0.4) / 0.6) * 1.1,
        brows=rng.uniform(0.6, 0.95),
    )
    # --- hair, beard and brow geometry + hair colours (multi-colour options)
    si = 0 if masc else 1
    hw = dict(HAIR_W)
    hw["Curly"] = tuple(v * (1 + 3 * anc[0]) for v in hw["Curly"])
    if masc and age > 0.5:
        hw[None] = (0.35, 0.0)
    style = _pick(rng, hw, si)
    beard = _pick(rng, BEARD_W) if masc else None
    if beard and age > 0.5 and rng.random() < 0.4:
        beard = "Full" if age < 0.8 else "Wizard"
    brows = _pick(rng, BROW_W, si)
    root = srgb(HAIR[hair])
    look = rng.choices(["natural", "sunkissed", "ombre", "streaks", "twotone"], weights=[50, 20, 12, 12, 6])[0]
    if hair in ("grey", "white") and look != "natural":
        look = "natural"
    hc = dict(root=root)
    if look == "sunkissed":
        hc.update(tip=_lighten(root, 0.35), ombre=0.8)
    elif look == "ombre":
        hc.update(tip=srgb(DYES[rng.choice(list(DYES))]), ombre=1.0)
    elif look == "streaks":
        hc.update(streak=srgb(DYES[rng.choice(list(DYES))]), streaks=rng.uniform(0.18, 0.35))
    elif look == "twotone":
        hc.update(streak=srgb(DYES[rng.choice(list(DYES))]), streaks=0.5)
    beard_col = dict(root=root if rng.random() < 0.8 else tuple(min(1.0, c * 1.35 + 0.004) for c in root))
    brow_col = dict(root=tuple(c * 0.8 for c in root))
    props["brows"] = 0.25                      # painted brows only as an underlayer now
    props["scalp"] = 0.0 if style in (None, "Mohawk") else 1.0
    props["beard_shadow"] = 0.5 if beard in ("Full", "Wizard", "Short", "ShortSideburns", "ChinStrap") else 0.0
    props["hair"] = root                        # hairline/beard tint on the skin = hair colour
    cloth = srgb(rng.choice(CLOTHS))
    height = max(-1.0, min(1.0, rng.gauss(0.0, 0.35)))
    outfit = random_cloak(rng, random_armor(rng, random_outfit(rng, masc), 0.3 if masc else 0.12))
    # now and then a clearly muscular build (labourers, soldiers): muscle sliders up, less fat
    if rng.random() < 0.15:
        for k in MUSCLE_SLIDERS:
            w.pop(k + "_Neg", None)
            w[k + "_Pos"] = rng.uniform(0.55, 0.95)
        w.pop("Slight", None)
        w["Muscular"] = max(w.get("Muscular", 0.0), rng.uniform(0.5, 1.0))
        w.pop("Heavy", None)
    return dict(seed=seed, keys=w, props=props, hair=hair, iris=iris, masc=masc, age=age, cloth=cloth, height=height,
                outfit=outfit,
                style=style, beard=beard, brow_style=brows, look=look,
                hair_colors=hc, beard_colors=beard_col, brow_colors=brow_col)


def _set_keys(ob, keys):
    if not ob.data.shape_keys:
        return
    for kb in ob.data.shape_keys.key_blocks[1:]:
        kb.value = 0.0
    for k, v in keys.items():
        kb = ob.data.shape_keys.key_blocks.get(k)
        if kb is not None:
            kb.slider_min = min(kb.slider_min, -1.0)
            kb.value = v


def apply_face(ob, face, lod=0):
    """Head keys + skin/eye colours, and (if the face has them) hair/beard/brow pieces + colours.
    lod > 0 drives Head_L<n> and the pieces in HUM_LOD<n> instead (ob is still the full head)."""
    suffix = "" if lod == 0 else f"_L{lod}"
    if lod:
        ob = bpy.data.objects[ob.name + suffix]
    import hum_builds
    bkeys = hum_builds.body_weights(face["keys"])
    _set_keys(ob, face["keys"])
    body = bpy.data.objects.get("Body" + suffix)
    if body is not None:
        _set_keys(body, bkeys)
        p = face["props"]
        import hum_cloth
        hide = 0
        for g in face.get("outfit", {}):
            for r in hum_cloth.GARMENTS[g]["hide"]:
                hide |= 1 << r
        suit = [face["outfit"][g] for g in face.get("outfit", {}) if hum_cloth.GARMENTS[g].get("bodysuit")]
        if suit:                                      # preview: the body in the suit's colour (Unity: Humans/Body)
            hum_material.set_body_props(body, suit[0], 0.0, 0.0, suit[0], 1.0, hide)
        else:
            hum_material.set_body_props(body, p.get("tone", (0.62, 0.40, 0.30)), p.get("blush", 0.5),
                                        p.get("freckles", 0.0), face.get("cloth", (0.55, 0.47, 0.38)),
                                        0.0 if face.get("masc", True) else 1.0, hide)
    arm = bpy.data.objects.get("HumanRig")
    hum_rig.pose_for_keys(arm, bkeys)
    ccol = bpy.data.collections.get("HUM_Cloth" if lod == 0 else f"HUM_LOD{lod}")
    outfit = face.get("outfit", {})
    import hum_cloth
    layer_hide = hum_cloth.outfit_hides(outfit)
    for co in (ccol.objects if ccol else []):
        if co.name.startswith("Cloth_"):
            g, tag, _ = hum_cloth.parse_cloth(co.name)
            on = g in outfit and tag == face.get("build")
            co.hide_set(not on)
            co.hide_render = not on
            if on:
                _set_keys(co, face["keys"])
                co["hum_color"] = tuple(outfit[g])
                co["hum_hide"] = float(layer_hide[g])
    if arm is not None and hum_rig.HEIGHT_RATIOS:
        s = height_scale(face.get("height", 0.0), hum_rig.HEIGHT_RATIOS)
        arm.scale = (s, s, s)      # (hum_rig.hips_lift is for Unity's Humanoid Animator; posed bones need none)
    hum_material.set_props(ob, **face["props"])
    if lod >= 2:
        hum_material.set_props(ob, brows=0.8)          # no brow geometry at the colony camera
    col = bpy.data.collections.get("HUM_Hair" if lod == 0 else f"HUM_LOD{lod}")
    if col is None or "style" not in face:
        return
    want = {}
    if face.get("style"):
        want["Hair_" + face["style"] + suffix] = face["hair_colors"]
    if face.get("beard"):
        want["Beard_" + face["beard"] + suffix] = face["beard_colors"]
    if face.get("brow_style"):
        want["Brows_" + face["brow_style"] + suffix] = face["brow_colors"]
    capcut = max([hum_cloth.GARMENTS[g].get("capcut", 0.0) for g in outfit] + [0.0])
    hides_hair = any(hum_cloth.GARMENTS[g].get("hides_hair") for g in outfit)
    hides_face = any(hum_cloth.GARMENTS[g].get("hides_face_hair") for g in outfit)
    hides_head = any(hum_cloth.GARMENTS[g].get("hides_head") for g in outfit)
    ob.hide_render = hides_head                   # a closed helm: nothing of the head shows
    ob.hide_set(hides_head)
    for hob in col.objects:
        if hob.name.startswith(("Head", "Body", "Cloth_")):
            continue
        hob["hum_capcut"] = float(capcut)
        hob["hum_hoodcut"] = 1.0 if any(hum_cloth.GARMENTS[g].get("hoodcut") for g in outfit) else 0.0
        if (hides_hair and hob.name.startswith("Hair_")) or hides_face:
            hob.hide_set(True)
            hob.hide_render = True
            continue
        on = hob.name in want
        hob.hide_set(not on)
        hob.hide_render = not on
        if on:
            _set_keys(hob, face["keys"])
            hum_material.set_hair_props(hob, **want[hob.name])


def lineup(ob, seeds, views=("Front", "34"), size=420, out="lineup.png"):
    sc = bpy.context.window_manager.windows[0].scene
    paths = []
    for s in seeds:
        apply_face(ob, random_face(s))
        for v in views:
            paths.append(hum_scene.render(sc, bpy.data.objects["Cam_" + v],
                                          os.path.join(hum_scene.RENDERS, "_tmp", f"face{s}_{v}.png"), size))
    return hum_scene.sheet(paths, len(views) * 4 if len(seeds) >= 4 else len(paths),
                           os.path.join(hum_scene.RENDERS, out))


def slider_sheet(ob, names, size=300, out="sliders.png"):
    """Each row: slider at -1, 0, +1 (front view)."""
    sc = bpy.context.window_manager.windows[0].scene
    paths = []
    for n in names:
        for s in (-1, 0, 1):
            apply_face(ob, dict(keys={}, props={}))
            k = f"{n}_Neg" if s < 0 else f"{n}_Pos"
            if s and k in ob.data.shape_keys.key_blocks:
                ob.data.shape_keys.key_blocks[k].value = 1.0
            paths.append(hum_scene.render(sc, bpy.data.objects["Cam_Front"],
                                          os.path.join(hum_scene.RENDERS, "_tmp", f"sl_{n}_{s}.png"), size))
    return hum_scene.sheet(paths, 6, os.path.join(hum_scene.RENDERS, out))
