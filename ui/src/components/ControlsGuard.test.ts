// The rule for the Settings tab, the My station tab, the Objects form and a station's Route (the station panel's group and the box under a conversation's header): every on/off is a tickbox, never a dropdown with two choices or
// an On/Off word; a dropdown is a real choice of three values or more; and a state is quiet text in a group, never a tag (the tags of state are the top bar's).
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref, shallowRef } from "vue";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import ConversationView from "@/components/ConversationView.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import StationPanel from "@/components/StationPanel.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Scope } from "@/lib/settings";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, fmRow, heardBy, hfRow, igateState, ownObject, radioRow, radiosTopic, station } from "@/test/fixtures";

const ON_OFF = /^(on|off|yes|no|true|false|enabled|disabled|ein|aus|an)$/i;
/** The dropdowns that have two choices and are no on/off: a list of kinds that grows (the HF radio's type is the Mercury modem and the Dummy HF radio today; the keying is the radio by itself and a CM108 chip before the ports are listed). */
const KINDS_OF_TWO = ["set-radio-2-type", "set-radio-2-keying"];

/** The dropdowns of a mounted surface, each as the values it offers. */
function dropdowns(root: Element): { id: string; values: string[] }[] {
  return [...root.querySelectorAll("select")].map((select) => ({ id: select.id, values: [...select.options].map((o) => o.text.trim()) }));
}

function surfaces() {
  const FM_ALONE = radiosTopic(fmRow());
  const scenes: [Scope, Record<string, string>, Record<string, string>, ReturnType<typeof radiosTopic>][] = [
    ["settings", { "igate/enabled": "true", "web/network": "true", "messages/alert": "true" }, { "radio/1/digipeat": "true" }, FM_ALONE],
    ["settings", {}, { "radio/1/tcp_host": "192.168.1.5", "radio/1/tcp_port": "8001" }, radiosTopic(radioRow(1, "kiss-tcp"))],
    [
      "settings",
      {},
      { "radio/2/keying": "vox", "radio/2/sound_card": "", "radio/2/tx_gain_db": "0" },
      radiosTopic(fmRow({ enabled: false, state: "stopped" }), hfRow()),
    ],
    ["beacon", { "gps/source": "gpsd", "beacon/interval_min": "30" }, {}, FM_ALONE],
    ["beacon", { "gps/source": "off", "beacon/interval_min": "0" }, {}, FM_ALONE],
  ];
  const settings = scenes.map(([scope, extra, own, radios]) =>
    mount(SettingsForm, {
      props: { scope },
      global: withDaemon(fakeDaemon({ config: configValues(extra, own), igate: igateState(), radios })),
    }),
  );
  const objects = mount(ObjectForm, {
    props: {
      form: useOwnObjects(new Map([["LEADER", ownObject("LEADER")]]), () => true, {
        show: vi.fn(),
        tab: ref("objects"),
      } as unknown as Panel),
      fallbackPath: "WIDE1-1",
    },
  });
  const alerts = mount(BrowserAlerts, { props: { alerts: useBrowserAlerts(() => undefined) } });
  return [...settings.map((w) => w.element as Element), objects.element as Element, alerts.element as Element];
}

describe("the controls of the Settings tab, the My station tab and the Objects form", () => {
  it("have no dropdown that is an on/off: a dropdown offers a real choice of three values or more, or is a list of what is found or of kinds (a port, a path, a radio type)", () => {
    for (const root of surfaces()) {
      for (const { id, values } of dropdowns(root)) {
        expect(values.length > 0 && values.every((v) => ON_OFF.test(v)), `${id}: ${values.join(" / ")} is an on/off: make it a tickbox`).toBe(false);
        expect(values.length === 2 && !KINDS_OF_TWO.includes(id), `${id}: two choices are a tickbox`).toBe(false);
      }
    }
  });

  it("show no tag in a group: the marks of a state are the top bar's, and a group says its state in quiet text", () => {
    for (const root of surfaces()) {
      const inGroup = [...root.querySelectorAll("fieldset .tag, fieldset .statepill")].filter((e) => !e.closest("[data-allow-tag]"));
      expect(inGroup.map((e) => e.className)).toEqual([]);
    }
  });

  it("have a tickbox first in the group of every feature that can be switched on or off, labelled with its name: RX only, Enable (the FM radio, the Mercury radio, Internet stations, Digipeater), Notify me (on the computer and in the browser)", () => {
    const groups = (root: Element) =>
      [...root.querySelectorAll("fieldset")].map((f) => ({
        legend: f.querySelector("legend")?.textContent?.replace(/\s*i$/, "").trim() ?? "",
        first: f.querySelector(".field input")?.getAttribute("type") ?? "",
        label: f.querySelector(".field label")?.textContent?.trim() ?? "",
      }));
    const all = surfaces().flatMap(groups);
    for (const [legend, label] of [
      ["Radio", "RX only"],
      ["FM radio", "Enable"],
      ["Mercury radio", "Enable"],
      ["Internet stations", "Enable"],
      ["Digipeater", "Enable"],
      ["On the NeoAPRS computer", "Notify me"],
      ["In this browser", "Notify me"],
    ]) {
      const found = all.find((g) => g.legend === legend);
      expect(found, legend).toBeDefined();
      expect([found?.first, found?.label], legend).toEqual(["checkbox", label]);
    }
  });
});

describe("the controls of a station's Route", () => {
  const BOTH = radiosTopic(fmRow(), hfRow());
  const six = radiosTopic(...[1, 2, 3, 4, 5, 6].map((id) => radioRow(id, id % 2 === 1 ? "kiss" : "mercury", { name: `Radio ${id}` })));
  async function routes(given: Parameters<typeof fakeDaemon>[0]) {
    const row = station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]), radio_now: 2 });
    const daemon = fakeDaemon({ radios: BOTH, stations: shallowRef(new Map([[row.call, row]])), ...given });
    const panel = mount(StationPanel, { props: { row, armed: false }, global: withDaemon(daemon) });
    const talk = mount(ConversationView, { props: { selected: row.call, narrow: false, thread: [] }, global: withDaemon(daemon) });
    await talk.find(".route-button").trigger("click");
    return [panel.find(".stationpanel-settings").element, talk.find(".route-box").element];
  }

  it("have the radio as a real choice of three values or more (Automatic and the radios), with two radios as with six", async () => {
    for (const given of [{}, { radios: six }]) {
      for (const root of await routes(given)) {
        const lists = dropdowns(root);
        expect(lists).toHaveLength(1);
        expect(lists[0]?.values.length).toBeGreaterThanOrEqual(3);
        expect(lists[0]?.values.every((v) => ON_OFF.test(v))).toBe(false);
      }
    }
  });

  it("show no tag in Route: the radio is a choice, and what greys the path says it in quiet text", async () => {
    for (const root of await routes({})) expect([...root.querySelectorAll(".tag, .statepill")].map((e) => e.className)).toEqual([]);
  });
});
