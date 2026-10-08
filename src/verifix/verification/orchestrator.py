from __future__ import annotations

import time

from verifix.events.emitter import EventEmitter
from verifix.evidence.store import EvidenceStore
from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.models.strategy import VerificationStrategy
from verifix.verification.base import VerificationContext
from verifix.verification.registry import VerifierRegistry

EXPENSIVE = {"requirement", "llm_review", "mutation", "integration_tests"}  # token- or time-hungry


class VerificationOrchestrator:
    """Runs selected verifiers and records their results."""

    def __init__(
        self,
        registry: VerifierRegistry,
        store: EvidenceStore,
        emitter: EventEmitter | None = None,
        fail_fast: bool = False,
    ) -> None:
        self.registry = registry
        self.store = store
        self.emitter = emitter or EventEmitter()
        self.fail_fast = fail_fast

    def run(
        self,
        context: VerificationContext,
        strategy: VerificationStrategy,
    ) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        skip_expensive = strategy.parameters.get("skip_expensive_on_fail", False)
        for name in strategy.verifier_names:
            if name not in self.registry.names():
                continue
            if skip_expensive and name in EXPENSIVE and any(r.status is VerificationStatus.FAIL for r in results):
                self.emitter.emit("verifier_skipped", verifier=name, patch_id=context.patch.patch_id,
                                  reason="a cheaper verifier already failed")
                continue
            context.extra["prior_results"] = list(results)
            self.emitter.emit("verifier_started", verifier=name, patch_id=context.patch.patch_id)
            start = time.monotonic()
            try:
                result = self.registry.get(name).verify(context)
            except Exception as exc:  # noqa: BLE001 - a crashing verifier is "no evidence", not a pass
                result = VerificationResult(
                    verifier_name=name,
                    status=VerificationStatus.UNCERTAIN,
                    findings=[VerificationFinding(message=f"verifier crashed: {exc!r}", severity="error")],
                )
            result.verifier_name = result.verifier_name or name
            result.duration_seconds = result.duration_seconds or time.monotonic() - start
            self.store.add(context.patch.patch_id, result)
            results.append(result)
            self.emitter.emit(
                "verifier_finished", verifier=name, patch_id=context.patch.patch_id,
                status=result.status.value, confidence=result.confidence,
                summary=result.findings[0].message if result.findings else "",
                findings=[f.message for f in result.findings][:20],
                duration=result.duration_seconds,
            )
            if self.fail_fast and result.status is VerificationStatus.FAIL:
                break
        return results
