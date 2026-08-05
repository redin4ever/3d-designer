"""``scene`` — the operation log and the geometry it generates (ADR-002, ADR-006).

The log is the source of truth; geometry is generated from it, never the reverse. That is
what makes undo a pointer move rather than a snapshot, and what keeps constraints live —
move the stair, and the railing constrained to its outer edge follows.

``Scene`` is assembled from five responsibility mixins, one per file
(``.claude/rules/modularity.md``'s "distinct decision" split):

- ``document.py``    — ``apply``/``replay``: turning the log into geometry.
- ``history.py``     — ``undo``/``redo``/``rollback_to``/``checkpoint``: moving the pointer.
- ``cache.py``       — ``snapshot_of``/``invalidate_cache``: reading geometry cheaply.
- ``events.py``      — ``subscribe``/``_emit``: what the live view subscribes to.
- ``persistence.py`` — ``save``/``load``: round-tripping the document to disk.

This file also assembles ``Scene`` itself out of those five mixins. A class needs a
constructor, and there is nowhere else for one to live without inventing an unrequested
sixth file — every behaviour still lives entirely in the five files above; what is here is
composition and field initialisation only.

See ``README.md`` for the full public interface and its invariants, ``CLAUDE.md`` for
current status and local conventions. Every method not yet implemented raises
``NotImplementedError("scene.<name>: not implemented")`` (Rule 4 — tests come first); the
signatures below and each mixin's docstrings are the contract and do not move.

``scene`` never imports ``src/viewer/``. The dependency arrow points from the web layer
into this module and never back (see ``contracts.SceneChangeEvent``'s own docstring, and
``events_test.py::test_scene_source_never_imports_the_viewer``, which checks this
statically rather than by convention alone).
"""

from __future__ import annotations

from contracts import EngineProtocol, HandlerRegistry, MeshSnapshot, SceneDocument

from .cache import CacheMixin
from .document import DocumentMixin
from .events import EventsMixin, Listener
from .history import HistoryMixin
from .persistence import PersistenceMixin

__all__ = ["Scene"]


class Scene(DocumentMixin, HistoryMixin, CacheMixin, EventsMixin, PersistenceMixin):
    """Owns one operation log, its per-object geometry cache, and its change listeners.

    See the module docstring for how behaviour is split across files, and ``README.md``
    for the full contract each method must satisfy once implemented.
    """

    def __init__(
        self, engine: EngineProtocol, handlers: HandlerRegistry, *, scene_id: str = ""
    ) -> None:
        self._engine = engine
        self._handlers: HandlerRegistry = dict(handlers)
        self._document = SceneDocument(scene_id=scene_id, engine_backend=engine.backend_name)
        self._cache: dict[str, MeshSnapshot] = {}
        self._listeners: list[Listener] = []

    @property
    def document(self) -> SceneDocument:
        """The live, mutable source of truth — not a copy. ``scene`` is the only module
        that mutates it (``scene_doc.py``'s own docstring); everything else, including
        this module's own tests setting up a write lease directly, reads or writes
        through this property rather than through a private field."""
        return self._document
