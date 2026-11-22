import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref, shallowReactive, shallowRef, type Ref } from "vue";
import { useBulletins } from "@/composables/useBulletins";
import { useConversations } from "@/composables/useConversations";
import { useEmail } from "@/composables/useEmail";
import { usePanel } from "@/composables/usePanel";
import { useSkeds } from "@/composables/useSkeds";
import { keyLink, takeKey } from "@/lib/access";
import type * as firststart from "@/lib/firststart";
import { heldNothing, systemEngine, whenLoaded } from "@/lib/firststart";
import { EMAIL_GATEWAY } from "@/lib/messages";
import type { BulletinRow, MessageRow, SkedsState } from "@/protocol/protocol";
import { ago, bulletin, incoming, sked, skedsState } from "@/test/fixtures";

// Whether the window's store was new when the page started is fixed when lib/firststart.ts is
// first evaluated; here the test sets it (`startedNew`) and the rest of the module is real.
const startedNew = vi.hoisted(() => ({ value: true }));
vi.mock("@/lib/firststart", async (importOriginal) => {
  const real = await importOriginal<typeof firststart>();
  return {
    ...real,
    seenAtStart: (loaded: Readonly<Ref<boolean>>, markAll: () => void): void => {
      if (startedNew.value) real.whenLoaded(loaded, markAll);
    },
  };
});

// The user agents of the four windows (WebKitGTK and WKWebView as pywebview leaves them, Qt 6's
// QtWebEngine, Edge's WebView2).
const WEBKITGTK =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";
const WKWEBVIEW = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)";
const QT_WINDOW =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.12.0 Chrome/130.0.6723.192 Safari/537.36";
const WEBVIEW2 =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0";
// A phone that read the Settings, Web page code: Safari on an iPhone is WebKit too and names no
// Chrome.
const IPHONE =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";

const table = (...rows: MessageRow[]) => shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
const board = (...rows: BulletinRow[]) => shallowReactive(new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r])));

/**
 * `make` inside a component, with the panel as `usePanel` makes it and the Stations tab in
 * front.
 */
function inComponent<T>(make: (panel: ReturnType<typeof usePanel>) => T): T {
  let made: T | undefined;
  mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        panel.show("stations");
        made = make(panel);
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return made;
}

/**
 * The daemon telling the messages whole, as useDaemon's `fill` does: the rows, then the mark
 * that they are all there.
 */
function fill(into: Map<string, MessageRow>, loaded: Ref<boolean>, ...rows: MessageRow[]): void {
  for (const row of rows) into.set(String(row.id), row);
  loaded.value = true;
}

beforeEach(() => {
  localStorage.clear();
  startedNew.value = true;
});
afterEach(() => {
  sessionStorage.clear();
  history.replaceState(null, "", location.pathname);
});

describe("the window's store at the start", () => {
  it("held nothing when no key of the page's is there, and is no new store when it cannot be read", () => {
    expect(heldNothing(() => localStorage)).toBe(true);
    localStorage.setItem("someone-else", "1");
    expect(heldNothing(() => localStorage)).toBe(true);
    localStorage.setItem("NeoAPRS.language", "fi");
    expect(heldNothing(() => localStorage)).toBe(false);
    expect(heldNothing(() => null)).toBe(false);
    expect(
      heldNothing(() => {
        throw new Error("blocked");
      }),
    ).toBe(false);
  });

  it("is new only in the app's window on the system's engine whose store held nothing of the page's when the module was first evaluated", async () => {
    const cases: [string, boolean, string, boolean][] = [
      ["#app", false, WEBKITGTK, true],
      ["#app", true, WEBKITGTK, false],
      ["", false, WEBKITGTK, false],
      ["#app", false, QT_WINDOW, false],
      ["#app", false, WEBVIEW2, false],
    ];
    for (const [hash, stored, userAgent, expected] of cases) {
      localStorage.clear();
      sessionStorage.clear();
      if (stored) localStorage.setItem("NeoAPRS.panelwidth", "420");
      history.replaceState(null, "", hash === "" ? location.pathname : hash);
      const agent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue(userAgent);
      vi.resetModules();
      const evaluated = await vi.importActual<typeof firststart>("@/lib/firststart");
      agent.mockRestore();
      const markAll = vi.fn();
      evaluated.seenAtStart(ref(true), markAll);
      expect(markAll.mock.calls.length, `${hash} ${String(stored)} ${userAgent}`).toBe(expected ? 1 : 0);
    }
  });

  it("is no new window on a phone that opens the address of the phone code with a new store, and taking its key leaves the window's #app and the store alone", async () => {
    const link = keyLink(`${location.origin}/`, "k7m2-x9pq-4hrt");
    localStorage.clear();
    sessionStorage.clear();
    history.replaceState(null, "", link.slice(link.indexOf("#")));
    const agent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue(IPHONE);
    vi.resetModules();
    const evaluated = await vi.importActual<typeof firststart>("@/lib/firststart");
    agent.mockRestore();
    const markAll = vi.fn();
    evaluated.seenAtStart(ref(true), markAll);
    // a phone's unread messages stay unread: it is a browser, not the app's window
    expect(markAll).not.toHaveBeenCalled();
    expect(takeKey()).toBe("k7m2-x9pq-4hrt");
    // the key is in no address and in no store
    expect([location.hash, heldNothing(() => localStorage)]).toEqual(["", true]);
    history.replaceState(null, "", "#app");
    expect([takeKey(), location.hash]).toEqual(["", "#app"]);
  });

  it("takes WebKitGTK and WKWebView for the system's engine, and Qt's window and WebView2 for Chromium", () => {
    expect(systemEngine(WEBKITGTK)).toBe(true);
    expect(systemEngine(WKWEBVIEW)).toBe(true);
    expect(systemEngine(QT_WINDOW)).toBe(false);
    expect(systemEngine(WEBVIEW2)).toBe(false);
  });

  it("runs what waits for the rows once, when they first are all there", async () => {
    const loaded = ref(false);
    const run = vi.fn();
    whenLoaded(loaded, run);
    expect(run).not.toHaveBeenCalled();
    loaded.value = true;
    await nextTick();
    loaded.value = false;
    await nextTick();
    loaded.value = true;
    await nextTick();
    expect(run).toHaveBeenCalledTimes(1);
    whenLoaded(loaded, run);
    expect(run).toHaveBeenCalledTimes(2);
  });
});

describe("a new window store: what the daemon tells first is seen", () => {
  it("marks every conversation read up to its newest message, and a message that comes after is unread", async () => {
    const messages = table();
    const loaded = ref(false);
    const talk = useConversations(messages, ref(false), ref(false), loaded);
    fill(messages, loaded, incoming(2, "OH2RDG"), incoming(3, "OH2XYZ"), incoming(4, "OH2XYZ"));
    await flushPromises();
    expect(talk.unread.value).toBe(0);
    expect(localStorage.getItem("NeoAPRS.read.OH2XYZ")).toBe("4");
    messages.set("5", incoming(5, "OH2RDG"));
    await flushPromises();
    expect(talk.unread.value).toBe(1);
  });

  it("leaves the marks as they are in a store that was not new", async () => {
    startedNew.value = false;
    const messages = table();
    const loaded = ref(false);
    const talk = useConversations(messages, ref(false), ref(false), loaded);
    fill(messages, loaded, incoming(2, "OH2RDG"), incoming(3, "OH2XYZ"));
    await flushPromises();
    expect(talk.unread.value).toBe(2);
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBeNull();
  });

  it("marks the mail of the gateway seen, and none of it bold", async () => {
    const messages = table();
    const loaded = ref(false);
    const mail = inComponent((panel) => useEmail(messages, panel, () => true, loaded));
    fill(messages, loaded, incoming(7, EMAIL_GATEWAY), incoming(9, EMAIL_GATEWAY));
    await flushPromises();
    expect(mail.unread.value).toBe(0);
    expect(mail.freshAfter.value).toBe(9);
    messages.set("10", incoming(10, EMAIL_GATEWAY));
    await flushPromises();
    expect(mail.unread.value).toBe(1);
  });

  it("takes the bulletins of the first board as seen, and counts one that comes after", async () => {
    const bulletins = board();
    const loaded = ref(false);
    const { fresh } = inComponent((panel) => useBulletins(bulletins, panel, loaded));
    bulletins.set("OH2XYZ/BLN1", bulletin("BLN1", { first_heard: ago(600) }));
    bulletins.set("OH2XYZ/BLN2", bulletin("BLN2", { first_heard: ago(300) }));
    loaded.value = true;
    await nextTick();
    expect(fresh.value).toBe(0);
    bulletins.set("OH2XYZ/BLN3", bulletin("BLN3", { first_heard: ago(60) }));
    await nextTick();
    expect(fresh.value).toBe(1);
  });

  it("takes the skeds of the first board told as seen, and counts one that comes after", async () => {
    const topic = shallowRef<SkedsState | null>(null);
    const { fresh } = inComponent((panel) => useSkeds(topic, panel, () => true, ref(true)));
    topic.value = skedsState([sked("a"), sked("b")]);
    await nextTick();
    expect(fresh.value).toBe(0);
    topic.value = skedsState([sked("a"), sked("b"), sked("c")]);
    await nextTick();
    expect(fresh.value).toBe(1);
  });
});
