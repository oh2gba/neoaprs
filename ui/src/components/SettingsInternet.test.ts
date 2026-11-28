import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, igateState, station, table } from "@/test/fixtures";

const LEGEND = "Internet (APRS-IS)";
const THREE = ["Show Internet stations", "Send what I hear", "Show Internet packets heard by radio"];

function make(extra: Record<string, string> = {}, more: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === LEGEND);
  const labels = () =>
    group()
      ?.findAll(".field")
      .map((f) => f.find("label").text());
  return { wrapper, daemon, group, labels };
}

describe("the Internet (APRS-IS) group of the Settings tab", () => {
  it("is after the Radio group and has three ticks, Show Internet stations, Send what I hear and Show Internet packets heard by radio, each with its (i): no passcode, no server, no note", () => {
    const { wrapper, group, labels } = make({ "igate/enabled": "true" }, { igate: igateState() });
    const legends = wrapper.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(legends.slice(0, 2)).toEqual(["Radio", LEGEND]);
    expect(labels()).toEqual(THREE);
    expect(group()?.findAll("input[type=checkbox]")).toHaveLength(3);
    expect(group()?.findAll("input")).toHaveLength(3);
    expect(group()?.findAll(".infotip")).toHaveLength(3);
    for (const gone of [
      "#set-igate-server",
      "#set-igate-password",
      "a.btn",
      ".igate-note",
      ".igate-request",
      ".problem",
    ])
      expect(group()?.find(gone).exists(), gone).toBe(false);
    expect(group()?.find(".tncstatus").text()).toBe("rotate.aprs2.net · no stations within 150 km yet");
    expect(group()?.text()).not.toMatch(/passcode/i);
  });

  it("keeps the status row's room while neither tick is on, so nothing below moves when one is ticked", async () => {
    const { wrapper, group } = make({}, { igate: igateState({ state: "off", enabled: false, gate: false }) });
    const row = () => group()?.find(".igatestatus");
    expect(row()?.exists()).toBe(true);
    expect(row()?.classes()).toContain("field-room");
    expect(row()?.attributes("aria-hidden")).toBe("true");
    expect(row()?.attributes("inert")).toBeDefined();
    await group()?.find<HTMLInputElement>("input[type=checkbox]").setValue(true);
    await wrapper.vm.$nextTick();
    expect(row()?.classes()).not.toContain("field-room");
    expect(row()?.attributes("aria-hidden")).toBeUndefined();
  });

  it("has the two ticks of APRS-IS off and Show Internet packets heard by radio on by default", () => {
    const { group } = make({}, { igate: igateState({ state: "off", enabled: false, gate: false }) });
    expect(
      group()
        ?.findAll<HTMLInputElement>("input[type=checkbox]")
        .map((i) => i.element.checked),
    ).toEqual([false, false, true]);
  });

  it("has the status row of the radio under the ticks: the arrow, the state word in the colour of the state, the quiet line, and behind the arrow the server, the filter and what was sent", () => {
    const { group } = make(
      { "igate/enabled": "true", "igate/gate": "true" },
      {
        igate: igateState({ gated: 3 }),
        stations: table(station("OH2NET", { heard_is: 4 }), station("OH2RF", { heard_rf: 4 })),
      },
    );
    const fold = group()?.find("details.statusfold");
    expect(fold?.exists()).toBe(true);
    const fields = group()?.element.querySelectorAll(".field");
    expect(fields?.[1]?.compareDocumentPosition(fold?.element as Element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(fold?.find("summary.statushead .statetext").classes()).toContain("tnc-connected");
    expect(fold?.find("summary .statetext").text()).toBe("connected");
    expect(fold?.find(".tncstatus").text()).toBe("rotate.aprs2.net · 1 station within 150 km");
    expect(fold?.findAll(".igatefold").map((p) => p.text())).toEqual([
      "Server: T2FINLAND (rotate.aprs2.net)",
      "Filter: stations within 150 km of your position",
      "Sent: 3 packets since NeoAPRS started",
    ]);
  });

  it("says what was sent, and asks for no stations, while only Send what I hear is ticked", () => {
    const { group } = make({ "igate/gate": "true" }, { igate: igateState({ enabled: false, gate: true, gated: 1 }) });
    expect(group()?.find(".tncstatus").text()).toBe("rotate.aprs2.net · 1 packet sent");
    expect(
      group()
        ?.findAll(".igatefold")
        .map((p) => p.text()),
    ).toEqual(["Server: T2FINLAND (rotate.aprs2.net)", "Sent: 1 packet since NeoAPRS started"]);
  });

  it("says in the (i) of Show Internet stations, in one line, what it shows", async () => {
    const { group } = make();
    const [show] = group()?.findAll(".field") ?? [];
    await show?.find(".info-toggle").trigger("click");
    expect(show?.findAll(".info-line").map((l) => l.text())).toEqual([
      "Shows APRS-IS stations within your map's radius.",
    ]);
  });

  it("says in the (i) of Send what I hear, in two lines, that the station is then an iGate and that a message to EMAIL-2 reaches it", async () => {
    const { group } = make();
    const gate = group()?.findAll(".field")[1];
    await gate?.find(".info-toggle").trigger("click");
    expect(gate?.findAll(".info-line").map((l) => l.text())).toEqual([
      "Puts what your radios hear on APRS-IS: your station is then an iGate for its radios.",
      "A message heard on the radio for a service such as EMAIL-2 reaches it this way.",
    ]);
    expect(gate?.find(".infotip button").attributes("title")).toBeUndefined();
  });

  it("shows only the ticks while both are off, and the status line the moment either is on", async () => {
    const { group, labels } = make({}, { igate: igateState({ state: "off", enabled: false, gate: false }) });
    const shown = () => !group()?.find(".igatestatus").classes().includes("field-room");
    expect(labels()).toEqual(THREE);
    expect(shown()).toBe(false);
    for (const id of ["#set-igate-enabled", "#set-igate-gate"]) {
      await group()?.find(id).setValue(true);
      expect(shown(), id).toBe(true);
      await group()?.find(id).setValue(false);
      expect(shown(), id).toBe(false);
    }
    await group()?.find("#set-igate-show_gated").setValue(false);
    expect(shown(), "the third tick logs in to nothing").toBe(false);
  });

  it("says Connecting to the server while it connects, why it is not connected, and that the server did not take the login", () => {
    const line = (
      given: Parameters<typeof igateState>[0],
      values: Record<string, string> = { "igate/enabled": "true" },
    ) =>
      make(values, { igate: igateState(given) })
        .group()
        ?.find(".tncstatus")
        .text();
    expect(line({ state: "connecting", server: "T2FINLAND" })).toBe("Connecting to T2FINLAND…");
    expect(line({ state: "connecting", reason: "unreachable" })).toBe("Not connected: the server cannot be reached");
    expect(line({ state: "unverified", reason: "unverified" }, { "igate/gate": "true" })).toBe(
      "Not sending: the server did not accept the login",
    );
  });

  it("shows the two ticks of APRS-IS greyed, which cannot be ticked, and no status row, while the call is not set: no line says why", () => {
    const { group, labels } = make({ "station/call": "" }, { igate: igateState({ state: "connecting" }) });
    expect(labels()).toEqual(THREE);
    const boxes = group()?.findAll<HTMLInputElement>("input[type=checkbox]") ?? [];
    expect(boxes.map((b) => b.element.disabled)).toEqual([true, true, false]);
    expect(group()?.findAll(".field.disabled")).toHaveLength(2);
    expect(group()?.find(".tncstatus").exists()).toBe(false);
    expect(group()?.find(".problem").exists()).toBe(false);
    expect(group()?.text()).not.toMatch(/call/i);
  });

  it("lets the ticks be ticked as soon as the call is set", async () => {
    const { daemon, group } = make({ "station/call": "" });
    await tell(daemon, { config: configValues({ "station/call": "OH2GBA" }) });
    const boxes = group()?.findAll<HTMLInputElement>("input[type=checkbox]") ?? [];
    expect(boxes.map((b) => b.element.disabled)).toEqual([false, false, false]);
  });

  it("sends each tick as it is changed, on its own", async () => {
    for (const [key, value] of [
      ["igate/enabled", true],
      ["igate/gate", true],
      ["igate/show_gated", false],
    ] as const) {
      const { group, daemon } = make();
      await group()
        ?.find(`#set-${key.replace("/", "-")}`)
        .setValue(value);
      expect(daemon.send).toHaveBeenCalledWith({ cmd: "set_config", values: { [key]: String(value) } });
    }
  });

  it("says in the (i) of Show Internet packets heard by radio, in one line and a picture, what it leaves out", async () => {
    const { group } = make();
    const gated = group()?.findAll(".field")[2];
    const button = gated?.find(".infotip button");
    expect(button?.attributes("aria-label")).toBe("About Internet packets heard by radio");
    expect(button?.attributes("title")).toBeUndefined();
    await button?.trigger("click");
    expect(gated?.findAll(".info-line").map((l) => l.text())).toEqual([
      "Some iGates put packets from the Internet on the air. Unticked, they are left out, except a message to you.",
    ]);
    expect(gated?.find("svg.hp").attributes("data-picture")).toBe("gated");
  });
});
