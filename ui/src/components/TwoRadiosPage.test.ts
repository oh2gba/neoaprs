// The places of the page where the two radios of before show beyond the Radio group: a conversation's note, the mark of an attempt over HF and the tag under a message that came over HF, the email gateway with the FM radio
// off, the channel tags FM and HF of the Stations table and the Packets tab while the HF radio is on (and RF as it always was while it is off). A conversation's radio, Route and Send are ConversationRadio.test.ts's and
// PathControlsRadios.test.ts's; the setup guide's Radio step, live as the Radio group is, is SetupGuide.test.ts's.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import ConversationView from "@/components/ConversationView.vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailPane from "@/components/EmailPane.vue";
import MessageChain from "@/components/MessageChain.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { ago, attemptRow, configValues, incoming, message, packet, station, table } from "@/test/fixtures";

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

  it("says above the box to write in that a station whose position takes no messages may not take them, with the (i) that says why, and lets the message go", async () => {
    const quiet = station("OH2PLN", { heard_fm: 2, may_not_message: true });
    const daemon = fakeDaemon({ config: configValues({}), stations: shallowRef(new Map([[quiet.call, quiet]])) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2PLN", narrow: false, thread: [] }, global: withDaemon(daemon) });
    const note = wrapper.find(".convo-maynot");
    expect(note.text()).toContain("This station may not take messages");
    expect(note.find(".infotip").exists()).toBe(true);
    await wrapper.find("#msg-text").setValue("hello anyway");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
    expect(header({}, "OH2FM").find(".convo-maynot").exists()).toBe(false);
  });
});

describe("the chain of a message sent over HF", () => {
  const attempt = (radio: "" | "fm" | "hf") => attemptRow({ acked: true, radio });

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

  it("keeps Send off with the title that says no radio the gateways hear is on, once there is an address and a text", async () => {
    const wrapper = compose(FM_OFF);
    await wrapper.find("#mail-to").setValue("a@example.org");
    await wrapper.find("#mail-text").setValue("hello");
    const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
    expect(send.element.disabled).toBe(true);
    expect(send.attributes("title")).toBe("No radio that internet gateways hear is on");
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
    expect([check?.element.disabled, check?.attributes("title")]).toEqual([true, "No radio that internet gateways hear is on"]);
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

describe("the tell helper still follows the radios", () => {
  it("shows the FM tags once the HF radio is ticked in a page that is already drawn", async () => {
    const daemon = fakeDaemon({ config: configValues({}), stations: table(heardOnFm) });
    const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(daemon) });
    expect(wrapper.find("tbody .via").text()).toBe("RF");
    await tell(daemon, { config: configValues(BOTH) });
    expect(wrapper.find("tbody .via").text()).toBe("FM");
  });
});
