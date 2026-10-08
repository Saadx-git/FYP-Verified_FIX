from __future__ import annotations

from verifix.models.evidence import PatchAssessment
from verifix.models.failure import FailureDiagnosis
from verifix.models.patch import CandidatePatch


class FailureDiagnoser:
    """Localizes and classifies verification failures."""

    def diagnose(
        self,
        patch: CandidatePatch,
        assessment: PatchAssessment,
    ) -> FailureDiagnosis:
        """TODO: Diagnose the failure."""
        raise NotImplementedError
