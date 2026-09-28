"""Portrait cameras, lights and contact-sheet renders for the Faces scene."""
import os
import bpy
import numpy as np
from mathutils import Vector

ROOT = r"E:\Unity\Projects\GameArtGeneration\Humans"
RENDERS = os.path.join(ROOT, "renders")

# name: (offset from the face target, lens)
VIEWS = {
    "Front": (Vector((0.0, -0.75, 0.0)), 85),
    "34": (Vector((0.42, -0.62, 0.03)), 85),
    "Side": (Vector((0.75, 0.0, 0.0)), 85),
    "Back": (Vector((0.0, 0.75, 0.05)), 85),
}


def look_at(ob, target):
    ob.rotation_euler = (target - ob.location).to_track_quat('-Z', 'Y').to_euler()


def camera(scene, name, target, view):
    off, lens = VIEWS[view]
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(ob)
    ob.data.lens = lens
    ob.location = target + off
    look_at(ob, target)
    return ob


def render(scene, cam, path, size=640):
    scene.camera = cam
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=scene.name)
    return path


def read_png(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def sheet(paths, cols, out, pad=4):
    """Tile equally sized PNGs (row-major, first path top-left) into one PNG."""
    tiles = [read_png(p) for p in paths]
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + cols - 1) // cols
    H, W = rows * h + (rows - 1) * pad, cols * w + (cols - 1) * pad
    canvas = np.ones((H, W, 4), np.float32)
    canvas[..., :3] = 0.08
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y0 = H - (r + 1) * h - r * pad          # Blender images are bottom-up
        x0 = c * (w + pad)
        canvas[y0:y0 + h, x0:x0 + w] = t
    img = bpy.data.images.new("_sheet", W, H, alpha=True)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = out
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return out


def clay(name="M_Clay", color=(0.8, 0.6, 0.5, 1)):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    b = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = color
    b.inputs['Roughness'].default_value = 0.6
    return mat


def eye_preview(name="M_EyePreview", iris=(0.18, 0.35, 0.55, 1)):
    """Procedural eye from the front-projected UV: sclera, iris ring, pupil, glossy."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    b.inputs['Roughness'].default_value = 0.08
    uv = nt.nodes.new('ShaderNodeUVMap')
    sub = nt.nodes.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    cr.interpolation = 'LINEAR'
    stops = [(0.0, (0.01, 0.01, 0.01, 1)), (0.11, (0.01, 0.01, 0.01, 1)), (0.125, iris),
             (0.23, tuple(c * 0.55 for c in iris[:3]) + (1,)), (0.255, (0.05, 0.04, 0.04, 1)),
             (0.27, (0.85, 0.82, 0.78, 1)), (1.0, (0.8, 0.72, 0.7, 1))]
    cr.elements[0].position, cr.elements[0].color = stops[0]
    cr.elements[1].position, cr.elements[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        e = cr.elements.new(pos); e.color = col
    nt.links.new(uv.outputs[0], sub.inputs[0])
    nt.links.new(sub.outputs[0], ln.inputs[0])
    nt.links.new(ln.outputs['Value'], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs['Base Color'])
    nt.links.new(b.outputs[0], out.inputs[0])
    return mat
