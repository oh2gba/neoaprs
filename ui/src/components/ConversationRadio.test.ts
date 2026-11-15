// The radio a conversation's messages go on, as the daemon says it (composables/useStationRadio.ts): that of a message on its way, else the station's radio now, else for a call the book does not hold the main radio; the
// operator's choice in force comes before all, as it holds for a message on its way from its next attempt. Where more than one radio is on the header names it with a tag (the room of a name of eight characters kept), Send
// waits for its link and says so with its name, and the bubbles of messages that came in name theirs; with one radio on none is named, and a message that came on a radio that is not on (off, removed) always is. The Email
// tab goes on the daemon's email radio, named beside Check email where radios are named, and is off with its reason while there is none; a mail that came in names the radio it came on as a bubble does.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import ConversationView from "@/components/ConversationView.vue";
import EmailPane from "@/components/EmailPane.vue";
import type { MessageRow, RadioRow, StationRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, incoming, message, radioRow, radiosTopic, station, status } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
afterEach(() => document.body.replaceChildren());

const BOTH = { "fm/enabled": "true", "hf/enabled": "true" };
const FM_OFF = { "fm/enabled": "false", "hf/enabled": "true" };
/** Six radios of the names an operator gives, the longest of eight characters: radio 1 FM, 2 HF, then two more of each kind. */
const SIX = radiosTopic(
  radioRow(1, "kenwood-tnc2", { name: "Shack" }),
  radioRow(2, "mercury", { name: "20 m" }),
  radioRow(3, "kiss", { name: "Mobile", number: 2 }),
  radioRow(4, "dummy-hf", { name: "40 m", number: 2 }),
  radioRow(5, "kiss-tcp", { name: "Portable", number: 3 }),
  radioRow(6, "mercury", { name: "80 m", number: 3, state: "waiting" }),
);

function header(call: string, rows: StationRow[], thread: MessageRow[] = [], given: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(BOTH), stations: shallowRef(new Map(rows.map((row) => [row.call, row]))), ...given });
  return mount(ConversationView, { props: { selected: call, narrow: false, thread }, global: withDaemon(daemon), attachTo: document.body });
}
type Wrapper = ReturnType<typeof header>;
const tag = (wrapper: Wrapper) => wrapper.find(".convo-head .convo-radio .tag");
const named = (wrapper: Wrapper) => (tag(wrapper).exists() ? tag(wrapper).text() : null);
const hasRoute = (wrapper: Wrapper) => wrapper.find(".route-button").exists();
async function sendOf(wrapper: Wrapper) {
  await wrapper.find("input.compose-text").setValue("Moi");
  const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
  return [send.element.disabled, send.attributes("title")];
}

describe("the radio of a conversation", () => {
  it("is HF for a station FM heard long ago and HF lately, which the daemon messages over HF", () => {
    const wrapper = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 })]);
    expect(named(wrapper)).toBe("HF");
    expect(tag(wrapper).classes()).toContain("tag-hf");
    expect(tag(wrapper).attributes("title")).toBe("Messages to this station go on radio HF");
  });

  it("is FM for a station heard on HF alone that the daemon messages over FM", () => {
    const wrapper = header("OH2FAR", [station("OH2FAR", { heard_fm: 0, heard_hf: 3, radio_now: 1 })]);
    expect([named(wrapper), tag(wrapper).classes()]).toEqual(["FM", expect.arrayContaining(["tag-neutral"])]);
  });

  it("is the radio of a message on its way that keeps HF though the station is now messaged over FM, and the station's once it is done", () => {
    const row = station("OH2RDG", { heard_fm: 3, heard_hf: 2, radio_now: 1 });
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "sending", radio_now: 2 })]))).toBe("HF");
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "queued", radio_now: 2 })]))).toBe("HF");
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "acked", radio_now: null })]))).toBe("FM");
  });

  it("follows the operator's choice at once while a message is on its way, which takes the radio chosen from its next attempt", () => {
    const pressedFm = station("OH2RDG", { heard_fm: 3, heard_hf: 2, radio_choice: 1, radio_now: 1 });
    const sending = message(4, { to_call: "OH2RDG", state: "sending", radio: "hf", radio_now: 2 });
    expect(named(header("OH2RDG", [pressedFm], [sending]))).toBe("FM");
    expect(named(header("OH2RDG", [{ ...pressedFm, radio_choice: 2, radio_now: 2 }], [{ ...sending, radio: "fm", radio_now: 1 }]))).toBe("HF");
  });

  it("is the main radio for a call nothing is known of, and for a row that names none", async () => {
    const hf = header("OH2NEW", [], [], { status: status({ main_radio: 2 }) });
    expect([named(hf), hasRoute(hf)]).toEqual(["HF", true]);
    await hf.find(".route-button").trigger("click");
    const path = hf.find<HTMLInputElement>(".route-box .pathbox input[type='text']");
    expect([path.element.disabled, path.attributes("title")]).toEqual([true, "HF: no path"]);
    expect(named(header("OH2NEW", [], [], { status: status({ main_radio: 1 }) }))).toBe("FM");
    expect(named(header("OH2NET", [station("OH2NET", { can_message: false, radio_now: null })], [], { status: status({ main_radio: 2 }) }))).toBe("HF");
  });

  it("is any radio the daemon says, a third one too, by the name the operator gave it", () => {
    const wrapper = header("OH2MOB", [station("OH2MOB", { radio_now: 3 })], [], { radios: SIX });
    expect([named(wrapper), tag(wrapper).attributes("title")]).toEqual(["Mobile", "Messages to this station go on radio Mobile"]);
    expect(named(header("OH2DX", [station("OH2DX", { radio_now: 4 })], [], { radios: SIX }))).toBe("40 m");
    expect(tag(header("OH2DX", [station("OH2DX", { radio_now: 4 })], [], { radios: SIX })).classes()).toContain("tag-dummy");
  });

  it("is not named while one radio is on: the header is today's, FM or HF alone", () => {
    for (const [values, now] of [
      [{}, 1],
      [FM_OFF, 2],
    ] as const) {
      const wrapper = header("OH2RDG", [station("OH2RDG", { heard_fm: 3, heard_hf: 3, radio_now: now })], [], { config: configValues(values) });
      expect(wrapper.find(".convo-radio").exists(), JSON.stringify(values)).toBe(false);
    }
  });

  it("follows the radios as they are ticked: the tag comes with the second radio and goes with it", async () => {
    const daemon = fakeDaemon({ config: configValues({}), stations: shallowRef(new Map([["OH2RDG", station("OH2RDG")]])) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, global: withDaemon(daemon) });
    expect(named(wrapper)).toBe(null);
    await tell(daemon, { config: configValues(BOTH) });
    expect(named(wrapper)).toBe("FM");
    await tell(daemon, { config: configValues({}) });
    expect(named(wrapper)).toBe(null);
  });

  it("has nothing of the radio for an overheard pair: no tag, no Route", () => {
    const wrapper = header("OH2AAA>OH2BBB", []);
    expect([wrapper.find(".convo-radio").exists(), hasRoute(wrapper)]).toEqual([false, false]);
  });

  it("keeps the room of a name of eight characters for the tag, right-aligned in it, so that the call's room before it is the same whichever radio it names", () => {
    const sheet = readFileSync(resolve(__dirname, "../styles/messages.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rule = sheet.match(/\.convo-radio \{([^}]*)\}/g)?.join("") ?? "";
    expect(rule).toContain("min-width: calc(8ch + 14px)");
    expect(rule).toContain("font-size: 11px");
    expect(rule).toContain("justify-content: flex-end");
  });

  it("keeps the room of the widest name of the radios that are on, whichever it names: the other radios' tags in the same place, hidden, so that a name wider than eight digits moves nothing either", async () => {
    const wide = radiosTopic(
      radioRow(1, "kenwood-tnc2", { name: "FM" }),
      radioRow(2, "mercury", { name: "HF" }),
      radioRow(3, "kiss", { name: "WWWWWWWW", number: 2 }),
    );
    const daemon = fakeDaemon({ config: configValues(BOTH), radios: wide, stations: shallowRef(new Map([["OH2RDG", station("OH2RDG", { radio_now: 2 })]])) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, global: withDaemon(daemon), attachTo: document.body });
    const room = () =>
      wrapper
        .findAll(".convo-radio .twowords > span")
        .map((part) => [part.text(), part.classes().includes("twowords-off"), part.attributes("aria-hidden"), part.find(".tag").attributes("title") ?? null]);
    expect(room()).toEqual([
      ["HF", false, "false", "Messages to this station go on radio HF"],
      ["FM", true, "true", null],
      ["WWWWWWWW", true, "true", null],
    ]);
    expect(named(wrapper)).toBe("HF");
    await tell(daemon, { stations: new Map([["OH2RDG", station("OH2RDG", { radio_now: 3 })]]) });
    expect(room().map(([name, hidden]) => [name, hidden])).toEqual([
      ["WWWWWWWW", false],
      ["FM", true],
      ["HF", true],
    ]);
    const sheet = readFileSync(resolve(__dirname, "../styles/tables.css"), "utf8");
    expect(sheet).toMatch(/\.twowords > span \{\s*grid-area: 1 \/ 1;/);
  });

  it("is in the header bar beside the call, before Route, and the compose has no radio to press", () => {
    const wrapper = header("OH2RDG", [station("OH2RDG", { heard_fm: 3, heard_hf: 2 })]);
    const head = [...wrapper.find(".convo-head").element.children].map((e) => e.className.split(" ")[0]);
    expect(head).toEqual(["convo-title", "convo-radio", "routemenu"]);
    expect(
      wrapper
        .find(".compose")
        .findAll("button")
        .map((b) => b.text()),
    ).toEqual(["Send"]);
  });
});

describe("Send of a conversation", () => {
  const twoUp = (hf: RadioRow["state"]) => radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { state: hf }));

  it("waits for the link of the radio the daemon says, and says which radio is not connected", async () => {
    const down = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 })], [], { radios: twoUp("waiting") });
    expect(await sendOf(down)).toEqual([true, "HF: not connected"]);
    const fm = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 1 })], [], { radios: twoUp("waiting") });
    expect(await sendOf(fm)).toEqual([false, undefined]);
  });

  it("waits for a sixth radio by its name", async () => {
    expect(await sendOf(header("OH2DX", [station("OH2DX", { radio_now: 6 })], [], { radios: SIX }))).toEqual([true, "80 m: not connected"]);
    expect(await sendOf(header("OH2DX", [station("OH2DX", { radio_now: 5 })], [], { radios: SIX }))).toEqual([false, undefined]);
  });

  it("holds Retry while the radio is not connected, as Send, and lets it go once it is", () => {
    const failed = [message(3, { to_call: "OH2DX", state: "failed", attempts: 4 })];
    const retry = (radio: number) =>
      header("OH2DX", [station("OH2DX", { radio_now: radio })], failed, { radios: SIX })
        .findAll<HTMLButtonElement>(".bubble button")
        .find((b) => b.text() === "Retry");
    expect([retry(6)?.element.disabled, retry(6)?.attributes("title")]).toEqual([true, "80 m: not connected"]);
    expect([retry(5)?.element.disabled, retry(5)?.attributes("title")]).toEqual([false, undefined]);
  });

  it("says the words of before with one radio on", async () => {
    expect(await sendOf(header("OH2RDG", [station("OH2RDG")], [], { config: configValues({}), connected: false }))).toEqual([true, "The TNC is not connected"]);
  });
});

describe("a message that came in", () => {
  const line = (m: MessageRow, given: Given = {}) =>
    mount(ConversationThread, { props: { thread: [m], peer: "OH2RDG" }, global: withDaemon(fakeDaemon({ config: configValues(BOTH), ...given })) }).find(
      ".bubble-route",
    );

  it("names the radio it came on before its route words where radios are named, FM as HF: none is the unmarked default", () => {
    const hf = line(incoming(2, "OH2RDG", { radio: "hf", route: "direct" }));
    expect([hf.text(), hf.find(".tag").classes(), hf.find(".tag").attributes("title")]).toEqual([
      "HF direct",
      expect.arrayContaining(["tag-hf"]),
      "Heard on radio HF",
    ]);
    expect(line(incoming(2, "OH2RDG", { radio: "fm", route: "via OH2RCH-2" })).text()).toBe("FM via OH2RCH-2");
    expect(line(incoming(2, "OH2RDG", { radio_id: 5, route: "direct" }), { radios: SIX }).text()).toBe("Portable direct");
  });

  it("is as today with one radio on: no tag for the one radio", () => {
    expect(line(incoming(2, "OH2RDG", { radio: "fm", route: "via OH2RCH-2" }), { config: configValues({}) }).text()).toBe("via OH2RCH-2");
    const hfAlone = line(incoming(2, "OH2RDG", { radio: "hf", route: "direct" }), { config: configValues(FM_OFF) });
    expect([hfAlone.text(), hfAlone.find(".tag").exists()]).toEqual(["direct", false]);
  });

  it("always names a radio that is not on: one switched off, one removed", () => {
    expect(line(incoming(2, "OH2RDG", { radio: "hf", route: "direct" }), { config: configValues({}) }).text()).toBe("HF direct");
    const removed = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { name: "Old", number: 2, removed: true, enabled: false, state: "stopped" }));
    expect(line(incoming(2, "OH2RDG", { radio_id: 3, route: "via OH2RCH-2" }), { config: configValues({}), radios: removed }).text()).toBe("Old via OH2RCH-2");
  });

  it("has no tag under a message of ours, nor under one from the internet", () => {
    expect(line(message(1, { radio: "", route: "" })).exists()).toBe(false);
    expect(line(incoming(2, "OH2RDG", { radio: "", route: "" })).exists()).toBe(false);
  });
});

describe("the radio of email", () => {
  const pane = (given: Given) => mount(EmailPane, { props: { thread: [], addresses: [] }, global: withDaemon(fakeDaemon(given)), attachTo: document.body });
  const check = (wrapper: ReturnType<typeof pane>) => {
    const button = wrapper.findAll("button").find((b) => b.text() === "Check email");
    return [button?.element.disabled, button?.attributes("title")];
  };
  const mailTag = (wrapper: ReturnType<typeof pane>) => wrapper.find(".mail-bar .mail-radio");

  it("is named beside Check email where radios are named: the daemon's email radio", () => {
    const wrapper = pane({ config: configValues(BOTH), radios: SIX, status: status({ email_radio: 3 }) });
    expect([mailTag(wrapper).text(), mailTag(wrapper).attributes("title")]).toEqual(["Mobile", "Email goes on radio Mobile"]);
    expect(check(wrapper)).toEqual([false, undefined]);
  });

  it("is not named with one radio on, as today", () => {
    expect(mailTag(pane({ config: configValues({}) })).exists()).toBe(false);
  });

  it("keeps Check email and Send off while its radio is not connected, saying which", async () => {
    const wrapper = pane({ config: configValues(BOTH), radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury")) });
    expect(check(wrapper)).toEqual([true, "FM: not connected"]);
    await wrapper.find("#mail-to").setValue("a@example.org");
    await wrapper.find("#mail-text").setValue("hello");
    const send = wrapper.find<HTMLButtonElement>(".mailform button[type='submit']");
    expect([send.element.disabled, send.attributes("title")]).toEqual([true, "FM: not connected"]);
  });

  it("holds Retry of a mail while its radio is not connected", () => {
    const thread = [message(7, { to_call: "EMAIL-2", text: "a@example.org hello", state: "failed", attempts: 2 })];
    const wrapper = mount(EmailPane, {
      props: { thread, addresses: [] },
      global: withDaemon(
        fakeDaemon({ config: configValues(BOTH), radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury")) }),
      ),
    });
    const retry = wrapper.findAll<HTMLButtonElement>("button").find((b) => b.text() === "Retry");
    expect([retry?.element.disabled, retry?.attributes("title")]).toEqual([true, "FM: not connected"]);
  });

  it("names the radio a mail that came in came on, before its route, as a bubble does, where radios are named", async () => {
    const mail = incoming(8, "EMAIL-2", { radio_id: 3, route: "via OH2RCH-2" });
    const wrapper = mount(EmailPane, { props: { thread: [mail], addresses: [] }, global: withDaemon(fakeDaemon({ config: configValues(BOTH), radios: SIX })) });
    await wrapper.find(".mail-body").trigger("click");
    const route = wrapper.find(".mail-detail .tag");
    expect([route.text(), route.classes(), route.attributes("title")]).toEqual(["Mobile", expect.arrayContaining(["tag-neutral"]), "Heard on radio Mobile"]);
    expect(wrapper.find(".mail-detail").text()).toContain("Mobile via OH2RCH-2");
  });

  it("names no radio under a mail with one radio on, as today", async () => {
    const mail = incoming(8, "EMAIL-2", { radio: "fm", route: "via OH2RCH-2" });
    const wrapper = mount(EmailPane, { props: { thread: [mail], addresses: [] }, global: withDaemon(fakeDaemon({ config: configValues({}) })) });
    await wrapper.find(".mail-body").trigger("click");
    expect([wrapper.find(".mail-detail .tag").exists(), wrapper.find(".mail-detail").text()]).toEqual([false, expect.stringContaining("via OH2RCH-2")]);
    expect(wrapper.find(".mail-detail").text()).not.toContain("FM");
  });

  it("goes over HF never: with no radio internet gateways hear on, both are off with that reason", () => {
    expect(check(pane({ config: configValues(FM_OFF), status: status({ email_radio: null }) }))).toEqual([true, "No radio that internet gateways hear is on"]);
  });
});
