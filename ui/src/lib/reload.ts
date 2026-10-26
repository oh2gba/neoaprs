// A page and a daemon of another protocol or another build of the page cannot work together: the page expects rows with fields the daemon does not send, or the daemon sends what the page cannot read. The page knows its own
// protocol and its own build (the name of the main script its index.html loaded) and no version of NeoAPRS: it compares those two with what the daemon says in hello. After an update, a page left open (or one a browser kept in its cache) loads itself again
// by itself, once for each daemon it meets: the guard is what a load was made for, in the tab's session storage (index.html is served no-cache and the files of assets/ carry the hash of their content, so a load fetches the new ones).
// A hello that matches clears it, so that the next update loads again. A hello that still differs after the load gives `stale`: the page does not run against that daemon, it says so (components/VersionMismatch.vue) and keeps the socket closed.
// The same code runs in the desktop app's window, which is the page in the system's web engine.
import { pageBuild } from "@/lib/build";
import { PROTOCOL } from "@/protocol/lists";

const KEY = "NeoAPRS.reloadedFor";

export interface DaemonHello {
  protocol: number;
  version: string;
  page?: string; // the build of the page (the name of its main script); empty or missing when not known, and then not compared
}

/** What the page is: its protocol and its build (empty in development and in the tests, and then not compared). */
export interface PageIdentity {
  protocol: number;
  page: string;
}

/** What a hello led to: the page is the daemon's (`same`), it loads itself again (`reload`), or it did so for this daemon already, or cannot tell (`stale`). */
export type Reload = "same" | "reload" | "stale";

/** The two sides of a mismatch as the notice shows them: `build/protocol` of the page, `version build/protocol` of the daemon. Identifiers, not words. */
export interface Mismatch {
  page: string;
  neoaprs: string;
}

export function currentPage(): PageIdentity {
  return { protocol: PROTOCOL, page: pageBuild() };
}

/** Do the page and the daemon that sent this hello go together? Only the protocol and the build are compared, never the version of NeoAPRS: a release that changed nothing of the page leaves them the same. */
export function matches(hello: DaemonHello, page: PageIdentity = currentPage()): boolean {
  const sameBuild = !hello.page || !page.page || hello.page === page.page;
  return hello.protocol === page.protocol && sameBuild;
}

export function describeMismatch(hello: DaemonHello, page: PageIdentity = currentPage()): Mismatch {
  return { page: `${page.page || "-"}/${page.protocol}`, neoaprs: `${hello.version}, ${hello.page || "-"}/${hello.protocol}` };
}

/** Looks at a hello and loads the page again when the daemon is another protocol or serves another build; the last two arguments are for the tests. */
export function reloadForDaemon(hello: DaemonHello, page: PageIdentity = currentPage(), reload: () => void = () => location.reload()): Reload {
  try {
    if (matches(hello, page)) {
      sessionStorage.removeItem(KEY);
      return "same";
    }
    const guard = `${hello.version}/${hello.protocol}/${hello.page ?? ""}`;
    if (sessionStorage.getItem(KEY) === guard) return "stale";
    sessionStorage.setItem(KEY, guard);
  } catch {
    return "stale"; // no storage, no way to tell a second load from the first: no load by itself (it could go on for ever), the notice has a button
  }
  reload();
  return "reload";
}
