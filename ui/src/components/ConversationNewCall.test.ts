// A conversation with a call no radio heard: the + in the head of the conversation list takes the
// call and opens an empty conversation with it, and there Route chooses the radio and sets the path
// as for a station heard, the daemon saying them back in the topic `call_routes`. The box to write
// in counts the room the radio's frame leaves (a station row's `text_max`).
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationList from "@/components/ConversationList.vue";
import ConversationView from "@/components/ConversationView.vue";
import type { CallRoute } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon, type Given } from "@/test/context";
import { radioRow, radiosTopic, station, status } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
afterEach(() => document.body.replaceChildren());

/** Packet on radio 1, Mercury on 2 and a second Packet radio with a path of its own on 3. */
const THREE = radiosTopic(
  radioRow(1, "kenwood-tnc2", { name: "VHF" }),
  radioRow(2, "mercury", { name: "HF" }),
  radioRow(3, "kiss", { name: "Mobile", number: 2 }),
);
const NEW = "EA8EE-2";
let daemon: FakeDaemon;
const sent = (cmd: string) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === cmd);

function conversation(call: string, given: Given = {}) {
  daemon = fakeDaemon({ radios: THREE, status: status({ unheard_radio: 1 }), ...given });
  return mount(ConversationView, {
    props: { selected: call, narrow: false, thread: [] },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
}
async function opened(wrapper: VueWrapper) {
  await wrapper.find(".route-button").trigger("click");
  return wrapper.find(".route-box");
}
const routes = (entries: Record<string, CallRoute>) => shallowRef(new Map(Object.entries(entries)));

describe("the + of the conversation list", () => {
  function list(ours: string | null = "OH2GBA") {
    return mount(ConversationList, {
      props: { conversations: [], selected: null, now: 0, showOverheard: false, ours },
      attachTo: document.body,
    });
  }

  it("is a button named for what it does, with no field until it is pressed", async () => {
    const wrapper = list();
    const add = wrapper.find(".convlist-head button.convlist-add");
    expect([add.attributes("aria-label"), wrapper.find("#msg-new-call").exists()]).toEqual(["New conversation", false]);
    await add.trigger("click");
    expect(document.activeElement?.id).toBe("msg-new-call");
    expect(wrapper.find(".convlist-new label").text()).toBe("Call");
    expect(wrapper.find(".convlist-new p").exists()).toBe(false);
  });

  it("opens the conversation with the call typed, in capitals, and closes", async () => {
    const wrapper = list();
    await wrapper.find("button.convlist-add").trigger("click");
    await wrapper.find("#msg-new-call").setValue(" ea8ee-2 ");
    await wrapper.find(".convlist-new").trigger("submit");
    expect(wrapper.emitted("write")).toEqual([[NEW, ""]]);
    expect(wrapper.find("#msg-new-call").exists()).toBe(false);
  });

  it("takes a call as the daemon does and marks one it would refuse, Write off, and our own call too", async () => {
    const wrapper = list();
    await wrapper.find("button.convlist-add").trigger("click");
    const field = wrapper.find("#msg-new-call");
    const write = wrapper.find<HTMLButtonElement>(".convlist-new button[type='submit']");
    for (const [typed, ok] of [
      ["OH2DPN", true],
      ["WINLINK", true],
      ["OH2DPN-15", true],
      ["OH 2DPN", false],
      ["OH2DPN-STATION", false],
      ["ÖH2DPN", false],
      ["oh2gba", false],
    ] as const) {
      await field.setValue(typed);
      expect([typed, write.element.disabled, field.classes("invalid")]).toEqual([typed, !ok, !ok]);
    }
    await field.setValue("");
    expect([write.element.disabled, field.classes("invalid")]).toEqual([true, false]);
    await wrapper.find(".convlist-new").trigger("submit");
    expect(wrapper.emitted("write")).toBeUndefined();
  });

  it("closes on Esc and on a second press", async () => {
    const wrapper = list();
    await wrapper.find("button.convlist-add").trigger("click");
    await wrapper.find("#msg-new-call").trigger("keydown", { key: "Escape" });
    expect(wrapper.find("#msg-new-call").exists()).toBe(false);
    await wrapper.find("button.convlist-add").trigger("click");
    await wrapper.find("button.convlist-add").trigger("click");
    expect(wrapper.find("#msg-new-call").exists()).toBe(false);
  });
});

describe("Route of a call no radio heard", () => {
  it("chooses its radio, live, and the header and the list follow the daemon's word for it", async () => {
    const wrapper = conversation(NEW);
    const box = await opened(wrapper);
    const pick = box.find<HTMLSelectElement>("select.route-radio-pick");
    expect([pick.element.disabled, pick.element.selectedOptions[0]?.text]).toEqual([false, "Automatic: VHF"]);
    await pick.setValue("2");
    expect(sent("station_radio")).toEqual([{ cmd: "station_radio", call: NEW, radio: 2 }]);
    await tell(daemon, { callRoutes: new Map([[NEW, { radio_choice: 2, radio_now: 2, paths: {} }]]) });
    expect(wrapper.find(".convo-head .convo-radio .tag").text()).toBe("HF");
    expect(wrapper.find<HTMLSelectElement>("select.route-radio-pick").element.value).toBe("2");
  });

  it("sets the path typed on the radio in force and shows the one the daemon keeps for that call and radio", async () => {
    const wrapper = conversation(NEW, {
      callRoutes: routes({ [NEW]: { radio_choice: 3, radio_now: 3, paths: { "3": "OH2GBA-12" } } }),
    });
    const box = await opened(wrapper);
    const field = box.find<HTMLInputElement>(".pathbox:not(.route-radio) input[type='text']");
    expect([field.element.value, field.element.disabled]).toEqual(["OH2GBA-12", false]);
    await field.setValue("OH2DPN");
    expect(sent("set_station_path")).toEqual([{ cmd: "set_station_path", call: NEW, path: "OH2DPN", radio: 3 }]);
  });

  it("keeps radio 1's path as for any station, and RF only live on Mercury", async () => {
    const wrapper = conversation(NEW, { callRoutes: routes({ [NEW]: { radio_choice: 2, radio_now: 2, paths: {} } }) });
    const box = await opened(wrapper);
    const rfOnly = box.find<HTMLInputElement>(".rfonly input");
    expect(rfOnly.element.disabled).toBe(false);
    await rfOnly.setValue(true);
    expect(sent("set_station_rf_only")).toEqual([{ cmd: "set_station_rf_only", call: NEW, on: true }]);
  });
});

describe("the room for the text", () => {
  it("is what the station's row says the radio's frame leaves, and the whole text where it says none", async () => {
    const row = station("OH2HF", { radio_now: 2, text_max: 66 });
    const wrapper = conversation("OH2HF", { stations: shallowRef(new Map([[row.call, row]])) });
    const text = wrapper.find("input.compose-text");
    await text.setValue("x".repeat(70));
    expect((text.element as HTMLInputElement).value).toHaveLength(66);
    expect(wrapper.find(".compose-left").text()).toBe("0 left");
    await tell(daemon, { stations: new Map([[row.call, { ...row, text_max: null }]]) });
    await text.setValue("x".repeat(67));
    expect((text.element as HTMLInputElement).value).toHaveLength(67);
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
  });
});
