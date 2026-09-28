r"""Build the Faces scene end to end.

    import sys; sys.path.insert(0, r"E:\Unity\Projects\GameArtGenerationHumanssrc")
    import hum_build
    hum_build.show()          # Faces scene on screen (own call: a scene switch applies after the call)
    hum_build.build_all()     # head, body, rig, keys, masks, hair, LODs
"""
import importlib
import bpy
import numpy as np

import hum_mpfb, hum_head, hum_scene, hum_uv, hum_paint, hum_material, hum_faces, hum_hair, hum_styles, hum_lod
import hum_rig, hum_body, hum_cloth

SCENE = "Faces"


def reload():
    for m in (hum_mpfb, hum_head, hum_scene, hum_uv, hum_paint, hum_hair, hum_styles, hum_lod, hum_material,
              hum_rig, hum_body, hum_faces, hum_cloth):
        importlib.reload(m)


def scene():
    sc = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    return sc


def show():
    bpy.context.window_manager.windows[0].scene = scene()


def build_head(sc=None):
    sc = sc or scene()
    src = hum_mpfb.source(sc)
    src.hide_set(True)
    src.hide_render = True
    rig = hum_head.Rig(src)
    ob = hum_head.build(sc, src, rig, materials=[hum_scene.clay(), hum_scene.clay("M_EyeClay", (1, 1, 1, 1))])
    V = np.array([v.co[:] for v in ob.data.vertices])
    ear_y = V[rig.regions['ears'], 1].mean()
    C = hum_head.full_coords(src, rig)
    mouth = rig.centre(C, 'joint-mouth')
    face, ear = hum_uv.mark_seams(ob, ear_y=ear_y, chin_z=mouth[2] - 0.055, face_back_y=ear_y - 0.035)
    hum_uv.unwrap(ob, face, ear)
    return ob, src, rig


def paint(ob):
    ia, ib = hum_paint.bake_head_masks(ob)
    ic = hum_hair.bake_skin_hair_mask(ob)
    ie = hum_paint.eye_mask()
    hum_paint.set_materials(ob, [hum_material.skin_material(ia, ib, ic), hum_material.eye_material(ie)])
    hum_material.set_props(ob)


def build_all():
    sc = scene()
    ob, src, rig = build_head()
    paint(ob)
    # skeleton + body from the same coordinate pipeline
    sk = hum_rig.Skeleton(src)
    bi = hum_body.BodyIndex(src, rig)
    C0 = hum_head.full_coords(src, rig)
    body = hum_body.build(sc, bi, C0, materials=[hum_scene.clay("M_BodyClay", (0.8, 0.6, 0.5, 1))])
    n, joints = hum_faces.add_shape_keys(ob, src, rig, sk, body, bi)
    hum_rig.JOINT_DELTAS.clear()
    hum_rig.JOINT_DELTAS.update(joints)
    hum_rig.SK = sk
    hum_rig.HEIGHT_RATIOS.clear()
    hum_rig.HEIGHT_RATIOS.update(hum_faces.height_ratios(src, rig))
    heads, tails = sk.ends(C0)
    arm = hum_rig.build_armature(sc, sk, heads, tails)
    ne = ob["n_eye_verts"] * 2
    hum_rig.skin(ob, arm, sk, sk.weight_matrix(np.concatenate([rig.head_idx, -1 - np.arange(ne)])))
    hum_rig.skin(body, arm, sk, sk.weight_matrix(bi.idx))
    joints = dict(zip(sk.bones, heads))
    nipple_z = float(C0[hum_mpfb.group_members(src, "nipple")][:, 2].mean())
    ma, mb = hum_body.paint_masks(body, sk, joints, nipple_z)
    hum_paint.set_materials(body, [hum_material.body_material(ma, mb)])
    hum_material.set_body_props(body, (0.62, 0.40, 0.30))
    tris = lambda o: sum(len(p.vertices) - 2 for p in o.data.polygons)
    print(f"Head: {tris(ob)} tris, {n} keys; Body: {tris(body)} tris, "
          f"{len(body.data.shape_keys.key_blocks) - 1} keys; rig {len(sk.bones)} bones")
    # body builds: face keys become head-only (faded at the neck edge), body keys stay for the builds;
    # before anything binds to the head's keys
    import hum_builds
    print("split keys:", hum_builds.split_keys(ob, body, sk))
    build_hair(ob)
    for name, (t, k) in hum_lod.build_all(sc, ob).items():
        print(f"{name}: {t} tris, {k} keys")
    for name, (t, k) in hum_cloth.build_all(sc, body, arm, sk).items():      # writes the body's Region UV
        print(f"{name}: {t} tris, {k} keys")
    for name, (t, k) in hum_lod.body_lods(sc, body).items():
        print(f"{name}: {t} tris, {k} keys")
    skin_all(arm, sk)
    aim_cameras(ob)
    return ob


def skin_all(arm, sk):
    """Hair pieces rigid on the head bone; LOD heads/bodies get weights interpolated from LOD0."""
    head, body = bpy.data.objects["Head"], bpy.data.objects["Body"]
    for cname in ("HUM_Hair", "HUM_LOD1", "HUM_LOD2"):
        col = bpy.data.collections.get(cname)
        for o in (col.objects if col else []):
            if o.name.startswith("Head_"):
                hum_rig.skin(o, arm, sk, hum_rig.transfer_weights(o, head, sk))
            elif o.name.startswith("Body_"):
                hum_rig.skin(o, arm, sk, hum_rig.transfer_weights(o, body, sk))
            elif o.name.startswith("Cloth_"):
                continue                                  # skinned by hum_cloth
            elif o.name.startswith("Hair_"):
                hum_rig.skin(o, arm, sk, hum_hair.hair_weights(o, sk, arm))
            else:
                hum_rig.rigid(o, arm, sk, "head")


def aim_cameras(head):
    import mathutils
    V = np.array([v.co[:] for v in head.data.vertices])
    c = mathutils.Vector(((V[:, 0].min() + V[:, 0].max()) / 2, V[:, 1].mean() + 0.02, V[:, 2].mean() + 0.03))
    for v in ("Front", "34", "Side", "Back"):
        hum_scene.camera(scene(), "Cam_" + v, c, v)


def build_hair(head=None):
    """Every hairstyle, beard and brow set as its own object in HUM_Hair, bound to the head keys."""
    head = head or bpy.data.objects["Head"]
    if bpy.data.objects.get("HumanRig"):
        hum_rig.rest(bpy.data.objects["HumanRig"])
    sc = scene()
    for k in head.data.shape_keys.key_blocks[1:]:
        k.value = 0.0
    H = hum_hair.HeadFrame(head)
    mat = hum_material.hair_material(hum_paint.strand_texture())
    for kind, table in (("hair", hum_styles.HAIR), ("beard", hum_styles.BEARD), ("brows", hum_styles.BROWS)):
        for name in table:
            ob = hum_styles.build(sc, H, kind, name)
            hum_paint.set_materials(ob, [mat])
            nk, err = hum_hair.bind_keys(ob, head)
            if kind == "hair":
                hum_hair.smooth_keys_spatial(ob)
            hum_material.set_hair_props(ob, (0.08, 0.05, 0.03))
            ob.hide_set(True)
            ob.hide_render = True
            print(f"{ob.name}: {hum_hair.tris(ob)} tris, {nk} keys")
