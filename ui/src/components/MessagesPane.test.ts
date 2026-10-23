import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MessagesPane from "@/components/MessagesPane.vue";
import { conversations } from "@/lib/messages";
import { NOW, incoming, message } from "@/test/fixtures";

const rows = [
  message(1, { to_call: "OH2RDG", text: "Hello Pekka", state: "acked", attempts: 2 }),
  incoming(2, "OH2RDG", { text: "Moi!" }),
  message(3, { to_call: "OH2RDG", text: "Where are you?", state: "failed", attempts: 6 }),
  message(4, { to_call: "OH2RDG", text: "Hello?", state: "sending", attempts: 2 }),
  incoming(5, "OH2XYZ", { text: "73 de OH2XYZ" }),
];

function pane(extra: Record<string, unknown> = {}) {
  const props = {
    conversations: conversations(rows, () => 0),
    selected: "OH2RDG",
    thread: rows.filter((r) => r.to_call === "OH2RDG" || r.from_call === "OH2RDG"),
    connected: true,
    now: NOW,
    showOverheard: false,
    paths: new Map<string, string>(),
    fallbackPath: "WIDE1-1,WIDE2-1",
    ...extra,
  };
  return mount(MessagesPane, { props });
}

describe("MessagesPane", () => {
  it("lists the conversations with the count of unread messages and the newest text", () => {
    const items = pane().findAll(".conv");
    expect(items.map((i) => i.find(".conv-call").text())).toEqual(["OH2XYZ", "OH2RDG"]);
    expect(items[0]?.find(".badge").text()).toBe("1");
    expect(items[0]?.text()).toContain("73 de OH2XYZ");
    expect(items[1]?.text()).toContain("You: Hello?");
    expect(items[1]?.classes()).toContain("active");
  });

  it("shows the delivery chain under a message of ours that has attempts, judging a hop that was not heard by the stations heard direct, and none under one that came in", () => {
    const chained = message(1, {
      to_call: "OH2RDG",
      attempts_detail: [
        { sent_at: "2026-10-22T12:00:00Z", hops: [{ call: "OH2RCH-2", heard: false, heard_at: null, by_internet: false }], internet: null, acked: false },
      ],
    });
    const wrapper = pane({ thread: [chained, incoming(2, "OH2RDG")], heardDirect: new Set(["OH2RCH-2"]) });
    const chains = wrapper.findAll(".chain");
    expect(chains).toHaveLength(1);
    expect(chains[0]?.findAll(".chip-hop").map((c) => c.attributes("data-kind"))).toEqual(["you", "unheard", "waiting"]);
    expect(chains[0]?.findAll(".chip-hop")[1]?.attributes("title")).toBe("not heard");
  });

  it("says a conversation was picked", async () => {
    const wrapper = pane();
    await wrapper.findAll(".conv")[0]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2XYZ"]]);
  });

  it("closes the thread when the row of the open conversation is clicked, and opens another that is", async () => {
    const wrapper = pane();
    await wrapper.findAll(".conv")[1]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([[null]]);
    await wrapper.findAll(".conv")[0]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([[null], ["OH2XYZ"]]);
    await wrapper.setProps({ selected: null, thread: [] });
    expect(wrapper.find(".thread").text()).toBe("");
    expect(wrapper.find(".thread-head").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("");
    await wrapper.findAll(".conv")[1]?.trigger("click");
    expect(wrapper.emitted("select")?.[2]).toEqual(["OH2RDG"]);
  });

  describe("deleting a conversation", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    const x = (wrapper: ReturnType<typeof pane>, i: number) => wrapper.findAll(".conv-item")[i]?.find(".conv-delete");

    it("has a small x at the right end of every row, outside the button that opens the row", () => {
      const wrapper = pane();
      expect(wrapper.findAll(".conv-delete").map((b) => b.text())).toEqual(["x", "x"]);
      expect(x(wrapper, 1)?.attributes("aria-label")).toBe("Delete the conversation with OH2RDG");
      expect(wrapper.find(".conv .conv-delete").exists()).toBe(false);
    });

    it("asks twice: the first click says sure?, the second sends the call, and neither opens or closes the thread", async () => {
      const wrapper = pane();
      await x(wrapper, 1)?.trigger("click");
      expect(x(wrapper, 1)?.text()).toBe("sure?");
      expect(x(wrapper, 0)?.text()).toBe("x");
      expect(wrapper.emitted("deleteConversation")).toBeUndefined();
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.emitted("deleteConversation")).toEqual([["OH2RDG"]]);
      expect(x(wrapper, 1)?.text()).toBe("x");
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("forgets the first click after 5 seconds, and is armed for one row at a time", async () => {
      const wrapper = pane();
      await x(wrapper, 0)?.trigger("click");
      await vi.advanceTimersByTimeAsync(5100);
      expect(x(wrapper, 0)?.text()).toBe("x");
      await x(wrapper, 0)?.trigger("click");
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.findAll(".conv-delete").map((b) => b.text())).toEqual(["x", "sure?"]);
      expect(wrapper.emitted("deleteConversation")).toBeUndefined();
    });

    describe("an overheard pair", () => {
      const heard = [...rows, message(6, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB" })];
      const wide = () => pane({ conversations: conversations(heard, () => 0, true), showOverheard: true });
      const at = (wrapper: ReturnType<typeof pane>, call: string) =>
        wrapper
          .findAll(".conv-item")
          .find((item) => item.find(".conv-call").text() === call)
          ?.find(".conv-delete");

      it("has the same x, only when the overheard rows are listed", () => {
        const wrapper = wide();
        expect(wrapper.findAll(".conv")).toHaveLength(3);
        expect(wrapper.findAll(".conv-delete")).toHaveLength(3);
        expect(at(wrapper, "OH2AAA > OH2BBB")?.attributes("aria-label")).toBe("Delete the overheard messages OH2AAA > OH2BBB");
        expect(pane({ conversations: conversations(heard, () => 0, false), showOverheard: false }).findAll(".conv-delete")).toHaveLength(2);
      });

      it("asks twice and then says which pair, as two calls, and not as a conversation", async () => {
        const wrapper = wide();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("sure?");
        expect(at(wrapper, "OH2RDG")?.text()).toBe("x");
        expect(wrapper.emitted("deleteOverheard")).toBeUndefined();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        expect(wrapper.emitted("deleteOverheard")).toEqual([["OH2AAA", "OH2BBB"]]);
        expect(wrapper.emitted("deleteConversation")).toBeUndefined();
        expect(wrapper.emitted("select")).toBeUndefined();
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("x");
      });

      it("forgets the first click after 5 seconds, and a conversation still sends deleteConversation", async () => {
        const wrapper = wide();
        await at(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
        await vi.advanceTimersByTimeAsync(5100);
        expect(at(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("x");
        await at(wrapper, "OH2RDG")?.trigger("click");
        await at(wrapper, "OH2RDG")?.trigger("click");
        expect(wrapper.emitted("deleteConversation")).toEqual([["OH2RDG"]]);
        expect(wrapper.emitted("deleteOverheard")).toBeUndefined();
      });
    });
  });

  it("shows the thread: the text, the direction, and the state with the attempts for ours", () => {
    const messages = pane().findAll(".msg");
    expect(messages.map((m) => m.classes().includes("in"))).toEqual([false, true, false, false]);
    expect(messages[0]?.text()).toContain("Hello Pekka");
    expect(messages[0]?.text()).toContain("acked, sent 2 times");
    expect(messages[1]?.text()).toContain("Moi!");
    expect(messages[1]?.find(".msg-state").exists()).toBe(false);
    expect(messages[2]?.text()).toContain("no answer after 6 attempts");
    expect(messages[3]?.text()).toContain("sending, attempt 2 of 6");
  });

  it("shows the route a message that came in came by, small under its time, and none on ours", () => {
    const messages = pane().findAll(".msg");
    expect(messages.map((m) => m.find(".msg-route").exists())).toEqual([false, true, false, false]);
    expect(messages[1]?.find(".msg-route").text()).toBe("via OH2RCH-2");
    const direct = [...rows.slice(0, 1), incoming(2, "OH2RDG", { text: "Moi!", route: "direct" }), incoming(6, "OH2RDG", { route: "" })];
    const wrapper = pane({ thread: direct });
    expect(wrapper.findAll(".msg-route").map((r) => r.text())).toEqual(["direct"]);
  });

  it("has the path above the thread: shown, saved when changed, cleared by the x, and the default said when it has none", async () => {
    const wrapper = pane({ paths: new Map([["OH2RDG", "OH2RCH-2"]]) });
    expect(wrapper.find<HTMLInputElement>(".thread-head .pathbox input[placeholder='direct']").element.value).toBe("OH2RCH-2");
    await wrapper.find(".thread-head .pathbox input[placeholder='direct']").setValue("WIDE2-1");
    expect(wrapper.emitted("path")).toEqual([["OH2RDG", "WIDE2-1"]]);
    await wrapper.find(".thread-head .use-default").trigger("click");
    expect(wrapper.emitted("clearPath")).toEqual([["OH2RDG"]]);
    expect(pane().find(".thread-head .pathbox").text()).toContain("(default)");
    expect(wrapper.findAll(".thread-head label").map((l) => l.text())).toEqual(["Path", "RF only"]);
  });

  it("has no attempts field and no map timeout above the thread: the daemon decides the attempts", () => {
    const wrapper = pane();
    expect(wrapper.find(".thread-head .timeout-input").exists()).toBe(false);
    expect(wrapper.find(".thread-head .attempts-input").exists()).toBe(false);
    expect(wrapper.find(".thread-head").text()).not.toContain("Attempts");
  });

  it("has the RF only tickbox beside the path above the thread, ticked for a station that is RF only, and saves it", async () => {
    const wrapper = pane({ rfOnly: new Set(["OH2RDG"]) });
    const box = wrapper.find<HTMLInputElement>(".thread-head .pathbox .rfonly input");
    expect(box.element.checked).toBe(true);
    await box.setValue(false);
    expect(wrapper.emitted("setRfOnly")).toEqual([["OH2RDG", false]]);
    expect(pane().find<HTMLInputElement>(".thread-head .rfonly input").element.checked).toBe(false);
  });

  it("puts the suggestion of the open conversation's station on the chip beside the path", async () => {
    const wrapper = pane({ suggestions: new Map([["OH2RDG", "OH2RCH-3,OH2RCH-1"]]) });
    await wrapper.find(".thread-head .use-suggested").trigger("click");
    expect(wrapper.emitted("path")).toEqual([["OH2RDG", "OH2RCH-3,OH2RCH-1"]]);
    const none = pane({ suggestions: new Map([["OH2XYZ", "OH2RCH-2"]]) });
    expect(none.find(".thread-head .use-suggested").exists()).toBe(false);
  });

  it("offers Retry for the message that failed and Cancel for the one being sent, and says which", async () => {
    const wrapper = pane();
    const messages = wrapper.findAll(".msg");
    const names = (i: number) => messages[i]?.findAll("button").map((b) => b.text());
    expect(names(0)).toEqual([]);
    expect(names(2)).toEqual(["Retry"]);
    expect(names(3)).toEqual(["Cancel"]);
    await messages[2]?.find("button").trigger("click");
    await messages[3]?.find("button").trigger("click");
    expect(wrapper.emitted("retry")).toEqual([[3]]);
    expect(wrapper.emitted("cancel")).toEqual([[4]]);
  });

  it("has no Delete button on a message of any kind: the x of the conversation is the one way to delete", () => {
    const wrapper = pane({
      thread: [
        ...rows.filter((r) => r.to_call === "OH2RDG" || r.from_call === "OH2RDG"),
        message(9, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2RDG" }),
      ],
    });
    expect(wrapper.findAll(".msg")).toHaveLength(5);
    expect(wrapper.findAll(".msg button").filter((b) => b.text().toLowerCase().includes("delete"))).toHaveLength(0);
    expect(wrapper.find(".msg-delete").exists()).toBe(false);
    expect(wrapper.findAll(".conv-delete")).toHaveLength(2);
  });

  it("puts a mark on each message of ours and none on one that came in", () => {
    const marks = pane()
      .findAll(".msg")
      .map((m) => (m.find(".mark").exists() ? m.find(".mark").attributes("data-mark") : null));
    expect(marks).toEqual(["check", null, "cross", "clock"]);
  });

  it("highlights a conversation with something not seen unless it is the open one", async () => {
    const wrapper = pane();
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("fresh"))).toEqual([true, false]);
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("fresh"))).toEqual([false, true]);
  });

  it("shows the path the messages of the open conversation go by, the default or the station's own, and says what is saved", async () => {
    const wrapper = pane();
    expect(wrapper.find<HTMLInputElement>(".thread-head input").element.value).toBe("WIDE1-1,WIDE2-1");
    expect(wrapper.find(".thread-head").text()).toContain("(default)");
    await wrapper.setProps({ paths: new Map([["OH2RDG", "OH2RCH-2"]]) });
    expect(wrapper.find<HTMLInputElement>(".thread-head input").element.value).toBe("OH2RCH-2");
    expect(wrapper.find(".thread-head").text()).not.toContain("(default)");
    await wrapper.find(".thread-head input").setValue("wide2-1");
    expect(wrapper.emitted("path")).toEqual([["OH2RDG", "WIDE2-1"]]);
    await wrapper.find(".thread-head .use-default").trigger("click");
    expect(wrapper.emitted("clearPath")).toEqual([["OH2RDG"]]);
  });

  it("lists the overheard pairs only when asked, and writes to the sender of one", async () => {
    const heard = [...rows, message(6, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter", attempts: 0 })];
    const wrapper = pane({ conversations: conversations(heard, () => 0, true), showOverheard: true });
    expect(wrapper.findAll(".conv").map((c) => c.find(".conv-call").text())).toContain("OH2AAA > OH2BBB");
    expect(wrapper.find(".conv.heard .badge").exists()).toBe(false);
    await wrapper.find<HTMLInputElement>(".toolbar input").setValue(false);
    expect(wrapper.emitted("update:showOverheard")).toEqual([[false]]);
    await wrapper.setProps({ selected: "OH2AAA>OH2BBB", thread: [heard[5]] });
    expect(wrapper.find(".thread-head").text()).toBe("Overheard: OH2AAA > OH2BBB");
    expect(wrapper.find(".thread-head input").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("OH2AAA");
  });

  it("says nothing before a conversation is picked, and that there is no message with the station", () => {
    expect(pane({ selected: null, thread: [] }).find(".thread").text()).toBe("");
    expect(pane({ selected: "OH2NEW", thread: [] }).find(".thread").text()).toContain("No message with OH2NEW yet");
    expect(pane({ conversations: [], selected: null, thread: [] }).find(".convs").text()).toContain("No message yet");
  });

  it("fills in the call of the conversation that is open, and when another is picked", async () => {
    const wrapper = pane();
    const to = wrapper.find<HTMLInputElement>("#msg-to");
    expect(to.element.value).toBe("OH2RDG");
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(to.element.value).toBe("OH2XYZ");
  });

  it("shows the bytes left of 67 as the text grows, and in red when there are too many", async () => {
    const wrapper = pane();
    expect(wrapper.find(".compose-left").text()).toBe("67");
    await wrapper.find("#msg-text").setValue("hello");
    expect(wrapper.find(".compose-left").text()).toBe("62");
    await wrapper.find("#msg-text").setValue("å".repeat(34));
    expect(wrapper.find(".compose-left").text()).toBe("-1");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    expect(wrapper.find(".compose button").attributes("disabled")).toBeDefined();
  });

  it("sends the call in capitals and the text, and empties the box", async () => {
    const wrapper = pane();
    await wrapper.find("#msg-to").setValue(" oh2abc-9 ");
    await wrapper.find("#msg-text").setValue("Moi Pekka");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2ABC-9", "Moi Pekka"]]);
    expect(wrapper.find<HTMLInputElement>("#msg-text").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("OH2ABC-9");
  });

  it("refuses EMAIL-2 as the addressee, in red, with a title that sends the user to the Email tab", async () => {
    const wrapper = pane();
    await wrapper.find("#msg-text").setValue("hello");
    await wrapper.find("#msg-to").setValue("email-2");
    const send = wrapper.find(".compose button");
    expect(send.attributes("disabled")).toBeDefined();
    expect(send.attributes("title")).toBe("Use the Email tab");
    expect(wrapper.find("#msg-to").classes()).toContain("invalid");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
    await wrapper.find("#msg-to").setValue("EMAIL-3");
    expect(send.attributes("disabled")).toBeUndefined();
    expect(send.attributes("title")).toBeUndefined();
  });

  it("sends on Enter in the text box", async () => {
    const wrapper = pane();
    await wrapper.find("#msg-text").setValue("hello");
    await wrapper.find("#msg-text").trigger("keydown.enter");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toHaveLength(1);
  });

  it("has Send off while the text is empty, the call is not a call, or the TNC is not connected, and explains nothing in words", async () => {
    const wrapper = pane();
    const send = () => wrapper.find(".compose button");
    expect(send().attributes("disabled")).toBeDefined();
    await wrapper.find("#msg-text").setValue("hello");
    expect(send().attributes("disabled")).toBeUndefined();
    await wrapper.find("#msg-to").setValue("not a call");
    expect(send().attributes("disabled")).toBeDefined();
    expect(wrapper.find("#msg-to").classes()).toContain("invalid");
    await wrapper.find("#msg-to").setValue("OH2RDG");
    expect(send().attributes("disabled")).toBeUndefined();
    expect(wrapper.find("#msg-to").classes()).not.toContain("invalid");
    expect(send().attributes("title")).toBeUndefined();
    await wrapper.setProps({ connected: false });
    expect(send().attributes("disabled")).toBeDefined();
    expect(send().attributes("title")).toBe("The TNC is not connected");
    expect(wrapper.find(".compose p").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
  });
});
