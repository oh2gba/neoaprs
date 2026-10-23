import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailPane from "@/components/EmailPane.vue";
import { incoming, message } from "@/test/fixtures";

const thread = [
  message(1, { to_call: "EMAIL-2", text: "jane@example.com Hello Pekka", state: "acked", attempts: 1 }),
  incoming(2, "EMAIL-2", { text: "Msg sent to jane@example.com", route: "via OH2RCH-2" }),
  message(3, { to_call: "EMAIL-2", text: "get", state: "failed", attempts: 6 }),
  message(4, { to_call: "EMAIL-2", text: "jane@example.com On my way", state: "sending", attempts: 2, attempts_max: 2 }),
  message(5, { to_call: "EMAIL-2", text: "me jane@example.com", state: "unconfirmed", attempts: 2, attempts_max: 2 }),
  message(6, { to_call: "EMAIL-2", text: "me R", state: "rejected", attempts: 1 }),
  incoming(7, "EMAIL-2", { text: "bob@example.org Hi from Bob" }),
  message(8, { to_call: "EMAIL-2", text: "me L", state: "acked", attempts: 2 }),
];

function pane(extra: Record<string, unknown> = {}) {
  return mount(EmailPane, { props: { thread, connected: true, addresses: [], ...extra }, attachTo: document.body });
}
type Pane = ReturnType<typeof pane>;
const rows = (wrapper: Pane) => wrapper.findAll(".mail");
const bar = (wrapper: Pane, label: string) => wrapper.findAll(".mail-bar button").find((b) => b.text() === label);

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] }));
afterEach(() => vi.useRealTimers());

const panelButton = (wrapper: Pane, label: string) => wrapper.findAll("section[aria-label='Contacts'] button").find((b) => b.text() === label);

describe("EmailPane: the top", () => {
  it("has the buttons New email, Contacts and Check for mail and an (i), all of one kind, and no form open", () => {
    const wrapper = pane();
    expect(wrapper.findAll(".mail-bar > button").map((b) => b.text())).toEqual(["New email", "Contacts", "Check for mail"]);
    expect(wrapper.findAll(".mail-bar > button").map((b) => b.classes().filter((c) => c !== "primary"))).toEqual([["btn"], ["btn"], ["btn"]]);
    expect(bar(wrapper, "New email")?.classes()).toContain("primary");
    expect(wrapper.findAll(".mail-bar .info-toggle")).toHaveLength(1);
    expect(wrapper.find(".info-toggle").attributes("aria-label")).toBe("About email");
    expect(wrapper.find("form").exists()).toBe(false);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    wrapper.unmount();
  });

  it("explains in the (i), in three short sentences, how mail goes, who can email you and what Check for mail does", async () => {
    const wrapper = pane();
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await wrapper.find(".info-toggle").trigger("click");
    const lines = wrapper.findAll(".info-text .info-line").map((l) => l.text());
    expect(lines).toEqual([
      "Mail goes through the internet gateway EMAIL-2 via an iGate, so a mail can say Not confirmed although it arrived.",
      "Only your contacts can email you; their mail arrives here.",
      "If your radio missed one, Check for mail asks the gateway to send again what it kept (it keeps mail for 24 hours).",
    ]);
    expect(wrapper.findAll("p.mail-meta")[0]?.text()).not.toContain("iGate");
    wrapper.unmount();
  });

  it("opens the New email form, and Send passes the mail up and closes it", async () => {
    const wrapper = pane({ addresses: ["me"] });
    await bar(wrapper, "New email")?.trigger("click");
    expect(wrapper.find("form[aria-label='New email']").exists()).toBe(true);
    await wrapper.find("#mail-to").setValue("me");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["me", "Hello"]]);
    expect(wrapper.find("form").exists()).toBe(false);
    wrapper.unmount();
  });

  it("closes the form with Cancel and with the New email button again, and passes up a forgotten addressee", async () => {
    const wrapper = pane({ addresses: ["carl@example.net"] });
    await bar(wrapper, "New email")?.trigger("click");
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find(".suggestion:not(.contact-pick) .xbtn").trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["carl@example.net"]]);
    await wrapper
      .findAll("form button")
      .find((b) => b.text() === "Cancel")
      ?.trigger("click");
    expect(wrapper.find("form").exists()).toBe(false);
    expect(wrapper.emitted("send")).toBeUndefined();
    await bar(wrapper, "New email")?.trigger("click");
    await bar(wrapper, "New email")?.trigger("click");
    expect(wrapper.find("form").exists()).toBe(false);
    wrapper.unmount();
  });

  it("suggests the contacts of the thread first in New email, with their address, then the addressees used before", async () => {
    const wrapper = pane({ addresses: ["me", "carl@example.net"] });
    await bar(wrapper, "New email")?.trigger("click");
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.findAll(".suggestion").map((li) => li.text())).toEqual(["mejane@example.com", "carl@example.net"]);
    wrapper.unmount();
  });
});

describe("EmailPane: Contacts", () => {
  it("opens the panel in place of New email, and the button closes it again", async () => {
    const wrapper = pane();
    await bar(wrapper, "New email")?.trigger("click");
    await bar(wrapper, "Contacts")?.trigger("click");
    expect(wrapper.find("form[aria-label='New email']").exists()).toBe(false);
    expect(wrapper.find("section[aria-label='Contacts']").exists()).toBe(true);
    expect(bar(wrapper, "Contacts")?.attributes("aria-expanded")).toBe("true");
    await bar(wrapper, "Contacts")?.trigger("click");
    expect(wrapper.find("section[aria-label='Contacts']").exists()).toBe(false);
    wrapper.unmount();
  });

  it("lists the contacts that the thread makes: me is there although its removal was rejected, and says it is not confirmed", async () => {
    const wrapper = pane();
    await bar(wrapper, "Contacts")?.trigger("click");
    expect(
      wrapper.findAll(".contact").map((c) => [c.find(".contact-name").text(), c.find(".contact-address").text(), c.find(".contact-state").text()]),
    ).toEqual([["me", "jane@example.com", "Not confirmed"]]);
    wrapper.unmount();
  });

  it("passes up Add contact, Email me the list and Remove (after sure?) from the panel", async () => {
    const wrapper = pane();
    await bar(wrapper, "Contacts")?.trigger("click");
    await wrapper.find("#contact-name").setValue("bob");
    await wrapper.find("#contact-address").setValue("bob@example.org");
    await wrapper.find("form[aria-label='Add contact']").trigger("submit");
    await panelButton(wrapper, "Email me the list")?.trigger("click");
    await panelButton(wrapper, "Remove")?.trigger("click");
    await panelButton(wrapper, "sure?")?.trigger("click");
    expect([wrapper.emitted("add"), wrapper.emitted("list"), wrapper.emitted("remove")]).toEqual([[["bob", "bob@example.org"]], [["me"]], [["me"]]]);
    await panelButton(wrapper, "Close")?.trigger("click");
    expect(wrapper.find("section[aria-label='Contacts']").exists()).toBe(false);
    wrapper.unmount();
  });

  it("opens New email to the contact when Mail is pressed, with the name in To and the focus in the text", async () => {
    const wrapper = pane();
    await bar(wrapper, "Contacts")?.trigger("click");
    await panelButton(wrapper, "Mail")?.trigger("click");
    expect(wrapper.find("section[aria-label='Contacts']").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("me");
    expect(document.activeElement).toBe(wrapper.find("#mail-text").element);
    await wrapper.find("#mail-text").setValue("Hi");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["me", "Hi"]]);
    wrapper.unmount();
  });

  it("opens New email empty with its own button after a Mail", async () => {
    const wrapper = pane();
    await bar(wrapper, "Contacts")?.trigger("click");
    await panelButton(wrapper, "Mail")?.trigger("click");
    await bar(wrapper, "New email")?.trigger("click");
    await bar(wrapper, "New email")?.trigger("click");
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("");
    wrapper.unmount();
  });
});

describe("EmailPane: Check for mail", () => {
  it("sends get up, and opens no form", async () => {
    const wrapper = pane();
    await bar(wrapper, "Check for mail")?.trigger("click");
    expect(wrapper.emitted("get")).toEqual([[]]);
    expect(wrapper.find("form").exists()).toBe(false);
    wrapper.unmount();
  });

  it("is off while a get of ours is still being sent, and says why", async () => {
    const wrapper = pane({ thread: [message(1, { to_call: "EMAIL-2", text: "get", state: "sending", attempts: 1 })] });
    const button = bar(wrapper, "Check for mail");
    expect(button?.attributes("disabled")).toBeDefined();
    expect(button?.attributes("title")).toBe("Already checking");
    await button?.trigger("click");
    expect(wrapper.emitted("get")).toBeUndefined();
    await wrapper.setProps({ thread: [message(1, { to_call: "EMAIL-2", text: "get", state: "unconfirmed", attempts: 2 })] });
    expect(bar(wrapper, "Check for mail")?.attributes("disabled")).toBeUndefined();
    expect(bar(wrapper, "Check for mail")?.attributes("title")).toBeUndefined();
    wrapper.unmount();
  });

  it("is off while the TNC is not connected, and says why", () => {
    const wrapper = pane({ connected: false });
    expect(bar(wrapper, "Check for mail")?.attributes("disabled")).toBeDefined();
    expect(bar(wrapper, "Check for mail")?.attributes("title")).toBe("The TNC is not connected");
    wrapper.unmount();
  });

  it("leaves the New email and Contacts buttons on while the TNC is not connected", () => {
    const wrapper = pane({ connected: false, thread: [] });
    expect(bar(wrapper, "New email")?.attributes("disabled")).toBeUndefined();
    expect(bar(wrapper, "Contacts")?.attributes("disabled")).toBeUndefined();
    wrapper.unmount();
  });
});

describe("EmailPane: the list", () => {
  it("has one row for each message to and from the gateway, the newest first, and no bubbles", () => {
    const wrapper = pane();
    expect(rows(wrapper)).toHaveLength(8);
    expect(rows(wrapper).map((r) => r.find(".mail-title").text())).toEqual([
      "Asked for the contact list (me)",
      "From bob@example.org",
      "Removed contact me",
      "Added contact me (jane@example.com)",
      "To jane@example.com",
      "Checked for mail",
      "From EMAIL-2",
      "To jane@example.com",
    ]);
    expect(wrapper.find(".msg").exists()).toBe(false);
    expect(wrapper.find(".thread").exists()).toBe(false);
    wrapper.unmount();
  });

  it("says each state of ours in words, with its mark: Sending, Delivered, Not confirmed, Rejected", () => {
    const wrapper = pane();
    const states = rows(wrapper).map((r) => [
      r.find(".mail-state").exists() ? r.find(".mail-state").text() : null,
      r.find(".mark").exists() ? r.find(".mark").attributes("data-mark") : null,
    ]);
    expect(states).toEqual([
      ["Delivered", "check"],
      [null, null],
      ["Rejected", "cross"],
      ["Not confirmed", "hollow"],
      ["Sending (2 of 2)", "clock"],
      ["Not confirmed", "hollow"],
      [null, null],
      ["Delivered", "check"],
    ]);
    expect(wrapper.text()).not.toContain("failed");
    wrapper.unmount();
  });

  it("colours Delivered and Rejected and leaves Not confirmed plain, and explains Not confirmed in the title of its mark only", () => {
    const wrapper = pane();
    const states = wrapper.findAll(".mail-state");
    expect(states.map((s) => s.classes().filter((c) => c.startsWith("tone-")))).toEqual([
      ["tone-ok"],
      ["tone-bad"],
      ["tone-plain"],
      ["tone-plain"],
      ["tone-plain"],
      ["tone-ok"],
    ]);
    expect(wrapper.findAll(".mark-hollow")[0]?.attributes("title")).toContain("iGate");
    wrapper.unmount();
  });

  it("shows the gateway's replies as From EMAIL-2 and the mail it forwards as From the address", () => {
    const wrapper = pane();
    const reply = rows(wrapper)[6];
    expect(reply?.find(".mail-title").text()).toBe("From EMAIL-2");
    expect(reply?.find(".mail-text").text()).toBe("Msg sent to jane@example.com");
    expect(reply?.find(".mail-state").exists()).toBe(false);
    const forwarded = rows(wrapper)[1];
    expect(forwarded?.find(".mail-title").text()).toBe("From bob@example.org");
    expect(forwarded?.find(".mail-text").text()).toBe("Hi from Bob");
    wrapper.unmount();
  });

  it("shows the commands in words with no text line, and the line as sent in the title", () => {
    const wrapper = pane();
    const get = rows(wrapper)[5];
    expect(get?.find(".mail-title").text()).toBe("Checked for mail");
    expect(get?.find(".mail-text").exists()).toBe(false);
    expect(get?.find(".mail-body").attributes("title")).toBe("get");
    expect(rows(wrapper)[7]?.find(".mail-text").text()).toBe("Hello Pekka");
    expect(rows(wrapper)[7]?.find(".mail-body").attributes("title")).toBe("jane@example.com Hello Pekka");
    wrapper.unmount();
  });

  it("has no row for the gateway's acks: a mail they settle is one row with its state", () => {
    const wrapper = pane({ thread: [message(1, { to_call: "EMAIL-2", text: "me Hi", state: "acked", attempts: 2 })] });
    expect(rows(wrapper)).toHaveLength(1);
    expect(rows(wrapper)[0]?.find(".mail-state").text()).toBe("Delivered");
    wrapper.unmount();
  });

  it("says there is no mail yet", () => {
    const wrapper = pane({ thread: [] });
    expect(wrapper.find(".empty").text()).toBe("No mail yet.");
    expect(wrapper.find("ul.maillist").exists()).toBe(false);
    wrapper.unmount();
  });

  it("opens a row on a click to show the whole text, the time and the route, and closes it again", async () => {
    const wrapper = pane();
    const reply = rows(wrapper)[6];
    expect(reply?.find(".mail-detail").exists()).toBe(false);
    await reply?.find(".mail-body").trigger("click");
    expect(reply?.classes()).toContain("open");
    expect(reply?.find(".mail-body").attributes("aria-expanded")).toBe("true");
    expect(reply?.find(".mail-detail").text()).toContain("via OH2RCH-2");
    await reply?.find(".mail-body").trigger("click");
    expect(reply?.find(".mail-detail").exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows the time in each row, short with the whole date and time in its title", () => {
    const wrapper = pane();
    const time = rows(wrapper)[0]?.find(".mail-meta span[title]:not(.mark)");
    expect(time?.text()).toMatch(/^(\d\d:\d\d|\d{1,2} \w{3} \d\d:\d\d)$/);
    expect(time?.attributes("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
    wrapper.unmount();
  });
});

describe("EmailPane: unread rows and the actions on a row", () => {
  it("makes the rows that came in after the seen mark bold, and none of ours", () => {
    const wrapper = pane({ freshAfter: 2 });
    expect(rows(wrapper).map((r) => r.classes().includes("fresh"))).toEqual([false, true, false, false, false, false, false, false]);
    wrapper.unmount();
  });

  it("makes none bold when it is not told what was seen", () => {
    const wrapper = pane();
    expect(wrapper.find(".mail.fresh").exists()).toBe(false);
    wrapper.unmount();
  });

  it("offers Retry on a mail that is not confirmed, rejected or cancelled and Cancel on one being sent", async () => {
    const wrapper = pane();
    const buttons = (r: ReturnType<Pane["findAll"]>[number]) => r.findAll(".mail-meta .btn").map((b) => b.text());
    expect(rows(wrapper).map(buttons)).toEqual([[], [], ["Retry"], ["Retry"], ["Cancel"], ["Retry"], [], []]);
    await rows(wrapper)[5]?.find(".mail-meta .btn").trigger("click");
    await rows(wrapper)[4]?.find(".mail-meta .btn").trigger("click");
    expect([wrapper.emitted("retry"), wrapper.emitted("cancel")]).toEqual([[[3]], [[4]]]);
    wrapper.unmount();
  });

  it("deletes a row with its trash can after a second press, and forgets the first press after 5 seconds", async () => {
    const wrapper = pane();
    const can = () => rows(wrapper)[7]?.find(".mail-delete");
    expect(can()?.attributes("aria-label")).toBe("Delete: To jane@example.com");
    await can()?.trigger("click");
    expect(can()?.text()).toBe("sure?");
    expect(wrapper.emitted("delete")).toBeUndefined();
    vi.advanceTimersByTime(5000);
    await wrapper.vm.$nextTick();
    expect(can()?.text()).toBe("");
    await can()?.trigger("click");
    await can()?.trigger("click");
    expect(wrapper.emitted("delete")).toEqual([[1]]);
    wrapper.unmount();
  });
});
