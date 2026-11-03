import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { fakeDaemon, withDaemon } from "@/test/context";

function make(version = "0.9.1") {
  return mount(SettingsAbout, { global: withDaemon(fakeDaemon({ version })) });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("the About group", () => {
  it("says what NeoAPRS is with the daemon's version, who made it, and has no control", () => {
    const wrapper = make();
    expect(wrapper.find("legend").text()).toBe("About");
    expect(wrapper.findAll("p")[0]?.text()).toBe("NeoAPRS 0.9.1, an APRS client for your radio, on VHF and over HF. Made by OH2GBA, 2026.");
    expect(wrapper.findAll("button, input, select")).toHaveLength(0);
  });

  it("shows the version the daemon reports", () => {
    expect(make("1.2.3").text()).toContain("NeoAPRS 1.2.3,");
  });

  it("says the year the project began, 2026, whatever year it is now", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2031-06-01T12:00:00Z"));
    expect(make().findAll("p")[0]?.text()).toContain("Made by OH2GBA, 2026.");
  });

  it("has the licence and the source as links that open in a new tab", () => {
    const wrapper = make();
    expect(wrapper.text()).toContain("Free software under the GNU General Public License, version 3 or later.");
    const [license, source] = wrapper.findAll("a");
    expect(license?.text()).toBe("GNU General Public License");
    expect(license?.attributes("href")).toBe("https://www.gnu.org/licenses/gpl-3.0.html");
    expect(source?.text()).toBe("Source code");
    expect(source?.attributes("href")).toBe("https://github.com/oh2gba/neoaprs");
    expect(wrapper.findAll("a")).toHaveLength(5); // (the licence, the source, the modem, and the two of the feedback line)
    for (const link of [license, source]) {
      expect(link?.attributes("target")).toBe("_blank");
      expect(link?.attributes("rel")).toContain("noopener");
    }
  });

  it("names the HF modem, its name a link to its source that opens in a new tab", () => {
    const wrapper = make();
    const line = wrapper.findAll("p")[3];
    expect(line?.text()).toBe("The HF modem is Mercury by Rhizomatica.");
    const link = line?.get("a");
    expect(link?.text()).toBe("Mercury");
    expect(link?.attributes("href")).toBe("https://github.com/Rhizomatica/mercury");
    expect(link?.attributes("target")).toBe("_blank");
    expect(link?.attributes("rel")).toContain("noopener");
  });

  it("thanks everyone who tried it and sent feedback, and names no one", () => {
    const wrapper = make();
    expect(wrapper.get("p.muted").text()).toBe("Thanks to everyone who tried it and sent feedback.");
    expect(wrapper.text()).not.toMatch(/OH2GAX|OH2DPN|OH7NFC/);
    expect(wrapper.findAll(".mono")).toHaveLength(0);
  });
});

describe("the feedback line", () => {
  it("says GitHub issues (preferred) or the address, both links, under the thanks line, in one line", () => {
    const wrapper = make();
    const paragraphs = wrapper.findAll("p");
    const line = paragraphs[paragraphs.length - 1];
    expect(line?.text()).toBe("Feedback and ideas: GitHub issues (preferred) or neoaprs@oh2gba.eu.");
    const links = line?.findAll("a");
    expect(links?.map((a) => a.attributes("href"))).toEqual(["https://github.com/oh2gba/neoaprs/issues", "mailto:neoaprs@oh2gba.eu"]);
    expect(links?.[0]?.attributes("target")).toBe("_blank");
    expect(wrapper.get("p.muted").element.nextElementSibling).toBe(line?.element);
  });
});

describe("the About group in the Settings tab", () => {
  it("is the last group, after Help, and the My station tab has none", () => {
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

  it("has the nine ids of the group in English", () => {
    expect(ids).toHaveLength(9);
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

describe("the typography of the group in French and Italian", () => {
  const texts = (code: string): string[] => {
    const messages = LOCALES.find((l) => l.code === code)?.messages as Record<string, string>;
    return Object.keys(messages)
      .filter((id) => id.startsWith("settings.about."))
      .map((id) => messages[id]);
  };

  it("French has a no-break space before : ; ? ! and %, never a plain one", () => {
    for (const text of texts("fr")) expect(text).not.toMatch(/ [:;?!%]/);
    expect(texts("fr").join(" ")).toContain("Retours et idées\u00a0: ");
  });

  it("Italian writes its apostrophe curly", () => {
    for (const text of texts("it")) expect(text).not.toContain("'");
    expect(texts("it").join(" ")).toContain("l\u2019hanno");
  });
});
