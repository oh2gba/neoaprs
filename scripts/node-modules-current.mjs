// Exit 0 when ui/node_modules is what ui/package-lock.json says (the same packages in the same versions; a package marked optional, which npm leaves out for another platform, may be missing),
// else 1. npm writes the list of what it installed to node_modules/.package-lock.json. Used by scripts/build-page and scripts/worktree-setup, to run `npm ci` (which deletes node_modules first) only when it is needed.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ui = join(dirname(fileURLToPath(import.meta.url)), "..", "ui");
const hiddenPath = join(ui, "node_modules", ".package-lock.json");
if (!existsSync(hiddenPath)) process.exit(1);
const wanted = JSON.parse(readFileSync(join(ui, "package-lock.json"), "utf8")).packages ?? {};
const installed = JSON.parse(readFileSync(hiddenPath, "utf8")).packages ?? {};
for (const [path, pkg] of Object.entries(wanted)) {
  if (path === "" || pkg.optional) continue;
  if (installed[path]?.version !== pkg.version) process.exit(1);
}
for (const [path, pkg] of Object.entries(installed)) {
  if (wanted[path]?.version !== pkg.version) process.exit(1);
}
