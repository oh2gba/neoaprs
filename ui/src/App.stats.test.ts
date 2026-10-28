import "@/test/mockmap";
import { afterEach, describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { setLocale } from "@/i18n";
import { FakeMap } from "@/test/fakemap";
import { open, useAppHarness } from "@/test/app";

useAppHarness();
afterEach(() => setLocale("en"));

const card = () => document.querySelector<HTMLElement>(".statscard");
const stats = () => document.querySelector<HTMLElement>(".mapmenu [role='menuitem'][data-item='stats']");

async function askForStats(): Promise<void> {
  FakeMap.last().fire("contextmenu", {
    lngLat: { lat: 60.1, lng: 24.9 },
    point: { x: 10, y: 10 },
    originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
  });
  await flushPromises();
  stats()?.click();
  await flushPromises();
}

describe("App: the statistics card", () => {
  it("opens from the map's menu with the page's numbers, closes with Esc, and is remembered by the browser", async () => {
    const { wrapper } = await open();
    expect(card()).toBeNull();
    await askForStats();
    expect(card()).not.toBeNull();
    const rows = Object.fromEntries(
      [...document.querySelectorAll<HTMLElement>(".statscard dt")].map((dt) => [dt.textContent ?? "", dt.nextElementSibling?.textContent ?? ""]),
    );
    expect(rows["Heard"]).toBe("3");
    expect(rows["In the database"]).toBe("2");
    expect(localStorage.getItem("NeoAPRS.stats")).toBe("open");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await flushPromises();
    expect(card()).toBeNull();
    expect(localStorage.getItem("NeoAPRS.stats")).toBe("closed");
    wrapper.unmount();
  });

  it("comes back with the page when it was left open, and its cross closes it", async () => {
    localStorage.setItem("NeoAPRS.stats", "open");
    await open();
    expect(card()).not.toBeNull();
    card()?.querySelector<HTMLElement>(".card-close")?.click();
    await flushPromises();
    expect(card()).toBeNull();
  });
});
