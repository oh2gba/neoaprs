// A setting of tickboxes (`multi` of SettingsField, the ship types of the group Ships (AIS)): a tickbox for each choice, ticked by the value (the choices separated by commas), and a tick or an untick says the new value in
// the order of the choices.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsField from "@/components/SettingsField.vue";
import { FIELDS } from "@/lib/settings";

describe("a setting of tickboxes", () => {
  it("ticks the ship types of the value and says the new value in the order of the choices", async () => {
    const wrapper = mount(SettingsField, {
      props: { id: "set-ais-types", info: FIELDS["ais/types"], modelValue: "tanker,cargo", fallback: "", error: "", changed: false, apply: true },
    });
    const boxes = wrapper.findAll<HTMLInputElement>(".multi input[type=checkbox]");
    expect(wrapper.findAll(".multi label").map((l) => l.text())).toEqual([
      "Cargo ships",
      "Tankers",
      "Passenger ships",
      "High-speed craft",
      "Fishing vessels",
      "Sailing and pleasure craft",
      "Tugs, pilots, rescue and other special craft",
      "Other and unknown",
    ]);
    expect(boxes.map((b) => b.element.checked)).toEqual([true, true, false, false, false, false, false, false]);
    expect(wrapper.get(".multi").attributes("aria-labelledby")).toBe("set-ais-types-label");
    await boxes[2]?.setValue(true);
    await boxes[0]?.setValue(false);
    expect(wrapper.emitted("choose")).toEqual([["cargo,tanker,passenger"], ["tanker"]]);
  });
});
