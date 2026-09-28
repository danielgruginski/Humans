# Stand-in weapons for Blender previews, bone-parented like the axe helper (tool_helper.py):
# SwordHelper / GreatswordHelper / SpearHelper on hand_r's grip frame (origin in the fist, +Y along the handle
# toward the head, +Z the knuckles' way), ShieldHelper on lowerarm_l (strapped: its face along the back of the
# forearm). show(kind) hides all but one set.
import bpy, bmesh, math, hum_anim
from mathutils import Matrix, Quaternion, Vector
H = hum_anim
rig = H.Rig()
ob = bpy.data.objects["HumanRig"]


def grip_frame(s="r", roll=0.0):
    o = rig.head[f"hand_{s}"] + rig.fist[s]
    y = rig.grip_axis[s].normalized()
    z = rig.strike_axis[s]
    z = (z - y * y.dot(z)).normalized()
    z = Quaternion(y, math.radians(roll)) @ z
    x = y.cross(z)
    return Matrix((x, y, z)).transposed().to_4x4(), o


def box(bm, c, size):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*size, 1.0)))


def cyl(bm, y0, y1, r, segs=10):
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=y1 - y0,
                          matrix=Matrix.Translation((0, (y0 + y1) / 2, 0)) @ Matrix.Rotation(math.radians(-90), 4, "X"))


def make(name, build, color):
    me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
    o.data = me
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    mat = bpy.data.materials.get(name + "Mat") or bpy.data.materials.new(name + "Mat")
    mat.diffuse_color = color
    if not me.materials:
        me.materials.append(mat)
    return o


def attach(o, bone_name, M):
    bone = ob.data.bones[bone_name]
    o.parent = ob
    o.parent_type = 'BONE'
    o.parent_bone = bone_name
    o.matrix_parent_inverse = Matrix.Translation((0, -bone.length, 0))    # bone parenting is at the tail
    o.matrix_basis = bone.matrix_local.inverted() @ M


def sword(bm):                                   # 75 cm blade, cross guard, grip, pommel
    box(bm, (0, 0.06 + 0.375, 0), (0.008, 0.75, 0.045))
    box(bm, (0, 0.055, 0), (0.025, 0.02, 0.17))
    cyl(bm, -0.07, 0.05, 0.015)
    box(bm, (0, -0.08, 0), (0.03, 0.03, 0.03))


def greatsword(bm):                              # 1 m blade from above the right fist; grip down past the left
    box(bm, (0, 0.07 + 0.5, 0), (0.01, 1.0, 0.055))
    box(bm, (0, 0.06, 0), (0.03, 0.025, 0.26))
    cyl(bm, -0.23, 0.06, 0.016)
    box(bm, (0, -0.24, 0), (0.035, 0.035, 0.035))


def spear(bm):                                   # 2 m: the butt 40 cm behind the right fist, the head in front
    cyl(bm, -0.40, 1.55, 0.016)
    box(bm, (0, 1.66, 0), (0.008, 0.22, 0.05))


def shield(bm):                                  # round, 58 cm: a flat disc on the forearm, a boss
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.29, radius2=0.29, depth=0.015,
                          matrix=Matrix.Rotation(math.radians(-90), 4, "X"))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.06, radius2=0.03, depth=0.04,
                          matrix=Matrix.Translation((0, 0.025, 0)) @ Matrix.Rotation(math.radians(-90), 4, "X"))


R, o = grip_frame("r", globals().get("SWORD_ROLL", 0.0))
for name, fn, color in (("SwordHelper", sword, (0.62, 0.62, 0.66, 1)), ("GreatswordHelper", greatsword, (0.62, 0.62, 0.66, 1)),
                        ("SpearHelper", spear, (0.45, 0.30, 0.17, 1))):
    attach(make(name, fn, color), "hand_r", Matrix.Translation(o) @ R)
# the shield: on the forearm's back (dorsal) side, its face (+Y of the disc) that way
fa, fh = rig.head["lowerarm_l"], rig.head["hand_l"]
axis = (fh - fa).normalized()
dors = rig.dorsal["l"]
dors = (dors - axis * axis.dot(dors)).normalized()
centre = fa.lerp(fh, 0.55) + dors * 0.06
Ms = Matrix((axis, dors, axis.cross(dors))).transposed().to_4x4()
attach(make("ShieldHelper", shield, (0.40, 0.24, 0.12, 1)), "lowerarm_l", Matrix.Translation(centre) @ Ms)

KIT = {"sword": ("SwordHelper", "ShieldHelper"), "twohand": ("GreatswordHelper",), "spear": ("SpearHelper",),
       "none": ()}


def show(kind):
    for k in ("SwordHelper", "ShieldHelper", "GreatswordHelper", "SpearHelper"):
        o2 = bpy.data.objects[k]
        on = k in KIT[kind]
        o2.hide_render = not on
        o2.hide_set(not on)


show(globals().get("KIT_SHOW", "none"))
print("weapon helpers ready")
