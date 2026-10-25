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
  const tab = ref("objects");
  const view = useOwnObjects(table, home, send, { show, tab } as unknown as Panel);
  return { view, sent, show, home, table, tab };
}

describe("useOwnObjects", () => {
  it("has a form for a new object where we are from the start, which the map shows with a pin while the Objects tab is in front", () => {
    const { view, tab } = setUp();
    expect(view.editing).toBeNull();
    expect(view.dirty).toBe(false);
    expect(view.picking).toBe(false);
    expect(view.draft).toMatchObject({ name: "", lat: "60.17", lon: "24.94", symbol: "/>" });
    expect(view.pin).toEqual({ lat: 60.17, lon: 24.94 });
    tab.value = "stations";
    expect(view.pin).toBeNull();
  });

  it("has no place, and no pin, while we do not know where we are, and takes the place when it is told, until something is typed", async () => {
    const { view, home } = setUp();
    home.value = null;
    await nextTick();
    expect(view.draft).toMatchObject({ lat: "", lon: "" });
    expect(view.pin).toBeNull();
    home.value = { lat: 61, lon: 25 };
    await nextTick();
    expect(view.draft).toMatchObject({ lat: "61", lon: "25" });
    view.draft.name = "MINE";
    home.value = { lat: 62, lon: 26 };
    await nextTick();
    expect(view.draft).toMatchObject({ name: "MINE", lat: "61", lon: "25" });
  });

  it("is dirty once something is typed, and Cancel clears it, with nothing of the last draft left", () => {
    const { view } = setUp();
    view.draft.name = "OLD";
    view.draft.comment = "typed";
    expect(view.dirty).toBe(true);
    view.cancel();
    expect(view.dirty).toBe(false);
    expect(view.draft).toMatchObject({ name: "", comment: "", lat: "60.17", lon: "24.94" });
  });

  it("selects an object: the form has what the daemon has of it and the Objects tab is put in front", () => {
    const { view, show } = setUp([ownObject("LEADER", { comment: "Rescue 1", course_deg: 88, speed_kmh: 40, path: "WIDE2-1" })]);
    view.edit("LEADER");
    expect(show).toHaveBeenCalledWith("objects");
    expect(view.editing).toBe("LEADER");
    expect(view.dirty).toBe(true);
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1", course: "88", speed: "40", path: "WIDE2-1", lat: "60.2", lon: "24.9" });
  });

  it("leaves the selection and clears the form on Cancel", () => {
    const { view } = setUp([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    view.cancel();
    expect(view.editing).toBeNull();
    expect(view.dirty).toBe(false);
    expect(view.draft).toMatchObject({ name: "", comment: "", lat: "60.17" });
  });

  it("does nothing for an object it does not have", () => {
    const { view, show } = setUp();
    view.edit("NOBODY");
    expect(view.editing).toBeNull();
    expect(show).not.toHaveBeenCalled();
  });

  it("lets go of the selected object when it is gone (killed, forgotten)", async () => {
    const { view, table } = setUp([ownObject("LEADER")]);
    view.edit("LEADER");
    table.delete("LEADER");
    await nextTick();
    expect(view.editing).toBeNull();
    expect(view.draft.name).toBe("");
  });

  it("picks the place on the map only while Choose on map is on, and a click sets it, to five decimals, and ends the picking", () => {
    const { view } = setUp();
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
    view.place(10, 190);
    expect(view.draft.lon).toBe("-170");
  });

  it("gives up the place it asked of the map when it is cancelled", () => {
    const { view } = setUp();
    view.togglePlacing();
    expect(view.picking).toBe(true);
    view.cancel();
    expect(view.picking).toBe(false);
  });

  it("has no pin while the position typed is not a position", () => {
    const { view } = setUp();
    view.draft.lat = "91";
    expect(view.pin).toBeNull();
    view.draft.lat = "x";
    expect(view.pin).toBeNull();
    view.draft.lat = "60";
    expect(view.pin).toEqual({ lat: 60, lon: 24.94 });
  });

  it("saves the object as the form has it, and keeps it as typed until the daemon has it", async () => {
    const { view, sent, table } = setUp();
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
        qru_group: "",
        on_request: false,
      },
    ]);
    expect(view.dirty).toBe(true);
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1", speed: "40" });
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 1", speed_kmh: 40 }));
    await nextTick();
    expect(view.dirty).toBe(false);
    expect(view.draft.name).toBe("");
  });

  it("keeps what was typed when the daemon refuses, for another try", async () => {
    const { view, sent, table } = setUp();
    view.draft.name = "LEADER";
    view.draft.comment = "Rescue 1";
    view.save();
    await nextTick();
    expect(view.dirty).toBe(true);
    expect(view.draft).toMatchObject({ name: "LEADER", comment: "Rescue 1" });
    view.draft.comment = "Rescue 2";
    view.save();
    expect(sent).toHaveLength(2);
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 1" }));
    await nextTick();
    expect(view.dirty).toBe(true);
    table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94, comment: "Rescue 2" }));
    await nextTick();
    expect(view.dirty).toBe(false);
  });

  it("clears the form at once when the object is there as the form has it, with nothing to send", () => {
    const { view, sent } = setUp([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    view.save();
    expect(sent).toEqual([]);
    expect(view.editing).toBeNull();
    expect(view.dirty).toBe(false);
  });

  it("waits for the change of an object that is there: a row that is not what was asked for does not clear the form", async () => {
    const { view, sent, table } = setUp([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    view.draft.comment = "Moved";
    view.save();
    expect(sent).toHaveLength(1);
    table.set("LEADER", ownObject("LEADER", { comment: "Rescue 1", sent: 5 }));
    await nextTick();
    expect(view.editing).toBe("LEADER");
    table.set("LEADER", ownObject("LEADER", { comment: "Moved" }));
    await nextTick();
    expect(view.editing).toBeNull();
  });

  it("does not clear a form that was cancelled and typed in again when the first object is confirmed", async () => {
    const { view, table } = setUp();
    view.draft.name = "ONE";
    view.save();
    view.cancel();
    view.draft.name = "TWO";
    table.set("ONE", ownObject("ONE", { lat: 60.17, lon: 24.94 }));
    await nextTick();
    expect(view.draft.name).toBe("TWO");
  });

  it("sends nothing for a draft that is not ready, and keeps what was typed when the command could not be sent", async () => {
    const { view, sent } = setUp();
    view.save();
    expect(sent).toEqual([]);
    const down = setUp([], false);
    down.view.draft.name = "LEADER";
    down.view.save();
    expect(down.sent).toHaveLength(1);
    expect(down.view.dirty).toBe(true);
    down.table.set("LEADER", ownObject("LEADER", { lat: 60.17, lon: 24.94 }));
    await nextTick();
    expect(down.view.dirty).toBe(true);
  });

  it("kills an object by its name, and lets go of it if it was the selected one", () => {
    const { view, sent } = setUp([ownObject("LEADER"), ownObject("OTHER")]);
    view.edit("LEADER");
    view.kill("OTHER");
    expect(view.editing).toBe("LEADER");
    view.kill("LEADER");
    expect(sent).toEqual([
      { cmd: "object_kill", name: "OTHER" },
      { cmd: "object_kill", name: "LEADER" },
    ]);
    expect(view.editing).toBeNull();
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
        qru_group: "",
        on_request: false,
      },
    ]);
    view.move("NOBODY", 1, 2);
    expect(sent).toHaveLength(1);
  });
});
