// A page built for another version of the protocol than the daemon speaks loads itself again, once: a second mismatch (the daemon serves a page that is older than itself) would be a loop.

const KEY = "NeoAPRS.reloaded";

/** Loads the page again unless it already did for this tab; true when it did. */
export function reloadOnce(): boolean {
  try {
    if (sessionStorage.getItem(KEY) !== null) return false;
    sessionStorage.setItem(KEY, "1");
  } catch {
    return false;
  }
  location.reload();
  return true;
}
