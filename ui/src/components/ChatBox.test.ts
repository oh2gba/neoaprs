import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import ChatBox from "@/components/ChatBox.vue";
import SkedsPane from "@/components/SkedsPane.vue";
import type { ChatLineRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { skedsState } from "@/test/fixtures";

let daemon: FakeDaemon;
beforeEach(() => {
  localStorage.clear();
  daemon = fakeDaemon({ skeds: skedsState(), chatState: { state: "ok" } });
});

const line = (id: number, over: Partial<ChatLineRow> = {}): ChatLineRow => ({
  id,
  at: "2026-10-21T12:00:00Z",
  call: "OH2XYZ",
  text: `line ${id}`,
  ours: false,
  ...over,
});
const table = (...rows: ChatLineRow[]): ReadonlyMap<string, ChatLineRow> => new Map(rows.map((r) => [String(r.id), r]));
const box = () => mount(ChatBox, { global: withDaemon(daemon), attachTo: document.body });
const said = () => daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === "chat_say");

describe("ChatBox", () => {
  it("lists the lines oldest first with the time, the call and the text, and markup in a line is text", async () => {
    const wrapper = box();
    await tell(daemon, {
      chatLines: table(
        line(3, { text: "<b>bold</b> <img src=x onerror=alert(1)>" }),
        line(1),
        line(2, { call: "OH3ABC" }),
      ),
    });
    const rows = wrapper.findAll(".chat-line");
    expect(rows.map((r) => r.find(".chat-call").text())).toEqual(["OH2XYZ", "OH3ABC", "OH2XYZ"]);
    expect(rows[0]?.find(".chat-at").text()).toMatch(/^\d{2}:\d{2}$/);
    expect(rows[2]?.find(".chat-text").text()).toBe("<b>bold</b> <img src=x onerror=alert(1)>");
    expect(wrapper.find(".chat-text b").exists()).toBe(false);
    expect(wrapper.find(".chat-text img").exists()).toBe(false);
  });

  it("says when nothing was said yet, and that a closed chat is closed, in a line that is always there", async () => {
    const wrapper = box();
    await tell(daemon, { chatLines: table() });
    expect(wrapper.find(".chat-lines .empty").text()).toBe("Nothing said yet.");
    expect(wrapper.find(".chat-state").exists()).toBe(true);
    expect(wrapper.find(".chat-state").text()).toBe("");
    await tell(daemon, { chatState: { state: "closed" } });
    expect(wrapper.find(".chat-state").text()).toBe("The chat is closed.");
    expect(wrapper.find<HTMLInputElement>("#chat-text").element.disabled).toBe(true);
  });

  it("sends the line on Enter and keeps it until the daemon has it as ours", async () => {
    const wrapper = box();
    await tell(daemon, { chatLines: table(line(1)) });
    const input = wrapper.find<HTMLInputElement>("#chat-text");
    await input.setValue("  QRV   on 7.0541 ");
    await wrapper.find("form").trigger("submit");
    expect(said()).toEqual([{ cmd: "chat_say", text: "  QRV   on 7.0541 " }]);
    expect(daemon.chat.draft.value).toBe("  QRV   on 7.0541 ");
    await wrapper.find("form").trigger("submit");
    expect(said()).toHaveLength(1);
    await tell(daemon, { chatLines: table(line(1), line(2, { call: "OH2GBA", text: "QRV on 7.0541", ours: true })) });
    expect(daemon.chat.draft.value).toBe("");
  });

  it("keeps the text when the daemon refuses the line", async () => {
    const wrapper = box();
    await wrapper.find<HTMLInputElement>("#chat-text").setValue("hello");
    await wrapper.find("form").trigger("submit");
    await tell(daemon, {
      lastError: { cmd: "chat_say", key: null, code: "chat.rate", params: {}, text: "", id: null, n: 1 },
    });
    expect(daemon.chat.draft.value).toBe("hello");
    expect(wrapper.find<HTMLButtonElement>("button[type=submit]").element.disabled).toBe(false);
  });

  it("has Send off for an empty or invisible line, and the line off without a call", async () => {
    const wrapper = box();
    const send = () => wrapper.find<HTMLButtonElement>("button[type=submit]").element.disabled;
    expect(send()).toBe(true);
    await wrapper.find<HTMLInputElement>("#chat-text").setValue("\u200b ");
    expect(send()).toBe(true);
    await tell(daemon, { call: null });
    expect(wrapper.find<HTMLInputElement>("#chat-text").element.disabled).toBe(true);
  });

  it("keeps a line being written when the tab goes and comes back", async () => {
    const first = mount(SkedsPane, { global: withDaemon(daemon) });
    await first.find<HTMLInputElement>("#chat-text").setValue("half a thought");
    first.unmount();
    const again = mount(SkedsPane, { global: withDaemon(daemon) });
    expect(again.find<HTMLInputElement>("#chat-text").element.value).toBe("half a thought");
  });

  it("counts the lines of others not seen yet, never ours, and a browser without a mark counts none at first", async () => {
    await tell(daemon, { chatLines: table(line(1), line(2)) });
    expect(daemon.chat.unread.value).toBe(0);
    await tell(daemon, { chatLines: table(line(1), line(2), line(3), line(4, { ours: true })) });
    expect(daemon.chat.unread.value).toBe(1);
    daemon.panel.show("skeds");
    await tell(daemon, {});
    expect(daemon.chat.unread.value).toBe(0);
  });
});
