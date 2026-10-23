import { flushPromises, mount } from "@vue/test-utils";
import { shallowReactive } from "vue";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import MessagesPane from "@/components/MessagesPane.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { MESSAGES_WIDE } from "@/lib/layout";
import { conversations } from "@/lib/messages";
import type { StationPref } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { incoming, message } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

const rows = [
  message(1, { to_call: "OH2RDG", text: "Hello Pekka", state: "acked", attempts: 2 }),
  incoming(2, "OH2RDG", { text: "Moi!" }),
  message(3, { to_call: "OH2RDG", text: "Where are you?", state: "failed", attempts: 6 }),
  message(4, { to_call: "OH2RDG", text: "Hello?", state: "sending", attempts: 2 }),
  incoming(5, "OH2XYZ", { text: "73 de OH2XYZ" }),
];

const WIDE = MESSAGES_WIDE + 120;
const NARROW = MESSAGES_WIDE - 120;

let width: ReturnType<typeof stubWidth>;
beforeEach(() => (width = stubWidth(WIDE)));
afterEach(() => {
  width.restore();
  document.body.innerHTML = "";
});

/** The page's context of the pane just made: what it sent, and what the page tells it later. */
let daemon: FakeDaemon;
const sent = (cmd: string) => daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === cmd);

/** The tab, as wide as the test says, with the conversation with OH2RDG open. The page's part of it is given as `paths`, `rfOnly`, `suggestions`, `heardDirect` and `connected`. */
async function pane({
  paths = new Map<string, string>(),
  rfOnly = new Set<string>(),
  suggestions,
  heardDirect,
  connected = true,
  ...extra
}: Record<string, unknown> = {}) {
  const props = {
    conversations: conversations(rows, () => 0),
    selected: "OH2RDG",
    thread: rows.filter((r) => r.to_call === "OH2RDG" || r.from_call === "OH2RDG"),
    showOverheard: false,
    ...extra,
  };
  const book = new Map<string, StationPref>();
  for (const [call, path] of paths as Map<string, string>) book.set(call, { path, hide_after_min: null, rf_only: false });
  for (const call of rfOnly as Set<string>) book.set(call, { path: book.get(call)?.path ?? null, hide_after_min: null, rf_only: true });
  daemon = fakeDaemon({ connected: connected as boolean, fallbackPath: "WIDE1-1,WIDE2-1" });
  daemon.prefs = useStationPrefs(shallowReactive(book), daemon.send);
  if (suggestions !== undefined) daemon.suggestions.value = suggestions as Map<string, string | null>;
  if (heardDirect !== undefined) daemon.heardDirect.value = heardDirect as Set<string>;
  const wrapper = mount(MessagesPane, { props, global: withDaemon(daemon), attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe("MessagesPane, wide", () => {
  it("lists the conversations with the count of unread messages and the newest text", async () => {
    const items = (await pane()).findAll(".conv");
    expect(items.map((i) => i.find(".conv-call").text())).toEqual(["OH2XYZ", "OH2RDG"]);
    expect(items[0]?.find(".badge").text()).toBe("1");
    expect(items[0]?.text()).toContain("73 de OH2XYZ");
    expect(items[1]?.text()).toContain("You: Hello?");
    expect(items[1]?.classes()).toContain("active");
  });

  it("has the list at the left and the open conversation at the right, side by side", async () => {
    const wrapper = await pane();
    expect(wrapper.classes()).toContain("wide");
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo").exists()).toBe(true);
    expect(wrapper.find(".convo-back").exists()).toBe(false);
    expect(Array.from((wrapper.element as HTMLElement).children).map((c) => c.className.split(" ")[0])).toEqual(["convlist", "convo"]);
  });

  it("is wide from MESSAGES_WIDE on, by the width of the tab", async () => {
    width.set(MESSAGES_WIDE);
    expect((await pane()).classes()).toContain("wide");
    width.set(MESSAGES_WIDE - 1);
    expect((await pane()).classes()).toContain("narrow");
  });

  it("highlights the open conversation in the list as the selected one", async () => {
    const wrapper = await pane();
    expect(wrapper.findAll(".conv-item").map((i) => i.classes().includes("open"))).toEqual([false, true]);
    expect(wrapper.findAll(".conv").map((c) => c.attributes("aria-current"))).toEqual(["false", "true"]);
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("active"))).toEqual([true, false]);
  });

  it("highlights a conversation with something not seen unless it is the open one", async () => {
    const wrapper = await pane();
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("fresh"))).toEqual([true, false]);
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(wrapper.findAll(".conv").map((c) => c.classes().includes("fresh"))).toEqual([false, true]);
  });

  it("says a conversation was picked, also the one that is open (no toggle: the right side keeps showing it)", async () => {
    const wrapper = await pane();
    await wrapper.findAll(".conv")[0]?.trigger("click");
    await wrapper.findAll(".conv")[1]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2XYZ"], ["OH2RDG"]]);
  });

  it("shows a quiet empty state that points to a station's Message button while no conversation is open, and has no New message anywhere", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    expect(wrapper.find(".convo").exists()).toBe(false);
    expect(wrapper.find(".convo-empty").text()).toBe("Choose a conversation, or a station's Message button");
    expect(wrapper.find(".convo-empty button").exists()).toBe(false);
    expect(wrapper.find(".new-message").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("New message");
    expect(wrapper.findAll(".conv")).toHaveLength(2);
  });

  it("explains what overheard means in an (i)", async () => {
    const wrapper = await pane();
    expect(wrapper.find(".convlist-overheard .info-toggle").attributes("aria-label")).toBe("What overheard means");
  });

  it("lists the overheard pairs only when asked, and has nothing to reply with: the bubbles and the header only", async () => {
    const heard = [...rows, message(6, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter", attempts: 0 })];
    const wrapper = await pane({ conversations: conversations(heard, () => 0, true), showOverheard: true });
    expect(wrapper.findAll(".conv").map((c) => c.find(".conv-call").text())).toContain("OH2AAA > OH2BBB");
    expect(wrapper.find(".conv.heard .badge").exists()).toBe(false);
    await wrapper.find<HTMLInputElement>(".convlist-overheard input").setValue(false);
    expect(wrapper.emitted("update:showOverheard")).toEqual([[false]]);
    await wrapper.setProps({ selected: "OH2AAA>OH2BBB", thread: [heard[5]] });
    expect(wrapper.find(".convo-head").text()).toBe("Overheard: OH2AAA > OH2BBB");
    expect(wrapper.find(".route-button").exists()).toBe(false);
    expect(wrapper.find(".bubble").text()).toContain("chatter");
    expect(wrapper.find(".compose").exists()).toBe(false);
    expect(wrapper.find("form").exists()).toBe(false);
    expect(wrapper.find("#msg-text").exists()).toBe(false);
    expect(wrapper.find("#msg-to").exists()).toBe(false);
    expect(wrapper.find(".convo .btn.primary").exists()).toBe(false);
    expect([...wrapper.find(".convo").element.children].map((c) => c.className.split(" ")[0])).toEqual(["convo-head", "bubbles"]);
  });

  it("has no To and no Stations in the box of a conversation: the conversation is the station", async () => {
    const wrapper = await pane();
    expect(wrapper.find("#msg-to").exists()).toBe(false);
    expect(wrapper.find(".compose").text()).not.toContain("Stations");
    expect(wrapper.find(".picker").exists()).toBe(false);
    expect(wrapper.find(".compose input").attributes("placeholder")).toBe("Message");
  });

  it("keeps the text being written when another conversation is picked", async () => {
    const wrapper = await pane();
    await wrapper.find("#msg-text").setValue("half a message");
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(wrapper.find<HTMLInputElement>("#msg-text").element.value).toBe("half a message");
  });
});

describe("MessagesPane, the route in the header", () => {
  const routeBox = (wrapper: Awaited<ReturnType<typeof pane>>) => wrapper.find(".convo-head .route-box");

  it("is a small Route button in the header bar, above the thread and not a block in it, closed until pressed", async () => {
    const wrapper = await pane();
    const head = wrapper.find(".convo-head");
    expect(head.find(".route-button").text()).toBe("Route");
    expect(head.find(".route-button").attributes("aria-expanded")).toBe("false");
    expect(routeBox(wrapper).exists()).toBe(false);
    await head.find(".route-button").trigger("click");
    expect(routeBox(wrapper).find(".pathbox").exists()).toBe(true);
    expect(head.find(".route-button").attributes("aria-expanded")).toBe("true");
    expect(wrapper.find(".bubbles .pathbox").exists()).toBe(false);
  });

  it("has a dot on the button when the station has a path of its own, or is RF only, and none otherwise", async () => {
    const dot = async (extra: Record<string, unknown>) => (await pane(extra)).find(".route-dot").exists();
    expect(await dot({})).toBe(false);
    expect(await dot({ paths: new Map([["OH2RDG", "OH2RCH-2"]]) })).toBe(true);
    expect(await dot({ rfOnly: new Set(["OH2RDG"]) })).toBe(true);
    expect(await dot({ paths: new Map([["OH2XYZ", "OH2RCH-2"]]) })).toBe(false);
  });

  it("has the path in the box: shown, saved when changed, cleared by the x, and the default said when it has none", async () => {
    const wrapper = await pane({ paths: new Map([["OH2RDG", "OH2RCH-2"]]) });
    await wrapper.find(".route-button").trigger("click");
    const input = () => wrapper.find<HTMLInputElement>(".route-box .pathbox input[placeholder='direct']");
    expect(input().element.value).toBe("OH2RCH-2");
    await input().setValue("WIDE2-1");
    expect(sent("set_station_path")).toEqual([{ cmd: "set_station_path", call: "OH2RDG", path: "WIDE2-1" }]);
    await wrapper.find(".route-box .use-default").trigger("click");
    expect(sent("clear_station_path")).toEqual([{ cmd: "clear_station_path", call: "OH2RDG" }]);
    expect(wrapper.findAll(".route-box label").map((l) => l.text())).toEqual(["Path", "RF only"]);
    const plain = await pane();
    await plain.find(".route-button").trigger("click");
    expect(plain.find(".route-box .pathbox").text()).toContain("(default)");
    expect(plain.find<HTMLInputElement>(".route-box input").element.value).toBe("WIDE1-1,WIDE2-1");
  });

  it("has no attempts field and no map timeout: the daemon decides the attempts", async () => {
    const wrapper = await pane();
    await wrapper.find(".route-button").trigger("click");
    expect(wrapper.find(".route-box .timeout-input").exists()).toBe(false);
    expect(wrapper.find(".route-box .attempts-input").exists()).toBe(false);
    expect(wrapper.find(".route-box").text()).not.toContain("Attempts");
  });

  it("has the RF only tickbox beside the path, ticked for a station that is RF only, and saves it", async () => {
    const wrapper = await pane({ rfOnly: new Set(["OH2RDG"]) });
    await wrapper.find(".route-button").trigger("click");
    const box = wrapper.find<HTMLInputElement>(".route-box .pathbox .rfonly input");
    expect(box.element.checked).toBe(true);
    await box.setValue(false);
    expect(sent("set_station_rf_only")).toEqual([{ cmd: "set_station_rf_only", call: "OH2RDG", on: false }]);
  });

  it("puts the suggestion of the open conversation's station on the chip beside the path", async () => {
    const wrapper = await pane({ suggestions: new Map([["OH2RDG", "OH2RCH-3,OH2RCH-1"]]) });
    await wrapper.find(".route-button").trigger("click");
    await wrapper.find(".route-box .use-suggested").trigger("click");
    expect(sent("set_station_path")).toEqual([{ cmd: "set_station_path", call: "OH2RDG", path: "OH2RCH-3,OH2RCH-1" }]);
    const none = await pane({ suggestions: new Map([["OH2XYZ", "OH2RCH-2"]]) });
    await none.find(".route-button").trigger("click");
    expect(none.find(".route-box .use-suggested").exists()).toBe(false);
  });

  it("closes on Esc without leaving the conversation, on a click outside, and for the next conversation", async () => {
    width.set(NARROW);
    const wrapper = await pane();
    await wrapper.find(".route-button").trigger("click");
    await wrapper.find(".route-box input").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".route-box").exists()).toBe(false);
    expect(wrapper.emitted("select")).toBeUndefined();
    await wrapper.find(".route-button").trigger("click");
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(wrapper.find(".route-box").exists()).toBe(false);
    await wrapper.find(".route-button").trigger("click");
    await wrapper.setProps({ selected: "OH2XYZ" });
    expect(wrapper.find(".route-box").exists()).toBe(false);
  });
});

describe("MessagesPane, the thread", () => {
  it("shows the bubbles: the text, the side, and the state with the attempts for ours", async () => {
    const messages = (await pane()).findAll(".bubble");
    expect(messages.map((m) => m.classes().includes("in"))).toEqual([false, true, false, false]);
    expect(messages.map((m) => m.classes().includes("out"))).toEqual([true, false, true, true]);
    expect(messages[0]?.text()).toContain("Hello Pekka");
    expect(messages[0]?.text()).toContain("acked, sent 2 times");
    expect(messages[1]?.text()).toContain("Moi!");
    expect(messages[1]?.find(".msg-state").exists()).toBe(false);
    expect(messages[2]?.text()).toContain("no answer after 6 attempts");
    expect(messages[3]?.text()).toContain("sending, attempt 2 of 6");
  });

  it("shows the delivery chain under a message of ours that has attempts, judging a hop that was not heard by the stations heard direct, and none under one that came in", async () => {
    const chained = message(1, {
      to_call: "OH2RDG",
      attempts_detail: [
        { sent_at: "2026-10-22T12:00:00Z", hops: [{ call: "OH2RCH-2", heard: false, heard_at: null, by_internet: false }], internet: null, acked: false },
      ],
    });
    const wrapper = await pane({ thread: [chained, incoming(2, "OH2RDG")], heardDirect: new Set(["OH2RCH-2"]) });
    const chains = wrapper.findAll(".chain");
    expect(chains).toHaveLength(1);
    expect(wrapper.findAll(".bubble")[0]?.find(".chain").exists()).toBe(true);
    expect(chains[0]?.findAll(".chip-hop").map((c) => c.attributes("data-kind"))).toEqual(["you", "unheard", "waiting"]);
    expect(chains[0]?.findAll(".chip-hop")[1]?.attributes("title")).toBe("not heard");
  });

  it("shows the route a message that came in came by, small under its time, and none on ours", async () => {
    const messages = (await pane()).findAll(".bubble");
    expect(messages.map((m) => m.find(".bubble-route").exists())).toEqual([false, true, false, false]);
    expect(messages[1]?.find(".bubble-route").text()).toBe("via OH2RCH-2");
    const direct = [...rows.slice(0, 1), incoming(2, "OH2RDG", { text: "Moi!", route: "direct" }), incoming(6, "OH2RDG", { route: "" })];
    const wrapper = await pane({ thread: direct });
    expect(wrapper.findAll(".bubble-route").map((r) => r.text())).toEqual(["direct"]);
  });

  it("offers Retry for the message that failed and Cancel for the one being sent, and says which", async () => {
    const wrapper = await pane();
    const messages = wrapper.findAll(".bubble");
    const names = (i: number) => messages[i]?.findAll("button").map((b) => b.text());
    expect(names(0)).toEqual([]);
    expect(names(2)).toEqual(["Retry"]);
    expect(names(3)).toEqual(["Cancel"]);
    await messages[2]?.find("button").trigger("click");
    await messages[3]?.find("button").trigger("click");
    expect(wrapper.emitted("retry")).toEqual([[3]]);
    expect(wrapper.emitted("cancel")).toEqual([[4]]);
  });

  it("has no Delete button on a message of any kind: the trash of the conversation is the one way to delete", async () => {
    const wrapper = await pane({
      thread: [
        ...rows.filter((r) => r.to_call === "OH2RDG" || r.from_call === "OH2RDG"),
        message(9, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2RDG" }),
      ],
    });
    expect(wrapper.findAll(".bubble")).toHaveLength(5);
    expect(wrapper.findAll(".bubble button").filter((b) => b.text().toLowerCase().includes("delete"))).toHaveLength(0);
    expect(wrapper.findAll(".conv-delete")).toHaveLength(2);
  });

  it("puts a mark on each message of ours and none on one that came in", async () => {
    const marks = (await pane()).findAll(".bubble").map((m) => (m.find(".mark").exists() ? m.find(".mark").attributes("data-mark") : null));
    expect(marks).toEqual(["check", null, "cross", "clock"]);
  });

  it("says that there is no message with the station", async () => {
    expect((await pane({ selected: "OH2NEW", thread: [] })).find(".bubbles").text()).toContain("No message with OH2NEW yet");
    expect((await pane({ conversations: [], selected: null, thread: [] })).find(".convs").text()).toContain("No message yet");
  });

  it("scrolls to the newest message when it is shown and when one is added", async () => {
    const scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 900 });
    try {
      const wrapper = await pane();
      expect(wrapper.find<HTMLElement>(".bubbles").element.scrollTop).toBe(900);
      wrapper.find<HTMLElement>(".bubbles").element.scrollTop = 10;
      await wrapper.setProps({ thread: [...rows.slice(0, 1), incoming(7, "OH2RDG", { text: "new" })] });
      await flushPromises();
      expect(wrapper.find<HTMLElement>(".bubbles").element.scrollTop).toBe(900);
    } finally {
      if (scroll) Object.defineProperty(HTMLElement.prototype, "scrollHeight", scroll);
      else Reflect.deleteProperty(HTMLElement.prototype, "scrollHeight");
    }
  });
});

describe("MessagesPane, the box to write in", () => {
  it("is the last thing of the conversation, under the thread", async () => {
    const wrapper = await pane();
    const parts = [...wrapper.find(".convo").element.children].map((c) => c.className.split(" ")[0]);
    expect(parts).toEqual(["convo-head", "bubbles", "compose"]);
  });

  it("shows the bytes left of 67 as the text grows, and in red when there are too many", async () => {
    const wrapper = await pane();
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
    await wrapper.find("#msg-text").setValue("hello");
    expect(wrapper.find(".compose-left").text()).toBe("62 left");
    await wrapper.find("#msg-text").setValue("å".repeat(34));
    expect(wrapper.find(".compose-left").text()).toBe("1 over");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    expect(wrapper.find(".compose button[type='submit']").attributes("disabled")).toBeDefined();
  });

  it("sends the text to the station of the conversation, and empties the box", async () => {
    const wrapper = await pane();
    await wrapper.find("#msg-text").setValue("Moi Pekka");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2RDG", "Moi Pekka"]]);
    expect(wrapper.find<HTMLInputElement>("#msg-text").element.value).toBe("");
  });

  it("sends to the station of the conversation that is open when another is picked, and for an overheard pair's sender nothing is possible", async () => {
    const wrapper = await pane({ selected: "OH2XYZ", thread: [] });
    await wrapper.find("#msg-text").setValue("Hi");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2XYZ", "Hi"]]);
  });

  it("sends on Enter in the text box", async () => {
    const wrapper = await pane();
    await wrapper.find("#msg-text").setValue("hello");
    await wrapper.find("#msg-text").trigger("keydown.enter");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toHaveLength(1);
  });

  it("has Send off while the text is empty or the TNC is not connected, and explains nothing in words", async () => {
    const wrapper = await pane();
    const send = () => wrapper.find(".compose button[type='submit']");
    expect(send().attributes("disabled")).toBeDefined();
    await wrapper.find("#msg-text").setValue("hello");
    expect(send().attributes("disabled")).toBeUndefined();
    expect(send().attributes("title")).toBeUndefined();
    await tell(daemon, { connected: false });
    expect(send().attributes("disabled")).toBeDefined();
    expect(send().attributes("title")).toBe("The TNC is not connected");
    expect(wrapper.find(".compose p").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
  });
});

describe("MessagesPane, narrow", () => {
  beforeEach(() => width.set(NARROW));

  it("shows the list alone, filling the tab, while no conversation is open", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    expect(wrapper.classes()).toContain("narrow");
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo").exists()).toBe(false);
    expect(wrapper.find(".convo-empty").exists()).toBe(false);
    expect(wrapper.find(".new-message").exists()).toBe(false);
  });

  it("shows the conversation alone, with a back arrow in its header, once one is open", async () => {
    const wrapper = await pane();
    expect(wrapper.find(".convlist").exists()).toBe(false);
    expect(wrapper.find(".convo").exists()).toBe(true);
    const back = wrapper.find(".convo-head .convo-back");
    expect(back.text()).toBe("‹");
    expect(back.attributes("aria-label")).toBe("Back to the conversations");
    expect(wrapper.find(".convo-head .convo-title").text()).toBe("OH2RDG");
  });

  it("goes from the list to the conversation to the list, and says select with the call and with null", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    await wrapper.findAll(".conv")[1]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG"]]);
    await wrapper.setProps({ selected: "OH2RDG" });
    expect(wrapper.find(".convlist").exists()).toBe(false);
    expect(wrapper.find(".convo").exists()).toBe(true);
    await wrapper.find(".convo-back").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG"], [null]]);
    await wrapper.setProps({ selected: null, thread: [] });
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo").exists()).toBe(false);
  });

  it("goes back on Esc in the conversation, and not on Esc while the list is shown", async () => {
    const wrapper = await pane();
    await wrapper.find(".convo").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toEqual([[null]]);
    const list = await pane({ selected: null, thread: [] });
    await list.find(".convlist").trigger("keydown", { key: "Escape" });
    expect(list.emitted("select")).toBeUndefined();
  });

  it("goes back on Esc typed in the text box too", async () => {
    const wrapper = await pane();
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toEqual([[null]]);
  });

  it("goes to the conversation straight when the page selects one (the Message button of a station card)", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    await wrapper.setProps({ selected: "OH2XYZ", thread: [] });
    expect(wrapper.find(".convlist").exists()).toBe(false);
    expect(wrapper.find(".convo-title").text()).toBe("OH2XYZ");
    expect(wrapper.find("#msg-to").exists()).toBe(false);
  });

  it("turns into two columns when the tab becomes wide, with the same conversation open", async () => {
    const wrapper = await pane();
    expect(wrapper.find(".convlist").exists()).toBe(false);
    width.set(WIDE);
    await flushPromises();
    expect(wrapper.classes()).toContain("wide");
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo-title").text()).toBe("OH2RDG");
    expect(wrapper.find(".convo-back").exists()).toBe(false);
  });

  it("keeps the delete button on the rows of the list, with two clicks", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    const trash = () => wrapper.findAll(".conv-delete")[1];
    await trash()?.trigger("click");
    expect(trash()?.text()).toBe("sure?");
    await trash()?.trigger("click");
    expect(wrapper.emitted("deleteConversation")).toEqual([["OH2RDG"]]);
  });
});

describe("MessagesPane, the group compose", () => {
  const calls = ["OH2AAA", "OH2BBB", "OH2CCC"];
  const open = (extra: Record<string, unknown> = {}) => pane({ selected: null, thread: [], group: calls, ...extra });

  it("takes the place of the conversation on a wide tab, beside the list, with the recipients as chips and Send to 3", async () => {
    const wrapper = await open();
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.find(".convo-empty").exists()).toBe(false);
    expect(
      wrapper
        .find(".group .recipients")
        .findAll(".chip")
        .map((c) => c.text()),
    ).toEqual(["OH2AAA ×", "OH2BBB ×", "OH2CCC ×"]);
    expect(wrapper.find(".group .compose button[type='submit']").text()).toBe("Send to 3");
    expect(wrapper.find(".group .compose-left").text()).toBe("67 left");
    expect(wrapper.find("#msg-to").exists()).toBe(false);
    expect(wrapper.find(".route-button").exists()).toBe(false);
  });

  it("takes the whole tab on a narrow one, with a back arrow, instead of the list", async () => {
    width.set(NARROW);
    const wrapper = await open();
    expect(wrapper.find(".convlist").exists()).toBe(false);
    expect(wrapper.find(".group .convo-back").exists()).toBe(true);
    await wrapper.find(".group .convo-back").trigger("click");
    expect(wrapper.emitted("update:group")).toEqual([[null]]);
  });

  it("says which recipients are left when one is taken out, and closes with the last one", async () => {
    const wrapper = await open();
    await wrapper.findAll(".group .chip")[0]?.trigger("click");
    expect(wrapper.emitted("update:group")).toEqual([[["OH2BBB", "OH2CCC"]]]);
    const one = await open({ group: ["OH2AAA"] });
    await one.find(".group .chip").trigger("click");
    expect(one.emitted("update:group")).toEqual([[null]]);
  });

  it("sends one text to all of them as sendMany, empties its box and closes, opening nothing", async () => {
    const wrapper = await open();
    await wrapper.find("#msg-text").setValue("Net at 20:00");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("sendMany")).toEqual([[calls, "Net at 20:00"]]);
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(wrapper.emitted("update:group")).toEqual([[null]]);
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("closes on Esc on a wide tab as on a narrow one, and has no draft of the conversations in it", async () => {
    const wide = await open();
    await wide.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wide.emitted("update:group")).toEqual([[null]]);
    width.set(NARROW);
    const narrow = await open();
    await narrow.find(".group").trigger("keydown", { key: "Escape" });
    expect(narrow.emitted("update:group")).toEqual([[null]]);
    expect(narrow.emitted("select")).toBeUndefined();
    const talk = await pane({ group: null });
    await talk.find("#msg-text").setValue("to one only");
    await talk.setProps({ selected: null, thread: [], group: calls });
    expect(talk.find<HTMLInputElement>("#msg-text").element.value).toBe("");
  });

  it("gives way to a conversation that is open", async () => {
    const wrapper = await pane({ group: calls });
    expect(wrapper.find(".group").exists()).toBe(false);
    expect(wrapper.find(".convo-title").text()).toBe("OH2RDG");
  });
});

describe.each([
  ["wide", WIDE],
  ["narrow", NARROW],
])("MessagesPane, Esc, %s", (_name, size) => {
  beforeEach(() => width.set(size));

  it("deselects the open conversation, and the page shows the empty state or the list as it is", async () => {
    const wrapper = await pane();
    await wrapper.find(".convo").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toEqual([[null]]);
    await wrapper.setProps({ selected: null, thread: [] });
    expect(wrapper.find(".convo").exists()).toBe(false);
    expect(wrapper.find(".convo-empty").exists()).toBe(size === WIDE);
    expect(wrapper.find(".convlist").exists()).toBe(true);
    expect(wrapper.findAll(".conv.active")).toHaveLength(0);
  });

  it("deselects with Esc in an empty text box, and does nothing to the selection while the box has text in it", async () => {
    const wrapper = await pane();
    await wrapper.find("#msg-text").setValue("half a message");
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toBeUndefined();
    expect(wrapper.find<HTMLInputElement>("#msg-text").element.value).toBe("half a message");
    await wrapper.find("#msg-text").setValue("");
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toEqual([[null]]);
  });

  it("closes the Route box first, and only the next Esc deselects", async () => {
    const wrapper = await pane();
    await wrapper.find(".route-button").trigger("click");
    await wrapper.find(".route-box input").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".route-box").exists()).toBe(false);
    expect(wrapper.emitted("select")).toBeUndefined();
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toEqual([[null]]);
  });

  it("does nothing to a list with no conversation open", async () => {
    const wrapper = await pane({ selected: null, thread: [] });
    await wrapper.find(".convlist").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("select")).toBeUndefined();
    expect(wrapper.emitted("update:group")).toBeUndefined();
  });

  it("closes the group compose with Esc, and keeps it while its text box has text", async () => {
    const wrapper = await pane({ selected: null, thread: [], group: ["OH2AAA", "OH2BBB"] });
    await wrapper.find("#msg-text").setValue("Net at 20:00");
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("update:group")).toBeUndefined();
    await wrapper.find("#msg-text").setValue("");
    await wrapper.find("#msg-text").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("update:group")).toEqual([[null]]);
    expect(wrapper.emitted("select")).toBeUndefined();
  });
});
