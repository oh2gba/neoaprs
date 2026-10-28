import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap } from "@/test/fakemap";
import { open, useAppHarness } from "@/test/app";

useAppHarness();

const bar = () => document.querySelector<HTMLElement>(".replaybar");

async function askForReplay(): Promise<void> {
  FakeMap.last().fire("contextmenu", {
    lngLat: { lat: 60.1, lng: 24.9 },
    point: { x: 10, y: 10 },
    originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
  });
  await flushPromises();
  document.querySelector<HTMLElement>(".mapmenu [role='menuitem'][data-item='replay']")?.click();
  await flushPromises();
}

describe("App: the replay of the map", () => {
  it("opens from the map's menu, asks the daemon for the span, and closes with Esc", async () => {
    const { wrapper, socket } = await open();
    expect(bar()).toBeNull();
    await askForReplay();
    expect(bar()).not.toBeNull();
    expect(socket.sent).toContainEqual({ cmd: "position_history", hours: 3 });
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await flushPromises();
    expect(bar()).toBeNull();
    wrapper.unmount();
  });

  it("closes with its cross, and is not open when the page comes back", async () => {
    const first = await open();
    await askForReplay();
    bar()?.querySelector<HTMLElement>(".replay-close")?.click();
    await flushPromises();
    expect(bar()).toBeNull();
    await askForReplay();
    first.wrapper.unmount();
    await open();
    expect(bar()).toBeNull();
  });
});
