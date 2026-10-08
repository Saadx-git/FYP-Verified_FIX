from __future__ import annotations

from verifix.verification.base import Verifier


class VerifierRegistry:
    """Holds available verifiers by name."""

    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, verifier: Verifier) -> None:
        self._verifiers[verifier.name] = verifier

    def get(self, name: str) -> Verifier:
        return self._verifiers[name]

    def names(self) -> list[str]:
        return list(self._verifiers)
