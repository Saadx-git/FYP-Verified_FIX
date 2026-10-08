from pathlib import Path

from verifix.agent.fake import FakeAgent
from verifix.evaluation.baseline import configurations, make_experiment
from verifix.evaluation.benchmark import BenchmarkRunner
from verifix.evaluation.experiment import aggregate

DATASET = str(Path(__file__).parent / "fixtures" / "dataset.json")


def _fake(inst):
    return FakeAgent.from_dir(str(Path(inst["base"]) / inst["fake_patches"]))


def test_baselines_accept_the_incomplete_patch_the_oracle_catches():
    for name in ("baseline-a", "baseline-b"):
        m = BenchmarkRunner().run(make_experiment(name, _fake), DATASET).metrics
        # discount's first patch is functionally right; clamp's first patch passes visible tests but is wrong
        assert (m.n_instances, m.issue_resolution_rate, m.false_acceptance_rate) == (2, 1.0, 0.5), name


def test_all_named_configurations_exist():
    names = set(configurations())
    assert {"baseline-a", "baseline-b", "baseline-c", "full"} <= names
    assert {f"ablation-{c}" for c in "abcdef"} <= names


def test_aggregate_metrics():
    rows = [
        {"accepted": True, "correct": True, "regression": False, "attempts": 2, "tokens": 100,
         "verification_tokens": 20, "seconds": 1.0, "first_attempt_failed": True},
        {"accepted": True, "correct": False, "regression": True, "attempts": 1, "tokens": 50,
         "verification_tokens": 0, "seconds": 3.0, "first_attempt_failed": False},
        {"accepted": False, "correct": False, "regression": False, "attempts": 3, "tokens": 150,
         "verification_tokens": 30, "seconds": 2.0, "first_attempt_failed": True},
    ]
    m = aggregate(rows)
    assert m.false_acceptance_rate == 0.5 and m.false_rejection_rate == 0.0
    assert m.verification_accuracy == 2 / 3 and m.repair_success_after_feedback == 0.5
    assert m.token_api_usage == 100 and m.repair_efficiency == 2.0
