import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import InfoTip from "@/components/InfoTip.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { fakeDaemon, withDaemon } from "@/test/context";

function make(over = {}) {
  return mount(SettingsHelp, { global: withDaemon(fakeDaemon({ call: "OH2GBA", version: "0.9.0", ...over })) });
}

describe("the Help group", () => {
  it("is one line, the one primary button Send feedback / logs with its (i), and nothing else", () => {
    const wrapper = make();
    expect(wrapper.find("legend").text()).toBe("Help");
    expect(wrapper.get("p").text()).toBe("Feedback, an idea or a problem? This is the fastest way to reach the developer.");
    expect(wrapper.findAll("a")).toHaveLength(0);
    const buttons = wrapper.findAll("button.btn");
    expect(buttons.map((b) => b.text())).toEqual(["Send feedback / logs"]);
    expect(buttons[0]?.attributes("id")).toBe("set-help-send");
    expect(buttons[0]?.classes()).toEqual(["btn", "primary"]);
    expect(buttons[0]?.attributes("disabled")).toBeUndefined();
    expect(wrapper.find("#set-help-logs").exists()).toBe(false);
    expect(wrapper.getComponent(InfoTip).props("label")).toBe("About the logs");
    expect(wrapper.findAll("p")).toHaveLength(1);
    expect(wrapper.find(".help-result").text()).toBe("");
  });

  it("tells in the (i) what the file holds", async () => {
    const wrapper = make();
    await wrapper.get(".infotip button").trigger("click");
    expect(wrapper.findAll(".info-line").map((line) => line.text())).toEqual([
      "The log, the settings without the access key, the packets heard and sent. They can be saved as a file or sent to the project.",
      "NeoAPRS sends nothing by itself.",
    ]);
  });
});

describe("the Help group in the Settings tab", () => {
  it("is the group before About, after Update check, and the My station tab has none", () => {
    const settings = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon() });
    const titles = settings.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(titles.slice(-3)).toEqual(["Update check", "Help", "About"]);
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon() });
    expect(beacon.find(".help-logs").exists()).toBe(false);
  });
});

describe("the words of the group in every language", () => {
  const english = en as Record<string, unknown>;
  const ids = Object.keys(english).filter((id) => id.startsWith("settings.help."));

  it("has the ids of the group in English", () => {
    expect(ids.length).toBeGreaterThanOrEqual(15);
    for (const gone of ["contents", "contents_link", "write"]) expect(ids).not.toContain(`settings.help.${gone}`);
  });

  for (const locale of LOCALES.filter((l) => l.code !== "en")) {
    it(`${locale.name} has every one, translated, with the address and the file where English has them`, () => {
      const messages = locale.messages as Record<string, unknown>;
      for (const id of ids) {
        const text = String(messages[id]);
        const source = String(english[id]);
        expect(text, id).not.toBe("undefined");
        // the word is borrowed as it is in German, Italian, Dutch and Portuguese; Dutch says "Help" too
        const borrowed =
          (id === "settings.help.label" && ["de", "it", "nl", "pt-BR"].includes(locale.code)) || (id === "settings.help.group" && locale.code === "nl");
        if (!borrowed) expect(text, id).not.toBe(source);
        for (const name of source.match(/\{\w+\}/g) ?? []) expect(text, id).toContain(name);
      }
    });
  }
});
