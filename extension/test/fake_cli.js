// Stand-in for the verifix CLI: records its arguments and prints canned JSONL events.
const fs = require("fs");
const args = process.argv.slice(2);
fs.appendFileSync(process.env.FAKE_CLI_LOG, JSON.stringify({ args, client: process.env.VERIFIX_CLIENT }) + "\n");
const out = (type, data) => console.log(JSON.stringify({ v: 1, ts: 0, type, data }));
const value = (flag) => args[args.indexOf(flag) + 1];
if (args.includes("understand")) {
  const file = args.includes("--description-file") ? value("--description-file") : "";
  const text = file ? fs.readFileSync(file, "utf8") : value("--issue");
  out("understanding_issue", { source: file ? "text" : "github" });
  out("issue_understood", { issue_id: "adhoc-1", title: `Understood: ${text}`, unclear: "", requirements: [], acceptance_criteria: [] });
} else if (args.includes("run")) {
  out("run_started", { max_attempts: 3 });
  out("issue_loaded", { issue_id: value("--issue") || "?", title: "t" });
  out("run_finished", { decision: "verified", attempts: 1, score: 1, diff: "" });
}
