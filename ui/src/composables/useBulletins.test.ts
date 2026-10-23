import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, shallowReactive } from "vue";
import { useBulletins } from "@/composables/useBulletins";
import { usePanel } from "@/composables/usePanel";
import type { BulletinRow } from "@/protocol/protocol";
import { ago, bulletin } from "@/test/fixtures";

const board = (...rows: BulletinRow[]) => shallowReactive(new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r])));

/** The composable inside a component, with the panel as `usePanel` makes it; `show` is the tab in front before it is made. */
function setUp(bulletins: Map<string, BulletinRow>, show?: "bulletins" | "stations", collapsed = false) {
  let made: { panel: ReturnType<typeof usePanel>; fresh: ReturnType<typeof useBulletins>["fresh"] } | undefined;
  mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        if (show) panel.show(show);
        panel.collapsed.value = collapsed;
        made = { panel, fresh: useBulletins(bulletins, panel).fresh };
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return made;
}

beforeEach(() => localStorage.clear());

describe("useBulletins", () => {
  it("counts every bulletin as new until the tab has been on show, and none after", async () => {
    const { panel, fresh } = setUp(board(bulletin("BLN1", { first_heard: ago(600) }), bulletin("BLN2", { first_heard: ago(300) })), "stations");
    expect(fresh.value).toBe(2);
    panel.show("bulletins");
    await nextTick();
    expect(fresh.value).toBe(0);
    expect(localStorage.getItem("NeoAPRS.bulletinsseen")).toBe(String(Date.parse(ago(300))));
  });

  it("counts a bulletin that comes while another tab is on show, and not one that comes while the board is looked at", async () => {
    const bulletins = board(bulletin("BLN1", { first_heard: ago(600) }));
    const { panel, fresh } = setUp(bulletins, "bulletins");
    expect(fresh.value).toBe(0);
    bulletins.set("OH2XYZ/BLN2", bulletin("BLN2", { first_heard: ago(100) }));
    await nextTick();
    expect(fresh.value).toBe(0);
    panel.show("stations");
    bulletins.set("OH2XYZ/BLN3", bulletin("BLN3", { first_heard: ago(50) }));
    await nextTick();
    expect(fresh.value).toBe(1);
    bulletins.set("OH2XYZ/BLN4", bulletin("BLN4", { first_heard: ago(20) }));
    await nextTick();
    expect(fresh.value).toBe(2);
    panel.show("bulletins");
    await nextTick();
    expect(fresh.value).toBe(0);
  });

  it("counts a bulletin whose sender changed the text, which is first heard again", async () => {
    const bulletins = board(bulletin("BLN1", { first_heard: ago(600) }));
    const { panel, fresh } = setUp(bulletins, "bulletins");
    panel.show("packets");
    bulletins.set("OH2XYZ/BLN1", bulletin("BLN1", { first_heard: ago(5), text: "changed" }));
    await nextTick();
    expect(fresh.value).toBe(1);
  });

  it("does not take them as seen while the panel is folded away, though the Bulletins tab is the tab", async () => {
    const bulletins = board();
    const { fresh } = setUp(bulletins, "bulletins", true);
    bulletins.set("OH2XYZ/BLN1", bulletin("BLN1"));
    await nextTick();
    expect(fresh.value).toBe(1);
  });

  it("remembers what was seen across page loads", async () => {
    setUp(board(bulletin("BLN1", { first_heard: ago(600) })), "bulletins");
    await nextTick();
    const again = setUp(board(bulletin("BLN1", { first_heard: ago(600) }), bulletin("BLN2", { first_heard: ago(10) })), "stations");
    expect(again.fresh.value).toBe(1);
  });
});
