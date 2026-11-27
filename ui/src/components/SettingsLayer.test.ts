import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { ref } from "vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { forgetLayerTicks, useMapLayers } from "@/composables/useMapLayers";
import { receiverLook } from "@/lib/receiverstatus";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, mapState, toastOf } from "@/test/fixtures";
import { AISSTREAM_KEY_URL } from "@/lib/links";
import { mapLayer } from "@/test/layerfixtures";
import type { LayerReceiver } from "@/protocol/protocol";

const NOW = Date.parse("2026-10-21T12:00:03Z");
const receiving = (things: number, heard_at: string | null = "2026-10-21T12:00:00Z"): LayerReceiver => ({
  state: "receiving",
  things,
  heard_at,
});

/**
 * The Settings tab with the layers of the map as `layers` says them and `extra` over the settings.
 */
function make(extra: Record<string, string> = {}, layers = [mapLayer("aircraft"), mapLayer("ships")]) {
  const daemon = fakeDaemon({ config: configValues(extra), map: mapState({ layers }) });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  return { wrapper, send: daemon.send, daemon };
}
const options = (wrapper: ReturnType<typeof make>["wrapper"], id: string) =>
  wrapper.findAll(`${id} option`).map((o) => o.text());

/** This browser's ticks of the Layers box. */
const ticks = () => useMapLayers(ref(null));

beforeEach(() => {
  localStorage.clear();
  forgetLayerTicks();
});

describe("Settings, Map: aircraft and ships", () => {
  it("has the Source rows of Aircraft and Ships, each in the box of its layer and at None out of the box, with no address field", () => {
    const { wrapper } = make();
    expect(wrapper.find<HTMLSelectElement>("#set-map-aircraft").element.value).toBe("none");
    expect(wrapper.find<HTMLSelectElement>("#set-map-ships").element.value).toBe("none");
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(false);
    expect(wrapper.find("#set-map-ships_host").exists()).toBe(false);
    expect(wrapper.find('label[for="set-map-aircraft"]').text()).toBe("Source");
    expect(wrapper.find('label[for="set-map-ships"]').text()).toBe("Source");
    expect(wrapper.find("#set-map-aircraft").element.closest("fieldset")?.querySelector("legend")?.textContent).toBe(
      "Aircraft ",
    );
    expect(wrapper.find("#set-map-ships").element.closest("fieldset")?.querySelector("legend")?.textContent).toBe(
      "Ships ",
    );
  });

  it("lists the sources the daemon offers, in its order, by the services' own names", () => {
    const { wrapper } = make();
    expect(options(wrapper, "#set-map-aircraft")).toEqual([
      "None",
      "adsb.fi",
      "adsb.lol",
      "Radarcape",
      "My own receiver",
    ]);
    expect(options(wrapper, "#set-map-ships")).toEqual(["None", "Fintraffic", "AISStream", "My own receiver"]);
  });

  it("has no Fintraffic in the Ships list where the daemon does not offer it", () => {
    const { wrapper } = make({}, [mapLayer("aircraft"), mapLayer("ships", { offered: ["none", "receiver"] })]);
    expect(options(wrapper, "#set-map-ships")).toEqual(["None", "My own receiver"]);
  });

  it("shows a stored source that is not offered as None", () => {
    const { wrapper } = make({ "map/ships": "fintraffic" }, [
      mapLayer("aircraft"),
      mapLayer("ships", { offered: ["none", "receiver"] }),
    ]);
    expect(wrapper.find<HTMLSelectElement>("#set-map-ships").element.value).toBe("none");
  });

  it("shows the stored source of a service", () => {
    const { wrapper } = make({ "map/aircraft": "adsblol" }, [
      mapLayer("aircraft", { source: "adsblol" }),
      mapLayer("ships"),
    ]);
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
    const { wrapper } = make({ "map/aircraft": "receiver" }, [
      mapLayer("aircraft", { source: "receiver", receiver: receiving(42) }),
      mapLayer("ships"),
    ]);
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(true);
    expect(wrapper.find('label[for="set-map-aircraft_host"]').text()).toBe("Receiver's address");
    expect(wrapper.find("#set-map-aircraft_host").attributes("placeholder")).toBe("This computer");
    expect(wrapper.find(".receiverstatus").exists()).toBe(true);
    expect(wrapper.find("#set-map-ships_host").exists()).toBe(false);
    await wrapper.find("#set-map-aircraft").setValue("adsbfi");
    expect(wrapper.find("#set-map-aircraft_host").exists()).toBe(false);
    expect(wrapper.find(".receiverstatus").exists()).toBe(false);
  });

  it("shows the address field and its state with a Radarcape chosen, with an empty box and an (i) of one line", async () => {
    const { wrapper } = make({ "map/aircraft": "radarcape" }, [
      mapLayer("aircraft", { source: "radarcape", receiver: receiving(30) }),
      mapLayer("ships"),
    ]);
    const input = wrapper.find("#set-map-aircraft_host");
    expect(input.exists()).toBe(true);
    expect(input.attributes("placeholder")).toBe("");
    expect(wrapper.find(".receiverstatus").text()).toContain("Receiving: 30 aircraft");
    input.element.closest(".field")?.querySelector<HTMLElement>(".info-toggle")?.click();
    await wrapper.vm.$nextTick();
    const note = input.element.closest(".field")?.textContent ?? "";
    expect(note).toContain("The address of your Radarcape on your network.");
    expect(note).not.toMatch(/aircraft\.json|port|file|\//i);
  });

  it("keeps This computer in the address box of My own receiver for aircraft and for ships", () => {
    const { wrapper } = make({ "map/aircraft": "receiver", "map/ships": "receiver" });
    expect(wrapper.find("#set-map-aircraft_host").attributes("placeholder")).toBe("This computer");
    expect(wrapper.find("#set-map-ships_host").attributes("placeholder")).toBe("This computer");
  });

  it("saves the typed address when the field is left", async () => {
    const { wrapper, send } = make({ "map/ships": "receiver" }, [
      mapLayer("aircraft"),
      mapLayer("ships", { source: "receiver", receiver: receiving(3) }),
    ]);
    await wrapper.find("#set-map-ships_host").setValue("ais.local:10110");
    await wrapper.find("#set-map-ships_host").trigger("blur");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/ships_host": "ais.local:10110" } });
  });

  it("says the refusal of an address in the page's words under the field", async () => {
    const { wrapper, daemon } = make({ "map/aircraft": "receiver" }, [
      mapLayer("aircraft", { source: "receiver" }),
      mapLayer("ships"),
    ]);
    await wrapper.find("#set-map-aircraft_host").setValue("a b");
    await wrapper.find("#set-map-aircraft_host").trigger("blur");
    await tell(daemon, {
      lastError: toastOf(
        "set_config: map/aircraft_host: 'a b' is not the address of a receiver",
        "setting.not_receiver",
        { value: "a b" },
      ),
    });
    const field = wrapper.find("#set-map-aircraft_host").element.closest(".field");
    expect(field?.querySelector(".field-error")?.textContent).toBe("'a b' is not the address of a receiver");
  });

  it("has an (i) on each row and on each address", () => {
    const { wrapper } = make({ "map/aircraft": "receiver", "map/ships": "receiver" });
    for (const id of ["aircraft", "ships", "aircraft_host", "ships_host"])
      expect(
        wrapper.find(`#set-map-${id}`).element.closest(".field")?.querySelector(".info-toggle"),
        id,
      ).not.toBeNull();
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
    expect(receiverLook("aircraft", receiving(42), NOW)).toMatchObject({
      state: "receiving",
      tone: "tnc-connected",
      line: "Receiving: 42 aircraft, 3 s ago",
    });
    expect(receiverLook("aircraft", { state: "no_answer", things: 0, heard_at: null }, NOW)).toMatchObject({
      state: "no answer",
      line: "No answer from the receiver",
    });
  });

  it("says a connected receiver that has sent nothing yet without claiming it works or not", () => {
    expect(receiverLook("ships", { state: "connected", things: 0, heard_at: null }, NOW)).toEqual({
      state: "connected",
      tone: "tnc-connecting",
      line: "Connected, no ship heard yet",
    });
  });

  it("says a source that answers but sends no AIS in a state of its own, a warning", () => {
    expect(receiverLook("ships", { state: "no_ais", things: 0, heard_at: null }, NOW)).toEqual({
      state: "no AIS",
      tone: "tnc-waiting",
      line: "Connected, but no AIS comes from it",
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
      for (const state of ["looking", "connected", "receiving", "no_answer", "no_ais"] as const)
        expect(
          JSON.stringify(receiverLook(layer, { state, things: 2, heard_at: "2026-10-21T12:00:00Z" }, NOW)),
        ).not.toMatch(/:\d|\d\.\d+\.\d|\//);
  });

  it("switches the layer on in this browser when a source is chosen, and leaves it as it is for None", async () => {
    const { wrapper } = make();
    await wrapper.find("#set-map-aircraft").setValue("adsbfi");
    expect(ticks().ticked("aircraft")).toBe(true);
    expect(localStorage.getItem("NeoAPRS.layer.aircraft")).toBe("on");
    expect(ticks().ticked("ships")).toBe(false);
    await wrapper.find("#set-map-ships").setValue("fintraffic");
    expect(ticks().ticked("ships")).toBe(true);
    ticks().setTicked("ships", false);
    await wrapper.find("#set-map-ships").setValue("none");
    expect(ticks().ticked("ships")).toBe(false);
  });

  it("switches the layer on again when the source is changed to another", async () => {
    const { wrapper } = make({ "map/aircraft": "adsblol" }, [
      mapLayer("aircraft", { source: "adsblol" }),
      mapLayer("ships"),
    ]);
    expect(ticks().ticked("aircraft")).toBe(false);
    await wrapper.find("#set-map-aircraft").setValue("adsbfi");
    expect(ticks().ticked("aircraft")).toBe(true);
  });

  it("does not switch the layer on where the source was chosen in another browser", async () => {
    const { daemon } = make();
    await tell(daemon, { config: configValues({ "map/aircraft": "adsbfi" }) });
    expect(ticks().ticked("aircraft")).toBe(false);
    expect(localStorage.getItem("NeoAPRS.layer.aircraft")).toBeNull();
  });

  describe("the AISStream key", () => {
    const MASK = "********";
    const keyRow = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper.find("#set-map-ships_key").element.closest<HTMLElement>(".field");

    it("keeps the key's room while another source is chosen, so nothing moves when AISStream is chosen", async () => {
      const { wrapper } = make();
      const row = keyRow(wrapper);
      expect(row?.classList.contains("field-room")).toBe(true);
      expect(row?.hasAttribute("inert")).toBe(true);
      await wrapper.find("#set-map-ships").setValue("aisstream");
      expect(keyRow(wrapper)).toBe(row);
      expect(row?.classList.contains("field-room")).toBe(false);
      expect(row?.hasAttribute("inert")).toBe(false);
    });

    it("has a masked field, a link to the page where a key is made, opened in a new tab, and an (i) of one line", async () => {
      const { wrapper } = make({ "map/ships": "aisstream", "map/ships_key": MASK }, [
        mapLayer("aircraft"),
        mapLayer("ships", { source: "aisstream" }),
      ]);
      const input = wrapper.find<HTMLInputElement>("#set-map-ships_key");
      expect(input.attributes("type")).toBe("password");
      expect(input.element.value).toBe(MASK);
      expect(wrapper.find('label[for="set-map-ships_key"]').text()).toBe("Key");
      const link = keyRow(wrapper)?.querySelector("a.field-link");
      expect(link?.textContent).toBe("Get a key");
      expect(link?.getAttribute("href")).toBe(AISSTREAM_KEY_URL);
      expect(link?.getAttribute("target")).toBe("_blank");
      expect(link?.getAttribute("rel")).toContain("noopener");
      keyRow(wrapper)?.querySelector<HTMLElement>(".info-toggle")?.click();
      await wrapper.vm.$nextTick();
      expect([...(keyRow(wrapper)?.querySelectorAll(".info-line") ?? [])].map((l) => l.textContent)).toEqual([
        "The key is your own, and AISStream gives it for free.",
      ]);
      expect(keyRow(wrapper)?.querySelector(".info-toggle")?.hasAttribute("title")).toBe(false);
    });

    it("saves a typed key when the field is left", async () => {
      const { wrapper, send } = make({ "map/ships": "aisstream" }, [
        mapLayer("aircraft"),
        mapLayer("ships", { source: "aisstream" }),
      ]);
      await wrapper.find("#set-map-ships_key").setValue("0123456789abcdef0123456789abcdef01234567");
      await wrapper.find("#set-map-ships_key").trigger("blur");
      expect(send).toHaveBeenLastCalledWith({
        cmd: "set_config",
        values: { "map/ships_key": "0123456789abcdef0123456789abcdef01234567" },
      });
    });

    it("says under the field that AISStream did not accept the key", () => {
      const { wrapper } = make({ "map/ships": "aisstream", "map/ships_key": MASK }, [
        mapLayer("aircraft"),
        mapLayer("ships", { source: "aisstream", problem: "key_refused" }),
      ]);
      expect(keyRow(wrapper)?.querySelector(".field-error")?.textContent).toBe("AISStream did not accept this key.");
    });

    it("gives the key's place to the receiver's address while My own receiver is chosen", () => {
      const { wrapper } = make({ "map/ships": "receiver" }, [
        mapLayer("aircraft"),
        mapLayer("ships", { source: "receiver" }),
      ]);
      expect(wrapper.find("#set-map-ships_key").exists()).toBe(false);
      expect(wrapper.find("#set-map-ships_host").exists()).toBe(true);
    });
  });
});
