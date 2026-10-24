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
    .findAll("#pane-objects .field")
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
const formOf = (wrapper: VueWrapper) => wrapper.find("#pane-objects form.composebar");
const opened = async () => {
  const harness = await open();
  await tabButton(harness.wrapper, "Objects")?.trigger("click");
  await harness.wrapper.find("#pane-objects .toolbar .btn").trigger("click");
  return harness;
};

describe("App: Esc in the Objects form", () => {
  it("closes a new form without saving, as Cancel does", async () => {
    const { wrapper, socket } = await opened();
    await field(wrapper, "Name")?.setValue("");
    expect(formOf(wrapper).exists()).toBe(true);
    await esc();
    expect(formOf(wrapper).exists()).toBe(false);
    expect(sent(socket, "object_set")).toEqual([]);
    await esc(); // (nothing is open: nothing happens)
    expect(formOf(wrapper).exists()).toBe(false);
  });

  it("closes the form of an object that is being changed, and the object stays as it was", async () => {
    const { wrapper, socket } = await open();
    await sayObjects(socket);
    await tabButton(wrapper, "Objects")?.trigger("click");
    await wrapper.find("#pane-objects .object-edit").trigger("click");
    await field(wrapper, "Comment")?.setValue("Changed");
    expect(formOf(wrapper).exists()).toBe(true);
    await esc();
    expect(formOf(wrapper).exists()).toBe(false);
    expect(sent(socket, "object_set")).toEqual([]);
    expect(wrapper.find("#pane-objects .ownobject .bulletin-text").text()).toBe("Rescue 1");
  });

  it("leaves a field that has text its first Esc, and closes the form with the next one from an empty field", async () => {
    const { wrapper } = await opened();
    const comment = field(wrapper, "Comment");
    await comment?.setValue("Rescue 1");
    await esc(comment?.element);
    expect(formOf(wrapper).exists()).toBe(true);
    await comment?.setValue("");
    await esc(comment?.element);
    expect(formOf(wrapper).exists()).toBe(false);
  });

  it("ends the choice on the map first, and then the form", async () => {
    const { wrapper } = await opened();
    await wrapper.find("#pane-objects .location-pick").trigger("click");
    expect(wrapper.find("#pane-objects .location-pick").text()).toBe("Cancel");
    await esc();
    expect(formOf(wrapper).exists()).toBe(true);
    expect(wrapper.find("#pane-objects .location-pick").text()).toBe("Choose on map");
    FakeMap.last().fire("click", { lngLat: { lat: 59.5, lng: 24.5 } }); // (the map no longer waits for a place)
    await flushPromises();
    expect(field(wrapper, "Latitude")?.element.value).toBe("60.17");
    await esc();
    expect(formOf(wrapper).exists()).toBe(false);
  });

  it("does not touch a form that is not in sight, and leaves the Esc to the first-run guide while it is open", async () => {
    const { wrapper, socket } = await opened();
    await tabButton(wrapper, "Messages")?.trigger("click");
    await esc();
    await tabButton(wrapper, "Objects")?.trigger("click");
    expect(formOf(wrapper).exists()).toBe(true);
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "station/call": "" }) });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(true);
    await esc();
    expect(wrapper.find(".setup").exists()).toBe(false);
    expect(formOf(wrapper).exists()).toBe(true);
  });

  it("ends the choice of the Beacon tab's place too", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    const pick = () => wrapper.find("#pane-beacon .location-pick");
    await pick().trigger("click");
    expect(pick().text()).toBe("Cancel");
    await esc();
    expect(pick().text()).toBe("Choose on map");
  });
});
