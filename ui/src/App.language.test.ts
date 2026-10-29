import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { locale } from "@/i18n";
import { open, useAppHarness } from "@/test/app";

useAppHarness();

describe("the language of the page", () => {
  it("is chosen at the top of the Settings tab, with every language by its own name, and the page is drawn again in it", async () => {
    localStorage.setItem("NeoAPRS.tab", "settings");
    const { wrapper } = await open();
    const field = wrapper.find("#language");
    expect(wrapper.find("label[for='language']").text()).toBe("Language");
    expect(wrapper.find("#pane-settings form").element.firstElementChild).toBe(field.element.closest(".field"));
    expect(wrapper.findAll("#language option").map((o) => o.text())).toEqual(expect.arrayContaining(["English"]));
    expect((field.element as HTMLSelectElement).value).toBe("en");
    expect(wrapper.find("#tab-stations").text()).toBe("Stations");

    await field.setValue("en-XA");
    await flushPromises();
    expect(locale.value).toBe("en-XA");
    expect(document.documentElement.lang).toBe("en-XA");
    expect(localStorage.getItem("NeoAPRS.language")).toBe("en-XA");
    expect(wrapper.find("#tab-stations").text()).toMatch(/^\[!! .* !!\]$/);
    expect(wrapper.find("label[for='language']").text()).toMatch(/^\[!! .* !!\]$/);
  });

  it("is not on the My station tab, which shows the settings of the beacon only", async () => {
    localStorage.setItem("NeoAPRS.tab", "beacon");
    const { wrapper } = await open();
    expect(wrapper.find("#pane-beacon #language").exists()).toBe(false);
  });
});
