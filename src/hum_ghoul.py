"""The ghoul's claws (2026-10-23, Daniel: an undead "with big claws and an arched posture", "a type of zombie").

The ghoul is the Undead build pushed further (hum_builds `MGhoul` / `FGhoul`: long thin fingers, long arms, the
shoulders hunched up and a hump; hum_undead `_deform_claws`, `_deform_long_arms`, `_deform_arch`) wearing the
zombies' rot (hum_undead GHOUL preset). Its back is arched at runtime (Unity HumanPosture: the spine turned forward
after the Animator, so every Humanoid clip plays bent over).

GhoulClaws is a garment like the Skeleton (its own maker, the Ghoul builds only, slot `claws`, material `bone`): a
hooked talon out of every finger's nail, rigid on the last finger bone, and a small one on each toe, rigid on the
ball bone. Built per build in build space, so the talons sit on that build's stretched fingers.

    with hum_builds.BuildSpace("MGhoul", sk): ...   (or via hum_builds.build_wardrobe(tags=["MGhoul", "FGhoul"]))
"""
import numpy as np

import hum_cloth as C

# talon length / root radius (metres) per finger; toes: big toe first. Daniel (2026-10-23): "claws can be even larger,
# it is hard to see them from a distance" - first cut 3.4-5 cm, then 5.5-8 (still ~5 px at the game camera's 22 m),
# now 8-12 and thicker.
TALON = {"thumb": (0.08, 0.0075), "index": (0.11, 0.008), "middle": (0.12, 0.0085), "ring": (0.105, 0.008),
         "pinky": (0.09, 0.007)}
TOE = [(0.034, 0.0068), (0.027, 0.0052), (0.025, 0.005), (0.023, 0.0046), (0.02, 0.0043)]
CURL = 0.45                                              # how far a talon hooks toward the palm (x its length)
LODS = {0: dict(sides=5, rings=6, toes=True), 1: dict(sides=4, rings=4, toes=True),
        2: dict(sides=3, rings=3, toes=False)}


def talon(root, d, up, length, r, sides, rings, curl=CURL):
    """A hooked talon from `root` (inside the finger) along d, curling away from `up` (the nail side): taller than
    wide, tapering to a point. Returns (V, faces, t per vertex: 0 at the root .. 1 at the tip)."""
    import hum_skeleton
    t = np.linspace(0.0, 1.0, rings)
    pts = [root + d * length * s - up * length * curl * s * s for s in t]
    taper = (1.0 - t) ** 0.7 + 0.04                       # full-bodied to past the middle: reads at a distance
    V, F = hum_skeleton.loft(pts, r * taper, r * 0.72 * taper, sides, ups=up, cap=0.6)
    tv = np.clip(((V - root) @ d) / length, 0.0, 1.0)
    return V, F, tv


def _hand_frame(j, side):
    h0 = j["hand_" + side]
    knuck = {f: j[f"{f}_01_{side}"] for f in ("index", "middle", "ring", "pinky")}
    mid = np.mean(list(knuck.values()), 0)
    uh = (mid - h0) / np.linalg.norm(mid - h0)
    pk = knuck["pinky"] - knuck["index"]
    pk -= uh * (pk @ uh)
    pk /= np.linalg.norm(pk)
    back = np.cross(uh, pk) * (1.0 if side == "l" else -1.0)   # the back of the hand (left: uh x pinky-ward)
    return uh, pk, back


def _perp(v, d):
    v = v - d * (v @ d)
    return v / np.linalg.norm(v)


def pieces(B, lod=0):
    """(V, faces, bone, t) per talon for the current build space (B: hum_cloth.BodyFrame)."""
    L = LODS[lod]
    j = B.j
    out = []

    def tip(bone, along):
        i = B.sk.index[bone]
        m = B.W[:, i] > 0.4
        P = B.co_raw[m]
        return P[np.argmax((P - j[bone]) @ along)]

    for side in ("l", "r"):
        uh, pk, back = _hand_frame(j, side)
        for f, (length, r) in TALON.items():
            b2, b3 = f"{f}_02_{side}", f"{f}_03_{side}"
            d = j[b3] - j[b2]
            d /= np.linalg.norm(d)
            up = _perp(back if f != "thumb" else (0.6 * back - 0.8 * pk), d)
            t0 = tip(b3, d)
            root = t0 - d * 0.013 + up * 0.0015
            V, F, tv = talon(root, d, up, length + 0.013, r, L["sides"], L["rings"])
            out.append((V, F, b3, tv))
        if not L["toes"]:
            continue
        s = 1.0 if side == "l" else -1.0
        nails = [n for n in toenails(B) if np.sign(n[0][0]) == s]
        nails.sort(key=lambda n: abs(n[0][0]))                 # big toe (nearest the middle) first
        for k, (c, up, front) in enumerate(nails[:5]):
            length, r = TOE[k]
            d = _perp(np.array([0.0, -1.0, 0.0]), up)          # along the toe (MPFB: -Y is the front) ...
            d = d * 0.95 + np.array([0.0, 0.0, -0.3])          # ... dipping a little
            d /= np.linalg.norm(d)
            root = front - d * 0.007 - up * 0.0015
            # the talon stays above the sole (z 0, 3 mm clear): turned up about the toe's side axis until it does
            side_ax = np.cross(d, up)
            side_ax /= np.linalg.norm(side_ax)
            curl = 0.3
            for _ in range(12):
                V, F, tv = talon(root, d, up, length + 0.007, r, L["sides"], L["rings"], curl=curl)
                if V[:, 2].min() >= 0.003:
                    break
                a = np.radians(5.0)                            # Rodrigues about side_ax: tip up
                rot = lambda v: v * np.cos(a) + np.cross(side_ax, v) * np.sin(a) + side_ax * (side_ax @ v) * (1 - np.cos(a))
                d, up = rot(d), rot(up)
                if d[2] > 0.15:
                    curl = max(0.0, curl - 0.1)
            out.append((V, F, "ball_" + side, tv))
    return out


_NAILS = {}


def toenails(B):
    """[(centre, up, front point)] per toenail of the current build's body: MPFB's "toenails" group on the source,
    mapped to the body's vertices and split into connected nails; `up` is the nail's mean normal, `front` its
    front-most point."""
    import bpy
    key = len(B.co_raw)
    if key not in _NAILS:
        import hum_body
        import hum_head
        import hum_mpfb
        src = bpy.data.objects["MPFB_Source"]
        bi = hum_body.BodyIndex(src, hum_head.Rig(src))
        on = np.isin(np.asarray(bi.idx), hum_mpfb.group_members(src, "toenails"))
        adj = {}
        for f in B.faces:
            m = [i for i in f if on[i]]
            for a in m:
                adj.setdefault(a, set()).update(m)
        seen, comps = set(), []
        for v in np.where(on)[0]:
            if v in seen:
                continue
            stack, comp = [int(v)], []
            seen.add(int(v))
            while stack:
                a = stack.pop()
                comp.append(a)
                for b in adj.get(a, ()):
                    if b not in seen:
                        seen.add(b)
                        stack.append(b)
            comps.append(np.array(comp))
        _NAILS[key] = [c for c in comps if len(c) >= 3]
    out = []
    for comp in _NAILS[key]:
        P = B.co_raw[comp]
        up = B.no[comp].mean(0)
        up /= np.linalg.norm(up)
        out.append((P.mean(0), up, P[np.argmin(P[:, 1])]))
    return out


def make_object(scene, name, parts, arm, sk, lod=0, material=None, slot="claws"):
    """One mesh from the talons: rigid weights, ClothData (darker at the root, where the talon leaves the skin),
    rest UVs, Region 0 (never covered), material M_HumanBone (or `material`); replaces an object of that name.
    parts: (V, faces, bone, t per vertex: 0 dark .. 1 lit). The lich's crown (hum_lich) is made the same way."""
    import bpy
    import hum_hair
    import hum_lod
    import hum_rig
    import hum_skeleton
    verts, faces, bones, ts, uvs = [], [], [], [], []
    off = 0
    for part in parts:                               # (V, F, bone, t[, uv per vertex]: hum_wings' feathers)
        V, F, bone, tv = part[:4]
        uvs.append(part[4] if len(part) > 4 else np.full((len(V), 2), 0.5))
        if hum_skeleton._signed_volume(V, F) < 0:
            F = [tuple(reversed(f)) for f in F]
        verts.append(V)
        faces.extend(tuple(i + off for i in f) for f in F)
        bones.extend([bone] * len(V) if isinstance(bone, str) else list(bone))
        ts.append(tv)
        off += len(V)
    V = np.vstack(verts)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    uv = me.uv_layers.new(name="UVMap")
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv.data.foreach_set("uv", np.vstack(uvs)[lv].astype(np.float32).ravel())
    reg = me.uv_layers.new(name="Region")
    reg.data.foreach_set("uv", np.zeros(len(me.loops) * 2, np.float32))
    C.write_rest_uv(me, V)
    ao = 0.55 + 0.45 * np.clip(np.concatenate(ts) * 2.5, 0, 1)
    att = me.color_attributes.new("ClothData", 'FLOAT_COLOR', 'POINT')
    data = np.stack([ao, np.zeros(len(V)), np.zeros(len(V)), np.ones(len(V))], 1)
    att.data.foreach_set("color", data.astype(np.float32).ravel())
    ob = hum_hair.replace_object(scene, name, me)
    if lod == 0:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        bpy.data.collections.get(C.CLOTH_COL).objects.link(ob)
    else:
        hum_lod._place(scene, ob, lod)
    ob.data.materials.append(material or hum_skeleton.bone_material())
    ob["hum_slot"] = slot
    W = np.zeros((len(V), len(sk.bones)))
    for i, b in enumerate(bones):                    # a bone name (rigid) or {bone: weight} (hum_wings' chains)
        if isinstance(b, str):
            W[i, sk.index[b]] = 1.0
        else:
            for name, w in b.items():
                W[i, sk.index[name]] += w
    hum_rig.skin(ob, arm, sk, W)
    return ob


def build(scene, B, name, arm, sk, body=None):
    """Cloth_GhoulClaws_<tag> and its LODs in the current build space (hum_cloth.BUILD); returns the LOD0 object
    (hum_builds.build_wardrobe stores it at rest with the others)."""
    import hum_builds
    import hum_rig
    hum_rig.rest(arm)
    out = None
    for lod in (0, 1, 2):
        nm = C.cloth_name(name) + ("" if lod == 0 else f"_L{lod}")
        ob = make_object(scene, nm, pieces(B, lod), arm, sk, lod)
        ob.hide_set(True)
        ob.hide_render = True
        if lod == 0:
            out = ob
        else:
            hum_builds.to_rest(ob, C.BUILD["dJ"], sk)
    return out


def export():
    """What the ghoul changed, without re-exporting every cloth family (Unity reimports what changes; all of it once
    ran the editor out of memory): Human_Body.fbx (the new keys), Human_Hair.fbx (the keys passed on), the Rags and
    Undead families (the Ghoul builds' rags, the claws), the config and the rig."""
    import os
    import bpy
    import hum_export as E
    head = bpy.data.objects["Head"]
    keys = head.data.shape_keys.key_blocks
    saved = {k.name: k.value for k in keys}
    arm = bpy.data.objects["HumanRig"]
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
    saved_scale = tuple(arm.scale)
    arm.scale = (1, 1, 1)
    body_parts = [o for o in (bpy.data.objects.get(n) for n in ("Body", "Body_L1", "Body_L2", "Head_L1", "Head_L2"))
                  if o is not None]
    for o in [head] + body_parts:
        for k in o.data.shape_keys.key_blocks:
            k.value = 0.0
    try:
        out = [E._export([arm, head] + body_parts, os.path.join(E.EXPORT, "Human_Body.fbx"))]
    finally:
        for k in keys:
            k.value = saved[k.name]
        arm.scale = saved_scale
    out.append(E.export_hair())
    out += [E.export_cloth_family(f) for f in ("Rags", "Undead")]
    out += [E.export_config(), E.export_rig()]
    return out


# colour group "Horn" (sRGB): old yellowed horn, light enough to read against the ground at the game camera (a dark
# brown vanished over grass and earth); darker at the root (ClothData), where it meets the pale skin
HORN = ["#a8946a", "#9c8a62", "#b09c74", "#948258", "#a39070"]

GHOUL_WEAR = {
    "GhoulClaws": dict(slot="claws", layer=0, material="bone", group="Horn", make=build, builds=("Ghoul",), hide=[],
                       cover=[]),
}
