"""Drive an MPFB (MakeHuman) base mesh and read back vertex positions.

The MPFB human is only a *source*: every face slider we ship is captured from it as
"coords with the slider on" minus "coords at the neutral face", then stored as a shape
key on our own head mesh. MPFB assets (base mesh, targets) are CC0.
"""
import bpy
import numpy as np
from mathutils import Vector

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.entities.objectproperties import HumanObjectProperties

SOURCE = "MPFB_Source"
WORK = "HUM_Work"

MACRO_DEFAULT = dict(gender=0.5, age=0.5, muscle=0.5, weight=0.5, proportions=0.5,
                     height=0.5, cupsize=0.5, firmness=0.5)
RACE_DEFAULT = dict(african=1 / 3, asian=1 / 3, caucasian=1 / 3)


def work_collection(scene):
    col = bpy.data.collections.get(WORK)
    if col is None:
        col = bpy.data.collections.new(WORK)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def source(scene=None):
    """The MPFB human (created once, kept hidden in HUM_Work)."""
    ob = bpy.data.objects.get(SOURCE)
    if ob is not None:
        return ob
    scene = scene or bpy.context.window_manager.windows[0].scene
    ob = HumanService.create_human(mask_helpers=False, detailed_helpers=True,
                                   extra_vertex_groups=True, feet_on_ground=True)
    ob.name = SOURCE
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    work_collection(scene).objects.link(ob)
    ob.hide_render = True
    return ob


def group_members(ob, name, thresh=0.5):
    gi = ob.vertex_groups[name].index
    return np.array([v.index for v in ob.data.vertices
                     if any(g.group == gi and g.weight > thresh for g in v.groups)], dtype=np.int64)


# ------------------------------------------------------------------ targets

_LOADED = set()


def _key(ob, name):
    kb = ob.data.shape_keys.key_blocks if ob.data.shape_keys else None
    return kb.get(name) if kb else None


def ensure_target(ob, name):
    """Load an MPFB detail target (e.g. 'l-eye-scale-incr') as a shape key named after it."""
    k = _key(ob, name)
    if k is None:
        path = TargetService.target_full_path(name)
        if path is None:
            raise KeyError(f"MPFB target not found: {name}")
        k = TargetService.load_target(ob, path, weight=0.0, name=name)
    return k


def set_state(ob, macros=None, race=None, targets=None):
    """Put the source human in a state: macro sliders (0..1), race mix, detail targets.

    `targets` maps MPFB target names to weights; a signed weight picks the -decr/-incr style
    pair via `pair_target`. Every detail target not listed goes back to 0.
    """
    m = dict(MACRO_DEFAULT, **(macros or {}))
    r = dict(RACE_DEFAULT, **(race or {}))
    for k, v in m.items():
        HumanObjectProperties.set_value(k, float(v), entity_reference=ob)
    for k, v in r.items():
        HumanObjectProperties.set_value(k, float(v), entity_reference=ob)
    TargetService.reapply_macro_details(ob, remove_zero_weight_targets=False)
    for kb in ob.data.shape_keys.key_blocks[1:]:
        if not kb.name.startswith("$md"):
            kb.value = 0.0
    for name, w in (targets or {}).items():
        ensure_target(ob, name).value = float(w)


def coords(ob):
    """Vertex positions of the current shape-key mix (relative keys, so a plain weighted sum)."""
    me = ob.data
    n = len(me.vertices)
    kbs = me.shape_keys.key_blocks
    basis = np.empty(n * 3, np.float32)
    kbs[0].data.foreach_get("co", basis)
    out = basis.astype(np.float64)
    tmp = np.empty(n * 3, np.float32)
    for kb in kbs[1:]:
        if kb.mute or abs(kb.value) < 1e-6:
            continue
        kb.data.foreach_get("co", tmp)
        out += kb.value * (tmp - basis)
    return out.reshape(n, 3)


def capture(ob, macros=None, race=None, targets=None):
    set_state(ob, macros, race, targets)
    return coords(ob)
