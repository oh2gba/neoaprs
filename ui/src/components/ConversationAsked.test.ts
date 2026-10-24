import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ConversationList from "@/components/ConversationList.vue";
import ConversationThread from "@/components/ConversationThread.vue";
import { conversations, queryKind } from "@/lib/messages";
import { incoming, message } from "@/test/fixtures";

const asked = (id: number, text: string, extra = {}) => message(id, { text, msg_id: null, state: "unconfirmed", attempts: 1, attempts_max: 1, ...extra });

describe("a query we sent, in the conversation", () => {
  it("is a message of ours with no id whose text is one of the four queries, and nothing else", () => {
    expect(queryKind(asked(1, "?APRSP"))).toBe("position");
    expect(queryKind(asked(1, "?APRSS"))).toBe("status");
    expect(queryKind(asked(1, "?APRSD"))).toBe("heard");
    expect(queryKind(asked(1, "?APRST"))).toBe("trace");
    expect(queryKind(asked(1, "?APRSP", { state: "sending", attempts: 0 }))).toBe("position");
    expect(queryKind(message(1, { text: "?APRSS", msg_id: "07" }))).toBeNull(); // (typed by the operator: a message with an id, a bubble)
    expect(queryKind(incoming(2, "OH2RDG", { text: "?APRSS", msg_id: null }))).toBeNull();
    expect(queryKind(asked(1, "?APRSS", { state: "overheard", direction: "in" }))).toBeNull();
    expect(queryKind(asked(1, "?APRSM"))).toBeNull();
    expect(queryKind(asked(1, "Hello"))).toBeNull();
  });

  it("is a grey line with the time, not a bubble, between the bubbles", () => {
    const thread = [message(1, { text: "Hello", state: "acked" }), asked(2, "?APRSS"), incoming(3, "OH2RDG", { text: "Moi!" })];
    const wrapper = mount(ConversationThread, { props: { thread, peer: "OH2RDG" } });
    expect(wrapper.findAll(".bubble")).toHaveLength(2);
    const note = wrapper.find("[data-asked]");
    expect(note.exists()).toBe(true);
    expect(note.classes()).toContain("muted");
    expect(note.text()).toMatch(/^You asked for its status\s*\d\d?[:.]\d\d/);
    expect(wrapper.text()).not.toContain("?APRSS");
    expect(wrapper.findAll(".bubble, [data-asked]").map((e) => (e.attributes("data-asked") !== undefined ? "note" : "bubble"))).toEqual([
      "bubble",
      "note",
      "bubble",
    ]);
  });

  it.each([
    ["?APRSP", "You asked for its position"],
    ["?APRSS", "You asked for its status"],
    ["?APRSD", "You asked what it hears direct"],
    ["?APRST", "You asked for the route"],
  ])("says %s as %s", (text, line) => {
    const wrapper = mount(ConversationThread, { props: { thread: [asked(1, text)], peer: "OH2RDG" } });
    expect(wrapper.find("[data-asked] span").text()).toBe(line);
  });

  it("has no Retry, no state words and no delivery chain, and a clock while it waits for the radio", () => {
    const thread = [asked(1, "?APRSS"), asked(2, "?APRSP", { state: "sending", attempts: 0 })];
    const wrapper = mount(ConversationThread, { props: { thread, peer: "OH2RDG" } });
    const [done, waiting] = wrapper.findAll("[data-asked]");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find(".msg-state").exists()).toBe(false);
    expect(done?.find(".mark").exists()).toBe(false);
    expect(waiting?.find(".mark").attributes("data-mark")).toBe("clock");
  });

  it("is the line of the conversation in the list, and the answer after it is the line when it comes", () => {
    const rows = [message(1, { text: "Hello", state: "acked" }), asked(2, "?APRSS")];
    const list = conversations(rows, () => 0);
    const wrapper = mount(ConversationList, {
      props: { conversations: list, selected: null, now: Date.now(), showOverheard: false },
    });
    expect(wrapper.find(".conv-text").text()).toBe("You asked for its status");
    const answered = conversations([...rows, incoming(3, "OH2RDG", { text: "Directs= OH2RCH-2" })], () => 0);
    const again = mount(ConversationList, { props: { conversations: answered, selected: null, now: Date.now(), showOverheard: false } });
    expect(again.find(".conv-text").text()).toBe("Directs= OH2RCH-2");
  });
});
