import { mount } from "@vue/test-utils";
import { shown } from "@/test/shown";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailPane from "@/components/EmailPane.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { incoming, message } from "@/test/fixtures";

const thread = [
  message(1, { to_call: "EMAIL-2", text: "jane@example.com Hello Pekka", state: "acked", attempts: 1 }),
  incoming(2, "EMAIL-2", { text: "Msg sent to jane@example.com", route: "via OH2RCH-2" }),
  message(3, { to_call: "EMAIL-2", text: "get", state: "failed", attempts: 6 }),
  message(4, { to_call: "EMAIL-2", text: "jane@example.com On my way", state: "sending", attempts: 2, attempts_max: 2 }),
  message(5, { to_call: "EMAIL-2", text: "bob@example.org Second mail", state: "unconfirmed", attempts: 2, attempts_max: 2 }),
  message(6, { to_call: "EMAIL-2", text: "bob@example.org Third mail", state: "rejected", attempts: 1 }),
  incoming(7, "EMAIL-2", { text: "bob@example.org Hi from Bob" }),
  message(8, { to_call: "EMAIL-2", text: "bob@example.org Last mail", state: "acked", attempts: 2 }),
];

function pane({ connected = true, ...extra }: Record<string, unknown> = {}) {
  return mount(EmailPane, {
    props: { thread, addresses: [], ...extra },
    global: withDaemon(fakeDaemon({ connected: connected as boolean })),
    attachTo: document.body,
  });
}
type Pane = ReturnType<typeof pane>;
/** The rows of the list, the newest first: the list itself is oldest first (see "the list order" below), so the row numbers here count from its bottom. */
const rows = (wrapper: Pane) => wrapper.findAll(".mail").reverse();
const bar = (wrapper: Pane, label: string) => wrapper.findAll(".mail-bar button").find((b) => b.text() === label);

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] }));
afterEach(() => vi.useRealTimers());

describe("EmailPane: the top", () => {
  it("has the one button Check email and the (i), and nothing else at the top", () => {
    const wrapper = pane();
    expect(wrapper.findAll(".mail-bar > button").map((b) => b.text())).toEqual(["Check email"]);
    expect(wrapper.findAll(".mail-bar .info-toggle")).toHaveLength(1);
    expect(wrapper.find(".info-toggle").attributes("aria-label")).toBe("About email");
    expect(wrapper.text()).not.toContain("Contacts");
    expect(wrapper.text()).not.toContain("New email");
    expect(wrapper.text()).not.toContain("Mailbox");
    wrapper.unmount();
  });

  it("explains in the (i), in two short sentences, how mail goes and what Check email does", async () => {
    const wrapper = pane();
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await wrapper.find(".info-toggle").trigger("click");
    expect(wrapper.findAll(".info-text .info-line").map((l) => l.text())).toEqual([
      "Mail goes through the internet gateway EMAIL-2, so a mail can show Not confirmed although it arrived.",
      "Check email asks the gateway for the mail it kept for you (24 hours).",
    ]);
    expect(wrapper.findAll("p.mail-meta")[0]?.text()).not.toContain("iGate");
    wrapper.unmount();
  });
});

describe("EmailPane: the box to write in", () => {
  it("is always there, last in the tab, with To, Text and Send, and no button opens it", () => {
    const wrapper = pane();
    expect(wrapper.find("form.composebar").element.nextElementSibling).toBeNull();
    expect(wrapper.find("form.composebar").element.parentElement).toBe(wrapper.find(".mailpane").element);
    expect(wrapper.find("form[aria-label='Write an email']").exists()).toBe(true);
    expect(wrapper.find("#mail-to").exists() && wrapper.find("#mail-text").exists()).toBe(true);
    expect(wrapper.find("form.composebar button[type='submit']").text()).toBe("Send");
    wrapper.unmount();
  });

  it("sends the mail up with Send, and the box stays", async () => {
    const wrapper = pane();
    await wrapper.find("#mail-to").setValue("jane@example.com");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form.composebar button[type='submit']").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["jane@example.com", "Hello"]]);
    expect(wrapper.find("form.composebar").exists()).toBe(true);
    wrapper.unmount();
  });

  it("is off with no TNC", () => {
    const wrapper = pane({ connected: false });
    expect(wrapper.find("form.composebar button[type='submit']").attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("suggests the addresses used before and passes up a forgotten one", async () => {
    const wrapper = pane({ addresses: ["carl@example.net", "jane@example.com"] });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.findAll(".suggestion").map((li) => shown(li))).toEqual(["carl@example.net", "jane@example.com"]);
    await wrapper.find(".suggestion .xbtn").trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["carl@example.net"]]);
    wrapper.unmount();
  });
});

describe("EmailPane: Check email", () => {
  it("passes get up", async () => {
    const wrapper = pane();
    await bar(wrapper, "Check email")?.trigger("click");
    expect(wrapper.emitted("get")).toEqual([[]]);
    wrapper.unmount();
  });

  it("is off while a get of ours is still being sent, and says why", async () => {
    const wrapper = pane({ thread: [message(1, { to_call: "EMAIL-2", text: "get", state: "sending", attempts: 1 })] });
    const button = bar(wrapper, "Check email");
    expect(button?.attributes("disabled")).toBeDefined();
    expect(button?.attributes("title")).toBe("Already checking");
    await button?.trigger("click");
    expect(wrapper.emitted("get")).toBeUndefined();
    await wrapper.setProps({ thread: [message(1, { to_call: "EMAIL-2", text: "get", state: "unconfirmed", attempts: 2 })] });
    expect(bar(wrapper, "Check email")?.attributes("disabled")).toBeUndefined();
    expect(bar(wrapper, "Check email")?.attributes("title")).toBeUndefined();
    wrapper.unmount();
  });

  it("is off while the TNC is not connected, and says why", () => {
    const wrapper = pane({ connected: false });
    expect(bar(wrapper, "Check email")?.attributes("disabled")).toBeDefined();
    expect(bar(wrapper, "Check email")?.attributes("title")).toBe("The TNC is not connected");
    wrapper.unmount();
  });
});

describe("EmailPane: the list", () => {
  it("is oldest first, so that the newest is next to the box", () => {
    const wrapper = pane();
    expect(wrapper.findAll(".mail").map((m) => m.find(".mail-title").text())[0]).toBe("To jane@example.com");
    expect(wrapper.findAll(".mail").at(-1)?.find(".mail-title").text()).toBe("To bob@example.org");
    wrapper.unmount();
  });

  it("has one row for each message to and from the gateway, and no bubbles", () => {
    const wrapper = pane();
    expect(rows(wrapper)).toHaveLength(8);
    expect(rows(wrapper).map((r) => r.find(".mail-title").text())).toEqual([
      "To bob@example.org",
      "From bob@example.org",
      "To bob@example.org",
      "To bob@example.org",
      "To jane@example.com",
      "Checked email",
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
      ["tone-plain"],
      ["tone-plain"],
      ["tone-plain"],
      ["tone-bad"],
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

  it("shows the get of Check email in words with no text line, and the line as sent in the title", () => {
    const wrapper = pane();
    const get = rows(wrapper)[5];
    expect(get?.find(".mail-title").text()).toBe("Checked email");
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
    expect(shown(can())).toBe("");
    await can()?.trigger("click");
    await can()?.trigger("click");
    expect(wrapper.emitted("delete")).toEqual([[1]]);
    wrapper.unmount();
  });
});
