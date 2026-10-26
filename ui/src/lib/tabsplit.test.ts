import { describe, expect, it } from "vitest";
import { TAB_IDS, type TabId } from "@/lib/layout";
import { splitTabs, type TabSizes } from "@/lib/tabsplit";

// The widths of the tabs, made up: 580 px in all, the More button 50 px and 24 px more with a count on it.
const tabs: Record<TabId, number> = { messages: 80, stations: 70, nearby: 60, email: 50, bulletins: 70, objects: 60, beacon: 60, packets: 60, settings: 70 };
const sizes: TabSizes = { tabs, more: 50, moreCount: 24 };
const split = (room: number, open: TabId = "messages", counts: Partial<Record<TabId, number>> = {}) => splitTabs(sizes, room, open, counts);

describe("which tabs stay in the row", () => {
  it("keeps all of them, and no More, when they fit, to the pixel", () => {
    expect(split(580)).toEqual({ shown: [...TAB_IDS], hidden: [] });
    expect(split(2000).hidden).toEqual([]);
  });

  it("keeps the first ones that fit with the More button, in the order of the tabs, when they do not", () => {
    expect(split(579)).toEqual({ shown: TAB_IDS.slice(0, 8), hidden: ["settings"] }); // 510 + the More button of 50 is 560
    expect(split(400)).toEqual({ shown: TAB_IDS.slice(0, 5), hidden: ["objects", "beacon", "packets", "settings"] });
    expect(split(160)).toEqual({ shown: ["messages"], hidden: TAB_IDS.slice(1) });
  });

  it("never fills the room with a later tab past one that did not fit: the order is the importance", () => {
    const narrow = splitTabs({ tabs: { ...tabs, stations: 300 }, more: 50, moreCount: 24 }, 400, "messages", {});
    expect(narrow.shown).toEqual(["messages"]);
  });

  it("has the tab on show in the row: it takes the place of the last one that fits, the others keep their order", () => {
    expect(split(400, "settings")).toEqual({
      shown: ["messages", "stations", "nearby", "email", "settings"],
      hidden: ["bulletins", "objects", "beacon", "packets"],
    });
    expect(split(400, "packets").shown).toEqual(["messages", "stations", "nearby", "email", "packets"]);
    expect(split(400, "email").shown).toEqual(TAB_IDS.slice(0, 5)); // already there: nothing moves
  });

  it("drops as many of the last ones as the tab on show needs room for", () => {
    const wide = splitTabs({ tabs: { ...tabs, settings: 200 }, more: 50, moreCount: 24 }, 400, "settings", {});
    expect(wide.shown).toEqual(["messages", "stations", "settings"]); // 350 of room: the bulletins, the email and the nearby go (330, 260 and 210 with the settings added are too much), 80 + 70 + 200 is just right
  });

  it("keeps the tab on show even when nothing else fits", () => {
    expect(split(100, "settings")).toEqual({ shown: ["settings"], hidden: TAB_IDS.slice(0, 8) });
    expect(split(0, "messages").shown).toEqual(["messages"]);
  });

  it("keeps room for the count on the More button once a tab under it has one", () => {
    const counts = { email: 1, bulletins: 2 };
    expect(split(320, "messages", {}).shown).toEqual(["messages", "stations", "nearby", "email"]); // 260 + 50
    expect(split(320, "messages", counts).shown).toEqual(["messages", "stations", "nearby"]); // 260 + 74 is too much
    expect(split(400, "messages", counts).shown).toEqual(TAB_IDS.slice(0, 5)); // what is under it has no count: no room kept
  });

  it("does not keep room for a count of zero", () => {
    expect(split(320, "messages", { email: 0, bulletins: 0 }).shown).toEqual(["messages", "stations", "nearby", "email"]);
  });

  it("gives every width the same answer when asked twice", () => {
    for (let room = 0; room <= 640; room += 7) {
      for (const open of TAB_IDS) {
        const answer = split(room, open, { messages: 2 });
        expect(answer).toEqual(split(room, open, { messages: 2 }));
        expect(answer.shown).toContain(open);
        expect([...answer.shown, ...answer.hidden].sort()).toEqual([...TAB_IDS].sort());
      }
    }
  });
});
