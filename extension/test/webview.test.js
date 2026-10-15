// Drives the sidebar's real script against a tiny fake DOM and replays host messages.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const app = { innerHTML: "" }, els = {}, handlers = {}, posted = [];
const el = (id) => (els[id] ??= { id, value: "" });
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, "../media/main.js"), "utf8"), {
  acquireVsCodeApi: () => ({ postMessage: (m) => posted.push(m) }),
  document: { getElementById: (id) => (id === "app" ? app : app.innerHTML.includes(`id="${id}"`) ? el(id) : null) },
  window: { addEventListener: (t, f) => { handlers[t] = f; } },
});
const send = (m) => handlers.message({ data: m });
const ev = (type, data) => send({ type: "event", event: { type, data } });
const html = () => app.innerHTML;
const same = (actual, expected, msg) => assert.strictEqual(JSON.stringify(actual), JSON.stringify(expected), msg);  // objects come from another realm
const issues = [{ id: "142", title: "Discount is wrong" }, { id: "7", title: "clamp ignores bounds" }];

function finishedRun(decision = "verified") {
  send({ type: "reset" });
  ev("run_started", { max_attempts: 3 });
  ev("issue_loaded", { issue_id: "142", title: "Discount is wrong" });
  ev("attempt_started", { attempt: 1, max_attempts: 3 });
  ev("patch_generated", { diff: "diff --git a/f b/f\n+x\n" });
  ev("verifier_started", { verifier: "unit_tests" });
  ev("verifier_finished", { verifier: "unit_tests", status: decision === "verified" ? "pass" : "fail", summary: "x", counts: {}, tests: [] });
  ev("decision", { attempt: 1, decision: decision === "verified" ? "verified" : "repair_required" });
  ev("run_finished", { decision, attempts: 1, score: 1, diff: "d" });
}

send({ type: "issues", issues });
assert.ok(html().includes('id="run"'), "idle: Run button present");

finishedRun();
assert.ok(html().includes("Verified fix synthesized") && html().includes("Apply Patch"), "run shows the verified result");
assert.ok(html().includes('id="run"') && html().includes("Run again"), "finished run offers Run again");
posted.length = 0; el("run").onclick();
same(posted[0], { type: "run", issueId: "142" }, "Run again re-runs the same issue");

// picking a different issue clears the old result
finishedRun();
el("issue").value = "7"; el("issue").onchange();
assert.ok(!html().includes("Apply Patch") && !html().includes("Patch applied") && !html().includes("Verified fix synthesized"), "old result cleared");
assert.ok(!html().includes("Attempt track") && !html().includes("Verification pipeline"), "old attempts/pipeline cleared");
assert.ok(html().includes('id="run"') && html().includes("Run Verifix") && !html().includes("Run again"), "fresh Run Verifix button for the new issue");
posted.length = 0; el("run").onclick();
same(posted[0], { type: "run", issueId: "7" }, "runs the newly selected issue");

// "applied" state must not leak into the next issue either
finishedRun(); send({ type: "applied" });
assert.ok(html().includes("Patch applied"));
el("issue").value = "142"; el("issue").onchange();
assert.ok(!html().includes("Patch applied") && !html().includes("Apply Patch"), "applied flag cleared on switch");

// choosing New issue... also resets
finishedRun();
el("issue").value = "__new__"; el("issue").onchange();
assert.ok(html().includes('id="draft"') && !html().includes("Apply Patch"), "New issue form shown, old result gone");

// a rejected run keeps its Retry button, and switching issue clears it
finishedRun("reject");
assert.ok(html().includes("Retry") && !html().includes("Apply Patch"), "rejected run offers Retry, no Apply Patch");
el("issue").value = "7"; el("issue").onchange();
assert.ok(!html().includes("Retry") && html().includes("Run Verifix"));

// while a run is in progress the selection must not wipe the live output
send({ type: "issues", issues }); send({ type: "reset" });
ev("attempt_started", { attempt: 1, max_attempts: 3 });
el("issue") && (el("issue").value = "7", el("issue").onchange && el("issue").onchange());
assert.ok(html().includes("Generating patch"), "live run output survives a stray change event");

// an issue that does not match the repo stops with a question and keeps the user's text
send({ type: "issues", issues: [] });
el("draft") && (el("draft").value = "Camp is not restricted to range", el("draft").oninput());
send({ type: "reset" });
ev("understanding_issue", { source: "text" });
ev("issue_unclear", { issue_id: "adhoc-1", question: "Which function do you mean?" });
ev("run_finished", { decision: "insufficient_evidence", attempts: 0, score: 0, diff: "" });
assert.ok(html().includes("Need more detail") && html().includes("Which function do you mean?"), "question shown");
assert.ok(!html().includes("Apply Patch") && !html().includes("Retry") && !html().includes("Attempts utilized"), "no verdict card or buttons");
assert.ok(html().includes('id="edit"'), "offers to edit the description");
el("edit").onclick();
assert.ok(html().includes('id="draft"') && html().includes("Camp is not restricted to range"), "back to the form, text kept");

// script errors in the sidebar are forwarded to the host log
posted.length = 0;
handlers.error({ message: "x is not defined", lineno: 7 });
same(posted[0], { type: "log", message: "x is not defined", line: 7 }, "UI errors are reported to the host");
// ---- detail: every attempt is a full record, and a rejected run says why and offers "apply anyway"
{
  send({ type: "issues", issues }); send({ type: "reset" });
  ev("run_started", { max_attempts: 2 });
  ev("attempt_started", { attempt: 1, max_attempts: 2 });
  ev("patch_generated", { attempt: 1, plan: "Flip the minus to a plus in the recursion", files: ["fib.py"], diff: "diff --git a/fib.py b/fib.py\n-    return fib(n-1) - fib(n-2)\n+    return fib(n-1) + fib(n-2)\n" });
  ev("verifier_started", { verifier: "unit_tests" });
  ev("verifier_finished", { verifier: "unit_tests", status: "fail", summary: "target test still failing: test_fib_3", findings: ["target test still failing: test_fib_3", "regression: test_sequence", "pre-existing failure: test_old"], counts: {}, tests: [] });
  ev("verifier_started", { verifier: "security" });
  ev("verifier_finished", { verifier: "security", status: "pass", summary: "no new security findings", findings: ["no new security findings"], counts: {}, tests: [] });
  ev("decision", { attempt: 1, decision: "repair_required", score: 0.4, rationale: "failed: unit_tests" });
  ev("diagnosis", { attempt: 1, category: "regression_introduced", strategy: "revise_patch", summary: "Your change broke previously passing behavior.", details: ["unit_tests: regression: test_sequence"] });
  ev("attempt_started", { attempt: 2, max_attempts: 2 });
  ev("agent_error", { attempt: 2, message: "Groq API error 429: rate limited" });
  ev("decision", { attempt: 2, decision: "repair_required", score: 0, rationale: "failed: patch" });
  ev("decision", { attempt: 2, decision: "reject", score: 0, rationale: "stopped after 2 attempt(s)" });
  ev("run_finished", { decision: "reject", attempts: 2, score: 0, diff: "diff --git a/fib.py b/fib.py\n+x\n" });
  const page = html();
  assert.ok(page.includes("Attempt 1 — Rejected by unit_tests") && page.includes("Attempt 2 — Rejected"), "both attempts listed");
  assert.ok(page.includes("Flip the minus to a plus") && page.includes("Changed: fib.py"), "the agent's plan and the files it changed");
  assert.ok(page.includes("<summary>Patch</summary>") && page.includes("fib(n-1) + fib(n-2)"), "the patch of that attempt is viewable");
  assert.ok(page.includes("3 findings") && page.includes("regression: test_sequence"), "all findings of a failed check are listed");
  assert.ok(page.includes("regression_introduced") && page.includes("revise_patch") && page.includes("broke previously passing"), "diagnosis, chosen strategy and feedback shown");
  assert.ok(page.includes("Agent error: Groq API error 429"), "an agent/API error is shown inside its attempt, not lost");
  assert.strictEqual((page.match(/Attempt 2 —/g) || []).length, 1, "the closing reject does not duplicate the attempt");
  assert.ok(page.includes("Not verified after 2 attempt(s)"), "final card says it was not verified");
  assert.ok(page.includes("Apply best patch anyway") && page.includes("Open run log") && page.includes("Retry"), "offers apply-anyway, run log and retry");
  assert.ok(!page.includes("Apply Patch"), "the normal Apply Patch is reserved for verified runs");
  posted.length = 0; el("applyanyway").onclick();
  same(posted[0], { type: "apply", force: true, detail: "" }, "apply-anyway goes to the host with force");
  posted.length = 0; el("openlog").onclick();
  same(posted[0], { type: "openLog" }, "open run log");
  send({ type: "applied" });
  assert.ok(html().includes("Patch applied (unverified)"), "an unverified apply is labelled as such");

  // the reason lists the failing checks of the final attempt
  send({ type: "reset" });
  ev("attempt_started", { attempt: 1, max_attempts: 1 });
  ev("verifier_started", { verifier: "requirement" });
  ev("verifier_finished", { verifier: "requirement", status: "fail", summary: "R1 not_met: lower bound missing", findings: ["R1 not_met: lower bound missing"], counts: {}, tests: [] });
  ev("decision", { attempt: 1, decision: "reject", score: 0.2, rationale: "stopped" });
  ev("run_finished", { decision: "reject", attempts: 1, score: 0.2, diff: "d" });
  assert.ok(html().includes("✗ requirement: R1 not_met: lower bound missing"), "the failing check is named on the final card");
  posted.length = 0; el("applyanyway").onclick();
  same(posted[0], { type: "apply", force: true, detail: "requirement: R1 not_met: lower bound missing" }, "the host's confirmation dialog gets the reasons");

  // no patch at all (e.g. crashed before one existed): nothing to apply anyway
  send({ type: "reset" });
  ev("run_finished", { decision: "reject", attempts: 0, score: 0, diff: "" });
  assert.ok(!html().includes("Apply best patch anyway"));

  // live progress: the agent's steps, rate-limit waits, and the switch to "Verifying"
  send({ type: "reset" });
  ev("attempt_started", { attempt: 2, max_attempts: 3 });
  ev("agent_step", { step: 4, max_steps: 16, tools: ["edit_file"], tokens: 900 });
  assert.ok(html().includes("Generating patch — attempt 2 of 3 · step 4 (edit_file)"), "agent step shown");
  ev("llm_wait", { seconds: 12 });
  assert.ok(html().includes("Rate-limited by the model provider: waiting 12s"), "rate-limit wait shown, so a slow run does not look frozen");
  ev("agent_step", { step: 5, max_steps: 16, tools: ["submit"], tokens: 100 });
  assert.ok(!html().includes("waiting 12s") && html().includes("step 5 (submit)"), "wait note clears on the next step");
  ev("patch_generated", { attempt: 2, plan: "p", files: ["a.py"], diff: "d" });
  ev("verifier_started", { verifier: "unit_tests" });
  assert.ok(html().includes("Verifying patch — attempt 2 of 3") && !html().includes("Generating patch"), "label switches to verifying");
  // a verified run keeps the normal button and also offers the log; an error offers the log too
  finishedRun();
  assert.ok(html().includes("Apply Patch") && html().includes("Open run log") && !html().includes("anyway"));
  send({ type: "reset" }); send({ type: "error", message: "boom" });
  assert.ok(html().includes("boom") && html().includes("Open run log") && html().includes("Run again"));
  el("issue").value = "142"; el("issue").onchange();  // back to idle for whatever follows
}

console.log("webview tests passed");

// confirm step: typed issue -> interpretation shown -> confirm runs the saved issue, edit goes back with the text kept
{
  send({ type: "mode", agent: "groq", confirm: true });
  send({ type: "issues", issues: [] });
  el("draft").value = "Camp is not restricted to range"; el("draft").oninput();
  assert.ok(html().includes("Check &amp; run"), "typed issue gets the check-and-run button");
  posted.length = 0; el("run").onclick();
  same(posted[0], { type: "understand", text: "Camp is not restricted to range" }, "typed issue is interpreted first, not run");
  send({ type: "reset" });
  ev("understanding_issue", { source: "text" });
  assert.ok(html().includes("Understanding the issue"));
  ev("issue_understood", { issue_id: "adhoc-1", title: "Clamp not restricting to range", unclear: "",
    requirements: [{ id: "R1", description: "clamp below lo", observed: "x", expected: "returns lo" }], acceptance_criteria: ["both bounds clamped"] });
  assert.ok(html().includes("How Verifix understood your issue") && html().includes("Clamp not restricting to range"), "interpretation shown");
  assert.ok(html().includes("returns lo") && html().includes("both bounds clamped"), "requirements and criteria shown");
  assert.ok(!html().includes('id="draft"') && !html().includes("Apply Patch"), "form hidden while reviewing");
  posted.length = 0; el("confirm").onclick();
  same(posted[0], { type: "run", issueId: "adhoc-1" }, "confirm runs the interpreted (saved) issue");
  ev("issue_understood", { issue_id: "adhoc-1", title: "t", unclear: "", requirements: [], acceptance_criteria: [] });
  el("edit").onclick();
  assert.ok(html().includes('id="draft"') && html().includes("Camp is not restricted to range"), "edit returns to the form with the text kept");
  // an unmatched report shows the question instead of a review
  send({ type: "reset" });
  ev("issue_understood", { issue_id: "adhoc-2", title: "t", unclear: "Which function do you mean?", requirements: [], acceptance_criteria: [] });
  assert.ok(html().includes("Need more detail") && !html().includes('id="confirm"'), "unclear report asks, no confirm button");
  // with confirmation turned off the typed issue runs directly, as before
  send({ type: "mode", agent: "groq", confirm: false });
  el("edit").onclick();  // back to the form from the "need more detail" card
  assert.ok(html().includes("Run Verifix") && !html().includes("Check &amp; run"));
  posted.length = 0; el("run").onclick();
  same(posted[0], { type: "run", text: "Camp is not restricted to range" }, "confirmation off: runs directly");
  console.log("confirm-step tests passed");
}
