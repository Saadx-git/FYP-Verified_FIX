// Host side of the confirm step: typed text is interpreted first (nothing is run), the confirmed issue is then run by id.
const Module = require("module"), fs = require("fs"), os = require("os"), path = require("path"), assert = require("assert");
const ws = fs.mkdtempSync(path.join(os.tmpdir(), "verifix-understand-"));
const log = path.join(ws, "cli.log");
process.env.FAKE_CLI_LOG = log;
let settings = { command: ["node", path.resolve(__dirname, "fake_cli.js")] };
const posted = [];
const opened = [];
const vscodeMock = {
  cmds: {},
  window: { registerWebviewViewProvider: (_i, p) => { vscodeMock.provider = p; return { dispose() {} }; },
            showInformationMessage: (m) => posted.push({ type: "vscode-info", m }), showErrorMessage: (m) => posted.push({ type: "vscode-error", m }),
            showTextDocument: async (d) => opened.push(d.file) },
  workspace: { workspaceFolders: [{ uri: { fsPath: ws } }], getConfiguration: () => ({ get: (k) => settings[k] }), openTextDocument: async (f) => ({ file: f }) },
  commands: { registerCommand: (id, fn) => { vscodeMock.cmds[id] = fn; return { dispose() {} }; }, executeCommand() {} },
  Uri: { joinPath: (...a) => ({ fsPath: a.join("/") }) }, ViewColumn: { Beside: 2 },
};
const load = Module._load;
Module._load = (req, ...r) => (req === "vscode" ? vscodeMock : load(req, ...r));
require(path.resolve(__dirname, "../out/extension.js")).activate({ extensionUri: {}, subscriptions: [] });
vscodeMock.provider.resolveWebviewView({ webview: { options: {}, html: "", asWebviewUri: (u) => u, cspSource: "",
  onDidReceiveMessage: () => {}, postMessage: (m) => posted.push(m) } });
const records = () => fs.readFileSync(log, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
const calls = () => records().map((r) => r.args);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  assert.strictEqual(posted.find((m) => m.type === "mode").confirm, true, "confirmation is on by default");

  // 1. typed text: interpreted (not run); the text reaches the CLI via a temp file that is cleaned up afterwards
  vscodeMock.provider.onMessage({ type: "understand", text: "Camp is not restricted to range" });
  await wait(900);
  let first = calls()[0];
  assert.strictEqual(first[0], "understand");
  assert.ok(first.includes("--description-file") && !first.includes("--events"), "typed text -> understand with a description file");
  const understood = posted.filter((m) => m.type === "event").map((m) => m.event).find((e) => e.type === "issue_understood");
  assert.strictEqual(understood.data.title, "Understood: Camp is not restricted to range", "the CLI received the typed text");
  assert.ok(!fs.existsSync(first[first.indexOf("--description-file") + 1]), "temp description file removed");
  assert.ok(!calls().some((c) => c[0] === "run"), "nothing was run before confirmation");

  // 2. a GitHub link is passed straight through
  vscodeMock.provider.onMessage({ type: "understand", text: "https://github.com/o/r/issues/5" });
  await wait(900);
  const gh = calls()[1];
  assert.deepStrictEqual(gh.slice(0, 1).concat(gh.slice(3)), ["understand", "--issue", "https://github.com/o/r/issues/5"]);

  // 3. confirming runs the saved, interpreted issue by id (no description file, no re-interpretation)
  vscodeMock.provider.onMessage({ type: "run", issueId: "adhoc-1" });
  await wait(900);
  const run = calls()[2];
  assert.strictEqual(run[0], "run");
  assert.strictEqual(run[run.indexOf("--issue") + 1], "adhoc-1");
  assert.ok(!run.includes("--description-file") && run.includes("--events"));
  assert.ok(posted.some((m) => m.type === "event" && m.event.type === "run_finished"));

  // the CLI is told it is being driven from VS Code, so its run log says so
  assert.ok(records().every((r) => r.client === "vscode"), "VERIFIX_CLIENT=vscode passed to the CLI");

  // the host log records each CLI start and exit, and never the typed text
  const host = fs.readFileSync(path.join(ws, ".verifix", "logs", "extension.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.deepStrictEqual(host.filter((h) => h.type === "cli_start").map((h) => h.data.command), ["understand", "understand", "run"]);
  assert.deepStrictEqual(host.filter((h) => h.type === "cli_exit").map((h) => h.data.code), [0, 0, 0]);
  assert.ok(!JSON.stringify(host).includes("Camp is not restricted"), "typed issue text is not written to the host log");

  // a command that cannot start is logged and reported
  settings = { ...settings, command: ["/no/such/binary"] };
  posted.length = 0; vscodeMock.provider.onMessage({ type: "understand", text: "x y z" });
  await wait(600);
  assert.ok(posted.some((m) => m.type === "error" && /Could not start/.test(m.message)));
  assert.ok(fs.readFileSync(path.join(ws, ".verifix", "logs", "extension.jsonl"), "utf8").includes("cli_spawn_error"));
  settings = { ...settings, command: ["node", path.resolve(__dirname, "fake_cli.js")] };

  // UI script errors reach the host log
  vscodeMock.provider.onMessage({ type: "log", message: "boom in sidebar", line: 42 });
  assert.ok(fs.readFileSync(path.join(ws, ".verifix", "logs", "extension.jsonl"), "utf8").includes("boom in sidebar"));

  // "Open Latest Run Log" opens the newest run log, not the host log
  fs.writeFileSync(path.join(ws, ".verifix", "logs", "20260101-000000-aaaaaa.jsonl"), "{}\n");
  fs.writeFileSync(path.join(ws, ".verifix", "logs", "20260102-000000-bbbbbb.jsonl"), "{}\n");
  await vscodeMock.cmds["verifix.openLogs"]();
  assert.strictEqual(path.basename(opened.at(-1)), "20260102-000000-bbbbbb.jsonl");

  // 4. the setting turns confirmation off
  settings = { ...settings, confirmInterpretation: false };
  posted.length = 0; vscodeMock.provider.refreshIssues();
  assert.strictEqual(posted.find((m) => m.type === "mode").confirm, false);
  fs.rmSync(ws, { recursive: true, force: true });
  console.log("understand host tests passed");
})().catch((e) => { console.error(e); process.exit(1); });
