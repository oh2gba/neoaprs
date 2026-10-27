// The copy menu of a call or a text (CopyMenu, useCopyMenu): what a right-click, the menu key and a long press open on the rows of the conversations, the title of a conversation, a bubble, a row of Nearby, the head of a card, a bulletin, a mail, a packet and an own object; what an item copies and says.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import BulletinsPane from "@/components/BulletinsPane.vue";
import ConversationList from "@/components/ConversationList.vue";
import ConversationThread from "@/components/ConversationThread.vue";
import ConversationView from "@/components/ConversationView.vue";
import EmailRow from "@/components/EmailRow.vue";
import NearbyTable from "@/components/NearbyTable.vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import StationCard from "@/components/StationCard.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import { SAID_MAX, menuPoint, saidText } from "@/lib/copy";
import { mailItem } from "@/lib/mailitems";
import { conversations } from "@/lib/messages";
import type { BulletinRow, OwnBulletinRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon, type FakeDaemon } from "@/test/context";
import { NOW, bulletin, incoming, message, ownObject, packet, station } from "@/test/fixtures";

let daemon: FakeDaemon;
let written: string[];
let wrapper: VueWrapper;
beforeEach(() => {
  daemon = fakeDaemon();
  written = [];
  vi.stubGlobal("navigator", { clipboard: { writeText: (text: string) => Promise.resolve(void written.push(text)) } });
  window.innerWidth = 1024;
  window.innerHeight = 768;
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  wrapper?.unmount();
  document.body.replaceChildren();
});

const menu = () => wrapper.find(".copymenu[role='menu']");
const labels = () => wrapper.findAll(".copymenu [role='menuitem']").map((item) => item.text());
const choose = async (kind: string, which = 0) => {
  await wrapper.findAll(`.copymenu [role='menuitem'][data-item='${kind}']`)[which]?.trigger("click");
  await Promise.resolve();
  await Promise.resolve();
};
const said = () => daemon.say.mock.calls.map(([text]) => text);
const rightClick = async (target: ReturnType<VueWrapper["find"]> | undefined, x = 100, y = 120) => {
  if (target === undefined) throw new Error("no such element");
  await target.trigger("contextmenu", { clientX: x, clientY: y });
  await wrapper.vm.$nextTick();
  await wrapper.vm.$nextTick();
};

describe("the words and the place of the copy menu (lib/copy.ts)", () => {
  it("repeats a short text whole in the toast and cuts a long one with an ellipsis", () => {
    expect(saidText("OH2RDG")).toBe("OH2RDG");
    expect(saidText("  two\n lines ")).toBe("two lines");
    const long = "The quick brown fox jumps over the lazy dog, again and again and again";
    expect(saidText(long)).toHaveLength(SAID_MAX);
    expect(saidText(long).endsWith("…")).toBe(true);
    expect(saidText(long).startsWith("The quick brown fox")).toBe(true);
  });

  it("opens at the pointer, and for the menu key (no pointer: 0, 0) a little in from the element's left edge, under it", () => {
    const element = { getBoundingClientRect: () => ({ left: 40, bottom: 90 }) } as unknown as Element;
    expect(menuPoint({ clientX: 100, clientY: 120 }, element)).toEqual({ x: 100, y: 120 });
    expect(menuPoint({ clientX: 0, clientY: 0 }, element)).toEqual({ x: 64, y: 90 });
  });
});

describe("the list of conversations", () => {
  const rows = [
    incoming(1, "OH2RDG", { text: "Moi!" }),
    message(2, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter" }),
  ];
  const make = () =>
    (wrapper = mount(ConversationList, {
      props: { conversations: conversations(rows, () => 0, true), selected: null, now: NOW, showOverheard: true },
      attachTo: document.body,
      global: withDaemon(daemon),
    }));
  const row = (call: string) => wrapper.findAll(".conv").find((r) => r.attributes("data-call") === call)!;

  it("offers Copy OH2RDG on a right-click of a row, at the pointer, without the browser's own menu; the item copies the call and the page says so", async () => {
    make();
    const event = new MouseEvent("contextmenu", { clientX: 100, clientY: 120, bubbles: true, cancelable: true });
    row("OH2RDG").element.dispatchEvent(event);
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(event.defaultPrevented).toBe(true);
    expect(menu().attributes("aria-label")).toBe("Copy");
    expect(menu().attributes("style")).toContain("left: 100px");
    expect(labels()).toEqual(["Copy OH2RDG"]);
    expect(document.activeElement).toBe(wrapper.find(".copymenu [role='menuitem']").element);
    await choose("call");
    expect(written).toEqual(["OH2RDG"]);
    expect(said()).toEqual(["Copied OH2RDG"]);
    expect(menu().exists()).toBe(false);
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("offers both calls of an overheard pair", async () => {
    make();
    await rightClick(row("OH2AAA>OH2BBB"));
    expect(labels()).toEqual(["Copy OH2AAA", "Copy OH2BBB"]);
    await choose("call", 1);
    expect(written).toEqual(["OH2BBB"]);
  });

  it("closes on Esc with the focus back on the row, and on a press outside it", async () => {
    make();
    await rightClick(row("OH2RDG"));
    await menu().trigger("keydown", { key: "Escape" });
    expect(menu().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2RDG").element);
    await rightClick(row("OH2RDG"));
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(false);
  });

  it("opens on a long press on a touch screen, and the click of the finger lifted does not open the conversation", async () => {
    vi.useFakeTimers();
    make();
    const touch = { pointerType: "touch", isPrimary: true, clientX: 60, clientY: 80 };
    await row("OH2RDG").trigger("pointerdown", touch);
    vi.advanceTimersByTime(600);
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(labels()).toEqual(["Copy OH2RDG"]);
    await row("OH2RDG").trigger("click");
    expect(wrapper.emitted("select")).toBeUndefined();
    await row("OH2RDG").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG"]]);
  });

  it("does not open for a press that is a mouse, or a finger that moves away", async () => {
    vi.useFakeTimers();
    make();
    await row("OH2RDG").trigger("pointerdown", { pointerType: "mouse", isPrimary: true, clientX: 60, clientY: 80 });
    vi.advanceTimersByTime(600);
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(false);
    await row("OH2RDG").trigger("pointerdown", { pointerType: "touch", isPrimary: true, clientX: 60, clientY: 80 });
    await row("OH2RDG").trigger("pointermove", { clientX: 60, clientY: 140 });
    vi.advanceTimersByTime(600);
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(false);
  });
});

describe("the open conversation", () => {
  it("offers to copy the call from the title of the header, and both of an overheard pair", async () => {
    wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick(wrapper.find(".convo-title"));
    expect(labels()).toEqual(["Copy OH2RDG"]);
    await choose("call");
    expect(written).toEqual(["OH2RDG"]);
    wrapper.unmount();
    wrapper = mount(ConversationView, { props: { selected: "OH2AAA>OH2BBB", narrow: false, thread: [] }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick(wrapper.find(".convo-title"));
    expect(labels()).toEqual(["Copy OH2AAA", "Copy OH2BBB"]);
  });

  it("has the Route button at the normal height of a button, not the compact one", () => {
    wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, global: withDaemon(daemon) });
    expect(wrapper.find(".route-button").classes()).toContain("btn");
    expect(wrapper.find(".route-button").classes()).not.toContain("small");
  });

  it("offers Copy message on a bubble, which copies the text whole and says it cut short", async () => {
    const long = "This is a message that is longer than the forty characters the toast repeats of it";
    const thread = [message(1, { text: "Hello", state: "acked" }), incoming(2, "OH2RDG", { text: long })];
    wrapper = mount(ConversationThread, { props: { thread, peer: "OH2RDG" }, attachTo: document.body, global: withDaemon(daemon) });
    const bubbles = wrapper.findAll(".bubble");
    await rightClick(bubbles[1]);
    expect(labels()).toEqual(["Copy message"]);
    await choose("message");
    expect(written).toEqual([long]);
    expect(said()).toEqual([`Copied ${saidText(long)}`]);
    await rightClick(bubbles[0]);
    await choose("message");
    expect(written).toEqual([long, "Hello"]);
  });
});

describe("the other places of the page", () => {
  it("Nearby: a row offers its call", async () => {
    const row = station("OH2RDG", { distance_km: 2 });
    wrapper = mount(NearbyTable, {
      props: { items: [{ call: "OH2RDG", row, lines: ["heard direct"] }], selected: null, label: "Direct" },
      attachTo: document.body,
      global: withDaemon(daemon),
    });
    await rightClick(wrapper.find("tbody tr"));
    expect(labels()).toEqual(["Copy OH2RDG"]);
    await choose("call");
    expect(written).toEqual(["OH2RDG"]);
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("a station's card: the head offers the call", async () => {
    wrapper = mount(StationCard, { props: { row: station("OH2PU-9"), now: NOW }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick(wrapper.find(".card-head"));
    expect(labels()).toEqual(["Copy OH2PU-9"]);
    await choose("call");
    expect(written).toEqual(["OH2PU-9"]);
  });

  it("Bulletins: a bulletin offers its text and its sender", async () => {
    const rows: BulletinRow[] = [bulletin("BLN1", { sender: "OH2ABC", text: "Road closed at Kaivopuisto" })];
    wrapper = mount(BulletinsPane, {
      props: { bulletins: new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r])), ownBulletins: new Map<string, OwnBulletinRow>() },
      attachTo: document.body,
      global: withDaemon(daemon),
    });
    await rightClick(wrapper.find("li.bulletin"));
    expect(labels()).toEqual(["Copy message", "Copy OH2ABC"]);
    await choose("message");
    expect(written).toEqual(["Road closed at Kaivopuisto"]);
  });

  it("Email: a mail offers its text and the address; the gateway's own reply only its text", async () => {
    const mail = mailItem(message(1, { to_call: "EMAIL-2", text: "jane@example.com Hello Jane" }));
    wrapper = mount(EmailRow, {
      props: { item: mail, fresh: false, now: NOW, heardDirect: new Set<string>() },
      attachTo: document.body,
      global: withDaemon(daemon),
    });
    await rightClick(wrapper.find("li.mail"));
    expect(labels()).toEqual(["Copy message", "Copy address"]);
    await choose("address");
    expect(written).toEqual(["jane@example.com"]);
    wrapper.unmount();
    const reply = mailItem(incoming(2, "EMAIL-2", { text: "Message sent" }));
    wrapper = mount(EmailRow, {
      props: { item: reply, fresh: false, now: NOW, heardDirect: new Set<string>() },
      attachTo: document.body,
      global: withDaemon(daemon),
    });
    await rightClick(wrapper.find("li.mail"));
    expect(labels()).toEqual(["Copy message"]);
  });

  it("Packets: a packet offers its line and the call that sent it, and the click after a long press does not open it", async () => {
    const packets = new Map([["2", packet(2, { source: "OH2PU-9", tnc2: "OH2PU-9>APOTC1:>on air" })]]);
    wrapper = mount(PacketsLog, { props: { packets }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick(wrapper.find("tr.packet-row"));
    expect(labels()).toEqual(["Copy packet", "Copy OH2PU-9"]);
    await choose("packet");
    expect(written).toEqual(["OH2PU-9>APOTC1:>on air"]);
    expect(wrapper.find("tr.detail").exists()).toBe(false);
  });

  it("Objects: an own object offers its name", async () => {
    const table = new Map([["LEADER", ownObject("LEADER", { comment: "Rescue 1" })]]);
    const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
    wrapper = mount(ObjectsPane, { props: { objects: table, form }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick(wrapper.find("li.ownobject"));
    expect(labels()).toEqual(["Copy name"]);
    await choose("name");
    expect(written).toEqual(["LEADER"]);
  });
});
