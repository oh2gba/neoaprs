import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { receiverLook } from "@/lib/receiverstatus";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, mapState, toastOf } from "@/test/fixtures";
import { mapLayer } from "@/test/layerfixtures";
import type { LayerReceiver } from "@/protocol/protocol";

const NOW = Date.parse("2026-10-21T12:00:03Z");
const receiving = (things: number, heard_at: string | null = "2026-10-21T12:00:00Z"): LayerReceiver => ({ state: "receiving", things, heard_at });

/** The Settings tab with the layers of the map as `layers` says them and `extra` over the settings. */
function make(extra: Record<string, string> = {}, layers = [mapLayer("aircraft"), mapLayer("ships")]) {
  const daemon = fakeDaemon({ config: configValues(extra), map: mapState({ layers }) });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  return { wrapper, send: daemon.send, daemon };
}
const options = (wrapper: ReturnType<typeof make>["wrapper"], id: string) => wrapper.findAll(`${id} option`).map((o) => o.text());

describe("Settings, Map: aircraft and ships", () => {
  it("has the rows Aircraft and Ships, each at None out of the box, with no address field", () => {
    const { wrapper } = make();
    expect(wrapper.find<HTMLSelectElement>("#set-map-aircraft").element.value).toBe("none");
    expect(wrapper.find<HTMLSelectElement>("#set-map-ships").element.value).toBe("none");
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(false);
    expect(wrapper.find("#set-map-ships_host").exists()).toBe(false);
    expect(wrapper.find('label[for="set-map-aircraft"]').text()).toBe("Aircraft");
    expect(wrapper.find('label[for="set-map-ships"]').text()).toBe("Ships");
  });

  it("lists the sources the daemon offers, in its order, by the services' own names", () => {
    const { wrapper } = make();
    expect(options(wrapper, "#set-map-aircraft")).toEqual(["None", "adsb.fi", "adsb.lol", "My own receiver"]);
    expect(options(wrapper, "#set-map-ships")).toEqual(["None", "Fintraffic", "My own receiver"]);
  });

  it("has no Fintraffic in the Ships list where the daemon does not offer it", () => {
    const { wrapper } = make({}, [mapLayer("aircraft"), mapLayer("ships", { offered: ["none", "receiver"] })]);
    expect(options(wrapper, "#set-map-ships")).toEqual(["None", "My own receiver"]);
  });

  it("shows a stored source that is not offered as None", () => {
    const { wrapper } = make({ "map/ships": "fintraffic" }, [mapLayer("aircraft"), mapLayer("ships", { offered: ["none", "receiver"] })]);
    expect(wrapper.find<HTMLSelectElement>("#set-map-ships").element.value).toBe("none");
  });

  it("shows the stored source of a service", () => {
    const { wrapper } = make({ "map/aircraft": "adsblol" }, [mapLayer("aircraft", { source: "adsblol" }), mapLayer("ships")]);
    expect(wrapper.find<HTMLSelectElement>("#set-map-aircraft").element.value).toBe("adsblol");
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(false);
  });

  it("saves each choice at once with set_config", async () => {
    const { wrapper, send } = make();
    await wrapper.find("#set-map-aircraft").setValue("adsbfi");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/aircraft": "adsbfi" } });
    const other = make();
    await other.wrapper.find("#set-map-ships").setValue("fintraffic");
    expect(other.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/ships": "fintraffic" } });
  });

  it("shows the address field and its state only while the choice is My own receiver, and hides it with another choice", async () => {
    const { wrapper } = make({ "map/aircraft": "receiver" }, [mapLayer("aircraft", { source: "receiver", receiver: receiving(42) }), mapLayer("ships")]);
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(true);
    expect(wrapper.find('label[for="set-map-aircraft_host"]').text()).toBe("Receiver's address");
    expect(wrapper.find("#set-map-aircraft_host").attributes("placeholder")).toBe("This computer");
    expect(wrapper.find(".receiverstatus").exists()).toBe(true);
    expect(wrapper.find("#set-map-ships_host").exists()).toBe(false);
    await wrapper.find("#set-map-aircraft").setValue("adsbfi");
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(false);
    expect(wrapper.find(".receiverstatus").exists()).toBe(false);
  });

  it("saves the typed address when the field is left", async () => {
    const { wrapper, send } = make({ "map/ships": "receiver" }, [mapLayer("aircraft"), mapLayer("ships", { source: "receiver", receiver: receiving(3) })]);
    await wrapper.find("#set-map-ships_host").setValue("ais.local:10110");
    await wrapper.find("#set-map-ships_host").trigger("blur");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/ships_host": "ais.local:10110" } });
  });

  it("says the refusal of an address in the page's words under the field", async () => {
    const { wrapper, daemon } = make({ "map/aircraft": "receiver" }, [mapLayer("aircraft", { source: "receiver" }), mapLayer("ships")]);
    await wrapper.find("#set-map-aircraft_host").setValue("a b");
    await wrapper.find("#set-map-aircraft_host").trigger("blur");
    await tell(daemon, {
      lastError: toastOf("set_config: map/aircraft_host: 'a b' is not the address of a receiver", "setting.not_receiver", { value: "a b" }),
    });
    const field = wrapper.find("#set-map-aircraft_host").element.closest(".field");
    expect(field?.querySelector(".field-error")?.textContent).toBe("'a b' is not the address of a receiver");
  });

  it("has an (i) on each row and on each address", () => {
    const { wrapper } = make({ "map/aircraft": "receiver", "map/ships": "receiver" });
    for (const id of ["aircraft", "ships", "aircraft_host", "ships_host"])
      expect(wrapper.find(`#set-map-${id}`).element.closest(".field")?.querySelector(".info-toggle"), id).not.toBeNull();
  });

  it("keeps the room of the state: a receiver that has not said yet is looking, so the row is there from the start", () => {
    const { wrapper } = make({ "map/aircraft": "receiver" });
    expect(wrapper.find(".receiverstatus").text()).toContain("looking");
    expect(wrapper.find(".receiverstatus").text()).toContain("Looking for the receiver");
  });
});

describe("the state of an own receiver in words", () => {
  it("says looking, receiving with the count and the age, and no answer", () => {
    expect(receiverLook("aircraft", { state: "looking", things: 0, heard_at: null }, NOW)).toMatchObject({
      state: "looking",
      line: "Looking for the receiver",
    });
    expect(receiverLook("aircraft", receiving(42), NOW)).toMatchObject({ state: "receiving", tone: "tnc-connected", line: "Receiving: 42 aircraft, 3 s ago" });
    expect(receiverLook("aircraft", { state: "no_answer", things: 0, heard_at: null }, NOW)).toMatchObject({
      state: "no answer",
      line: "No answer from the receiver",
    });
  });

  it("counts ships in the singular and the plural, and tells a connection that has heard none", () => {
    expect(receiverLook("ships", receiving(1), NOW).line).toBe("Receiving: 1 ship, 3 s ago");
    expect(receiverLook("ships", receiving(12), NOW).line).toBe("Receiving: 12 ships, 3 s ago");
    expect(receiverLook("ships", receiving(0, null), NOW).line).toBe("Connected, no ship heard yet");
    expect(receiverLook("aircraft", receiving(0, null), NOW).line).toBe("Receiving, no aircraft yet");
  });

  it("names no address and no port", () => {
    for (const layer of ["aircraft", "ships"] as const)
      for (const state of ["looking", "receiving", "no_answer"] as const)
        expect(JSON.stringify(receiverLook(layer, { state, things: 2, heard_at: "2026-10-21T12:00:00Z" }, NOW))).not.toMatch(/:\d|\d\.\d+\.\d|\//);
  });
});
