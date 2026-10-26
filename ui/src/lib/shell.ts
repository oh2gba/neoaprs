// Whether this page is the desktop app's window rather than a browser tab. The app (neoaprs/desktop) loads the daemon's page with the fragment `#app` (`links.window_url`); in it page and daemon are one, so the page shows no Daemon mark.
/** The fragment the app's window adds to the page's address (the same text as `APP_MARK` of neoaprs/desktop/links.py). */
const APP_FRAGMENT = "#app";

/** True in the app's window. `hash` is the page's own (`location.hash`). */
export const inApp = (hash: string = location.hash): boolean => hash === APP_FRAGMENT;
