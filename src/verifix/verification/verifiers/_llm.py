from __future__ import annotations

import json
import re

from verifix.llm.client import GroqClient
from verifix.verification.base import VerificationContext

MAX_DIFF = 6000


def ask_json(client: GroqClient, model: str, system: str, user: str, purpose: str = "") -> tuple[dict, int]:
    """One JSON-mode call; returns (parsed object, tokens). Unparseable output yields {}."""
    resp = client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       max_tokens=2048, json_mode=True, reasoning_effort="low", purpose=purpose)
    text = resp.text.strip()
    try:
        return json.loads(text), resp.tokens
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            return (json.loads(m.group(0)) if m else {}), resp.tokens
        except json.JSONDecodeError:
            return {}, resp.tokens


def issue_text(context: VerificationContext) -> str:
    i = context.issue
    parts = [f"Issue #{i.issue_id}: {i.title}\n{i.body}"]
    if i.acceptance_criteria:
        parts.append("Acceptance criteria:\n- " + "\n- ".join(i.acceptance_criteria))
    return "\n\n".join(parts)


def prior_text(context: VerificationContext) -> str:
    rs = context.extra.get("prior_results", [])
    def line(r) -> str:
        pre = [f for f in r.findings if "pre-existing failure" in f.message]
        note = f"; {len(pre)} failure(s) are pre-existing: they also fail without this patch and are NOT caused by it" if pre else ""
        return f"- {r.verifier_name}: {r.status.value} ({r.findings[0].message if r.findings else ''}{note})"
    return "\n".join(line(r) for r in rs) or "none"
