const Module = require("module"), fs = require("fs"), path = require("path");
const calls = { info: [], error: [], opened: [], posted: [], warned: [], warnAnswer: undefined };
const os = require("os"), cp = require("child_process"), assert = require("assert");
const root = fs.mkdtempSync(path.join(os.tmpdir(), "verifix-apply-"));
const fixture = path.resolve(__dirname, "../../tests/fixtures/demo-retry");
fs.cpSync(fixture, path.join(root, "demo"), { recursive: true, filter: (s) => !s.includes(`${path.sep}runs`) });
const git = (...a) => cp.execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", ...a], { cwd: root });
git("init", "-q"); git("add", "-A"); git("commit", "-q", "-m", "base");  // the workspace is a SUBFOLDER of a git repo
const ws = path.join(root, "demo");
const vscodeMock = {
  window: { registerWebviewViewProvider: (_id, p) => { calls.provider = p; return { dispose() {} }; },
            showInformationMessage: (m) => calls.info.push(m),
            showWarningMessage: async (m, opts, ...buttons) => { calls.warned.push({ m, opts }); return calls.warnAnswer; }, showErrorMessage: (m) => calls.error.push(m),
            showTextDocument: async (d) => calls.opened.push(d.file), createWebviewPanel: () => ({ webview: {} }) },
  workspace: { workspaceFolders: [{ uri: { fsPath: ws } }], getConfiguration: () => ({ get: () => undefined }),
               openTextDocument: async (f) => ({ file: f }) },
  commands: { registerCommand: () => ({ dispose() {} }), executeCommand() {} },
  Uri: { joinPath: (...a) => ({ fsPath: a.join("/") }) }, ViewColumn: { Beside: 2 },
};
const orig = Module._load;
Module._load = (req, ...r) => (req === "vscode" ? vscodeMock : orig(req, ...r));
const ext = require(path.resolve(__dirname, "../out/extension.js"));
ext.activate({ extensionUri: {}, subscriptions: [] });
const view = { webview: { options: {}, html: "", asWebviewUri: (u) => u, cspSource: "", onDidReceiveMessage: () => {},
                          postMessage: (m) => calls.posted.push(m.type) } };
calls.provider.resolveWebviewView(view);
const diff = fs.readFileSync(path.join(ws, "patches/2-correct.diff"), "utf8");
calls.provider.handleLine(JSON.stringify({ type: "run_finished", data: { diff, decision: "verified" } }));
const before = fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8");
calls.provider.onMessage({ type: "apply" });
setTimeout(() => {
  const after = fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8");
  assert.ok(before !== after && after.includes("max(0"), "Apply Patch must really change the file");
  assert.deepStrictEqual(calls.error, []);
  assert.match(calls.info[0], /patch applied to pricing\/discount\.py/);
  assert.deepStrictEqual(calls.opened.map((f) => path.relative(ws, f)), ["pricing/discount.py"]);
  assert.ok(calls.posted.includes("applied"));
  calls.info.length = 0;
  calls.provider.onMessage({ type: "apply" });  // already applied: must be reported as a failure, not a success
  setTimeout(async () => {
    assert.strictEqual(calls.error.length, 1);
    assert.strictEqual(calls.info.length, 0);
    const host = fs.readFileSync(path.join(ws, ".verifix", "logs", "extension.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l))
      .filter((h) => h.type === "apply_result");
    assert.deepStrictEqual(host.map((h) => h.data.landed), [true, false], "both apply attempts are logged with their outcome");
    assert.deepStrictEqual(host[0].data.files, ["pricing/discount.py"]);
    // --- an UNVERIFIED run: no silent apply; force needs the modal confirmation; declining changes nothing
    git("checkout", "--", ".");
    const original = fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8");
    calls.provider.handleLine(JSON.stringify({ type: "run_finished", data: { diff, decision: "reject" } }));
    calls.info.length = 0; calls.error.length = 0;
    calls.provider.onMessage({ type: "apply" });                       // plain apply of an unverified patch: ignored
    await new Promise((r) => setTimeout(r, 400));
    assert.strictEqual(calls.warned.length, 0);
    assert.strictEqual(fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8"), original, "unverified patch must not be applied silently");
    calls.warnAnswer = undefined;                                       // user dismisses the dialog
    calls.provider.onMessage({ type: "apply", force: true, detail: "unit_tests: 1 failed" });
    await new Promise((r) => setTimeout(r, 600));
    assert.strictEqual(calls.warned.length, 1);
    assert.ok(calls.warned[0].opts.modal && calls.warned[0].opts.detail.includes("unit_tests: 1 failed"), "modal shows what failed");
    assert.strictEqual(fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8"), original, "declined: nothing applied");
    calls.warnAnswer = "Apply anyway";                                  // user confirms
    calls.provider.onMessage({ type: "apply", force: true, detail: "unit_tests: 1 failed" });
    await new Promise((r) => setTimeout(r, 900));
    assert.ok(fs.readFileSync(path.join(ws, "pricing/discount.py"), "utf8").includes("max(0"), "confirmed: applied");
    assert.match(calls.info[0], /\(not verified\)/);
    const log = fs.readFileSync(path.join(ws, ".verifix", "logs", "extension.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l))
      .filter((h) => h.type === "apply_unverified").map((h) => h.data.confirmed);
    assert.deepStrictEqual(log, [false, true], "both decisions are logged");
    fs.rmSync(root, { recursive: true, force: true });
    console.log("apply-patch tests passed");
  }, 600);
}, 800);
