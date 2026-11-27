// The fold of Local info's Ask (ObjectsQru.vue with RequestPath.vue): the path of a request to QRU,
// and that the request is unchanged when it is left alone.
import { mount } from "@vue/test-utils";
import { shallowReactive } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import ObjectsQru from "@/components/ObjectsQru.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { cssRule } from "@/test/css";
import { fakeDaemon, ofRadios, tell, withDaemon } from "@/test/context";
import { ago, configValues, NOW, qruAsked, qruState, radioRow, radiosTopic, status } from "@/test/fixtures";
import type { Command, QruServer, RadioRow, StationPref } from "@/protocol/protocol";

function make(given: Parameters<typeof fakeDaemon>[0] = {}) {
  const daemon = fakeDaemon({ fallbackPath: "WIDE1-1,WIDE2-1", qru: qruState({ asked: null }), ...given });
  const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
  return { wrapper, daemon };
}
type Wrapper = ReturnType<typeof make>["wrapper"];
const ask = (wrapper: Wrapper) => wrapper.find(".qru-ask button.btn");
const pills = (wrapper: Wrapper) => wrapper.findAll("button.qru-group");
const fold = (wrapper: Wrapper) => wrapper.find("details.disclosure");
const pathField = (wrapper: Wrapper) => fold(wrapper).find("input[type='text']");
const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);
let told = 0;
/** The daemon tells the request it took, long enough ago to hold nothing back: the next press
 * sends. */
const answer = (daemon: ReturnType<typeof make>["daemon"]) =>
  tell(daemon, {
    qru: { ...(daemon.qru.value ?? qruState({ asked: null })), asked: qruAsked("INFO", ago(100 + ++told)) },
  });

beforeEach(() => localStorage.clear());

describe("the path of a request for local info", () => {
  it("is in a closed fold titled Advanced under Ask, as in Ask around, with its radio's path as the placeholder and no RF only tick", () => {
    const { wrapper } = make();
    expect(fold(wrapper).attributes("open")).toBeUndefined();
    expect(fold(wrapper).find("summary").text()).toBe("Advanced");
    expect(
      fold(wrapper)
        .findAll("label")
        .map((l) => l.text()),
    ).toEqual(["Path"]);
    expect(fold(wrapper).find("input[type='checkbox']").exists()).toBe(false);
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
  });

  it("has as its placeholder the path its ticked radios share, a LoRa radio's own WIDE1-1 among them, and the page's word for the default while theirs differ", async () => {
    const ticked = { beacon: true, status: false, ask: false, local_info: true, path: "", digipeat: false };
    const LORA = radioRow(3, "lora-tcp", { choices: { ...ticked, digipeat: null } });
    const config = (fm: string) =>
      configValues(
        {},
        { "radio/1/path": fm, "radio/1/local_info": "true", "radio/3/path": "", "radio/3/local_info": "true" },
      );
    const { wrapper, daemon } = make({
      ...ofRadios(radioRow(1, "kenwood-tnc2", { choices: ticked }), LORA),
      config: config(""),
    });
    expect(pathField(wrapper).attributes("placeholder")).toBe("(default)");
    await tell(daemon, { config: config("WIDE1-1") });
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1");
  });

  it("has the station QRU's own path as the placeholder when it has one", () => {
    const prefs = useStationPrefs(
      shallowReactive(new Map<string, StationPref>([["QRU", { path: "OH2RCH-2", rf_only: false, alert: null }]])),
      () => true,
    );
    const { wrapper } = make({ prefs });
    expect(pathField(wrapper).attributes("placeholder")).toBe("OH2RCH-2");
  });

  it("left alone, sends the request as it always went: no path and no RF only in the command", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
  });

  it("sends the path typed with Ask and with a group, and none once it is emptied", async () => {
    const { wrapper, daemon } = make();
    await pathField(wrapper).setValue("OH2RDK-7,OH2RCH-2");
    await ask(wrapper).trigger("click");
    await answer(daemon);
    await pills(wrapper)[0]?.trigger("click");
    await answer(daemon);
    await pathField(wrapper).setValue("");
    expect(sent(daemon)).toEqual([
      { cmd: "qru_ask", text: "INFO 150", path: "OH2RDK-7,OH2RCH-2" },
      { cmd: "qru_ask", text: "RP70 150", path: "OH2RDK-7,OH2RCH-2" },
    ]);
    await ask(wrapper).trigger("click");
    expect(sent(daemon)[2]).toEqual({ cmd: "qru_ask", text: "INFO 150" });
  });

  it("keeps Ask and the groups off while the path is wrong, with the reason, and the field orange", async () => {
    const { wrapper } = make({ config: configValues() });
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(fold(wrapper).find(".field").classes()).toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Calls separated by commas, at most 8");
    expect(
      pills(wrapper).every(
        (p) =>
          p.attributes("disabled") !== undefined && p.attributes("title") === "Calls separated by commas, at most 8",
      ),
    ).toBe(true);
  });

  it("is remembered by the browser apart from Ask around's, and opens the fold when it is not the usual", async () => {
    const first = make();
    await pathField(first.wrapper).setValue("OH2RDK-7,OH2RCH-2");
    first.wrapper.unmount();
    expect(localStorage.getItem("NeoAPRS.qru.path")).toBe("OH2RDK-7,OH2RCH-2");
    expect(localStorage.getItem("NeoAPRS.ask.path")).toBeNull();
    const { wrapper } = make();
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7,OH2RCH-2");
    expect(fold(wrapper).attributes("open")).toBeDefined();
  });

  it("does not hold Ask for a stored path that is wrong while the FM radio is off and the fold is not there, and sends no path", async () => {
    localStorage.setItem("NeoAPRS.qru.path", "not a path!");
    const { wrapper, daemon } = make({
      radios: radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury")),
    });
    expect(fold(wrapper).exists()).toBe(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
    expect(ask(make().wrapper).attributes("disabled")).toBeDefined();
  });
});

describe("the Send on of Local info", () => {
  /** A station of these radios as the daemon tells them: the topic `radios`. */
  function on(given: Parameters<typeof fakeDaemon>[0], ...rows: RadioRow[]) {
    return make({ ...ofRadios(...rows), ...given });
  }
  const FM = radioRow(1, "kenwood-tnc2");
  const HF = radioRow(2, "mercury");
  const Mobile = radioRow(3, "kiss", { name: "Mobile" });
  const ticked = (row: RadioRow, local_info = true): RadioRow => ({ ...row, choices: { ...row.choices, local_info } });
  const sendOn = (wrapper: Wrapper) => wrapper.find("#qru-send-on").element.closest(".field");
  const ticks = (wrapper: Wrapper) =>
    wrapper.findAll<HTMLInputElement>("#qru-send-on ~ .field-control input[type=checkbox]");
  const shown = (wrapper: Wrapper) =>
    ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined]);
  const line = (wrapper: Wrapper) => wrapper.find(".qrustatus .statusline, .qrustatus").text();
  const requests = (daemon: ReturnType<typeof make>["daemon"]): Command[] =>
    sent(daemon).filter((command) => command.cmd === "qru_ask");
  const saves = (daemon: ReturnType<typeof make>["daemon"]): Command[] =>
    sent(daemon).filter((command) => command.cmd === "set_config");
  const tags = (wrapper: Wrapper) => wrapper.findAll("li.qru-server .qru-call .tag").map((tag) => tag.text());
  /** The fixture's server, as it answered on that radio. */
  const answeredOn = (radio: number | null, extra: Partial<QruServer> = {}): QruServer[] =>
    qruState().servers.map((server) => ({ ...server, radio, ...extra }));

  it("is not there with one radio that can send, whichever it is: nothing is ticked, tagged, named or sent with the request", async () => {
    for (const rows of [[FM], [FM, { ...HF, enabled: false }], [{ ...FM, enabled: false }, HF]]) {
      const id = rows[0]?.enabled === true ? 1 : 2;
      const { wrapper, daemon } = on(
        { qru: qruState({ asked: qruAsked("INFO 150", ago(90), id), servers: answeredOn(id) }) },
        ...rows,
      );
      expect(wrapper.find("#qru-send-on").exists()).toBe(false);
      expect(wrapper.find(".qru-ask select").exists()).toBe(false);
      expect(tags(wrapper)).toEqual([]);
      expect(line(wrapper)).not.toMatch(/FM:|Mercury:/);
      await ask(wrapper).trigger("click");
      await answer(daemon);
      await pills(wrapper)[0]?.trigger("click");
      expect(sent(daemon)).toEqual([
        { cmd: "qru_ask", text: "INFO 150" },
        { cmd: "qru_ask", text: "RP70 150" },
      ]);
    }
  });

  it("is the beacon's row on a row of its own under Ask, before the fold: a tick for each radio that can send, by its name, and no select of a radio", () => {
    const { wrapper } = on({}, FM, HF, radioRow(4, "tnc-text"), { ...Mobile, enabled: false });
    const row = sendOn(wrapper);
    expect(row?.querySelector(".field-label")?.textContent).toBe("Send on");
    expect(row?.getAttribute("aria-labelledby")).toBe("qru-send-on");
    expect(row?.previousElementSibling).toBe(wrapper.find(".qru-ask").element);
    expect(row?.nextElementSibling).toBe(fold(wrapper).element);
    expect(ticks(wrapper).map((tick) => tick.attributes("id"))).toEqual([
      "set-radio-1-local_info",
      "set-radio-2-local_info",
    ]);
    expect([...(row?.querySelectorAll("label.check") ?? [])].map((label) => label.textContent)).toEqual([
      "FM",
      "Mercury",
    ]);
    expect(wrapper.find(".qru-ask").element.firstElementChild).toBe(ask(wrapper).element);
    expect(wrapper.find(".qru-ask select").exists()).toBe(false);
  });

  it("starts with no tick ticked and Ask off without a title, and a tick sends that tick alone; Ask names no radio", async () => {
    const { wrapper, daemon } = on({ status: status({ unheard_radio: 2 }) }, FM, HF, Mobile);
    expect(shown(wrapper)).toEqual([
      [false, false],
      [false, false],
      [false, false],
    ]);
    expect([ask(wrapper).attributes("disabled") !== undefined, ask(wrapper).attributes("title")]).toEqual([
      true,
      undefined,
    ]);
    await ask(wrapper).trigger("click");
    expect(requests(daemon)).toEqual([]);
    await ticks(wrapper)[2]?.setValue(true);
    expect(saves(daemon)).toEqual([{ cmd: "set_config", values: { "radio/3/local_info": "true" } }]);
    expect(shown(wrapper)).toEqual([
      [false, false],
      [false, false],
      [true, true],
    ]);
    await ask(wrapper).trigger("click");
    expect(requests(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
  });

  it("has one Path fold for every radio, kept by the browser under the key of before, greyed with its value kept while no ticked radio carries a path", async () => {
    const { wrapper, daemon } = on({}, ticked(FM), ticked(HF), Mobile);
    await pathField(wrapper).setValue("OH2RDK-7");
    expect(localStorage.getItem("NeoAPRS.qru.path")).toBe("OH2RDK-7");
    expect(Object.keys(localStorage).filter((key) => /qru\.\d/.test(key))).toEqual([]);
    await ask(wrapper).trigger("click");
    expect(requests(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150", path: "OH2RDK-7" }]);
    await answer(daemon);
    await ticks(wrapper)[0]?.setValue(false); // (Mercury alone, which carries no path)
    expect(
      fold(wrapper)
        .findAll(".field")
        .every((field) => field.classes().includes("disabled")),
    ).toBe(true);
    expect((pathField(wrapper).element as HTMLInputElement).disabled).toBe(true);
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7");
    expect(fold(wrapper).find("button.pathbuild-open").attributes("disabled")).toBeDefined();
    expect(
      fold(wrapper).find("button.pathbuild-open").attributes("title"),
      "the path builder's button says why it is off, as its row does",
    ).toBe("Mercury: no path");
    expect(
      fold(wrapper)
        .findAll(".field")
        .map((field) => field.attributes("title")),
      "the reason, as Route's greyed Path has it",
    ).toEqual(["Mercury: no path"]);
    await tell(daemon, { now: NOW + 61_000 });
    await ask(wrapper).trigger("click");
    expect(requests(daemon)[1]).toEqual({ cmd: "qru_ask", text: "INFO 150" });
  });

  it("does not hold Ask for a wrong path while no ticked radio carries one", async () => {
    const { wrapper } = on({}, ticked(FM), ticked(HF));
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await ticks(wrapper)[0]?.setValue(false);
    expect(fold(wrapper).find(".field").classes()).not.toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("holds Ask while a ticked radio is inside its minute, and not for the minute of a radio that is not ticked", async () => {
    const { wrapper } = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(20), 1), servers: [] }) },
      ticked(FM),
      ticked(HF),
    );
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Next request in 40 s");
    await ticks(wrapper)[0]?.setValue(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("is on while one ticked radio is connected, and off with a line for each while none is", () => {
    const one = on({}, ticked(FM), ticked({ ...HF, state: "waiting" }));
    expect(ask(one.wrapper).attributes("disabled")).toBeUndefined();
    const none = on({}, ticked({ ...FM, state: "waiting" }), ticked({ ...HF, state: "waiting" }));
    expect(ask(none.wrapper).attributes("disabled")).toBeDefined();
    expect(ask(none.wrapper).attributes("title")).toBe("FM: not connected\nMercury: not connected");
    const alone = on({}, { ...FM, state: "waiting" });
    expect(ask(alone.wrapper).attributes("title")).toBe("The radio is not connected");
  });

  it("names on the state word of the status line the radios the request went on", () => {
    const { wrapper } = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(90), 1, 2) }) }, ticked(FM), ticked(HF));
    expect(wrapper.find(".qrustatus .statetext").text()).toBe("FM and Mercury: Asked");
    expect(line(wrapper)).toMatch(/^FM and Mercury: Asked\s*\d\d:\d\d · /);
  });

  it("tags a server's row with the radio it answered on, and sends its group's button and Ask again on that radio, whatever is ticked", async () => {
    const lost = answeredOn(2, { received: ["RPKUM"], settles_at: ago(5) });
    const { wrapper, daemon } = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(90), 1, 2), servers: lost }) },
      ticked(FM),
      HF,
    );
    expect(tags(wrapper)).toEqual(["Mercury"]);
    expect(wrapper.find("li.qru-server .qru-call .tag").attributes("title")).toBe("Heard on radio Mercury");
    expect(wrapper.find("li.qru-server .qru-call").text()).toBe("DF8LS-10Mercury");
    expect(wrapper.find("li.qru-server .qru-call .mono").text()).toBe("DF8LS-10");
    await pills(wrapper)[0]?.trigger("click");
    await answer(daemon);
    await wrapper.find("button.qru-again").trigger("click");
    expect(requests(daemon)).toEqual([
      { cmd: "qru_ask", text: "RP70 150", radio: 2 },
      { cmd: "qru_ask", text: "RP70 150", radio: 2 },
    ]);
  });

  it("holds a group's button for its server's radio alone: its wait, its link and its path", async () => {
    const servers = answeredOn(2);
    const waiting = on({ qru: qruState({ asked: qruAsked("RP70 150", ago(20), 1), servers }) }, ticked(FM), HF);
    expect(pills(waiting.wrapper)[0]?.attributes("disabled")).toBeUndefined();
    const away = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(90), 1), servers }) }, ticked(FM), {
      ...HF,
      state: "waiting",
    });
    expect(pills(away.wrapper)[0]?.attributes("title")).toBe("Mercury: not connected");
    expect(ask(away.wrapper).attributes("disabled")).toBeUndefined();
    const { wrapper, daemon } = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(90), 1), servers }) },
      ticked(FM),
      HF,
    );
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await pills(wrapper)[0]?.trigger("click");
    expect(requests(daemon)).toEqual([{ cmd: "qru_ask", text: "RP70 150", radio: 2 }]);
  });

  it("sends a group's button on the radios of Send on once the radio the server answered on is off, or when it named none", async () => {
    const gone = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(90), 2), servers: answeredOn(2) }) },
      ticked(FM),
      { ...HF, removed: true, enabled: false },
      ticked(Mobile),
    );
    expect(tags(gone.wrapper)).toEqual(["Mercury"]); // (the radio it answered on is named: it is not on)
    expect(line(gone.wrapper)).toMatch(/^Mercury: Asked\s*\d\d:\d\d · /);
    await pills(gone.wrapper)[0]?.trigger("click");
    expect(requests(gone.daemon)).toEqual([{ cmd: "qru_ask", text: "RP70 150" }]);
    const none = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(90), 1), servers: answeredOn(null) }) },
      ticked(FM),
      ticked(HF),
    );
    expect(tags(none.wrapper)).toEqual([]);
    await pills(none.wrapper)[0]?.trigger("click");
    expect(requests(none.daemon)).toEqual([{ cmd: "qru_ask", text: "RP70 150" }]);
  });

  it("keeps six radios by names of up to eight characters on a phone: the ticks wrap in their row", () => {
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
    expect(cssRule(".qru-ask")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".toolbar-checks")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".qru-call")).toMatch(/display:\s*inline-flex/);
  });
});
