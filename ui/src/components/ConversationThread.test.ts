import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ConversationThread from "@/components/ConversationThread.vue";
import { message } from "@/test/fixtures";

describe("a queued message in the conversation", () => {
  it("is a quiet bubble that says it waits for the message before, with a clock and Cancel but no Retry, while the one before it is sent", () => {
    const thread = [message(1, { text: "first", state: "sending", attempts: 1 }), message(2, { text: "second", state: "queued", attempts: 0 })];
    const wrapper = mount(ConversationThread, { props: { thread, peer: "OH2RDG" } });
    const [sending, queued] = wrapper.findAll(".bubble");
    expect(sending?.classes()).not.toContain("queued");
    expect(queued?.classes()).toContain("queued");
    expect(queued?.find(".msg-state").text()).toBe("waits for the message before");
    expect(queued?.find(".mark").attributes("data-mark")).toBe("clock");
    expect(queued?.findAll("button").map((b) => b.text())).toEqual(["Cancel"]);
  });
});

describe("a failed message in the conversation", () => {
  it("shows its reason where the attempts are told, in the same place, with Retry as for any failed message", () => {
    const thread = [
      message(1, { text: "long", state: "failed", attempts: 0, failure: "too_long_for_radio" }),
      message(2, { text: "unanswered", state: "failed", attempts: 4 }),
    ];
    const wrapper = mount(ConversationThread, { props: { thread, peer: "OH2RDG" } });
    const [refused, unanswered] = wrapper.findAll(".bubble");
    expect(refused?.find(".msg-state").text()).toBe("too long for the radio");
    expect(refused?.text()).not.toContain("no answer");
    expect(refused?.find(".msg-state").classes()).toContain("state-failed");
    expect(refused?.findAll(".bubble-meta").length).toBe(1);
    expect(refused?.findAll("button").map((b) => b.text())).toContain("Retry");
    expect(unanswered?.find(".msg-state").text()).toBe("no answer after 4 attempts");
  });
});

describe("encrypted messages and keys in the conversation", () => {
  const mounted = (thread: ReturnType<typeof message>[]) => mount(ConversationThread, { props: { thread, peer: "OH2RDG" } });

  it("marks a message that was read with a padlock and shows its text, and one that cannot be read here as encrypted, not as the letters that came", () => {
    const wrapper = mounted([
      message(1, { text: "Moi, täällä ok", state: "acked", seal: "open" }),
      message(2, {
        direction: "in",
        from_call: "OH2RDG",
        to_call: "OH2GBA",
        text: "!EAQIDBAUGq8z6pHk2Aun7/N4nDjtT1TgF8GQi4UWwXn4",
        state: "received",
        seal: "shut",
      }),
    ]);
    const [open, shut] = wrapper.findAll(".bubble");
    expect(open?.find(".bubble-text").text()).toBe("Moi, täällä ok");
    expect(open?.find("[data-mark='lock']").attributes("title")).toBe("Encrypted");
    expect(shut?.find(".bubble-text").text()).toBe("Encrypted; no key to read it here");
    expect(shut?.find(".bubble-text").classes()).toContain("sealed");
    expect(shut?.find("[data-mark='lock']").attributes("title")).toBe("Encrypted; no key to read it here");
  });

  it("shows a key announcement as what it is, ours and theirs, with a key mark, and one that differs from the key kept as not taken", () => {
    const wrapper = mounted([
      message(1, { text: "!KhSDS6YIjgKTWQfj0A8M8GuVgrzMI3ARSKyXNn1aQD2U", state: "acked", seal: "key" }),
      message(2, {
        direction: "in",
        from_call: "OH2RDG",
        to_call: "OH2GBA",
        text: "!KhSDS6YIjgKTWQfj0A8M8GuVgrzMI3ARSKyXNn1aQD2U",
        state: "received",
        seal: "key",
      }),
      message(3, {
        direction: "in",
        from_call: "OH2RDG",
        to_call: "OH2GBA",
        text: "!KhSDS6YIjgKTWQfj0A8M8GuVgrzMI3ARSKyXNn1aQD2U",
        state: "received",
        seal: "key_other",
      }),
    ]);
    expect(wrapper.findAll(".bubble-text").map((b) => b.text())).toEqual(["Your key", "Its key", "A different key: not taken"]);
    expect(wrapper.findAll("[data-mark='key']")).toHaveLength(3);
    expect(wrapper.findAll(".bubble-text").every((b) => b.classes().includes("sealed"))).toBe(true);
  });

  it("shows a plain message with no such mark", () => {
    const wrapper = mounted([message(1, { text: "plain", state: "acked" })]);
    expect(wrapper.find("[data-mark='lock']").exists()).toBe(false);
    expect(wrapper.find("[data-mark='key']").exists()).toBe(false);
    expect(wrapper.find(".bubble-text").classes()).not.toContain("sealed");
  });
});
