import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { fakeDaemon, withDaemon } from "@/test/context";

function make(version = "0.9.1") {
  return mount(SettingsAbout, { global: withDaemon(fakeDaemon({ version })) });
}

describe("the About group", () => {
  it("says what NeoAPRS is with the daemon's version, who made it, and has no control", () => {
    const wrapper = make();
    expect(wrapper.find("legend").text()).toBe("About");
    expect(wrapper.findAll("p")[0]?.text()).toBe("NeoAPRS 0.9.1, an APRS client for your radio. Made by OH2GBA.");
    expect(wrapper.findAll("button, input, select")).toHaveLength(0);
  });

  it("shows the version the daemon reports", () => {
    expect(make("1.2.3").text()).toContain("NeoAPRS 1.2.3,");
  });

  it("has the licence and the source as links that open in a new tab", () => {
    const wrapper = make();
    expect(wrapper.text()).toContain("Free software under the GNU General Public License, version 3 or later.");
    const [license, source] = wrapper.findAll("a");
    expect(license?.text()).toBe("GNU General Public License");
    expect(license?.attributes("href")).toBe("https://www.gnu.org/licenses/gpl-3.0.html");
    expect(source?.text()).toBe("Source code");
    expect(source?.attributes("href")).toBe("https://github.com/oh2gba/neoaprs");
    expect(wrapper.findAll("a")).toHaveLength(2);
    for (const link of [license, source]) {
      expect(link?.attributes("target")).toBe("_blank");
      expect(link?.attributes("rel")).toContain("noopener");
    }
  });

  it("thanks the three calls, in the body font like the rest of the sentence: a call in running text is not monospace, whose selection box would look cut", () => {
    const wrapper = make();
    const thanks = wrapper.get("p.muted");
    expect(thanks.text()).toBe("Thanks to OH2GAX, OH2DPN and OH7NFC for their feedback.");
    expect(wrapper.findAll(".mono")).toHaveLength(0);
  });
});

describe("the About group in the Settings tab", () => {
  it("is the last group, after Help, and the Beacon tab has none", () => {
    const settings = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon() });
    const titles = settings.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(titles.slice(-2)).toEqual(["Help", "About"]);
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon() });
    expect(beacon.find(".about").exists()).toBe(false);
  });
});

describe("the words of the group in every language", () => {
  const english = en as Record<string, unknown>;
  const ids = Object.keys(english).filter((id) => id.startsWith("settings.about."));

  it("has the six ids of the group in English", () => {
    expect(ids).toHaveLength(6);
  });

  for (const locale of LOCALES.filter((l) => l.code !== "en")) {
    it(`${locale.name} has every one, translated, with the values and the places where English has them`, () => {
      const messages = locale.messages as Record<string, unknown>;
      for (const id of ids) {
        const text = String(messages[id]);
        const source = String(english[id]);
        expect(text, id).not.toBe("undefined");
        // the name of the licence is kept in German as it is written there
        if (!(locale.code === "de" && id === "settings.about.license_link")) expect(text, id).not.toBe(source);
        for (const name of source.match(/\{\w+\}/g) ?? []) expect(text, id).toContain(name);
      }
    });
  }
});
