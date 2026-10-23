import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";
import { useTabAlert } from "@/composables/useTabAlert";
import { useTitle } from "@/composables/useTitle";
import { DOT_ICON } from "@/lib/pagealert";
import { resetSeen, setSeen } from "@/test/fakealert";

const ORIGINAL = "data:image/svg+xml,original";
const icon = () => document.querySelector("link[rel~='icon']")?.getAttribute("href");

beforeEach(() => {
  vi.useFakeTimers();
  document.head.innerHTML = `<link rel="icon" href="${ORIGINAL}" />`;
  document.title = "NeoAPRS";
});
afterEach(() => {
  vi.useRealTimers();
  resetSeen();
  document.head.innerHTML = "";
});

function make() {
  const scope = effectScope();
  const unread = ref(0);
  const tab = scope.run(() => {
    const tab = useTabAlert();
    useTitle(unread, tab.shown);
    return tab;
  });
  if (tab === undefined) throw new Error("no scope");
  return { tab, scope, unread };
}

describe("useTabAlert", () => {
  it("alternates the title between the sender and the usual one, and puts a dot on the icon, while the page is hidden", async () => {
    setSeen(false);
    const { tab, scope } = make();
    tab.start("OH2DPN");
    await nextTick();
    expect(document.title).toBe("✉ OH2DPN");
    expect(icon()).toBe(DOT_ICON);
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(document.title).toBe("✉ OH2DPN");
    scope.stop();
  });

  it("keeps the count of messages not seen in the title between the beats", async () => {
    setSeen(false);
    const { tab, unread, scope } = make();
    unread.value = 2;
    tab.start("OH2DPN");
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(document.title).toBe("(2) NeoAPRS");
    scope.stop();
  });

  it("alerts for an unfocused page too, and stops when the page is seen again", async () => {
    setSeen(false);
    const { tab, scope } = make();
    tab.start("OH2DPN");
    await nextTick();
    expect(document.title).toBe("✉ OH2DPN");
    setSeen(true);
    window.dispatchEvent(new Event("focus"));
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    expect(icon()).toBe(ORIGINAL);
    vi.advanceTimersByTime(5000);
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    scope.stop();
  });

  it("stops when the tab is shown again (visibilitychange)", async () => {
    setSeen(false);
    const { tab, scope } = make();
    tab.start("OH2DPN");
    setSeen(true);
    document.dispatchEvent(new Event("visibilitychange"));
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    expect(icon()).toBe(ORIGINAL);
    scope.stop();
  });

  it("does not alert a page that is in front", async () => {
    setSeen(true);
    const { tab, scope } = make();
    tab.start("OH2DPN");
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    expect(icon()).toBe(ORIGINAL);
    scope.stop();
  });

  it("shows a test for a few seconds on a page in front, then lets go", async () => {
    setSeen(true);
    const { tab, scope } = make();
    tab.start("OH2GBA-7", true);
    await nextTick();
    expect(document.title).toBe("✉ OH2GBA-7");
    vi.advanceTimersByTime(4000);
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
    expect(icon()).toBe(ORIGINAL);
    scope.stop();
  });

  it("makes an icon for a page that has none, and takes it away again", () => {
    document.head.innerHTML = "";
    setSeen(false);
    const { tab, scope } = make();
    tab.start("OH2DPN");
    expect(icon()).toBe(DOT_ICON);
    tab.stop();
    expect(document.querySelector("link[rel~='icon']")).toBeNull();
    scope.stop();
  });
});
