import pytest


@pytest.fixture(autouse=True)
def _isolated_run_logs(tmp_path_factory, monkeypatch):
    """CLI runs in tests must not write logs into the sample repos (or the user's real log folders)."""
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path_factory.mktemp("runlogs")))
