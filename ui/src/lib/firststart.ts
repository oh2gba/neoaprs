// Whether this page is the desktop app's window on a store of its own that was new when the page started: a window whose web engine changed (the Linux and Mac window, from Qt's Chromium to the system's
// own engine) starts with nothing of what the page remembered, so the messages, bulletins and skeds already there would all count as new once. When it is so, the composables that own the marks of what
// was seen (useConversations, useEmail, useBulletins, useSkeds) take what the daemon tells first as seen. The store is looked at when this module is first evaluated: main.ts imports it before anything
// that may write to the store. A store that cannot be read is no new store: the page behaves as it always has. Only the system's own engine counts (WebKitGTK, WKWebView): Qt's window and Windows' WebView2
// are Chromium, whose store a user has lost only by removing it, and there the messages unread are left unread.
import { watch, type Ref } from "vue";
import { inApp } from "@/lib/shell";
import { STORE_PREFIX } from "@/lib/storage";

/** True when `storage` holds no key of the page's (none starting with `STORE_PREFIX`); false when it holds one or cannot be read. */
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

/** True for the system's own web engine, false for Chromium (Qt's window and WebView2 name Chrome in the user agent; WebKitGTK and WKWebView do not). */
export function systemEngine(userAgent: string): boolean {
  return !/\bChrome\//.test(userAgent);
}

/** True in the app's window on the system's own engine whose store held nothing of the page's when the page started. */
const NEW_AT_START = heldNothing(() => localStorage) && inApp() && systemEngine(navigator.userAgent);

/** Runs `run` once, when `loaded` first holds (at once when it holds already). */
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

/** Takes what the daemon tells first as seen (`markAll`, once the rows have come whole: `loaded`) when the window's store was new at the start; else does nothing. */
export function seenAtStart(loaded: Readonly<Ref<boolean>>, markAll: () => void): void {
  if (NEW_AT_START) whenLoaded(loaded, markAll);
}
