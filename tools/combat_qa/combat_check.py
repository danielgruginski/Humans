# Numeric clip check (run after combat_sheet.py set the character up): per frame, how deep the weapon's blade/shaft
# sits inside the body or clothes, whether it crosses the shield disc, and how much of the shield is inside the body.
# CHECK: [(clip, kit)]. Prints one line per clip with the worst frames.
import bpy, importlib, hum_anim
exec(open(r"E:\Unity\Projects\GameArtGeneration\Humans\tools\combat_qa\weapons_helper.py").read())
from mathutils import Vector
from mathutils.bvhtree import BVHTree
SEG = {"sword": ("SwordHelper", 0.06, 0.81), "twohand": ("GreatswordHelper", 0.07, 1.07),
       "spear": ("SpearHelper", -0.40, 1.77)}
MESHES = [bpy.data.objects["Body"], bpy.data.objects["Head"]]      # closed skin, outward normals (clothes have
                                                                   # inner shells and the beard is open: false hits)
rigob = bpy.data.objects["HumanRig"]


def hands():
    out = []
    for s in "lr":
        pb = rigob.pose.bones[f"hand_{s}"]
        a = rigob.matrix_world @ pb.head; b = rigob.matrix_world @ pb.tail
        out.append((a, b + (b - a).normalized() * 0.06))
    return out


def near_seg(p, a, b):
    ab = b - a; t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def depth(trees, p):
    worst = 0.0
    for t in trees:
        hit = t.find_nearest(p, 0.12)
        if hit[0] is not None and (p - hit[0]).dot(hit[1]) < 0:
            worst = max(worst, hit[3])
    return worst


def check(clip, kit):
    hum_anim.use(clip)
    n = hum_anim.CLIPS[clip][0]
    rows = []
    for fr in range(n + 1):
        bpy.context.scene.frame_set(fr)
        dg = bpy.context.evaluated_depsgraph_get()
        trees = [BVHTree.FromObject(o, dg) for o in MESHES]
        hs = hands()
        blade = shield_x = shield_in = 0.0
        if kit in SEG:
            name, y0, y1 = SEG[kit]
            M = bpy.data.objects[name].matrix_world
            k = int((y1 - y0) / 0.02)
            for i in range(k + 1):
                p = M @ Vector((0, y0 + (y1 - y0) * i / k, 0))
                if min(near_seg(p, a, b) for a, b in hs) < 0.07:
                    continue
                blade = max(blade, depth(trees, p))
        if kit == "sword":
            S = bpy.data.objects["ShieldHelper"].matrix_world
            c = S.translation; nrm = (S.to_3x3() @ Vector((0, 1, 0))).normalized()
            name, y0, y1 = SEG["sword"]
            M = bpy.data.objects[name].matrix_world
            a, b = M @ Vector((0, y0, 0)), M @ Vector((0, y1, 0))
            da, db = (a - c).dot(nrm), (b - c).dot(nrm)
            if da * db < 0:
                q = a.lerp(b, da / (da - db))
                r = (q - c).length
                if r < 0.29:
                    shield_x = 0.29 - r
            import math
            tang = (S.to_3x3() @ Vector((1, 0, 0))).normalized(); bit = nrm.cross(tang)
            cnt = 0
            for rr in (0.1, 0.2, 0.29):
                for j in range(16):
                    ang = j * math.pi / 8
                    p = c + (tang * math.cos(ang) + bit * math.sin(ang)) * rr
                    if min(near_seg(p, a2, b2) for a2, b2 in hs) < 0.07:
                        continue
                    if depth(trees, p) > 0.005:
                        cnt += 1
            shield_in = cnt
        rows.append((fr, blade, shield_x, shield_in))
    bad = [r for r in rows if r[1] > 0.01 or r[2] > 0 or r[3] > 0]
    print(clip, "max blade depth %.3f" % max(r[1] for r in rows),
          "| bad frames:", " ".join("%d(b%.2f s%.2f i%d)" % r for r in bad[:14]))


for clip, kit in CHECK:
    show(kit)
    check(clip, kit)
show("none")
bpy.context.scene.frame_set(0)
