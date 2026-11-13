import "@/test/mockmap";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap } from "@/test/fakemap";
import { open, useAppHarness } from "@/test/app";
import { hfState } from "@/test/fixtures";

const harness = useAppHarness();

const card = () => document.querySelector<HTMLElement>(".monitorcard");
const item = () => document.querySelector<HTMLElement>(".mapmenu [role='menuitem'][data-item='monitor']");

beforeEach(() => {
  const context = new Proxy(
    {},
    {
      get: (_t, name: string) =>
        name === "createImageData"
          ? (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) })
          : name === "measureText"
            ? () => ({ width: 10 })
            : () => undefined,
      set: () => true,
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
});
afterEach(() => vi.restoreAllMocks());

async function rightClick(): Promise<void> {
  FakeMap.last().fire("contextmenu", {
    lngLat: { lat: 60.1, lng: 24.9 },
    point: { x: 10, y: 10 },
    originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
  });
  await flushPromises();
}

const scoped = (socket: Awaited<ReturnType<typeof open>>["socket"]) => {
  const state = hfState();
  socket.say({ type: "state", topic: "hf", rev: 0, value: { ...state, modem: { ...state.modem!, scope: true } } });
};
const statsCard = () => document.querySelector<HTMLElement>(".statscard");
const menuItem = (name: string) => document.querySelector<HTMLElement>(`.mapmenu [role='menuitem'][data-item='${name}']`);
const escape = async (): Promise<void> => {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  await flushPromises();
};

describe("App: the monitor card", () => {
  it("is in the map's menu only while the HF radio has a scope, opens the card, asks for the rows, closes with Esc and is remembered", async () => {
    const { wrapper, socket } = await open();
    await rightClick();
    expect(item()).toBeNull();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    const state = hfState();
    socket.say({ type: "state", topic: "hf", rev: 0, value: { ...state, modem: { ...state.modem!, scope: true } } });
    await flushPromises();
    await rightClick();
    expect(item()).not.toBeNull();
    item()?.click();
    await flushPromises();
    expect(card()).not.toBeNull();
    expect(socket.sent).toContainEqual({ cmd: "hf_scope", on: true });
    expect(localStorage.getItem("NeoAPRS.monitor")).toBe("open");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await flushPromises();
    expect(card()).toBeNull();
    expect(socket.sent.at(-1)).toEqual({ cmd: "hf_scope", on: false });
    expect(localStorage.getItem("NeoAPRS.monitor")).toBe("closed");
    wrapper.unmount();
  });

  it("comes back with the page when it was left open, once the radio has said it has a scope, and its cross closes it", async () => {
    localStorage.setItem("NeoAPRS.monitor", "open");
    const { socket } = await open();
    expect(card()).toBeNull();
    const state = hfState();
    socket.say({ type: "state", topic: "hf", rev: 0, value: { ...state, modem: { ...state.modem!, scope: true } } });
    await flushPromises();
    expect(card()).not.toBeNull();
    card()?.querySelector<HTMLElement>(".card-close")?.click();
    await flushPromises();
    expect(card()).toBeNull();
  });

  it("is not forgotten by an Esc while it is hidden because the HF radio has no scope", async () => {
    localStorage.setItem("NeoAPRS.monitor", "open");
    localStorage.setItem("NeoAPRS.stats", "open");
    const { socket } = await open();
    expect(card()).toBeNull();
    await escape(); // (closes the statistics card, the one that is shown)
    expect(statsCard()).toBeNull();
    expect(localStorage.getItem("NeoAPRS.monitor")).toBe("open");
    scoped(socket);
    await flushPromises();
    expect(card()).not.toBeNull();
  });

  it("stands beside the statistics card where the map has room for both, and takes its place where it has not", async () => {
    const { setPanelWidth } = harness;
    setPanelWidth(1000);
    const { socket } = await open();
    scoped(socket);
    await flushPromises();
    await rightClick();
    menuItem("stats")?.click();
    await flushPromises();
    await rightClick();
    menuItem("monitor")?.click();
    await flushPromises();
    expect([statsCard() !== null, card() !== null]).toEqual([true, true]);
    await escape();
    await escape();
    setPanelWidth(600);
    await flushPromises();
    await rightClick();
    menuItem("stats")?.click();
    await flushPromises();
    await rightClick();
    menuItem("monitor")?.click();
    await flushPromises();
    expect([statsCard() !== null, card() !== null]).toEqual([false, true]);
    expect(localStorage.getItem("NeoAPRS.stats")).toBe("closed");
    await rightClick();
    menuItem("stats")?.click();
    await flushPromises();
    expect([statsCard() !== null, card() !== null]).toEqual([true, false]);
    await escape();
    expect([statsCard() !== null, card() !== null]).toEqual([false, false]);
    expect(localStorage.getItem("NeoAPRS.monitor")).toBe("closed");
  });
});
