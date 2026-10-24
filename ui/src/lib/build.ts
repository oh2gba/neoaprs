// The version of NeoAPRS this page was built with (VERSION of neoaprs/__init__.py, put in by vite.config.ts): a daemon that says another one has been updated, and the page loads itself again (lib/reload.ts).
export const PAGE_VERSION: string = __PAGE_VERSION__;

/** The build of this page: the name of the main script its index.html loaded (`index-<hash>.js` of assets/), as the daemon names the page it serves in hello; empty in development and in the tests. */
export function pageBuild(doc: Document = document): string {
  for (const script of Array.from(doc.querySelectorAll<HTMLScriptElement>("script[type=module][src]"))) {
    const found = /assets\/(index-[\w-]+\.js)/.exec(script.getAttribute("src") ?? "");
    if (found?.[1]) return found[1];
  }
  return "";
}
