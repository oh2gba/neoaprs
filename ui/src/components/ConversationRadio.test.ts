// The radio a conversation's messages go on, as the daemon says it (composables/useStationRadio.ts): that of a message on its way, else the station's radio now, else for a call the book does not hold the radio the daemon
// names for a call no radio heard (`status.unheard_radio`), which Route shows as what Automatic gives before Send; the
// operator's choice in force comes before all, as it holds for a message on its way from its next attempt. Where more than one radio is on the header names it with a tag (the room of a name of eight characters kept), Send
// waits for its link and says so with its name, and the bubbles of messages that came in name theirs; with one radio on none is named, and a message that came on a radio that is not on (off, removed) always is. The Email
// tab goes on the daemon's email radio, which a list beside Check email chooses while several radios that can send are on (every such radio, of any kind; `email/radio`), and is off with its reason while that radio is not
// connected or there is none; a mail that came in names the radio it came on as a bubble does.
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
import { configValues, heardBy, incoming, message, radioRow, radiosTopic, station, status } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
afterEach(() => document.body.replaceChildren());

const BOTH = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"));
const FM_OFF = radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury"));
const HF_OFF = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" }));
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
  const daemon = fakeDaemon({ radios: BOTH, stations: shallowRef(new Map(rows.map((row) => [row.call, row]))), ...given });
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
  it("is Mercury for a station FM heard long ago and Mercury lately, which the daemon messages over Mercury", () => {
    const wrapper = header("OH2LATE", [station("OH2LATE", { heard: heardBy([1, 30], [2, 2, null]), radio_now: 2 })]);
    expect(named(wrapper)).toBe("Mercury");
    expect(tag(wrapper).classes()).toContain("tag-hf");
    expect(tag(wrapper).attributes("title")).toBe("Messages to this station go on radio Mercury");
  });

  it("is FM for a station heard on Mercury alone that the daemon messages over FM", () => {
    const wrapper = header("OH2FAR", [station("OH2FAR", { heard: heardBy([2, 3, null]), radio_now: 1 })]);
    expect([named(wrapper), tag(wrapper).classes()]).toEqual(["FM", expect.arrayContaining(["tag-neutral"])]);
  });

  it("is the radio of a message on its way that keeps Mercury though the station is now messaged over FM, and the station's once it is done", () => {
    const row = station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]), radio_now: 1 });
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "sending", radio_now: 2 })]))).toBe("Mercury");
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "queued", radio_now: 2 })]))).toBe("Mercury");
    expect(named(header("OH2RDG", [row], [message(4, { to_call: "OH2RDG", state: "acked", radio_now: null })]))).toBe("FM");
  });

  it("follows the operator's choice at once while a message is on its way, which takes the radio chosen from its next attempt", () => {
    const pressedFm = station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]), radio_choice: 1, radio_now: 1 });
    const sending = message(4, { to_call: "OH2RDG", state: "sending", radio_id: 2, radio_now: 2 });
    expect(named(header("OH2RDG", [pressedFm], [sending]))).toBe("FM");
    expect(named(header("OH2RDG", [{ ...pressedFm, radio_choice: 2, radio_now: 2 }], [{ ...sending, radio_id: 1, radio_now: 1 }]))).toBe("Mercury");
  });

  it("is, for a call nothing is known of and for a row that names none, the radio the daemon names for a call no radio heard", async () => {
    const hf = header("OH2NEW", [], [], { status: status({ unheard_radio: 2 }) });
    expect([named(hf), hasRoute(hf)]).toEqual(["Mercury", true]);
    await hf.find(".route-button").trigger("click");
    const path = hf.find<HTMLInputElement>(".route-box .pathbox input[type='text']");
    expect([path.element.disabled, path.attributes("title")]).toEqual([true, "Mercury: no path"]);
    expect(named(header("OH2NEW", [], [], { status: status({ unheard_radio: 1 }) }))).toBe("FM");
    expect(named(header("OH2NET", [station("OH2NET", { can_message: false, radio_now: null })], [], { status: status({ unheard_radio: 2 }) }))).toBe("Mercury");
  });

  it('shows in Route, before Send, which radio Automatic gives a call no radio heard: the row greyed on "Automatic: NAME", in the page\'s own words', async () => {
    const route = async (given: Given) => {
      const wrapper = header("OH2NEW", [], [], given);
      await wrapper.find(".route-button").trigger("click");
      const list = wrapper.find<HTMLSelectElement>(".route-box select.route-radio-pick");
      if (!list.exists()) return null;
      return [list.element.disabled, list.element.selectedOptions[0]?.text, list.findAll("option").map((option) => option.text())];
    };
    expect(await route({ status: status({ unheard_radio: 2 }) })).toEqual([true, "Automatic: Mercury", ["Automatic: Mercury", "FM", "Mercury"]]);
    expect(await route({ status: status({ unheard_radio: 1 }) })).toEqual([true, "Automatic: FM", ["Automatic: FM", "FM", "Mercury"]]);
    expect((await route({ radios: SIX, status: status({ unheard_radio: 6 }) }))?.[1]).toBe("Automatic: 80 m");
    expect(await route({ radios: HF_OFF, status: status({ unheard_radio: 1 }) })).toBeNull(); // (one radio that can send: no row)
  });

  it("names the radio of a text to CQ, which is no station, as it does a call no radio heard", async () => {
    const wrapper = header("CQ", [], [], { status: status({ unheard_radio: 2 }) });
    expect(named(wrapper)).toBe("Mercury");
    expect(await sendOf(wrapper)).toEqual([false, undefined]);
    const down = header("CQ", [], [], {
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { state: "waiting" })),
      status: status({ unheard_radio: 2 }),
    });
    expect(await sendOf(down)).toEqual([true, "Mercury: not connected"]);
  });

  it("is any radio the daemon says, a third one too, by the name the operator gave it", () => {
    const wrapper = header("OH2MOB", [station("OH2MOB", { radio_now: 3 })], [], { radios: SIX });
    expect([named(wrapper), tag(wrapper).attributes("title")]).toEqual(["Mobile", "Messages to this station go on radio Mobile"]);
    expect(named(header("OH2DX", [station("OH2DX", { radio_now: 4 })], [], { radios: SIX }))).toBe("40 m");
    expect(tag(header("OH2DX", [station("OH2DX", { radio_now: 4 })], [], { radios: SIX })).classes()).toContain("tag-dummy");
  });

  it("is not named while one radio is on: the header is today's, FM or Mercury alone", () => {
    for (const [values, now] of [
      [HF_OFF, 1],
      [FM_OFF, 2],
    ] as const) {
      const wrapper = header("OH2RDG", [station("OH2RDG", { heard: heardBy([1, 3], [2, 3, null]), radio_now: now })], [], { radios: values });
      expect(wrapper.find(".convo-radio").exists(), String(now)).toBe(false);
    }
  });

  it("follows the radios as they are ticked: the tag comes with the second radio and goes with it", async () => {
    const daemon = fakeDaemon({ radios: HF_OFF, stations: shallowRef(new Map([["OH2RDG", station("OH2RDG")]])) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, global: withDaemon(daemon) });
    expect(named(wrapper)).toBe(null);
    await tell(daemon, { radios: BOTH });
    expect(named(wrapper)).toBe("FM");
    await tell(daemon, { radios: HF_OFF });
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
      radioRow(2, "mercury", { name: "Mercury" }),
      radioRow(3, "kiss", { name: "WWWWWWWW", number: 2 }),
    );
    const daemon = fakeDaemon({ radios: wide, stations: shallowRef(new Map([["OH2RDG", station("OH2RDG", { radio_now: 2 })]])) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2RDG", narrow: false, thread: [] }, global: withDaemon(daemon), attachTo: document.body });
    const room = () =>
      wrapper
        .findAll(".convo-radio .twowords > span")
        .map((part) => [part.text(), part.classes().includes("twowords-off"), part.attributes("aria-hidden"), part.find(".tag").attributes("title") ?? null]);
    expect(room()).toEqual([
      ["Mercury", false, "false", "Messages to this station go on radio Mercury"],
      ["FM", true, "true", null],
      ["WWWWWWWW", true, "true", null],
    ]);
    expect(named(wrapper)).toBe("Mercury");
    await tell(daemon, { stations: new Map([["OH2RDG", station("OH2RDG", { radio_now: 3 })]]) });
    expect(room().map(([name, hidden]) => [name, hidden])).toEqual([
      ["WWWWWWWW", false],
      ["FM", true],
      ["Mercury", true],
    ]);
    const sheet = readFileSync(resolve(__dirname, "../styles/tables.css"), "utf8");
    expect(sheet).toMatch(/\.twowords > span \{\s*grid-area: 1 \/ 1;/);
  });

  it("is in the header bar beside the call, before Route, and the compose has no radio to press", () => {
    const wrapper = header("OH2RDG", [station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]) })]);
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
    const down = header("OH2LATE", [station("OH2LATE", { heard: heardBy([1, 30], [2, 2, null]), radio_now: 2 })], [], { radios: twoUp("waiting") });
    expect(await sendOf(down)).toEqual([true, "Mercury: not connected"]);
    const fm = header("OH2LATE", [station("OH2LATE", { heard: heardBy([1, 30], [2, 2, null]), radio_now: 1 })], [], { radios: twoUp("waiting") });
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

  it("says that the TNC is not connected while the one radio on is not", async () => {
    const down = radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury", { enabled: false, state: "stopped" }));
    expect(await sendOf(header("OH2RDG", [station("OH2RDG")], [], { radios: down, connected: false }))).toEqual([true, "The radio is not connected"]);
  });
});

describe("a message that came in", () => {
  const line = (m: MessageRow, given: Given = {}) =>
    mount(ConversationThread, { props: { thread: [m], peer: "OH2RDG" }, global: withDaemon(fakeDaemon({ radios: BOTH, ...given })) }).find(".bubble-route");

  it("names the radio it came on before its route words where radios are named, FM as Mercury: none is the unmarked default", () => {
    const hf = line(incoming(2, "OH2RDG", { radio_id: 2, route: "direct" }));
    expect([hf.text(), hf.find(".tag").classes(), hf.find(".tag").attributes("title")]).toEqual([
      "Mercury direct",
      expect.arrayContaining(["tag-hf"]),
      "Heard on radio Mercury",
    ]);
    expect(line(incoming(2, "OH2RDG", { radio_id: 1, route: "via OH2RCH-2" })).text()).toBe("FM via OH2RCH-2");
    expect(line(incoming(2, "OH2RDG", { radio_id: 5, route: "direct" }), { radios: SIX }).text()).toBe("Portable direct");
  });

  it("is as today with one radio on: no tag for the one radio", () => {
    expect(line(incoming(2, "OH2RDG", { radio_id: 1, route: "via OH2RCH-2" }), { radios: HF_OFF }).text()).toBe("via OH2RCH-2");
    const hfAlone = line(incoming(2, "OH2RDG", { radio_id: 2, route: "direct" }), { radios: FM_OFF });
    expect([hfAlone.text(), hfAlone.find(".tag").exists()]).toEqual(["direct", false]);
  });

  it("always names a radio that is not on: one switched off, one removed", () => {
    expect(line(incoming(2, "OH2RDG", { radio_id: 2, route: "direct" }), { radios: HF_OFF }).text()).toBe("Mercury direct");
    const removed = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { name: "Old", number: 2, removed: true, enabled: false, state: "stopped" }));
    expect(line(incoming(2, "OH2RDG", { radio_id: 3, route: "via OH2RCH-2" }), { radios: removed }).text()).toBe("Old via OH2RCH-2");
  });

  it("has no tag under a message of ours, nor under one from the internet", () => {
    expect(line(message(1, { radio_id: null, route: "" })).exists()).toBe(false);
    expect(line(incoming(2, "OH2RDG", { radio_id: null, route: "" })).exists()).toBe(false);
  });
});

describe("the radio of email", () => {
  const mount_ = (given: Given) => {
    const daemon = fakeDaemon(given);
    return { daemon, wrapper: mount(EmailPane, { props: { thread: [], addresses: [] }, global: withDaemon(daemon), attachTo: document.body }) };
  };
  const pane = (given: Given) => mount_(given).wrapper;
  const check = (wrapper: ReturnType<typeof pane>) => {
    const button = wrapper.findAll("button").find((b) => b.text() === "Check email");
    return [button?.element.disabled, button?.attributes("title")];
  };
  const list = (wrapper: ReturnType<typeof pane>) => wrapper.find<HTMLSelectElement>(".mail-bar .mail-radio select");
  const offered = (wrapper: ReturnType<typeof pane>) =>
    list(wrapper)
      .findAll("option")
      .map((option) => option.text());
  const sendOfMail = async (wrapper: ReturnType<typeof pane>) => {
    await wrapper.find("#mail-to").setValue("a@example.org");
    await wrapper.find("#mail-text").setValue("hello");
    const send = wrapper.find<HTMLButtonElement>(".mailform button[type='submit']");
    return [send.element.disabled, send.attributes("title")];
  };
  /** Six radios with a monitor that only receives (7) and a radio that is off (8) beside them. */
  const EIGHT = radiosTopic(
    ...SIX.values(),
    radioRow(7, "tnc-text", { name: "FTM", number: 4 }),
    radioRow(8, "dummy-lora", { name: "Bike", enabled: false, state: "stopped" }),
  );

  it("is chosen in a list beside Check email while several radios that can send are on: every such radio by its name, of any kind, and the daemon's email radio shown", () => {
    const wrapper = pane({ radios: EIGHT, status: status({ email_radio: 3 }) });
    expect(offered(wrapper)).toEqual(["Shack", "20 m", "Mobile", "40 m", "Portable", "80 m"]);
    expect([list(wrapper).element.value, list(wrapper).element.selectedOptions[0]?.text]).toEqual(["3", "Mobile"]);
    const label = wrapper.find(".mail-bar .mail-radio label");
    expect([label.text(), label.attributes("for"), label.classes()]).toEqual(["Send on", list(wrapper).attributes("id"), ["path-label"]]);
    expect([list(wrapper).attributes("aria-label"), list(wrapper).attributes("title"), list(wrapper).classes()]).toEqual([undefined, undefined, ["input"]]);
    expect(wrapper.find(".mail-bar .mail-radio").classes()).toEqual(["pathbox", "mail-radio"]);
    expect(check(wrapper)).toEqual([false, undefined]);
    expect(wrapper.find(".mail-bar .tag").exists()).toBe(false);
  });

  it("stores the radio picked at once as `email/radio`, shows it while the daemon is asked, and follows the daemon's email radio after", async () => {
    const { daemon, wrapper } = mount_({ radios: BOTH, status: status({ email_radio: 1 }) });
    expect(list(wrapper).element.value).toBe("1");
    await list(wrapper).setValue("2");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "email/radio": "2" } });
    expect(list(wrapper).element.value).toBe("2");
    await tell(daemon, { config: configValues({}, { "email/radio": "2" }), status: status({ email_radio: 2 }) });
    expect([list(wrapper).element.value, list(wrapper).element.selectedOptions[0]?.text]).toEqual(["2", "Mercury"]);
    expect(daemon.send).toHaveBeenCalledTimes(1);
  });

  it("shows the radio in force while the one stored is off: the list has the radios that are on, and the stored one comes back with its radio", async () => {
    const stored = configValues({}, { "email/radio": "2" });
    const { daemon, wrapper } = mount_({
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" }), radioRow(3, "dummy-lora")),
      config: stored,
      status: status({ email_radio: 1 }),
    });
    expect([offered(wrapper), list(wrapper).element.value]).toEqual([["FM", "LoRa"], "1"]);
    await tell(daemon, {
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "dummy-lora")),
      status: status({ email_radio: 2 }),
    });
    expect([offered(wrapper), list(wrapper).element.value]).toEqual([["FM", "Mercury", "LoRa"], "2"]);
    expect(daemon.send).not.toHaveBeenCalled();
  });

  it("has no list with one radio that can send, a monitor beside it or not: email goes on that radio and nothing is shown", async () => {
    for (const radios of [HF_OFF, FM_OFF, radiosTopic(radioRow(2, "mercury"), radioRow(7, "tnc-text", { name: "FTM" }))]) {
      const wrapper = pane({ radios, status: status({ email_radio: [...radios.values()].find((row) => row.enabled && row.can.transmit)?.id ?? null }) });
      expect([list(wrapper).exists(), wrapper.find(".mail-bar .tag").exists()]).toEqual([false, false]);
      expect(check(wrapper)).toEqual([false, undefined]);
      expect(await sendOfMail(wrapper)).toEqual([false, undefined]);
      wrapper.unmount();
    }
  });

  it("takes the same room whichever radio is chosen: the list beside the button, then the room, then the (i), and no line of words", async () => {
    const { daemon, wrapper } = mount_({ radios: SIX, status: status({ email_radio: 1 }) });
    const bar = () => [...wrapper.find(".mail-bar").element.children].map((e) => `${e.tagName.toLowerCase()}.${e.className.split(" ").join(".")}`);
    const before = bar();
    expect(before).toEqual(["button.btn", "div.pathbox.mail-radio", "span.grow", "span.infotip"]);
    await list(wrapper).setValue("6");
    await tell(daemon, { status: status({ email_radio: 6 }) });
    expect(bar()).toEqual(before);
    expect(wrapper.find(".mail-bar").text()).toBe("Check emailSend onShack20 mMobile40 mPortable80 mi");
    const sheet = readFileSync(resolve(__dirname, "../styles/email.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rule = sheet.match(/\.mail-radio \{([^}]*)\}/)?.[1] ?? "";
    expect([rule.includes("flex: none"), rule.includes("flex-wrap: nowrap")], "the label and the list go as one, as wide as the longest name").toEqual([
      true,
      true,
    ]);
    expect(sheet.match(/\.mail-bar \{([^}]*)\}/)?.[1], "at 375 px the two go under the button rather than out of the screen").toContain("flex-wrap: wrap");
  });

  it("keeps Check email and Send off while its radio is not connected, saying which", async () => {
    const wrapper = pane({ radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury")) });
    expect(check(wrapper)).toEqual([true, "FM: not connected"]);
    expect(await sendOfMail(wrapper)).toEqual([true, "FM: not connected"]);
  });

  it("has Send on while the radio chosen takes frames, a Mercury radio too, and off while that one is not connected though another is", async () => {
    const up = pane({ radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury")), status: status({ email_radio: 2 }) });
    expect([check(up), await sendOfMail(up)]).toEqual([
      [false, undefined],
      [false, undefined],
    ]);
    const down = pane({ radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { state: "waiting" })), status: status({ email_radio: 2 }) });
    expect([check(down), await sendOfMail(down)]).toEqual([
      [true, "Mercury: not connected"],
      [true, "Mercury: not connected"],
    ]);
  });

  it("holds Retry of a mail while its radio is not connected", () => {
    const thread = [message(7, { to_call: "EMAIL-2", text: "a@example.org hello", state: "failed", attempts: 2 })];
    const wrapper = mount(EmailPane, {
      props: { thread, addresses: [] },
      global: withDaemon(fakeDaemon({ radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury")) })),
    });
    const retry = wrapper.findAll<HTMLButtonElement>("button").find((b) => b.text() === "Retry");
    expect([retry?.element.disabled, retry?.attributes("title")]).toEqual([true, "FM: not connected"]);
  });

  it("names the radio a mail that came in came on, before its route, as a bubble does, where radios are named", async () => {
    const mail = incoming(8, "EMAIL-2", { radio_id: 3, route: "via OH2RCH-2" });
    const wrapper = mount(EmailPane, { props: { thread: [mail], addresses: [] }, global: withDaemon(fakeDaemon({ radios: SIX })) });
    await wrapper.find(".mail-body").trigger("click");
    const route = wrapper.find(".mail-detail .tag");
    expect([route.text(), route.classes(), route.attributes("title")]).toEqual(["Mobile", expect.arrayContaining(["tag-neutral"]), "Heard on radio Mobile"]);
    expect(wrapper.find(".mail-detail").text()).toContain("Mobile via OH2RCH-2");
  });

  it("names no radio under a mail with one radio on, as today", async () => {
    const mail = incoming(8, "EMAIL-2", { radio_id: 1, route: "via OH2RCH-2" });
    const wrapper = mount(EmailPane, { props: { thread: [mail], addresses: [] }, global: withDaemon(fakeDaemon({ radios: HF_OFF })) });
    await wrapper.find(".mail-body").trigger("click");
    expect([wrapper.find(".mail-detail .tag").exists(), wrapper.find(".mail-detail").text()]).toEqual([false, expect.stringContaining("via OH2RCH-2")]);
    expect(wrapper.find(".mail-detail").text()).not.toContain("FM");
  });

  it("goes over Mercury where that is the one radio that can send, and is off with the reason of every send while no radio is on", async () => {
    const hfAlone = pane({ radios: FM_OFF, status: status({ email_radio: 2 }) });
    expect([check(hfAlone), await sendOfMail(hfAlone)]).toEqual([
      [false, undefined],
      [false, undefined],
    ]);
    const none = radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury", { enabled: false, state: "stopped" }));
    const off = pane({ radios: none, status: status({ email_radio: null }) });
    expect(check(off)).toEqual([true, "there is no radio: add one, or turn one on"]);
    expect(await sendOfMail(off)).toEqual([true, "there is no radio: add one, or turn one on"]);
    expect(list(off).exists()).toBe(false);
  });
});

describe("a station whose position takes no messages", () => {
  it("is said above the box to write in, with the (i) that says why, and the message goes all the same", async () => {
    const wrapper = header("OH2PLN", [station("OH2PLN", { may_not_message: true })], [], { radios: radiosTopic(radioRow(1, "kenwood-tnc2")) });
    const note = wrapper.find(".convo-maynot");
    expect(note.text()).toContain("This station may not take messages");
    expect(note.find(".infotip").exists()).toBe(true);
    await wrapper.find("#msg-text").setValue("hello anyway");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
    expect(
      header("OH2FM", [station("OH2FM")])
        .find(".convo-maynot")
        .exists(),
    ).toBe(false);
  });
});
