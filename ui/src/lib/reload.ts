// A page and a daemon of another protocol or another build of the page cannot work together. The
// page knows its own protocol and build (the name of the main script its index.html loaded), not
// the NeoAPRS version: it compares those two with what the daemon says in hello. After an update, a
// page left open (or kept in a browser cache) reloads itself once for each daemon it meets: the
// guard records what a load was made for, in the tab's session storage (index.html is served
// no-cache and the files of assets/ carry a content hash, so a load fetches the new ones).
// A hello that matches clears the guard, so the next update reloads again. A hello that still
// differs after the load gives `stale`: the page does not run against that daemon, shows
// components/VersionMismatch.vue and keeps the socket closed.
// The same code runs in the desktop app's window, which is the page in the system's web engine.
import { pageBuild } from "@/lib/build";
import { STORE_PREFIX } from "@/lib/storage";
import { PROTOCOL } from "@/protocol/lists";

const KEY = `${STORE_PREFIX}reloadedFor`;

export interface DaemonHello {
  protocol: number;
  version: string;
  // The build of the page (the name of its main script); empty or missing when not known, and then
  // not compared.
  page?: string;
}

/** What the page is: its protocol and build (empty in development and in tests, and then not
 * compared). */
export interface PageIdentity {
  protocol: number;
  page: string;
}

/** What a hello led to: the page is the daemon's (`same`), it reloads (`reload`), or it already did
 * for this daemon or cannot tell (`stale`). */
export type Reload = "same" | "reload" | "stale";

/** The two sides of a mismatch as the notice shows them: `build/protocol` of the page, `version
 * build/protocol` of the daemon. Identifiers, not words. */
export interface Mismatch {
  page: string;
  neoaprs: string;
}

export function currentPage(): PageIdentity {
  return { protocol: PROTOCOL, page: pageBuild() };
}

/** Whether the page and the daemon that sent this hello go together. Only the protocol and build
 * are compared, never the NeoAPRS version. */
export function matches(hello: DaemonHello, page: PageIdentity = currentPage()): boolean {
  const sameBuild = !hello.page || !page.page || hello.page === page.page;
  return hello.protocol === page.protocol && sameBuild;
}

export function describeMismatch(hello: DaemonHello, page: PageIdentity = currentPage()): Mismatch {
  return {
    page: `${page.page || "-"}/${page.protocol}`,
    neoaprs: `${hello.version}, ${hello.page || "-"}/${hello.protocol}`,
  };
}

/** Looks at a hello and reloads the page when the daemon has another protocol or build; the last
 * two arguments are for the tests. */
export function reloadForDaemon(
  hello: DaemonHello,
  page: PageIdentity = currentPage(),
  reload: () => void = () => location.reload(),
): Reload {
  try {
    if (matches(hello, page)) {
      sessionStorage.removeItem(KEY);
      return "same";
    }
    const guard = `${hello.version}/${hello.protocol}/${hello.page ?? ""}`;
    if (sessionStorage.getItem(KEY) === guard) return "stale";
    sessionStorage.setItem(KEY, guard);
  } catch {
    // Without storage a second load cannot be told from the first, and reloading could go on
    // forever.
    return "stale";
  }
  reload();
  return "reload";
}
