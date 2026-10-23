import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MessageMark from "@/components/MessageMark.vue";
import type { MessageRow } from "@/protocol/protocol";
import { incoming, message } from "@/test/fixtures";

const mark = (row: MessageRow) => mount(MessageMark, { props: { row } });

describe("MessageMark", () => {
  it("draws a clock with the attempt for the title while a message is being sent", () => {
    const wrapper = mark(message(1, { state: "sending", attempts: 3, attempts_max: 6 }));
    expect(wrapper.attributes("data-mark")).toBe("clock");
    expect(wrapper.attributes("title")).toBe("attempt 3 of 6");
    expect(wrapper.attributes("aria-label")).toBe("attempt 3 of 6");
    expect(wrapper.find("svg circle").exists()).toBe(true);
  });

  it("draws a check, a cross and a dash, each with the state for the title", () => {
    const check = mark(message(1, { state: "acked", acked_at: "2026-10-21T12:34:56Z" }));
    expect([check.attributes("data-mark"), check.attributes("title")?.startsWith("acked ")]).toEqual(["check", true]);
    for (const [state, kind] of [
      ["failed", "cross"],
      ["rejected", "cross"],
      ["cancelled", "dash"],
    ] as const) {
      const wrapper = mark(message(1, { state }));
      expect([wrapper.attributes("data-mark"), wrapper.attributes("title")]).toEqual([kind, state]);
      expect(wrapper.find("svg path").exists()).toBe(true);
    }
  });

  it("draws a hollow check, a ring with a check in it, titled 'sent, no ack expected', for an unconfirmed message", () => {
    const wrapper = mark(message(1, { state: "unconfirmed", attempts: 2, attempts_max: 2 }));
    expect(wrapper.attributes("data-mark")).toBe("hollow");
    expect(wrapper.attributes("title")).toBe("sent, no ack expected");
    expect(wrapper.attributes("aria-label")).toBe("sent, no ack expected");
    expect(wrapper.find("svg circle").exists()).toBe(true);
    expect(wrapper.find("svg path").exists()).toBe(true);
    expect(wrapper.find("svg").attributes("fill")).toBe("none");
  });

  it("draws nothing for a message that came in", () => {
    expect(mark(incoming(1, "OH2RDG")).find(".mark").exists()).toBe(false);
  });

  it("uses the colour of the text only, so that both colour schemes show it", () => {
    const svg = mark(message(1, { state: "acked" })).find("svg");
    expect(svg.attributes("stroke")).toBe("currentColor");
    expect(svg.html()).not.toMatch(/#[0-9a-f]{3,6}|rgb\(/i);
  });
});
