from __future__ import annotations

from verifix.models.evidence import VerificationResult


class EvidenceStore:
    """Stores verification results per patch."""

    def add(self, patch_id: str, result: VerificationResult) -> None:
        """TODO: Store a result."""
        raise NotImplementedError

    def get(self, patch_id: str) -> list[VerificationResult]:
        """TODO: Retrieve results for a patch."""
        raise NotImplementedError

    def clear(self, patch_id: str) -> None:
        """TODO: Remove results for a patch."""
        raise NotImplementedError
