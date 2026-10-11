// Copies a sample repo into .workspaces/<name> so Apply Patch changes a throwaway copy, never the tracked fixtures.
const fs = require("fs"), path = require("path");
const name = process.argv[2];
if (!name) { console.error("usage: prepare-workspace.js <fixture name>"); process.exit(2); }
const root = path.resolve(__dirname, "../..");
const src = path.join(root, "tests/fixtures", name), dest = path.join(root, ".workspaces", name);
if (!fs.existsSync(src)) { console.error(`no such fixture: ${src}`); process.exit(2); }
fs.rmSync(dest, { recursive: true, force: true });
fs.cpSync(src, dest, { recursive: true, filter: (s) => !/[\\/](\.verifix[\\/](runs|cache)|__pycache__)/.test(s) && !s.endsWith("runs.db") });
console.log(`fresh workspace: ${dest}`);
