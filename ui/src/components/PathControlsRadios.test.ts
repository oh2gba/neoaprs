// The controls that carry a path follow the radios. Route of a conversation and of the station
// panel holds the station's radio as its first row where more than one radio is on (with
// "Automatic", which names the radio it gives), then Path and RF only: present while a radio that
// is on may carry a path, greyed with the value kept while the radio in force carries none. A path
// belongs to the radio it was set on. The station panel's queries go on the station's radio: off
// while it is not connected, Trace the route greyed while it carries no path and left out while no
// radio that is on may carry one. Advanced of Ask around and Local info is there while the Packet radio
// is on.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationView from "@/components/ConversationView.vue";
import NearbyAsk from "@/components/NearbyAsk.vue";
import ObjectsQru from "@/components/ObjectsQru.vue";
import StationPanel from "@/components/StationPanel.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { fakeDaemon, tell, withDaemon, type FakeDaemon, type Given } from "@/test/context";
import { configValues, heardBy, qruState, radioRow, radiosTopic, station, status } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
afterEach(() => document.body.replaceChildren());

const off = { enabled: false, state: "stopped" } as const;
/**
 * The radios on: the Packet radio (radio 1) alone, both it and the HF radio (radio 2), the HF radio
 * alone.
 */
const FM: Given = { radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", off)) };
const BOTH: Given = { radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")) };
const FM_OFF: Given = { radios: radiosTopic(radioRow(1, "kenwood-tnc2", off), radioRow(2, "mercury")) };

const fmHeard = station("OH2FM", { heard: heardBy([1, 3]) });
const bothHeard = station("OH2BOTH", { heard: heardBy([1, 3], [2, 2, null]) });
const hfHeard = station("OH2HF", { heard: heardBy([2, 3, null]), heard_rf: 3 });
/** Six radios on, radio 3 a second Packet radio with a path of its own. */
const SIX = radiosTopic(
  radioRow(1, "kenwood-tnc2", { name: "Shack" }),
  radioRow(2, "mercury", { name: "20 m" }),
  radioRow(3, "kiss", { name: "Mobile", number: 2 }),
  radioRow(4, "dummy-hf", { name: "40 m", number: 2 }),
  radioRow(5, "kiss-tcp", { name: "Portable", number: 3 }),
  radioRow(6, "mercury", { name: "80 m", number: 3 }),
);

const stations = (...rows: ReturnType<typeof station>[]) => new Map(rows.map((row) => [row.call, row]));

let daemon: FakeDaemon;
function conversation(radios: Given, call: string, rows = stations(fmHeard, bothHeard, hfHeard), given: Given = {}) {
  daemon = fakeDaemon({ ...radios, stations: shallowRef(rows), fallbackPath: "WIDE1-1,WIDE2-1", ...given });
  return mount(ConversationView, {
    props: { selected: call, narrow: false, thread: [] },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
}
const hasRoute = (wrapper: VueWrapper) => wrapper.findAll("button").some((b) => b.text() === "Route");
async function opened(wrapper: VueWrapper) {
  await wrapper.find(".route-button").trigger("click");
  return wrapper.find(".route-box");
}
const sent = (cmd: string) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === cmd);
const options = (box: ReturnType<VueWrapper["find"]>) => box.findAll(".route-radio option").map((o) => o.text());

function panel(radios: Given, row: ReturnType<typeof station>, given: Given = {}) {
  daemon = fakeDaemon({ ...radios, fallbackPath: "WIDE1-1,WIDE2-1", ...given });
  return mount(StationPanel, { props: { row, armed: false }, global: withDaemon(daemon), attachTo: document.body });
}
const hasPrefs = (wrapper: VueWrapper) => wrapper.findAll("legend").some((l) => l.text() === "Route");
const query = (wrapper: VueWrapper, item: string) => wrapper.find<HTMLButtonElement>(`[data-item='${item}']`);

const askPath = (given: Given) =>
  mount(NearbyAsk, { global: withDaemon(fakeDaemon({ fallbackPath: "WIDE1-1", ...given })) });
const qruPath = (given: Given) =>
  mount(ObjectsQru, {
    global: withDaemon(fakeDaemon({ fallbackPath: "WIDE1-1", qru: qruState({ asked: null }), ...given })),
  });
const hasAdvanced = (wrapper: ReturnType<typeof askPath>) =>
  wrapper.findAll("details summary").some((s) => s.text() === "Advanced");

describe("Route in a conversation", () => {
  it("is there for a station heard on Packet, or on both radios, or never heard, while the Packet radio is on", () => {
    for (const [name, values] of [
      ["Packet", FM],
      ["both", BOTH],
    ] as const) {
      expect(
        [
          hasRoute(conversation(values, "OH2FM")),
          hasRoute(conversation(values, "OH2BOTH")),
          hasRoute(conversation(values, "OH2NEW")),
        ],
        name,
      ).toEqual([true, true, true]);
    }
  });

  it("holds, with one radio on, the path and RF only as today, and no radio to choose", async () => {
    const box = await opened(conversation(FM, "OH2FM"));
    expect(box.findAll("label").map((l) => l.text())).toEqual(["Path", "RF only"]);
    expect(box.find("select").exists()).toBe(false);
  });

  it("is there for a station messaged on Mercury while the Packet radio is on too: its radio first, then the path greyed with the reason as its title, RF only live, and the line saying what the messages go by (plan section 6)", async () => {
    const box = await opened(conversation(BOTH, "OH2HF"));
    expect(box.findAll("label").map((l) => l.text())).toEqual(["Radio", "Path", "RF only"]);
    expect(options(box)).toEqual(["Automatic: Mercury", "Packet", "Mercury"]);
    const path = box.find<HTMLInputElement>(".pathbox input[type='text']");
    expect([path.element.disabled, path.attributes("title")]).toEqual([true, "Mercury: no path"]);
    expect(box.find<HTMLInputElement>(".rfonly input").element.disabled).toBe(false);
    expect(box.find(".rfonly").attributes("title")).toBe("iGates do not put these messages on the internet");
    expect(box.find(".path-line").text()).toBe("Automatic: direct");
    expect(box.find<HTMLButtonElement>(".pathbox button").element.disabled).toBe(true);
  });

  it("says the gateway a station on Mercury is answered through, with RF only live there and heard direct too, and the path still greyed", async () => {
    const wrapper = conversation(BOTH, "OH2HF", stations({ ...hfHeard, replies: { "2": "OH2GBA-12,WIDE2-1" } }));
    const box = await opened(wrapper);
    expect(box.find(".path-line").text()).toBe("Automatic: via OH2GBA-12,WIDE2-1");
    expect(box.find<HTMLInputElement>(".pathbox input[type='text']").element.disabled).toBe(true);
    const rfOnly = box.find<HTMLInputElement>(".rfonly input");
    expect([rfOnly.element.disabled, box.find(".rfonly").attributes("title")]).toEqual([
      false,
      "iGates do not put these messages on the internet",
    ]);
    await rfOnly.setValue(true);
    expect(sent("set_station_rf_only")).toEqual([{ cmd: "set_station_rf_only", call: "OH2HF", on: true }]);
    await tell(daemon, { stations: stations(hfHeard) });
    expect([
      wrapper.find(".path-line").text(),
      wrapper.find<HTMLInputElement>(".rfonly input").element.disabled,
    ]).toEqual(["Automatic: direct", false]);
  });

  it("keeps the path of the Packet radio while the station goes over Mercury, and shows it again once it goes over Packet", async () => {
    const prefs = useStationPrefs(new Map([["OH2BOTH", { path: "OH2RCH-2", rf_only: true, alert: null }]]), () => true);
    const wrapper = conversation(BOTH, "OH2BOTH", stations({ ...bothHeard, radio_now: 2 }), { prefs });
    let box = await opened(wrapper);
    expect(box.find<HTMLInputElement>(".pathbox input[type='text']").element.value).toBe("");
    expect(box.find<HTMLInputElement>(".rfonly input").element.checked).toBe(true);
    await tell(daemon, { stations: stations({ ...bothHeard, radio_now: 1 }) });
    box = wrapper.find(".route-box");
    expect(box.find<HTMLInputElement>(".pathbox input[type='text']").element.value).toBe("OH2RCH-2");
    expect(box.find<HTMLInputElement>(".pathbox input[type='text']").element.disabled).toBe(false);
    expect([sent("clear_station_path"), sent("set_station_rf_only")]).toEqual([[], []]);
  });

  it("is not there while the Packet radio is off, whatever station it is: one radio, and it carries no path", () => {
    for (const call of ["OH2FM", "OH2BOTH", "OH2HF", "OH2NEW"])
      expect(hasRoute(conversation(FM_OFF, call)), call).toBe(false);
  });

  it("follows the radios as they are ticked", async () => {
    const wrapper = conversation(FM, "OH2FM", stations(fmHeard));
    expect(hasRoute(wrapper)).toBe(true);
    await tell(daemon, FM_OFF);
    expect(hasRoute(wrapper)).toBe(false);
    await tell(daemon, BOTH);
    expect(hasRoute(wrapper)).toBe(true);
  });

  it("chooses the station's radio: a radio sends it by its id, Automatic gives it back to the daemon, and the list shows the choice in force", async () => {
    const wrapper = conversation(BOTH, "OH2BOTH");
    const box = await opened(wrapper);
    await box.find("select").setValue("2");
    expect(sent("station_radio")).toEqual([{ cmd: "station_radio", call: "OH2BOTH", radio: 2 }]);
    await tell(daemon, { stations: stations({ ...bothHeard, radio_choice: 2, radio_now: 2 }) });
    const chosen = wrapper.find<HTMLSelectElement>(".route-box select");
    expect([chosen.element.value, options(wrapper.find(".route-box"))]).toEqual([
      "2",
      ["Automatic", "Packet", "Mercury"],
    ]);
    expect(wrapper.find(".route-dot").exists()).toBe(true);
    await chosen.setValue("");
    expect(sent("station_radio").at(-1)).toEqual({ cmd: "station_radio", call: "OH2BOTH", radio: null });
  });

  it("shows only the choice the station's row says: one the daemon refuses is not left in the list", async () => {
    const wrapper = conversation(BOTH, "OH2BOTH");
    const list = (await opened(wrapper)).find<HTMLSelectElement>("select");
    await list.setValue("2");
    expect([sent("station_radio"), list.element.value]).toEqual([
      [{ cmd: "station_radio", call: "OH2BOTH", radio: 2 }],
      "",
    ]);
    await tell(daemon, { stations: stations({ ...bothHeard, radio_choice: 2, radio_now: 2 }) });
    expect(wrapper.find<HTMLSelectElement>(".route-box select").element.value).toBe("2");
  });

  it("has no dot while the daemon chooses the radio and the station has no path of its own", () => {
    expect(conversation(BOTH, "OH2BOTH").find(".route-dot").exists()).toBe(false);
  });

  it("offers six radios in the one list, by their names, with Automatic first", async () => {
    const box = await opened(
      conversation(BOTH, "OH2MOB", stations(station("OH2MOB", { radio_now: 3 })), { radios: SIX }),
    );
    expect(options(box)).toEqual(["Automatic: Mobile", "Shack", "20 m", "Mobile", "40 m", "Portable", "80 m"]);
    expect(box.findAll(".route-radio select")).toHaveLength(1);
  });

  it("has the radio's row live on Automatic for a call the book does not hold, and still once the station is heard, nothing above Path moving", async () => {
    const wrapper = conversation(BOTH, "OH2NEW", stations(fmHeard));
    const box = await opened(wrapper);
    const list = box.find<HTMLSelectElement>(".route-radio select");
    expect([
      list.element.disabled,
      box.find(".route-radio").classes(),
      options(box),
      box.findAll("label").map((l) => l.text()),
    ]).toEqual([
      false,
      ["pathbox", "route-radio"],
      ["Automatic: Packet", "Packet", "Mercury"],
      ["Radio", "Path", "RF only"],
    ]);
    const before = box.findAll(".prefs > *").map((row) => row.classes()[0]);
    await tell(daemon, { stations: stations(fmHeard, station("OH2NEW", { heard: heardBy([1, 1]), radio_now: 1 })) });
    const now = wrapper.find(".route-box");
    expect([
      now.find<HTMLSelectElement>(".route-radio select").element.disabled,
      now.find(".route-radio").classes(),
    ]).toEqual([false, ["pathbox", "route-radio"]]);
    expect(now.findAll(".prefs > *").map((row) => row.classes()[0])).toEqual(before);
    expect(sent("station_radio")).toEqual([]);
  });

  it("has Route's button for a call the book does not hold where no radio that is on carries a path, so that it does not come when the station is heard", () => {
    const twoHf = radiosTopic(
      radioRow(2, "mercury", { name: "20 m" }),
      radioRow(4, "dummy-hf", { name: "40 m", number: 2 }),
    );
    expect(hasRoute(conversation(BOTH, "OH2NEW", stations(), { radios: twoHf }))).toBe(true);
  });

  it("greys Route's rows on a radio that carries no path with the look of every greyed field (`.disabled`, as Ask's and the object's Path), and the path builder says why too", async () => {
    const box = await opened(conversation(BOTH, "OH2HF"));
    const row = box.find(".pathbox:not(.route-radio)");
    expect(row.classes()).toContain("disabled");
    expect(box.find(".pathbuild-open").attributes("title")).toBe("Mercury: no path");
    const live = await opened(conversation(BOTH, "OH2FM"));
    expect([
      live.find(".pathbox:not(.route-radio)").classes(),
      live.find(".pathbuild-open").attributes("title"),
    ]).toEqual([["pathbox"], "Build the path"]);
    const sheet = readFileSync(resolve(__dirname, "../styles/settings.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const dimmed =
      sheet.match(/([^{}]*)\{\s*opacity: 0\.5;\s*\}/g)?.find((rule) => rule.includes(".field.disabled label")) ?? "";
    expect(dimmed).toContain(".pathbox.disabled .path-label");
    expect(dimmed, "RF only stays live on a radio that carries no path").not.toContain(".rfonly");
  });

  it("sets and clears the path of the radio in force: radio 1's as before, another's with the radio named, its own path setting as the automatic one", async () => {
    const values = configValues({}, { "radio/3/path": "WIDE2-2" });
    const mobile = station("OH2MOB", { radio_now: 3, paths: { "3": "OH2RCH-3" } });
    const wrapper = conversation(BOTH, "OH2MOB", stations(mobile), { radios: SIX, config: values });
    const box = await opened(wrapper);
    const field = box.find<HTMLInputElement>(".pathbox input[type='text']");
    expect(field.element.value).toBe("OH2RCH-3");
    await field.setValue("OH2RDG");
    expect(sent("set_station_path")).toEqual([{ cmd: "set_station_path", call: "OH2MOB", path: "OH2RDG", radio: 3 }]);
    await box.find(".use-default").trigger("click");
    expect(sent("clear_station_path")).toEqual([{ cmd: "clear_station_path", call: "OH2MOB", radio: 3 }]);
    await tell(daemon, { stations: stations({ ...mobile, paths: {} }) });
    expect(wrapper.find(".route-box .path-line").text()).toBe("Automatic: WIDE2-2");

    const shack = conversation(BOTH, "OH2FM", stations({ ...fmHeard, radio_now: 1 }), { radios: SIX });
    const own = (await opened(shack)).find<HTMLInputElement>(".pathbox input[type='text']");
    await own.setValue("OH2RCH-2");
    expect(sent("set_station_path")).toEqual([{ cmd: "set_station_path", call: "OH2FM", path: "OH2RCH-2" }]);
    expect(shack.find(".route-box .path-line").text()).toBe("Automatic: WIDE1-1,WIDE2-1");
  });

  it("says as the automatic path the one the radio in force really takes: radio 1's own path, a LoRa radio's WIDE1-1, else the station's symbol's", async () => {
    const lora = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(4, "lora-tcp"));
    const values = configValues({}, { "radio/1/path": "WIDE2-1", "radio/4/path": "" });
    const onLora = conversation(
      { radios: lora },
      "OH2LOR",
      stations(station("OH2LOR", { radio_now: 4, heard: heardBy([4, 3]) })),
      { config: values },
    );
    expect((await opened(onLora)).find(".path-line").text()).toBe("Automatic: WIDE1-1");
    const onFm = conversation({ radios: lora }, "OH2FM", stations({ ...fmHeard, radio_now: 1 }), { config: values });
    expect((await opened(onFm)).find(".path-line").text(), "radio 1's own path, whatever radio is first").toBe(
      "Automatic: WIDE2-1",
    );
  });

  it("has a list of radios of a set width, not the box's, that shrinks with its row and takes it at a phone's width as the Path field does", async () => {
    const sheet = readFileSync(resolve(__dirname, "../styles/messages.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rule = sheet.match(/\.route-radio-pick \{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("flex: 0 1 15em");
    expect(rule).toContain("min-width: 0");
    expect(rule).toContain("max-width: 100%");
    expect(sheet).toMatch(/@media \(max-width: 800px\) \{\s*\.prefs \.pathbox \.input \{\s*flex: 1 1 8em;/);
    const box = await opened(
      conversation(BOTH, "OH2MOB", stations(station("OH2MOB", { radio_now: 3 })), { radios: SIX }),
    );
    expect(box.find(".prefs .pathbox select.input.route-radio-pick").exists()).toBe(true);
  });
});

describe("Route in the station panel", () => {
  it("is there for a station messaged on Packet while the Packet radio is on", () => {
    expect([hasPrefs(panel(FM, fmHeard)), hasPrefs(panel(BOTH, fmHeard)), hasPrefs(panel(BOTH, bothHeard))]).toEqual([
      true,
      true,
      true,
    ]);
  });

  it("is there for a station messaged on Mercury while the Packet radio is on too, greyed, and not while the Packet radio is off (plan section 6)", () => {
    const hf = panel(BOTH, hfHeard);
    expect(hasPrefs(hf)).toBe(true);
    expect(hf.find<HTMLInputElement>(".stationpanel-settings .pathbox input[type='text']").element.disabled).toBe(true);
    expect([hasPrefs(panel(FM_OFF, fmHeard)), hasPrefs(panel(FM_OFF, hfHeard))]).toEqual([false, false]);
  });

  it("has the radio first where more than one is on, and chooses it as the conversation does", async () => {
    const wrapper = panel(BOTH, bothHeard);
    expect(wrapper.findAll(".stationpanel-settings .route-radio option").map((o) => o.text())).toEqual([
      "Automatic: Packet",
      "Packet",
      "Mercury",
    ]);
    await wrapper.find(".stationpanel-settings select").setValue("2");
    expect(sent("station_radio")).toEqual([{ cmd: "station_radio", call: "OH2BOTH", radio: 2 }]);
    expect(panel(FM, fmHeard).find(".stationpanel-settings select").exists()).toBe(false);
  });

  it("shows the radio of the email gateway greyed and chooses nothing: its radio is chosen in the Email tab, and a thing is offered once", () => {
    // a stale choice: it says nothing
    const gateway = station("EMAIL-2", { heard: heardBy([1, 3]), radio_choice: 1, radio_now: 2 });
    const wrapper = panel(BOTH, gateway, { status: status({ email_radio: 2 }) });
    const list = wrapper.find<HTMLSelectElement>(".stationpanel-settings .route-radio select");
    expect([
      list.element.disabled,
      list.element.selectedOptions[0]?.text,
      wrapper.find(".stationpanel-settings .route-radio").classes(),
    ]).toEqual([true, "Mercury", ["pathbox", "route-radio", "disabled"]]);
    expect(sent("station_radio")).toEqual([]);
    const fm = panel(BOTH, gateway, { status: status({ email_radio: 1 }) });
    expect(
      fm.find<HTMLSelectElement>(".stationpanel-settings .route-radio select").element.selectedOptions[0]?.text,
    ).toBe("Packet");
    expect(
      panel(BOTH, bothHeard).find<HTMLSelectElement>(".stationpanel-settings .route-radio select").element.disabled,
    ).toBe(false);
  });
});

describe("the queries of the station panel", () => {
  const twoUp = (fm: "connected" | "waiting", hf: "connected" | "waiting") =>
    radiosTopic(radioRow(1, "kenwood-tnc2", { state: fm }), radioRow(2, "mercury", { state: hf }));
  const queries = ["ask_position", "ask_status", "ask_heard", "ask_trace"];

  it("go while the station's radio is connected, as today with one radio", () => {
    const wrapper = panel(FM, fmHeard);
    expect(queries.map((item) => query(wrapper, item).element.disabled)).toEqual([false, false, false, false]);
  });

  it("are off while the station's radio is not connected, saying which; Message is not, and neither is the other radio's station", () => {
    const wrapper = panel(BOTH, hfHeard, { radios: twoUp("connected", "waiting") });
    expect(
      queries.map((item) => [query(wrapper, item).element.disabled, query(wrapper, item).attributes("title")]),
    ).toEqual(queries.map(() => [true, "Mercury: not connected"]));
    expect(query(wrapper, "message").element.disabled).toBe(false);
    const ask = wrapper.find<HTMLButtonElement>("button[data-query='ask']");
    expect([ask.element.disabled, ask.attributes("title")]).toEqual([true, "Mercury: not connected"]);
    const fm = panel(BOTH, fmHeard, { radios: twoUp("connected", "waiting") });
    expect(queries.map((item) => query(fm, item).element.disabled)).toEqual([false, false, false, false]);
  });

  it("say that the TNC is not connected while the one radio is not", () => {
    const wrapper = panel(
      { radios: radiosTopic(radioRow(1, "kenwood-tnc2", { state: "waiting" }), radioRow(2, "mercury", off)) },
      fmHeard,
      {
        connected: false,
      },
    );
    expect([
      query(wrapper, "ask_position").element.disabled,
      query(wrapper, "ask_position").attributes("title"),
    ]).toEqual([true, "The radio is not connected"]);
  });

  it("grey Trace the route for a station whose radio carries no path, in its place, and leave the others", () => {
    const wrapper = panel(BOTH, hfHeard);
    expect(
      wrapper
        .findAll("[data-item]")
        .map((b) => b.attributes("data-item"))
        .slice(0, 5),
    ).toEqual(["message", ...queries]);
    expect([query(wrapper, "ask_trace").element.disabled, query(wrapper, "ask_trace").attributes("title")]).toEqual([
      true,
      "Mercury: no path",
    ]);
    expect(query(wrapper, "ask_heard").element.disabled).toBe(false);
  });

  it("leave Trace the route out while no radio that is on may carry a path", () => {
    expect(panel(FM_OFF, hfHeard).find("[data-item='ask_trace']").exists()).toBe(false);
    expect(panel(FM_OFF, hfHeard).find("[data-item='ask_heard']").exists()).toBe(true);
  });
});

describe("the path of Ask around and of Local info", () => {
  it("is there while the Packet radio is on, with Mercury on or off", () => {
    for (const values of [FM, BOTH]) {
      expect(hasAdvanced(askPath(values)), "ask around").toBe(true);
      expect(hasAdvanced(qruPath(values)), "local info").toBe(true);
    }
  });

  it("is not there while the Packet radio is off", () => {
    expect(hasAdvanced(askPath(FM_OFF))).toBe(false);
    expect(hasAdvanced(qruPath(FM_OFF))).toBe(false);
  });
});
