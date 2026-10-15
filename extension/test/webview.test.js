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
