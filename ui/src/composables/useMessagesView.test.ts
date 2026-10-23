import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, shallowReactive } from "vue";
import { useMessagesView } from "@/composables/useMessagesView";
import { usePanel } from "@/composables/usePanel";
import type { Command, MessageRow } from "@/protocol/protocol";
import { incoming, message } from "@/test/fixtures";

function setUp(...rows: MessageRow[]) {
  const messages = shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
  const send = vi.fn((_command: Command) => true);
  let made: { panel: ReturnType<typeof usePanel>; view: ReturnType<typeof useMessagesView> } | undefined;
  mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        made = { panel, view: useMessagesView(messages, panel, send) };
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return { send, ...made };
}

beforeEach(() => localStorage.clear());

describe("useMessagesView", () => {
  it("opens the Messages tab on a station from its card, the panel unfolded", () => {
    const { panel, view } = setUp();
    panel.collapsed.value = true;
    view.writeTo("OH2RDG");
    expect([view.selected.value, panel.tab.value, panel.collapsed.value]).toEqual(["OH2RDG", "messages", false]);
  });

  it("opens the Email tab, not a conversation, from the card of the email gateway", () => {
    const { panel, view } = setUp();
    view.writeTo("EMAIL-2");
    expect([view.selected.value, panel.tab.value]).toEqual([null, "email"]);
  });

  it("lists no conversation with the email gateway and counts none of its messages", () => {
    const { view } = setUp(message(1, { to_call: "EMAIL-2" }), incoming(2, "EMAIL-2"), incoming(3, "OH2RDG"));
    expect(view.list.value.map((c) => c.call)).toEqual(["OH2RDG"]);
    expect(view.unread.value).toBe(1);
  });

  it("opens the newest conversation with something new from the header, unless the open one has some", () => {
    const { view } = setUp(message(1, { to_call: "OH2XYZ" }), incoming(2, "OH2RDG"), incoming(3, "OH2PU-9"));
    view.selected.value = "OH2XYZ";
    view.openMessages();
    expect(view.selected.value).toBe("OH2PU-9");
    view.selected.value = "OH2RDG";
    view.openMessages();
    expect(view.selected.value).toBe("OH2RDG");
  });

  it("sends a message and opens its conversation; deletes a conversation and closes its thread if it was open", () => {
    const { send, view } = setUp();
    view.sendMessage("OH2RDG", "Moi");
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "OH2RDG", text: "Moi" });
    expect(view.selected.value).toBe("OH2RDG");
    view.deleteConversation("OH2XYZ");
    expect(view.selected.value).toBe("OH2RDG");
    view.deleteConversation("OH2RDG");
    expect(send).toHaveBeenLastCalledWith({ cmd: "conversation_delete", call: "OH2RDG" });
    expect(view.selected.value).toBeNull();
  });

  it("sends the same text to several stations, a command for each, and leaves the open conversation as it is", () => {
    const { send, view } = setUp();
    view.selected.value = "OH2XYZ";
    view.sendMessages(["OH2AAA", "OH2BBB", "OH2CCC"], "Net at 20:00");
    expect(send.mock.calls.map(([c]) => c)).toEqual([
      { cmd: "send_message", to: "OH2AAA", text: "Net at 20:00" },
      { cmd: "send_message", to: "OH2BBB", text: "Net at 20:00" },
      { cmd: "send_message", to: "OH2CCC", text: "Net at 20:00" },
    ]);
    expect(view.selected.value).toBe("OH2XYZ");
  });

  it("deletes an overheard pair with its two calls, and closes its thread if it was open", () => {
    const { send, view } = setUp();
    view.selected.value = "OH2AAA>OH2BBB";
    view.deleteOverheard("OH2AAA", "OH2CCC");
    expect(send).toHaveBeenLastCalledWith({ cmd: "overheard_delete", from_call: "OH2AAA", to_call: "OH2CCC" });
    expect(view.selected.value).toBe("OH2AAA>OH2BBB");
    view.deleteOverheard("OH2AAA", "OH2BBB");
    expect(send).toHaveBeenLastCalledWith({ cmd: "overheard_delete", from_call: "OH2AAA", to_call: "OH2BBB" });
    expect(view.selected.value).toBeNull();
  });

  it("remembers whether the overheard messages are listed", async () => {
    const { view } = setUp();
    expect(view.showOverheard.value).toBe(false);
    view.showOverheard.value = true;
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.overheard")).toBe("on");
  });
});
