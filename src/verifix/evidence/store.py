from __future__ import annotations

from verifix.models.evidence import VerificationResult


class EvidenceStore:
    """Stores verification results per patch (in memory)."""

    def __init__(self) -> None:
        self._results: dict[str, list[VerificationResult]] = {}

    def add(self, patch_id: str, result: VerificationResult) -> None:
        self._results.setdefault(patch_id, []).append(result)

    def get(self, patch_id: str) -> list[VerificationResult]:
        return list(self._results.get(patch_id, []))

    def clear(self, patch_id: str) -> None:
        self._results.pop(patch_id, None)
