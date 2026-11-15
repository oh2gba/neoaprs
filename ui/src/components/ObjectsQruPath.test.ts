// The fold of Local info's Ask (ObjectsQru.vue with RequestPath.vue): the path and RF only of a request to QRU, and that the request is as it always was when they are left alone.
import { mount } from "@vue/test-utils";
import { shallowReactive } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import ObjectsQru from "@/components/ObjectsQru.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { cssRule } from "@/test/css";
import { fakeDaemon, ofRadios, tell, withDaemon } from "@/test/context";
import { ago, configValues, qruAsked, qruState, radioRow, radiosTopic, status } from "@/test/fixtures";
import type { RadioRow, StationPref } from "@/protocol/protocol";

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
const rfOnly = (wrapper: Wrapper) => fold(wrapper).find("input[type='checkbox']");
const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);

beforeEach(() => localStorage.clear());

describe("the path of a request for local info", () => {
  it("is in a closed fold titled Advanced under Ask, as in Ask around, with the beacon's path as the placeholder and RF only ticked", () => {
    const { wrapper } = make();
    expect(fold(wrapper).attributes("open")).toBeUndefined();
    expect(fold(wrapper).find("summary").text()).toBe("Advanced");
    expect(
      fold(wrapper)
        .findAll("label")
        .map((l) => l.text()),
    ).toEqual(["Path", "RF only"]);
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect((rfOnly(wrapper).element as HTMLInputElement).checked).toBe(true);
  });

  it("has the station QRU's own path as the placeholder when it has one", () => {
    const prefs = useStationPrefs(shallowReactive(new Map<string, StationPref>([["QRU", { path: "OH2RCH-2", rf_only: false, alert: null }]])), () => true);
    const { wrapper } = make({ prefs });
    expect(pathField(wrapper).attributes("placeholder")).toBe("OH2RCH-2");
  });

  it("left alone, sends the request as it always went: no path and no RF only in the command", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
  });

  it("sends the path typed, and RF only as it is ticked, with Ask and with a group", async () => {
    const { wrapper, daemon } = make();
    await pathField(wrapper).setValue("OH2RDK-7,OH2RCH-2");
    await ask(wrapper).trigger("click");
    await rfOnly(wrapper).setValue(false);
    await pills(wrapper)[0]?.trigger("click");
    await pathField(wrapper).setValue("");
    expect(sent(daemon)).toEqual([
      { cmd: "qru_ask", text: "INFO 150", path: "OH2RDK-7,OH2RCH-2", rf_only: true },
      { cmd: "qru_ask", text: "RP70 150", path: "OH2RDK-7,OH2RCH-2", rf_only: false },
    ]);
    await ask(wrapper).trigger("click");
    expect(sent(daemon)[2]).toEqual({ cmd: "qru_ask", text: "INFO 150", path: null, rf_only: false });
  });

  it("keeps Ask and the groups off while the path is wrong, with the reason, and the field orange", async () => {
    const { wrapper } = make({ config: configValues() });
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(fold(wrapper).find(".field").classes()).toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Calls separated by commas, at most 8");
    expect(pills(wrapper).every((p) => p.attributes("disabled") !== undefined && p.attributes("title") === "Calls separated by commas, at most 8")).toBe(true);
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
    const { wrapper, daemon } = make({ config: configValues({ "fm/enabled": "false", "hf/enabled": "true" }) });
    expect(fold(wrapper).exists()).toBe(false);
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
    expect(ask(make().wrapper).attributes("disabled")).toBeDefined();
  });
});

describe("the radio of a request for local info (plan rule 3.6)", () => {
  /** A station of these radios as the daemon tells them once the settings of before are gone (lib/radiosides.ts takes the Enable of radios 1 and 2 from those while they are there). */
  function on(given: Parameters<typeof fakeDaemon>[0], ...rows: RadioRow[]) {
    return make({ ...ofRadios(...rows), ...given });
  }
  const FM = radioRow(1, "kenwood-tnc2");
  const HF = radioRow(2, "mercury");
  const choice = (wrapper: Wrapper) => wrapper.find<HTMLSelectElement>("select.qru-radio");
  const line = (wrapper: Wrapper) => wrapper.find(".qrustatus .statusline, .qrustatus").text();

  it("is not chosen, named or sent with one radio on, whichever it is", async () => {
    for (const rows of [[FM], [FM, { ...HF, enabled: false }], [{ ...FM, enabled: false }, HF]]) {
      const { wrapper, daemon } = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(90), rows[0]?.enabled === true ? 1 : 2) }) }, ...rows);
      expect(choice(wrapper).exists()).toBe(false);
      expect(line(wrapper)).not.toMatch(/FM:|HF:/);
      await ask(wrapper).trigger("click");
      expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
    }
  });

  it("is chosen in front of Ask while several are on, as in Ask around, the main radio first and at the start, and goes with the request and with a group's button", async () => {
    const { wrapper, daemon } = on({ status: status({ main_radio: 2 }) }, FM, HF, radioRow(3, "kiss", { name: "Mobile" }));
    expect(choice(wrapper).exists()).toBe(true);
    expect(choice(wrapper).element.nextElementSibling).toBe(ask(wrapper).element);
    expect(choice(wrapper).attributes("aria-label")).toBe("Radio");
    expect(
      choice(wrapper)
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["HF", "FM", "Mobile"]);
    expect(choice(wrapper).element.value).toBe("2");
    await ask(wrapper).trigger("click");
    await choice(wrapper).setValue("3");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "qru_ask", text: "INFO 150", radio: 2 },
      { cmd: "qru_ask", text: "INFO 150", radio: 3 },
    ]);
  });

  it("greys the path, its values kept, on a radio that carries none, and sends none; a radio that carries one has its own path, remembered apart", async () => {
    const { wrapper, daemon } = on({}, FM, HF, radioRow(3, "kiss", { name: "Mobile" }));
    await pathField(wrapper).setValue("OH2RDK-7");
    await choice(wrapper).setValue("2");
    expect(
      fold(wrapper)
        .findAll(".field")
        .every((f) => f.classes().includes("disabled")),
    ).toBe(true);
    expect((pathField(wrapper).element as HTMLInputElement).disabled).toBe(true);
    expect((rfOnly(wrapper).element as HTMLInputElement).disabled).toBe(true);
    expect(fold(wrapper).find("button.pathbuild-open").attributes("disabled")).toBeDefined();
    expect(fold(wrapper).find("button.pathbuild-open").attributes("title"), "the path builder's button says why it is off, as its row does").toBe(
      "HF: no path",
    );
    expect(
      fold(wrapper)
        .findAll(".field")
        .map((f) => f.attributes("title")),
      "the reason, as Route's greyed Path has it",
    ).toEqual(["HF: no path", "HF: no path"]);
    await ask(wrapper).trigger("click");
    await choice(wrapper).setValue("3");
    expect(
      fold(wrapper)
        .findAll(".field")
        .some((f) => f.classes().includes("disabled")),
    ).toBe(false);
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("");
    await pathField(wrapper).setValue("OH2RCH-2");
    await choice(wrapper).setValue("1");
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7");
    expect(sent(daemon)[0]).toEqual({ cmd: "qru_ask", text: "INFO 150", radio: 2 });
    expect(localStorage.getItem("NeoAPRS.qru.path")).toBe("OH2RDK-7");
    expect(localStorage.getItem("NeoAPRS.qru.3.path")).toBe("OH2RCH-2");
  });

  it("holds a wrong path of a radio that carries none against nothing", async () => {
    const { wrapper } = on({}, FM, HF);
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    await choice(wrapper).setValue("2");
    expect(fold(wrapper).find(".field").classes()).not.toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("holds Ask for the minute of the radio the request goes on, not of another", async () => {
    const { wrapper } = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(20), 1) }) }, FM, HF);
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Next request in 40 s");
    await choice(wrapper).setValue("2");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("is off while the radio chosen is not connected, with that as its reason, the radio named", async () => {
    const { wrapper } = on({}, FM, { ...HF, state: "waiting" });
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    await choice(wrapper).setValue("2");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("HF: not connected");
    const one = on({}, { ...FM, state: "waiting" });
    expect(ask(one.wrapper).attributes("title")).toBe("The TNC is not connected");
  });

  it("says on the state word of the status line the radio the request went on, and sends a group's button and Ask again on that radio while it is on", async () => {
    const lost = qruState().servers.map((server) => ({ ...server, received: ["RPKUM"], settles_at: ago(5) }));
    const { wrapper, daemon } = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(90), 2), servers: lost }) }, FM, HF);
    expect(wrapper.find(".qrustatus .statetext").text()).toBe("HF: Asked");
    expect(line(wrapper)).toMatch(/^HF: Asked\s*\d\d:\d\d · /);
    expect(choice(wrapper).element.value).toBe("2"); // (the choice is the radio of the request kept)
    await pills(wrapper)[0]?.trigger("click");
    await wrapper.find("button.qru-again").trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "qru_ask", text: "RP70 150", radio: 2 },
      { cmd: "qru_ask", text: "RP70 150", radio: 2 },
    ]);
  });

  it("sends a group's button on the radio chosen once the radio the request went on is off", async () => {
    const { wrapper, daemon } = on(
      { qru: qruState({ asked: qruAsked("INFO 150", ago(90), 2) }) },
      FM,
      { ...HF, removed: true, enabled: false },
      radioRow(3, "kiss", { name: "Mobile" }),
    );
    expect(line(wrapper)).toMatch(/^HF: Asked\s*\d\d:\d\d · /); // (the radio it went on is named: it is not on)
    expect(choice(wrapper).element.value).toBe("1");
    await pills(wrapper)[0]?.trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "RP70 150", radio: 1 }]);
  });

  it("follows each request to its radio, so that the fold in sight is the one a group's button goes by", async () => {
    const { wrapper, daemon } = on({ qru: qruState({ asked: qruAsked("INFO 150", ago(90), 3) }) }, FM, HF, radioRow(3, "kiss", { name: "FM 2", number: 2 }));
    expect(choice(wrapper).element.value).toBe("3");
    await pathField(wrapper).setValue("OH2RDK-7");
    await rfOnly(wrapper).setValue(false);
    await pills(wrapper)[0]?.trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "RP70 150", path: "OH2RDK-7", rf_only: false, radio: 3 }]);
    await choice(wrapper).setValue("1");
    await tell(daemon, { qru: qruState({ asked: qruAsked("INFO 150", ago(1), 2) }) });
    expect(choice(wrapper).element.value).toBe("2");
    await tell(daemon, { qru: qruState({ asked: qruAsked("INFO 150", ago(0), 1) }) });
    expect(choice(wrapper).element.value).toBe("1");
  });

  it("forgets a choice that goes off: the main radio is chosen, and stays chosen when that radio is on again", async () => {
    const Mobile = radioRow(3, "kiss", { name: "Mobile" });
    const { wrapper, daemon } = on({}, FM, HF, Mobile);
    await choice(wrapper).setValue("3");
    await tell(daemon, { radios: radiosTopic(FM, HF, { ...Mobile, enabled: false }) });
    expect(choice(wrapper).element.value).toBe("1");
    await tell(daemon, { radios: radiosTopic(FM, HF, Mobile) });
    expect(choice(wrapper).element.value).toBe("1");
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150", radio: 1 }]);
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
      choice(wrapper)
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["Shack", "20m", "Mobile", "HFdummy", "Remote12", "40m"]);
    expect(cssRule(".qru-ask")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".qru-radio")).toMatch(/flex:\s*none/);
    expect(cssRule(".qru-radio")).toMatch(/max-width:\s*100%/);
  });
});
