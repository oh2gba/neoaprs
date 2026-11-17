// The web engine's own menu in the desktop app's window: the right button (or the menu key) shows it only where it has something to cut, copy or paste, a text field and the text that is selected under the pointer (not on a link or a picture, where the engine adds its page and link items to Copy);
// everywhere else (its Back, Forward, Reload, View source and the like, which have no place in the app) it is not shown. The page's own menus (the map's, a row's copy menu) are as they are: the rule is heard
// first (the capture of the window), takes nothing from them and is not stopped by them. One rule for both shells and every engine (Qt's Chromium, WebView2, WebKitGTK), set by main.ts as the page starts; in a browser
// the menu is the user's and nothing is done (lib/shell.ts `inApp`). The loading page the window shows before this page answers has no menu at all (neoaprs/desktop/loading.py).
import { inApp } from "@/lib/shell";

/** Input types that take typed text, where cut, copy and paste are at home. */
const TEXT_INPUTS = new Set(["text", "search", "email", "url", "tel", "password", "number"]);

/** Whether `target` is in a field the operator types into: a textarea, an input of text, an editable element. */
function inTextField(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const field = target.closest("input, textarea, [contenteditable]:not([contenteditable='false'])");
  if (field instanceof HTMLInputElement) return TEXT_INPUTS.has(field.type);
  return field !== null;
}

/** Whether the point (`x`, `y`, the window's pixels) is on text that `selection` holds. */
function onSelection(selection: Selection | null, x: number, y: number): boolean {
  if (selection === null || selection.isCollapsed) return false;
  for (let i = 0; i < selection.rangeCount; i++) {
    const range = selection.getRangeAt(i);
    const rects = typeof range.getClientRects === "function" ? [...range.getClientRects()] : [];
    if (rects.some((r) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom)) return true;
  }
  return false;
}

/** Whether `target` is a link or a picture: there the engine's menu is its page and link items (Back, Reload, open in a new window, save the image), selected text or not. */
function onLinkOrMedia(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("a[href], img, video, audio") !== null;
}

/** Whether the engine's menu may show for this right-click: only in a text field or on the selected text that is not a link's. */
function engineMenuWanted(event: MouseEvent, selection: Selection | null): boolean {
  if (inTextField(event.target)) return true;
  return !onLinkOrMedia(event.target) && onSelection(selection, event.clientX, event.clientY);
}

/** In the app's window: from now on a right-click shows the engine's menu only where `engineMenuWanted` says. The function returned takes the rule away (the tests). */
export function keepEngineMenuToText(target: Window = window, app: boolean = inApp()): () => void {
  if (!app) return () => undefined;
  const listener = (event: MouseEvent): void => {
    if (!engineMenuWanted(event, target.getSelection())) event.preventDefault();
  };
  target.addEventListener("contextmenu", listener, true);
  return () => target.removeEventListener("contextmenu", listener, true);
}
