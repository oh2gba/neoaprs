// Whether this page is the desktop app's window rather than a browser tab. The app
// (neoaprs/desktop) loads the page with the fragment `#app` (`links.window_url`); the page then
// shows no Server mark. The window remembers this in sessionStorage, so a reload without the
// fragment is still the app.
/**
 * The fragment the app's window adds to the page's address (`APP_MARK` in
 * neoaprs/desktop/links.py).
 */
const APP_FRAGMENT = "#app";
const REMEMBERED = "neoaprs-in-app";

/** The window's session store, or null where unusable (blocked, private mode). */
function store(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * True in the app's window: the fragment is `#app` now, or was when this window first loaded the
 * page.
 */
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

/** Whether the user agent says Macintosh (Qt's web engine and WKWebView on a Mac both do). */
const onMac = (agent: string): boolean => /Macintosh|Mac OS X/.test(agent);

/**
 * True in the app's window where the daemon's own alert announces a new message (it runs a command
 * on the computer the person is at; the default notification and sound work on Windows and Linux).
 * The Mac command has no program, so there the window keeps its own sound.
 */
export function daemonTells(hash: string = location.hash, memory: Storage | null = store(), agent: string = navigator.userAgent): boolean {
  return inApp(hash, memory) && !onMac(agent);
}
