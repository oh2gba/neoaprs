// The call with its SSID in a dropdown beside it (CallInput), in the Beacon tab and in the setup guide: the call is the letters and digits, the stored setting stays `OH2GBA-9`.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";
import { ssidChoices } from "@/lib/settingchoices";
import { setLocale } from "@/i18n";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues } from "@/test/fixtures";

function beacon(call = "OH2GBA") {
  const daemon = fakeDaemon({ config: configValues({ "station/call": call }) });
  const wrapper = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(daemon), attachTo: document.body });
  const field = () => wrapper.find<HTMLInputElement>("#set-station-call");
  const ssid = () => wrapper.find<HTMLSelectElement>("#set-station-call-ssid");
  return { wrapper, send: daemon.send, field, ssid };
}

describe("the call field of the Beacon tab", () => {
  it("shows the stored call apart: the call in the field and its SSID in the dropdown beside it, in the same row", () => {
    const { field, ssid } = beacon("OH2GBA-9");
    expect(field().element.value).toBe("OH2GBA");
    expect(ssid().element.value).toBe("9");
    expect(ssid().element.closest(".field-control")).toBe(field().element.closest(".field-control"));
    expect(ssid().attributes("aria-label")).toBe("SSID");
  });

  it("sends nothing when the tab is only opened: a stored call of an earlier version stays as it is (no rewrite on load)", async () => {
    for (const call of ["OH2GBA", "OH2GBA-9", "OH2GBA-15"]) {
      const { send, wrapper } = beacon(call);
      await wrapper.vm.$nextTick();
      expect(send, call).not.toHaveBeenCalled();
    }
  });

  it("shows none for a call without an SSID, and for -0", () => {
    expect(beacon("OH2GBA").ssid().element.value).toBe("");
    expect(beacon("OH2GBA-0").ssid().element.value).toBe("");
  });

  it("offers none and 1 to 15, with words that begin with the number, the value being the number", () => {
    const { ssid } = beacon();
    const options = ssid().findAll("option");
    expect(options.map((o) => o.element.value)).toEqual(["", ...Array.from({ length: 15 }, (_, i) => String(i + 1))]);
    expect(options[0]?.text()).toBe("none · main station");
    expect(options[9]?.text()).toBe("-9 · car");
    expect(options[10]?.text()).toBe("-10 · internet, iGate");
    for (const [i, option] of options.entries()) if (i > 0) expect(option.text().startsWith(`-${i} · `), option.text()).toBe(true);
  });

  it("sends the call and the SSID joined, at once, when an SSID is chosen", async () => {
    const { ssid, send } = beacon();
    await ssid().setValue("9");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/call": "OH2GBA-9" } });
  });

  it("sends the call alone when none is chosen again", async () => {
    const { ssid, send } = beacon("OH2GBA-9");
    await ssid().setValue("");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/call": "OH2GBA" } });
  });

  it("sends the typed call with the SSID it has, when the field is left", async () => {
    const { field, send } = beacon("OH2GBA-9");
    await field().setValue("oh2rdg");
    expect(field().element.value).toBe("OH2RDG");
    expect(send).not.toHaveBeenCalled();
    await field().trigger("blur");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/call": "OH2RDG-9" } });
  });

  it("moves an SSID that is typed or pasted with the call into the dropdown, instead of refusing it", async () => {
    const { field, ssid, send } = beacon();
    await field().setValue("oh2gba-9");
    expect(ssid().element.value).toBe("9");
    await field().trigger("blur");
    expect(field().element.value).toBe("OH2GBA");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/call": "OH2GBA-9" } });
  });

  it("takes a pasted call with its SSID apart at once", async () => {
    const { field, ssid } = beacon();
    const input = field().element;
    input.value = "oh2gba-10";
    await field().trigger("input", { inputType: "insertFromPaste" });
    expect(input.value).toBe("OH2GBA");
    expect(ssid().element.value).toBe("10");
  });

  it("lets a dash and its number be typed one key after the other", async () => {
    const { field, ssid } = beacon();
    await field().setValue("OH2GBA-");
    expect(field().element.value).toBe("OH2GBA-");
    await field().setValue("OH2GBA-1");
    expect(ssid().element.value).toBe("1");
    await field().setValue("OH2GBA-15");
    expect(ssid().element.value).toBe("15");
    expect(field().element.value).toBe("OH2GBA-15");
    await field().trigger("blur");
    expect(field().element.value).toBe("OH2GBA");
    expect(ssid().element.value).toBe("15");
  });

  it("accepts nothing but letters and digits otherwise: a dash that leads nowhere goes when the field is left", async () => {
    const { field, ssid, send } = beacon();
    await field().setValue("oh2 gba!");
    expect(field().element.value).toBe("OH2GBA");
    await field().setValue("OH2GBA-16");
    expect(ssid().element.value).toBe("");
    await field().trigger("blur");
    expect(field().element.value).toBe("OH2GBA");
    expect(send).not.toHaveBeenCalled(); // (nothing differs from what the daemon has)
  });

  it("shows the page's reason under the field when what is left is no call, and sends nothing", async () => {
    const { wrapper, field, send } = beacon();
    await field().setValue("AB");
    await field().trigger("blur");
    expect(send).not.toHaveBeenCalled();
    expect(wrapper.find(".field-error").text()).toBe("Not a call");
  });

  it("does not send an empty call when an SSID is chosen while the field is empty", async () => {
    const { field, ssid, send } = beacon();
    await field().setValue("");
    await ssid().setValue("7");
    expect(send).not.toHaveBeenCalled();
    expect(ssid().element.value).toBe("7");
    await field().setValue("oh2gba");
    await field().trigger("blur");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/call": "OH2GBA-7" } });
  });

  it("has one (i) for the row, with the SSID said in it and the picture of the SSID", async () => {
    const { wrapper, field } = beacon();
    const row = field().element.closest(".field");
    expect(row?.querySelectorAll(".infotip")).toHaveLength(1);
    wrapper.find<HTMLButtonElement>("#set-station-call").element.closest(".field")?.querySelector<HTMLButtonElement>(".info-toggle")?.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").text()).toContain("Several stations under one call; the number tells others what kind of station it is.");
    expect(wrapper.find(".info-text svg").exists()).toBe(true);
  });
});

describe("the SSID choices", () => {
  const labelIds = Array.from({ length: 16 }, (_, n) => `settings.ssid.s${n}`);

  for (const locale of LOCALES) {
    it(`have their 16 words and the (i) line in ${locale.name}, each with its number and none the same`, () => {
      const messages = locale.messages as Record<string, Message>;
      const labels = labelIds.map((id) => texts(messages[id] ?? "")[0] ?? "");
      expect(labels.every((label) => label.trim() !== "")).toBe(true);
      labels.slice(1).forEach((label, i) => expect(label.startsWith(`-${i + 1} · `), label).toBe(true));
      expect(new Set(labels.slice(0, 1).concat(labels.slice(5, 15))).size).toBe(11); // (the others of -1 to -4 and -15 are one thing)
      expect(texts(messages["settings.ssid.label"] ?? "")).toEqual(["SSID"]);
      expect(texts(messages["settings.call.tip2"] ?? "")[0]).not.toMatch(/-9|-10/); // (the line of the (i) says what the SSID is; the dropdown has the numbers)
    });

    it(`are the dropdown's options in ${locale.name}`, () => {
      setLocale(locale.code);
      try {
        const messages = locale.messages as Record<string, Message>;
        expect(ssidChoices().map((c) => c.label)).toEqual(labelIds.map((id) => texts(messages[id] ?? "")[0]));
      } finally {
        setLocale("en");
      }
    });
  }
});
