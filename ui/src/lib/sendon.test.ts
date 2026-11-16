import { describe, expect, it } from "vitest";
import { draftTicks, inForce, radiosBlockedReason, radiosNamed, radiosPathless, ticked } from "@/lib/sendon";
import { pageRadios, type PageRadio, type RadioId } from "@/lib/radios";
import { radioRow, radiosTopic } from "@/test/fixtures";

const radios = (...rows: Parameters<typeof radiosTopic>): PageRadio[] => pageRadios(radiosTopic(...rows), null);
const [fm, hf, away] = radios(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "kiss", { name: "Mobile", state: "waiting" }));
const several = (): boolean => true;
const alone = (): boolean => false;

describe("what the panes that ask on the radios of a Send on share", () => {
  it("says why nothing may go: none of the radios is connected, a line for each of several, or there is none", () => {
    if (fm === undefined || hf === undefined || away === undefined) throw new Error("no radios");
    const waiting = { ...hf, connected: false };
    expect(radiosBlockedReason([fm, away], several, true)).toBeUndefined();
    expect(radiosBlockedReason([waiting, away], several, true)).toBe("Mercury: not connected\nMobile: not connected");
    expect(radiosBlockedReason([away], several, true)).toBe("Mobile: not connected");
    expect(radiosBlockedReason([away], alone, true)).toBe("The radio is not connected");
    expect(radiosBlockedReason([], alone, true)).toBe("there is no radio: add one, or turn one on");
    expect(radiosBlockedReason([], alone, false)).toBeUndefined(); // (before the daemon has told its radios)
  });

  it("names the radios something went on, those that are named and that the page has", () => {
    const all = [fm, hf, away].filter((radio) => radio !== undefined);
    const byId = (id: RadioId) => all.find((radio) => radio.id === id);
    expect(radiosNamed([1, 2], byId, several)).toBe("FM, Mercury");
    expect(radiosNamed([1, 9], byId, several)).toBe("FM");
    expect(radiosNamed([1, 2], byId, alone)).toBe("");
    expect(radiosNamed([], byId, several)).toBe("");
  });

  it("says why a path is greyed for radios that carry none, as Route does", () => {
    if (hf === undefined) throw new Error("no radio");
    expect(radiosPathless([hf])).toBe("Mercury: no path");
    expect(radiosPathless([hf, { ...hf, name: "40m" }])).toBe("Mercury, 40m: no path");
    expect(radiosPathless([])).toBeUndefined();
  });
});

describe("Send on bound to a draft (an object's, a bulletin's)", () => {
  it("has in force the radios of the set that are on, in the order of the boxes; the one radio that can send whatever the set says; none while none of the set is on", () => {
    expect(inForce([3, 1], [1, 2, 3])).toEqual([1, 3]);
    expect(inForce([1, 3], [1, 2])).toEqual([1]); // (radio 3 is off: kept, not in force)
    expect(inForce([3], [1, 2])).toEqual([]); // (ticked nowhere: no other radio stands for it)
    expect(inForce([3], [2])).toEqual([2]);
    expect(inForce([], [1, 2])).toEqual([]);
    expect(inForce([3], [])).toEqual([]);
  });

  it("takes a tick on or off, keeps a radio that is off beside the ticks, and starts from the tick alone when none of the set is on", () => {
    expect(ticked([1], [1, 2, 3], 3)).toEqual([1, 3]);
    expect(ticked([1, 3], [1, 2, 3], 1)).toEqual([3]);
    expect(ticked([1, 4], [1, 2], 2)).toEqual([1, 2, 4]); // (radio 4 is off and stays kept)
    expect(ticked([4], [1, 2], 2)).toEqual([2]); // (none of the set is on: the tick is its one radio)
    expect(ticked([2], [1, 2, 3], 3)).toEqual([2, 3]); // (a new one, as the one saved last, and a tick more)
  });

  it("ticks the radios of the set in force and greys the one left; with none in force none is ticked and none greyed", () => {
    if (fm === undefined || hf === undefined || away === undefined) throw new Error("no radios");
    const row = (own: RadioId[]) => draftTicks([fm, hf, away], own, "post").map((tick) => [tick.key, tick.name, tick.on, tick.last]);
    expect(row([1, 2])).toEqual([
      ["post/1", "FM", true, false],
      ["post/2", "Mercury", true, false],
      ["post/3", "Mobile", false, false],
    ]);
    expect(row([2]).map(([, , on, last]) => [on, last])).toEqual([
      [false, false],
      [true, true],
      [false, false],
    ]);
    expect(row([9]).map(([, , on, last]) => [on, last])).toEqual([
      [false, false],
      [false, false],
      [false, false],
    ]);
  });
});
