// Esc in the Objects tab. A page of an earlier test would take the key too (its listeners are on the document), so the pages are unmounted after each test, in a file of their own.
import "@/test/mockmap";
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { FakeMap } from "@/test/fakemap";
import { type FakeSocket } from "@/test/fakesocket";
import { configValues, ownObject } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();
enableAutoUnmount(afterEach);

const sent = (socket: ReturnType<typeof FakeSocket.last>, cmd: string) => socket.sent.filter((c) => (c as { cmd?: string }).cmd === cmd);
const field = (wrapper: VueWrapper, label: string) =>
  wrapper
    .findAll("#pane-objects .field:not(.location-field)")
    .find((f) => f.find("label").text() === label)
    ?.find<HTMLInputElement>("input");
const sayObjects = async (socket: ReturnType<typeof FakeSocket.last>) => {
  socket.say({ type: "state", topic: "own_objects", rev: 0, value: { LEADER: ownObject("LEADER", { comment: "Rescue 1" }) } });
  await flushPromises();
};
const esc = async (target: Element | Document = document.body) => {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  await flushPromises();
};
const name = (wrapper: VueWrapper) => field(wrapper, "Name");
const opened = async () => {
  const harness = await open();
  await tabButton(harness.wrapper, "Objects")?.trigger("click");
  return harness;
};

describe("App: Esc in the Objects form", () => {
  it("clears what was typed in the form without saving, as Cancel does, and then leaves the Esc to the cards", async () => {
    const { wrapper, socket } = await opened();
    await name(wrapper)?.setValue("MARK");
    await esc();
    expect(name(wrapper)?.element.value).toBe("");
    expect(sent(socket, "object_set")).toEqual([]);
    await esc(); // (nothing is held: nothing happens)
    expect(name(wrapper)?.element.value).toBe("");
  });

  it("leaves the selected object and clears the form, and the object stays as it was", async () => {
    const { wrapper, socket } = await open();
    await sayObjects(socket);
    await tabButton(wrapper, "Objects")?.trigger("click");
    await wrapper.find("#pane-objects .ownobject").trigger("click");
    await field(wrapper, "Comment")?.setValue("Changed");
    expect(wrapper.find("#pane-objects .ownobject").classes()).toContain("selected");
    await esc();
    expect(wrapper.find("#pane-objects .ownobject").classes()).not.toContain("selected");
    expect(name(wrapper)?.element.value).toBe("");
    expect(wrapper.find("#pane-objects button[type='submit']").text()).toBe("Add");
    expect(sent(socket, "object_set")).toEqual([]);
    expect(wrapper.find("#pane-objects .ownobject .bulletin-text").text()).toBe("Rescue 1");
  });

  it("clears the whole form with the Esc of a field of the form too, the text in it or not: nothing of the form's own is left to it", async () => {
    const { wrapper } = await opened();
    await name(wrapper)?.setValue("MARK");
    const comment = field(wrapper, "Comment");
    await comment?.setValue("Rescue 1");
    await field(wrapper, "Speed")?.setValue("40");
    await esc(comment?.element);
    expect(name(wrapper)?.element.value).toBe("");
    expect(field(wrapper, "Comment")?.element.value).toBe("");
    expect(field(wrapper, "Speed")?.element.value).toBe("");
    expect(wrapper.find("#pane-objects .location-place").text()).toBe("Not set");
  });

  it("moves the map to a place that is typed, and not for the form that Esc clears", async () => {
    const { wrapper } = await opened();
    const map = FakeMap.last();
    await wrapper.find("#pane-objects .location-place").trigger("click");
    const entry = (label: string) =>
      wrapper
        .findAll("#pane-objects .location-entry .field")
        .find((f) => f.find("label").text() === label)
        ?.find<HTMLInputElement>("input");
    await entry("Latitude")?.setValue("61");
    await entry("Longitude")?.setValue("26");
    await flushPromises();
    expect(map.flights).toHaveLength(1);
    await esc();
    expect(wrapper.find("#pane-objects .location-place").text()).toBe("Not set");
    expect(map.flights).toHaveLength(1);
  });

  it("closes the note of an (i) of the form first and leaves what was typed, and the next Esc clears the form", async () => {
    const { wrapper } = await opened();
    await name(wrapper)?.setValue("MARK");
    const tip = wrapper.find<HTMLButtonElement>("#pane-objects .objform .info-toggle");
    await tip.trigger("click");
    expect(wrapper.find("#pane-objects .info-text").exists()).toBe(true);
    await esc(tip.element);
    expect(wrapper.find("#pane-objects .info-text").exists()).toBe(false);
    expect(name(wrapper)?.element.value).toBe("MARK");
    await esc(tip.element);
    expect(name(wrapper)?.element.value).toBe("");
  });

  it("leaves a field outside the form its first Esc", async () => {
    const { wrapper } = await opened();
    await name(wrapper)?.setValue("MARK");
    const outside = document.createElement("input");
    outside.value = "text";
    document.body.append(outside);
    await esc(outside);
    expect(name(wrapper)?.element.value).toBe("MARK");
    outside.remove();
  });

  it("ends the choice on the map first, and then clears the form", async () => {
    const { wrapper } = await opened();
    await name(wrapper)?.setValue("MARK");
    await wrapper.find("#pane-objects .location-pick").trigger("click");
    expect(wrapper.find("#pane-objects .location-pick").text()).toBe("Cancel");
    await esc();
    expect(name(wrapper)?.element.value).toBe("MARK");
    expect(wrapper.find("#pane-objects .location-pick").text()).toBe("Choose on map");
    FakeMap.last().fire("click", { lngLat: { lat: 59.5, lng: 24.5 } }); // (the map no longer waits for a place)
    await flushPromises();
    expect(wrapper.find("#pane-objects .location-place").text()).toBe("Not set");
    await esc();
    expect(name(wrapper)?.element.value).toBe("");
  });

  it("does not touch a form that is not in sight, and leaves the Esc to the first-run guide while it is open", async () => {
    const { wrapper, socket } = await opened();
    await name(wrapper)?.setValue("MARK");
    await tabButton(wrapper, "Messages")?.trigger("click");
    await esc();
    await tabButton(wrapper, "Objects")?.trigger("click");
    expect(name(wrapper)?.element.value).toBe("MARK");
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "station/call": "" }) });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(true);
    await esc();
    expect(wrapper.find(".setup").exists()).toBe(false);
    expect(name(wrapper)?.element.value).toBe("MARK");
  });

  it("ends the choice of the My station tab's place too", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "My station")?.trigger("click");
    const pick = () => wrapper.find("#pane-beacon .location-pick");
    await pick().trigger("click");
    expect(pick().text()).toBe("Cancel");
    await esc();
    expect(pick().text()).toBe("Choose on map");
  });
});
