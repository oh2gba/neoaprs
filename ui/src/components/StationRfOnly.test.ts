import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationRfOnly from "@/components/StationRfOnly.vue";
import { LOCALES } from "@/i18n/locales";

function box(on: string[] = [], call = "OH2RDG") {
  return mount(StationRfOnly, { props: { call, rfOnly: new Set(on) } });
}

describe("StationRfOnly", () => {
  it("is a tickbox called Radio only, with no hover title and no text under it", () => {
    const wrapper = box();
    expect(wrapper.find("label").text()).toBe("Radio only");
    expect(wrapper.find("label").attributes("title")).toBeUndefined();
    expect(wrapper.find("input").attributes("title")).toBeUndefined();
    expect(wrapper.find<HTMLInputElement>("input").attributes("type")).toBe("checkbox");
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".hint").exists()).toBe(false);
  });

  it("names the radio in every language, never RF, and has no words left for a hover title", () => {
    const wrong = LOCALES.flatMap(({ code, messages }) =>
      [messages["route.rf_only"], messages["settings.igate.show_gated_label"]].flatMap((words) =>
        typeof words === "string" && /RF/.test(words) ? [`${code}: ${words}`] : [],
      ),
    );
    expect(wrong).toEqual([]);
    expect(LOCALES.filter(({ messages }) => "route.rf_only_title" in messages).map(({ code }) => code)).toEqual([]);
  });

  it("is ticked for a station that is RF only and not for another", () => {
    expect(box(["OH2RDG"]).find<HTMLInputElement>("input").element.checked).toBe(true);
    expect(box(["OH2XYZ"]).find<HTMLInputElement>("input").element.checked).toBe(false);
  });

  it("saves the choice when it is ticked and when it is cleared", async () => {
    const wrapper = box();
    await wrapper.find("input").setValue(true);
    await wrapper.find("input").setValue(false);
    expect(wrapper.emitted("set")).toEqual([
      ["OH2RDG", true],
      ["OH2RDG", false],
    ]);
  });

  it("follows the daemon", async () => {
    const wrapper = box();
    await wrapper.setProps({ rfOnly: new Set(["OH2RDG"]) });
    expect(wrapper.find<HTMLInputElement>("input").element.checked).toBe(true);
  });

  it("is not there for the email gateway, which is on the internet", () => {
    expect(box([], "EMAIL-2").find("input").exists()).toBe(false);
    expect(box([], "email-2").find("input").exists()).toBe(false);
  });
});
