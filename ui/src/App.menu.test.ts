import "@/test/mockmap";
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { setLocale } from "@/i18n";
import { message } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();
afterEach(() => setLocale("en"));

const row = (wrapper: VueWrapper, call: string) => wrapper.findAll("#pane-stations tbody tr").find((r) => r.find("td.call .callname").text() === call)!;
const choose = async (wrapper: VueWrapper, name: string) => {
  await wrapper.find(`[role='menuitem'][data-item='${name}']`).trigger("click");
  await flushPromises();
};
const toast = (wrapper: VueWrapper) => wrapper.find(".toast");

describe("App: the menu of a row of the Stations table", () => {
  it("asks the station, tells the daemon with one query and says so in a toast", async () => {
    const { wrapper, socket } = await open();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "ask_status");
    expect(socket.sent).toContainEqual({ cmd: "query", call: "OH2RDG", kind: "status" });
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "query")).toHaveLength(1);
    expect(toast(wrapper).text()).toContain("Asked OH2RDG for its status");
    expect(toast(wrapper).attributes("role")).toBe("status");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it.each([
    ["ask_position", "position", "Asked OH2RDG for its position"],
    ["ask_heard", "heard", "Asked OH2RDG what it hears direct"],
    ["ask_trace", "trace", "Asked OH2RDG for the route"],
  ])("%s sends the %s query", async (item, kind, line) => {
    const { wrapper, socket } = await open();
    await row(wrapper, "OH2RDG").find("button.morebtn").trigger("click");
    await choose(wrapper, item);
    expect(socket.sent).toContainEqual({ cmd: "query", call: "OH2RDG", kind });
    expect(toast(wrapper).text()).toContain(line);
  });

  it("gives way to the daemon's refusal, in the words of the page", async () => {
    const { wrapper, socket } = await open();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "ask_status");
    socket.say({
      type: "error",
      cmd: "query",
      key: null,
      code: "query.too_soon",
      params: { call: "OH2RDG", seconds: 42 },
      text: "query: OH2RDG was asked the same a moment ago: wait 42 s",
    });
    await flushPromises();
    expect(toast(wrapper).attributes("role")).toBe("alert");
    expect(toast(wrapper).text()).toContain("OH2RDG was asked the same a moment ago: wait 42 s");
  });

  it("says the toast in the page's language", async () => {
    const { wrapper } = await open();
    setLocale("de");
    await flushPromises();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    expect(wrapper.find("[role='menuitem'][data-item='ask_status']").text()).toBe("Status erfragen");
    await choose(wrapper, "ask_status");
    expect(toast(wrapper).text()).toContain("OH2RDG nach dem Status gefragt");
  });

  it("writes to the station with Message, and shows its card with Show on map", async () => {
    const { wrapper } = await open();
    await row(wrapper, "OH2PU-9").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "message");
    expect(wrapper.find("#pane-messages").isVisible()).toBe(true);
    expect(wrapper.find("#pane-messages .convo-head").text()).toContain("OH2PU-9");

    await tabButton(wrapper, "Stations")?.trigger("click");
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "show");
    expect(wrapper.find(".card").text()).toContain("OH2RDG");
  });

  it("copies the call and says so", async () => {
    const written: string[] = [];
    vi.stubGlobal("navigator", { clipboard: { writeText: (text: string) => Promise.resolve(void written.push(text)) } });
    const { wrapper } = await open();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "copy");
    expect(written).toEqual(["OH2RDG"]);
    expect(toast(wrapper).text()).toContain("Copied OH2RDG");
  });

  it("forgets the station after two presses", async () => {
    const { wrapper, socket } = await open();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "forget");
    expect(socket.sent).not.toContainEqual({ cmd: "forget_station", call: "OH2RDG" });
    await choose(wrapper, "forget");
    expect(socket.sent).toContainEqual({ cmd: "forget_station", call: "OH2RDG" });
  });

  it("puts the question in the conversation as a grey line, not a bubble, and the answer as a bubble after it", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "patch",
      topic: "messages",
      rev: 1,
      ops: [
        { op: "set", key: "4", value: message(4, { to_call: "OH2RDG", text: "?APRSD", msg_id: null, state: "unconfirmed", attempts: 1, attempts_max: 1 }) },
        {
          op: "set",
          key: "5",
          value: message(5, {
            direction: "in",
            from_call: "OH2RDG",
            to_call: "OH2GBA",
            text: "Directs= OH2RCH-2",
            msg_id: null,
            state: "received",
            attempts: 0,
          }),
        },
      ],
    });
    await flushPromises();
    await row(wrapper, "OH2RDG").trigger("contextmenu", { clientX: 200, clientY: 100 });
    await choose(wrapper, "message");
    const thread = wrapper.find("#pane-messages .bubbles");
    expect(thread.find("[data-asked]").text()).toContain("You asked what it hears direct");
    expect(thread.text()).not.toContain("?APRSD");
    expect(thread.text()).toContain("Directs= OH2RCH-2");
  });
});
