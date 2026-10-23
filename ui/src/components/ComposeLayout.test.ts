// One layout for writing on every tab (Bulletins, Email, Objects; Messages is the model): the list fills the tab, the box to write in is the last thing in it, and in the box the counter is left of the buttons, the
// secondary button left of the primary one, which is the last. The behaviour of each box (sending, editing, the two presses of a delete) is tested with the tab; this is only where things are.
import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import BulletinsPane from "@/components/BulletinsPane.vue";
import EmailPane from "@/components/EmailPane.vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { NOW, ago, bulletin, incoming, message, ownObject } from "@/test/fixtures";

function bulletins() {
  const rows = [bulletin("BLN1", { text: "Road closed" })];
  return mount(BulletinsPane, {
    props: { bulletins: new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r])), ownBulletins: new Map<string, OwnBulletinRow>(), call: "OH2GBA", now: NOW },
  });
}

function email(thread = [message(1, { to_call: "EMAIL-2", text: "jane@example.com Hello" }), incoming(2, "EMAIL-2", { text: "bob@example.org Hi" })]) {
  return mount(EmailPane, { props: { thread, connected: true, addresses: [] }, attachTo: document.body });
}

function objects() {
  const table = new Map([["LEADER", ownObject("LEADER", { created_at: ago(900) })]]);
  const form = useOwnObjects(table, ref({ lat: 60.17, lon: 24.94 }), () => true, { show: vi.fn() } as unknown as Panel);
  const wrapper = mount(ObjectsPane, { props: { objects: table, form, fallbackPath: "", now: NOW } });
  return { wrapper, form };
}

const barOf = (wrapper: VueWrapper) => wrapper.find<HTMLFormElement>("form.composebar");
const kids = (wrapper: VueWrapper) => [...(wrapper.element as Element).children];

/** The box is the last thing in the tab, after the list. */
function expectAtTheBottom(wrapper: VueWrapper, list: string): void {
  const last = kids(wrapper).at(-1);
  expect(last).toBe(barOf(wrapper).element);
  const listAt = kids(wrapper).findIndex((c) => c.matches(list));
  expect(listAt).toBeGreaterThanOrEqual(0);
  expect(listAt).toBeLessThan(kids(wrapper).length - 1);
}

/** In the line under the fields: the counter before the buttons, Cancel (a plain button) before the primary one, which is the last and the one that submits. */
function expectTheBar(wrapper: VueWrapper, primary: string, secondary: string | null): void {
  const foot = barOf(wrapper).find(".composebar-foot");
  const buttons = foot.findAll("button");
  const last = buttons.at(-1);
  expect(last?.text()).toBe(primary);
  expect(last?.classes()).toContain("primary");
  expect(last?.attributes("type")).toBe("submit");
  if (secondary !== null) expect(buttons.at(-2)?.text()).toBe(secondary);
  expect(buttons.filter((b) => b.classes().includes("primary") && b.text() === primary)).toHaveLength(1);
  const counter = foot.find(".compose-left").element;
  expect(counter).not.toBeNull();
  for (const b of foot.findAll("button").filter((x) => !foot.find(".composebar-aside").element.contains(x.element))) {
    expect(counter.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
  expect(counter.closest("form")).toBe(barOf(wrapper).element);
}

describe("Bulletins", () => {
  it("has the board and under it, last in the tab, the box with the counter and Post at its right", () => {
    const wrapper = bulletins();
    expectAtTheBottom(wrapper, ".boardpane");
    expectTheBar(wrapper, "Post", null);
    expect(barOf(wrapper).find(".compose-left").text()).toBe("67 left");
    expect(barOf(wrapper).find("#post-kind").exists()).toBe(true);
    expect(barOf(wrapper).find("#post-text").exists()).toBe(true);
  });

  it("keeps the board newest first in its sections", () => {
    const rows = [bulletin("BLN1", { text: "old", last_heard: ago(900) }), bulletin("BLN2", { text: "new", last_heard: ago(30) })];
    const wrapper = mount(BulletinsPane, {
      props: { bulletins: new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r])), ownBulletins: new Map<string, OwnBulletinRow>(), call: null, now: NOW },
    });
    expect(wrapper.findAll(".bulletin-text").map((t) => t.text())).toEqual(["new", "old"]);
  });
});

describe("Email", () => {
  it("has the list and under it, last in the tab, the box with the counter and Send at its right, with no button to open it", () => {
    const wrapper = email();
    expectAtTheBottom(wrapper, ".maillist-wrap");
    expectTheBar(wrapper, "Send", null);
    expect(barOf(wrapper).find(".compose-left").text()).toMatch(/left$/);
    wrapper.unmount();
  });

  it("lists the mail oldest first, the newest at the bottom next to the box", () => {
    const wrapper = email();
    expect(wrapper.findAll(".mail").map((m) => m.find(".mail-title").text())).toEqual(["To jane@example.com", "From bob@example.org"]);
    const newest = wrapper.findAll(".mail").at(-1)?.element ?? document.body;
    expect(newest.compareDocumentPosition(barOf(wrapper).element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    wrapper.unmount();
  });

  it("scrolls the list to the newest when mail comes in", async () => {
    const wrapper = email();
    const list = wrapper.find(".maillist-wrap").element;
    Object.defineProperty(list, "scrollHeight", { configurable: true, value: 500 });
    await wrapper.setProps({ thread: [...(wrapper.props("thread") as []), incoming(3, "EMAIL-2", { text: "bob@example.org Again" })] });
    await wrapper.vm.$nextTick();
    expect(list.scrollTop).toBe(500);
    wrapper.unmount();
  });

  it("opens the suggestions of the address upward, inside the box", async () => {
    const wrapper = mount(EmailPane, { props: { thread: [], connected: true, addresses: ["carl@example.net"] }, attachTo: document.body });
    await wrapper.find("#mail-to").trigger("focus");
    expect(barOf(wrapper).find(".mail-address .suggestions").exists()).toBe(true);
    wrapper.unmount();
  });
});

describe("Objects", () => {
  it("has the list and, once New is pressed, the form last in the tab: Pick on the map at its left, the counter, Cancel and Save at its right", async () => {
    const { wrapper, form } = objects();
    expect(barOf(wrapper).exists()).toBe(false);
    form.start();
    await wrapper.vm.$nextTick();
    expectAtTheBottom(wrapper, ".objectlist");
    expectTheBar(wrapper, "Save", "Cancel");
    const aside = barOf(wrapper).find(".composebar-aside");
    expect(aside.findAll("button").map((b) => b.text())).toEqual(["Pick on the map"]);
    expect(barOf(wrapper).find(".compose-left").text()).toBe("43 left");
  });

  it("has the toolbar with New on top and the list between it and the form", async () => {
    const { wrapper, form } = objects();
    form.start();
    await wrapper.vm.$nextTick();
    expect(kids(wrapper).map((c) => c.className.split(" ")[0])).toEqual(["toolbar", "objectlist", "composebar"]);
  });

  it("names the form for a new object and for the one being changed", async () => {
    const { wrapper, form } = objects();
    form.start();
    await wrapper.vm.$nextTick();
    expect(barOf(wrapper).attributes("aria-label")).toBe("New object");
    form.edit("LEADER");
    await wrapper.vm.$nextTick();
    expect(barOf(wrapper).attributes("aria-label")).toBe("Edit LEADER");
  });
});
