from __future__ import annotations

from verifix.verification.base import Verifier


class VerifierRegistry:
    """Holds available verifiers by name."""

    def register(self, verifier: Verifier) -> None:
        """TODO: Register a verifier."""
        raise NotImplementedError

    def get(self, name: str) -> Verifier:
        """TODO: Look up a verifier."""
        raise NotImplementedError

    def names(self) -> list[str]:
        """TODO: List registered verifier names."""
        raise NotImplementedError
