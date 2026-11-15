// A radio of a type that only listens (`tnc-text`) on the page of a station that has senders beside it: it is in none of the lists of the radios to send on (the main radio, Send on, the radio beside Ask), its box has
// no Find my radio, no path and no "find automatically" for its port, and while it is the only radio that is on, the beacon's fields are greyed as with RX only ticked.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import BeaconPane from "@/components/BeaconPane.vue";
import ConversationView from "@/components/ConversationView.vue";
import NearbyAsk from "@/components/NearbyAsk.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import StationPanel from "@/components/StationPanel.vue";
import type { RadioRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { radioRow, radiosTopic, station, status } from "@/test/fixtures";

afterEach(() => document.body.replaceChildren());

const TEXT = radioRow(1, "tnc-text", { name: "FTM" });
const DUMMY = radioRow(3, "dummy", { name: "Dummy", number: 2 });
const KISS = radioRow(4, "kiss", { name: "Mobile", number: 3 });

const daemonOf = (...rows: RadioRow[]) =>
  fakeDaemon({ radios: radiosTopic(...rows), status: status({ main_radio: rows.find((row) => row.type !== "tnc-text")?.id ?? 1 }) });
const settings = (...rows: RadioRow[]) => mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemonOf(...rows)), attachTo: document.body });
const mainChoices = (wrapper: ReturnType<typeof settings>) => wrapper.findAll("#set-station-main_radio option").map((option) => option.text());

describe("a radio that only listens beside radios that send", () => {
  it("is no main radio: with one sender beside it there is none to choose, with two the choice is of those two", () => {
    expect(settings(TEXT, DUMMY).find("#set-station-main_radio").exists()).toBe(false);
    expect(mainChoices(settings(TEXT, DUMMY, KISS))).toEqual(["Dummy", "Mobile"]);
  });

  it("has a box with its port and its speed alone: no Find my radio, no path, and no port found automatically", () => {
    const wrapper = settings(TEXT, DUMMY);
    expect(wrapper.find("#set-radio-1-find").exists()).toBe(false);
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(daemonOf(TEXT, DUMMY, KISS)), attachTo: document.body });
    expect([beacon.find("#set-radio-1-path").exists(), beacon.find("#set-radio-3-path").exists()]).toEqual([false, true]); // (a Path row for each radio on that may carry one: not the text radio)
    expect(wrapper.find("#set-radio-1-digipeat").exists()).toBe(false);
    expect(wrapper.find("#set-radio-1-port").exists()).toBe(true);
    expect(wrapper.findAll("#set-radio-1-port option").map((option) => option.text())[0]).toBe("not set");
  });

  it("is no tick of Send on and no choice beside Ask", () => {
    const pane = (...rows: RadioRow[]) => mount(BeaconPane, { global: withDaemon(daemonOf(...rows)) });
    const ticks = (wrapper: ReturnType<typeof pane>) => wrapper.findAll("#beacon-send-on ~ .field-control label.check").map((label) => label.text());
    expect(pane(TEXT, DUMMY).find("#beacon-send-on").exists()).toBe(false);
    expect(ticks(pane(TEXT, DUMMY, KISS))).toEqual(["Dummy", "Mobile"]);
    const ask = (...rows: RadioRow[]) => mount(NearbyAsk, { global: withDaemon(daemonOf(...rows)) });
    expect(ask(TEXT, DUMMY).find("select.ask-radio").exists()).toBe(false);
    expect(
      ask(TEXT, DUMMY, KISS)
        .findAll("select.ask-radio option")
        .map((option) => option.text()),
    ).not.toContain("FTM");
  });

  it("alone greys the beacon's fields as RX only does", () => {
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(daemonOf(TEXT)), attachTo: document.body });
    expect(beacon.find<HTMLInputElement>("#set-station-comment").element.disabled).toBe(true);
    const sending = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(daemonOf(TEXT, DUMMY)), attachTo: document.body });
    expect(sending.find<HTMLInputElement>("#set-station-comment").element.disabled).toBe(false);
  });

  it("is no radio Route offers for a station's messages, in the conversation and in the station panel", async () => {
    const heard = station("OH2ABC-7", { radio_now: 3 });
    const routeRadios = async (...rows: RadioRow[]) => {
      const given = {
        radios: radiosTopic(...rows),
        status: status({ main_radio: 3 }),
        stations: shallowRef(new Map([[heard.call, heard]])),
        fallbackPath: "WIDE1-1,WIDE2-1",
      };
      const convo = mount(ConversationView, {
        props: { selected: heard.call, narrow: false, thread: [] },
        global: withDaemon(fakeDaemon(given)),
        attachTo: document.body,
      });
      await convo.find(".route-button").trigger("click");
      const box = mount(StationPanel, { props: { row: heard, armed: false }, global: withDaemon(fakeDaemon(given)), attachTo: document.body });
      return [convo, box].map((wrapper) => wrapper.findAll(".route-radio-pick option").map((option) => option.text()));
    };
    expect(await routeRadios(TEXT, DUMMY)).toEqual([[], []]); // (one radio sends: there is none to choose)
    for (const offered of await routeRadios(TEXT, DUMMY, KISS)) {
      expect(offered).toContain("Mobile");
      expect(offered).not.toContain("FTM");
    }
  });
});

describe("the words of the boxes of the new types", () => {
  const BOARD = radioRow(5, "lora-tcp", { name: "Board", number: 1 });
  const tip = async (wrapper: ReturnType<typeof settings>, id: string): Promise<string> => {
    const toggle = wrapper.find(`#${id}`).element.closest(".field")?.querySelector<HTMLButtonElement>(".info-toggle");
    expect(toggle, id).toBeTruthy();
    toggle?.click();
    await wrapper.vm.$nextTick();
    const text = wrapper.find(".info-text").text();
    toggle?.click();
    await wrapper.vm.$nextTick();
    return text;
  };

  it("say of a LoRa board's address and port what is true of a board on the network: no default, no Direwolf, and an (i) on its Enable", async () => {
    const wrapper = settings(TEXT, DUMMY, BOARD);
    const host = wrapper.find<HTMLInputElement>("#set-radio-5-tcp_host");
    expect(host.attributes("placeholder")).toBe("");
    const words = [await tip(wrapper, "set-radio-5-tcp_host"), await tip(wrapper, "set-radio-5-tcp_port")].join(" ");
    expect(words).toContain("address of the board on your network");
    expect(words).not.toMatch(/127\.0\.0\.1|Direwolf|soundmodem/);
    expect(wrapper.find("#set-radio-5-tcp_port").element.closest(".field")?.innerHTML ?? "").not.toMatch(/Direwolf|soundmodem/);
    expect(await tip(wrapper, "set-radio-5-enabled")).toContain("LoRa APRS board");
  });

  it("say on the Enable of a radio that only listens that nothing is sent on it, and nothing of a beacon, paths or digipeaters", async () => {
    const text = await tip(settings(TEXT, DUMMY), "set-radio-1-enabled");
    expect(text).toContain("nothing is ever sent on it");
    expect(text).not.toMatch(/digipeater|beacon|path/i);
  });
});
