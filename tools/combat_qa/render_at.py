import bpy, math
from mathutils import Vector


def render_at(target, dist, path, yaw=30, pitch=10, lens=50, res=700, hide=()):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("_DbgCam")
    if cam is None:
        cam = bpy.data.objects.new("_DbgCam", bpy.data.cameras.new("_DbgCam"))
        sc.collection.objects.link(cam)
    cam.data.lens = lens
    t = Vector(target)
    y, p = math.radians(yaw), math.radians(pitch)
    d = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
    cam.location = t + d * dist
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    old = sc.camera
    sc.camera = cam
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.filepath = path
    hidden = []
    for o in sc.objects:
        if any(o.name.startswith(h) for h in hide) and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False
    sc.camera = old
