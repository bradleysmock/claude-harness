"""Per-gate log file writer with a path-containment guard.

FR-3 requires each gate's output to land in its own log file under a fixed
directory. The gate name becomes the filename, so it is untrusted input for path
construction: NFR-4 requires it to be validated as a safe single path component
(no separators, no ``..``) before the path is built. :class:`LogWriter` enforces
that both structurally (reject separators / traversal tokens up front) and by
asserting the resolved path stays within ``log_dir`` (defense in depth).
"""

from __future__ import annotations

from pathlib import Path

#: Tokens that must never appear in a gate name used as a filename component.
_FORBIDDEN = ("/", "\\", "\x00")


class LogWriter:
    """Write ``<log_dir>/<gate_name>.log`` files, one per gate.

    ``log_dir`` is created on first write. ``write`` returns the resolved path so
    callers can record it in structured logs (solution: "emits ... log_path").
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = Path(log_dir)

    def _safe_path(self, gate_name: str) -> Path:
        """Resolve ``<log_dir>/<gate_name>.log`` after validating ``gate_name``.

        Raises ``ValueError`` when ``gate_name`` is empty, a relative-path token, or
        contains a separator/traversal component, or when the resolved path escapes
        ``log_dir``. The structural check rejects ``..`` and separators before the
        path is built; the ``relative_to`` check is the containment backstop.
        """
        if gate_name in ("", ".", "..") or any(t in gate_name for t in _FORBIDDEN):
            raise ValueError(f"unsafe gate name for log path: {gate_name!r}")
        root = self.log_dir.resolve()
        candidate = (root / f"{gate_name}.log").resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"log path for gate {gate_name!r} escapes {root}"
            ) from exc
        return candidate

    def write(self, gate_name: str, content: str) -> Path:
        """Write ``content`` to ``<log_dir>/<gate_name>.log`` and return the path.

        The full ``content`` is written verbatim (no truncation) so a large gate
        output is preserved byte-for-byte in the log even though the ``GateResult``
        keeps only parsed findings (D-15).
        """
        path = self._safe_path(gate_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
