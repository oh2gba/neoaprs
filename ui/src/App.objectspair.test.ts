import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { type FakeSocket } from "@/test/fakesocket";
import { ownObject } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: two objects", () => {
  const field = (wrapper: VueWrapper, label: string) =>
    wrapper
      .findAll("#pane-objects .field")
      .find((f) => f.find("label").text() === label)
      ?.find<HTMLInputElement>("input");
  const sentSets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd?: string }).cmd === "object_set") as { name: string }[];

  it("makes a second object while the first stays, as the daemon tells it in patches", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "own_objects", rev: 0, value: {} });
    await tabButton(wrapper, "Objects")?.trigger("click");
    await field(wrapper, "Name")?.setValue("ALPHA");
    await wrapper.find("#pane-objects form").trigger("submit");
    socket.say({
      type: "patch",
      topic: "own_objects",
      rev: 1,
      ops: [{ op: "set", key: "ALPHA", value: ownObject("ALPHA", { lat: 60.17, lon: 24.94, sent: 0, last_sent_at: null }) }],
    });
    await flushPromises();
    expect(field(wrapper, "Name")?.element.value).toBe("");
    await field(wrapper, "Name")?.setValue("BRAVO");
    await wrapper.find("#pane-objects form").trigger("submit");
    expect(sentSets(socket).map((c) => c.name)).toEqual(["ALPHA", "BRAVO"]);
    socket.say({
      type: "patch",
      topic: "own_objects",
      rev: 2,
      ops: [{ op: "set", key: "BRAVO", value: ownObject("BRAVO", { lat: 60.17, lon: 24.94, sent: 0, last_sent_at: null }) }],
    });
    await flushPromises();
    expect(field(wrapper, "Name")?.element.value).toBe("");
    expect(wrapper.findAll("#pane-objects .ownobject strong").map((e) => e.text())).toEqual(["ALPHA", "BRAVO"]);
  });

  it("changes and kills one of two without touching the other, and shows both again after a reload", async () => {
    const { wrapper, socket } = await open();
    const both = { ALPHA: ownObject("ALPHA", { lat: 60.17, lon: 24.94 }), BRAVO: ownObject("BRAVO", { lat: 60.17, lon: 24.94 }) };
    socket.say({ type: "state", topic: "own_objects", rev: 0, value: both });
    await tabButton(wrapper, "Objects")?.trigger("click");
    await flushPromises();
    expect(wrapper.findAll("#pane-objects .ownobject strong").map((e) => e.text())).toEqual(["ALPHA", "BRAVO"]);
    await wrapper.findAll("#pane-objects .ownobject")[1]?.trigger("click");
    await field(wrapper, "Comment")?.setValue("changed");
    await wrapper.find("#pane-objects form").trigger("submit");
    expect(sentSets(socket).map((c) => c.name)).toEqual(["BRAVO"]);
    const kill = () => wrapper.findAll("#pane-objects .ownobject .bulletin-delete")[0];
    await kill()?.trigger("click");
    await kill()?.trigger("click");
    expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "object_kill")).toEqual([{ cmd: "object_kill", name: "ALPHA" }]);
    socket.say({ type: "patch", topic: "own_objects", rev: 1, ops: [{ op: "set", key: "ALPHA", value: ownObject("ALPHA", { state: "killing", sent: 0 }) }] });
    await flushPromises();
    expect(wrapper.findAll("#pane-objects .ownobject strong").map((e) => e.text())).toEqual(["ALPHA", "BRAVO"]);
    socket.say({ type: "state", topic: "own_objects", rev: 0, value: both }); // (a reload: the daemon tells the table whole)
    await flushPromises();
    expect(wrapper.findAll("#pane-objects .ownobject strong").map((e) => e.text())).toEqual(["ALPHA", "BRAVO"]);
  });
});
