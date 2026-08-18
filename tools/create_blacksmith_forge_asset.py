"""Build a richly detailed, old-world blacksmith forge scene.

The scene is intentionally assembled through forge3d's real Blender path so the
result is useful both as a rendered reference and as an editable/exportable asset.
"""

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
object_materials: dict[str, str] = {}
pre_beveled: set[str] = set()


def perform(operation_kind: str, **params):
    global counter
    counter += 1
    result = app.handlers[operation_kind](
        engine,
        Operation(
            op_id=f"forge-{counter:04d}-{operation_kind}",
            kind=operation_kind,
            params=params,
        ),
    )
    if not result.ok:
        raise RuntimeError(f"{operation_kind} failed: {result.error_detail}")
    return result


def xform(at, axis=None, angle=0.0):
    return Transform(
        translation=Vec3(*at),
        rotation=Quat.from_axis_angle(Vec3(*axis), angle) if axis else Quat(),
    )


def primitive(name: str, kind: str, size, at, material: str, axis=None, angle=0.0):
    perform(
        "add_primitive",
        object_id=name,
        kind=kind,
        size=size,
        transform=xform(at, axis, angle),
    )
    object_materials[name] = material
    return name


def box(name: str, size, at, material: str, axis=None, angle=0.0):
    return primitive(name, "cube", size, at, material, axis, angle)


def cyl(name: str, diameter: float, depth: float, at, material: str, axis=None, angle=0.0):
    return primitive(name, "cylinder", [diameter, diameter, depth], at, material, axis, angle)


def sphere(name: str, size, at, material: str):
    return primitive(name, "sphere", size, at, material)


def cone(name: str, diameter: float, depth: float, at, material: str, axis=None, angle=0.0):
    return primitive(name, "cone", [diameter, diameter, depth], at, material, axis, angle)


def torus(name: str, diameter: float, tube: float, at, material: str):
    return primitive(name, "torus", [diameter, diameter, tube], at, material)


def chamfered_profile(width: float, height: float, chamfer: float, *, v_offset=0.0):
    """Counter-clockwise local [u, v] section with clipped corners."""
    half_width, half_height = width / 2.0, height / 2.0
    cut = min(chamfer, half_width * 0.45, half_height * 0.45)
    return [
        [-half_width + cut, v_offset - half_height],
        [half_width - cut, v_offset - half_height],
        [half_width, v_offset - half_height + cut],
        [half_width, v_offset + half_height - cut],
        [half_width - cut, v_offset + half_height],
        [-half_width + cut, v_offset + half_height],
        [-half_width, v_offset + half_height - cut],
        [-half_width, v_offset - half_height + cut],
    ]


def profiled(name: str, origin, axis: str, sections, material: str, bevel_width=0.012):
    perform("add_profiled_solid",
        object_id=name,
        origin=origin,
        axis=axis,
        sections=sections,
        bevel_width=bevel_width,
    )
    object_materials[name] = material
    pre_beveled.add(name)
    return name


# --- The room: hand-laid flagstones, soot-darkened masonry, and oak framing. ---
box("flagstone_floor", [12.5, 10.0, 0.22], [0, 0, -0.11], "stone_dark")
for row, y in enumerate(range(-4, 5, 2)):
    for col, x in enumerate(range(-5, 6, 2)):
        # Slightly varied courses keep the floor from looking like a single tile.
        w = 1.72 if (row + col) % 3 else 1.42
        h = 1.68 if (row * 2 + col) % 4 else 1.86
        box(f"flag_{row}_{col}", [w, h, 0.055], [x + (0.16 if row % 2 else 0), y, 0.025],
            "stone_warm", axis=[0, 0, 1], angle=(0.008 * ((row + col) % 3)))

# Back wall and side return, with visible mortar courses and heavy posts.
box("back_wall", [12.5, 0.32, 6.8], [0, 4.85, 3.4], "masonry")
box("left_wall", [0.32, 9.7, 6.8], [-6.1, 0.0, 3.4], "masonry")
for z in (0.65, 1.65, 2.65, 3.65, 4.65, 5.65):
    box(f"mortar_back_{z}", [12.1, 0.035, 0.045], [0, 4.67, z], "mortar")
for z in (0.65, 1.65, 2.65, 3.65, 4.65, 5.65):
    box(f"mortar_left_{z}", [0.035, 9.35, 0.045], [-5.92, 0, z], "mortar")
for i, x in enumerate((-5.65, -2.7, 0.3, 3.25, 5.55)):
    box(f"timber_post_{i}", [0.34, 0.46, 6.4], [x, 4.54, 3.35], "oak_dark")
for i, x in enumerate((-4.9, -1.75, 1.4, 4.55)):
    box(f"brick_pier_{i}", [0.66, 0.50, 5.65], [x, 4.49, 2.86], "brick")
    for j in range(5):
        box(f"brick_cap_{i}_{j}", [0.74, 0.54, 0.055], [x, 4.45, 0.6 + j * 1.05], "mortar")
box("top_beam", [12.5, 0.55, 0.42], [0, 4.45, 6.36], "oak_dark")
box("left_beam", [0.55, 9.6, 0.40], [-5.70, 0, 6.36], "oak_dark")
for i, x in enumerate((-4.3, -1.45, 1.4, 4.25)):
    box(f"ceiling_joist_{i}", [0.28, 10.0, 0.32], [x, 0, 6.38], "oak")
# The rafters are left open above the camera's sightline so the hood and chimney
# remain readable; a solid ceiling here would turn the upper third into a slab.

# --- Central masonry forge hearth and hood. ---
for row in range(3):
    for col in range(5):
        x = -3.95 + col * 0.62 + (0.31 if row % 2 else 0)
        box(f"hearth_brick_{row}_{col}", [0.58, 1.42, 0.43], [x, 2.48, 0.22 + row * 0.43], "brick")
box("hearth_slab", [3.45, 1.90, 0.18], [-2.55, 2.46, 1.55], "stone_light")
box("hearth_lip", [3.10, 0.25, 0.26], [-2.55, 1.58, 1.70], "iron")
box("fire_bowl", [2.18, 1.22, 0.26], [-2.55, 2.50, 1.76], "iron")
for x, y, s in ((-2.95, 2.42, 0.38), (-2.55, 2.62, 0.46), (-2.18, 2.40, 0.33), (-2.72, 2.82, 0.30), (-2.32, 2.77, 0.27)):
    sphere(f"coal_{x}_{y}", [s, s * 0.82, s * 0.68], [x, y, 1.99 + s * 0.18], "coal_hot")
    sphere(f"ember_{x}_{y}", [s * 0.55, s * 0.44, s * 0.38], [x + 0.03, y - 0.03, 2.16 + s * 0.18], "ember")
for i, x in enumerate((-3.26, -2.88, -2.50, -2.12, -1.76)):
    box(f"grate_bar_{i}", [0.10, 1.46, 0.10], [x, 2.48, 1.91], "iron")

profiled("forge_hood", [-2.55, 2.55, 2.92], "z", [
    {"offset": 0.0, "profile": chamfered_profile(3.65, 1.72, 0.10)},
    {"offset": 0.34, "profile": chamfered_profile(3.65, 1.72, 0.10)},
    {"offset": 1.02, "profile": chamfered_profile(2.35, 1.18, 0.08)},
    {"offset": 1.62, "profile": chamfered_profile(1.02, 0.74, 0.07)},
], "iron_dark", bevel_width=0.018)
box("hood_front_lintel", [3.66, 0.24, 0.18], [-2.55, 1.69, 2.98], "iron")
for x in (-4.0, -3.0, -2.1, -1.1):
    cyl(f"hood_rivet_{x}", 0.12, 0.08, [x, 1.54, 3.00], "iron_bright", axis=[1, 0, 0], angle=math.pi / 2)
for z, diameter in ((4.78, 1.50), (5.40, 1.22), (6.03, 0.96)):
    cyl(f"chimney_{z}", diameter, 0.58, [-2.55, 2.56, z], "iron_dark")
    torus(f"chimney_band_{z}", diameter + 0.12, 0.10, [-2.55, 2.56, z + 0.24], "iron_bright")
cone("chimney_cap", 1.46, 0.38, [-2.55, 2.56, 6.48], "iron_dark")

# Bellows, including the timber arms and leather folds, tucked beside the hearth.
profiled("bellows_body", [-4.55, 2.22, 1.55], "x", [
    {"offset": -0.72, "profile": chamfered_profile(0.50, 0.18, 0.05)},
    {"offset": -0.43, "profile": chamfered_profile(0.68, 0.56, 0.10)},
    {"offset": 0.43, "profile": chamfered_profile(0.68, 0.56, 0.10)},
    {"offset": 0.72, "profile": chamfered_profile(0.50, 0.18, 0.05)},
], "leather", bevel_width=0.008)
box("bellows_top", [1.60, 0.70, 0.12], [-4.55, 2.22, 1.88], "oak")
box("bellows_bottom", [1.60, 0.70, 0.12], [-4.55, 2.22, 1.22], "oak")
for i, x in enumerate((-5.05, -4.76, -4.47, -4.18)):
    box(f"bellows_fold_{i}", [0.075, 0.70, 0.58], [x, 2.22, 1.55], "leather_dark")
box("bellows_handle", [1.90, 0.15, 0.15], [-4.55, 1.55, 1.58], "oak", axis=[0, 1, 0], angle=math.radians(12))
box("bellows_nozzle", [0.22, 0.82, 0.22], [-3.63, 2.22, 1.55], "iron", axis=[0, 1, 0], angle=math.pi / 2)

# --- Anvil and stump in front of the hearth. ---
cyl("anvil_stump", 1.62, 1.52, [-0.05, 0.95, 0.76], "oak_dark")
for i, z in enumerate((0.18, 0.54, 0.90, 1.26)):
    torus(f"stump_ring_{i}", 1.66, 0.055, [-0.05, 0.95, z], "iron")
profiled("anvil_base", [-0.05, 0.95, 1.66], "x", [
    {"offset": -0.86, "profile": chamfered_profile(1.18, 0.28, 0.08)},
    {"offset": 0.66, "profile": chamfered_profile(1.18, 0.28, 0.08)},
], "iron_dark", bevel_width=0.018)
profiled("anvil_body", [-0.05, 0.95, 2.25], "x", [
    {"offset": -1.18, "profile": chamfered_profile(0.88, 0.30, 0.06, v_offset=0.42)},
    {"offset": -0.88, "profile": chamfered_profile(1.02, 0.40, 0.08, v_offset=0.36)},
    {"offset": -0.58, "profile": chamfered_profile(1.04, 0.62, 0.10, v_offset=0.22)},
    {"offset": -0.28, "profile": chamfered_profile(0.72, 0.94, 0.12, v_offset=-0.10)},
    {"offset": 0.08, "profile": chamfered_profile(0.64, 0.92, 0.12, v_offset=-0.12)},
    {"offset": 0.42, "profile": chamfered_profile(0.86, 0.74, 0.10, v_offset=0.04)},
    {"offset": 0.70, "profile": chamfered_profile(0.94, 0.54, 0.09, v_offset=0.26)},
    {"offset": 1.02, "profile": chamfered_profile(0.66, 0.36, 0.07, v_offset=0.36)},
    {"offset": 1.36, "profile": chamfered_profile(0.36, 0.22, 0.05, v_offset=0.42)},
    {"offset": 1.62, "profile": chamfered_profile(0.10, 0.10, 0.02, v_offset=0.43)},
], "iron_bright", bevel_width=0.0)
profiled("anvil_face", [-0.05, 0.95, 2.25], "x", [
    {"offset": -1.28, "profile": chamfered_profile(1.02, 0.13, 0.025, v_offset=0.625)},
    {"offset": 0.72, "profile": chamfered_profile(1.02, 0.13, 0.025, v_offset=0.625)},
], "steel_face", bevel_width=0.0)
box("anvil_step", [0.70, 0.98, 0.22], [-0.94, 0.95, 2.72], "steel_face")
box("anvil_tail", [0.34, 1.04, 0.34], [-1.05, 0.95, 2.67], "iron_bright")
box("anvil_hardy_hole", [0.20, 0.20, 0.035], [-0.78, 0.95, 2.94], "iron_dark")
cyl("anvil_pritchel_hole", 0.12, 0.035, [-0.48, 0.95, 2.94], "iron_dark")

# A partially worked red-hot bar lying on the anvil.
cyl("hot_bar", 0.16, 1.55, [0.12, 0.96, 3.10], "hot_steel", axis=[0, 1, 0], angle=math.radians(82))
for i in range(3):
    torus(f"hot_bar_heat_{i}", 0.20, 0.026, [0.12, 0.47 + i * 0.22, 3.10 + i * 0.05], "ember")

# --- Workbench and post vise on the right. ---
box("workbench_top", [3.50, 1.50, 0.24], [3.65, 1.18, 1.58], "oak")
box("workbench_front_apron", [3.34, 0.16, 0.62], [3.65, 0.48, 1.20], "oak_dark")
for x in (2.25, 5.05):
    box(f"bench_leg_{x}", [0.24, 0.26, 1.36], [x, 1.18, 0.82], "oak_dark")
    box(f"bench_foot_{x}", [0.72, 1.25, 0.18], [x, 1.18, 0.16], "oak_dark")
box("bench_shelf", [3.12, 1.16, 0.16], [3.65, 1.18, 0.48], "oak")
box("vise_body", [0.82, 0.82, 0.52], [3.12, 0.76, 2.02], "iron_dark")
box("vise_fixed_jaw", [0.18, 0.92, 0.48], [2.72, 0.76, 2.27], "steel_face")
box("vise_moving_jaw", [0.18, 0.92, 0.48], [3.52, 0.76, 2.27], "steel_face")
box("vise_grip", [1.28, 0.10, 0.10], [3.12, 0.36, 1.72], "iron_bright", axis=[1, 0, 0], angle=math.pi / 2)
cyl("vise_screw", 0.12, 0.92, [3.12, 0.76, 2.06], "iron", axis=[1, 0, 0], angle=math.pi / 2)
for i, (x, z) in enumerate(((2.45, 1.92), (4.85, 1.92), (2.45, 1.30), (4.85, 1.30))):
    cyl(f"bench_bolt_{i}", 0.11, 0.06, [x, 0.37, z], "iron_bright", axis=[1, 0, 0], angle=math.pi / 2)

# --- Tool wall, shelf, and a full spread of hand tools. ---
box("tool_rack", [5.15, 0.18, 2.10], [1.05, 4.25, 3.08], "oak_dark")
box("tool_shelf", [5.55, 0.62, 0.18], [1.05, 3.98, 1.92], "oak")
box("tool_shelf_lip", [5.55, 0.12, 0.22], [1.05, 3.66, 2.06], "oak_dark")
for x in (-1.15, 0.25, 1.65, 3.05):
    cyl(f"rack_hook_{x}", 0.07, 0.76, [x, 3.91, 3.15], "iron", axis=[1, 0, 0], angle=math.pi / 2)
    torus(f"rack_hook_ring_{x}", 0.20, 0.035, [x, 3.50, 3.15], "iron")

# Hammers: wooden handles and heavy iron heads, hung at deliberate intervals.
for i, (x, z, scale) in enumerate(((-0.85, 3.20, 1.0), (0.35, 3.95, 0.82), (1.65, 3.12, 0.72), (2.95, 3.90, 0.92))):
    cyl(f"hammer_handle_{i}", 0.13 * scale, 1.55 * scale, [x, 3.56, z - 0.63 * scale], "tool_handle", axis=[1, 0, 0], angle=math.radians(4))
    box(f"hammer_head_{i}", [0.82 * scale, 0.36 * scale, 0.42 * scale], [x, 3.56, z + 0.18 * scale], "tool_steel")
    cyl(f"hammer_peen_{i}", 0.24 * scale, 0.40 * scale, [x + 0.58 * scale, 3.56, z + 0.18 * scale], "tool_steel", axis=[0, 1, 0], angle=math.pi / 2)
    box(f"hammer_eye_{i}", [0.14 * scale, 0.40 * scale, 0.18 * scale], [x, 3.56, z + 0.18 * scale], "iron_dark")

# Tongs and long-handled tools on the lower rack.
for i, x in enumerate((-0.72, 0.10, 0.92, 1.74, 2.56)):
    cyl(f"tong_handle_{i}", 0.075, 1.70, [x, 3.64, 2.52], "tool_handle", axis=[1, 0, 0], angle=math.radians(-9 + i * 3))
    cyl(f"tong_arm_{i}", 0.09, 0.82, [x, 3.64, 3.45], "tool_steel", axis=[1, 0, 0], angle=math.radians(-9 + i * 3))
    sphere(f"tong_grip_{i}", [0.18, 0.18, 0.18], [x, 3.64, 1.68], "tool_handle")
for i, x in enumerate((3.75, 4.28, 4.81)):
    cyl(f"punch_{i}", 0.11, 1.22, [x, 3.72, 2.62], "tool_steel", axis=[1, 0, 0], angle=math.pi / 2)
    cone(f"punch_point_{i}", 0.18, 0.32, [x, 3.72, 3.34], "tool_steel")

# Small shelf objects: files, wire spools, chisels, and a square of billets.
for i, x in enumerate((2.35, 2.72, 3.09, 3.46)):
    cyl(f"file_{i}", 0.10, 0.94, [x, 3.78, 2.16], "tool_steel", axis=[1, 0, 0], angle=math.pi / 2)
    sphere(f"file_handle_{i}", [0.20, 0.20, 0.24], [x, 3.78, 2.73], "tool_handle")
for i in range(3):
    torus(f"wire_spool_{i}", 0.52, 0.10, [4.42 + i * 0.44, 3.78, 2.16], "iron_bright")
    cyl(f"wire_spool_core_{i}", 0.18, 0.30, [4.42 + i * 0.44, 3.78, 2.16], "wood", axis=[1, 0, 0], angle=math.pi / 2)

# --- Quench station and coal bins. ---
cyl("quench_barrel", 1.72, 1.74, [4.82, -1.75, 0.93], "barrel")
torus("barrel_top_hoop", 1.80, 0.08, [4.82, -1.75, 1.77], "iron")
torus("barrel_mid_hoop", 1.80, 0.07, [4.82, -1.75, 0.92], "iron")
torus("barrel_bottom_hoop", 1.80, 0.07, [4.82, -1.75, 0.15], "iron")
cyl("barrel_water", 1.52, 0.035, [4.82, -1.75, 1.76], "water")
for i, y in enumerate((-2.15, -1.75, -1.35)):
    cyl(f"quench_tongs_{i}", 0.08, 1.85, [4.42, y, 2.82], "tool_steel", axis=[1, 0, 0], angle=math.radians(18))
box("water_bucket", [0.72, 0.72, 0.86], [5.35, -0.45, 0.49], "iron_dark")
torus("bucket_handle", 0.74, 0.055, [5.35, -0.45, 0.98], "iron")
box("coal_bin", [2.18, 1.55, 0.82], [-4.68, -1.70, 0.43], "oak_dark")
box("coal_bin_front", [2.05, 0.10, 0.68], [-4.68, -2.48, 0.54], "oak")
for i, (x, y, s) in enumerate(((-5.3, -1.75, 0.36), (-4.95, -1.55, 0.40), (-4.55, -1.85, 0.32), (-4.15, -1.60, 0.35), (-4.80, -2.05, 0.30))):
    sphere(f"bin_coal_{i}", [s, s * 0.82, s * 0.64], [x, y, 0.98 + (i % 2) * 0.13], "coal")

# Wood pile, scrap rack, and loose stock give the floor believable clutter.
for i, x in enumerate((2.8, 3.3, 3.8, 4.3)):
    cyl(f"log_{i}", 0.36, 1.70, [x, -3.25, 0.35 + (i % 2) * 0.30], "wood", axis=[0, 1, 0], angle=math.pi / 2)
    cyl(f"log_end_{i}", 0.26, 0.02, [x, -3.25 - 0.86, 0.35 + (i % 2) * 0.30], "wood_end", axis=[0, 1, 0], angle=math.pi / 2)
box("scrap_rack", [1.25, 1.00, 1.55], [-1.55, -2.95, 0.78], "iron_dark")
for i, x in enumerate((-1.82, -1.52, -1.22)):
    cyl(f"scrap_bar_{i}", 0.10, 2.00, [x, -2.95, 1.72], "scrap_steel", axis=[0, 1, 0], angle=math.pi / 2)
for i, (x, y, z, a) in enumerate(((-1.9, -2.40, 0.18, 0.25), (-1.4, -2.25, 0.16, -0.35), (0.8, -2.30, 0.12, 0.62), (1.3, -2.85, 0.16, -0.46))):
    cyl(f"loose_scrap_{i}", 0.08, 1.30, [x, y, z], "scrap_steel", axis=[0, 1, 0], angle=a)

# Hanging lantern, wall sign, and a few functional small details.
box("lantern_body", [0.48, 0.48, 0.78], [4.95, 4.18, 4.78], "iron_dark")
box("lantern_glass", [0.30, 0.30, 0.50], [4.95, 3.92, 4.78], "lantern_glass")
cone("lantern_cap", 0.62, 0.22, [4.95, 4.18, 5.30], "iron")
torus("lantern_hook", 0.42, 0.035, [4.95, 4.18, 5.48], "iron")
box("shop_sign", [2.55, 0.12, 0.70], [4.20, 4.23, 5.84], "oak_dark")
box("shop_sign_inset", [2.20, 0.035, 0.42], [4.20, 4.15, 5.84], "brass")

# Bolts, nails, ash pieces, and hot sparks scattered around the active work area.
for i, (x, y, z) in enumerate(((-3.45, 1.32, 1.86), (-1.25, 1.40, 1.82), (-0.95, -0.10, 0.09), (1.85, 0.20, 0.10), (-3.80, -0.35, 0.10))):
    cyl(f"floor_nail_{i}", 0.06, 0.11, [x, y, z], "iron_bright", axis=[0, 1, 0], angle=math.pi / 2)
for i, (x, y, z, s) in enumerate(((-1.60, 2.08, 2.56, 0.08), (-1.25, 2.22, 2.74, 0.06), (-2.05, 2.10, 2.48, 0.055), (-3.42, 2.07, 2.34, 0.045))):
    sphere(f"spark_{i}", [s, s, s], [x, y, z], "ember")


# --- Materials and finish. ---
materials = {
    "stone_dark": ((0.14, 0.13, 0.12), 0.94, 0.0),
    "stone_warm": ((0.27, 0.24, 0.20), 0.88, 0.0),
    "stone_light": ((0.36, 0.33, 0.28), 0.78, 0.0),
    "masonry": ((0.22, 0.19, 0.17), 0.96, 0.0),
    "brick": ((0.31, 0.12, 0.065), 0.90, 0.0),
    "mortar": ((0.08, 0.07, 0.065), 1.0, 0.0),
    "oak": ((0.28, 0.105, 0.032), 0.78, 0.0),
    "oak_dark": ((0.12, 0.042, 0.018), 0.90, 0.0),
    "wood_shadow": ((0.055, 0.025, 0.012), 0.98, 0.0),
    "wood": ((0.39, 0.14, 0.035), 0.84, 0.0),
    "wood_end": ((0.23, 0.075, 0.020), 0.92, 0.0),
    "iron": ((0.055, 0.062, 0.060), 0.48, 0.82),
    "iron_dark": ((0.020, 0.024, 0.024), 0.60, 0.90),
    "iron_bright": ((0.22, 0.24, 0.23), 0.32, 0.92),
    "steel_face": ((0.31, 0.33, 0.31), 0.22, 0.94),
    "tool_steel": ((0.14, 0.15, 0.14), 0.36, 0.88),
    "scrap_steel": ((0.10, 0.11, 0.10), 0.52, 0.82),
    "tool_handle": ((0.43, 0.16, 0.045), 0.72, 0.0),
    "leather": ((0.16, 0.035, 0.014), 0.90, 0.0),
    "leather_dark": ((0.075, 0.015, 0.008), 0.95, 0.0),
    "barrel": ((0.20, 0.065, 0.022), 0.82, 0.0),
    "coal": ((0.012, 0.010, 0.009), 0.98, 0.0),
    "coal_hot": ((0.10, 0.010, 0.003), 0.46, 0.05),
    "hot_steel": ((0.72, 0.06, 0.008), 0.24, 0.72),
    "ember": ((0.95, 0.055, 0.004), 0.24, 0.05),
    "water": ((0.025, 0.14, 0.17), 0.12, 0.12),
    "lantern_glass": ((0.65, 0.22, 0.025), 0.18, 0.05),
    "brass": ((0.58, 0.25, 0.035), 0.28, 0.78),
}
for name, (color, roughness, metallic) in materials.items():
    engine.create_material(name, color)
    engine.set_pbr(name, roughness=roughness, metallic=metallic)
for name, material in object_materials.items():
    engine.assign_material(name, material)

for name in engine.list_objects():
    if name in pre_beveled:
        continue
    if name.startswith(("flag_", "mortar_", "brick_cap_", "spark_")):
        continue
    try:
        engine.bevel_edges(name, width=0.025 if "anvil" not in name else 0.018, segments=2)
    except Exception:
        pass


artifacts = ROOT / "artifacts"
artifacts.mkdir(exist_ok=True)
blend_path = artifacts / "blacksmith_forge.blend"
render_path = artifacts / "blacksmith_forge.png"
glb_path = artifacts / "blacksmith_forge.glb"

engine.execute(
    """
bpy = __import__('bpy')
from mathutils import Vector
import math

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1200
scene.render.resolution_y = 820
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(render_path)
scene.render.film_transparent = False
scene.view_settings.look = 'AgX - Medium High Contrast'

world = scene.world or bpy.data.worlds.new('ForgeWorld')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
bg.inputs['Color'].default_value = (0.012, 0.009, 0.007, 1.0)
bg.inputs['Strength'].default_value = 0.18

def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

camera_data = bpy.data.cameras.new('ForgeCamera')
camera = bpy.data.objects.new('ForgeCamera', camera_data)
scene.collection.objects.link(camera)
camera.location = (11.8, -15.8, 8.5)
camera_data.lens = 52
point_at(camera, (-0.25, 1.0, 2.55))
scene.camera = camera

def area(name, energy, size, location, color, target=(-1.0, 1.3, 2.2)):
    data = bpy.data.lights.new(name, type='AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    point_at(obj, target)
    return obj

area('FireGlow', 1250, 3.2, (-2.55, 1.65, 3.15), (1.0, 0.16, 0.025), (-1.0, 1.5, 1.2))
area('ForgeKey', 1050, 5.0, (-7.0, -5.5, 8.8), (1.0, 0.48, 0.20))
area('CoolWindow', 900, 5.5, (6.5, -1.0, 7.2), (0.20, 0.34, 0.46))
area('AnvilRim', 700, 2.5, (1.8, -3.5, 5.0), (1.0, 0.30, 0.08), (0, 1, 2.4))

sun_data = bpy.data.lights.new('MoonFill', type='SUN')
sun_data.energy = 0.38
sun_data.angle = math.radians(18)
sun = bpy.data.objects.new('MoonFill', sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(28), math.radians(-22), math.radians(-38))

for mat_name, color, strength in (
    ('ember', (1.0, 0.015, 0.001, 1.0), 12.0),
    ('coal_hot', (0.85, 0.006, 0.001, 1.0), 3.5),
    ('hot_steel', (1.0, 0.018, 0.001, 1.0), 5.0),
    ('lantern_glass', (1.0, 0.065, 0.004, 1.0), 3.0),
):
    mat = bpy.data.materials.get(mat_name)
    if mat and mat.node_tree:
        bsdf = next((node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if bsdf:
            for socket in bsdf.inputs:
                if socket.name in {'Emission Color', 'Emission'}:
                    socket.default_value = color
                elif socket.name == 'Emission Strength':
                    socket.default_value = strength

def apply_surface_variation(mat_name, scale, contrast, rough_min, rough_max, bump_strength):
    # Subtle object-space wear; material identity stays legible at scene distance.
    mat = bpy.data.materials.get(mat_name)
    if not mat or not mat.node_tree:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf:
        return
    base = tuple(bsdf.inputs['Base Color'].default_value[:3])
    texcoord = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 5.0
    noise.inputs['Roughness'].default_value = 0.72
    ramp = nodes.new('ShaderNodeValToRGB')
    dark = tuple(max(0.0, component * (1.0 - contrast)) for component in base)
    light = tuple(min(1.0, component * (1.0 + contrast * 0.55)) for component in base)
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    roughness = nodes.new('ShaderNodeMapRange')
    roughness.inputs['To Min'].default_value = rough_min
    roughness.inputs['To Max'].default_value = rough_max
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = bump_strength
    bump.inputs['Distance'].default_value = 0.035
    links.new(texcoord.outputs['Generated'], noise.inputs['Vector'])
    links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(noise.outputs['Fac'], roughness.inputs['Value'])
    links.new(roughness.outputs['Result'], bsdf.inputs['Roughness'])
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

for args in (
    ('masonry', 3.2, 0.34, 0.78, 0.98, 0.30),
    ('brick', 5.5, 0.30, 0.72, 0.96, 0.24),
    ('stone_warm', 4.2, 0.26, 0.70, 0.94, 0.22),
    ('oak', 3.6, 0.32, 0.58, 0.88, 0.18),
    ('oak_dark', 4.4, 0.28, 0.66, 0.92, 0.20),
    ('iron', 7.0, 0.18, 0.28, 0.62, 0.12),
    ('iron_dark', 8.5, 0.20, 0.34, 0.70, 0.15),
    ('iron_bright', 9.0, 0.16, 0.20, 0.48, 0.09),
    ('leather', 12.0, 0.30, 0.70, 0.96, 0.28),
):
    apply_surface_variation(*args)

# A very restrained atmospheric haze catches the warm light under the hood.
scene.world.color = (0.01, 0.008, 0.006)
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
