// Every labelled input, select and checkbox of the Objects form and of the Settings tab has an (i) beside it (InfoTip), so that a field added later cannot be left without one. A field that deliberately has none is in
// ALLOWED with the reason; a stale entry (a field that has a tip now or is gone) fails too, so that the list cannot grow into an excuse.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Scope } from "@/lib/settings";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, ownObject } from "@/test/fixtures";

/** The fields that have no (i) on purpose, by the text of their label, with why. */
const ALLOWED_OBJECTS: Record<string, string> = {
  // the place is the Location control of the Beacon tab, shared by the Objects form and the setup guide; its button and the place in words say what it is
  Latitude: "part of the Location control: a coordinate, in degrees",
  Longitude: "part of the Location control: a coordinate, in degrees",
  Locator: "part of the Location control: a Maidenhead locator, which the field shows",
};
const ALLOWED_SETTINGS: Record<string, string> = {
  Call: "a call sign is what it says",
  Language: "the choice is the languages' own names",
  "TCP host": "an address, which the placeholder shows",
  "TCP port": "a number, with the programs' usual ports in its title",
  Alert: "the (i) of its group, On the NeoAPRS computer, explains the alert and its command",
  Command: "the (i) of its group, On the NeoAPRS computer, explains the alert and its command",
  "Alert for a new message": "the choice names what each answer does (off, sound, pop-up)",
};

/** The labelled controls of a mounted surface with no (i) in their own field, by the text of their label. */
function untipped(root: Element): string[] {
  const missing: string[] = [];
  for (const control of root.querySelectorAll<HTMLElement>("input:not([type=hidden]), select, textarea")) {
    const label = control.id ? root.querySelector(`label[for="${control.id}"]`) : null;
    const wrapping = control.closest("label");
    const name = (label ?? wrapping)?.textContent?.replace(/\s+/g, " ").trim();
    if (!name) continue;
    const field = control.closest(".field");
    const tipped = field !== null && [...field.querySelectorAll(".infotip")].some((tip) => tip.closest(".field") === field);
    if (!tipped) missing.push(name.replace(/\s*i$/, ""));
  }
  return missing;
}

function objectsForm(rows = [ownObject("LEADER")]) {
  const view = useOwnObjects(new Map(rows.map((r) => [r.name, r])), ref({ lat: 60.17, lon: 24.94 }), () => true, {
    show: vi.fn(),
    tab: ref("objects"),
  } as unknown as Panel);
  return mount(ObjectForm, { props: { form: view, fallbackPath: "WIDE1-1,WIDE2-1" } });
}

function settingsTab(scope: Scope, extra: Record<string, string>) {
  return mount(SettingsForm, { props: { scope }, global: withDaemon(fakeDaemon({ config: configValues(extra) })) });
}

describe("every field has an (i)", () => {
  it("in the Objects form, with the entry of the place and the folds opened", async () => {
    const wrapper = objectsForm();
    await wrapper.find(".location-place").trigger("click");
    for (const fold of (wrapper.element as HTMLElement).querySelectorAll("details")) fold.open = true;
    const names = untipped(wrapper.element as HTMLElement);
    expect(names.filter((n) => !(n in ALLOWED_OBJECTS))).toEqual([]);
    expect(Object.keys(ALLOWED_OBJECTS).filter((n) => !names.includes(n))).toEqual([]);
  });

  it("in the Settings tab, in every group, with the folds opened", () => {
    // (a radio on the network, a GPS on a serial port and the rest that only some settings show)
    const scenes: [Scope, Record<string, string>][] = [
      ["settings", {}],
      ["settings", { "tnc/profile": "network", "tcp/host": "192.168.1.5", "tcp/port": "8001" }],
      ["beacon", { "gps/source": "serial", "gps/baud": "9600" }],
      ["beacon", { "gps/source": "gpsd" }],
    ];
    const missing = new Set<string>();
    for (const [scope, extra] of scenes) {
      const wrapper = settingsTab(scope, extra);
      for (const fold of (wrapper.element as HTMLElement).querySelectorAll("details")) fold.open = true;
      for (const name of untipped(wrapper.element as HTMLElement)) missing.add(name);
    }
    expect([...missing].filter((n) => !(n in ALLOWED_SETTINGS))).toEqual([]);
    expect(Object.keys(ALLOWED_SETTINGS).filter((n) => !missing.has(n))).toEqual([]);
  });
});
