// The fold of Local info's Ask (ObjectsQru.vue with RequestPath.vue): the path and RF only of a request to QRU, and that the request is as it always was when they are left alone.
import { mount } from "@vue/test-utils";
import { shallowReactive } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import ObjectsQru from "@/components/ObjectsQru.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, qruState } from "@/test/fixtures";
import type { StationPref } from "@/protocol/protocol";

function make(given: Parameters<typeof fakeDaemon>[0] = {}) {
  const daemon = fakeDaemon({ fallbackPath: "WIDE1-1,WIDE2-1", qru: qruState({ asked: null }), ...given });
  const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
  return { wrapper, daemon };
}
type Wrapper = ReturnType<typeof make>["wrapper"];
const ask = (wrapper: Wrapper) => wrapper.find(".qru-ask button.btn");
const pills = (wrapper: Wrapper) => wrapper.findAll("button.qru-group");
const fold = (wrapper: Wrapper) => wrapper.find("details.disclosure");
const pathField = (wrapper: Wrapper) => fold(wrapper).find("input[type='text']");
const rfOnly = (wrapper: Wrapper) => fold(wrapper).find("input[type='checkbox']");
const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);

beforeEach(() => localStorage.clear());

describe("the path of a request for local info", () => {
  it("is in a closed fold titled Advanced under Ask, as in Ask around, with the beacon's path as the placeholder and RF only ticked", () => {
    const { wrapper } = make();
    expect(fold(wrapper).attributes("open")).toBeUndefined();
    expect(fold(wrapper).find("summary").text()).toBe("Advanced");
    expect(
      fold(wrapper)
        .findAll("label")
        .map((l) => l.text()),
    ).toEqual(["Path", "RF only"]);
    expect(pathField(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect((rfOnly(wrapper).element as HTMLInputElement).checked).toBe(true);
  });

  it("has the station QRU's own path as the placeholder when it has one", () => {
    const prefs = useStationPrefs(shallowReactive(new Map<string, StationPref>([["QRU", { path: "OH2RCH-2", rf_only: false, alert: null }]])), () => true);
    const { wrapper } = make({ prefs });
    expect(pathField(wrapper).attributes("placeholder")).toBe("OH2RCH-2");
  });

  it("left alone, sends the request as it always went: no path and no RF only in the command", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    expect(sent(daemon)).toEqual([{ cmd: "qru_ask", text: "INFO 150" }]);
  });

  it("sends the path typed, and RF only as it is ticked, with Ask and with a group", async () => {
    const { wrapper, daemon } = make();
    await pathField(wrapper).setValue("OH2RDK-7,OH2RCH-2");
    await ask(wrapper).trigger("click");
    await rfOnly(wrapper).setValue(false);
    await pills(wrapper)[0]?.trigger("click");
    await pathField(wrapper).setValue("");
    expect(sent(daemon)).toEqual([
      { cmd: "qru_ask", text: "INFO 150", path: "OH2RDK-7,OH2RCH-2", rf_only: true },
      { cmd: "qru_ask", text: "RP70 150", path: "OH2RDK-7,OH2RCH-2", rf_only: false },
    ]);
    await ask(wrapper).trigger("click");
    expect(sent(daemon)[2]).toEqual({ cmd: "qru_ask", text: "INFO 150", path: null, rf_only: false });
  });

  it("keeps Ask and the groups off while the path is wrong, with the reason, and the field red", async () => {
    const { wrapper } = make({ config: configValues() });
    await pathField(wrapper).setValue("OH2RDK-7,???");
    expect(fold(wrapper).find(".field").classes()).toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Calls separated by commas, at most 8");
    expect(pills(wrapper).every((p) => p.attributes("disabled") !== undefined && p.attributes("title") === "Calls separated by commas, at most 8")).toBe(true);
  });

  it("is remembered by the browser apart from Ask around's, and opens the fold when it is not the usual", async () => {
    const first = make();
    await pathField(first.wrapper).setValue("OH2RDK-7,OH2RCH-2");
    first.wrapper.unmount();
    expect(localStorage.getItem("NeoAPRS.qru.path")).toBe("OH2RDK-7,OH2RCH-2");
    expect(localStorage.getItem("NeoAPRS.ask.path")).toBeNull();
    const { wrapper } = make();
    expect((pathField(wrapper).element as HTMLInputElement).value).toBe("OH2RDK-7,OH2RCH-2");
    expect(fold(wrapper).attributes("open")).toBeDefined();
  });
});
