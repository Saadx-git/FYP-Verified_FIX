import { ChildProcess, spawn, spawnSync } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

interface IssueInfo { id: string; title: string; targetFile: string }

class SidebarProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private proc?: ChildProcess;
  private finalDiff = "";
  private reportPath = "";

  constructor(private readonly ctx: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.ctx.extensionUri, "media")] };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((m) => this.onMessage(m));
    this.refreshIssues();
  }

  post(msg: unknown): void { this.view?.webview.postMessage(msg); }

  refreshIssues(): void {
    this.post({ type: "issues", issues: this.findIssues() });
  }

  private workspace(): string | undefined { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }

  private findIssues(): IssueInfo[] {
    const ws = this.workspace();
    if (!ws) { return []; }
    const dir = path.join(ws, ".verifix", "issues");
    if (!fs.existsSync(dir)) { return []; }
    return fs.readdirSync(dir).filter((f) => f.endsWith(".json")).flatMap((f) => {
      try {
        const d = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
        return [{ id: String(d.issue_id ?? f.replace(".json", "")), title: d.title ?? "", targetFile: d.target_file ?? "" }];
      } catch { return []; }
    });
  }

  /** Locate the Verifix Python project: setting, else walk up from the workspace. */
  private projectDir(): string | undefined {
    const cfg = vscode.workspace.getConfiguration("verifix").get<string>("projectDir");
    if (cfg) { return cfg; }
    let dir = this.workspace();
    while (dir && dir !== path.dirname(dir)) {
      const py = path.join(dir, "pyproject.toml");
      if (fs.existsSync(py) && /name\s*=\s*"verifix"/.test(fs.readFileSync(py, "utf8"))) { return dir; }
      dir = path.dirname(dir);
    }
    return undefined;
  }

  private onMessage(m: { type: string; issueId?: string; text?: string }): void {
    if (m.type === "ready") { this.refreshIssues(); }
    else if (m.type === "run" && (m.issueId || m.text)) { this.run(m.issueId ?? "", m.text ?? ""); }
    else if (m.type === "cancel") { this.proc?.kill(); }
    else if (m.type === "apply") { this.applyPatch(); }
    else if (m.type === "report") { this.openReport(); }
  }

  run(issueId: string, text = ""): void {
    const ws = this.workspace();
    if (!ws) { vscode.window.showErrorMessage("Verifix: open a folder first."); return; }
    const cfg = vscode.workspace.getConfiguration("verifix");
    const [cmd, ...base] = cfg.get<string[]>("command") ?? ["uv", "run", "verifix"];
    this.reportPath = path.join(ws, ".verifix", "runs", `${issueId || "latest"}.json`);
    fs.mkdirSync(path.dirname(this.reportPath), { recursive: true });
    const github = /^(https?:\/\/)?(www\.)?github\.com\/[\w.-]+\/[\w.-]+\/issues\/\d+|^#?\d+$/;
    const issueArgs: string[] = [];
    let tmpDescription = "";
    if (issueId) { issueArgs.push("--issue", issueId); }
    else if (github.test(text.trim())) { issueArgs.push("--issue", text.trim()); }
    else {
      tmpDescription = path.join(os.tmpdir(), `verifix-issue-${Date.now()}.txt`);
      fs.writeFileSync(tmpDescription, text);
      issueArgs.push("--description-file", tmpDescription);
    }
    const args = [...base, "run", "--repo", ws, ...issueArgs, "--events", "jsonl",
      "--report", this.reportPath, "--agent", cfg.get<string>("agent") ?? "groq",
      "--max-attempts", String(cfg.get<number>("maxAttempts") ?? 3),
      "--sandbox", cfg.get<string>("sandbox") ?? "local"];
    const fake = cfg.get<string>("fakePatches");
    if (fake) { args.push("--fake-patches", path.isAbsolute(fake) ? fake : path.join(ws, fake)); }

    this.finalDiff = "";
    this.post({ type: "reset" });
    this.proc?.kill();
    const proc = spawn(cmd, args, { cwd: this.projectDir() ?? ws });
    this.proc = proc;
    let buf = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      buf += chunk.toString();
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) { this.handleLine(line); }
      }
    });
    let stderr = "";
    proc.stderr.on("data", (c: Buffer) => { stderr += c.toString(); this.post({ type: "log", text: c.toString() }); });
    proc.on("error", (e) => this.post({ type: "error", message: `Could not start "${cmd}": ${e.message}` }));
    proc.on("close", (code, signal) => {
      if (tmpDescription) { fs.rmSync(tmpDescription, { force: true }); }
      if (proc !== this.proc) { return; }
      if (signal) { this.post({ type: "cancelled" }); }
      else if (code === 2 || (code !== 0 && code !== 1)) {
        this.post({ type: "error", message: stderr.trim().split("\n").slice(-3).join("\n") || `verifix exited with code ${code}` });
      }
    });
  }

  private handleLine(line: string): void {
    try {
      const ev = JSON.parse(line);
      if (ev.type === "run_finished") { this.finalDiff = ev.data.diff ?? ""; }
      this.post({ type: "event", event: ev });
    } catch { this.post({ type: "log", text: line + "\n" }); }
  }

  private applyPatch(): void {
    const ws = this.workspace();
    if (!ws || !this.finalDiff) { return; }
    const tmp = path.join(os.tmpdir(), `verifix-${Date.now()}.diff`);
    fs.writeFileSync(tmp, this.finalDiff);
    const r = spawnSync("git", ["apply", "--whitespace=nowarn", tmp], { cwd: ws, encoding: "utf8" });
    fs.unlinkSync(tmp);
    if (r.status === 0) { vscode.window.showInformationMessage("Verifix: patch applied."); this.post({ type: "applied" }); }
    else { vscode.window.showErrorMessage(`Verifix: could not apply patch: ${r.stderr}`); }
  }

  private async openReport(): Promise<void> {
    const htmlPath = this.reportPath.replace(/\.json$/, ".html");
    if (!this.reportPath || !fs.existsSync(htmlPath)) { return; }
    const panel = vscode.window.createWebviewPanel("verifix.report", "Verifix report", vscode.ViewColumn.Beside, {});
    panel.webview.html = fs.readFileSync(htmlPath, "utf8");
  }

  private html(webview: vscode.Webview): string {
    const media = (f: string) => webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, "media", f));
    const nonce = Math.random().toString(36).slice(2);
    return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
<link rel="stylesheet" href="${media("main.css")}"></head><body><div id="app"></div>
<script nonce="${nonce}" src="${media("main.js")}"></script></body></html>`;
  }
}

export function activate(ctx: vscode.ExtensionContext): void {
  const provider = new SidebarProvider(ctx);
  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider("verifix.sidebar", provider),
    vscode.commands.registerCommand("verifix.refreshIssues", () => provider.refreshIssues()),
    vscode.commands.registerCommand("verifix.run", () => vscode.commands.executeCommand("verifix.sidebar.focus")),
  );
}

export function deactivate(): void {}
