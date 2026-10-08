(function () {
  const vscode = acquireVsCodeApi();
  const app = document.getElementById("app");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fresh = () => ({ phase: "idle", attempt: 0, max: 0, diff: "", verifiers: [], track: [], logs: "", error: "", final: null, applied: false });
  let issues = [];
  let selected = "";
  let s = fresh();

  const renderDiff = (d) => `<pre class="diff">${d.split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l)).map((l) => {
    const c = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hdr" : "";
    return `<div class="${c}">${esc(l) || " "}</div>`; }).join("")}</pre>`;

  function icon(st) {
    return st === "pass" ? '<span class="ico ok">✓</span>' : st === "fail" ? '<span class="ico fail">✗</span>'
      : st === "running" ? '<span class="ico spin">◌</span>' : st === "skipped" ? '<span class="ico">–</span>' : '<span class="ico warn">⚠</span>';
  }

  function render() {
    const issue = issues.find((i) => i.id === selected);
    const running = s.phase === "running";
    let h = `<h4>Active GitHub issue</h4><select id="issue" ${running ? "disabled" : ""}>` +
      (issues.length ? issues.map((i) => `<option value="${esc(i.id)}" ${i.id === selected ? "selected" : ""}>#${esc(i.id)} — ${esc(i.title)}</option>`).join("")
        : "<option>No issues in .verifix/issues/</option>") + "</select>";
    h += `<h4>Target file</h4><div class="field">${esc(issue?.targetFile || "—")}</div>`;

    if (s.phase === "idle") {
      h += `<div class="row"><button id="run" ${issue ? "" : "disabled"}>Run Verifix</button></div>
        <div class="empty"><div class="shield">🛡</div>Select an issue and run Verifix to generate an evidence-verified patch.</div>`;
    } else {
      if (running) {
        h += `<div class="card active"><span class="ico spin">◌</span><div>${s.attempt ? `Generating patch — attempt ${s.attempt} of ${s.max}` : "Starting…"}</div></div>`;
      }
      if (s.diff) { h += `<h4>Synthesized diff (candidate #${s.attempt})</h4>` + renderDiff(s.diff); }
      if (s.verifiers.length) {
        h += "<h4>Verification pipeline</h4>" + s.verifiers.map((v) => `<div class="card ${v.status === "fail" ? "fail" : ""}">${icon(v.status)}<div>${esc(v.name)}${v.summary ? ` — ${esc(v.summary)}` : ""}</div></div>`).join("");
      }
      if (s.track.length) {
        h += "<h4>Attempt track</h4>" + s.track.map((t) => `<div class="card ${t.ok ? "ok" : "warn"}">${icon(t.ok ? "pass" : "fail")}<div class="${t.ok ? "" : "struck"}">Attempt ${t.attempt} — ${esc(t.text)}${t.sub ? `<div class="sub">→ ${esc(t.sub)}</div>` : ""}</div></div>`).join("");
      }
      if (s.final) {
        const f = s.final;
        h += f.ok
          ? `<div class="card ok"><span class="ico ok">✓</span><div><b>Verified fix synthesized</b><div class="sub">Verified on attempt ${f.attempts}</div></div></div>`
          : `<div class="card fail"><span class="ico fail">✗</span><div><b>${esc(f.decision === "reject" ? "Rejected" : f.decision)}</b><div class="sub">Evidence insufficient after ${f.attempts} attempt(s)</div></div></div>`;
        h += `<div class="stats"><div><span>Attempts utilized</span><b>${f.attempts} / ${s.max}</b></div><div><span>Reliability score</span><b>${f.score}</b></div></div>`;
        if (f.ok) {
          h += `<div class="row"><button id="apply" ${s.applied ? "disabled" : ""}>${s.applied ? "Patch applied" : "Apply Patch"}</button><button class="secondary" id="report">View Report</button></div>`;
        } else {
          h += `<div class="row"><button id="run">Retry</button><button class="secondary" id="report">View Report</button></div>`;
        }
      } else if (running) {
        h += `<div class="row"><button class="secondary" id="cancel">Cancel</button></div>`;
      }
      if (s.error) { h += `<div class="err">${esc(s.error)}</div>`; }
      if (s.phase === "cancelled" || s.phase === "error") { h += `<div class="row"><button id="run">Run again</button></div>`; }
      if (s.logs) { h += `<h4>Model logs</h4><div class="log">${esc(s.logs.slice(-1500))}</div>`; }
    }
    app.innerHTML = h;
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
    const sel = document.getElementById("issue");
    if (sel) sel.onchange = () => { selected = sel.value; render(); };
    on("run", () => vscode.postMessage({ type: "run", issueId: selected }));
    on("cancel", () => vscode.postMessage({ type: "cancel" }));
    on("apply", () => vscode.postMessage({ type: "apply" }));
    on("report", () => vscode.postMessage({ type: "report" }));
  }

  function onEvent(ev) {
    const d = ev.data;
    switch (ev.type) {
      case "run_started": s.max = d.max_attempts; break;
      case "attempt_started": s.attempt = d.attempt; s.max = d.max_attempts; s.verifiers = []; s.diff = ""; break;
      case "patch_generated": s.diff = d.diff; break;
      case "verifier_started": s.verifiers.push({ name: d.verifier, status: "running", summary: "" }); break;
      case "verifier_skipped": s.verifiers.push({ name: d.verifier, status: "skipped", summary: "skipped — " + d.reason }); break;
      case "verifier_finished": {
        const v = s.verifiers.find((x) => x.name === d.verifier && x.status === "running");
        if (v) { v.status = d.status; v.summary = d.summary; }
        break;
      }
      case "decision":
        if (d.decision !== "verified") {
          const failed = s.verifiers.filter((v) => v.status === "fail").map((v) => v.name).join(", ");
          s.track.push({ attempt: d.attempt, ok: false, text: `Rejected${failed ? " by " + failed : ""}`, sub: "" });
        }
        break;
      case "diagnosis": {
        const last = s.track[s.track.length - 1];
        if (last) last.sub = `feedback sent, executing attempt ${d.attempt + 1}: ${d.summary}`;
        break;
      }
      case "run_finished":
        s.phase = "done";
        s.final = { ok: d.decision === "verified", decision: d.decision, attempts: d.attempts, score: d.score };
        break;
    }
    render();
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (m.type === "issues") { issues = m.issues; if (!issues.find((i) => i.id === selected)) selected = issues[0]?.id ?? ""; render(); }
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
