# Blender Import Repair — assumptions

All choices preserve the existing public import contract; reversal costs are local unless noted.

- **A-105:** Link loaded hierarchy into the active scene before evaluating world transforms. Reversal would reintroduce lost placement.
- **A-106:** Flatten bakes exact world placement into vertices. Reversal is the existing Flatten toggle.
- **A-107:** Shared mesh data becomes single-user before distinct transform baking. Reversal would require a transform-aware instancing representation.
- **A-108:** Native files append to the current scene. Reversal requires a separately designed replacement flow.
- **A-109:** This repair remains mesh-only. Expanding types requires engine/viewer contracts.
- **A-110:** Imported datablocks remain local and editable. Linked-library mode would be a separate option.
- **A-111:** Existing scene geometry is preserved. Reversal would contradict append behavior.
- **A-112:** Flattened objects end with identity transforms after one bake. Reversal is low cost in the conversion loop.
- **A-113:** Unflattened mesh objects retain source world placement after skipped parents are detached. Reversal is local.
- **A-114:** Axis and unit conversions apply after source hierarchy evaluation. Reversal is local but would change placement.
- **A-115:** Mesh copies preserve materials and attributes. Reversal is unnecessary data loss.
- **A-116:** Modifier behavior is unchanged in this focused repair. Applying modifiers is a separate import-policy feature.
- **A-117:** Skipped non-mesh objects continue producing warnings. Reversal is presentation-only.
- **A-118:** Import remains atomic. Partial recovery would require new UX and transaction semantics.
- **A-119:** Browser upload headers remain unchanged. Reversal is a coordinated frontend/API change.
- **A-120:** Pause, progress, and completion behavior remain unchanged. Reversal is UI/workflow scope.
- **A-121:** Blender mutation remains on the owner thread. Reversal is unsafe for `bpy` context.
- **A-122:** End-to-end proof covers uploaded bytes, job completion, authoritative geometry, and viewer delivery. Reversal only weakens evidence.
- **A-123:** Every checked-in `.blend` asset receives a post-fix smoke import. Reversal only weakens evidence.
