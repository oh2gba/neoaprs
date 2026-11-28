import { beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope } from "vue";
import { useChat } from "@/composables/useChat";
import type { ChatFreshMessage, ChatLineRow } from "@/protocol/protocol";
import { fakeDaemon, tell, type FakeDaemon } from "@/test/context";

const line = (id: number, over: Partial<ChatLineRow> = {}): ChatLineRow => ({
  id,
  at: "2026-10-21T12:00:00Z",
  call: "OH2XYZ",
  text: `line ${id}`,
  ours: false,
  ...over,
});
const table = (...rows: ChatLineRow[]): ReadonlyMap<string, ChatLineRow> => new Map(rows.map((r) => [String(r.id), r]));
const fresh: ChatFreshMessage = { type: "chat_fresh", count: 1, id: 2, call: "OH3ABC", text: "hi" };

let daemon: FakeDaemon;
let announce: ReturnType<typeof vi.fn>;
let chat: ReturnType<typeof useChat>;

beforeEach(() => {
  localStorage.clear();
  daemon = fakeDaemon({ chatState: { state: "ok" } });
  announce = vi.fn();
  chat = effectScope().run(() => useChat(daemon, daemon.panel, announce))!;
});

describe("useChat", () => {
  it("lowers the stored mark when the server's ids started again, so new lines count", async () => {
    localStorage.setItem("NeoAPRS.chatseen", "500");
    chat = effectScope().run(() => useChat(daemon, daemon.panel, announce))!;
    await tell(daemon, { chatLines: table(line(1), line(2)) });
    expect(localStorage.getItem("NeoAPRS.chatseen")).toBe("2");
    await tell(daemon, { chatLines: table(line(1), line(2), line(3)) });
    expect(chat.unread.value).toBe(1);
  });

  it("clears the draft only when the line said comes back as a newer line of ours", async () => {
    await tell(daemon, { chatLines: table(line(1, { text: "73", ours: true })) });
    chat.draft.value = "73";
    expect(chat.say()).toBe(true);
    await tell(daemon, { chatLines: table(line(1, { text: "73", ours: true }), line(2, { call: "OH3ABC" })) });
    expect(chat.draft.value).toBe("73");
    expect(chat.busy.value).toBe(true);
    await tell(daemon, {
      lastError: { cmd: "chat_say", key: null, code: "chat.rate", params: {}, text: "", id: null, n: 1 },
    });
    expect(chat.draft.value).toBe("73");
    expect(chat.say()).toBe(true);
    await tell(daemon, { chatLines: table(line(1, { text: "73", ours: true }), line(3, { text: "7 3", ours: true })) });
    expect(chat.draft.value).toBe("");
    expect(chat.busy.value).toBe(false);
  });

  it("rings for a new line of others only while the HF tests tab is not in front", async () => {
    await tell(daemon, { chatFresh: fresh });
    expect(announce).toHaveBeenCalledTimes(1);
    daemon.panel.show("skeds");
    await tell(daemon, { chatFresh: { ...fresh, text: "again" } });
    expect(announce).toHaveBeenCalledTimes(1);
  });
});
