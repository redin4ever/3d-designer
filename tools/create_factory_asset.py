"""Build a finished industrial factory artifact with forge3d and Blender."""

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
            op_id=f"factory-{counter:03d}-{operation_kind}",
            kind=operation_kind,
            params=params,
        ),
    )
    if not result.ok:
        raise RuntimeError(f"{operation_kind} failed: {result.error_detail}")
    return result


def primitive(name: str, kind: str, size, at, rotation=None):
    transform = {"translation": at}
    if rotation is not None:
        transform["rotation"] = rotation
    return perform(
        "add_primitive", object_id=name, kind=kind, size=size, transform=transform
    ).produced_objects[0]


def box(name: str, size, at, rotation=None):
    return primitive(name, "cube", size, at, rotation)


# Site and main industrial shell.
box("factory_lot", [24.0, 20.0, 0.20], [0.0, 0.0, -0.10])
box("loading_apron", [18.5, 5.4, 0.10], [0.0, -7.4, 0.01])
perform("add_floor", object_id="factory_foundation", width=14.5, depth=10.5,
        thickness=0.35, origin=[0.0, 0.0, 0.175])

wall_base = 0.35
wall_top = 5.35
wall_height = wall_top - wall_base
perform("add_wall", object_id="wall_front", start=[-7, -5, wall_base], end=[7, -5, wall_base],
        height=wall_height, thickness=0.24)
perform("add_wall", object_id="wall_back", start=[7, 5, wall_base], end=[-7, 5, wall_base],
        height=wall_height, thickness=0.24)
perform("add_wall", object_id="wall_left", start=[-7, 5, wall_base], end=[-7, -5, wall_base],
        height=wall_height, thickness=0.24)
perform("add_wall", object_id="wall_right", start=[7, -5, wall_base], end=[7, 5, wall_base],
        height=wall_height, thickness=0.24)

# Loading bays, personnel access, and high office windows.
for wall, position, width, height, sill in (
    ("wall_front", 3.9, 3.4, 3.75, 0.0),
    ("wall_front", 8.7, 3.0, 3.45, 0.0),
    ("wall_front", 12.6, 1.05, 2.25, 0.0),
    ("wall_left", 8.5, 1.05, 2.25, 0.0),
    ("wall_right", 2.0, 1.55, 1.25, 2.25),
    ("wall_right", 5.0, 1.55, 1.25, 2.25),
    ("wall_right", 8.0, 1.55, 1.25, 2.25),
    ("wall_back", 3.0, 1.7, 1.25, 2.15),
    ("wall_back", 7.0, 1.7, 1.25, 2.15),
    ("wall_back", 11.0, 1.7, 1.25, 2.15),
):
    perform("add_opening", object_id=f"opening_{wall}_{position}", wall_id=wall,
            position=position, width=width, height=height, sill_height=sill)

roof_pitch = 18.0
perform(
    "add_gable_roof", object_id="factory_roof", origin=[0, 0, wall_top], width=14.0,
    depth=10.0, pitch_degrees=roof_pitch, thickness=0.20, overhang=0.50,
    trim_width=0.20, trim_depth=0.24, ridge_axis="y",
)
ridge_z = wall_top + math.tan(math.radians(roof_pitch)) * 7.0
for label, y0 in (("front", -5.0), ("back", 5.0)):
    y_a, y_b = y0 - 0.12, y0 + 0.12
    verts = [
        Vec3(-7, y_a, wall_top), Vec3(7, y_a, wall_top), Vec3(0, y_a, ridge_z),
        Vec3(-7, y_b, wall_top), Vec3(7, y_b, wall_top), Vec3(0, y_b, ridge_z),
    ]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    engine.create_mesh(f"wall_gable_{label}", verts, faces)

# Corrugated-panel ribs are derived from the cut wall meshes, so door and window
# openings split the strips instead of being covered by them.
for name, wall, toward in (
    ("front_ribs", "wall_front", [0, -10, 2.5]),
    ("back_ribs", "wall_back", [0, 10, 2.5]),
    ("left_ribs", "wall_left", [-12, 0, 2.5]),
    ("right_ribs", "wall_right", [12, 0, 2.5]),
):
    perform("add_facade_ribs", object_id=name, wall_id=wall, toward=toward,
            spacing=2.0, width=0.08, depth=0.10, edge_margin=0.40,
            opening_clearance=0.05, min_segment=0.10)

# Roller shutters and safety-striped dock equipment.
for name, x, width, height in (("loading_door_a", -3.1, 3.30, 3.66),
                                ("loading_door_b", 1.7, 2.90, 3.36)):
    box(name, [width, 0.10, height], [x, -5.15, wall_base + height / 2])
    for j in range(1, 8):
        z = wall_base + height * j / 8
        box(f"{name}_slat_{j}", [width - 0.12, 0.045, 0.035], [x, -5.215, z])
    for dx in (-width / 2 - 0.08, width / 2 + 0.08):
        box(f"{name}_guide_{dx}", [0.12, 0.16, height + 0.20], [x + dx, -5.18, wall_base + height / 2])

box("personnel_door", [0.98, 0.10, 2.17], [5.60, -5.15, 1.435])
box("door_kickplate", [0.78, 0.045, 0.30], [5.60, -5.215, 0.57])
primitive("door_handle", "sphere", [0.085, 0.085, 0.085], [5.94, -5.23, 1.42])
box("door_canopy", [1.55, 0.75, 0.12], [5.60, -5.40, 2.78])

box("loading_dock", [4.6, 1.25, 0.65], [-3.1, -5.73, 0.325])
for x in (-4.55, -1.65):
    box(f"dock_bumper_{x}", [0.28, 0.18, 0.55], [x, -6.38, 0.62])
for i, x in enumerate((-5.05, -4.65, -1.55, -1.15, 0.15, 3.25, 4.95, 6.25)):
    primitive(f"bollard_{i}", "cylinder", [0.16, 0.16, 1.15], [x, -5.95, 0.575])

# Glazed office strip on the right elevation and matching rear windows.
for i, y in enumerate((-3.0, 0.0, 3.0)):
    z = wall_base + 2.25 + 0.625
    box(f"office_window_{i}_glass", [0.055, 1.35, 1.08], [7.14, y, z])
    for dy in (-0.78, 0.78):
        box(f"office_window_{i}_frame_v_{dy}", [0.17, 0.10, 1.40], [7.16, y + dy, z])
    for dz in (-0.625, 0.625):
        box(f"office_window_{i}_frame_h_{dz}", [0.17, 1.65, 0.10], [7.16, y, z + dz])
    box(f"office_window_{i}_mullion", [0.18, 0.07, 1.26], [7.17, y, z])
for i, x in enumerate((-4.0, 0.0, 4.0)):
    z = wall_base + 2.15 + 0.625
    box(f"rear_window_{i}_glass", [1.50, 0.055, 1.08], [x, 5.14, z])
    for dx in (-0.85, 0.85):
        box(f"rear_window_{i}_frame_v_{dx}", [0.10, 0.17, 1.40], [x + dx, 5.16, z])
    for dz in (-0.625, 0.625):
        box(f"rear_window_{i}_frame_h_{dz}", [1.80, 0.17, 0.10], [x, 5.16, z + dz])

# Roof skylights derive both their plane and their rotation from each roof panel.
for side, roof_id in (("left", "factory_roof_slope_neg"),
                      ("right", "factory_roof_slope_pos")):
    for i, horizontal_fraction in enumerate((0.22, 0.50, 0.78)):
        perform("add_roof_window", object_id=f"skylight_{side}_{i}", roof_id=roof_id,
                width=1.15, height=2.0, frame_width=0.10, depth=0.10,
                horizontal_fraction=horizontal_fraction, vertical_fraction=0.50)

# Raised exportable mesh text, horizontally centered on the selected exterior wall face.
perform("add_wall_sign", object_id="factory_sign", wall_id="wall_front",
        text="FORGE WORKS", toward=[0, -12, 4], center_height=4.65,
        height=0.65, depth=0.08, edge_margin=0.35)

# Exhaust stacks, rooftop vents, tanks and connecting pipework.
for i, (x, y) in enumerate(((-4.5, 1.5), (-3.2, 2.2))):
    base_z = wall_top + math.tan(math.radians(roof_pitch)) * (7.0 - abs(x))
    primitive(f"exhaust_stack_{i}", "cylinder", [0.62, 0.62, 3.2], [x, y, base_z + 1.55])
    primitive(f"exhaust_cap_{i}", "cone", [0.86, 0.86, 0.45], [x, y, base_z + 3.32])
for i, y in enumerate((-3.3, 0.0, 3.3)):
    primitive(f"roof_vent_{i}", "cylinder", [0.55, 0.55, 0.75], [1.1, y, ridge_z + 0.05])
    primitive(f"roof_vent_cap_{i}", "cone", [0.82, 0.82, 0.30], [1.1, y, ridge_z + 0.55])

for i, y in enumerate((-1.7, 1.7)):
    primitive(f"storage_tank_{i}", "cylinder", [2.2, 2.2, 3.7], [9.2, y, 1.85])
    primitive(f"tank_cap_{i}", "sphere", [2.05, 2.05, 0.65], [9.2, y, 3.68])
    for j, z in enumerate((0.55, 1.85, 3.15)):
        primitive(f"tank_band_{i}_{j}", "cylinder", [2.30, 2.30, 0.08], [9.2, y, z])
box("tank_pipe_horizontal", [0.22, 3.4, 0.22], [8.0, 0.0, 1.1])
primitive("tank_pipe_vertical", "cylinder", [0.24, 0.24, 2.5], [6.6, 0.0, 2.15])

# Yard markings, pallets and crates supply useful scene scale.
for i, x in enumerate((-5.5, -2.8, -0.1, 2.6)):
    box(f"parking_line_{i}", [0.09, 4.4, 0.018], [x, -7.55, 0.075])
for i, (x, y) in enumerate(((-6.0, 6.0), (-4.5, 6.1), (5.4, 6.2))):
    box(f"pallet_{i}", [1.25, 1.0, 0.14], [x, y, 0.12])
    box(f"crate_{i}", [1.05, 0.82, 0.92], [x, y, 0.65])

# Industrial material palette: cool cladding, dark steel, orange safety accents.
materials = {
    "asphalt": ((0.055, 0.065, 0.075), 0.93, 0.0),
    "concrete": ((0.38, 0.40, 0.41), 0.86, 0.0),
    "wall": ((0.48, 0.56, 0.60), 0.72, 0.05),
    "roof": ((0.075, 0.12, 0.15), 0.38, 0.42),
    "steel": ((0.13, 0.16, 0.18), 0.30, 0.72),
    "accent": ((0.88, 0.25, 0.035), 0.42, 0.18),
    "door": ((0.18, 0.27, 0.31), 0.48, 0.38),
    "glass": ((0.04, 0.30, 0.39), 0.14, 0.15),
    "aluminum": ((0.48, 0.52, 0.55), 0.22, 0.82),
    "yellow": ((0.95, 0.65, 0.035), 0.45, 0.05),
    "rubber": ((0.025, 0.025, 0.025), 0.65, 0.0),
    "wood": ((0.45, 0.23, 0.08), 0.72, 0.0),
}
for name, (color, roughness, metallic) in materials.items():
    engine.create_material(name, color)
    engine.set_pbr(name, roughness=roughness, metallic=metallic)

for name in engine.list_objects():
    material = "steel"
    if name == "factory_lot": material = "asphalt"
    elif name in {"loading_apron", "factory_foundation", "loading_dock"}: material = "concrete"
    elif name.startswith("wall_"): material = "wall"
    elif "slope" in name: material = "roof"
    elif "skylight" in name or "glass" in name: material = "glass"
    elif name.startswith("loading_door"): material = "door" if "slat" not in name else "accent"
    elif name in {"personnel_door", "door_kickplate"}: material = "accent"
    elif name == "factory_sign": material = "accent"
    elif name.startswith("bollard_") or name.startswith("parking_line_"): material = "yellow"
    elif name.startswith("dock_bumper_"): material = "rubber"
    elif name.startswith("storage_tank_") or name.startswith("tank_cap_"): material = "aluminum"
    elif name.startswith("tank_band_"): material = "accent"
    elif name.startswith("pallet_") or name.startswith("crate_"): material = "wood"
    elif "trim" in name or "fascia" in name or "ridge" in name: material = "accent"
    engine.assign_material(name, material)

for name in engine.list_objects():
    if name == "factory_lot" or "glass" in name or "slope" in name or name.startswith("parking_line_"):
        continue
    if name.startswith(("rib_", "front_rib", "back_rib", "left_rib", "right_rib")):
        continue
    try:
        engine.bevel_edges(name, width=0.018, segments=2)
    except Exception:
        pass

artifacts = ROOT / "artifacts"
artifacts.mkdir(exist_ok=True)
blend_path = artifacts / "factory.blend"
render_path = artifacts / "factory.png"
glb_path = artifacts / "factory.glb"

engine.execute(
    """
bpy = __import__('bpy')
from mathutils import Vector

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1000
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(render_path)

world = scene.world or bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
bg.inputs['Color'].default_value = (0.025, 0.04, 0.055, 1.0)
bg.inputs['Strength'].default_value = 0.28

def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

camera_data = bpy.data.cameras.new('FactoryCamera')
camera = bpy.data.objects.new('FactoryCamera', camera_data)
scene.collection.objects.link(camera)
camera.location = (21.5, -26.0, 16.8)
camera_data.lens = 56
point_at(camera, (0.8, -0.1, 3.55))
scene.camera = camera

sun_data = bpy.data.lights.new('Sun', type='SUN')
sun_data.energy = 2.4
sun_data.angle = math.radians(14)
sun = bpy.data.objects.new('Sun', sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(32), math.radians(-18), math.radians(-42))

key_data = bpy.data.lights.new('IndustrialKey', type='AREA')
key_data.energy = 1600
key_data.shape = 'DISK'
key_data.size = 8.0
key = bpy.data.objects.new('IndustrialKey', key_data)
scene.collection.objects.link(key)
key.location = (-8.0, -10.0, 15.0)
point_at(key, (0.0, 0.0, 3.0))

fill_data = bpy.data.lights.new('IndustrialFill', type='AREA')
fill_data.energy = 900
fill_data.size = 7.0
fill = bpy.data.objects.new('IndustrialFill', fill_data)
scene.collection.objects.link(fill)
fill.location = (12.0, 7.0, 10.0)
point_at(fill, (2.0, 0.0, 3.0))

glass = bpy.data.materials.get('glass')
if glass and glass.node_tree:
    bsdf = next((n for n in glass.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for socket in bsdf.inputs:
            if socket.name in {'Transmission Weight', 'Transmission'}:
                socket.default_value = 0.30
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
