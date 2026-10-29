// The rule for the Settings tab, the My station tab and the Objects form: every on/off is a tickbox, never a dropdown with two choices or an On/Off word; a dropdown is a real choice of three values or more; and a state is quiet text in a group, never a tag (the tags of state are the top bar's).
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Scope } from "@/lib/settings";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, igateState, ownObject, tncState } from "@/test/fixtures";

const ON_OFF = /^(on|off|yes|no|true|false|enabled|disabled|ein|aus|an)$/i;

/** The dropdowns of a mounted surface, each as the values it offers. */
function dropdowns(root: Element): { id: string; values: string[] }[] {
  return [...root.querySelectorAll("select")].map((select) => ({ id: select.id, values: [...select.options].map((o) => o.text.trim()) }));
}

function surfaces() {
  const scenes: [Scope, Record<string, string>][] = [
    ["settings", { "igate/enabled": "true", "digi/enabled": "true", "web/network": "true", "messages/alert": "true" }],
    ["settings", { "tnc/profile": "network", "tcp/host": "192.168.1.5", "tcp/port": "8001" }],
    ["beacon", { "gps/source": "gpsd", "beacon/interval_min": "30" }],
    ["beacon", { "gps/source": "off", "beacon/interval_min": "0" }],
  ];
  const settings = scenes.map(([scope, extra]) =>
    mount(SettingsForm, { props: { scope }, global: withDaemon(fakeDaemon({ config: configValues(extra), igate: igateState(), tnc: tncState() })) }),
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
  it("have no dropdown that is an on/off: a dropdown offers a real choice of three values or more, or is a list of what is found (a port, a path)", () => {
    for (const root of surfaces()) {
      for (const { id, values } of dropdowns(root)) {
        expect(
          values.every((v) => ON_OFF.test(v)),
          `${id}: ${values.join(" / ")} is an on/off: make it a tickbox`,
        ).toBe(false);
        expect(values.length === 2 && !/port|path|language|kind/i.test(id), `${id}: two choices are a tickbox`).toBe(false);
      }
    }
  });

  it("show no tag in a group: the marks of a state are the top bar's, and a group says its state in quiet text", () => {
    for (const root of surfaces()) {
      const inGroup = [...root.querySelectorAll("fieldset .tag, fieldset .statepill")].filter((e) => !e.closest("[data-allow-tag]"));
      expect(inGroup.map((e) => e.className)).toEqual([]);
    }
  });

  it("have a tickbox first in the group of every feature that can be switched on or off, labelled with its name: RX only, Enable (Internet stations, Digipeater), Alert", () => {
    const groups = (root: Element) =>
      [...root.querySelectorAll("fieldset")].map((f) => ({
        legend: f.querySelector("legend")?.textContent?.replace(/\s*i$/, "").trim() ?? "",
        first: f.querySelector(".field input")?.getAttribute("type") ?? "",
        label: f.querySelector(".field label")?.textContent?.trim() ?? "",
      }));
    const all = surfaces().flatMap(groups);
    for (const [legend, label] of [
      ["Radio", "RX only"],
      ["Internet stations", "Enable"],
      ["Digipeater", "Enable"],
      ["On the NeoAPRS computer", "Alert"],
      ["In this browser", "Alert"],
    ]) {
      const found = all.find((g) => g.legend === legend);
      expect(found, legend).toBeDefined();
      expect([found?.first, found?.label], legend).toEqual(["checkbox", label]);
    }
  });
});
