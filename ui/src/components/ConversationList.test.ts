import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ConversationList from "@/components/ConversationList.vue";
import { conversations } from "@/lib/messages";
import { NOW, incoming, message } from "@/test/fixtures";

const rows = [
  message(1, { to_call: "OH2RDG", text: "Hello Pekka", state: "acked", attempts: 2 }),
  incoming(2, "OH2RDG", { text: "Moi!" }),
  message(4, { to_call: "OH2RDG", text: "Hello?", state: "sending", attempts: 2 }),
  incoming(5, "OH2XYZ", { text: "73 de OH2XYZ" }),
];
const heard = [...rows, message(6, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter" })];

function list(extra: Record<string, unknown> = {}) {
  return mount(ConversationList, {
    props: { conversations: conversations(rows, () => 0), selected: "OH2RDG", now: NOW, showOverheard: false, ...extra },
  });
}

describe("ConversationList", () => {
  it("has a row for each conversation: the call, the age, the last text on one line and the unread count", () => {
    const items = list().findAll(".conv");
    expect(items.map((i) => i.find(".conv-call").text())).toEqual(["OH2XYZ", "OH2RDG"]);
    expect(items[0]?.find(".conv-age").text()).not.toBe("");
    expect(items[0]?.find(".conv-text").text()).toBe("73 de OH2XYZ");
    expect(items[0]?.find(".badge").attributes("title")).toBe("1 message not seen yet");
    expect(items[1]?.find(".conv-text").text()).toBe("You: Hello?");
    expect(items[1]?.find(".badge").exists()).toBe(true);
  });

  it("has no New message button: a chat starts from a station, and the (i) of Show overheard is the only thing at the top", () => {
    const wrapper = list();
    expect(wrapper.text()).not.toContain("New message");
    expect(wrapper.findAll(".convlist-head button").map((b) => b.classes())).toEqual([["info-toggle"]]);
    expect(wrapper.find(".convlist-head .info-toggle").exists()).toBe(true);
  });

  it("marks the selected row, and only that one", () => {
    const wrapper = list();
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("active"))).toEqual([false, true]);
    expect(list({ selected: null }).findAll(".conv.active")).toHaveLength(0);
  });

  it("says the call of the row that was picked", async () => {
    const wrapper = list();
    await wrapper.findAll(".conv")[0]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2XYZ"]]);
  });

  it("can be walked with Tab: every row and every trash is a button", () => {
    const wrapper = list();
    const stops = wrapper.findAll("button");
    expect(stops.map((b) => b.attributes("tabindex"))).not.toContain("-1");
    expect(wrapper.findAll(".conv-item button").map((b) => b.classes().includes("conv") || b.classes().includes("xbtn"))).toEqual([true, true, true, true]);
  });

  it("says there is no message yet", () => {
    expect(list({ conversations: [], selected: null }).find(".convs").text()).toContain("No message yet");
  });

  it("has Show overheard with an (i), and says what was ticked", async () => {
    const wrapper = list();
    expect(wrapper.find(".convlist-overheard").text()).toContain("Show overheard");
    expect(wrapper.find(".convlist-overheard .info-toggle").attributes("aria-label")).toBe("What overheard means");
    await wrapper.find<HTMLInputElement>(".convlist-overheard input").setValue(true);
    expect(wrapper.emitted("update:showOverheard")).toEqual([[true]]);
  });

  describe("deleting a conversation", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    const x = (wrapper: ReturnType<typeof list>, i: number) => wrapper.findAll(".conv-item")[i]?.find(".conv-delete");

    it("has a trash at the right end of every row, outside the button that opens the row", () => {
      const wrapper = list();
      expect(wrapper.findAll(".conv-delete").map((b) => b.text())).toEqual(["", ""]);
      expect(x(wrapper, 1)?.attributes("aria-label")).toBe("Delete the conversation with OH2RDG");
      expect(wrapper.find(".conv .conv-delete").exists()).toBe(false);
    });

    it("asks twice: the first click says sure?, the second sends the call, and neither opens the row", async () => {
      const wrapper = list();
      await x(wrapper, 1)?.trigger("click");
      expect(x(wrapper, 1)?.text()).toBe("sure?");
      expect(x(wrapper, 0)?.text()).toBe("");
      expect(wrapper.emitted("deleteConversation")).toBeUndefined();
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.emitted("deleteConversation")).toEqual([["OH2RDG"]]);
      expect(x(wrapper, 1)?.text()).toBe("");
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("forgets the first click after 5 seconds, and is armed for one row at a time", async () => {
      const wrapper = list();
      await x(wrapper, 0)?.trigger("click");
      await vi.advanceTimersByTimeAsync(5100);
      expect(x(wrapper, 0)?.text()).toBe("");
      await x(wrapper, 0)?.trigger("click");
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.findAll(".conv-delete").map((b) => b.text())).toEqual(["", "sure?"]);
      expect(wrapper.emitted("deleteConversation")).toBeUndefined();
    });

    describe("an overheard pair", () => {
      const wide = () => list({ conversations: conversations(heard, () => 0, true), showOverheard: true });
      const at = (wrapper: ReturnType<typeof list>, call: string) =>
        wrapper
          .findAll(".conv-item")
          .find((item) => item.find(".conv-call").text() === call)
          ?.find(".conv-delete");

      it("has the same trash, only when the overheard rows are listed", () => {
        const wrapper = wide();
        expect(wrapper.findAll(".conv")).toHaveLength(3);
        expect(wrapper.findAll(".conv-delete")).toHaveLength(3);
        expect(at(wrapper, "OH2AAA > OH2BBB")?.attributes("aria-label")).toBe("Delete the overheard messages OH2AAA > OH2BBB");
        expect(list({ conversations: conversations(heard, () => 0, false), showOverheard: false }).findAll(".conv-delete")).toHaveLength(2);
      });

      it("asks twice and then says which pair, as two calls, and not as a conversation", async () => {
        const wrapper = wide();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("sure?");
        expect(at(wrapper, "OH2RDG")?.text()).toBe("");
        expect(wrapper.emitted("deleteOverheard")).toBeUndefined();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        expect(wrapper.emitted("deleteOverheard")).toEqual([["OH2AAA", "OH2BBB"]]);
        expect(wrapper.emitted("deleteConversation")).toBeUndefined();
        expect(wrapper.emitted("select")).toBeUndefined();
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("");
      });

      it("forgets the first click after 5 seconds, and a conversation still sends deleteConversation", async () => {
        const wrapper = wide();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        await vi.advanceTimersByTimeAsync(5100);
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("");
        await at(wrapper, "OH2RDG")?.trigger("click");
        await at(wrapper, "OH2RDG")?.trigger("click");
        expect(wrapper.emitted("deleteConversation")).toEqual([["OH2RDG"]]);
        expect(wrapper.emitted("deleteOverheard")).toBeUndefined();
      });
    });
  });
});
