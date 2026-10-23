// A page built for another version of NeoAPRS than the daemon's loads itself again when the daemon says hello: after an update, a page that was left open picks up the new one by itself (the shell index.html is served no-cache and the files of assets/ carry
// the hash of their content, so a load fetches the new ones). It happens once for each version of the daemon: the guard is the version a load was made for, in the tab's session storage. A hello that matches clears it, so that the next update loads
// again; one that still differs after the load (a daemon that serves a page older than itself) does not load again and says nothing. The same code runs in the desktop app's window, which is the page in the system's web engine.
import { PAGE_VERSION } from "@/lib/build";
import { PROTOCOL } from "@/protocol/lists";

const KEY = "NeoAPRS.reloadedFor";

export interface DaemonHello {
  protocol: number;
  version: string;
}

/** What a hello led to: the page is the daemon's (`same`), it loads itself again (`reload`), or it has done so for this version already (`stale`). */
export type Reload = "same" | "reload" | "stale";

/** Looks at a hello and loads the page again when it was built for another version or protocol; the last two arguments are for the tests. */
export function reloadForDaemon(
  hello: DaemonHello,
  page: DaemonHello = { protocol: PROTOCOL, version: PAGE_VERSION },
  reload: () => void = () => location.reload(),
): Reload {
  try {
    if (hello.protocol === page.protocol && hello.version === page.version) {
      sessionStorage.removeItem(KEY);
      return "same";
    }
    const guard = `${hello.version}/${hello.protocol}`;
    if (sessionStorage.getItem(KEY) === guard) return "stale";
    sessionStorage.setItem(KEY, guard);
  } catch {
    return "stale"; // no storage, no way to tell a second load from the first: carry on with this page
  }
  reload();
  return "reload";
}
