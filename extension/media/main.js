(function () {
  const vscode = acquireVsCodeApi();
  const app = document.getElementById("app");
  // script errors in the sidebar are reported to the host's log instead of vanishing
  window.addEventListener("error", (e) => vscode.postMessage({ type: "log", message: String(e.message), line: e.lineno }));
  window.addEventListener("unhandledrejection", (e) => vscode.postMessage({ type: "log", message: "unhandled rejection: " + String(e.reason) }));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fresh = () => ({ phase: "idle", unclear: "", status: "", attempt: 0, max: 0, diff: "", verifiers: [], track: [], logs: "", error: "", final: null, applied: false, cur: null, step: 0, tool: "", wait: 0 });
  let issues = [];
  let selected = "";
  let draft = "";
  let agent = "groq";
  let confirm = true;  // typed / GitHub issues are shown for confirmation before running
  const NEW = "__new__";
  let s = fresh();

  const renderDiff = (d) => `<pre class="diff">${d.split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l)).map((l) => {
    const c = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hdr" : "";
    return `<div class="${c}">${esc(l) || " "}</div>`; }).join("")}</pre>`;

  const OUT_ICON = { passed: "✓", xpassed: "✓", failed: "✗", error: "✗", xfailed: "–" };
  const testsHtml = (v) => (v.tests && v.tests.length)
    ? `<details ${v.tests.some((t) => t.outcome === "failed" || t.outcome === "error") ? "open" : ""}><summary>${esc(v.name)} tests: ${
      Object.entries(v.counts || {}).map(([k, n]) => `${n} ${esc(k)}`).join(", ")}</summary>${v.tests.map((t) =>
      `<div class="t o-${esc(t.outcome)}">${OUT_ICON[t.outcome] || "?"} ${esc(t.id.split("::").pop())} <span class="role">${esc(t.role)}</span>${
        t.message ? `<pre>${esc(t.message)}</pre>` : ""}</div>`).join("")}</details>` : "";

  function icon(st) {
    return st === "pass" ? '<span class="ico ok">✓</span>' : st === "fail" ? '<span class="ico fail">✗</span>'
      : st === "running" ? '<span class="ico spin">◌</span>' : st === "skipped" || st === "not_run" ? '<span class="ico">–</span>' : '<span class="ico warn">⚠</span>';
  }

  // one check's result row; failed / warning checks list their findings (open by default)
  const verifierRow = (v) => `<div class="card ${v.status === "fail" ? "fail" : ""}">${icon(v.status)}<div>${esc(v.name)}${v.summary ? ` — ${esc(v.summary)}` : ""}${
    v.findings && v.findings.length > 1 && v.status !== "pass" ? `<details ${v.status === "fail" ? "open" : ""}><summary>${v.findings.length} findings</summary>${v.findings.slice(0, 8).map((f) => `<div class="t">${esc(f)}</div>`).join("")}</details>` : ""}${testsHtml(v)}</div></div>`;

  // everything that happened in one attempt: plan, files, patch, checks, why it was rejected, what Verifix did next
  const attemptHtml = (t, open) => `<details class="attempt" ${open ? "open" : ""}><summary>${icon(t.ok ? "pass" : "fail")} Attempt ${t.attempt} — ${esc(t.text)}${t.score !== undefined ? ` <span class="sub">score ${esc(t.score)}</span>` : ""}</summary>
    ${t.plan ? `<div class="sub">${esc(t.plan.slice(0, 300))}</div>` : ""}
    ${t.error ? `<div class="err">Agent error: ${esc(t.error)}</div>` : ""}
    <div class="sub">${t.files && t.files.length ? "Changed: " + t.files.map(esc).join(", ") : "No files changed"}</div>
    ${t.diff ? `<details><summary>Patch</summary>${renderDiff(t.diff)}</details>` : ""}
    ${(t.verifiers || []).map(verifierRow).join("")}
    ${t.rationale && !t.ok ? `<div class="sub">Why: ${esc(t.rationale)}</div>` : ""}
    ${t.diag ? `<div class="card warn"><span class="ico warn">↻</span><div><b>${esc(t.diag.category)}</b> → ${esc(t.diag.strategy)}<div class="sub">${esc(t.diag.summary)}</div>${(t.diag.details || []).map((x) => `<div class="sub">${esc(x)}</div>`).join("")}</div></div>` : ""}</details>`;

  const failingChecks = () => { const last = s.track[s.track.length - 1]; return last ? (last.verifiers || []).filter((v) => v.status === "fail").map((v) => `${v.name}: ${v.summary}`) : []; };

  function render() {
    const isNew = selected === NEW;
    const issue = issues.find((i) => i.id === selected);
    const running = s.phase === "running";
    let h = agent === "fake" ? `<div class="card warn"><span class="ico warn">⚠</span><div><b>DEMO MODE</b><div class="sub">Canned agent with a planned first failure. Not a real run.</div></div></div>` : "";
    h += `<h4>Active GitHub issue</h4><select id="issue" ${running ? "disabled" : ""}>` +
      issues.map((i) => `<option value="${esc(i.id)}" ${i.id === selected ? "selected" : ""}>#${esc(i.id)} — ${esc(i.title)}</option>`).join("") +
      `<option value="${NEW}" ${isNew ? "selected" : ""}>＋ New issue…</option></select>`;
    if (isNew && !running && s.phase !== "review") {
      h += `<h4>Describe the bug, or paste a GitHub issue link / #number</h4>
        <textarea id="draft" rows="5" placeholder="e.g. apply_discount returns the discount instead of the discounted price">${esc(draft)}</textarea>`;
    }
    const canRun = isNew ? draft.trim().length > 0 : !!issue;

    if (s.phase === "idle") {
      h += `<div class="row"><button id="run" ${canRun ? "" : "disabled"}>${isNew && confirm ? "Check &amp; run" : "Run Verifix"}</button></div>
        <div class="empty"><div class="shield">🛡</div>Select an issue and run Verifix to generate an evidence-verified patch.</div>`;
    } else if (s.phase === "review") {
      const i = s.interpreted;
      h += `<h4>How Verifix understood your issue</h4><div class="card"><div><b>${esc(i.title)}</b>
        <ul>${i.requirements.map((r) => `<li><b>${esc(r.id)}</b> ${esc(r.description)}${r.expected ? `<div class="sub">expected: ${esc(r.expected)}</div>` : ""}</li>`).join("")}</ul>
        ${i.acceptance_criteria.length ? `<div class="sub">Done when: ${i.acceptance_criteria.map(esc).join(" · ")}</div>` : ""}</div></div>
        <div class="sub" style="margin-top:6px">If this is not what you meant, edit the description. Verifix verifies the patch against exactly this reading.</div>
        <div class="row"><button id="confirm">Looks right — Run Verifix</button><button class="secondary" id="edit">Edit description</button></div>`;
    } else {
      if (running) {
        const label = s.verifiers.length ? "Verifying patch" : "Generating patch";
        h += `<div class="card active"><span class="ico spin">◌</span><div>${s.attempt ? `${label} — attempt ${s.attempt} of ${s.max}${!s.verifiers.length && s.step ? ` · step ${s.step}${s.tool ? ` (${esc(s.tool)})` : ""}` : ""}` : esc(s.status || "Starting…")}${
          s.wait ? `<div class="sub">Rate-limited by the model provider: waiting ${s.wait}s, then retrying…</div>` : ""}</div></div>`;
        if (s.diff) { h += `<h4>Synthesized diff (candidate #${s.attempt})</h4>` + renderDiff(s.diff); }
        if (s.verifiers.length) { h += "<h4>Verification pipeline</h4>" + s.verifiers.map(verifierRow).join(""); }
      }
      if (s.track.length) {
        h += "<h4>Attempt track</h4>" + s.track.map((t, i) => attemptHtml(t, !running && i === s.track.length - 1)).join("");
      }
      if (s.final) {
        const f = s.final;
        if (s.unclear) {
          h += `<div class="card warn"><span class="ico warn">⚠</span><div><b>Need more detail</b><div class="sub">${esc(s.unclear)}</div></div></div>
            <div class="row"><button id="edit">Edit description</button></div>`;
        } else
        h += f.ok
          ? `<div class="card ok"><span class="ico ok">✓</span><div><b>Verified fix synthesized</b><div class="sub">Verified on attempt ${f.attempts}</div></div></div>`
          : `<div class="card fail"><span class="ico fail">✗</span><div><b>${esc(f.decision === "reject" ? "Rejected" : f.decision)}</b><div class="sub">Not verified after ${f.attempts} attempt(s)</div>${
            failingChecks().map((w) => `<div class="sub">✗ ${esc(w)}</div>`).join("")}</div></div>`;
        if (!s.unclear) h += `<div class="stats"><div><span>Attempts utilized</span><b>${f.attempts} / ${s.max}</b></div><div><span>Reliability score</span><b>${f.score}</b></div></div>`;
        if (s.unclear) { /* nothing to apply or retry: the user must rewrite the description */ }
        else if (f.ok) {
          h += `<div class="row"><button id="apply" ${s.applied ? "disabled" : ""}>${s.applied ? "Patch applied" : "Apply Patch"}</button><button class="secondary" id="report">View Report</button></div><div class="row"><button class="secondary" id="run">Run again</button><button class="secondary" id="openlog">Open run log</button></div>`;
        } else {
          h += `<div class="row"><button id="run">Retry</button><button class="secondary" id="report">View Report</button></div>
            ${f.diff ? `<div class="row"><button class="secondary" id="applyanyway" ${s.applied ? "disabled" : ""}>${s.applied ? "Patch applied (unverified)" : "Apply best patch anyway"}</button></div>` : ""}
            <div class="row"><button class="secondary" id="openlog">Open run log</button></div>`;
        }
      } else if (running) {
        h += `<div class="row"><button class="secondary" id="cancel">Cancel</button></div>`;
      }
      if (s.error) { h += `<div class="err">${esc(s.error)}</div>`; }
      if (s.phase === "cancelled" || s.phase === "error") { h += `<div class="row"><button id="run">Run again</button><button class="secondary" id="openlog">Open run log</button></div>`; }
      if (s.logs) { h += `<h4>Model logs</h4><div class="log">${esc(s.logs.slice(-1500))}</div>`; }
    }
    app.innerHTML = h;
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
    const sel = document.getElementById("issue");
    // picking another issue after a run clears the previous result (Apply Patch, report, attempts...)
    if (sel) sel.onchange = () => { selected = sel.value; if (s.phase !== "running") s = fresh(); render(); };
    const ta = document.getElementById("draft");
    if (ta) ta.oninput = () => { draft = ta.value; const b = document.getElementById("run"); if (b) b.disabled = !draft.trim(); };
    on("run", () => vscode.postMessage(selected === NEW ? { type: confirm ? "understand" : "run", text: draft } : { type: "run", issueId: selected }));
    on("confirm", () => vscode.postMessage({ type: "run", issueId: s.interpreted.issue_id }));
    on("cancel", () => vscode.postMessage({ type: "cancel" }));
    on("apply", () => vscode.postMessage({ type: "apply" }));
    on("edit", () => { s = fresh(); render(); });  // back to the form with the text still in the box
    on("report", () => vscode.postMessage({ type: "report" }));
    on("openlog", () => vscode.postMessage({ type: "openLog" }));
    on("applyanyway", () => vscode.postMessage({ type: "apply", force: true, detail: failingChecks().join("\n") }));
  }

  function onEvent(ev) {
    const d = ev.data;
    switch (ev.type) {
      case "understanding_issue": s.status = d.source === "github" ? "Fetching and understanding the GitHub issue…" : "Understanding the issue…"; break;
      case "issue_loaded":
        if (!issues.find((i) => i.id === d.issue_id)) issues.unshift({ id: d.issue_id, title: d.title });
        selected = d.issue_id; draft = ""; break;
      case "issue_unclear": s.unclear = d.question; break;
      case "issue_understood":
        s.interpreted = d;
        if (d.unclear) { s.unclear = d.unclear; s.phase = "done"; s.final = { ok: false, decision: "insufficient_evidence", attempts: 0, score: 0 }; }
        else { s.phase = "review"; }
        break;
      case "run_started": s.max = d.max_attempts; break;
      case "attempt_started": s.attempt = d.attempt; s.max = d.max_attempts; s.verifiers = []; s.diff = ""; s.step = 0; s.tool = ""; s.wait = 0; s.cur = { attempt: d.attempt, plan: "", files: [], diff: "", error: "" }; break;
      case "patch_generated": s.diff = d.diff; if (s.cur) Object.assign(s.cur, { plan: d.plan, files: d.files, diff: d.diff }); break;
      case "agent_error": if (s.cur) s.cur.error = d.message; break;
      case "agent_step": s.step = d.step; s.tool = (d.tools || []).join(", "); s.wait = 0; break;
      case "llm_wait": s.wait = d.seconds; break;
      case "verifier_started": s.wait = 0; s.verifiers.push({ name: d.verifier, status: "running", summary: "" }); break;
      case "verifier_skipped": s.verifiers.push({ name: d.verifier, status: "skipped", summary: "skipped — " + d.reason }); break;
      case "verifier_finished": {
        const v = s.verifiers.find((x) => x.name === d.verifier && x.status === "running");
        if (v) { v.status = d.status; v.summary = d.summary; v.tests = d.tests || []; v.counts = d.counts || {}; v.findings = d.findings || []; }
        break;
      }
      case "decision": {
        const ok = d.decision === "verified";
        const failed = s.verifiers.filter((v) => v.status === "fail").map((v) => v.name).join(", ");
        const text = ok ? "Verified" : `Rejected${failed ? " by " + failed : ""}`;
        const last = s.track[s.track.length - 1];
        if (last && last.attempt === d.attempt) { last.rationale = d.rationale; last.ok = ok; }  // the stopping policy's closing "reject" for the same attempt
        else s.track.push({ ...s.cur, attempt: d.attempt, ok, text, rationale: d.rationale, score: d.score, sub: "", verifiers: s.verifiers.map((v) => ({ ...v })) });
        break;
      }
      case "diagnosis": {
        const last = s.track[s.track.length - 1];
        if (last) { last.sub = `feedback sent, executing attempt ${d.attempt + 1}: ${d.summary}`; last.diag = { category: d.category, strategy: d.strategy, summary: d.summary, details: d.details || [] }; }
        break;
      }
      case "run_finished":
        s.phase = "done";
        s.final = { ok: d.decision === "verified", decision: d.decision, attempts: d.attempts, score: d.score, diff: d.diff || "" };
        break;
    }
    render();
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (m.type === "mode") { agent = m.agent; confirm = m.confirm !== false; render(); }
    else if (m.type === "issues") { issues = m.issues; if (selected !== NEW && !issues.find((i) => i.id === selected)) selected = issues[0]?.id ?? NEW; render(); }
    else if (m.type === "reset") { s = fresh(); s.phase = "running"; render(); }
    else if (m.type === "event") onEvent(m.event);
    else if (m.type === "log") { s.logs += m.text; render(); }
    else if (m.type === "error") { s.error = m.message; s.phase = s.final ? "done" : "error"; render(); }
    else if (m.type === "cancelled") { s.phase = "cancelled"; render(); }
    else if (m.type === "applied") { s.applied = true; render(); }
  });
  render();
  vscode.postMessage({ type: "ready" });
})();
