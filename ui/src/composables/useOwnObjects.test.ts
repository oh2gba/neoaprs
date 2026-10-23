import { describe, expect, it, vi } from "vitest";
import { nextTick, ref, shallowReactive } from "vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Command, OwnObjectRow } from "@/protocol/protocol";
import { ownObject } from "@/test/fixtures";

function setUp(rows: OwnObjectRow[] = [], sends = true) {
  const table = shallowReactive(new Map(rows.map((r) => [r.name, r])));
  const sent: Command[] = [];
  const send = vi.fn((command: Command) => {
    sent.push(command);
    return sends;
  });
  const show = vi.fn();
  const home = ref<{ lat: number; lon: number } | null>({ lat: 60.17, lon: 24.94 });
  const view = useOwnObjects(table, home, send, { show } as unknown as Panel);
  return { view, sent, show, home, table };
}

describe("useOwnObjects", () => {
  it("has the form closed, and nothing picked or pinned", () => {
    const { view } = setUp();
    expect(view.open).toBe(false);
    expect(view.picking).toBe(false);
    expect(view.pin).toBeNull();
    expect(view.editing).toBeNull();
  });

  it("opens the form for a new object where we are, which the map shows with a pin", () => {
    const { view, home } = setUp();
    view.start();
    expect(view.open).toBe(true);
    expect(view.editing).toBeNull();
    expect(view.draft).toMatchObject({ name: "", lat: "60.17", lon: "24.94", symbol: "/>" });
    expect(view.pin).toEqual({ lat: 60.17, lon: 24.94 });
    home.value = null;
    view.start();
    expect(view.draft).toMatchObject({ lat: "", lon: "" });
    expect(view.pin).toBeNull();
  });

  it("keeps nothing of the last draft when a new object is started", () => {
    const { view } = setUp();
    view.start();
    view.draft.name = "OLD";
    view.draft.comment = "typed";
    view.start();
    expect(view.draft).toMatchObject({ name: "", comment: "" });
  });

  it("opens the form with what the daemon has of an object and puts the Objects tab in front", () => {
    const { view, show } = setUp([ownObject("LEADER", { comment: "Rescue 1", course_deg: 88, speed_kmh: 40, path: "WIDE2-1" })]);
    view.edit("LEADER");
    expect(show).toHaveBeenCalledWith("objects");
    expect(view.open).toBe(true);
    expect(view.editing).toBe("LEADER");
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1", course: "88", speed: "40", path: "WIDE2-1", lat: "60.2", lon: "24.9" });
  });

  it("does nothing for an object it does not have", () => {
    const { view, show } = setUp();
    view.edit("NOBODY");
    expect(view.open).toBe(false);
    expect(show).not.toHaveBeenCalled();
  });

  it("picks the place on the map only while Place is on, and a click sets it, to five decimals, and ends the picking", () => {
    const { view } = setUp();
    view.start();
    expect(view.picking).toBe(false);
    view.togglePlacing();
    expect(view.picking).toBe(true);
    view.place(60.123456789, 24.987654321);
    expect(view.draft).toMatchObject({ lat: "60.12346", lon: "24.98765" });
    expect(view.picking).toBe(false);
    expect(view.pin).toEqual({ lat: 60.12346, lon: 24.98765 });
  });

  it("brings a longitude from a map that was wrapped round into -180 to 180", () => {
    const { view } = setUp();
    view.start();
    view.place(10, 190);
    expect(view.draft.lon).toBe("-170");
  });

  it("is not picking or pinning once the form is closed", () => {
    const { view } = setUp();
    view.start();
    view.togglePlacing();
    view.cancel();
    expect(view.open).toBe(false);
    expect(view.picking).toBe(false);
    expect(view.pin).toBeNull();
  });

  it("has no pin while the position typed is not a position", () => {
    const { view } = setUp();
    view.start();
    view.draft.lat = "91";
    expect(view.pin).toBeNull();
    view.draft.lat = "x";
    expect(view.pin).toBeNull();
    view.draft.lat = "60";
    expect(view.pin).toEqual({ lat: 60, lon: 24.94 });
  });

  it("saves the object as the form has it, and keeps the form open until the daemon has it", async () => {
    const { view, sent, table } = setUp();
    view.start();
    view.draft.name = "LEADER";
    view.draft.comment = "Rescue 1";
    view.draft.speed = "40";
    view.save();
    expect(sent).toEqual([
      {
        cmd: "object_set",
        name: "LEADER",
        kind: "object",
        lat: 60.17,
        lon: 24.94,
        symbol_table: "/",
        symbol_code: ">",
        comment: "Rescue 1",
        course_deg: null,
        speed_kmh: 40,
        path: null,
      },
    ]);
    expect(view.open).toBe(true);
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1", speed: "40" });
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 1", speed_kmh: 40 }));
    await nextTick();
    expect(view.open).toBe(false);
  });

  it("keeps the form open with what was typed when the daemon refuses, for another try", async () => {
    const { view, sent, table } = setUp();
    view.start();
    view.draft.name = "LEADER";
    view.draft.comment = "Rescue 1";
    view.save();
    await nextTick();
    expect(view.open).toBe(true);
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1" });
    view.draft.comment = "Rescue 2";
    view.save();
    expect(sent).toHaveLength(2);
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 1" }));
    await nextTick();
    expect(view.open).toBe(true);
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 2" }));
    await nextTick();
    expect(view.open).toBe(false);
  });

  it("closes a change at once when the object is there as the form has it, with nothing to send", () => {
    const { view, sent } = setUp([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    view.save();
    expect(sent).toEqual([]);
    expect(view.open).toBe(false);
  });

  it("waits for the change of an object that is there: a row that is not what was asked for does not close the form", async () => {
    const { view, sent, table } = setUp([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    view.draft.comment = "Moved";
    view.save();
    expect(sent).toHaveLength(1);
    table.set("LEADER", ownObject("LEADER", { comment: "Rescue 1", sent: 5 }));
    await nextTick();
    expect(view.open).toBe(true);
    table.set("LEADER", ownObject("LEADER", { comment: "Moved" }));
    await nextTick();
    expect(view.open).toBe(false);
  });

  it("does not close a form that was cancelled and opened for another object when the first one is confirmed", async () => {
    const { view, table } = setUp();
    view.start();
    view.draft.name = "ONE";
    view.save();
    view.start();
    view.draft.name = "TWO";
    table.set("ONE", ownObject("ONE", { lat: 60.17, lon: 24.94 }));
    await nextTick();
    expect(view.open).toBe(true);
  });

  it("sends nothing for a draft that is not ready, and keeps the form open when the command could not be sent", async () => {
    const { view, sent } = setUp();
    view.start();
    view.save();
    expect(sent).toEqual([]);
    expect(view.open).toBe(true);
    const down = setUp([], false);
    down.view.start();
    down.view.draft.name = "LEADER";
    down.view.save();
    expect(down.sent).toHaveLength(1);
    expect(down.view.open).toBe(true);
    down.table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94 }));
    await nextTick();
    expect(down.view.open).toBe(true);
  });

  it("kills an object by its name", () => {
    const { view, sent } = setUp([ownObject("LEADER")]);
    view.kill("LEADER");
    expect(sent).toEqual([{ cmd: "object_kill", name: "LEADER" }]);
  });

  it("moves an object to where its marker was dropped, everything else as it is", () => {
    const { view, sent } = setUp([ownObject("LEADER", { comment: "Rescue 1", course_deg: 88, speed_kmh: 40, path: "WIDE2-1" })]);
    view.move("LEADER", 60.5, 25.5);
    expect(sent).toEqual([
      {
        cmd: "object_set",
        name: "LEADER",
        kind: "object",
        lat: 60.5,
        lon: 25.5,
        symbol_table: "/",
        symbol_code: ">",
        comment: "Rescue 1",
        course_deg: 88,
        speed_kmh: 40,
        path: "WIDE2-1",
      },
    ]);
    view.move("NOBODY", 1, 2);
    expect(sent).toHaveLength(1);
  });
});
