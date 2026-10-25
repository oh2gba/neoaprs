import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { FakeMap, FakeMarker } from "@/test/fakemap";
import { type FakeSocket } from "@/test/fakesocket";
import { configValues, errorOf, ownObject, station } from "@/test/fixtures";
import { open, stations, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the Objects tab", () => {
  describe("the Objects tab", () => {
    const mine = { LEADER: ownObject("LEADER", { comment: "Rescue 1" }) };
    const ours = {
      ...stations,
      LEADER: station("LEADER", {
        kind: "object",
        own: true,
        reported_by: "OH2GBA",
        lat: 60.3,
        lon: 25.0,
        symbol_name: "Car",
        distance_km: 15,
        bearing_deg: 10,
      }),
    };
    const sayObjects = async (socket: ReturnType<typeof FakeSocket.last>) => {
      socket.say({ type: "state", topic: "stations", rev: 1, value: ours });
      socket.say({ type: "state", topic: "own_objects", rev: 0, value: mine });
      await flushPromises();
    };
    const sent = (socket: ReturnType<typeof FakeSocket.last>, cmd: string) => socket.sent.filter((c) => (c as { cmd?: string }).cmd === cmd);
    const field = (wrapper: VueWrapper, label: string) =>
      wrapper
        .findAll("#pane-objects .field")
        .find((f) => f.find("label").text() === label)
        ?.find<HTMLInputElement>("input");
    const button = (wrapper: VueWrapper, text: string) => wrapper.findAll("#pane-objects button").find((b) => b.text() === text);

    it("comes after Bulletins and lists our objects", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      await tabButton(wrapper, "Objects")?.trigger("click");
      expect(wrapper.findAll("#pane-objects .ownobject")).toHaveLength(1);
      expect(wrapper.find("#pane-objects .ownobject strong").text()).toBe("LEADER");
    });

    it("makes an object from the form with one command, at the place we are unless a click on the map says another", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.17");
      await field(wrapper, "Name")?.setValue("MARK");
      await button(wrapper, "Choose on map")?.trigger("click");
      FakeMap.last().fire("click", { lngLat: { lat: 60.5, lng: 25.5 } });
      await flushPromises();
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.5");
      expect(field(wrapper, "Longitude")?.element.value).toBe("25.5");
      await wrapper.find("#pane-objects form").trigger("submit");
      expect(sent(socket, "object_set")).toEqual([
        {
          cmd: "object_set",
          name: "MARK",
          kind: "object",
          lat: 60.5,
          lon: 25.5,
          symbol_table: "/",
          symbol_code: ">",
          comment: "",
          course_deg: null,
          speed_kmh: null,
          path: null,
          qru_group: "",
          on_request: false,
        },
      ]);
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(true);
      expect(field(wrapper, "Name")?.element.value).toBe("MARK");
      socket.say({ type: "state", topic: "own_objects", rev: 0, value: { MARK: ownObject("MARK", { lat: 60.5, lon: 25.5 }) } });
      await flushPromises();
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(false);
    });

    it("keeps the form and what was typed when the daemon refuses the object, and shows its error", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      await field(wrapper, "Name")?.setValue("MARK");
      await field(wrapper, "Comment")?.setValue("kept");
      await wrapper.find("#pane-objects form").trigger("submit");
      socket.say(errorOf("object_set: set your call first"));
      await flushPromises();
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(true);
      expect(field(wrapper, "Comment")?.element.value).toBe("kept");
      expect(wrapper.find(".toast").text()).toContain("set your call first");
    });

    it("shows a pin on the map while the form has a place, and a click on the map is not the first-run guide's", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      const pins = () => FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"));
      expect(pins()).toHaveLength(0);
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      expect(pins()).toHaveLength(1);
      expect(pins()[0]?.lngLat).toEqual([24.94, 60.17]);
      await button(wrapper, "Cancel")?.trigger("click");
      expect(pins()).toHaveLength(0);
      expect(wrapper.find(".setup").exists()).toBe(false);
      expect(sent(socket, "set_config")).toEqual([]);
    });

    it("kills an object after two presses of its x, with one command", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      await tabButton(wrapper, "Objects")?.trigger("click");
      const x = () => wrapper.find("#pane-objects .ownobject .bulletin-delete");
      await x().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([]);
      await x().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([{ cmd: "object_kill", name: "LEADER" }]);
    });

    it("changes an object from its card on the map: Edit opens the Objects tab with it, and Save sends the change", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      const marker = FakeMarker.live().find((m) => m.element.textContent === "LEADER");
      expect(marker?.draggable).toBe(true);
      marker?.element.click();
      await flushPromises();
      expect(wrapper.find(".card .card-call").text()).toContain("LEADER");
      await wrapper.find(".card .card-foot .primary").trigger("click");
      expect(tabButton(wrapper, "Objects")?.attributes("aria-selected")).toBe("true");
      expect(wrapper.find<HTMLInputElement>("#pane-objects .objform input[maxlength='9']").element.value).toBe("LEADER");
      await field(wrapper, "Comment")?.setValue("Moved on");
      await wrapper.find("#pane-objects form").trigger("submit");
      expect(sent(socket, "object_set")).toMatchObject([{ name: "LEADER", comment: "Moved on", lat: 60.2, lon: 24.9 }]);
    });

    it("kills an object from its card, which asks twice", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      FakeMarker.live()
        .find((m) => m.element.textContent === "LEADER")
        ?.element.click();
      await flushPromises();
      const kill = () => wrapper.find(".card .card-foot .forget");
      await kill().trigger("click");
      expect(kill().text()).toBe("Really kill?");
      await kill().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([{ cmd: "object_kill", name: "LEADER" }]);
      expect(sent(socket, "forget_station")).toEqual([]);
    });

    it("moves an object where its marker is dropped, with one command that keeps the rest of it", async () => {
      const { socket } = await open();
      await sayObjects(socket);
      FakeMarker.live()
        .find((m) => m.element.textContent === "LEADER")
        ?.dragTo(60.8, 25.9);
      await flushPromises();
      expect(sent(socket, "object_set")).toEqual([
        {
          cmd: "object_set",
          name: "LEADER",
          kind: "object",
          lat: 60.8,
          lon: 25.9,
          symbol_table: "/",
          symbol_code: ">",
          comment: "Rescue 1",
          course_deg: null,
          speed_kmh: null,
          path: null,
          qru_group: "",
          on_request: false,
        },
      ]);
    });

    it("lets the first-run guide have the click of the map while it picks a position", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "station/call": "" }) });
      await flushPromises();
      await wrapper.find("#setup-call").setValue("oh2abc");
      await wrapper.find(".setup form").trigger("submit");
      expect(wrapper.find("#setup-lat").exists()).toBe(true);
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      await button(wrapper, "Choose on map")?.trigger("click");
      FakeMap.last().fire("click", { lngLat: { lat: 59.5, lng: 24.5 } });
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#setup-lat").element.value).toBe("59.5");
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.17");
    });
  });
});
