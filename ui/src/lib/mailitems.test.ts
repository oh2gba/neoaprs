import { describe, expect, it } from "vitest";
import { mailItem, mailItems, mailState, mailTime } from "@/lib/mailitems";
import { incoming, message } from "@/test/fixtures";

const sent = (text: string) => mailItem(message(1, { to_call: "EMAIL-2", text }));

describe("mailItem: what we sent", () => {
  it("is a mail to the first word with the rest as its text", () => {
    expect(sent("jane@example.com Hello Pekka")).toMatchObject({ kind: "mail", title: "To jane@example.com", text: "Hello Pekka" });
    expect(sent("me hello")).toMatchObject({ kind: "mail", title: "To me", text: "hello" });
  });

  it("reads the gateway's commands in words, with no text line", () => {
    expect(sent("get")).toMatchObject({ kind: "get", title: "Checked for mail", text: "" });
    expect(sent("GET")).toMatchObject({ kind: "get" });
    expect(sent("me jane@example.com")).toMatchObject({ kind: "contact", title: "Added contact me (jane@example.com)", text: "" });
    expect(sent("me L")).toMatchObject({ kind: "list", title: "Asked for the contact list (me)" });
    expect(sent("me R")).toMatchObject({ kind: "remove", title: "Removed contact me" });
  });

  it("keeps a mail to an address whose text is an address, or an L, a mail", () => {
    expect(sent("jane@example.com bob@example.com")).toMatchObject({ kind: "mail", text: "bob@example.com" });
    expect(sent("jane@example.com L")).toMatchObject({ kind: "mail", text: "L" });
  });

  it("shows a line of one word as it was sent, and keeps the line for the title", () => {
    expect(sent("L")).toMatchObject({ kind: "mail", title: "To L", text: "" });
    expect(sent("  me   hello ").line).toBe("me   hello");
  });
});

describe("mailItem: what came in", () => {
  const from = (text: string) => mailItem(incoming(2, "EMAIL-2", { text }));

  it("is From EMAIL-2 for the gateway's own replies", () => {
    expect(from("Msg sent to jane@example.com")).toMatchObject({ kind: "reply", title: "From EMAIL-2", text: "Msg sent to jane@example.com" });
    expect(from("No email address found!")).toMatchObject({ kind: "reply", title: "From EMAIL-2" });
  });

  it("is From the address when the text starts with one: the mail the gateway forwards", () => {
    expect(from("jane@example.com Hello Pekka")).toMatchObject({ kind: "forwarded", title: "From jane@example.com", text: "Hello Pekka" });
    expect(from("<jane@example.com> Hello")).toMatchObject({ kind: "forwarded", title: "From jane@example.com", text: "Hello" });
    expect(from("jane@example.com: Hello")).toMatchObject({ kind: "forwarded", title: "From jane@example.com", text: "Hello" });
    expect(from("jane@example.com")).toMatchObject({ kind: "reply" });
  });
});

describe("mailItems", () => {
  it("lists the oldest first", () => {
    expect(mailItems([message(1), message(3), message(2)]).map((i) => i.row.id)).toEqual([1, 2, 3]);
  });
});

describe("mailState", () => {
  const state = (extra: Parameters<typeof message>[1]) => mailState(message(1, extra));

  it("says Sending with the attempt, or that the radio is waited for", () => {
    expect(state({ state: "sending", attempts: 2, attempts_max: 2 })).toEqual({ word: "Sending (2 of 2)", tone: "plain" });
    expect(state({ state: "sending", attempts: 0 })?.word).toBe("Waiting for the radio");
  });

  it("says Delivered for an ack and Rejected for a reject", () => {
    expect(state({ state: "acked" })).toEqual({ word: "Delivered", tone: "ok" });
    expect(state({ state: "rejected" })).toEqual({ word: "Rejected", tone: "bad" });
    expect(state({ state: "cancelled" })?.word).toBe("Cancelled");
  });

  it("says Not confirmed, never failed, for a mail whose attempts ran out", () => {
    expect(state({ state: "unconfirmed" })).toEqual({ word: "Not confirmed", tone: "plain" });
    expect(state({ state: "failed" })).toEqual({ word: "Not confirmed", tone: "plain" });
  });

  it("has none for what came in", () => {
    expect(mailState(incoming(2, "EMAIL-2"))).toBeNull();
  });
});

describe("mailTime", () => {
  const noon = new Date(2026, 9, 23, 12, 0).getTime();

  it("is the clock for today and the day and month before", () => {
    expect(mailTime(new Date(2026, 9, 23, 9, 5).toISOString(), noon)).toBe("09:05");
    expect(mailTime(new Date(2026, 9, 21, 18, 41).toISOString(), noon)).toBe("21 Oct 18:41");
  });
});
