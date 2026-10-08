from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request

from verifix.llm.client import env_value

_URL = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/issues/(\d+))?/?$")
_ISSUE_URL = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)")


def looks_like_github_issue(ref: str) -> bool:
    return bool(_ISSUE_URL.match(ref.strip())) or bool(re.fullmatch(r"#?\d+", ref.strip()))


def parse_ref(ref: str, repo_path: str) -> tuple[str, str, int]:
    """'https://github.com/o/r/issues/12' or '#12' (owner/repo taken from the git remote)."""
    ref = ref.strip()
    if m := _ISSUE_URL.match(ref):
        return m[1], m[2], int(m[3])
    number = int(ref.lstrip("#"))
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_path, capture_output=True, text=True, check=False)
    m = _URL.search(remote.stdout.strip())
    if not m:
        raise RuntimeError("cannot resolve '#N': this folder has no GitHub 'origin' remote; paste the full issue URL")
    return m[1], m[2], number


def fetch_issue(ref: str, repo_path: str, transport=None) -> tuple[int, str, str]:
    """Return (number, title, body[+comments]) from the GitHub REST API (token via GITHUB_TOKEN, optional)."""
    owner, repo, number = parse_ref(ref, repo_path)
    base = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    get = transport or _http
    issue = get(base)
    if "pull_request" in issue:
        raise RuntimeError(f"{owner}/{repo}#{number} is a pull request, not an issue")
    body = issue.get("body") or ""
    if issue.get("comments"):
        comments = get(base + "/comments?per_page=5")
        body += "\n\nComments:\n" + "\n---\n".join((c.get("body") or "")[:800] for c in comments)
    return number, issue.get("title", ""), body


def _http(url: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "verifix/0.1"}
    if token := env_value("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        hint = " (private repo? set GITHUB_TOKEN)" if e.code in (401, 403, 404) else ""
        raise RuntimeError(f"GitHub API error {e.code} for {url}{hint}") from e
