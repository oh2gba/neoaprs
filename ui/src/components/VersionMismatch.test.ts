import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import VersionMismatch from "@/components/VersionMismatch.vue";
import { LOCALES } from "@/i18n/locales";
import { setLocale } from "@/i18n";

const mismatch = { page: "index-AAAA.js/12", neoaprs: "0.9.2, index-BBBB.js/12" };

describe("VersionMismatch", () => {
  it("says what does not match, and what to do, in plain words with a Reload button", () => {
    const wrapper = mount(VersionMismatch, { props: { mismatch } });
    expect(wrapper.find("p").text()).toBe(
      "This page and NeoAPRS do not match (page index-AAAA.js/12, NeoAPRS 0.9.2, index-BBBB.js/12). Reload the page; if this stays, restart NeoAPRS.",
    );
    expect(wrapper.find("button").text()).toBe("Reload");
    expect(wrapper.attributes("role")).toBe("alert");
  });

  it("loads the page again when the button is pressed", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    await mount(VersionMismatch, { props: { mismatch } }).find("button").trigger("click");
    expect(reload).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it.each(LOCALES.map((l) => [l.code]))("is worded in %s with both values in it", (code) => {
    setLocale(code ?? "en");
    const wrapper = mount(VersionMismatch, { props: { mismatch } });
    expect(wrapper.find("p").text()).toContain("index-AAAA.js/12");
    expect(wrapper.find("p").text()).toContain("0.9.2, index-BBBB.js/12");
    expect(wrapper.find("button").text().length).toBeGreaterThan(0);
  });
});
