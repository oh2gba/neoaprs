import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import NearbyAsk from "@/components/NearbyAsk.vue";
import { clockText } from "@/lib/format";
import { fakeDaemon, ofRadios, tell, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { ago, configValues, NOW, radioRow, radiosTopic, status, toastOf } from "@/test/fixtures";
import type { GeneralAsked, GeneralState, RadioRow } from "@/protocol/protocol";

function make(given: Parameters<typeof fakeDaemon>[0] = {}) {
  const daemon = fakeDaemon({ fallbackPath: "WIDE1-1,WIDE2-1", ...given });
  const wrapper = mount(NearbyAsk, { global: withDaemon(daemon) });
  return { wrapper, daemon };
}
type Wrapper = ReturnType<typeof make>["wrapper"];
const ask = (wrapper: Wrapper) => wrapper.find(".ask-row button.btn");
const choice = (wrapper: Wrapper) => wrapper.find("select.ask-kind");
const fold = (wrapper: Wrapper) => wrapper.find("details.disclosure");
const pathField = (wrapper: Wrapper) => wrapper.find("details input[type='text']");
const rfOnly = (wrapper: Wrapper) => wrapper.find("details input[type='checkbox']");
const lines = (wrapper: Wrapper) => wrapper.findAll("p.ask-line");
const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);

function askedOf(extra: Partial<GeneralAsked> = {}): GeneralAsked {
  const at = extra.at ?? ago(20);
  return {
    kind: "aprs",
    query: "?APRS?",
    radio: 1,
    at,
    path: ["OH2RDK-7", "OH2RCH-2", "RFONLY"],
    until: new Date(Date.parse(at) + 120_000).toISOString(),
    new: [],
    ...extra,
  };
}
/** The topic as the daemon tells it while the queries went on one radio: the last of each kind is also the last of each kind on that radio. */
const general = (...asked: GeneralAsked[]): GeneralState => ({ asked, by_radio: asked });

beforeEach(() => localStorage.clear());

describe("Ask around in the Nearby tab", () => {
  it("is a group box with an (i), the query in plain words with the query itself in each hover, and Ask", async () => {
    const { wrapper } = make();
    expect(wrapper.find("fieldset > legend").text().replace(/ ?i$/, "")).toBe("Ask around");
    await wrapper.find("legend button.info-toggle").trigger("click");
    expect(wrapper.find("legend .info-text").text()).toContain(
      "Stations answer with their position, iGates with what they do, weather stations with their weather.",
    );
    expect(
      choice(wrapper)
        .findAll("option")
        .map((o) => [o.text(), o.attributes("title")]),
    ).toEqual([
      ["Who is around", "?APRS?"],
      ["iGates", "?IGATE?"],
      ["Weather stations", "?WX?"],
    ]);
    expect(choice(wrapper).attributes("title")).toBe("?APRS?");
    expect(ask(wrapper).text()).toBe("Ask");
    expect(ask(wrapper).attributes("title")).toBe("Send ?APRS? once, by radio");
  });

  it("sends the query chosen by the beacon's path with RF only, as the fold starts", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    await choice(wrapper).setValue("wx");
    expect(ask(wrapper).attributes("title")).toBe("Send ?WX? once, by radio");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "general_query", kind: "aprs", path: null, rf_only: true },
      { cmd: "general_query", kind: "wx", path: null, rf_only: true },
    ]);
  });

  it("has the path and RF only in a closed fold titled Advanced, the path's placeholder the beacon's path, RF only ticked; what is set there goes with the query", async () => {
    const { wrapper, daemon } = make();
    expect(fold(wrapper).attributes("open")).toBeUndefined();
    expect(fold(wrapper).find("summary").text()).toBe("Advanced");
    expect(
      fold(wrapper)
        .findAll("label")
        .map((l) => l.text()),
    ).toEqual(["Path", "RF only"]);
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect((rfOnly(wrapper).element as HTMLInputElement).checked).toBe(true);
    await pathField(wrapper).setValue(" oh2rdk-7,OH2RCH-2 ");
    await rfOnly(wrapper).setValue(false);
    await choice(wrapper).setValue("igate");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "igate", path: "oh2rdk-7,OH2RCH-2", rf_only: false }]);
  });

  it("says direct as the placeholder when the beacon's path is direct", () => {
    const { wrapper } = make({ fallbackPath: "" });
    expect(pathField(wrapper).attributes("placeholder")).toBe("direct");
  });

  it("remembers the query, the path and RF only in this browser, and opens the fold when they are not the usual", async () => {
    const first = make();
    await choice(first.wrapper).setValue("igate");
    await pathField(first.wrapper).setValue("OH2RDK-7,OH2RCH-2");
    await rfOnly(first.wrapper).setValue(false);
    first.wrapper.unmount();
    const { wrapper, daemon } = make();
    expect((choice(wrapper).element as HTMLSelectElement).value).toBe("igate");
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7,OH2RCH-2");
    expect((rfOnly(wrapper).element as HTMLInputElement).checked).toBe(false);
    expect(fold(wrapper).attributes("open")).toBeDefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "igate", path: "OH2RDK-7,OH2RCH-2", rf_only: false }]);
    expect(localStorage.getItem("NeoAPRS.qru.path")).toBeNull();
  });

  it("shows a wrong path the way the other path fields do, and keeps Ask off with the reason", async () => {
    const { wrapper, daemon } = make();
    for (const wrong of ["OH2RDK-7,???", "WIDE1-1,DIRECT", "A1,A2,A3,A4,A5,A6,A7,A8,A9"]) {
      await pathField(wrapper).setValue(wrong);
      expect(wrapper.find("details .field").classes(), wrong).toContain("invalid");
      expect(wrapper.find("details .field").attributes("title"), wrong).toBe("Calls separated by commas, at most 8");
      expect(ask(wrapper).attributes("disabled"), wrong).toBeDefined();
      expect(ask(wrapper).attributes("title"), wrong).toBe("Calls separated by commas, at most 8");
    }
    await pathField(wrapper).setValue("A1,A2,A3,A4,A5,A6,A7,A8");
    expect(ask(wrapper).attributes("title")).toBe("path too long for RF only: 8 digipeaters and RFONLY make more than the 8 a path may have");
    await rfOnly(wrapper).setValue(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await pathField(wrapper).setValue("direct");
    expect(wrapper.find("details .field").classes()).not.toContain("invalid");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: "direct", rf_only: false }]);
  });

  it("keeps Ask off in RX only, and for the minute after a query of the same kind, with the seconds left; another kind may go", async () => {
    const rx = make({ config: configValues({ "station/transmit": "false" }) });
    expect(ask(rx.wrapper).attributes("disabled")).toBeDefined();
    expect(ask(rx.wrapper).attributes("title")).toBe("RX only: nothing is sent");
    const { wrapper, daemon } = make({ general: general(askedOf({ at: ago(20) })) });
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Asked a moment ago: again in 40 s");
    await ask(wrapper).trigger("click");
    await choice(wrapper).setValue("igate");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await choice(wrapper).setValue("aprs");
    await tell(daemon, { now: NOW + 40_000 });
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    expect(sent(daemon)).toEqual([]);
  });

  it("keeps two quiet lines whatever they say: what Ask does before a query, then what was asked, when and by what path, and who spoke after it", async () => {
    const { wrapper, daemon } = make();
    expect(lines(wrapper).map((l) => l.text())).toEqual(["Asks the stations in radio range to make themselves known.", ""]);
    const at = ago(20);
    const time = clockText(at).slice(0, 5);
    await tell(daemon, { general: general(askedOf({ at })) });
    expect(lines(wrapper)).toHaveLength(2);
    expect(lines(wrapper)[0]?.text()).toBe(`Asked who is around at ${time} by OH2RDK-7,OH2RCH-2; answers arrive on the map and in Stations`);
    expect(lines(wrapper)[0]?.attributes("title")).toBe("?APRS? OH2RDK-7,OH2RCH-2,RFONLY");
    expect(lines(wrapper)[1]?.text()).toBe("Listening for stations that were quiet in the 10 minutes before…");
    await tell(daemon, { general: general(askedOf({ at, new: ["OH2DPN", "OH2XYZ"] })) });
    expect(lines(wrapper)[1]?.text()).toBe("2 stations quiet in the 10 minutes before have spoken since…");
    expect(lines(wrapper)[1]?.attributes("title")).toBe(
      "OH2DPN, OH2XYZ. Most are likely answers; a station whose own beacon fell in those minutes counts too.",
    );
    await tell(daemon, { now: NOW + 120_000 });
    expect(lines(wrapper)[1]?.text()).toBe("2 stations quiet in the 10 minutes before spoke in the 2 minutes after");
    await tell(daemon, { general: general(askedOf({ at: ago(300), new: [] }), askedOf({ kind: "wx", query: "?WX?", at: ago(10), path: [] })) });
    expect(lines(wrapper)[0]?.text()).toMatch(/^Asked the weather stations at \d\d:\d\d by direct; answers arrive/);
  });

  it("says a refusal of the daemon in the first line, in the warn colour, until the next query", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    await tell(daemon, { lastError: toastOf("general_query: too soon for another ?APRS?: wait 12 s", "general.too_soon", { query: "?APRS?", seconds: 12 }) });
    expect(lines(wrapper)[0]?.text()).toBe("Not sent: too soon for another ?APRS?: wait 12 s");
    expect(lines(wrapper)[0]?.classes()).toContain("warn");
    expect(lines(wrapper)[1]?.text()).toBe("");
    await tell(daemon, { general: general(askedOf({ at: ago(1) })) });
    expect(lines(wrapper)[0]?.classes()).not.toContain("warn");
    expect(lines(wrapper)[0]?.text()).toMatch(/^Asked who is around/);
  });

  it("does not hold Ask for a stored path that is wrong while the FM radio is off and the fold is not there, and sends no path", async () => {
    localStorage.setItem("NeoAPRS.ask.path", "not a path!");
    const { wrapper, daemon } = make({ radios: radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury")) });
    expect(fold(wrapper).exists()).toBe(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: null, rf_only: true }]);
    const withFm = make();
    expect(ask(withFm.wrapper).attributes("disabled")).toBeDefined();
  });
});

describe("the radio of Ask around (plan rule 3.6)", () => {
  /** A station of these radios as the daemon tells them: the topic `radios`. */
  function on(given: Parameters<typeof fakeDaemon>[0], ...rows: RadioRow[]) {
    return make({ ...ofRadios(...rows), ...given });
  }
  const FM = radioRow(1, "kenwood-tnc2");
  const HF = radioRow(2, "mercury");
  const radio = (wrapper: Wrapper) => wrapper.find<HTMLSelectElement>("select.ask-radio");

  it("is not chosen, named or sent with one radio on, whichever it is", async () => {
    for (const rows of [[FM], [FM, { ...HF, enabled: false }], [{ ...FM, enabled: false }, HF]]) {
      const id = rows[0]?.enabled === true ? 1 : 2;
      const { wrapper, daemon } = on({ general: general(askedOf({ at: ago(90), radio: id })) }, ...rows);
      expect(radio(wrapper).exists()).toBe(false);
      expect(lines(wrapper)[0]?.text()).toMatch(/^Asked who is around/);
      await ask(wrapper).trigger("click");
      expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: null, rf_only: true }]);
    }
  });

  it("is chosen beside Ask while several are on, after the query, the main radio first and at the start, and goes with the query", async () => {
    const { wrapper, daemon } = on({ status: status({ main_radio: 2 }) }, FM, HF, radioRow(3, "kiss", { name: "Mobile" }));
    expect(
      wrapper
        .find(".ask-row")
        .findAll("select, button")
        .map((e) => e.classes()[1] ?? e.text()),
    ).toEqual(["ask-kind", "ask-radio", "Ask"]);
    expect(radio(wrapper).attributes("aria-label")).toBe("Radio");
    expect(
      radio(wrapper)
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["Mercury", "FM", "Mobile"]);
    expect(radio(wrapper).element.value).toBe("2");
    expect(fold(wrapper).find(".field").classes()).toContain("disabled"); // (HF carries no path)
    await ask(wrapper).trigger("click");
    await radio(wrapper).setValue("3");
    expect(fold(wrapper).find(".field").classes()).not.toContain("disabled");
    await pathField(wrapper).setValue("OH2RDK-7");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "general_query", kind: "aprs", path: null, rf_only: true, radio: 2 },
      { cmd: "general_query", kind: "aprs", path: "OH2RDK-7", rf_only: true, radio: 3 },
    ]);
    expect(localStorage.getItem("NeoAPRS.ask.3.path")).toBe("OH2RDK-7");
    expect(localStorage.getItem("NeoAPRS.ask.path")).toBeNull();
  });

  it("forgets a choice that goes off: the main radio is chosen, and stays chosen when that radio is on again", async () => {
    const Mobile = radioRow(3, "kiss", { name: "Mobile" });
    const { wrapper, daemon } = on({}, FM, HF, Mobile);
    await radio(wrapper).setValue("3");
    await tell(daemon, { radios: radiosTopic(FM, HF, { ...Mobile, enabled: false }) });
    expect(radio(wrapper).element.value).toBe("1");
    await tell(daemon, { radios: radiosTopic(FM, HF, Mobile) });
    expect(radio(wrapper).element.value).toBe("1");
    await ask(wrapper).trigger("click");
    expect(sent(daemon).at(-1)).toMatchObject({ cmd: "general_query", radio: 1 });
  });

  it("holds Ask for the minute of a kind on the radio the query goes on, not on another", async () => {
    const first = askedOf({ at: ago(20), radio: 1 });
    const { wrapper } = on({ general: { asked: [first], by_radio: [first] } }, FM, HF);
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Asked a moment ago: again in 40 s");
    await radio(wrapper).setValue("2");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    const both = { asked: [askedOf({ at: ago(30), radio: 2 })], by_radio: [first, askedOf({ at: ago(30), radio: 2 })] };
    const later = on({ general: both }, FM, HF);
    expect(ask(later.wrapper).attributes("title")).toBe("Asked a moment ago: again in 40 s"); // (FM's own, though HF's is the latest)
  });

  it("is off while the radio chosen is not connected, with that as its reason, the radio named", async () => {
    const { wrapper } = on({}, FM, { ...HF, state: "connecting" });
    await radio(wrapper).setValue("2");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Mercury: not connected");
    const one = on({}, { ...FM, state: "waiting" });
    expect(ask(one.wrapper).attributes("title")).toBe("The radio is not connected");
    const none = on({ status: status({ main_radio: null }) }, { ...FM, enabled: false, state: "stopped" });
    expect(ask(none.wrapper).attributes("title")).toBe("there is no radio: add one, or turn one on");
  });

  it("says in the first line the radio the latest query went on, and not in a refusal, which says it itself", async () => {
    const at = ago(20);
    const time = clockText(at).slice(0, 5);
    const asked = askedOf({ at, radio: 2, path: [] });
    const { wrapper, daemon } = on({ general: { asked: [asked], by_radio: [asked] } }, FM, HF);
    expect(lines(wrapper)[0]?.text()).toBe(`Mercury: Asked who is around at ${time} by direct; answers arrive on the map and in Stations`);
    expect(lines(wrapper)[1]?.text()).toBe("Listening for stations that were quiet in the 10 minutes before…");
    await ask(wrapper).trigger("click");
    await tell(daemon, { lastError: toastOf("general_query: radio Mercury is not connected", "radio.not_connected", { name: "Mercury" }) });
    expect(lines(wrapper)[0]?.text()).toBe("Not sent: radio Mercury is not connected");
    expect(lines(wrapper)).toHaveLength(2);
  });

  it("offers six radios by names of up to eight characters on a phone, the row wrapping and the choice as wide as its longest name", () => {
    const six = [
      radioRow(1, "kenwood-tnc2", { name: "Shack" }),
      radioRow(2, "mercury", { name: "20m" }),
      radioRow(3, "kiss", { name: "Mobile" }),
      radioRow(4, "dummy-hf", { name: "HFdummy" }),
      radioRow(5, "kiss-tcp", { name: "Remote12" }),
      radioRow(6, "mercury", { name: "40m", number: 2 }),
    ];
    const { wrapper } = on({}, ...six);
    expect(
      radio(wrapper)
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["Shack", "20m", "Mobile", "HFdummy", "Remote12", "40m"]);
    expect(cssRule(".ask-row")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".ask-radio")).toMatch(/flex:\s*none/);
    expect(cssRule(".ask-line")).toMatch(/text-overflow:\s*ellipsis/); // (a line with the radio's name in front keeps its one line)
  });
});
