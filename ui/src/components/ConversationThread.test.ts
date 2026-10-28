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
