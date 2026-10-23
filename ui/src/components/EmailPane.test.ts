import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmailPane from "@/components/EmailPane.vue";
import { incoming, message } from "@/test/fixtures";

const thread = [
  message(1, { to_call: "EMAIL-2", text: "me hello", state: "acked", attempts: 1 }),
  incoming(2, "EMAIL-2", { text: "Msg sent to jane@example.com", route: "via OH2RCH-2" }),
  message(3, { to_call: "EMAIL-2", text: "get", state: "failed", attempts: 6 }),
  message(4, { to_call: "EMAIL-2", text: "L", state: "sending", attempts: 2 }),
];

function pane(extra: Record<string, unknown> = {}) {
  return mount(EmailPane, { props: { thread, connected: true, addresses: [], attempts: { own: new Map<string, number>(), defaultCount: 6 }, ...extra } });
}

describe("EmailPane", () => {
  it("has the compose box, the three buttons and the thread under them, in that order", () => {
    const html = pane().html();
    expect([html.indexOf("mail-to"), html.indexOf("mail-tools"), html.indexOf('role="log"')].every((i) => i >= 0)).toBe(true);
    expect(html.indexOf("mail-to")).toBeLessThan(html.indexOf("mail-tools"));
    expect(html.indexOf("mail-tools")).toBeLessThan(html.indexOf('role="log"'));
  });

  it("shows every message to and from EMAIL-2 with the marks, the states and the routes", () => {
    const messages = pane().findAll(".msg");
    expect(messages.map((m) => m.classes().includes("in"))).toEqual([false, true, false, false]);
    expect(messages[0]?.text()).toContain("acked, sent once");
    expect(messages[1]?.find(".msg-route").text()).toBe("via OH2RCH-2");
    expect(messages.map((m) => (m.find(".mark").exists() ? m.find(".mark").attributes("data-mark") : null))).toEqual(["check", null, "cross", "clock"]);
  });

  it("offers Retry and Cancel as the Messages tab does", async () => {
    const wrapper = pane();
    const messages = wrapper.findAll(".msg");
    await messages[2]?.find("button").trigger("click");
    await messages[3]?.find("button").trigger("click");
    expect(wrapper.emitted("retry")).toEqual([[3]]);
    expect(wrapper.emitted("cancel")).toEqual([[4]]);
  });

  it("says there is no message with the gateway yet", () => {
    expect(pane({ thread: [] }).find(".thread").text()).toBe("No message with EMAIL-2 yet.");
  });

  it("passes up what the compose box and the buttons say", async () => {
    const wrapper = pane({ addresses: ["me"] });
    await wrapper.find("#mail-to").setValue("me");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form.compose").trigger("submit");
    await wrapper.find(".address-forget").trigger("click");
    await wrapper.findAll(".mail-tools > button")[0]?.trigger("click");
    await wrapper.findAll(".mail-tools > button")[2]?.trigger("click");
    await wrapper.find("#mail-to").setValue("jane@example.com");
    await wrapper.findAll(".mail-tools > button")[1]?.trigger("click");
    await wrapper.find("#mail-shortcut").setValue("jane");
    await wrapper.find(".mail-shortcut").trigger("submit");
    await wrapper.find(".mail-shortcut").trigger("submit");
    await wrapper.find(".mail-tools .attempts-input").setValue("3");
    expect([wrapper.emitted("send"), wrapper.emitted("forget"), wrapper.emitted("list"), wrapper.emitted("get"), wrapper.emitted("remove")]).toEqual([
      [["me", "Hello"]],
      [["me"]],
      [["me"]],
      [[]],
      [["jane"]],
    ]);
    expect(wrapper.emitted("setAttempts")).toEqual([["EMAIL-2", 3]]);
  });
});
