import { describe, expect, it } from "vitest";
import {
  bytesLeft,
  canCancel,
  canDelete,
  canRetry,
  conversationName,
  conversations,
  effectivePath,
  EMAIL_GATEWAY,
  isGateway,
  attemptText,
  isHighlighted,
  markOf,
  isOverheard,
  newestIncomingByCall,
  newestIncomingId,
  peerOf,
  replyTo,
  overheardPair,
  stateText,
  textBytes,
  threadOf,
  threadUnread,
  unreadTotal,
} from "@/lib/messages";
import { dateTimeText } from "@/lib/format";
import { ago, incoming, message } from "@/test/fixtures";

const none = () => 0;

describe("messages: the other station", () => {
  it("is the sender of a message that came in and the addressee of one we sent", () => {
    expect(peerOf(incoming(1, "OH2RDG-7"))).toBe("OH2RDG-7");
    expect(peerOf(message(2, { to_call: "OH2XYZ" }))).toBe("OH2XYZ");
  });
});

describe("messages: conversations", () => {
  const rows = [
    message(1, { to_call: "OH2RDG", at: ago(900) }),
    incoming(2, "OH2RDG", { at: ago(800) }),
    incoming(3, "OH2XYZ", { at: ago(700) }),
    message(4, { to_call: "OH2RDG", at: ago(600) }),
    incoming(5, "OH2RDG", { at: ago(500) }),
    incoming(6, "OH2RDG-7", { at: ago(400) }),
  ];

  it("has one for each other station, the one with the newest message first", () => {
    const list = conversations(rows, none);
    expect(list.map((c) => c.call)).toEqual(["OH2RDG-7", "OH2RDG", "OH2XYZ"]);
    expect(list.map((c) => c.count)).toEqual([1, 4, 1]);
    expect(list[1]?.last.id).toBe(5);
  });

  it("puts a station with an SSID in a conversation of its own", () => {
    expect(conversations(rows, none).filter((c) => c.call.startsWith("OH2RDG"))).toHaveLength(2);
  });

  it("counts the messages that came in after the newest one seen, and only those", () => {
    const seen: Record<string, number> = { OH2RDG: 2, OH2XYZ: 3 };
    const list = conversations(rows, (call) => seen[call] ?? 0);
    expect(Object.fromEntries(list.map((c) => [c.call, c.unread]))).toEqual({ "OH2RDG-7": 1, OH2RDG: 1, OH2XYZ: 0 });
    expect(unreadTotal(list)).toBe(2);
  });

  it("counts everything as unread when nothing was seen, and our own messages never", () => {
    const list = conversations(rows, none);
    expect(Object.fromEntries(list.map((c) => [c.call, c.unread]))).toEqual({ "OH2RDG-7": 1, OH2RDG: 2, OH2XYZ: 1 });
  });

  it("takes the later id when two messages have the same time, whatever the order they come in", () => {
    const at = ago(10);
    const list = conversations([message(8, { at }), message(7, { at })], none);
    expect(list[0]?.last.id).toBe(8);
  });

  it("leaves the email gateway out, with its unread messages, whichever way its messages went", () => {
    const withMail = [...rows, message(7, { to_call: "EMAIL-2", text: "me hello" }), incoming(8, "EMAIL-2", { text: "ok" })];
    const list = conversations(withMail, none);
    expect(list.map((c) => c.call)).toEqual(["OH2RDG-7", "OH2RDG", "OH2XYZ"]);
    expect(unreadTotal(list)).toBe(unreadTotal(conversations(rows, none)));
    expect(threadOf(withMail, EMAIL_GATEWAY).map((r) => r.id)).toEqual([7, 8]);
  });

  it("is empty for no messages", () => {
    expect(conversations([], none)).toEqual([]);
    expect(unreadTotal([])).toBe(0);
  });
});

describe("messages: a thread", () => {
  it("is the messages with one station, both ways, the oldest first", () => {
    const rows = [incoming(5, "OH2RDG"), message(2, { to_call: "OH2RDG" }), incoming(3, "OH2XYZ"), message(9, { to_call: "OH2RDG" })];
    expect(threadOf(rows, "OH2RDG").map((r) => r.id)).toEqual([2, 5, 9]);
    expect(threadOf(rows, "NOBODY")).toEqual([]);
  });

  it("counts the messages of a thread that came in after the newest one seen", () => {
    const thread = [message(1, { to_call: "EMAIL-2" }), incoming(2, "EMAIL-2"), incoming(3, "EMAIL-2"), incoming(4, "EMAIL-2")];
    expect(threadUnread(thread, 0)).toBe(3);
    expect(threadUnread(thread, 3)).toBe(1);
    expect(threadUnread(thread, 4)).toBe(0);
    expect(threadUnread([], 0)).toBe(0);
  });

  it("knows the newest message that came in", () => {
    expect(newestIncomingId([message(9), incoming(5, "A"), incoming(3, "A")])).toBe(5);
    expect(newestIncomingId([message(9)])).toBe(0);
  });

  it("knows the newest message that came in from each station", () => {
    const newest = newestIncomingByCall([
      message(9, { to_call: "OH2RDG" }),
      incoming(5, "A"),
      incoming(3, "A"),
      incoming(4, "B"),
      incoming(8, "B", { state: "overheard", to_call: "C" }),
    ]);
    expect([...newest]).toEqual([
      ["A", 5],
      ["B", 4],
    ]);
  });
});

describe("messages: the compose box", () => {
  it("counts bytes, not characters", () => {
    expect(textBytes("hello")).toBe(5);
    expect(textBytes("åäö")).toBe(6);
    expect(textBytes("")).toBe(0);
  });

  it("says how many of the 67 bytes are left, and goes negative", () => {
    expect(bytesLeft("")).toBe(67);
    expect(bytesLeft("hello")).toBe(62);
    expect(bytesLeft("x".repeat(67))).toBe(0);
    expect(bytesLeft("x".repeat(66) + "å")).toBe(-1);
  });

  it("knows the email gateway however it is typed, and never sends to it from here", () => {
    expect([isGateway("EMAIL-2"), isGateway(" email-2 "), isGateway("EMAIL"), isGateway("EMAIL-3")]).toEqual([true, true, false, false]);
  });
});

describe("messages: the state", () => {
  it("is told with the attempts", () => {
    expect(stateText(message(1, { state: "sending", attempts: 0 }))).toBe("waiting for the radio");
    expect(stateText(message(1, { state: "sending", attempts: 2 }))).toBe("sending, attempt 2 of 6");
    expect(stateText(message(1, { state: "sending", attempts: 3, attempts_max: 10 }))).toBe("sending, attempt 3 of 10");
    expect(stateText(message(1, { state: "acked", attempts: 1 }))).toBe("acked, sent once");
    expect(stateText(message(1, { state: "acked", attempts: 3 }))).toBe("acked, sent 3 times");
    expect(stateText(message(1, { state: "rejected" }))).toBe("rejected");
    expect(stateText(message(1, { state: "failed", attempts: 6 }))).toBe("no answer after 6 attempts");
    expect(stateText(message(1, { state: "unconfirmed", attempts: 1, attempts_max: 1 }))).toBe("sent once, no ack");
    expect(stateText(message(1, { state: "unconfirmed", attempts: 2, attempts_max: 2 }))).toBe("sent twice, no ack");
    expect(stateText(message(1, { state: "cancelled", attempts: 1 }))).toBe("cancelled after 1 attempt");
    expect(stateText(incoming(1, "A"))).toBe("");
  });

  it("says a message that waits for the one before it to the same station is queued, with no attempt told", () => {
    expect(stateText(message(2, { state: "queued", attempts: 0 }))).toBe("waits for the message before");
  });

  it("offers Cancel and not Retry for a queued message: the daemon stops it as it does one being sent", () => {
    expect([canRetry(message(2, { state: "queued" })), canCancel(message(2, { state: "queued" })), canDelete(message(2, { state: "queued" }))]).toEqual([
      false,
      true,
      false,
    ]);
  });

  it("offers Retry for a message that did not get through and Cancel for one being sent", () => {
    for (const state of ["failed", "unconfirmed", "rejected", "cancelled"] as const) {
      expect([canRetry(message(1, { state })), canCancel(message(1, { state }))]).toEqual([true, false]);
    }
    expect([canRetry(message(1, { state: "sending" })), canCancel(message(1, { state: "sending" }))]).toEqual([false, true]);
    expect([canRetry(message(1, { state: "acked" })), canCancel(message(1, { state: "acked" }))]).toEqual([false, false]);
    expect([canRetry(incoming(1, "A")), canCancel(incoming(1, "A"))]).toEqual([false, false]);
  });
});

describe("messages: overheard", () => {
  const heard = message(9, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", attempts: 0, last_attempt_at: null, at: ago(100) });

  it("belongs to the pair of stations, and is a conversation only when asked for", () => {
    expect(peerOf(heard)).toBe("OH2AAA>OH2BBB");
    expect(isOverheard("OH2AAA>OH2BBB")).toBe(true);
    expect(isOverheard("OH2AAA")).toBe(false);
    expect([conversationName("OH2AAA>OH2BBB"), conversationName("OH2RDG")]).toEqual(["OH2AAA > OH2BBB", "OH2RDG"]);
    expect(replyTo("OH2AAA>OH2BBB")).toBe("OH2AAA");
    expect(replyTo("OH2RDG")).toBe("OH2RDG");
    expect(conversations([heard, incoming(1, "OH2RDG")], none)).toHaveLength(1);
    const all = conversations([heard, incoming(1, "OH2RDG", { at: ago(900) })], none, true);
    expect(all.map((c) => [c.call, c.overheard, c.unread])).toEqual([
      ["OH2AAA>OH2BBB", true, 0],
      ["OH2RDG", false, 1],
    ]);
  });

  it("is never unread, and its thread is its pair's", () => {
    expect(newestIncomingId([heard])).toBe(0);
    expect(threadOf([heard, incoming(1, "OH2AAA")], "OH2AAA>OH2BBB").map((r) => r.id)).toEqual([9]);
    expect(stateText(heard)).toBe("for OH2BBB");
  });
});

describe("messages: the path of a station", () => {
  it("is the station's own when it has one, even an empty one, else the default", () => {
    const paths = new Map([
      ["OH2RDG", "OH2RCH-2"],
      ["OH2DIR", ""],
    ]);
    expect(effectivePath(paths, "WIDE1-1", "oh2rdg")).toEqual({ text: "OH2RCH-2", own: true });
    expect(effectivePath(paths, "WIDE1-1", "OH2DIR")).toEqual({ text: "", own: true });
    expect(effectivePath(paths, "WIDE1-1", "OH2XYZ")).toEqual({ text: "WIDE1-1", own: false });
  });
});

describe("messages: the mark", () => {
  it("is a clock while a message of ours is being sent, and its title says which attempt", () => {
    expect(markOf(message(1, { state: "sending", attempts: 3, attempts_max: 6 }))).toEqual({ kind: "clock", title: "attempt 3 of 6" });
    expect(markOf(message(1, { state: "sending", attempts: 2, attempts_max: 10 }))?.title).toBe("attempt 2 of 10");
    expect(markOf(message(1, { state: "sending", attempts: 0 }))).toEqual({ kind: "clock", title: "waiting for the radio" });
    expect(attemptText(message(1, { attempts: 1, attempts_max: 3 }))).toBe("attempt 1 of 3");
  });

  it("is a clock for a queued message too, its title saying that it waits for the message before", () => {
    expect(markOf(message(2, { state: "queued", attempts: 0 }))).toEqual({ kind: "clock", title: "waits for the message before" });
  });

  it("is a check once acked, with the time of the ack for the title", () => {
    const acked = markOf(message(1, { state: "acked", acked_at: "2026-10-21T12:34:56Z" }));
    expect(acked?.kind).toBe("check");
    expect(acked?.title).toBe(`acked ${dateTimeText("2026-10-21T12:34:56Z")}`);
    expect(markOf(message(1, { state: "acked", acked_at: null }))).toEqual({ kind: "check", title: "acked" });
  });

  it("is a cross for a message that failed or was rejected, with the state for the title, and a dash for one that was cancelled", () => {
    expect(markOf(message(1, { state: "failed" }))).toEqual({ kind: "cross", title: "failed" });
    expect(markOf(message(1, { state: "rejected" }))).toEqual({ kind: "cross", title: "rejected" });
    expect(markOf(message(1, { state: "cancelled" }))).toEqual({ kind: "dash", title: "cancelled" });
  });

  it("is a hollow check for a message that was sent and whose ack is not expected", () => {
    expect(markOf(message(1, { state: "unconfirmed", attempts: 2, attempts_max: 2 }))).toEqual({ kind: "hollow", title: "sent, no ack expected" });
  });

  it("is none on a message that came in or was overheard", () => {
    expect(markOf(incoming(1, "OH2RDG"))).toBeNull();
    expect(markOf(message(1, { direction: "in", state: "overheard", from_call: "A", to_call: "B" }))).toBeNull();
  });
});

describe("messages: the highlight", () => {
  it("is on a conversation with something not seen unless it is the open one", () => {
    expect(isHighlighted(2, "OH2RDG", "OH2XYZ")).toBe(true);
    expect(isHighlighted(2, "OH2RDG", null)).toBe(true);
    expect(isHighlighted(2, "OH2RDG", "OH2RDG")).toBe(false);
    expect(isHighlighted(0, "OH2RDG", "OH2XYZ")).toBe(false);
  });
});

describe("messages: an overheard pair", () => {
  it("is the sender and the addressee of the row's call, and none for a conversation", () => {
    expect(overheardPair("OH2AAA>OH2BBB")).toEqual(["OH2AAA", "OH2BBB"]);
    expect(overheardPair("OH2AAA-7>OH2BBB-1")).toEqual(["OH2AAA-7", "OH2BBB-1"]);
    expect(overheardPair("OH2RDG")).toBeNull();
  });
});
