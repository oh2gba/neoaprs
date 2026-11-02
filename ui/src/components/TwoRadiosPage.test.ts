// The places of the page where the two radios show beyond the Radio group: the HF tag of a conversation, the mark of an attempt over HF and the tag under a message that came over HF, the email gateway with the FM radio off, the channel tags FM and HF
// of the Stations table and the Packets tab while the HF radio is on (and RF as it always was while it is off), and the two boxes of the setup guide.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick, ref, shallowRef } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import ConversationView from "@/components/ConversationView.vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailPane from "@/components/EmailPane.vue";
import MessageChain from "@/components/MessageChain.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import StationsTable from "@/components/StationsTable.vue";
import type { Toast } from "@/composables/useDaemon";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { chainOf } from "@/lib/chain";
import type { Command, ConfigValues, PortsMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { ago, configValues, incoming, message, packet, station, table } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
afterEach(() => document.body.replaceChildren());

const BOTH = { "hf/enabled": "true" };
const FM_OFF = { "fm/enabled": "false", "hf/enabled": "true" };
const heardOnHf = station("OH2HF", { heard_rf: 3, heard_fm: 0, heard_hf: 3 });
const heardOnFm = station("OH2FM", { heard_fm: 3 });

describe("the conversation header", () => {
  const header = (values: Record<string, string>, call: string) => {
    const daemon = fakeDaemon({ config: configValues(values), stations: shallowRef(new Map([heardOnHf, heardOnFm].map((row) => [row.call, row]))) });
    return mount(ConversationView, { props: { selected: call, narrow: false, thread: [] }, global: withDaemon(daemon) });
  };
  const tag = (wrapper: ReturnType<typeof header>) => wrapper.find(".convo-head .convo-radio");

  it("has the neutral tag HF in the place of Route for a station heard on the HF radio alone, with the title that says where its messages go", () => {
    const wrapper = header(BOTH, "OH2HF");
    expect(tag(wrapper).text()).toBe("HF");
    expect(tag(wrapper).classes()).toContain("tag-neutral");
    expect(tag(wrapper).attributes("title")).toBe("Messages to this station go over the HF radio: direct, no path");
    expect(wrapper.findAll("button").some((b) => b.text() === "Route")).toBe(false);
  });

  it("has Route and no tag for a station heard on FM, on both or never, as it is today", () => {
    for (const call of ["OH2FM", "OH2NEW"]) {
      const wrapper = header(BOTH, call);
      expect(tag(wrapper).exists(), call).toBe(false);
      expect(
        wrapper.findAll("button").some((b) => b.text() === "Route"),
        call,
      ).toBe(true);
    }
  });

  it("has the tag for every station while the FM radio is off, and none while the HF radio is off whatever was heard", () => {
    for (const call of ["OH2HF", "OH2FM", "OH2NEW"]) expect(tag(header(FM_OFF, call)).exists(), call).toBe(true);
    const off = header({}, "OH2HF");
    expect(tag(off).exists()).toBe(false);
    expect(off.findAll("button").some((b) => b.text() === "Route")).toBe(true);
  });
});

describe("the chain of a message sent over HF", () => {
  const attempt = (radio: "" | "fm" | "hf") => ({ sent_at: "2026-10-22T12:00:00Z", hops: [], internet: null, acked: true, radio });

  it("marks the you chip HF, with the hover that says over HF, and leaves an FM attempt and one kept before there were two radios as they were", () => {
    const row = message(1, { to_call: "OH2CUB-7", state: "acked", acked_at: "2026-10-22T12:00:05Z" });
    const hf = chainOf(row, attempt("hf"), true);
    expect(hf.map((chip) => [chip.text, chip.mark])).toEqual([
      ["you", "HF"],
      ["OH2CUB-7", "✓"],
    ]);
    expect(hf[0]?.title).toMatch(/^sent \d{4}-\d\d-\d\d \d\d:\d\d:\d\d over HF$/);
    for (const radio of ["fm", ""] as const) {
      const chips = chainOf(row, attempt(radio), true);
      expect([chips[0]?.mark, chips[0]?.title]).toEqual(["", expect.stringMatching(/^sent \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/)]);
    }
  });

  it("is drawn with the mark after the chip", () => {
    const row = message(1, { to_call: "OH2CUB-7", state: "acked", acked_at: "2026-10-22T12:00:05Z", attempts_detail: [attempt("hf")] });
    const wrapper = mount(MessageChain, { props: { row } });
    expect(wrapper.find(".chips li").text()).toBe("youHF");
  });
});

describe("a message that came in over HF", () => {
  const thread = (radio: "" | "fm" | "hf", route = "direct") => [incoming(2, "OH2HF", { radio, route })];

  it("has the tag HF before its route words under the bubble, and an FM message's line is as it was", () => {
    const hf = mount(ConversationThread, { props: { thread: thread("hf"), peer: "OH2HF" } });
    const line = hf.find(".bubble-route");
    expect(line.find(".tag").text()).toBe("HF");
    expect(line.text()).toBe("HF direct");
    const fm = mount(ConversationThread, { props: { thread: thread("fm", "via OH2RCH-2"), peer: "OH2HF" } });
    expect(fm.find(".bubble-route").text()).toBe("via OH2RCH-2");
    expect(fm.find(".bubble-route .tag").exists()).toBe(false);
  });

  it("has no tag under a message of ours", () => {
    const wrapper = mount(ConversationThread, { props: { thread: [message(1, { radio: "", route: "" })], peer: "OH2HF" } });
    expect(wrapper.find(".bubble-route").exists()).toBe(false);
  });
});

describe("the email gateway with the FM radio off", () => {
  const compose = (values: Record<string, string>) =>
    mount(EmailCompose, {
      props: { connected: true, addresses: [] },
      global: withDaemon(fakeDaemon({ config: configValues(values) })),
      attachTo: document.body,
    });

  it("keeps Send off with the title that says the gateway goes out over FM, once there is an address and a text", async () => {
    const wrapper = compose(FM_OFF);
    await wrapper.find("#mail-to").setValue("a@example.org");
    await wrapper.find("#mail-text").setValue("hello");
    const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
    expect(send.element.disabled).toBe(true);
    expect(send.attributes("title")).toBe("Email goes out over the FM radio, which is off");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("sends as it does today while the FM radio is on, with the HF radio on or off", async () => {
    for (const values of [{}, BOTH]) {
      const wrapper = compose(values);
      await wrapper.find("#mail-to").setValue("a@example.org");
      await wrapper.find("#mail-text").setValue("hello");
      const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
      expect([send.element.disabled, send.attributes("title")]).toEqual([false, undefined]);
    }
  });

  it("keeps Check email off with the same title", () => {
    const wrapper = mount(EmailPane, {
      props: { thread: [], addresses: [] },
      global: withDaemon(fakeDaemon({ config: configValues(FM_OFF) })),
    });
    const check = wrapper.findAll("button").find((b) => b.text() === "Check email");
    expect([check?.element.disabled, check?.attributes("title")]).toEqual([true, "Email goes out over the FM radio, which is off"]);
  });
});

describe("the channel tags while the HF radio is on", () => {
  const stations = (values: Record<string, string>) => {
    const both = station("OH2BOTH", { heard_rf: 5, heard_fm: 3, heard_hf: 2, last_heard: ago(10) });
    return mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ config: configValues(values), stations: table(both, heardOnFm, heardOnHf) })),
    });
  };
  const labels = (wrapper: ReturnType<typeof stations>) =>
    wrapper.findAll("tbody tr[data-call]").map((tr) => [tr.attributes("data-call"), tr.findAll(".via").map((v) => v.text())]);

  it("names the FM radio FM beside HF, in the table, and keeps RF as it always was while the HF radio is off", () => {
    expect(labels(stations(BOTH)).sort()).toEqual([
      ["OH2BOTH", ["FM", "HF"]],
      ["OH2FM", ["FM"]],
      ["OH2HF", ["HF"]],
    ]);
    expect(labels(stations({})).sort()).toEqual([
      ["OH2BOTH", ["RF", "HF"]],
      ["OH2FM", ["RF"]],
      ["OH2HF", ["HF"]],
    ]);
  });

  it("says the same in the Packets tab: FM and HF while the HF radio is on, RF while it is off", () => {
    const packets = new Map([
      ["1", packet(1, { radio: "fm" })],
      ["2", packet(2, { radio: "hf" })],
    ]);
    const via = (values: Record<string, string>) =>
      mount(PacketsLog, { props: { packets }, global: withDaemon(fakeDaemon({ config: configValues(values) })) })
        .findAll("td.via")
        .map((td) => td.text());
    expect(via(BOTH)).toEqual(["HF", "FM"]);
    expect(via({})).toEqual(["HF", "RF"]);
  });
});

describe("the radio step of the setup guide", () => {
  const fresh = (extra: Record<string, string> = {}) =>
    configValues({ "beacon/interval_min": "0", "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "", "serial/port": "", ...extra });
  const portList = (): PortsMessage => ({ type: "ports", sound_cards: [], search: true, find: true, ports: [] });

  async function open(values: Record<string, string> = {}) {
    const config = ref<ConfigValues | null>(fresh(values));
    const sent: Command[] = [];
    const send = (command: Command) => (sent.push(command), true);
    const guide = useSetupGuide(config, ref<Toast | null>(null), ref<PortsMessage | null>(portList()), send);
    guide.show();
    const daemon = fakeDaemon({ config, guide, send, ports: portList() });
    const wrapper = mount(SetupGuide, { global: withDaemon(daemon), attachTo: document.body });
    await wrapper.find<HTMLInputElement>("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find<HTMLInputElement>("#setup-lat").setValue("60.17");
    await wrapper.find<HTMLInputElement>("#setup-lon").setValue("24.94");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    return { wrapper, guide, sent, daemon };
  }

  it("has the two boxes, FM radio with its Enable ticked and greyed (the only radio) and the fields as today, and HF radio as its Enable row alone", async () => {
    const { wrapper, guide } = await open();
    expect(wrapper.findAll("fieldset.subbox legend").map((l) => l.text())).toEqual(["FM radio", "HF radio"]);
    const [fmBox, hfBox] = wrapper.findAll("fieldset.subbox");
    expect(fmBox?.find<HTMLInputElement>("#setup-fm").element.checked).toBe(true);
    expect(fmBox?.find<HTMLInputElement>("#setup-fm").element.disabled).toBe(true);
    expect(fmBox?.find("#setup-fm").element.closest(".field")?.getAttribute("title")).toBe("The station's only radio: tick the other first");
    for (const id of ["#setup-profile", "#setup-port", "#setup-baud", "#setup-find-radio"]) expect(fmBox?.find(id).exists(), id).toBe(true);
    expect(hfBox?.findAll("select, input").map((e) => e.attributes("id"))).toEqual(["setup-hf"]);
    expect(Object.keys(guide.changes)).not.toContain("fm/enabled");
  });

  it("saves the HF radio ticked with the rest, and the FM radio unticked, with nothing of the FM radio's line to ask for or save", async () => {
    const { wrapper, guide } = await open();
    await wrapper.find("#setup-hf").setValue(true);
    expect(guide.changes).toMatchObject({ "hf/enabled": "true" });
    expect(wrapper.find<HTMLInputElement>("#setup-fm").element.disabled).toBe(false);
    await wrapper.find("#setup-fm").setValue(false);
    await nextTick();
    expect(guide.changes).toMatchObject({ "hf/enabled": "true", "fm/enabled": "false" });
    for (const id of ["#setup-profile", "#setup-port", "#setup-baud", "#setup-find-radio"]) expect(wrapper.find(id).exists(), id).toBe(false);
    expect(Object.keys(guide.changes).filter((key) => /^(tnc|serial|tcp)\//.test(key))).toEqual([]);
    expect(wrapper.find<HTMLInputElement>("#setup-hf").element.disabled).toBe(true);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined(); // (Finish: a station with the HF radio alone needs no port)
  });

  it("starts from the settings: a station with the HF radio alone has its box ticked and the FM radio's fields out of sight", async () => {
    const { wrapper } = await open({ "fm/enabled": "false", "hf/enabled": "true" });
    expect(wrapper.find<HTMLInputElement>("#setup-fm").element.checked).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#setup-hf").element.checked).toBe(true);
    expect(wrapper.find("#setup-profile").exists()).toBe(false);
  });
});

describe("the tell helper still follows the radios", () => {
  it("shows the FM tags once the HF radio is ticked in a page that is already drawn", async () => {
    const daemon = fakeDaemon({ config: configValues({}), stations: table(heardOnFm) });
    const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(daemon) });
    expect(wrapper.find("tbody .via").text()).toBe("RF");
    await tell(daemon, { config: configValues(BOTH) });
    expect(wrapper.find("tbody .via").text()).toBe("FM");
  });
});
