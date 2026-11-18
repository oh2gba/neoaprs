import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap } from "@/test/fakemap";
import { open, useAppHarness } from "@/test/app";
import { packet } from "@/test/fixtures";

const harness = useAppHarness();

const card = () => document.querySelector<HTMLElement>(".packetscard");
const statsCard = () => document.querySelector<HTMLElement>(".statscard");
const menuItem = (name: string) => document.querySelector<HTMLElement>(`.mapmenu [role='menuitem'][data-item='${name}']`);

async function choose(name: string): Promise<void> {
  FakeMap.last().fire("contextmenu", {
    lngLat: { lat: 60.1, lng: 24.9 },
    point: { x: 10, y: 10 },
    originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
  });
  await flushPromises();
  if (name === "packets") expect(menuItem(name)?.textContent?.trim()).toBe("Packets"); // (the tab's own word)
  menuItem(name)?.click();
  await flushPromises();
}
const escape = async (): Promise<void> => {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  await flushPromises();
};

describe("App: the Packets card", () => {
  it("opens from the map's menu with the tab's own name and the tab's own rows, follows the packets as the tab does, closes with Esc and is remembered", async () => {
    const { wrapper, socket } = await open();
    await choose("packets");
    expect(card()).not.toBeNull();
    expect(card()?.querySelector(".card-head strong")?.textContent).toBe("Packets");
    expect(card()?.querySelectorAll(".packet-row")).toHaveLength(2);
    expect(card()?.querySelector("input[type='search']")).not.toBeNull();
    socket.say({ type: "patch", topic: "packets", rev: 1, ops: [{ op: "set", key: "3", value: packet(3, { tnc2: "OH2NEW>APRS:>hello" }) }] });
    await flushPromises();
    expect(card()?.querySelectorAll(".packet-row")).toHaveLength(3);
    expect(localStorage.getItem("NeoAPRS.packets")).toBe("open");
    await escape();
    expect(card()).toBeNull();
    expect(localStorage.getItem("NeoAPRS.packets")).toBe("closed");
    wrapper.unmount();
  });

  it("comes back with the page when it was left open, and its cross closes it", async () => {
    localStorage.setItem("NeoAPRS.packets", "open");
    await open();
    expect(card()).not.toBeNull();
    card()?.querySelector<HTMLElement>(".card-close")?.click();
    await flushPromises();
    expect(card()).toBeNull();
  });

  it("stands beside the statistics card where the map has room for both, and takes its place where it has not", async () => {
    harness.setPanelWidth(1000);
    await open();
    await choose("stats");
    await choose("packets");
    expect([statsCard() !== null, card() !== null]).toEqual([true, true]);
    await escape();
    expect([statsCard() !== null, card() !== null]).toEqual([false, false]);
    harness.setPanelWidth(600);
    await flushPromises();
    await choose("stats");
    await choose("packets");
    expect([statsCard() !== null, card() !== null]).toEqual([false, true]);
    expect(localStorage.getItem("NeoAPRS.stats")).toBe("closed");
  });
});
