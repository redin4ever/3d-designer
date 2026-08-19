"""Build the user-facing house artifact with forge3d's real Blender backend."""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import build_app  # noqa: E402
from contracts import Operation, Vec3  # noqa: E402


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
        Operation(
            op_id=f"house-{counter:03d}-{operation_kind}",
            kind=operation_kind,
            params=params,
        ),
    )
    if not result.ok:
        raise RuntimeError(f"{operation_kind} failed: {result.error_detail}")
    return result


def box(name: str, size, at):
    return perform(
        "add_primitive",
        object_id=name,
        kind="cube",
        size=size,
        transform={"translation": at},
    ).produced_objects[0]


def primitive(name: str, kind: str, size, at):
    return perform(
        "add_primitive",
        object_id=name,
        kind=kind,
        size=size,
        transform={"translation": at},
    ).produced_objects[0]


# Site, foundation and shell.
box("lawn", [13.5, 12.0, 0.18], [0.0, 0.0, -0.09])
perform("add_floor", object_id="foundation", width=8.4, depth=6.4, thickness=0.45,
        origin=[0.0, 0.0, 0.225])

wall_base = 0.45
wall_top = 3.45
wall_height = wall_top - wall_base
perform("add_wall", object_id="wall_front", start=[-4, -3, wall_base], end=[4, -3, wall_base],
        height=wall_height, thickness=0.22)
perform("add_wall", object_id="wall_back", start=[4, 3, wall_base], end=[-4, 3, wall_base],
        height=wall_height, thickness=0.22)
perform("add_wall", object_id="wall_left", start=[-4, 3, wall_base], end=[-4, -3, wall_base],
        height=wall_height, thickness=0.22)
perform("add_wall", object_id="wall_right", start=[4, -3, wall_base], end=[4, 3, wall_base],
        height=wall_height, thickness=0.22)

# Openings are cut from the actual wall meshes.
for wall, position, width, height, sill in (
    ("wall_front", 4.0, 1.2, 2.25, 0.0),
    ("wall_front", 1.35, 1.25, 1.25, 0.85),
    ("wall_front", 6.65, 1.25, 1.25, 0.85),
    ("wall_back", 2.0, 1.6, 1.3, 0.8),
    ("wall_back", 6.0, 1.6, 1.3, 0.8),
    ("wall_left", 1.65, 1.35, 1.25, 0.85),
    ("wall_left", 4.35, 1.35, 1.25, 0.85),
    ("wall_right", 3.0, 1.8, 1.35, 0.8),
):
    perform("add_opening", object_id=f"opening_{wall}_{position}", wall_id=wall,
            position=position, width=width, height=height, sill_height=sill)

perform(
    "add_gable_roof", object_id="main_roof", origin=[0, 0, wall_top], width=8.0, depth=6.0,
    pitch_degrees=33.0, thickness=0.18, overhang=0.48, trim_width=0.15,
    trim_depth=0.20, ridge_axis="y",
)

# The roof operation intentionally produces roofing rather than wall infill. Close the two
# gable ends so this is a complete weather-tight visual shell, not an open demonstration.
ridge_z = wall_top + math.tan(math.radians(33.0)) * 4.0
for label, y0 in (("front", -3.0), ("back", 3.0)):
    y_a, y_b = y0 - 0.11, y0 + 0.11
    vertices = [
        Vec3(-4.0, y_a, wall_top), Vec3(4.0, y_a, wall_top), Vec3(0.0, y_a, ridge_z),
        Vec3(-4.0, y_b, wall_top), Vec3(4.0, y_b, wall_top), Vec3(0.0, y_b, ridge_z),
    ]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    engine.create_mesh(f"wall_gable_{label}", vertices, faces)
perform(
    "add_chimney", object_id="chimney", origin=[2.35, 0.75, 4.18], width=0.78, depth=0.66,
    shaft_height=2.0, flashing_overhang=0.16, flashing_height=0.18, crown_overhang=0.12,
    crown_height=0.18, flue_count=2, flue_radius=0.105, flue_wall_thickness=0.025,
    flue_height=0.42, rim_overhang=0.035, rim_height=0.065,
)

# Front porch, canopy, supported steps and railings.
perform("add_floor", object_id="porch", width=3.25, depth=1.55, thickness=0.18,
        origin=[0.0, -3.72, 0.36])
perform(
    "add_staircase_to_landing", object_id="entry_stair", landing_id="porch",
    start=[0.0, -5.15, 0.0], treads=3, width=1.65, tread_thickness=0.08,
    stringer_width=0.10, stringer_depth=0.20,
)
for x in (-1.35, 1.35):
    box(f"porch_column_{'left' if x < 0 else 'right'}", [0.16, 0.16, 2.28],
        [x, -4.23, 1.59])
perform(
    "add_gable_roof", object_id="porch_roof", origin=[0, -3.72, 2.78], width=3.35, depth=1.75,
    pitch_degrees=24.0, thickness=0.13, overhang=0.18, trim_width=0.10,
    trim_depth=0.13, ridge_axis="y",
)
for side, x in (("left", -0.88), ("right", 0.88)):
    perform("add_railing", object_id=f"stair_rail_{side}",
            path=[[x, -5.15, 0.02], [x, -4.45, 0.45]], height=0.88,
            post_spacing=0.65, baluster_gap=0.11)
for side, x in (("left", -1.50), ("right", 1.50)):
    perform("add_railing", object_id=f"porch_rail_{side}",
            path=[[x, -4.42, 0.45], [x, -3.22, 0.45]], height=0.88,
            post_spacing=0.75, baluster_gap=0.11)

# Doors and front-facing window assemblies.
box("front_door", [1.10, 0.10, 2.17], [0.0, -3.13, 1.535])
for z in (0.78, 1.54, 2.29):
    box(f"door_panel_{z}", [0.82, 0.045, 0.045], [0.0, -3.195, z])
primitive("door_handle", "sphere", [0.09, 0.09, 0.09], [0.39, -3.225, 1.53])


def front_window(prefix: str, x: float, width: float = 1.25):
    z = wall_base + 0.85 + 0.625
    box(f"{prefix}_glass", [width - 0.18, 0.055, 1.08], [x, -3.13, z])
    for dx in (-(width / 2), width / 2):
        box(f"{prefix}_frame_v_{dx}", [0.10, 0.16, 1.37], [x + dx, -3.15, z])
    for dz in (-0.625, 0.625):
        box(f"{prefix}_frame_h_{dz}", [width + 0.10, 0.16, 0.10], [x, -3.15, z + dz])
    box(f"{prefix}_mullion", [0.07, 0.17, 1.24], [x, -3.16, z])
    box(f"{prefix}_sill", [width + 0.22, 0.28, 0.10], [x, -3.20, z - 0.70])


front_window("front_window_left", -2.65)
front_window("front_window_right", 2.65)

# Side glazing (visible from the hero camera).
for y in (-1.35, 1.35):
    z = wall_base + 0.85 + 0.625
    box(f"left_window_{y}_glass", [0.055, 1.17, 1.08], [-4.13, y, z])
    for dy in (-0.675, 0.675):
        box(f"left_window_{y}_frame_v_{dy}", [0.16, 0.10, 1.37], [-4.15, y + dy, z])
    for dz in (-0.625, 0.625):
        box(f"left_window_{y}_frame_h_{dz}", [0.16, 1.45, 0.10], [-4.15, y, z + dz])
    box(f"left_window_{y}_mullion", [0.17, 0.07, 1.24], [-4.16, y, z])
    box(f"left_window_{y}_sill", [0.28, 1.55, 0.10], [-4.20, y, z - 0.70])

# One wide window on the right elevation.
z = wall_base + 0.8 + 0.675
box("right_window_glass", [0.055, 1.62, 1.18], [4.13, 0.0, z])
for y in (-0.90, 0.90):
    box(f"right_window_frame_v_{y}", [0.16, 0.10, 1.47], [4.15, y, z])
for dz in (-0.675, 0.675):
    box(f"right_window_frame_h_{dz}", [0.16, 1.90, 0.10], [4.15, 0.0, z + dz])
box("right_window_mullion", [0.17, 0.07, 1.34], [4.16, 0.0, z])
box("right_window_sill", [0.28, 2.00, 0.10], [4.20, 0.0, z - 0.75])

# Rear glazing keeps the exported model complete from every viewing angle.
for i, x in enumerate((-2.0, 2.0)):
    z = wall_base + 0.8 + 0.65
    box(f"back_window_{i}_glass", [1.42, 0.055, 1.12], [x, 3.13, z])
    for dx in (-0.8, 0.8):
        box(f"back_window_{i}_frame_v_{dx}", [0.10, 0.16, 1.42], [x + dx, 3.15, z])
    for dz in (-0.65, 0.65):
        box(f"back_window_{i}_frame_h_{dz}", [1.70, 0.16, 0.10], [x, 3.15, z + dz])
    box(f"back_window_{i}_mullion", [0.07, 0.17, 1.30], [x, 3.16, z])
    box(f"back_window_{i}_sill", [1.82, 0.28, 0.10], [x, 3.20, z - 0.72])

# Walkway, planters, shrubs and a small tree make the asset read as a finished home.
for i, y in enumerate((-5.85, -5.35, -4.85)):
    box(f"paver_{i}", [1.45, 0.38, 0.08], [0.0, y, 0.04])
for i, (x, y, scale) in enumerate(((-3.35, -3.75, 0.75), (3.35, -3.75, 0.78),
                                    (-3.45, 2.3, 0.9), (3.25, 2.35, 0.85))):
    primitive(f"shrub_{i}", "sphere", [scale * 1.35, scale, scale * 1.05],
              [x, y, scale * 0.48])
primitive("tree_trunk", "cylinder", [0.36, 0.36, 2.25], [-5.15, 2.0, 1.125])
for i, (x, y, z, s) in enumerate(((-5.15, 2.0, 2.65, 1.8), (-5.65, 2.0, 2.5, 1.35),
                                  (-4.7, 2.1, 2.55, 1.45), (-5.1, 2.0, 3.35, 1.35))):
    primitive(f"tree_crown_{i}", "sphere", [s, s * 0.85, s], [x, y, z])

# Materials are intentionally restrained and readable from a distance.
materials = {
    "grass": ((0.18, 0.42, 0.11), 0.88, 0.0),
    "foundation": ((0.24, 0.27, 0.30), 0.76, 0.0),
    "wall": ((0.82, 0.76, 0.64), 0.82, 0.0),
    "roof": ((0.055, 0.12, 0.18), 0.42, 0.05),
    "trim": ((0.92, 0.91, 0.85), 0.52, 0.0),
    "wood": ((0.43, 0.19, 0.075), 0.58, 0.0),
    "door": ((0.06, 0.30, 0.30), 0.35, 0.0),
    "glass": ((0.07, 0.32, 0.42), 0.16, 0.12),
    "metal": ((0.16, 0.17, 0.18), 0.25, 0.72),
    "brick": ((0.45, 0.13, 0.07), 0.73, 0.0),
    "leaf": ((0.12, 0.34, 0.065), 0.90, 0.0),
    "stone": ((0.46, 0.45, 0.41), 0.86, 0.0),
}
for name, (color, roughness, metallic) in materials.items():
    engine.create_material(name, color)
    engine.set_pbr(name, roughness=roughness, metallic=metallic)

for name in engine.list_objects():
    material = "trim"
    if name == "lawn": material = "grass"
    elif name == "foundation": material = "foundation"
    elif name.startswith("wall_"): material = "wall"
    elif "slope" in name: material = "roof"
    elif name.startswith("chimney_shaft"): material = "brick"
    elif name.startswith("chimney_flue") or name == "door_handle": material = "metal"
    elif name.startswith("chimney_"): material = "trim"
    elif name == "porch" or "tread" in name or name.startswith("door_panel"): material = "wood"
    elif "stringer" in name: material = "foundation"
    elif name == "front_door": material = "door"
    elif "glass" in name: material = "glass"
    elif name.startswith("paver_"): material = "stone"
    elif name.startswith("shrub_") or name.startswith("tree_crown_"): material = "leaf"
    elif name == "tree_trunk": material = "wood"
    engine.assign_material(name, material)

# Small bevels prevent razor-sharp CG edges while preserving architectural lines.
for name in engine.list_objects():
    if name == "lawn" or "glass" in name or "slope" in name:
        continue
    width = 0.012
    if name.startswith("shrub_") or name.startswith("tree_") or "flue" in name:
        continue
    if name.startswith("paver_") or name == "foundation":
        width = 0.025
    try:
        engine.bevel_edges(name, width=width, segments=2)
    except Exception:
        pass

artifacts = ROOT / "artifacts"
artifacts.mkdir(exist_ok=True)
blend_path = artifacts / "house.blend"
render_path = artifacts / "house.png"
glb_path = artifacts / "house.glb"

# Raw execution is the documented escape hatch for scene-only concerns (camera, lights,
# render settings and Blender's native working-file save), not construction geometry.
engine.execute(
    """
bpy = __import__('bpy')
from mathutils import Vector

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 900
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False
scene.render.filepath = str(render_path)
scene.render.image_settings.color_mode = 'RGBA'

world = scene.world or bpy.data.worlds.new('World')
scene.world = world
world.color = (0.035, 0.045, 0.06)
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
bg.inputs['Color'].default_value = (0.035, 0.055, 0.085, 1.0)
bg.inputs['Strength'].default_value = 0.35

def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

camera_data = bpy.data.cameras.new('HeroCamera')
camera = bpy.data.objects.new('HeroCamera', camera_data)
scene.collection.objects.link(camera)
camera.location = (10.8, -13.2, 8.6)
camera_data.lens = 53
point_at(camera, (0.0, -0.25, 2.15))
scene.camera = camera

sun_data = bpy.data.lights.new('Sun', type='SUN')
sun_data.energy = 2.2
sun_data.angle = math.radians(18)
sun = bpy.data.objects.new('Sun', sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(28), math.radians(-24), math.radians(-38))

area_data = bpy.data.lights.new('Softbox', type='AREA')
area_data.energy = 1150
area_data.shape = 'DISK'
area_data.size = 6.0
area = bpy.data.objects.new('Softbox', area_data)
scene.collection.objects.link(area)
area.location = (-5.0, -7.0, 9.0)
point_at(area, (0.0, 0.0, 2.0))

fill_data = bpy.data.lights.new('Fill', type='AREA')
fill_data.energy = 650
fill_data.size = 5.0
fill = bpy.data.objects.new('Fill', fill_data)
scene.collection.objects.link(fill)
fill.location = (6.0, 4.0, 5.5)
point_at(fill, (0.0, 0.0, 2.0))

# Make the panes read as glass while keeping the GLB material portable.
glass = bpy.data.materials.get('glass')
if glass and glass.node_tree:
    bsdf = next((n for n in glass.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for socket in bsdf.inputs:
            if socket.name in {'Transmission Weight', 'Transmission'}:
                socket.default_value = 0.35
            elif socket.name == 'IOR':
                socket.default_value = 1.45

bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)
""",
    {"blend_path": blend_path, "render_path": render_path, "math": math},
)

engine.export_model(engine.list_objects(), str(glb_path), y_up=True, apply_modifiers=True)
print(f"Created {len(engine.list_objects())} mesh objects")
print(blend_path)
print(glb_path)
print(render_path)
