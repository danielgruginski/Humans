# CLIPS: [(clip, kit)], FRAMES_N frames per clip (evenly spread), VIEWS [(yaw, dist)], OUT
import bpy, numpy as np, importlib, hum_faces, hum_builds, hum_anim
importlib.reload(hum_anim)
exec(open(r"E:\Unity\Projects\GameArtGeneration\Humans\tools\combat_qa\rfeet.py").read())
exec(open(r"E:\Unity\Projects\GameArtGeneration\Humans\tools\combat_qa\weapons_helper.py").read())
head = bpy.data.objects["Head"]; S = hum_faces.srgb
d = r"E:\Unity\Projects\GameArtGeneration\Humans\renders\_tmp\\"
TAG = globals().get("TAG", "MStrong")
FRAMES_N = globals().get("FRAMES_N", 7)
VIEWS = globals().get("VIEWS", [(90, 3.0), (25, 3.0)])
f = hum_faces.random_face(3)
f["keys"] = {k: v for k, v in f["keys"].items() if k not in hum_builds.BODY_KEYS}
f["keys"].update(hum_builds.BUILDS[TAG]["keys"]); f["build"] = TAG
f["outfit"] = globals().get("OUTFIT", {"Shirt": S("#d6ccb2"), "Trousers": S("#5e5344"), "Boots": S("#3a2415")})
hum_faces.apply_face(head, f)
hum_anim.build_clips([c for c, k in CLIPS])
rows = []
for clip, kit in CLIPS:
    show(kit)
    hum_anim.use(clip)
    n = hum_anim.CLIPS[clip][0]
    frames = globals().get("FRAMES") or [round(i * n / FRAMES_N) for i in range(FRAMES_N)]
    for yaw, dist in VIEWS:
        arrs = []
        for fr in frames:
            bpy.context.scene.frame_set(fr)
            p = d + "cs.png"
            render_at((0, -0.1, 0.95), dist, p, yaw=yaw, pitch=4, res=globals().get("RES", 230))
            im = bpy.data.images.load(p); w, h = im.size
            arrs.append(np.array(im.pixels[:]).reshape(h, w, 4)); bpy.data.images.remove(im)
        rows.append(np.concatenate(arrs, 1))
show("none")
A_ = np.concatenate(rows[::-1], 0)
out = bpy.data.images.new("_s", A_.shape[1], A_.shape[0], alpha=True)
out.pixels[:] = A_.ravel(); out.filepath_raw = d + OUT; out.file_format = 'PNG'; out.save()
bpy.data.images.remove(out)
bpy.context.scene.frame_set(0)
print("ok")
