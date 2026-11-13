import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import SkedCompose from "@/components/SkedCompose.vue";
import type { SkedsState } from "@/protocol/protocol";
import { configValues } from "@/test/fixtures";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { NOW, sked, skedsState } from "@/test/fixtures";

// The fixtures' time is Wednesday 21 October 2026, 12:00 UTC: the form opens on that day, from 12:00 to 13:00, on 7.0541 MHz USB.
let daemon: FakeDaemon;
beforeEach(() => (daemon = fakeDaemon({ skeds: skedsState() })));
const sent = (cmd: string) => daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === cmd);

function form(state: Partial<SkedsState> = {}) {
  daemon.skeds.value = skedsState([], state);
  return mount(SkedCompose, { global: withDaemon(daemon), attachTo: document.body });
}
const post = (wrapper: ReturnType<typeof form>) => wrapper.find("button[type='submit']");
const select = (wrapper: ReturnType<typeof form>, id: string) => wrapper.find<HTMLSelectElement>(`#${id}`);

describe("SkedCompose", () => {
  it("is a group box with the day, the time with its label saying UTC, the frequency and the note, and a button that says where it posts", () => {
    const wrapper = form();
    expect(wrapper.find("legend").text()).toBe("Post a sked");
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Day", "Time (UTC)", "Frequency", "Note"]);
    expect(post(wrapper).text()).toBe("Post on neo.oh2gba.eu");
    expect(wrapper.find("#sked-from").attributes("aria-label")).toBe("From");
    expect(wrapper.find("#sked-to").attributes("aria-label")).toBe("To");
  });

  it("is built of selects and one line for the note: no date or time field", () => {
    const wrapper = form();
    expect(wrapper.findAll("select")).toHaveLength(4);
    expect(wrapper.findAll("input")).toHaveLength(1);
    expect(wrapper.find("input[type='date'], input[type='time'], input[type='datetime-local']").exists()).toBe(false);
  });

  it("offers the next 30 UTC days, today first, written in the language of the page", () => {
    const wrapper = form();
    const options = select(wrapper, "sked-day").findAll("option");
    expect(options).toHaveLength(30);
    expect(options[0]?.text()).toBe("Wed 21 Oct");
    expect(options[0]?.element.value).toBe("2026-10-21");
    expect(options.at(-1)?.element.value).toBe("2026-11-19");
  });

  it("offers the half hours for From and To", () => {
    const wrapper = form();
    for (const id of ["sked-from", "sked-to"]) {
      const times = select(wrapper, id).findAll("option");
      expect(times).toHaveLength(48);
      expect(times[0]?.text()).toBe("00:00");
      expect(times[47]?.text()).toBe("23:30");
    }
  });

  it("opens on today, from the next half hour for an hour, on the first dial the project suggests, with Post on", () => {
    const wrapper = form();
    expect(select(wrapper, "sked-day").element.value).toBe("2026-10-21");
    expect(select(wrapper, "sked-from").element.value).toBe("12:00");
    expect(select(wrapper, "sked-to").element.value).toBe("13:00");
    expect(select(wrapper, "sked-frequency").element.value).toBe("7.0541 MHz USB");
    expect(post(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("offers the suggested frequencies with their bands, and Other", () => {
    const options = select(form(), "sked-frequency").findAll("option");
    expect(options.map((o) => o.text())).toEqual(["7.0541 MHz USB (40 m)", "14.1070 MHz USB (20 m)", "50.6200 MHz USB (6 m)", "Other"]);
  });

  it("posts what is chosen with one command, and never the call", async () => {
    const wrapper = form();
    await select(wrapper, "sked-day").setValue("2026-10-24");
    await select(wrapper, "sked-from").setValue("18:00");
    await select(wrapper, "sked-to").setValue("20:30");
    await select(wrapper, "sked-frequency").setValue("14.1070 MHz USB");
    await wrapper.find("#sked-note").setValue("  Mercury, 10 W ");
    await wrapper.find("form").trigger("submit");
    expect(sent("sked_post")).toEqual([
      { cmd: "sked_post", from: "2026-10-24T18:00:00Z", to: "2026-10-24T20:30:00Z", dial: "14.1070 MHz USB", note: "Mercury, 10 W" },
    ]);
    expect(Object.keys(sent("sked_post")[0] ?? {})).not.toContain("call");
  });

  it("takes a To that is not after From as the next day", async () => {
    const wrapper = form();
    await select(wrapper, "sked-from").setValue("22:00");
    await select(wrapper, "sked-to").setValue("02:00");
    await wrapper.find("form").trigger("submit");
    expect(sent("sked_post")).toMatchObject([{ from: "2026-10-21T22:00:00Z", to: "2026-10-22T02:00:00Z" }]);
  });

  it("marks the To and turns Post off for a sked that has ended, and has it on for one that runs", async () => {
    const wrapper = form();
    await select(wrapper, "sked-from").setValue("08:00");
    await select(wrapper, "sked-to").setValue("10:00");
    expect(select(wrapper, "sked-to").classes()).toContain("invalid");
    expect(select(wrapper, "sked-from").classes()).not.toContain("invalid");
    expect(post(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.find("form").trigger("submit");
    expect(sent("sked_post")).toEqual([]);
    await select(wrapper, "sked-to").setValue("13:00");
    expect(select(wrapper, "sked-to").classes()).not.toContain("invalid");
    expect(post(wrapper).attributes("disabled")).toBeUndefined();
  });

  describe("the frequency", () => {
    it("brings a row to type one with Other, in the form of the page, and takes it back with a dial of the list", async () => {
      const wrapper = form();
      expect(wrapper.find("#sked-dial").exists()).toBe(false);
      await select(wrapper, "sked-frequency").setValue("other");
      expect(wrapper.find("#sked-dial").exists()).toBe(true);
      expect(wrapper.find<HTMLInputElement>("#sked-dial").attributes("placeholder")).toBe("7.0541 MHz USB");
      expect(post(wrapper).attributes("disabled")).toBeDefined(); // (nothing typed yet)
      expect(wrapper.find("#sked-dial").classes()).not.toContain("invalid");
      await select(wrapper, "sked-frequency").setValue("14.1070 MHz USB");
      expect(wrapper.find("#sked-dial").exists()).toBe(false);
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
    });

    it("posts a typed dial in the form of the board, and marks one that is not of the form and keeps Post off", async () => {
      const wrapper = form();
      await select(wrapper, "sked-frequency").setValue("other");
      await wrapper.find("#sked-dial").setValue("7.1");
      expect(wrapper.find("#sked-dial").classes()).toContain("invalid");
      expect(post(wrapper).attributes("disabled")).toBeDefined();
      await wrapper.find("#sked-dial").setValue("3.6150 mhz lsb");
      expect(wrapper.find("#sked-dial").classes()).not.toContain("invalid");
      await wrapper.find("form").trigger("submit");
      expect(sent("sked_post")).toMatchObject([{ dial: "3.6150 MHz LSB" }]);
    });

    it("types the dial where the project suggests none", async () => {
      const wrapper = form({ frequencies: [] });
      expect(wrapper.find("#sked-dial").exists()).toBe(true);
      expect(
        select(wrapper, "sked-frequency")
          .findAll("option")
          .map((o) => o.text()),
      ).toEqual(["Other"]);
      await wrapper.find("#sked-dial").setValue("7.0541 MHz USB");
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
    });

    it("keeps Other where it was chosen when the board is told again", async () => {
      const wrapper = form();
      await select(wrapper, "sked-frequency").setValue("other");
      await tell(daemon, { skeds: skedsState([sked("a")]) });
      expect(select(wrapper, "sked-frequency").element.value).toBe("other");
      expect(wrapper.find("#sked-dial").exists()).toBe(true);
    });

    it("starts on the first dial when the list arrives after the form is made", async () => {
      daemon.skeds.value = null;
      const wrapper = mount(SkedCompose, { global: withDaemon(daemon) });
      expect(post(wrapper).attributes("disabled")).toBeDefined();
      await tell(daemon, { skeds: skedsState() });
      expect(select(wrapper, "sked-frequency").element.value).toBe("7.0541 MHz USB");
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
    });
  });

  describe("the note", () => {
    it("counts the characters it has left, in red when it is too long, and Post is off then", async () => {
      const wrapper = form();
      expect(wrapper.find(".compose-left").text()).toBe("80 left");
      await wrapper.find("#sked-note").setValue("Mercury, 10 W");
      expect(wrapper.find(".compose-left").text()).toBe("67 left");
      await wrapper.find("#sked-note").setValue("x".repeat(81));
      expect(wrapper.find(".compose-left").text()).toBe("1 over");
      expect(wrapper.find(".compose-left").classes()).toContain("over");
      expect(post(wrapper).attributes("disabled")).toBeDefined();
      await wrapper.find("#sked-note").setValue("x".repeat(80));
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
    });

    it("may be empty", async () => {
      const wrapper = form();
      await wrapper.find("form").trigger("submit");
      expect(sent("sked_post")).toMatchObject([{ note: "" }]);
    });

    it("is cleared when the daemon has the sked, and stays when it has not", async () => {
      const wrapper = form();
      await wrapper.find("#sked-note").setValue("Mercury");
      await wrapper.find("form").trigger("submit");
      const [command] = sent("sked_post") as { from: string; to: string; dial: string }[];
      await tell(daemon, { skeds: skedsState([sked("x", { ours: false, from: command?.from, to: command?.to, dial: command?.dial })]) });
      expect(wrapper.find<HTMLInputElement>("#sked-note").element.value).toBe("Mercury"); // (somebody else's sked of the same times is not ours)
      await tell(daemon, { skeds: skedsState([sked("y", { ours: true, from: command?.from, to: command?.to, dial: command?.dial })]) });
      expect(wrapper.find<HTMLInputElement>("#sked-note").element.value).toBe("");
    });

    it("is kept when it was changed after Post was pressed", async () => {
      const wrapper = form();
      await wrapper.find("#sked-note").setValue("Mercury");
      await wrapper.find("form").trigger("submit");
      await wrapper.find("#sked-note").setValue("something else");
      const [command] = sent("sked_post") as { from: string; to: string; dial: string }[];
      await tell(daemon, { skeds: skedsState([sked("y", { ours: true, from: command?.from, to: command?.to, dial: command?.dial })]) });
      expect(wrapper.find<HTMLInputElement>("#sked-note").element.value).toBe("something else");
    });
  });

  describe("when Post is off", () => {
    it("is off while there is no call, or a placeholder, and on with one", async () => {
      const wrapper = form();
      await tell(daemon, { call: null });
      expect(post(wrapper).attributes("disabled")).toBeDefined();
      await tell(daemon, { call: "N0CALL" });
      expect(post(wrapper).attributes("disabled")).toBeDefined();
      await tell(daemon, { call: "OH2GBA" });
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
    });

    it("is off while the board cannot be reached or the check is off, and says nothing about it", () => {
      for (const state of ["offline", "off"] as const) {
        const wrapper = form({ state });
        expect(post(wrapper).attributes("disabled"), state).toBeDefined();
        expect(post(wrapper).attributes("title")).toBeUndefined();
        expect(wrapper.text()).not.toMatch(/offline|reach|error/i);
      }
    });

    it("is not off for RX only: nothing here is sent by radio", async () => {
      const wrapper = form();
      await tell(daemon, { config: configValues({ "station/transmit": "false" }) });
      expect(post(wrapper).attributes("disabled")).toBeUndefined();
      expect(post(wrapper).attributes("title")).toBeUndefined();
      await wrapper.find("form").trigger("submit");
      expect(sent("sked_post")).toHaveLength(1);
    });
  });

  it("carries the room of nothing: no hint, range or reason line in the form", () => {
    const wrapper = form();
    expect(wrapper.find(".field-hint, .field-error, .infotip").exists()).toBe(false);
  });

  it("goes on with a day that is one of the choices as the UTC day turns", async () => {
    const wrapper = form();
    await select(wrapper, "sked-day").setValue("2026-10-21");
    await tell(daemon, { now: NOW + 13 * 3_600_000 }); // (Thursday 22 October 01:00 UTC: the list starts a day later)
    expect(select(wrapper, "sked-day").element.value).toBe("2026-10-22");
    expect(select(wrapper, "sked-day").findAll("option")[0]?.element.value).toBe("2026-10-22");
  });
});
