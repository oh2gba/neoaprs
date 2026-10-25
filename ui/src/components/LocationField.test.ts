import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LocationField from "@/components/LocationField.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { cssRule, mediaRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues } from "@/test/fixtures";
import { ref } from "vue";
import { vi } from "vitest";

function make(props: Record<string, unknown> = {}) {
  return mount(LocationField, { props: { id: "loc", place: "60.17 N, 24.94 E · KP20le", picking: false, lat: "60.17", lon: "24.94", ...props } });
}

describe("LocationField", () => {
  it("is one row: the plain Choose on map button at the left and, beside it, the place as text that is a button", () => {
    const wrapper = make();
    const control = wrapper.find(".field-control");
    expect([...control.element.children].map((c) => c.tagName + "." + c.className.split(" ")[0])).toEqual(["BUTTON.btn", "BUTTON.location-place"]);
    expect(wrapper.find(".location-pick").classes()).not.toContain("primary");
    expect(wrapper.find(".location-place").attributes("type")).toBe("button");
    expect(wrapper.find(".location-place").text()).toBe("60.17 N, 24.94 E · KP20le");
  });

  it("says Cancel while the map waits, and asks for the pick with a click", async () => {
    const wrapper = make({ picking: true });
    expect(wrapper.find(".location-pick").text()).toBe("Cancel");
    expect(wrapper.find(".location-pick").attributes("aria-pressed")).toBe("true");
    await wrapper.find(".location-pick").trigger("click");
    expect(wrapper.emitted("pick")).toHaveLength(1);
  });

  it("opens the entry with a click or the keyboard on the place, tells a screen reader, and puts the cursor in the latitude", async () => {
    const wrapper = mount(LocationField, {
      props: { id: "loc", place: "60.17 N, 24.94 E · KP20le", picking: false, lat: "60.17", lon: "24.94" },
      attachTo: document.body,
    });
    const place = wrapper.find(".location-place");
    expect(place.attributes("aria-expanded")).toBe("false");
    expect(place.attributes("aria-controls")).toBe("loc-entry");
    expect(place.attributes("title")).toBe("Type coordinates or a locator");
    await place.trigger("click");
    expect(place.attributes("aria-expanded")).toBe("true");
    expect(wrapper.find("#loc-entry").attributes("aria-label")).toBe("Coordinates or locator");
    expect(document.activeElement).toBe(wrapper.find("#loc-lat").element);
    wrapper.unmount();
  });

  it("has the entry closed from the start, with or without a place, open when a coordinate is wrong, and open with no place only when asked (the guide)", async () => {
    expect(make().find(".location-entry").exists()).toBe(false);
    expect(make({ place: null, lat: "", lon: "" }).find(".location-entry").exists()).toBe(false);
    const empty = make({ place: null, lat: "", lon: "" });
    await empty.find(".location-place").trigger("click");
    expect(empty.find(".location-entry").exists()).toBe(true);
    expect(make({ place: null, lat: "", lon: "", openWhenEmpty: true }).find(".location-entry").exists()).toBe(true);
    expect(make({ openWhenEmpty: true }).find(".location-entry").exists()).toBe(false);
    expect(
      make({ errors: { lon: "Between -180 and 180" } })
        .find(".location-entry")
        .exists(),
    ).toBe(true);
    expect(make({ place: null, lat: "", lon: "" }).find(".location-place").text()).toBe("Not set");
  });

  it("follows the coordinates with the locator and the locator with the coordinates, 6 characters, the centre of the square", async () => {
    const wrapper = make({ place: null, lat: "", lon: "", openWhenEmpty: true });
    expect(wrapper.find<HTMLInputElement>("#loc-locator").element.value).toBe("");
    await wrapper.find("#loc-locator").setValue("kp20ie");
    expect(wrapper.emitted("update:lat")).toEqual([["60.1875"]]);
    expect(wrapper.emitted("update:lon")).toEqual([["24.7083"]]);
    await wrapper.setProps({ lat: "60.1875", lon: "24.7083", place: "x" });
    expect(wrapper.find<HTMLInputElement>("#loc-locator").element.value).toBe("kp20ie"); // (as typed, while it names the place)
    await wrapper.setProps({ lat: "61.5", lon: "25.5" });
    expect(wrapper.find<HTMLInputElement>("#loc-locator").element.value).toBe("KP21sm");
    await wrapper.find("#loc-locator").setValue("KP20");
    expect(wrapper.emitted("update:lat")?.at(-1)).toEqual(["60.5"]);
  });

  it("says a locator of 6 characters or more that is none, and nothing while it is still being typed", async () => {
    const wrapper = make({ place: null, lat: "", lon: "", openWhenEmpty: true });
    await wrapper.find("#loc-locator").setValue("KP20i");
    expect(wrapper.find(".field-error").exists()).toBe(false);
    await wrapper.find("#loc-locator").setValue("SS00aa");
    expect(wrapper.find(".field-error").text()).toBe("Not a locator");
    expect(wrapper.emitted("update:lat")).toBeUndefined();
  });

  it("applies as the form does when asked to: Enter and leaving a field commit, with the part, and Esc cancels a field that holds a change", async () => {
    const wrapper = make({ apply: true, changed: { lat: true } });
    await wrapper.find(".location-place").trigger("click");
    await wrapper.find("#loc-lat").trigger("keydown", { key: "Enter" });
    await wrapper.find("#loc-lon").trigger("blur");
    await wrapper.find("#loc-locator").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("commit")).toEqual([
      ["lat", null],
      ["lon", null],
      ["locator", null],
    ]);
    await wrapper.find("#loc-lat").trigger("keydown", { key: "Escape" });
    await wrapper.find("#loc-locator").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("cancel")).toEqual([["lat"], ["locator"]]);
  });

  it("does not commit or cancel when the form has its own button (Enter submits it)", async () => {
    const wrapper = make();
    await wrapper.find(".location-place").trigger("click");
    await wrapper.find("#loc-lat").trigger("keydown", { key: "Enter" });
    await wrapper.find("#loc-lat").trigger("blur");
    expect(wrapper.emitted("commit")).toBeUndefined();
  });

  it("wraps on a narrow panel: the place goes under the button and is never cut off, and the button is as wide as the other actions", () => {
    expect(cssRule(".location-control")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".location-control")).not.toMatch(/overflow:\s*hidden/);
    const place = cssRule(".location-place");
    expect(place).toMatch(/overflow-wrap:\s*anywhere/);
    expect(place).toMatch(/max-width:\s*100%/);
    expect(place).not.toMatch(/white-space:\s*nowrap/);
    expect(place).not.toMatch(/text-overflow/);
    expect(cssRule(".location-pick")).toContain("min-width: var(--action-w)");
    expect(cssRule(".location-control .location-pick")).toMatch(/flex:\s*none/);
  });

  it("looks like text with a hover, a keyboard focus ring and a finger-high box on a touch screen, and its entry is a row under the control", () => {
    expect(cssRule(".location-place")).toMatch(/cursor:\s*pointer/);
    expect(cssRule(".location-place:hover")).toContain("--row-hover");
    expect(cssRule(".location-place:focus-visible")).toMatch(/outline:\s*2px solid var\(--accent\)/);
    expect(mediaRule("(pointer: coarse)", ".location-place")).toContain("min-height: 40px");
    expect(cssRule(".location-entry")).toMatch(/grid-column:\s*2/);
  });
});

describe("the one Location control", () => {
  it("is the same component in the Beacon tab, the Objects form and the first-run guide", async () => {
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(fakeDaemon({ config: configValues() })) });
    const objects = mount(ObjectForm, {
      props: {
        form: useOwnObjects(new Map(), ref({ lat: 60.17, lon: 24.94 }), () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel),
        fallbackPath: "",
      },
    });
    const config = ref(configValues({ "station/lat": "60.17", "station/lon": "24.94" }));
    const guide = useSetupGuide(config, ref(null), ref(null), () => true);
    guide.show();
    guide.step = 1;
    const setup = mount(SetupGuide, { global: withDaemon(fakeDaemon({ config, guide })) });
    const shape = (wrapper: ReturnType<typeof mount>) => {
      const row = wrapper.find(".location-field");
      return {
        children: [...row.element.children].map((c) => c.className.split(" ")[0]),
        control: [...row.find(".field-control").element.children].map((c) => c.tagName + "." + c.className.split(" ")[0]),
        label: row.find(".field-label").text(),
        button: [row.find(".location-pick").text(), row.find(".location-pick").classes().includes("primary")],
        place: row.find(".location-place").text(),
      };
    };
    expect(shape(beacon)).toEqual(shape(objects));
    expect(shape(setup)).toEqual(shape(objects));
    for (const wrapper of [beacon, objects, setup]) {
      expect(wrapper.find(".location-pick").classes()).not.toContain("primary");
      await wrapper.find(".location-place").trigger("click");
      expect(wrapper.findAll(".location-entry label").map((l) => l.text())).toEqual(["Latitude", "Longitude", "Locator"]);
    }
  });
});
