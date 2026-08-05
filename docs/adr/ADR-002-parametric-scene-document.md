# ADR-002 — The parametric scene document is the source of truth

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 6.1, 3.4

## Decision

A model is stored as a **parametric document**: an ordered list of typed operations with their
parameters and constraints. Mesh geometry is *generated* from it. glTF is an export product, not
storage. The `.blend` file is a cache, not the record.

## Context

Gate A 1.3 named "still looks like glued boxes" as the deal-breaker, and Gate A 6.1 chose the
parametric option. The dominant complaint about AI-generated 3D is that the output is frozen:
"there are no loops, I would have to sculpt it like clay." A mesh cannot be re-edited by an agent
in any meaningful way — a railing becomes 47 anonymous triangle soups and "move the balusters
closer" means rebuilding.

Gate A 3.4 chose constraint-based placement. A constraint is only re-checkable if it is *stored*.
That requires this document.

## Consequences

- Every operation must be **replayable and deterministic**. Same document in, same geometry out.
  This is what makes undo (ADR-006) a pointer move rather than a snapshot.
- Constraints stay live: move the stair, and the railing that was constrained to its outer edge
  follows. This is the capability that distinguishes the tool from a mesh generator.
- The document is the diff surface. Gate A 4.1's "what changed" response and the live view's
  incremental updates both read from it rather than from mesh state.
- **Cost:** two representations to keep in sync, and a rebuild step whose cost grows with document
  length. Mitigated by caching evaluated geometry per operation and only re-evaluating downstream
  of a change.
- Any agent action that cannot be expressed as a typed operation (see ADR-009's raw escape hatch)
  breaks the parametric chain and must be recorded as an opaque mesh edit that blocks re-evaluation
  upstream of it. This is a real and deliberate hole; it is documented, not hidden.

## Superseded by

Nothing.
