"""More peoples as face presets over a rolled face (2026-10-23, the card game's units; Daniel: "Keep moving on the
creatures / humanoids"), like the orcs (hum_orcs) and the undead (hum_undead): a preset dict in PRESETS, exported in
the config, applied by Unity's HumanFaceGenerator.ApplyPreset; preview in Blender with hum_undead.undead_face(seed, P).

ELF    tall and slender (the Slim build), long pointed ears, tilted almond eyes, high cheekbones, a narrow chin and
       straight nose, fair to dusky skin, long fair or dark hair, no beard.
GIANT  a hill giant: the Orc build (every orc garment fits it), human skin, a heavy brow and jaw, small deep eyes, a
       broad flat nose, shaggy hair and beard; scaled up in Unity (the build is a person's size: a giant is ~3 m, the
       prefab's or the creature's scale).
"""

ELF = dict(
    name="Elf",
    sliders={"EarPointed": (1.0, 0.0), "EarSize": (0.45, 0.15), "EarOut": (0.2, 0.15), "EyeTilt": (0.8, 0.1),
             "Lipless": (0.45, 0.1), "MouthCorners": (0.25, 0.1),     # finer lips (the head's own pout), not sad
             "EyeSize": (0.25, 0.15), "CheekBones": (0.6, 0.15), "CheekFull": (-0.4, 0.15), "FaceFat": (-0.5, 0.15),
             "ChinWidth": (-0.45, 0.15), "ChinForward": (0.1, 0.15), "NoseWidth": (-0.35, 0.15), "NoseHump": (-0.3, 0.2),
             "NoseTipUp": (0.15, 0.15), "LipUpper": (-0.35, 0.1), "LipLower": (-0.3, 0.1), "MouthWidth": (-0.15, 0.1),
             "FaceOval": (0.4, 0.2), "BrowAngle": (0.35, 0.15), "HeadLength": (0.15, 0.15)},
    age=(0.12, 0.3),                                       # ageless adults (rolled ages made some old; under 0.12 childlike)
    build="Slim",
    fem_scale=0.8,
    tones=["#f1dccb", "#ead2bc", "#f4e4d6", "#d9b896", "#b88a66", "#e8d6c8"],
    irises=["#3d7a5a", "#5a8fb0", "#7a9a4a", "#9a7a3a", "#6a7e8e"],
    hair_styles=["Ponytail", "Ponytail", "Swept", "Bun"],   # the ears out (Long covers them)
    hair_colors=["blond", "white", "black", "auburn", "brown"],
    beard="", beard_color="", no_beard=True,
    brows=["Thin", "Straight"],
    height=(0.3, 0.8),
    sex_min=0.0,
    blush=(0.0, 0.15),
    outfit=dict(M=["Shirt:#d8d0b8", "Leggings:#2e3a22", "ElvenTunic:#3c5a2e", "Boots:#3a2a1a", "ElvenCape:#2c4026"],
                F=["Shirt:#d8d0b8", "Leggings:#2e3a22", "ElvenTunic:#4a5e34", "Boots:#3a2a1a", "ElvenCape:#5a4a2e"]),  # preview
                                                           # (hum_elven: the leaf-hemmed tunic and cape, 2026-10-23)
)

GIANT = dict(
    name="Giant",
    sliders={"JawWide": (1.0, 0.0), "BrowHeavy": (0.9, 0.1), "BrowRidge": (0.7, 0.15), "Underbite": (0.35, 0.2),
             "NoseWidth": (0.8, 0.15), "NoseFlare": (0.6, 0.2), "NoseLength": (0.3, 0.2), "EyeSize": (-0.5, 0.15),
             "EyeSunken": (0.35, 0.1), "ChinWidth": (0.6, 0.15), "FaceSquare": (0.6, 0.2), "CheekFull": (0.3, 0.2),
             "EarSize": (0.35, 0.2), "MouthWidth": (0.35, 0.15), "HeadWidth": (0.25, 0.15)},
    build="Orc",                                           # the bulkiest body; every orc garment fits it
    fem_scale=0.75,
    tones=["#c9956e", "#b8845f", "#d4a582", "#a87656", "#c08b68", "#9a6a4c"],   # weathered, ruddy
    irises=["#4a2a14", "#6a4c26", "#6f7d86", "#4e6e3a"],
    hair_styles=["Long", "Curly", "Crop", "", "Mohawk"],
    hair_colors=["dark_brown", "brown", "auburn", "black", "red", "grey"],
    beard="", beard_color="",                              # a man's rolled beard stays
    brows=["Bushy", "Bushy", "Normal"],
    height=(0.7, 1.0),
    sex_min=0.6,
    blush=(0.1, 0.3),
    age=(0.3, 0.7),
    outfit=dict(M=["OrcKilt:#5a4430", "OrcMantle:#6b5a44", "Bracers:#4a3826"],
                F=["RagShirt:#6a5a44", "OrcKilt:#5a4430", "OrcMantle:#6b5a44"]),   # Blender preview only
)

DWARF = dict(
    # 2026-10-24 (Daniel: "no fantasy pack is done if it does not have dwarves"): short and stocky (the Dwarf build, the
    # head a little big), a big broad nose, heavy brow over deep-set eyes, a square face, ruddy weathered skin; the men's
    # long broad Dwarf beard in the hair's colour (my call: the women unbearded, so they read as women from above)
    name="Dwarf",
    sliders={"NoseWidth": (0.7, 0.2), "NoseLength": (0.35, 0.2), "NoseTipWidth": (0.7, 0.2), "NoseFlare": (0.5, 0.2),
             "NoseHump": (0.25, 0.3), "BrowHeavy": (0.8, 0.1), "BrowRidge": (0.6, 0.15), "EyeSunken": (0.3, 0.1),
             "EyeSize": (-0.2, 0.15), "CheekFull": (0.4, 0.2), "FaceSquare": (0.5, 0.2), "JawWide": (0.6, 0.15),
             "ChinWidth": (0.4, 0.15), "HeadWidth": (0.3, 0.1), "EarSize": (0.2, 0.15), "MouthWidth": (0.2, 0.15)},
    build="Dwarf",
    head_scale=(1.06, 1.14),
    fem_scale=0.7,
    tones=["#d9a582", "#c99070", "#e0b08f", "#b8805e", "#c48a68", "#a87656"],   # ruddy, weathered
    irises=["#4a2a14", "#6a4c26", "#6f7d86", "#4e6e8a", "#3e5e3a"],
    hair_styles=["Long", "Long", "Bun", "Crop", "Ponytail", ""],
    hair_colors=["red", "auburn", "brown", "dark_brown", "black", "blond", "grey", "white"],
    beard="Dwarf", beard_color="", beard_masc_only=True, beard_from_hair=True,
    brows=["Bushy"],
    height=(-0.9, -0.5),
    sex_min=0.0,
    blush=(0.25, 0.5),
    age=(0.3, 0.7),
    outfit=dict(M=["Gambeson:#5a4a3a", "Trousers:#5a4632", "Boots:#3a2a1a", "Hauberk:#8a8a8a", "PlatePauldrons:#9a9a9e",
                   "PlateHelm:#9a9a9e"],                  # preview (a Hauberk or a Gambeson takes no Belt or Shirt)
                F=["Gambeson:#6b5a48", "Trousers:#5a4632", "Boots:#3a2a1a", "Bracers:#4a3420"]),
)

EARTH_ELEMENTAL = dict(
    name="EarthElemental",
    sliders={},
    build="Orc",
    fem_scale=1.0,
    tones=[], irises=[], hair_styles=[""], hair_colors=[], beard="", beard_color="", no_beard=True, brows=[""],
    height=(0.6, 1.0),
    sex_min=0.0,                                           # built on both Orc builds (FOrc: a slimmer stack)
    blush=(0.0, 0.0),
    wear=["EarthElemental"],                               # the rocks (hum_elemental): body and head hidden
    glow=["#ff8a2a", "#ffb03a", "#8cff6a", "#6ad8ff"],     # magma, amber, moss green, crystal blue
)

DEMON = dict(
    # a horned brute (the wings come later): the Orc build, red to charcoal skin, burning yellow eyes, horns (a beard
    # style like the tusks: rooted above the temples, rigid on the head), pointed ears, a scowl
    name="Demon",
    sliders={"BrowHeavy": (1.0, 0.0), "BrowAngle": (0.6, 0.15), "BrowHeight": (-0.4, 0.15), "EarPointed": (0.8, 0.1),
             "EarSize": (0.3, 0.15), "CheekBones": (0.7, 0.15), "CheekFull": (-0.4, 0.15), "JawWide": (0.6, 0.15),
             "ChinForward": (0.35, 0.15), "EyeSize": (-0.2, 0.1), "MouthWidth": (0.3, 0.1), "MouthCorners": (-0.5, 0.15),
             "Lipless": (0.4, 0.1), "NoseWidth": (0.3, 0.15)},
    build="Orc",
    fem_scale=0.8,
    tones=["#8a2a20", "#7a2018", "#9a3424", "#6e1e18", "#a03a28", "#3e3434"],   # deep reds, a charcoal one
    lip_from_tone=(0.45, 0.25, 0.25),
    irises=["#ffcc33", "#ffaa22", "#ff7a1a"],
    hair_styles=["", "", "Mohawk", "Long"],
    hair_colors=["black", "black", "dark_brown"],
    beard="Horns", beard_color="#2a2220",                  # dark horn (a woman's too: the horns are its "beard")
    brows=["Bushy", "Straight"],
    height=(0.6, 1.0),
    sex_min=0.0,
    blush=(0.0, 0.0),
    age=(0.3, 0.5),
    wear=["DemonWings"],                                   # bat wings (hum_wings); a game may take them off
    outfit=dict(M=["OrcKilt:#2a1c18", "OrcPauldrons:#2b2c30", "Bracers:#2a1c18"],
                F=["RagShirt:#2a1c18", "OrcKilt:#2a1c18", "OrcPauldrons:#2b2c30"]),   # Blender preview only
)

IMP = dict(
    # a small, wiry demon: its own Imp build (short legs, long arms, pot belly; scaled ~0.55 in Unity) and a big head
    # (head_scale: the head bone's scale in Unity), big pointed ears, a pinched face, red to violet
    name="Imp",
    sliders={"EarPointed": (1.0, 0.0), "EarSize": (0.9, 0.1), "EarOut": (0.6, 0.15), "BrowAngle": (0.7, 0.15),
             "BrowHeavy": (0.5, 0.15), "NoseLength": (0.5, 0.2), "NoseTipUp": (-0.4, 0.2), "ChinForward": (0.6, 0.15),
             "ChinWidth": (-0.6, 0.15), "CheekBones": (0.7, 0.15), "CheekFull": (-0.6, 0.15), "MouthWidth": (0.5, 0.15),
             "MouthCorners": (0.4, 0.15), "Lipless": (0.5, 0.1), "EyeSize": (0.3, 0.15), "HeadLength": (0.3, 0.15)},
    build="Imp",
    head_scale=(1.28, 1.4),
    fem_scale=1.0,
    tones=["#a83a2a", "#8a2a3a", "#6a2a4a", "#b04a2a"],     # reds to violet
    lip_from_tone=(0.45, 0.25, 0.25),
    irises=["#ffcc33", "#ff7a1a", "#c8ff3a"],
    hair_styles=[""], hair_colors=["black"],
    beard="Horns", beard_color="#2a2220",
    brows=[""],
    height=(-0.6, -0.2),
    sex_min=0.0,
    blush=(0.0, 0.0),
    age=(0.2, 0.4),
    wear=["DemonWings"],
    outfit=dict(M=["RagTrousers:#2a1c18"], F=["RagTrousers:#2a1c18"]),     # Blender preview only
)

ANGEL = dict(
    # serene and tall: the Slim build, fair or golden skin, gold or pale hair, gold and pale eyes, no beard; feathered
    # wings (hum_wings); a white robe with gold trim (a game's choice)
    name="Angel",
    sliders={"CheekBones": (0.5, 0.15), "FaceOval": (0.5, 0.15), "ChinWidth": (-0.3, 0.15), "NoseWidth": (-0.3, 0.15),
             "NoseHump": (-0.4, 0.15), "EyeSize": (0.2, 0.1), "MouthCorners": (0.35, 0.1), "Lipless": (0.3, 0.1),
             "BrowHeight": (0.2, 0.1)},
    build="Slim",
    fem_scale=1.0,
    tones=["#f4e4d6", "#f1dccb", "#e8c9a8", "#c99a6e", "#f6ead8"],
    irises=["#d4a83a", "#9ab8d8", "#c8b070", "#e0c060"],
    hair_styles=["Long", "Long", "Curly", "SidePart", "Ponytail"],
    hair_colors=["blond", "white", "blond", "auburn"],
    beard="", beard_color="", no_beard=True,
    brows=["Thin", "Straight"],
    height=(0.4, 0.8),
    sex_min=0.0,
    blush=(0.05, 0.15),
    age=(0.12, 0.3),
    wear=["AngelWings"],
    outfit=dict(M=["Trousers:#e8e2d4", "Robe:#ece6da", "RobeTrim:#c9a03a", "Shoes:#c9b89a"],
                F=["Trousers:#e8e2d4", "Robe:#ece6da", "RobeTrim:#c9a03a", "Shoes:#c9b89a"]),   # Blender preview only
)

PRESETS = [ELF, GIANT, EARTH_ELEMENTAL, DEMON, IMP, ANGEL, DWARF]


def build_horns():
    """Beard_Horns and its LODs (hum_orcs.build_tusks with the Horns style), then every key made a rigid move of each
    horn with the skin at its root: bound by Surface Deform like the tusks, a 13 cm horn levered the skin's local
    stretch out to its tip, and with a demon's face keys the horns stood 3 cm off the skull."""
    import bpy
    import hum_orcs
    made = hum_orcs.build_tusks(style="Horns", colour=(0.16, 0.13, 0.12))
    head = bpy.data.objects["Head"]
    for name, _, _ in made:
        rigid_keys(bpy.data.objects[name], head)
    return made


def rigid_keys(ob, head, reach=0.012):
    """Each key of a rigid head piece (horns) as a translation per side (x > 0, x < 0): the mean move of the head's
    vertices within `reach` of the piece's root (its vertices nearest the skin)."""
    import numpy as np
    from mathutils.kdtree import KDTree
    hk = head.data.shape_keys.key_blocks
    H0 = np.array([d.co[:] for d in hk[0].data])
    kd = KDTree(len(H0))
    for i, p in enumerate(H0):
        kd.insert(p, i)
    kd.balance()
    ok = ob.data.shape_keys.key_blocks
    B0 = np.array([d.co[:] for d in ok[0].data])
    dist = np.array([kd.find(p)[2] for p in B0])
    sides = []
    for s in (1.0, -1.0):
        m = np.sign(B0[:, 0]) == s
        if not m.any():
            continue
        root = B0[m][np.argsort(dist[m])[:6]]                  # the vertices sunk at the skin
        near = sorted({i for p in root for _, i, _ in kd.find_range(p, reach)})
        sides.append((m, near))
    for kb in ok[1:]:
        h = hk.get(kb.name)
        if h is None:
            continue
        D = np.array([d.co[:] for d in h.data]) - H0
        B = B0.copy()
        for m, near in sides:
            if near:
                B[m] += D[near].mean(0)
        kb.data.foreach_set("co", B.astype(np.float32).ravel())
    ob.data.update()
