import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref, shallowReactive } from "vue";
import { useConversations, useReadMarks } from "@/composables/useConversations";
import type { MessageRow } from "@/protocol/protocol";
import { incoming, message } from "@/test/fixtures";

function table(...rows: MessageRow[]) {
  return shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
}

beforeEach(() => localStorage.clear());

describe("useReadMarks", () => {
  it("remembers the highest id seen for each call in the browser, and never goes back", () => {
    const marks = useReadMarks();
    expect(marks.readUpTo("OH2RDG")).toBe(0);
    marks.mark("OH2RDG", 7);
    marks.mark("OH2RDG", 4);
    expect(marks.readUpTo("OH2RDG")).toBe(7);
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBe("7");
    expect(useReadMarks().readUpTo("OH2RDG")).toBe(7);
    expect(useReadMarks().readUpTo("OH2XYZ")).toBe(0);
  });

  it("brings a mark above every message of the thread down to the newest one, once", () => {
    localStorage.setItem("NeoAPRS.read.OH2RDG", "60");
    const marks = useReadMarks();
    marks.settle("OH2RDG", 55);
    expect(marks.readUpTo("OH2RDG")).toBe(55);
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBe("55");
    marks.settle("OH2RDG", 40);
    expect(marks.readUpTo("OH2RDG")).toBe(55);
    localStorage.setItem("NeoAPRS.read.OH2XYZ", "5");
    marks.settle("OH2XYZ", 9);
    expect(marks.readUpTo("OH2XYZ")).toBe(5);
  });

  it("ignores a stored value that is no number, and works without localStorage", () => {
    localStorage.setItem("NeoAPRS.read.A", "many");
    expect(useReadMarks().readUpTo("A")).toBe(0);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const marks = useReadMarks();
    marks.mark("B", 3);
    expect(marks.readUpTo("B")).toBe(3);
    vi.restoreAllMocks();
  });
});

describe("useConversations", () => {
  it("counts the unread messages of every conversation, and the total", () => {
    const messages = table(message(1), incoming(2, "OH2RDG"), incoming(3, "OH2XYZ"), incoming(4, "OH2XYZ"));
    const talk = useConversations(messages, ref(false));
    expect(talk.list.value.map((c) => [c.call, c.unread])).toEqual([
      ["OH2XYZ", 2],
      ["OH2RDG", 1],
    ]);
    expect(talk.unread.value).toBe(3);
  });

  it("counts the messages that follow a restored database as unread although the browser remembers higher ids", () => {
    localStorage.setItem("NeoAPRS.read.OH2RDG", "60");
    const messages = table(incoming(2, "OH2RDG"), incoming(5, "OH2RDG"));
    const talk = useConversations(messages, ref(false));
    expect(talk.unread.value).toBe(0);
    messages.set("6", incoming(6, "OH2RDG"));
    expect(talk.unread.value).toBe(1);
  });

  it("does not count a conversation as seen until the tab is on show with it open", async () => {
    const messages = table(incoming(2, "OH2RDG"));
    const viewing = ref(false);
    const talk = useConversations(messages, viewing);
    talk.selected.value = "OH2RDG";
    await flushPromises();
    expect(talk.unread.value).toBe(1);
    viewing.value = true;
    await flushPromises();
    expect(talk.unread.value).toBe(0);
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBe("2");
  });

  it("marks a conversation seen when it is opened while the tab is on show, and not the others", async () => {
    const messages = table(incoming(2, "OH2RDG"), incoming(3, "OH2XYZ"));
    const talk = useConversations(messages, ref(true));
    expect(talk.unread.value).toBe(2);
    talk.selected.value = "OH2XYZ";
    await flushPromises();
    expect(talk.list.value.map((c) => [c.call, c.unread])).toEqual([
      ["OH2XYZ", 0],
      ["OH2RDG", 1],
    ]);
  });

  it("keeps a message that arrives in the open conversation seen, and counts one that arrives in another", async () => {
    const messages = table(incoming(2, "OH2RDG"));
    const talk = useConversations(messages, ref(true));
    talk.selected.value = "OH2RDG";
    await flushPromises();
    messages.set("3", incoming(3, "OH2RDG"));
    messages.set("4", incoming(4, "OH2XYZ"));
    await flushPromises();
    expect(talk.unread.value).toBe(1);
    expect(talk.thread.value.map((m) => m.id)).toEqual([2, 3]);
  });

  it("keeps counting a message in the open conversation while the tab is not on show, and has seen it when it is", async () => {
    const messages = table(incoming(2, "OH2RDG"));
    const viewing = ref(true);
    const talk = useConversations(messages, viewing);
    talk.selected.value = "OH2RDG";
    await flushPromises();
    expect(talk.unread.value).toBe(0);
    viewing.value = false;
    messages.set("3", incoming(3, "OH2RDG"));
    await flushPromises();
    expect(talk.unread.value).toBe(1);
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBe("2");
    viewing.value = true;
    await flushPromises();
    expect(talk.unread.value).toBe(0);
  });

  it("starts from what the browser remembers", () => {
    localStorage.setItem("NeoAPRS.read.OH2RDG", "2");
    const messages = table(incoming(2, "OH2RDG"), incoming(3, "OH2RDG"));
    expect(useConversations(messages, ref(false)).unread.value).toBe(1);
  });

  it("lists the messages we only overheard when asked, and never counts them as unread", () => {
    const heard = message(5, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB" });
    const messages = table(incoming(2, "OH2RDG"), heard);
    const show = ref(false);
    const talk = useConversations(messages, ref(false), show);
    expect(talk.list.value.map((c) => c.call)).toEqual(["OH2RDG"]);
    show.value = true;
    expect(talk.list.value.map((c) => c.call).sort()).toEqual(["OH2AAA>OH2BBB", "OH2RDG"]);
    expect(talk.unread.value).toBe(1);
  });

  it("can have a conversation open that has no message yet", () => {
    const talk = useConversations(table(), ref(true));
    talk.selected.value = "OH2NEW";
    expect(talk.thread.value).toEqual([]);
    expect(talk.list.value).toEqual([]);
  });
});
