import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { setLocale } from "@/i18n";
import { PROTOCOL } from "@/protocol/lists";
import { FakeSocket } from "@/test/fakesocket";
import { hello, station } from "@/test/fixtures";
import { mountApp, useAppHarness } from "@/test/app";

useAppHarness();

const wrong = { version: "0.9.2", protocol: PROTOCOL + 1, page: "index-Daemon01.js" };

/** The page after a load that was made for this daemon already (the guard of lib/reload.ts), which meets it again. */
async function meetTheDaemonTwice() {
  const reload = vi.spyOn(location, "reload").mockImplementation(() => undefined);
  mountApp();
  await flushPromises();
  FakeSocket.last().say(hello(wrong));
  await flushPromises();
  expect(reload).toHaveBeenCalledTimes(1);
  FakeSocket.all = [];
  const wrapper = mountApp();
  await flushPromises();
  const socket = FakeSocket.last();
  socket.say(hello(wrong));
  await flushPromises();
  return { wrapper, socket, reload };
}

describe("a page that does not go with its daemon", () => {
  it("loads itself again once, and then shows a notice on the whole page instead of itself, with a button that loads it again, and the socket closed", async () => {
    const { wrapper, socket, reload } = await meetTheDaemonTwice();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(wrapper.find(".app").exists()).toBe(false);
    expect(wrapper.find(".mismatch[role='alert']").text()).toContain(
      `This page and NeoAPRS do not match (page -/${PROTOCOL}, NeoAPRS 0.9.2, index-Daemon01.js/${PROTOCOL + 1}). Reload the page; if this stays, restart NeoAPRS.`,
    );
    expect(socket.closed).toBe(true);
    socket.say({ type: "state", topic: "stations", rev: 0, value: { A: station("A") } });
    await flushPromises();
    expect(wrapper.find(".mismatch").exists()).toBe(true);
    const button = wrapper.find(".mismatch button.btn.primary");
    expect(button.text()).toBe("Reload");
    await button.trigger("click");
    expect(reload).toHaveBeenCalledTimes(2);
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("says it in the language of the page", async () => {
    setLocale("de");
    const { wrapper } = await meetTheDaemonTwice();
    expect(wrapper.find(".mismatch p").text()).toMatch(
      /^Diese Seite und NeoAPRS passen nicht zusammen \(Seite -\/\d+, NeoAPRS 0\.9\.2, index-Daemon01\.js\/\d+\)\./,
    );
    expect(wrapper.find(".mismatch button").text()).toBe("Neu laden");
  });

  it("is not shown to a page that goes with its daemon, whatever the daemon's version is", async () => {
    const wrapper = mountApp();
    await flushPromises();
    FakeSocket.last().say(hello({ version: "77.0.0" }));
    await flushPromises();
    expect(wrapper.find(".mismatch").exists()).toBe(false);
    expect(wrapper.find(".app").exists()).toBe(true);
    expect(wrapper.find(".panelfoot").exists()).toBe(false);
  });
});
