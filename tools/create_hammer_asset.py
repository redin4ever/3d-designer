"""Build a finished futuristic hammer hero asset with forge3d's Blender backend."""

from __future__ import annotations

import math
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


def prism(name: str, profile, depth: float, at=(0.0, 0.0, 0.0)):
    """Create a closed extruded X/Z profile, centred around the local Y axis."""
    half = depth / 2.0
    verts = [Vec3(x, -half, z) for x, z in profile] + [Vec3(x, half, z) for x, z in profile]
    n = len(profile)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return engine.create_mesh(name, verts, faces, xform(at))


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
primitive("neck_collar", "cylinder", [0.95, 0.95, 0.32], (0.0, 0.0, 4.88))
primitive("neck_ring", "torus", [1.06, 1.06, 0.13], (0.0, 0.0, 5.02))

# Main head: an angular silhouette instead of a single rectangular block.
profile = [
    (-2.05, -0.42), (-1.66, -0.78), (-0.72, -0.70), (-0.28, -0.50),
    (0.28, -0.50), (0.72, -0.70), (1.66, -0.78), (2.05, -0.42),
    (1.82, 0.42), (1.14, 0.74), (0.40, 0.58), (0.0, 0.72),
    (-0.40, 0.58), (-1.14, 0.74), (-1.82, 0.42),
]
prism("head_shell", profile, 1.22, (0.0, 0.0, 5.76))
box("head_core", [1.28, 1.42, 0.92], (0.0, 0.0, 5.76))
box("head_top_rail", [2.2, 1.48, 0.14], (0.0, 0.0, 6.46), axis=(0, 1, 0), angle=math.radians(-5))
box("head_bottom_rail", [2.15, 1.44, 0.14], (0.0, 0.0, 5.08), axis=(0, 1, 0), angle=math.radians(5))

# Striking faces, rear claw geometry, and the contained ion reactor.
for side, x in (("left", -2.08), ("right", 2.08)):
    primitive(f"strike_face_{side}", "cylinder", [0.66, 1.52, 1.52], (x, 0.0, 5.76), axis=(0, 1, 0), angle=math.pi / 2)
    primitive(f"strike_ring_{side}", "torus", [0.22, 1.64, 1.64], (x + (-0.34 if side == "left" else 0.34), 0.0, 5.76), axis=(0, 1, 0), angle=math.pi / 2)
for y, z in ((-0.36, 5.50), (0.36, 5.50)):
    primitive(f"claw_{'lower' if y < 0 else 'upper'}", "cone", [1.05, 0.30, 0.30], (2.34, y, z), axis=(0, 1, 0), angle=math.pi / 2)
    box(f"claw_guard_{'lower' if y < 0 else 'upper'}", [0.36, 0.15, 0.72], (1.78, y, z), axis=(0, 1, 0), angle=math.radians(28))
primitive("ion_reactor", "cylinder", [0.62, 0.54, 0.54], (0.0, 0.0, 5.76), axis=(0, 1, 0), angle=math.pi / 2)
primitive("ion_reactor_ring", "torus", [0.78, 0.78, 0.10], (0.0, 0.0, 5.76), axis=(0, 1, 0), angle=math.pi / 2)

# Face plates and service lines give the head a designed, manufactured language.
for side, x in (("left", -0.84), ("right", 0.84)):
    tilt = math.radians(18 if x > 0 else -18)
    box(f"cheek_{side}", [0.16, 1.46, 0.92], (x, 0.0, 5.76), axis=(0, 1, 0), angle=tilt)
    box(f"cheek_light_{side}", [0.06, 1.18, 0.12], (x + (0.10 if x > 0 else -0.10), 0.0, 5.76), axis=(0, 1, 0), angle=tilt)
for y in (-0.53, 0.53):
    box(f"service_line_{'front' if y < 0 else 'back'}", [1.32, 0.05, 0.08], (0.0, y, 5.76))

# Two floating status fins make the presentation read as a premium game asset.
for side, x in (("left", -3.0), ("right", 3.0)):
    tilt = math.radians(18 if x > 0 else -18)
    box(f"status_fin_{side}", [0.12, 1.08, 0.88], (x, 0.0, 5.76), axis=(0, 1, 0), angle=tilt)
    primitive(f"status_node_{side}", "sphere", [0.22, 0.22, 0.22], (x + (0.08 if x > 0 else -0.08), -0.58, 5.76))

# Material palette: near-black steel, warm copper, ceramic grey, and electric cyan.
materials = {
    "void_steel": ((0.018, 0.025, 0.036), 0.28, 0.90),
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
    elif name.startswith(("handle_core", "handle_spine", "head_core", "head_shell")): mat = "void_steel"
    elif name.startswith(("grip_ring", "pommel", "pommel_cap", "neck_")): mat = "copper"
    elif name.startswith(("pulse_", "ion_", "status_node", "service_line", "cheek_light")): mat = "ion"
    elif name.startswith(("strike_face", "strike_ring")): mat = "edge_steel"
    elif name.startswith(("head_", "claw", "cheek", "status_fin")): mat = "ceramic"
    engine.assign_material(name, mat)

for name in engine.list_objects():
    if name.startswith("grid_"):
        continue
    try:
        engine.bevel_edges(name, width=0.035 if name in {"head_shell", "head_core"} else 0.018, segments=3)
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
bg.inputs['Strength'].default_value = 0.20

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

mat = bpy.data.materials.get('ion')
if mat and mat.node_tree:
    bsdf = next((node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for socket in bsdf.inputs:
            if socket.name in {'Emission Color', 'Emission'}:
                socket.default_value = (0.0, 0.55, 1.0, 1.0)
            elif socket.name == 'Emission Strength':
                socket.default_value = 7.0

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
