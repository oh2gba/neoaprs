import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmailPane from "@/components/EmailPane.vue";
import { incoming, message } from "@/test/fixtures";

const thread = [
  message(1, { to_call: "EMAIL-2", text: "me hello", state: "acked", attempts: 1 }),
  incoming(2, "EMAIL-2", { text: "Msg sent to jane@example.com", route: "via OH2RCH-2" }),
  message(3, { to_call: "EMAIL-2", text: "get", state: "failed", attempts: 6 }),
  message(4, { to_call: "EMAIL-2", text: "L", state: "sending", attempts: 2 }),
  message(5, { to_call: "EMAIL-2", text: "me hi", state: "unconfirmed", attempts: 2, attempts_max: 2 }),
  message(6, { to_call: "EMAIL-2", text: "me no", state: "rejected", attempts: 1 }),
];

function pane(extra: Record<string, unknown> = {}) {
  return mount(EmailPane, { props: { thread, connected: true, addresses: [], ...extra } });
}

describe("EmailPane", () => {
  it("has Send an email, the mailbox and the shortcuts, and the thread under them, in that order", () => {
    const wrapper = pane();
    const html = wrapper.html();
    expect(wrapper.findAll("strong").map((s) => s.text())).toEqual(["Send an email", "Mailbox", "Shortcut"]);
    expect([html.indexOf("mail-to"), html.indexOf("mail-tools"), html.indexOf('role="log"')].every((i) => i >= 0)).toBe(true);
    expect(html.indexOf("mail-to")).toBeLessThan(html.indexOf("mail-tools"));
    expect(html.indexOf("mail-tools")).toBeLessThan(html.indexOf('role="log"'));
  });

  it("shows every message to and from EMAIL-2 with the marks, the states and the routes", () => {
    const messages = pane().findAll(".msg");
    expect(messages.map((m) => m.classes().includes("in"))).toEqual([false, true, false, false, false, false]);
    expect(messages[0]?.text()).toContain("acked, sent once");
    expect(messages[1]?.find(".msg-route").text()).toBe("via OH2RCH-2");
    expect(messages.map((m) => (m.find(".mark").exists() ? m.find(".mark").attributes("data-mark") : null))).toEqual([
      "check",
      null,
      "hollow",
      "clock",
      "hollow",
      "cross",
    ]);
  });

  it("says sent, not confirmed, and never failed, for a mail whose ack did not come back", () => {
    const messages = pane().findAll(".msg");
    expect(messages[2]?.find(".msg-state").text()).toBe("sent 6 times, not confirmed");
    expect(messages[4]?.find(".msg-state").text()).toBe("sent twice, not confirmed");
    expect(messages[2]?.find(".msg-state").classes()).not.toContain("state-failed");
    expect(messages[2]?.find(".mark").attributes("title")).toContain("iGate");
    expect(messages[5]?.find(".msg-state").text()).toBe("rejected");
    expect(pane().text()).not.toContain("failed");
  });

  it("marks what the gateway sent as its answer, and nothing of ours", () => {
    const messages = pane().findAll(".msg");
    expect(messages[1]?.find(".msg-from").text()).toBe("EMAIL-2 answers");
    expect(pane().findAll(".msg-from")).toHaveLength(1);
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
    await wrapper.find("#mail-shortcut").setValue("jane");
    await wrapper.find("#mail-address").setValue("jane@example.com");
    await wrapper.find("form.mail-shortcut").trigger("submit");
    const buttons = wrapper.findAll(".mail-tools button");
    await buttons.find((b) => b.text() === "Fetch held mail")?.trigger("click");
    await buttons.find((b) => b.text() === "Email the list")?.trigger("click");
    await buttons.find((b) => b.text() === "Remove")?.trigger("click");
    await wrapper
      .findAll(".mail-tools button")
      .find((b) => b.text() === "sure?")
      ?.trigger("click");
    expect([
      wrapper.emitted("send"),
      wrapper.emitted("forget"),
      wrapper.emitted("register"),
      wrapper.emitted("get"),
      wrapper.emitted("list"),
      wrapper.emitted("remove"),
    ]).toEqual([[["me", "Hello"]], [["me"]], [["jane", "jane@example.com"]], [[]], [["jane"]], [["jane"]]]);
  });
});
