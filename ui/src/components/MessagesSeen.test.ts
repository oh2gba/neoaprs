// What counts as seen in the Messages tab, in both layouts: a message is seen only while its conversation is open and visible, which on a narrow tab means the conversation shown and not the list.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, shallowReactive } from "vue";
import MessagesPane from "@/components/MessagesPane.vue";
import { useMessagesView } from "@/composables/useMessagesView";
import { usePanel } from "@/composables/usePanel";
import { MESSAGES_WIDE } from "@/lib/layout";
import type { Command, MessageRow } from "@/protocol/protocol";
import { NOW, incoming, message } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

let width: ReturnType<typeof stubWidth>;
beforeEach(() => localStorage.clear());
afterEach(() => {
  width.restore();
  document.body.innerHTML = "";
});

/** The page's wiring of the tab (App.vue): the Messages tab on show, the conversations and the thread from the view of the messages. */
async function page(size: number, ...rows: MessageRow[]) {
  width = stubWidth(size);
  const messages = shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
  const send = vi.fn((_command: Command) => true);
  let made: { panel: ReturnType<typeof usePanel>; view: ReturnType<typeof useMessagesView> } | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        panel.show("messages");
        const view = useMessagesView(messages, panel, send);
        made = { panel, view };
        return () =>
          h(MessagesPane, {
            conversations: view.list.value,
            selected: view.selected.value,
            thread: view.thread.value,
            connected: true,
            now: NOW,
            showOverheard: false,
            paths: new Map(),
            fallbackPath: "WIDE1-1",
            onSelect: (call: string | null) => (view.selected.value = call),
            onDeleteConversation: view.deleteConversation,
          });
      },
    }),
    { attachTo: document.body },
  );
  await flushPromises();
  if (made === undefined) throw new Error("not set up");
  return { wrapper, send, messages, ...made };
}

const rows = [incoming(1, "OH2RDG"), incoming(2, "OH2XYZ"), incoming(3, "OH2XYZ")];

describe.each([
  ["wide", MESSAGES_WIDE + 120],
  ["narrow", MESSAGES_WIDE - 120],
])("the messages not seen, %s", (_name, size) => {
  it("counts them all while no conversation is open", async () => {
    const { view } = await page(size, ...rows);
    expect(view.unread.value).toBe(3);
  });

  it("counts a conversation as seen once it is open, and the others still not", async () => {
    const { wrapper, view } = await page(size, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    expect(view.selected.value).toBe("OH2XYZ");
    expect(view.unread.value).toBe(1);
  });

  it("counts a message that comes in while its conversation is open as seen, and one for another conversation as not", async () => {
    const { wrapper, view, messages } = await page(size, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    messages.set("4", incoming(4, "OH2XYZ"));
    await flushPromises();
    expect(view.unread.value).toBe(1);
    messages.set("5", incoming(5, "OH2RDG"));
    await flushPromises();
    expect(view.unread.value).toBe(2);
  });

  it("counts nothing as seen while the tab is not the one on show", async () => {
    const { wrapper, view, panel } = await page(size, ...rows);
    panel.tab.value = "stations";
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    expect(view.unread.value).toBe(3);
    panel.tab.value = "messages";
    await flushPromises();
    expect(view.unread.value).toBe(1);
  });

  it("opens the conversation of the Message button of a station's card and counts it as seen", async () => {
    const { wrapper, view, panel } = await page(size, ...rows);
    panel.tab.value = "stations";
    view.writeTo("OH2XYZ");
    await flushPromises();
    expect(panel.tab.value).toBe("messages");
    expect(wrapper.find(".convo-title").text()).toBe("OH2XYZ");
    expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("OH2XYZ");
    expect(view.unread.value).toBe(1);
  });

  it("deletes a conversation from its row with two clicks", async () => {
    const { wrapper, send } = await page(size, ...rows);
    const trash = wrapper.find(".conv-item:has(.conv[data-call='OH2XYZ']) .conv-delete");
    await trash.trigger("click");
    expect(send).not.toHaveBeenCalled();
    await trash.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "conversation_delete", call: "OH2XYZ" });
  });
});

describe("the messages not seen, narrow only", () => {
  it("shows the list again when the open conversation is deleted", async () => {
    const { wrapper, view } = await page(MESSAGES_WIDE - 120, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    view.deleteConversation("OH2XYZ");
    await flushPromises();
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo").exists()).toBe(false);
  });

  it("counts a conversation as not seen again after going back to the list, and a message that comes in then as not seen", async () => {
    const { wrapper, view, messages } = await page(MESSAGES_WIDE - 120, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    await wrapper.find(".convo-back").trigger("click");
    await flushPromises();
    expect(view.selected.value).toBeNull();
    messages.set("4", incoming(4, "OH2XYZ"));
    await flushPromises();
    expect(view.unread.value).toBe(2);
    expect(wrapper.find(".conv[data-call='OH2XYZ'] .badge").text()).toBe("1");
  });

  it("puts the focus on the conversation when it opens, and on its row in the list when going back", async () => {
    const { wrapper } = await page(MESSAGES_WIDE - 120, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.find(".convo").element);
    await wrapper.find(".convo-back").trigger("click");
    await flushPromises();
    expect(document.activeElement?.getAttribute("data-call")).toBe("OH2XYZ");
  });

  it("goes back to the list on Esc, and then counts again", async () => {
    const { wrapper, view, messages } = await page(MESSAGES_WIDE - 120, ...rows);
    await wrapper.find(".conv[data-call='OH2RDG']").trigger("click");
    await wrapper.find(".convo").trigger("keydown", { key: "Escape" });
    await flushPromises();
    expect(wrapper.find(".convlist").exists()).toBe(true);
    messages.set("4", incoming(4, "OH2RDG"));
    await flushPromises();
    expect(view.unread.value).toBe(3);
  });

  it("opens the conversation of the Message button of a station's card straight, not the list", async () => {
    const { wrapper, view } = await page(MESSAGES_WIDE - 120, ...rows);
    view.writeTo("OH2NEW");
    await flushPromises();
    expect(wrapper.find(".convlist").exists()).toBe(false);
    expect(wrapper.find(".convo-title").text()).toBe("OH2NEW");
    expect(wrapper.find(".bubbles").text()).toContain("No message with OH2NEW yet");
  });
});

describe("the messages not seen, wide only", () => {
  it("shows the empty state again when the open conversation is deleted", async () => {
    const { wrapper, view } = await page(MESSAGES_WIDE + 120, ...rows);
    await wrapper.find(".conv[data-call='OH2XYZ']").trigger("click");
    const trash = wrapper.find(".conv-item:has(.conv[data-call='OH2XYZ']) .conv-delete");
    await trash.trigger("click");
    await trash.trigger("click");
    await flushPromises();
    expect(view.selected.value).toBeNull();
    expect(wrapper.find(".convo-empty").exists()).toBe(true);
  });

  it("counts a message that comes in as seen while its conversation is at the right, with the list beside it", async () => {
    const { wrapper, view, messages } = await page(MESSAGES_WIDE + 120, ...rows);
    await wrapper.find(".conv[data-call='OH2RDG']").trigger("click");
    expect(wrapper.find(".convlist").exists()).toBe(true);
    messages.set("4", message(4, { to_call: "OH2RDG" }));
    messages.set("5", incoming(5, "OH2RDG"));
    await flushPromises();
    expect(view.unread.value).toBe(2);
  });
});
