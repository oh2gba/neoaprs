import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import SkedsPane from "@/components/SkedsPane.vue";
import type { SkedRow, SkedsState } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { NOW, sked, skedsState } from "@/test/fixtures";

let daemon: FakeDaemon;
beforeEach(() => (daemon = fakeDaemon({ skeds: skedsState() })));
const sent = (cmd: string) => daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === cmd);
const at = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString().slice(0, 19) + "Z";

function pane(rows: SkedRow[] = [], extra: Partial<SkedsState> = {}) {
  daemon.skeds.value = skedsState(rows, extra);
  return mount(SkedsPane, { global: withDaemon(daemon), attachTo: document.body });
}
const rows = (wrapper: ReturnType<typeof pane>) => wrapper.findAll(".sked");

// The fixtures' time is Wednesday 21 October 2026, 12:00 UTC; a sked() starts in 2 hours and lasts 2.
describe("SkedsPane", () => {
  it("has an (i) at the top that says what a sked is, that the board is public and that it is not sent by radio", async () => {
    const wrapper = pane();
    const bar = wrapper.find(".tab-help");
    expect((wrapper.element as HTMLElement).firstElementChild).toBe(bar.element);
    await bar.find("button.info-toggle").trigger("click");
    expect(bar.find(".info-text").text()).toContain("A sked says when you will be on the air");
    expect(bar.find(".info-text").text()).toContain("The board is public");
    expect(bar.find(".info-text").text()).toContain("not sent by radio");
  });

  it("shows a row with the time in UTC, how long until it, the dial and the call; the viewer's own time is the title", () => {
    const wrapper = pane([sked("a", { call: "OH2XYZ" })]);
    const [row] = rows(wrapper);
    expect(row?.find(".sked-when strong").text()).toBe("Wed 21 Oct 14:00 to 16:00 UTC");
    expect(row?.find(".sked-when .muted").text()).toBe("in 2 h");
    expect(row?.find(".sked-when").attributes("title")).toMatch(/^Your time: Wed 21 Oct \d{2}:\d{2} to (\w{3} \d{1,2} \w{3} )?\d{2}:\d{2}$/);
    expect(row?.find(".sked-dial").text()).toBe("7.0541 MHz USB");
    expect(row?.findAll(".sked-call").map((c) => c.text())).toEqual(["OH2XYZ"]);
  });

  it("says now while a sked runs, and writes the end with its day when the sked runs over midnight", () => {
    const wrapper = pane([sked("run", { from: at(-1), to: at(1) }), sked("late", { from: "2026-10-21T22:00:00Z", to: "2026-10-22T02:00:00Z" })]);
    expect(rows(wrapper)[0]?.find(".sked-when .muted").text()).toBe("now");
    expect(rows(wrapper)[1]?.find(".sked-when strong").text()).toBe("Wed 21 Oct 22:00 to Thu 22 Oct 02:00 UTC");
  });

  it("lists the nearest first", () => {
    const wrapper = pane([
      sked("c", { call: "OH2CCC", from: at(30), to: at(31) }),
      sked("a", { call: "OH2AAA", from: at(2), to: at(3) }),
      sked("b", { call: "OH2BBB", from: at(5), to: at(6) }),
    ]);
    expect(wrapper.findAll(".sked-call").map((c) => c.text())).toEqual(["OH2AAA", "OH2BBB", "OH2CCC"]);
  });

  it("makes skeds with the same times and dial one row that lists the calls", () => {
    const wrapper = pane([sked("a", { call: "OH2AAA" }), sked("b", { call: "OH2BBB" }), sked("c", { call: "OH2CCC", dial: "14.1070 MHz USB" })]);
    expect(rows(wrapper)).toHaveLength(2);
    expect(
      rows(wrapper)[0]
        ?.findAll(".sked-call")
        .map((c) => c.text()),
    ).toEqual(["OH2CCC"]); // (14.1070 sorts before 7.0541)
    expect(
      rows(wrapper)[1]
        ?.findAll(".sked-call")
        .map((c) => c.text()),
    ).toEqual(["OH2AAA", "OH2BBB"]);
  });

  it("shows the note on one line with the whole note in the title, and as text, never as markup", () => {
    const wrapper = pane([sked("a", { note: "<b>Mercury</b>, 10 W & more" })]);
    const note = wrapper.find(".sked-note");
    expect(note.text()).toBe("<b>Mercury</b>, 10 W & more");
    expect(note.attributes("title")).toBe("<b>Mercury</b>, 10 W & more");
    expect(note.find("b").exists()).toBe(false);
    expect(
      pane([sked("a")])
        .find(".sked-note")
        .exists(),
    ).toBe(false);
  });

  it("leaves out a sked that has ended by the page's clock", async () => {
    const wrapper = pane([sked("a", { from: at(-3), to: at(-1) }), sked("b")]);
    expect(rows(wrapper)).toHaveLength(1);
    await tell(daemon, { now: NOW + 3 * 3_600_000 });
    expect(rows(wrapper)).toHaveLength(1);
    await tell(daemon, { now: NOW + 5 * 3_600_000 });
    expect(rows(wrapper)).toHaveLength(0);
  });

  describe("Delete and Join", () => {
    it("has Delete on a row with a sked of ours, which asks twice and then deletes that sked", async () => {
      const wrapper = pane([sked("mine", { call: "OH2GBA", ours: true }), sked("other", { call: "OH2XYZ", from: at(5), to: at(6) })]);
      const [ours, other] = rows(wrapper);
      expect(ours?.classes()).toContain("mine");
      expect(ours?.find(".sked-call .tag").text()).toBe("ours");
      expect(other?.find(".xbtn").exists()).toBe(false);
      const button = ours?.find(".xbtn");
      await button?.trigger("click");
      expect(sent("sked_delete")).toEqual([]);
      expect(button?.text()).toBe("sure?");
      await button?.trigger("click");
      expect(sent("sked_delete")).toEqual([{ cmd: "sked_delete", id: "mine" }]);
    });

    it("has Join on a row of others, which posts a sked of ours with the same times and dial and no note", async () => {
      const wrapper = pane([sked("a", { call: "OH2XYZ", note: "Mercury", dial: "14.1070 MHz USB" })]);
      const join = wrapper.find(".sked-actions .btn");
      expect(join.text()).toBe("Join");
      expect(join.attributes("aria-label")).toContain("OH2XYZ");
      await join.trigger("click");
      expect(sent("sked_post")).toEqual([{ cmd: "sked_post", from: at(2), to: at(4), dial: "14.1070 MHz USB", note: "" }]);
    });

    it("has no Join on a row that has our call already, and Delete only for the sked that is ours", () => {
      const wrapper = pane([sked("a", { call: "OH2GBA" }), sked("b", { call: "OH2GBA", from: at(5), to: at(6) })]);
      expect(wrapper.findAll(".sked-actions .btn")).toHaveLength(0);
      expect(wrapper.findAll(".sked-actions .xbtn")).toHaveLength(0);
    });

    it("has Delete, and not Join, on a row that lists ours among the others", async () => {
      const wrapper = pane([sked("a", { call: "OH2XYZ" }), sked("b", { call: "OH2GBA", ours: true })]);
      expect(wrapper.findAll(".sked-actions .btn")).toHaveLength(0);
      const button = wrapper.find(".sked-actions .xbtn");
      await button.trigger("click");
      await button.trigger("click");
      expect(sent("sked_delete")).toEqual([{ cmd: "sked_delete", id: "b" }]);
    });

    it("keeps Join but off while the board cannot be reached or there is no call, and hides it for a closed board", async () => {
      const join = (w: ReturnType<typeof pane>) => w.find(".sked-actions .btn");
      expect(join(pane([sked("a")])).attributes("disabled")).toBeUndefined();
      expect(join(pane([sked("a")], { state: "offline" })).attributes("disabled")).toBeDefined();
      expect(join(pane([sked("a")], { state: "off" })).attributes("disabled")).toBeDefined();
      expect(join(pane([sked("a")], { state: "closed" })).exists()).toBe(false);
      await tell(daemon, { call: null });
      expect(join(pane([sked("a")])).attributes("disabled")).toBeDefined();
      await tell(daemon, { call: "N0CALL" });
      expect(join(pane([sked("a")])).attributes("disabled")).toBeDefined();
    });

    it("has the column of Delete and Join in every row, whichever the row has, so that the rows keep their width", () => {
      const wrapper = pane([
        sked("a", { ours: true, call: "OH2GBA" }),
        sked("b", { from: at(5), to: at(6) }),
        sked("c", { call: "OH2GBA", from: at(7), to: at(8) }),
      ]);
      expect(wrapper.findAll(".sked .sked-actions")).toHaveLength(3);
    });
  });

  describe("the state of the board", () => {
    it("says the board is empty when it was read, and when it is closed", () => {
      expect(pane().find(".empty").text()).toBe("No skeds to come.");
      expect(pane([], { state: "closed" }).find(".empty").text()).toBe("No skeds to come.");
    });

    it("says nothing about a board that cannot be reached or is off, and nothing before the daemon has told, and shows the skeds last read", () => {
      expect(pane([], { state: "offline" }).find(".empty").exists()).toBe(false);
      expect(pane([], { state: "off" }).find(".empty").exists()).toBe(false);
      expect(pane([sked("a")], { state: "offline" }).findAll(".sked")).toHaveLength(1);
      daemon.skeds.value = null;
      const wrapper = mount(SkedsPane, { global: withDaemon(daemon) });
      expect(wrapper.find(".empty").exists()).toBe(false);
      expect(wrapper.text()).not.toMatch(/error|offline|unreachable|cannot/i);
    });

    it("shows the board without the form for a closed board, and with the form otherwise", () => {
      const closed = pane([sked("a")], { state: "closed" });
      expect(closed.find("form").exists()).toBe(false);
      expect(closed.findAll(".sked")).toHaveLength(1);
      for (const state of ["ok", "offline", "off"] as const) expect(pane([], { state }).find("form").exists()).toBe(true);
    });

    it("shows the form again when the board opens", async () => {
      const wrapper = pane([], { state: "closed" });
      expect(wrapper.find("form").exists()).toBe(false);
      await tell(daemon, { skeds: skedsState([]) });
      expect(wrapper.find("form").exists()).toBe(true);
    });
  });
});
