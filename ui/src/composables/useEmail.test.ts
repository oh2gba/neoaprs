import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, shallowReactive, shallowRef, type Ref } from "vue";
import { useEmail } from "@/composables/useEmail";
import { usePanel } from "@/composables/usePanel";
import type { Command, MessageRow } from "@/protocol/protocol";
import { incoming, message } from "@/test/fixtures";

function setUp(send = vi.fn((_command: Command) => true), ...rows: MessageRow[]) {
  const attempts = shallowRef<ReadonlyMap<string, number>>(new Map([["EMAIL-2", 2]]));
  return withAttempts(attempts, send, ...rows);
}

function withAttempts(attempts: Ref<ReadonlyMap<string, number>>, send = vi.fn((_command: Command) => true), ...rows: MessageRow[]) {
  const messages = shallowReactive(new Map(rows.map((r) => [String(r.id), r])));
  let made: { panel: ReturnType<typeof usePanel>; mail: ReturnType<typeof useEmail> } | undefined;
  mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        made = { panel, mail: useEmail(messages, panel, send, attempts) };
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return { send, messages, attempts, ...made };
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

  it("makes a shortcut by sending the name, a space and the address, and remembers the name as an addressee", () => {
    const { send, mail } = setUp();
    mail.registerShortcut(" john ", "jane@example.com");
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "john jane@example.com" });
    expect(mail.addresses.value).toEqual(["john"]);
  });

  it("sends the three commands as the texts name L, name R and get", () => {
    const { send, mail } = setUp();
    mail.listShortcuts("me");
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "me L" });
    mail.removeShortcut("jane");
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "jane R" });
    mail.getHeld();
    expect(send).toHaveBeenLastCalledWith({ cmd: "send_message", to: "EMAIL-2", text: "get" });
    expect(mail.addresses.value).toEqual([]);
  });
});

describe("useEmail: the gateway's attempts", () => {
  const none = (): Ref<ReadonlyMap<string, number>> => shallowRef<ReadonlyMap<string, number>>(new Map());
  type Send = ReturnType<typeof vi.fn<(command: Command) => boolean>>;
  const sent = (send: Send): Command[] => send.mock.calls.map((c) => c[0]);
  const sets = (send: Send): Command[] => sent(send).filter((c) => c.cmd === "set_station_attempts");
  const texts = (send: Send): Command[] => sent(send).filter((c) => c.cmd === "send_message");
  const said = (send: Send): string[] => texts(send).map((c) => (c.cmd === "send_message" ? c.text : ""));

  it("sends the mail at once, and sets nothing, when the gateway has a count of its own", () => {
    const { send, mail } = setUp();
    mail.sendMail("me", "Hi");
    expect(sets(send)).toEqual([]);
    expect(texts(send)).toEqual([{ cmd: "send_message", to: "EMAIL-2", text: "me Hi" }]);
  });

  it("sets the gateway to 2 attempts the first time mail is sent, and sends the mail when the daemon has told the count", async () => {
    vi.useFakeTimers();
    const attempts = none();
    const { send, mail } = withAttempts(attempts);
    mail.sendMail("me", "Hi");
    expect(send.mock.calls.map((c) => c[0])).toEqual([{ cmd: "set_station_attempts", call: "EMAIL-2", attempts: 2 }]);
    expect(mail.addresses.value).toEqual([]);
    attempts.value = new Map([["EMAIL-2", 2]]);
    await nextTick();
    expect(send.mock.calls.map((c) => c[0])).toEqual([
      { cmd: "set_station_attempts", call: "EMAIL-2", attempts: 2 },
      { cmd: "send_message", to: "EMAIL-2", text: "me Hi" },
    ]);
    expect(mail.addresses.value).toEqual(["me"]);
    await vi.advanceTimersByTimeAsync(10000);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("holds every mail sent meanwhile, in order, and sends the mail anyway if the daemon does not answer in time", async () => {
    vi.useFakeTimers();
    const { send, mail } = withAttempts(none());
    mail.sendMail("me", "one");
    mail.sendMail("you", "two");
    expect(send).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3100);
    expect(said(send)).toEqual(["me one", "you two"]);
    expect(sets(send)).toHaveLength(1);
  });

  it("does it once: not again when the count was cleared on purpose, not after a reload either", async () => {
    vi.useFakeTimers();
    const attempts = none();
    const first = withAttempts(attempts);
    first.mail.sendMail("me", "one");
    attempts.value = new Map([["EMAIL-2", 2]]);
    await nextTick();
    attempts.value = new Map();
    await nextTick();
    first.mail.sendMail("me", "two");
    expect(sets(first.send)).toHaveLength(1);
    expect(said(first.send)).toEqual(["me one", "me two"]);
    const reloaded = withAttempts(none());
    reloaded.mail.sendMail("me", "three");
    expect(sets(reloaded.send)).toEqual([]);
    expect(texts(reloaded.send)).toHaveLength(1);
  });

  it("counts a count the operator set himself as done, so that clearing it later does not bring the 2 back", () => {
    const attempts = shallowRef<ReadonlyMap<string, number>>(new Map([["EMAIL-2", 4]]));
    const { send, mail } = withAttempts(attempts);
    mail.sendMail("me", "one");
    attempts.value = new Map();
    mail.sendMail("me", "two");
    expect(sets(send)).toEqual([]);
    expect(texts(send)).toHaveLength(2);
  });

  it("does it for a command or a new shortcut as for mail, and remembers none of them as an addressee", async () => {
    vi.useFakeTimers();
    const attempts = none();
    const { send, mail } = withAttempts(attempts);
    mail.getHeld();
    mail.listShortcuts("me");
    mail.registerShortcut("jane", "jane@example.com");
    expect(sent(send)).toEqual([{ cmd: "set_station_attempts", call: "EMAIL-2", attempts: 2 }]);
    attempts.value = new Map([["EMAIL-2", 2]]);
    await nextTick();
    expect(said(send)).toEqual(["get", "me L", "jane jane@example.com"]);
    expect(mail.addresses.value).toEqual(["jane"]);
  });

  it("sends the mail anyway when the set cannot be sent (the socket is down)", () => {
    const { send, mail } = withAttempts(
      none(),
      vi.fn(() => false),
    );
    mail.sendMail("me", "one");
    expect(send).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem("NeoAPRS.emailattempts")).toBeNull();
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
