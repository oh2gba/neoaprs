import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, shallowReactive } from "vue";
import { useEmail } from "@/composables/useEmail";
import { usePanel } from "@/composables/usePanel";
import type { Command, MessageRow } from "@/protocol/protocol";
import { incoming, message } from "@/test/fixtures";

function setUp(send = vi.fn((_command: Command) => true), ...rows: MessageRow[]) {
  const messages = shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
  let made: { panel: ReturnType<typeof usePanel>; mail: ReturnType<typeof useEmail> } | undefined;
  mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        made = { panel, mail: useEmail(messages, panel, send) };
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return { send, messages, ...made };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

describe("useEmail: what it sends", () => {
  it("sends mail as one message to EMAIL-2 with the addressee, a space and the text, and remembers the addressee", () => {
    const { send, mail } = setUp();
    mail.sendMail("jane@example.com", "Hello");
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "jane@example.com Hello" });
    expect(mail.addresses.value).toEqual(["jane@example.com"]);
    mail.sendMail("me", "Hi");
    expect(mail.addresses.value).toEqual(["me", "jane@example.com"]);
  });

  it("does not remember an addressee whose message was not sent", () => {
    const { mail } = setUp(vi.fn(() => false));
    mail.sendMail("me", "Hi");
    expect(mail.addresses.value).toEqual([]);
  });

  it("forgets an addressee", () => {
    const { mail } = setUp();
    mail.sendMail("me", "Hi");
    mail.forget("me");
    expect(mail.addresses.value).toEqual([]);
  });

  it("checks the mail by sending the text get, and remembers no addressee for it", () => {
    const { send, mail } = setUp();
    mail.checkMail();
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "get" });
    expect(mail.addresses.value).toEqual([]);
  });
});

describe("useEmail: what the page sends", () => {
  it("sends mail and the get at once as messages to the gateway, with no setting of attempts before them", () => {
    const { send, mail } = setUp();
    mail.sendMail("me", "Hi");
    mail.checkMail();
    expect(send.mock.calls.map((c) => c[0])).toEqual([
      { cmd: "send_message", to: "EMAIL-2", text: "me Hi" },
      { cmd: "send_message", to: "EMAIL-2", text: "get" },
    ]);
    expect(mail.addresses.value).toEqual(["me"]);
  });

  it("remembers no addressee for a message that could not be sent", () => {
    const { mail } = setUp(vi.fn(() => false));
    mail.sendMail("me", "one");
    expect(mail.addresses.value).toEqual([]);
  });
});

describe("useEmail: the new rows and Delete", () => {
  const rows = [incoming(2, "EMAIL-2", { text: "held mail" }), incoming(3, "EMAIL-2", { text: "more" })];

  it("takes what came in since the tab was last on show for new, for as long as the tab stays on show", async () => {
    const { panel, messages, mail } = setUp(undefined, ...rows);
    expect(mail.freshAfter.value).toBe(0);
    panel.show("email");
    await nextTick();
    expect(mail.freshAfter.value).toBe(0);
    messages.set("4", incoming(4, "EMAIL-2"));
    await nextTick();
    expect(mail.freshAfter.value).toBe(0);
    expect(mail.unread.value).toBe(0);
    panel.show("packets");
    await nextTick();
    panel.show("email");
    await nextTick();
    expect(mail.freshAfter.value).toBe(4);
  });

  it("asks the daemon to delete a row", () => {
    const { send, mail } = setUp();
    mail.remove(7);
    expect(send).toHaveBeenLastCalledWith({ cmd: "message_delete", id: 7 });
    expect(mail.addresses.value).toEqual([]);
  });
});

describe("useEmail: the thread and the badge", () => {
  const rows = [
    message(1, { to_call: "EMAIL-2", text: "me hello" }),
    incoming(2, "EMAIL-2", { text: "ack" }),
    message(3, { to_call: "OH2RDG" }),
    incoming(4, "OH2RDG"),
    incoming(5, "EMAIL-2", { text: "held mail" }),
  ];

  it("has every message to and from the gateway and none else, and counts those that came in", () => {
    const { mail } = setUp(undefined, ...rows);
    expect(mail.thread.value.map((r) => r.id)).toEqual([1, 2, 5]);
    expect(mail.unread.value).toBe(2);
  });

  it("has seen them only while the Email tab is on show, and counts the next one when it is not", async () => {
    const { panel, messages, mail } = setUp(undefined, ...rows);
    panel.show("messages");
    await nextTick();
    expect(mail.unread.value).toBe(2);
    panel.show("email");
    await nextTick();
    expect(mail.unread.value).toBe(0);
    messages.set("6", incoming(6, "EMAIL-2"));
    await nextTick();
    expect(mail.unread.value).toBe(0);
    panel.show("packets");
    messages.set("7", incoming(7, "EMAIL-2"));
    await nextTick();
    expect(mail.unread.value).toBe(1);
    panel.show("email");
    await nextTick();
    expect(mail.unread.value).toBe(0);
  });

  it("keeps counting while the panel is folded", async () => {
    const { panel, messages, mail } = setUp(undefined, ...rows);
    panel.show("email");
    await nextTick();
    panel.collapsed.value = true;
    messages.set("6", incoming(6, "EMAIL-2"));
    await nextTick();
    expect(mail.unread.value).toBe(1);
    panel.collapsed.value = false;
    await nextTick();
    expect(mail.unread.value).toBe(0);
  });

  it("does not take a message from another station for the gateway's, nor the Messages tab's seen mark", async () => {
    const { panel, mail } = setUp(undefined, ...rows);
    panel.show("email");
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.read.EMAIL-2")).toBe("5");
    expect(localStorage.getItem("NeoAPRS.read.OH2RDG")).toBeNull();
    expect(mail.thread.value.every((r) => r.from_call === "EMAIL-2" || r.to_call === "EMAIL-2")).toBe(true);
  });
});
