import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import NearbyAsk from "@/components/NearbyAsk.vue";
import { clockText } from "@/lib/format";
import { fakeDaemon, ofRadios, tell, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { ago, configValues, NOW, radioRow, radiosTopic, status, toastOf } from "@/test/fixtures";
import type { Command, GeneralAsked, GeneralState, RadioRow } from "@/protocol/protocol";

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
const lines = (wrapper: Wrapper) => wrapper.findAll("p.ask-line");
const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);

function askedOf(extra: Partial<GeneralAsked> = {}): GeneralAsked {
  const at = extra.at ?? ago(20);
  return {
    kind: "aprs",
    query: "?APRS?",
    radios: [1],
    at,
    path: ["OH2RDK-7", "OH2RCH-2", "RFONLY"],
    until: new Date(Date.parse(at) + 120_000).toISOString(),
    new: [],
    ...extra,
  };
}
/** The topic as the daemon tells it: the last query of each kind, and when each went on each of
 * its radios. */
const general = (...asked: GeneralAsked[]): GeneralState => ({
  asked,
  by_radio: asked.flatMap((one) => one.radios.map((radio) => ({ kind: one.kind, radio, at: one.at }))),
});

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

  it("sends the query chosen by the beacon's path, with no RF only in the command (the daemon adds RFONLY)", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    await tell(daemon, { general: general(askedOf()) });
    await choice(wrapper).setValue("wx");
    expect(ask(wrapper).attributes("title")).toBe("Send ?WX? once, by radio");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "general_query", kind: "aprs", path: null },
      { cmd: "general_query", kind: "wx", path: null },
    ]);
  });

  it("has the path alone in a closed fold titled Advanced, its placeholder its radio's path, and no RF only tick; the path goes with the query", async () => {
    const { wrapper, daemon } = make();
    expect(fold(wrapper).attributes("open")).toBeUndefined();
    expect(fold(wrapper).find("summary").text()).toBe("Advanced");
    expect(
      fold(wrapper)
        .findAll("label")
        .map((l) => l.text()),
    ).toEqual(["Path"]);
    expect(fold(wrapper).find("input[type='checkbox']").exists()).toBe(false);
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    await pathField(wrapper).setValue(" oh2rdk-7,OH2RCH-2 ");
    await choice(wrapper).setValue("igate");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "igate", path: "oh2rdk-7,OH2RCH-2" }]);
  });

  it("says direct as the placeholder when its radio's path is direct", () => {
    const { wrapper } = make({ config: configValues({}, { "radio/1/path": "DIRECT" }) });
    expect(pathField(wrapper).attributes("placeholder")).toBe("direct");
  });

  it("has as its placeholder the path its ticked radios share, each as the daemon gives it, and the page's word for the default while theirs differ", async () => {
    const ticked = { beacon: true, status: false, ask: true, local_info: false, path: "", digipeat: false };
    const FM = radioRow(1, "kenwood-tnc2", { choices: ticked });
    const LORA = radioRow(3, "lora-tcp", { choices: { ...ticked, digipeat: null } });
    const config = (lora: string) =>
      configValues({}, { "radio/1/path": "", "radio/1/ask": "true", "radio/3/path": lora, "radio/3/ask": "true" });
    const { wrapper, daemon } = make({ ...ofRadios(FM, LORA), config: config("") });
    expect(
      pathField(wrapper).attributes("placeholder"),
      "Packet by the station's symbol (WIDE1-1,WIDE2-1 here), LoRa by WIDE1-1",
    ).toBe("(default)");
    await tell(daemon, { config: config("WIDE1-1,WIDE2-1") });
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    await tell(daemon, {
      radios: radiosTopic(FM, radioRow(2, "mercury", { choices: { ...ticked, path: null, digipeat: null } })),
    });
    expect(pathField(wrapper).attributes("placeholder"), "the Mercury radio carries no path: Packet's alone").toBe(
      "WIDE1-1,WIDE2-1",
    );
  });

  it("remembers the query and the path in this browser, and opens the fold when a path is typed", async () => {
    const first = make();
    await choice(first.wrapper).setValue("igate");
    await pathField(first.wrapper).setValue("OH2RDK-7,OH2RCH-2");
    first.wrapper.unmount();
    const { wrapper, daemon } = make();
    expect((choice(wrapper).element as HTMLSelectElement).value).toBe("igate");
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7,OH2RCH-2");
    expect(fold(wrapper).attributes("open")).toBeDefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "igate", path: "OH2RDK-7,OH2RCH-2" }]);
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
    expect(ask(wrapper).attributes("title")).toBe(
      "path too long for RF only: 8 digipeaters and RFONLY make more than the 8 a path may have",
    );
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await pathField(wrapper).setValue("direct");
    expect(wrapper.find("details .field").classes()).not.toContain("invalid");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: "direct" }]);
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
    expect(lines(wrapper).map((l) => l.text())).toEqual([
      "Asks the stations in radio range to make themselves known.",
      "",
    ]);
    const at = ago(20);
    const time = clockText(at).slice(0, 5);
    await tell(daemon, { general: general(askedOf({ at })) });
    expect(lines(wrapper)).toHaveLength(2);
    expect(lines(wrapper)[0]?.text()).toBe(
      `Asked who is around at ${time} by OH2RDK-7,OH2RCH-2; answers arrive on the map and in Stations`,
    );
    expect(lines(wrapper)[0]?.attributes("title")).toBe("?APRS? OH2RDK-7,OH2RCH-2,RFONLY");
    expect(lines(wrapper)[1]?.text()).toBe("Listening for stations that were quiet in the 10 minutes before…");
    await tell(daemon, { general: general(askedOf({ at, new: ["OH2DPN", "OH2XYZ"] })) });
    expect(lines(wrapper)[1]?.text()).toBe("2 stations quiet in the 10 minutes before have spoken since…");
    expect(lines(wrapper)[1]?.attributes("title")).toBe(
      "OH2DPN, OH2XYZ. Most are likely answers; a station whose own beacon fell in those minutes counts too.",
    );
    await tell(daemon, { now: NOW + 120_000 });
    expect(lines(wrapper)[1]?.text()).toBe("2 stations quiet in the 10 minutes before spoke in the 2 minutes after");
    await tell(daemon, {
      general: general(
        askedOf({ at: ago(300), new: [] }),
        askedOf({ kind: "wx", query: "?WX?", at: ago(10), path: [] }),
      ),
    });
    expect(lines(wrapper)[0]?.text()).toMatch(/^Asked the weather stations at \d\d:\d\d by direct; answers arrive/);
  });

  it("names no path in the first line while its radios went each by its own and those differ, for every kind; the hover is the query alone", async () => {
    const { wrapper, daemon } = make();
    const at = ago(20);
    const time = clockText(at).slice(0, 5);
    const said = {
      aprs: `Asked who is around at ${time}; answers arrive on the map and in Stations`,
      igate: `Asked the iGates at ${time}; answers arrive on the map and in Stations`,
      wx: `Asked the weather stations at ${time}; answers arrive on the map and in Stations`,
    };
    for (const [kind, query] of [
      ["aprs", "?APRS?"],
      ["igate", "?IGATE?"],
      ["wx", "?WX?"],
    ] as const) {
      await tell(daemon, { general: general(askedOf({ kind, query, at, radios: [1, 3], path: null })) });
      expect(lines(wrapper)[0]?.text(), kind).toBe(said[kind]);
      expect(lines(wrapper)[0]?.text(), kind).not.toContain("(default)");
      expect(lines(wrapper)[0]?.attributes("title"), kind).toBe(query);
    }
  });

  it("says a refusal of the daemon in the first line, in the warn colour, until the next query", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    await tell(daemon, {
      lastError: toastOf("general_query: too soon for another ?APRS?: wait 12 s", "general.too_soon", {
        query: "?APRS?",
        seconds: 12,
      }),
    });
    expect(lines(wrapper)[0]?.text()).toBe("Not sent: too soon for another ?APRS?: wait 12 s");
    expect(lines(wrapper)[0]?.classes()).toContain("warn");
    expect(lines(wrapper)[1]?.text()).toBe("");
    await tell(daemon, { general: general(askedOf({ at: ago(1) })) });
    expect(lines(wrapper)[0]?.classes()).not.toContain("warn");
    expect(lines(wrapper)[0]?.text()).toMatch(/^Asked who is around/);
  });

  it("does not hold Ask for a stored path that is wrong while the Packet radio is off and the fold is not there, and sends no path", async () => {
    localStorage.setItem("NeoAPRS.ask.path", "not a path!");
    const { wrapper, daemon } = make({
      radios: radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury")),
    });
    expect(fold(wrapper).exists()).toBe(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: null }]);
    const withFm = make();
    expect(ask(withFm.wrapper).attributes("disabled")).toBeDefined();
  });
});

describe("the Send on of Ask around", () => {
  /** A station of these radios as the daemon tells them: the topic `radios`. */
  function on(given: Parameters<typeof fakeDaemon>[0], ...rows: RadioRow[]) {
    return make({ ...ofRadios(...rows), ...given });
  }
  const FM = radioRow(1, "kenwood-tnc2");
  const HF = radioRow(2, "mercury");
  const Mobile = radioRow(3, "kiss", { name: "Mobile" });
  const ticked = (row: RadioRow, ask = true): RadioRow => ({ ...row, choices: { ...row.choices, ask } });
  const sendOn = (wrapper: Wrapper) => wrapper.find("#ask-send-on").element.closest(".field");
  const ticks = (wrapper: Wrapper) =>
    wrapper.findAll<HTMLInputElement>("#ask-send-on ~ .field-control input[type=checkbox]");
  const shown = (wrapper: Wrapper) =>
    ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined]);
  const queries = (daemon: ReturnType<typeof make>["daemon"]): Command[] =>
    sent(daemon).filter((command) => command.cmd === "general_query");
  const saves = (daemon: ReturnType<typeof make>["daemon"]): Command[] =>
    sent(daemon).filter((command) => command.cmd === "set_config");

  it("is not there with one radio that can send, whichever it is: nothing is ticked, named or sent with the query", async () => {
    for (const rows of [
      [FM],
      [FM, { ...HF, enabled: false }],
      [{ ...FM, enabled: false }, HF],
      [FM, radioRow(4, "tnc-text")],
    ]) {
      const id = rows[0]?.enabled === true ? 1 : 2;
      const { wrapper, daemon } = on({ general: general(askedOf({ at: ago(90), radios: [id] })) }, ...rows);
      expect(wrapper.find("#ask-send-on").exists()).toBe(false);
      expect(wrapper.find(".ask-row select:not(.ask-kind)").exists()).toBe(false);
      expect(lines(wrapper)[0]?.text()).toMatch(
        rows.length === 2 && rows.every((row) => row.enabled) ? /^Packet: Asked who is around/ : /^Asked who is around/,
      );
      await ask(wrapper).trigger("click");
      expect(sent(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: null }]);
    }
  });

  it("is the beacon's row on a row of its own under Ask, before the fold: a tick for each radio that can send, by its name, and no select of a radio", () => {
    const { wrapper } = on({}, FM, HF, radioRow(4, "tnc-text"), { ...Mobile, enabled: false });
    const row = sendOn(wrapper);
    expect(row?.querySelector(".field-label")?.textContent).toBe("Send on");
    expect(row?.getAttribute("role")).toBe("group");
    expect(row?.getAttribute("aria-labelledby")).toBe("ask-send-on");
    expect(row?.querySelector(".field-control")?.classList.contains("toolbar-checks")).toBe(true);
    expect(row?.previousElementSibling).toBe(wrapper.find(".ask-row").element);
    expect(row?.nextElementSibling).toBe(fold(wrapper).element);
    expect(ticks(wrapper).map((tick) => tick.attributes("id"))).toEqual(["set-radio-1-ask", "set-radio-2-ask"]);
    expect([...(row?.querySelectorAll("label.check") ?? [])].map((label) => label.textContent)).toEqual([
      "Packet",
      "Mercury",
    ]);
    expect(
      wrapper
        .find(".ask-row")
        .findAll("select, button")
        .map((e) => e.classes()[1] ?? e.text()),
    ).toEqual(["ask-kind", "Ask"]);
    expect(row?.querySelector("p, small, .hint")).toBeNull(); // (no line that explains it)
  });

  it("starts with no tick ticked and Ask off without a title, and a tick sends that tick alone", async () => {
    const { wrapper, daemon } = on({ status: status({ unheard_radio: 2 }) }, FM, HF, Mobile);
    expect(shown(wrapper)).toEqual([
      [false, false],
      [false, false],
      [false, false],
    ]);
    expect([ask(wrapper).attributes("disabled") !== undefined, ask(wrapper).attributes("title")]).toEqual([
      true,
      "Send ?APRS? once, by radio",
    ]);
    await ask(wrapper).trigger("click");
    expect(queries(daemon)).toEqual([]);
    await ticks(wrapper)[0]?.setValue(true);
    expect(saves(daemon)).toEqual([{ cmd: "set_config", values: { "radio/1/ask": "true" } }]);
    expect(shown(wrapper)).toEqual([
      [true, true],
      [false, false],
      [false, false],
    ]);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await ask(wrapper).trigger("click");
    expect(queries(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: null }]);
  });

  it("ticks as the daemon has it, greys the last one ticked, and applies a tick at once", async () => {
    const { wrapper, daemon } = on({}, ticked(FM), ticked(HF), Mobile);
    expect(shown(wrapper)).toEqual([
      [true, false],
      [true, false],
      [false, false],
    ]);
    await ticks(wrapper)[0]?.setValue(false);
    expect(saves(daemon)).toEqual([{ cmd: "set_config", values: { "radio/1/ask": "false" } }]);
    expect(shown(wrapper)).toEqual([
      [false, false],
      [true, true],
      [false, false],
    ]);
  });

  it("has one Path fold for every radio, kept by the browser under the key of before, greyed with its value kept while no ticked radio carries a path", async () => {
    const { wrapper, daemon } = on({}, ticked(FM), ticked(HF), Mobile);
    await pathField(wrapper).setValue("OH2RDK-7");
    expect(localStorage.getItem("NeoAPRS.ask.path")).toBe("OH2RDK-7");
    expect(Object.keys(localStorage).filter((key) => /ask\.\d/.test(key))).toEqual([]);
    expect(fold(wrapper).find(".field").classes()).not.toContain("disabled");
    await ask(wrapper).trigger("click");
    expect(queries(daemon)).toEqual([{ cmd: "general_query", kind: "aprs", path: "OH2RDK-7" }]);
    await tell(daemon, { general: general(askedOf()) });
    await ticks(wrapper)[0]?.setValue(false); // (Mercury alone, which carries no path)
    expect(
      fold(wrapper)
        .findAll(".field")
        .every((field) => field.classes().includes("disabled")),
    ).toBe(true);
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7");
    expect((pathField(wrapper).element as HTMLInputElement).disabled).toBe(true);
    expect(
      fold(wrapper)
        .findAll(".field")
        .map((field) => field.attributes("title")),
    ).toEqual(["Mercury: no path"]);
    await choice(wrapper).setValue("igate");
    await ask(wrapper).trigger("click");
    expect(queries(daemon)[1]).toEqual({ cmd: "general_query", kind: "igate", path: null });
    await ticks(wrapper)[2]?.setValue(true); // (and the Mobile radio, which carries one)
    expect(fold(wrapper).find(".field").classes()).not.toContain("disabled");
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7");
  });

  it("does not hold Ask for a wrong path while no ticked radio carries one", async () => {
    const { wrapper } = on({}, ticked(FM), ticked(HF));
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await ticks(wrapper)[0]?.setValue(false);
    expect(fold(wrapper).find(".field").classes()).not.toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("holds Ask while one of the ticked radios is inside its minute for the kind, and not for the minute of a radio that is not ticked", async () => {
    const first = askedOf({ at: ago(20), radios: [1] });
    const { wrapper } = on({ general: general(first) }, ticked(FM), ticked(HF));
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Asked a moment ago: again in 40 s");
    await ticks(wrapper)[0]?.setValue(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    const both = {
      asked: [askedOf({ at: ago(30), radios: [2] })],
      by_radio: [...general(first).by_radio, { kind: "aprs" as const, radio: 2, at: ago(30) }],
    };
    const later = on({ general: both }, ticked(FM), ticked(HF));
    expect(ask(later.wrapper).attributes("title")).toBe("Asked a moment ago: again in 40 s");
  });

  it("is on while one ticked radio is connected, and off with a line for each while none is", () => {
    const one = on({}, ticked(FM), ticked({ ...HF, state: "connecting" }));
    expect(ask(one.wrapper).attributes("disabled")).toBeUndefined();
    const none = on({}, ticked({ ...FM, state: "waiting" }), ticked({ ...HF, state: "connecting" }));
    expect(ask(none.wrapper).attributes("disabled")).toBeDefined();
    expect(ask(none.wrapper).attributes("title")).toBe("Packet: not connected\nMercury: not connected");
    const hf = on({}, FM, ticked({ ...HF, state: "connecting" }));
    expect(ask(hf.wrapper).attributes("title")).toBe("Mercury: not connected");
    const alone = on({}, { ...FM, state: "waiting" });
    expect(ask(alone.wrapper).attributes("title")).toBe("The radio is not connected");
    const off = on({ status: status({ unheard_radio: null }) }, { ...FM, enabled: false, state: "stopped" });
    expect(ask(off.wrapper).attributes("title")).toBe("there is no radio: add one, or turn one on");
  });

  it("names in the first line the radios the latest query went on, and not in a refusal, which says it itself", async () => {
    const at = ago(20);
    const time = clockText(at).slice(0, 5);
    const { wrapper, daemon } = on({ general: general(askedOf({ at, radios: [1, 2] })) }, ticked(FM), ticked(HF));
    expect(lines(wrapper)[0]?.text()).toBe(
      `Packet and Mercury: Asked who is around at ${time} by OH2RDK-7,OH2RCH-2; answers arrive on the map and in Stations`,
    );
    expect(lines(wrapper)[1]?.text()).toBe("Listening for stations that were quiet in the 10 minutes before…");
    await tell(daemon, { general: general(askedOf({ at, radios: [2], path: [] })) });
    expect(lines(wrapper)[0]?.text()).toBe(
      `Mercury: Asked who is around at ${time} by direct; answers arrive on the map and in Stations`,
    );
    await tell(daemon, { general: general(askedOf({ at, radios: [1, 3], path: null })) });
    expect(lines(wrapper)[0]?.text()).toBe(
      `Packet: Asked who is around at ${time}; answers arrive on the map and in Stations`,
    );
    expect(lines(wrapper)[0]?.attributes("title")).toBe("?APRS?");
    await ask(wrapper).trigger("click");
    await tell(daemon, {
      lastError: toastOf("general_query: radio Mercury is not connected", "radio.not_connected", { name: "Mercury" }),
    });
    expect(lines(wrapper)[0]?.text()).toBe("Not sent: radio Mercury is not connected");
    expect(lines(wrapper)).toHaveLength(2);
  });

  it("keeps six radios by names of up to eight characters on a phone: the ticks wrap in their row, and each line keeps its one line", () => {
    const six = [
      radioRow(1, "kenwood-tnc2", { name: "Shack" }),
      radioRow(2, "mercury", { name: "20m" }),
      radioRow(3, "kiss", { name: "Mobile" }),
      radioRow(4, "dummy-hf", { name: "HFdummy" }),
      radioRow(5, "kiss-tcp", { name: "Remote12" }),
      radioRow(6, "mercury", { name: "40m", number: 2 }),
    ];
    const { wrapper } = on({}, ...six);
    expect([...(sendOn(wrapper)?.querySelectorAll("label.check") ?? [])].map((label) => label.textContent)).toEqual([
      "Shack",
      "20m",
      "Mobile",
      "HFdummy",
      "Remote12",
      "40m",
    ]);
    expect(cssRule(".toolbar-checks")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".ask-row")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".ask-line")).toMatch(/text-overflow:\s*ellipsis/);
  });
});

describe("Ask around in flight", () => {
  it("sends once for two clicks before the daemon tells the query, and again once it has", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toHaveLength(1);
    await tell(daemon, { general: general(askedOf()) });
    await choice(wrapper).setValue("wx");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toHaveLength(2);
  });
});
