// Whether this page is the desktop app's window rather than a browser tab. The app (neoaprs/desktop) loads the daemon's page with the fragment `#app` (`links.window_url`); in it page and daemon are one, so the page shows no
// Server mark. The window remembers it for as long as it lives (sessionStorage), so a reload or a load of the page without the fragment in the app's window is still the app.
/** The fragment the app's window adds to the page's address (the same text as `APP_MARK` of neoaprs/desktop/links.py). */
const APP_FRAGMENT = "#app";
const REMEMBERED = "neoaprs-in-app";

/** The window's own store, or null where it cannot be used (blocked, private mode). */
function store(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** True in the app's window: the fragment is `#app` now, or was when this window first loaded the page. `hash` is the page's own (`location.hash`). */
export function inApp(hash: string = location.hash, memory: Storage | null = store()): boolean {
  try {
    if (hash === APP_FRAGMENT) {
      memory?.setItem(REMEMBERED, "1");
      return true;
    }
    return memory?.getItem(REMEMBERED) === "1";
  } catch {
    return hash === APP_FRAGMENT;
  }
}

/** The browser engine's own word for the system it runs on says Macintosh (Qt's web engine and WKWebView on a Mac both do). */
const onMac = (agent: string): boolean => /Macintosh|Mac OS X/.test(agent);

/** True in the app's window where the daemon's own alert is the one that tells of a new message: it runs a command on the very computer the person is at, and its default (a notification and a sound) does both on Windows and on a Linux desktop. The Mac has no program in that command, so there the window keeps its own sound. */
export function daemonTells(hash: string = location.hash, memory: Storage | null = store(), agent: string = navigator.userAgent): boolean {
  return inApp(hash, memory) && !onMac(agent);
}
