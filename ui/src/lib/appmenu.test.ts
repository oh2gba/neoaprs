// The engine's own menu in the app's window (lib/appmenu.ts): a right-click on the page shows
// none (no Back, no Reload); in a text field and on selected text it does (cut, copy, paste);
// the page's own menus open as before; in a browser nothing is changed.
import { afterEach, describe, expect, it, vi } from "vitest";
import { keepEngineMenuToText } from "@/lib/appmenu";

let undo: () => void = () => undefined;

afterEach(() => {
  undo();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

/** Put `html` in the page and return the element `selector` names. */
function place(html: string, selector: string): HTMLElement {
  document.body.innerHTML = html;
  return document.querySelector<HTMLElement>(selector) as HTMLElement;
}

/**
 * Right-click `target` at (`x`, `y`): true when the engine's menu would show (the event was not
 * prevented).
 */
function rightClick(target: Element, x = 10, y = 10): boolean {
  const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: x, clientY: y });
  return target.dispatchEvent(event);
}

/** A selection of text whose one rectangle is from (left, top) to (right, bottom). */
function selected(left: number, top: number, right: number, bottom: number): Selection {
  const rect = { left, top, right, bottom, width: right - left, height: bottom - top, x: left, y: top } as DOMRect;
  const range = { getClientRects: () => [rect] } as unknown as Range;
  return { isCollapsed: false, rangeCount: 1, getRangeAt: () => range } as unknown as Selection;
}

describe("in the app's window", () => {
  it("shows no engine menu on the page: a panel, a heading, a button, a link, a checkbox, the map", () => {
    undo = keepEngineMenuToText(window, true);
    const page = place(
      `<main><h2>Stations</h2><button>Send</button><a href="https://example.org/">link</a><input type="checkbox"><input type="radio"><select><option>a</option></select><div class="map"><canvas></canvas></div></main>`,
      "main",
    );
    for (const target of [page, ...page.querySelectorAll("*")]) expect(rightClick(target), target.tagName).toBe(false);
  });

  it("keeps it in a field the operator types into: a text, a search, a number, a textarea, an editable element and what is inside one", () => {
    undo = keepEngineMenuToText(window, true);
    place(
      `<form><input id="a"><input id="b" type="search"><input id="c" type="number"><input id="d" type="password"><textarea id="e"></textarea><div id="f" contenteditable="true"><b id="g">x</b></div><div id="h" contenteditable="false">y</div></form>`,
      "form",
    );
    for (const id of ["a", "b", "c", "d", "e", "f", "g"])
      expect(rightClick(document.getElementById(id) as Element), id).toBe(true);
    expect(rightClick(document.getElementById("h") as Element)).toBe(false);
  });

  it("keeps it on the selected text under the pointer only: beside the selection, or with none, the page has no menu", () => {
    undo = keepEngineMenuToText(window, true);
    const text = place(`<p>OH2GBA-9 heard 3 min ago</p>`, "p");
    const choose = vi.spyOn(window, "getSelection");
    choose.mockReturnValue(selected(0, 0, 100, 20));
    expect(rightClick(text, 50, 10)).toBe(true);
    expect(rightClick(text, 150, 10)).toBe(false);
    expect(rightClick(text, 50, 40)).toBe(false);
    choose.mockReturnValue({
      isCollapsed: true,
      rangeCount: 1,
      getRangeAt: () => ({ getClientRects: () => [] }),
    } as unknown as Selection);
    expect(rightClick(text, 50, 10)).toBe(false);
    choose.mockReturnValue(null);
    expect(rightClick(text, 50, 10)).toBe(false);
  });

  it("shows none on a link or a picture, also on its selected text: the engine puts Back, Reload and open in a new window there", () => {
    undo = keepEngineMenuToText(window, true);
    const link = place(`<p><a href="https://www.qrz.com/db/OH2GBA"><b>OH2GBA</b></a><img src="x.png"></p>`, "a");
    vi.spyOn(window, "getSelection").mockReturnValue(selected(0, 0, 100, 20));
    expect(rightClick(link, 50, 10)).toBe(false);
    expect(rightClick(link.querySelector("b") as Element, 50, 10)).toBe(false);
    expect(rightClick(document.querySelector("img") as Element, 50, 10)).toBe(false);
    expect(rightClick(link.parentElement as Element, 50, 10)).toBe(true);
  });

  it("is heard before the page's own menus, which still open (they keep the engine's away themselves), even one that stops the click there", () => {
    undo = keepEngineMenuToText(window, true);
    const row = place(`<table><tr><td>OH2GBA</td></tr></table>`, "td");
    const opened = vi.fn((event: MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
    });
    row.addEventListener("contextmenu", opened);
    expect(rightClick(row)).toBe(false);
    expect(opened).toHaveBeenCalledTimes(1);
    const quiet = place(`<div class="map"><canvas></canvas></div>`, "canvas");
    const stopsOnly = vi.fn((event: MouseEvent) => event.stopPropagation());
    quiet.addEventListener("contextmenu", stopsOnly);
    expect(rightClick(quiet)).toBe(false); // a handler that only stops the event does not let the engine's menu through
    expect(stopsOnly).toHaveBeenCalledTimes(1);
  });

  it("goes when it is taken away", () => {
    keepEngineMenuToText(window, true)();
    expect(rightClick(place(`<p>x</p>`, "p"))).toBe(true);
  });
});

describe("in a browser", () => {
  it("changes nothing: the menu is the user's", () => {
    undo = keepEngineMenuToText(window, false);
    const page = place(`<main><h2>Stations</h2><canvas></canvas></main>`, "main");
    for (const target of [page, ...page.querySelectorAll("*")]) expect(rightClick(target)).toBe(true);
  });
});

describe("which window it is", () => {
  it("is the page's own question: the window's address says #app, or said it when the window first loaded the page", () => {
    sessionStorage.clear();
    location.hash = "";
    undo = keepEngineMenuToText();
    expect(rightClick(place(`<p>x</p>`, "p"))).toBe(true);
    undo();
    location.hash = "#app";
    undo = keepEngineMenuToText();
    expect(rightClick(place(`<p>x</p>`, "p"))).toBe(false);
    location.hash = "";
    sessionStorage.clear();
  });
});
