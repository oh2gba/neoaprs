// Whether this page is the desktop app's window on a web-engine store that was new when the page
// started. Such a window (the Linux and Mac app on the system's own engine) starts with nothing the
// page remembered, so messages, bulletins and skeds already there would all count as new once.
// Then the composables that keep the seen marks (useConversations, useEmail, useBulletins,
// useSkeds) take what the daemon tells first as seen. The store is checked when this module is
// first evaluated; main.ts imports it before anything that writes to the store. An unreadable
// store is not new. Only the system's engine counts (WebKitGTK, WKWebView), not Chromium
// (Qt, WebView2), whose store is lost only by removing it.
import { watch, type Ref } from "vue";
import { inApp } from "@/lib/shell";
import { STORE_PREFIX } from "@/lib/storage";

/** True when `storage` holds no key with `STORE_PREFIX`; false if it does or cannot be read. */
export function heldNothing(storage: () => Storage | null): boolean {
  try {
    const store = storage();
    if (store === null) return false;
    for (let i = 0; i < store.length; i++) if (store.key(i)?.startsWith(STORE_PREFIX)) return false;
    return true;
  } catch {
    return false;
  }
}

/** True for the system's web engine, false for Chromium (which names Chrome in the user agent). */
export function systemEngine(userAgent: string): boolean {
  return !/\bChrome\//.test(userAgent);
}

/** True in the app's window on the system's engine when its store held nothing at start. */
const NEW_AT_START = heldNothing(() => localStorage) && inApp() && systemEngine(navigator.userAgent);

/** Run `run` once, when `loaded` first holds (at once if it already does). */
export function whenLoaded(loaded: Readonly<Ref<boolean>>, run: () => void): void {
  if (loaded.value) {
    run();
    return;
  }
  const stop = watch(loaded, (now) => {
    if (!now) return;
    stop();
    run();
  });
}

/**
 * Mark what the daemon tells first as seen (`markAll`, once `loaded`) if the store was new at
 * start.
 */
export function seenAtStart(loaded: Readonly<Ref<boolean>>, markAll: () => void): void {
  if (NEW_AT_START) whenLoaded(loaded, markAll);
}
