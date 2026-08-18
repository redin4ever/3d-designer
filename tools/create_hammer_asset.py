"""Build a finished futuristic hammer hero asset with forge3d's Blender backend."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import build_app  # noqa: E402
from contracts import Operation, Quat, Transform, Vec3  # noqa: E402


app = build_app(prefer_blender=True, include_raw=True, attach_viewer=False)
engine = app.engine
if not engine.backend_name.startswith("bpy-"):
    raise RuntimeError(f"A real Blender backend is required, got {engine.backend_name}")

counter = 0


def perform(operation_kind: str, **params):
    global counter
    counter += 1
    result = app.handlers[operation_kind](
        engine,
        Operation(op_id=f"hammer-{counter:03d}-{operation_kind}", kind=operation_kind, params=params),
    )
    if not result.ok:
        raise RuntimeError(f"{operation_kind} failed: {result.error_detail}")
    return result


def xform(at, axis=None, angle=0.0):
    return Transform(
        translation=Vec3(*at),
        rotation=Quat.from_axis_angle(Vec3(*axis), angle) if axis else Quat(),
    )


def primitive(name: str, kind: str, size, at, axis=None, angle=0.0):
    return perform(
        "add_primitive", object_id=name, kind=kind, size=size,
        transform=xform(at, axis, angle),
    ).produced_objects[0]


def box(name: str, size, at, axis=None, angle=0.0):
    return primitive(name, "cube", size, at, axis, angle)


# Presentation plinth and an understated technical grid.
primitive("plinth", "cylinder", [8.2, 8.2, 0.28], (0.0, 0.0, 0.14))
primitive("plinth_inner", "cylinder", [6.9, 6.9, 0.12], (0.0, 0.0, 0.34))
primitive("plinth_ring", "torus", [7.25, 7.25, 0.18], (0.0, 0.0, 0.43))
for i, offset in enumerate((-3.1, -1.55, 0.0, 1.55, 3.1)):
    box(f"grid_x_{i}", [0.035, 6.7, 0.025], (offset, 0.0, 0.42))
for i, offset in enumerate((-2.4, -0.8, 0.8, 2.4)):
    box(f"grid_y_{i}", [6.7, 0.035, 0.026], (0.0, offset, 0.42))

# Handle: a deep composite grip with copper collars and cyan pulse rings.
primitive("handle_core", "cylinder", [0.62, 0.62, 4.45], (0.0, 0.0, 2.72))
primitive("handle_spine", "cylinder", [0.18, 0.18, 4.56], (0.0, 0.0, 2.72))
for i, z in enumerate((0.72, 1.12, 1.52, 1.92, 2.32, 2.72, 3.12, 3.52, 3.92, 4.32)):
    primitive(f"grip_ring_{i}", "torus", [0.72, 0.72, 0.11], (0.0, 0.0, z))
for i, z in enumerate((0.84, 1.64, 2.44, 3.24, 4.04)):
    primitive(f"pulse_ring_{i}", "torus", [0.80, 0.80, 0.035], (0.0, 0.0, z))
primitive("pommel", "sphere", [1.02, 1.02, 0.52], (0.0, 0.0, 0.56))
primitive("pommel_cap", "cylinder", [0.84, 0.84, 0.20], (0.0, 0.0, 0.34))

# The hero head is built by the same fitted semantic operation available to connected agents.
perform("add_impact_head",
        object_id="hero_head", origin=[0.0, 0.0, 5.78], width=3.5, depth=1.45,
        height=1.50, corner_chamfer=0.24, plate_thickness=0.12, plate_inset=0.28,
        shoulder_depth=0.42, shoulder_diameter=0.90, socket_depth=0.18,
        collar_depth=0.20, collar_diameter=1.28, face_depth=0.48,
        face_diameter=1.60, striker_depth=0.11, striker_socket_depth=0.045,
        striker_diameter=0.78, rim_depth=0.10, rim_overhang=0.10,
        handle_socket_diameter=0.72, handle_socket_depth=0.22,
        handle_collar_depth=0.18, handle_collar_overhang=0.11,
        bevel_width=0.025)

# Material palette: near-black steel, warm copper, ceramic grey, and electric cyan.
materials = {
    "void_steel": ((0.035, 0.050, 0.070), 0.34, 0.84),
    "mid_steel": ((0.105, 0.135, 0.16), 0.34, 0.82),
    "edge_steel": ((0.34, 0.40, 0.45), 0.22, 0.92),
    "copper": ((0.52, 0.16, 0.055), 0.30, 0.78),
    "ceramic": ((0.22, 0.26, 0.28), 0.44, 0.35),
    "ion": ((0.01, 0.42, 0.58), 0.18, 0.25),
    "plinth": ((0.012, 0.018, 0.028), 0.68, 0.30),
}
for name, (color, roughness, metallic) in materials.items():
    engine.create_material(name, color)
    engine.set_pbr(name, roughness=roughness, metallic=metallic)

for name in engine.list_objects():
    mat = "mid_steel"
    if name.startswith(("plinth", "grid_")): mat = "plinth"
    elif name.startswith(("handle_core", "handle_spine")) or name == "hero_head_body": mat = "void_steel"
    elif name.startswith(("grip_ring", "pommel", "pommel_cap")): mat = "copper"
    elif name.startswith("pulse_") or name.startswith("hero_head_rim_"): mat = "ion"
    elif name == "hero_head_top_plate" or name.startswith("hero_head_cheek_"): mat = "ceramic"
    elif name.startswith("hero_head_shoulder_") or name == "hero_head_handle_socket": mat = "mid_steel"
    elif name.startswith("hero_head_collar_") or name == "hero_head_handle_collar": mat = "copper"
    elif name.startswith("hero_head_face_"): mat = "edge_steel"
    elif name.startswith("hero_head_striker_"): mat = "void_steel"
    engine.assign_material(name, mat)

for name in engine.list_objects():
    if name.startswith(("grid_", "hero_head_")):
        continue
    try:
        engine.bevel_edges(name, width=0.018, segments=3)
    except Exception:
        pass

artifacts = ROOT / "artifacts"
artifacts.mkdir(exist_ok=True)
blend_path = artifacts / "futuristic_hammer.blend"
render_path = artifacts / "futuristic_hammer.png"
glb_path = artifacts / "futuristic_hammer.glb"

engine.execute(
    """
bpy = __import__('bpy')
from mathutils import Vector

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(render_path)
scene.render.film_transparent = False

world = scene.world or bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
bg.inputs['Color'].default_value = (0.004, 0.009, 0.018, 1.0)
bg.inputs['Strength'].default_value = 0.32

def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

camera_data = bpy.data.cameras.new('HammerHeroCamera')
camera = bpy.data.objects.new('HammerHeroCamera', camera_data)
scene.collection.objects.link(camera)
camera.location = (9.2, -12.8, 8.2)
camera_data.lens = 58
point_at(camera, (0.0, 0.0, 3.15))
scene.camera = camera

def area(name, energy, size, location, color):
    data = bpy.data.lights.new(name, type='AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    point_at(obj, (0.0, 0.0, 3.3))
    return obj

area('Key', 1250, 5.5, (-5.5, -7.5, 10.5), (0.56, 0.78, 1.0))
area('WarmRim', 980, 4.5, (6.5, 3.0, 7.5), (1.0, 0.32, 0.12))
area('TopFill', 1150, 4.0, (0.0, 1.5, 12.0), (0.12, 0.65, 1.0))
area('CameraFill', 1550, 5.0, (4.5, -9.5, 6.8), (0.38, 0.62, 1.0))

sun_data = bpy.data.lights.new('StructuralKey', type='SUN')
sun_data.energy = 2.4
sun_data.angle = 0.22
sun = bpy.data.objects.new('StructuralKey', sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (0.55, -0.38, -0.72)

mat = bpy.data.materials.get('ion')
if mat and mat.node_tree:
    bsdf = next((node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for socket in bsdf.inputs:
            if socket.name in {'Emission Color', 'Emission'}:
                socket.default_value = (0.0, 0.42, 0.82, 1.0)
            elif socket.name == 'Emission Strength':
                socket.default_value = 4.2

scene.view_settings.look = 'AgX - Medium High Contrast'
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)
""",
    {"blend_path": blend_path, "render_path": render_path},
)

engine.export_model(engine.list_objects(), str(glb_path), y_up=True, apply_modifiers=True)
print(f"Created {len(engine.list_objects())} mesh objects")
print(blend_path)
print(glb_path)
print(render_path)
