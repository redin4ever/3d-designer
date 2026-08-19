# Part textures implementation plan

The feature is split into six independently testable units. Existing shared seams—engine
protocols, operation registries, live-server routes, mesh payloads, renderer wiring, and
the inspector shell—remain main-agent integration work after their supporting units are
green.

1. Build the texture-domain library and managed import policy.
2. Add a Blender adapter for PBR image nodes and portable exports.
3. Add replayable agent operations for create, update, list, and multi-object apply.
4. Add an allowlisted local texture asset resolver.
5. Add browser-side texture loading and UV sampling without weakening selection overlays.
6. Add the selected-part texture inspector and multi-selection feedback.

Each unit starts with a failing contract test, receives its implementation in a separate
commit, and is then connected through the existing shared seams in one integration pass.
