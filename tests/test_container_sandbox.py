import shutil
import sys
from pathlib import Path

import pytest

from verifix.cli.main import main
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.sandbox.docker_sandbox import DockerSandbox

FIXTURE = Path(__file__).parent / "fixtures" / "discount"
pytestmark = pytest.mark.skipif(shutil.which("podman") is None and shutil.which("docker") is None, reason="no container runtime")


def test_container_runs_tests_with_patch_and_no_network(tmp_path):
    sb = DockerSandbox()
    patch = (FIXTURE / "patches" / "2-correct.diff").read_text()
    ok = sb.execute(ExecutionRequest(command=[sys.executable, "-m", "pytest", "-q"], repo_path=str(FIXTURE), patch_diff=patch,
                                     limits=ResourceLimits(timeout_seconds=120)))
    assert ok.exit_code == 0 and "3 passed" in ok.stdout, ok.stdout + ok.stderr
    bad = sb.execute(ExecutionRequest(command=[sys.executable, "-m", "pytest", "-q"], repo_path=str(FIXTURE)))
    assert bad.exit_code != 0  # unpatched repo still fails: the patch really is applied in the container
    net = sb.execute(ExecutionRequest(
        command=[sys.executable, "-c", "import urllib.request as u; u.urlopen('https://example.com', timeout=5)"], repo_path=str(FIXTURE)))
    assert net.exit_code != 0  # network is off
    slow = sb.execute(ExecutionRequest(command=["sleep", "30"], repo_path=str(FIXTURE), limits=ResourceLimits(timeout_seconds=3)))
    assert slow.timed_out


def test_pipeline_end_to_end_in_container(tmp_path, capsys):
    out = tmp_path / "r.json"
    code = main(["run", "--repo", str(FIXTURE), "--issue", "142", "--agent", "fake", "--fake-patches", str(FIXTURE / "patches"),
                 "--verifiers", "unit_tests,static_analysis,security", "--sandbox", "container", "--report", str(out)])
    assert code == 0 and '"attempts": 2' in out.read_text()
