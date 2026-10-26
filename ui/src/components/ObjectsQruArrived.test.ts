// What a request for a group came to: how many objects the server's closing line says it sent and how many arrived (Local info), Ask again for the ones that did not, and the way from there to the Stations tab, where the objects are
// (with the Local info tag, StationsTable).
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ObjectsQru from "@/components/ObjectsQru.vue";
import StationsTable from "@/components/StationsTable.vue";
import { usePanel } from "@/composables/usePanel";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { NOW, ago, qruState, station, table } from "@/test/fixtures";

const attend = vi.hoisted(() => vi.fn(() => Promise.resolve(true)));
vi.mock("@/lib/attention", () => ({ attend }));

/** The server of the exchange with OH2DPN: INFO 150 listed TEST(1); TEST 150 was asked and its closing line says one object went. */
const dpn = (over: Record<string, unknown>) => ({
  call: "OH2DPN",
  groups: [{ name: "TEST", count: 1 }],
  max_objects: 5,
  range: 150,
  unit: "km" as const,
  at: ago(40),
  sent: "Sent 1 TEST Objects Max 5@150km de OH2DPN",
  sent_at: ago(40),
  sent_objects: 1,
  request: "TEST 150",
  received: [] as string[],
  settles_at: ago(10),
  ...over,
});
const state = (over: Record<string, unknown>, asked = { text: "TEST 150", at: ago(45) }) => qruState({ asked, servers: [dpn(over)] });
const line = (wrapper: ReturnType<typeof mount>) => wrapper.find(".qru-sent");
beforeEach(() => attend.mockClear());

describe("Local info: what arrived of what the server sent", () => {
  it("says sent 1 and 1 arrived quietly, with the closing line as the hover, and no Ask again", () => {
    const wrapper = mount(ObjectsQru, { global: withDaemon(fakeDaemon({ qru: state({ received: ["TESTOBJ"] }) })) });
    expect(line(wrapper).text()).toContain("sent 1 · 1 arrived");
    expect(line(wrapper).classes()).toContain("muted");
    expect(line(wrapper).classes()).not.toContain("warn");
    expect(line(wrapper).attributes("title")).toBe("Sent 1 TEST Objects Max 5@150km de OH2DPN");
    expect(wrapper.find(".qru-again").exists()).toBe(false);
  });

  it("says sent 1 and 0 arrived in the warn colour with Ask again once the time for late ones is over, and Ask again sends the same request", async () => {
    const daemon = fakeDaemon({ qru: state({}, { text: "TEST 150", at: ago(90) }) });
    const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
    expect(line(wrapper).text()).toContain("sent 1 · 0 arrived");
    expect(line(wrapper).classes()).toContain("warn");
    expect(line(wrapper).attributes("title")).toBe("Fewer arrived than the server said it sent");
    const again = wrapper.find<HTMLButtonElement>("button.qru-again");
    expect(again.text()).toBe("Ask again");
    expect(again.classes()).toContain("small");
    expect(again.attributes("title")).toBe("Ask OH2DPN again: TEST 150");
    expect(again.attributes("disabled")).toBeUndefined();
    await again.trigger("click");
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "qru_ask", text: "TEST 150" });
    expect(wrapper.find("a, button.qru-stations").exists()).toBe(false);
  });

  it("does not call it lost while a late object may still come, and Ask again is not there yet", async () => {
    const daemon = fakeDaemon({ qru: state({ settles_at: ago(-20) }) });
    const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
    expect(line(wrapper).text()).toContain("sent 1 · 0 arrived");
    expect(line(wrapper).classes()).not.toContain("warn");
    expect(wrapper.find(".qru-again").exists()).toBe(false);
    await tell(daemon, { now: NOW + 21_000 });
    expect(line(wrapper).classes()).toContain("warn");
    expect(wrapper.find(".qru-again").exists()).toBe(true);
  });

  it("holds Ask again for the minute of the same request (the daemon's limit) with the time left, and for ten seconds after any other, and in RX only", async () => {
    const daemon = fakeDaemon({ qru: state({}, { text: "TEST 150", at: ago(45) }) });
    const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
    const again = () => wrapper.find<HTMLButtonElement>("button.qru-again");
    expect(again().attributes("disabled")).toBeDefined();
    expect(again().attributes("title")).toBe("Next request in 15 s");
    await again().trigger("click");
    expect(daemon.send).not.toHaveBeenCalled();
    await tell(daemon, { now: NOW + 16_000 });
    expect(again().attributes("disabled")).toBeUndefined();
    await tell(daemon, { qru: state({}, { text: "INFO 150", at: ago(5) }) });
    expect(again().attributes("title")).toBe("Ask OH2DPN again: TEST 150");
    await tell(daemon, { qru: state({}, { text: "INFO", at: ago(-14) }) });
    expect(again().attributes("disabled")).toBeDefined();
    const rx = mount(ObjectsQru, { global: withDaemon(fakeDaemon({ qru: state({}), receiveOnly: true })) });
    expect(rx.find("button.qru-again").attributes("title")).toBe("RX only: nothing is sent");
  });

  it("says only how many arrived when no closing line was heard, and nothing when nothing arrived", () => {
    const some = mount(ObjectsQru, {
      global: withDaemon(fakeDaemon({ qru: state({ sent_objects: null, request: "", sent: "", sent_at: null, settles_at: null, received: ["A", "B"] }) })),
    });
    expect(line(some).text()).toContain("2 arrived");
    expect(some.find(".qru-again").exists()).toBe(false);
    const none = mount(ObjectsQru, {
      global: withDaemon(fakeDaemon({ qru: state({ sent_objects: null, request: "", sent: "", sent_at: null, settles_at: null }) })),
    });
    expect(none.find(".qru-sent").exists()).toBe(false);
  });

  it("has no second list of the objects: a link to the Stations tab opens it and flashes the row of the first object", async () => {
    const panel = usePanel();
    const wrapper = mount(ObjectsQru, { global: withDaemon(fakeDaemon({ panel, qru: state({ received: ["TESTOBJ", "OTHER"] }) })) });
    expect(wrapper.text()).not.toContain("TESTOBJ");
    const link = wrapper.find<HTMLButtonElement>("button.qru-stations");
    expect(link.text()).toBe("in Stations");
    await link.trigger("click");
    expect(panel.tab.value).toBe("stations");
    expect(attend).toHaveBeenCalledWith("station-TESTOBJ");
  });
});

describe("the objects that arrived, in the Stations tab", () => {
  const make = (qru = state({ received: ["TESTOBJ"] })) =>
    mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ qru, stations: table(station("TESTOBJ", { kind: "object", heard_rf: 1 }), station("OH2RF", { heard_rf: 3 })) })),
    });

  it("carry a Local info tag in the tag column, beside RF, with the server's call in its hover; a station that is no answer has none", () => {
    const wrapper = make();
    const tags = (call: string) => wrapper.find(`tr[data-call='${call}']`).findAll(".via");
    expect(tags("TESTOBJ").map((tag) => tag.text())).toEqual(["RF", "Local info"]);
    expect(tags("TESTOBJ")[1]?.attributes("title")).toBe("Sent to us by OH2DPN when we asked for local info");
    expect(tags("TESTOBJ")[1]?.classes()).toContain("tag-neutral");
    expect(tags("OH2RF").map((tag) => tag.text())).toEqual(["RF"]);
  });

  it("have a row that the link can bring into view: its id is the one lib/stations gives", () => {
    expect(make().find("tr[data-call='TESTOBJ']").attributes("id")).toBe("station-TESTOBJ");
  });

  it("lose the tag when the daemon has forgotten the answer", () => {
    expect(
      make(state({ received: [] }))
        .find("tr[data-call='TESTOBJ']")
        .findAll(".via")
        .map((tag) => tag.text()),
    ).toEqual(["RF"]);
  });
});
