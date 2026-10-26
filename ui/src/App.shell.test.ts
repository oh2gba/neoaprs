import "@/test/mockmap";
import { describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeSocket } from "@/test/fakesocket";
import { configValues, hello, tncState } from "@/test/fixtures";
import { mountApp, open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App", () => {
  it("opened on the Settings tab, shows no 'not connected' toast and asks for the ports once the daemon is connected", async () => {
    localStorage.setItem("NeoAPRS.tab", "settings");
    const wrapper = mountApp();
    await flushPromises();
    const socket = FakeSocket.last();
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(0);
    socket.say(hello());
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Not connected to the daemon");
  });

  it("says Connecting… under the panel, then nothing of the radio; the header has the title and not our call", async () => {
    const wrapper = mountApp();
    await flushPromises();
    expect(wrapper.find(".panelfoot").text()).toContain("Connecting…");
    const socket = FakeSocket.last();
    socket.say(hello());
    socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    const header = wrapper.find(".appheader").text();
    expect(header).toBe("NeoAPRS");
    expect(wrapper.find(".appheader a").attributes("href")).toBe("https://oh2gba.github.io/neoaprs/");
    const foot = wrapper.find(".panelfoot").text();
    expect(foot).toBe("");
    expect(wrapper.find("#pane-settings").element.parentElement?.lastElementChild).toBe(wrapper.find(".panelfoot").element);
    expect(wrapper.find(".mapwrap .panelfoot").exists()).toBe(false);
  });

  it("shows the radio under the panel only while it is not connected, and the line does not change", async () => {
    const { wrapper, socket } = await open();
    const foot = wrapper.find(".panelfoot");
    expect(foot.find("button.status").exists()).toBe(false);
    socket.say({ type: "state", topic: "tnc", rev: 1, value: tncState({ state: "waiting", problem: "no radio found", describe: "waiting" }) });
    await flushPromises();
    expect(wrapper.find(".panelfoot").element).toBe(foot.element);
    expect(foot.find("button.status").text()).toBe("Radio: not connected");
    socket.say({ type: "state", topic: "tnc", rev: 2, value: tncState() });
    await flushPromises();
    expect(foot.find("button.status").exists()).toBe(false);
    expect(wrapper.find(".appheader").text()).not.toMatch(/radio/i);
  });

  it("says daemon offline when the socket closes, and connects again", async () => {
    const { wrapper, socket } = await open();
    vi.useFakeTimers();
    socket.hangUp();
    await flushPromises();
    expect(wrapper.find(".panelfoot .link-bad").text()).toBe("Daemon offline");
    vi.advanceTimersByTime(1000);
    vi.useRealTimers();
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("remembers the tab and the folding of the panel and its width", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Packets")?.trigger("click");
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowLeft" });
    await wrapper.find(".panel-fold").trigger("click");
    expect(localStorage.getItem("NeoAPRS.tab")).toBe("packets");
    expect(localStorage.getItem("NeoAPRS.panel")).toBe("collapsed");
    expect(Number(localStorage.getItem("NeoAPRS.panelwidth"))).toBeGreaterThan(480);
    wrapper.unmount();
    const again = await open();
    expect(again.wrapper.find(".panel").classes()).toContain("collapsed");
    await again.wrapper.find(".panel-fold").trigger("click");
    expect(again.wrapper.find("[aria-selected='true']").text()).toBe("Packets");
  });

  it("remembers a panel wider than 900 px, shows it as wide as the window allows, and keeps it for a wider window", async () => {
    const wide = window.innerWidth;
    localStorage.setItem("NeoAPRS.panelwidth", "1200");
    const { wrapper } = await open();
    expect(wrapper.find(".panel").attributes("style")).toContain(`--panel-width: ${Math.min(Math.floor(wide * 0.8), wide - 360)}px`);
    window.innerWidth = 2000;
    window.dispatchEvent(new Event("resize"));
    await flushPromises();
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 1200px");
    expect(localStorage.getItem("NeoAPRS.panelwidth")).toBe("1200");
    window.innerWidth = wide;
  });

  it("works without localStorage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { wrapper } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toBe("Settings");
    vi.restoreAllMocks();
  });
});
