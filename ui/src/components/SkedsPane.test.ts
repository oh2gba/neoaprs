import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import SkedsPane from "@/components/SkedsPane.vue";
import type { SkedPast, SkedRow, SkedsState } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { NOW, sked, skedsState, toastOf } from "@/test/fixtures";

let daemon: FakeDaemon;
beforeEach(() => {
  localStorage.clear();
  daemon = fakeDaemon({ skeds: skedsState() });
});
afterEach(() => document.body.replaceChildren());
/** The dialog of Plan a test, which is put at the end of the page. */
const dialog = () => document.querySelector<HTMLElement>(".skeddialog");
const field = <T extends HTMLInputElement | HTMLSelectElement = HTMLSelectElement>(id: string) =>
  dialog()?.querySelector<T>(`#${id}`) ?? null;
async function setField(id: string, value: string): Promise<void> {
  const element = field<HTMLInputElement | HTMLSelectElement>(id);
  if (element === null) throw new Error(`no #${id}`);
  element.value = value;
  element.dispatchEvent(new Event(element.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  await flushPromises();
}
async function post(): Promise<void> {
  dialog()
    ?.querySelector("form")
    ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await flushPromises();
}
const plan = (wrapper: { find: (selector: string) => ReturnType<ReturnType<typeof mount>["find"]> }) =>
  wrapper.find("button.sked-plan");
const sent = (cmd: string) =>
  daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === cmd);
const at = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString().slice(0, 19) + "Z";

function pane(rows: SkedRow[] = [], extra: Partial<SkedsState> = {}) {
  daemon.skeds.value = skedsState(rows, extra);
  return mount(SkedsPane, { global: withDaemon(daemon), attachTo: document.body });
}
const rows = (wrapper: ReturnType<typeof pane>) => wrapper.findAll(".boardpane > .board > .sked");
const pastRows = (wrapper: ReturnType<typeof pane>) => wrapper.findAll(".sked-past .sked");

// The fixtures' time is Wednesday 21 October 2026, 12:00 UTC; a sked() starts in 2 hours and lasts
// 2.
describe("SkedsPane", () => {
  it("has an (i) at the top that says what a sked is, that the board is public and that it is not sent by radio", async () => {
    const wrapper = pane();
    const bar = wrapper.find(".tab-help");
    expect((wrapper.element as HTMLElement).firstElementChild).toBe(bar.element);
    await bar.find("button.info-toggle").trigger("click");
    expect(bar.find(".info-text").text()).toContain("For stations trying APRS on HF: say when you will be on the air");
    expect(bar.find(".info-text").text()).toContain("The board is public");
    expect(bar.find(".info-text").text()).toContain("not sent by radio");
  });

  it("shows a row with the time in UTC, how long until it, the dial and the call; the viewer's own time is the title", () => {
    const wrapper = pane([sked("a", { call: "OH2XYZ" })]);
    const [row] = rows(wrapper);
    expect(row?.find(".sked-when strong").text()).toBe("Wed 21 Oct 14:00 to 16:00 UTC");
    expect(row?.find(".sked-when .muted").text()).toBe("in 2 h");
    expect(row?.find(".sked-when").attributes("title")).toMatch(
      /^Your time: Wed 21 Oct \d{2}:\d{2} to (\w{3} \d{1,2} \w{3} )?\d{2}:\d{2}$/,
    );
    expect(row?.find(".sked-dial").text()).toBe("7.0541 MHz USB");
    expect(row?.findAll(".sked-call").map((c) => c.text())).toEqual(["OH2XYZ"]);
  });

  it("says now while a sked runs, and writes the end with its day when the sked runs over midnight", () => {
    const wrapper = pane([
      sked("run", { from: at(-1), to: at(1) }),
      sked("late", { from: "2026-10-21T22:00:00Z", to: "2026-10-22T02:00:00Z" }),
    ]);
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
    const wrapper = pane([
      sked("a", { call: "OH2AAA" }),
      sked("b", { call: "OH2BBB" }),
      sked("c", { call: "OH2CCC", dial: "14.1070 MHz USB" }),
    ]);
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
      const wrapper = pane([
        sked("mine", { call: "OH2GBA", ours: true }),
        sked("other", { call: "OH2XYZ", from: at(5), to: at(6) }),
      ]);
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

    it("has Join on a row of others, which opens Plan a test filled with that test's day, times and frequency, and posts nothing", async () => {
      const wrapper = pane([
        sked("a", { call: "OH2XYZ", note: "Mercury", dial: "14.1070 MHz USB", from: at(26), to: at(28) }),
      ]);
      const join = wrapper.find(".sked-actions .btn");
      expect(join.text()).toBe("Join");
      expect(join.attributes("aria-label")).toContain("OH2XYZ");
      await join.trigger("click");
      expect(sent("sked_post")).toEqual([]);
      expect(dialog()?.querySelector("h2")?.textContent).toBe("Plan a test");
      expect(
        ["sked-day", "sked-from", "sked-to", "sked-frequency"].map((id) => field<HTMLSelectElement>(id)?.value),
      ).toEqual(["2026-10-22", "14:00", "16:00", "14.1070 MHz USB"]);
      expect(field<HTMLInputElement>("sked-note")?.value).toBe("");
      await post();
      expect(sent("sked_post")).toEqual([
        { cmd: "sked_post", from: at(26), to: at(28), dial: "14.1070 MHz USB", note: "" },
      ]);
    });

    it("fills a dial the project does not suggest as Other with its number", async () => {
      const wrapper = pane([sked("a", { dial: "10.1470 MHz USB" })]);
      await wrapper.find(".sked-actions .btn").trigger("click");
      expect([field<HTMLSelectElement>("sked-frequency")?.value, field<HTMLInputElement>("sked-dial")?.value]).toEqual([
        "other",
        "10.1470",
      ]);
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

  describe("the past tests", () => {
    const gone = (id: string, extra: Partial<SkedPast> = {}): SkedPast => ({
      id,
      call: "OH2XYZ",
      from: at(-5),
      to: at(-3),
      dial: "7.0541 MHz USB",
      note: "",
      ...extra,
    });

    it("are a section under the board, the last of the pane, that says so when there are none", () => {
      const wrapper = pane([sked("a")]);
      const section = wrapper.find("fieldset.sked-past");
      expect(section.find("legend").text()).toBe("Past tests");
      expect(section.find(".empty").text()).toBe("No past tests.");
      expect(wrapper.find(".boardpane").element.lastElementChild).toBe(section.element);
    });

    it("fold by the arrow of their title as a Settings group does, closed at first with nothing but the title, and remembered in this browser", async () => {
      const wrapper = pane([], { past: [gone("a")] });
      const section = wrapper.find("fieldset.sked-past");
      const arrow = section.find("legend > button.groupfold");
      const body = section.find(".group-body");
      expect([arrow.text(), arrow.attributes("aria-expanded"), arrow.attributes("aria-controls")]).toEqual([
        "Past tests",
        "false",
        body.attributes("id"),
      ]);
      expect(section.classes("folded")).toBe(true);
      expect((body.element as HTMLElement).style.display).toBe("none");
      expect(section.find("legend").text()).toBe("Past tests");
      await arrow.trigger("click");
      expect([arrow.attributes("aria-expanded"), (body.element as HTMLElement).style.display]).toEqual(["true", ""]);
      const again = pane([], { past: [gone("a")] });
      expect(again.find("fieldset.sked-past legend button").attributes("aria-expanded")).toBe("true");
      await again.find("fieldset.sked-past legend button").trigger("click");
      await tell(daemon, { skeds: skedsState([], { past: [gone("a"), gone("b", { from: at(-9), to: at(-8) })] }) });
      expect(again.find("fieldset.sked-past legend button").attributes("aria-expanded")).toBe("false");
    });

    it("show a test in the board's own row: the time in UTC with the viewer's own in the title, the dial, every call and the note, with no Join", () => {
      const wrapper = pane([], {
        past: [gone("a", { call: "OH2GBA", note: "Mercury, 10 W" }), gone("b", { call: "OH3ABC" })],
      });
      const [row] = pastRows(wrapper);
      expect(pastRows(wrapper)).toHaveLength(1);
      expect(row?.find(".sked-when strong").text()).toBe("Wed 21 Oct 07:00 to 09:00 UTC");
      expect(row?.find(".sked-when .muted").exists()).toBe(false);
      expect(row?.find(".sked-when").attributes("title")).toMatch(/^Your time: /);
      expect(row?.find(".sked-dial").text()).toBe("7.0541 MHz USB");
      expect(row?.findAll(".sked-call").map((c) => c.text())).toEqual(["OH2GBA", "OH3ABC"]);
      expect(row?.find(".sked-note").text()).toBe("OH2GBA: Mercury, 10 W");
      expect(row?.find(".sked-actions").exists()).toBe(true);
      expect(row?.find(".sked-actions .btn").exists()).toBe(false);
      expect(row?.find(".tag").exists()).toBe(false);
    });

    it("have the trash in the column of Delete and Join, which asks twice and then takes the whole test off this list", async () => {
      const wrapper = pane([sked("a", { call: "OH2XYZ" })], {
        past: [gone("a1", { call: "OH2GBA" }), gone("a2", { call: "OH3ABC" })],
      });
      expect(rows(wrapper)[0]?.find(".xbtn").exists()).toBe(false);
      const button = pastRows(wrapper)[0]?.find(".sked-actions .xbtn");
      expect(button?.attributes("aria-label")).toBe("Delete the past test, Wed 21 Oct 07:00 to 09:00 UTC");
      await button?.trigger("click");
      expect(sent("sked_past_delete")).toEqual([]);
      expect(button?.text()).toBe("sure?");
      await button?.trigger("click");
      expect(sent("sked_past_delete")).toEqual([{ cmd: "sked_past_delete", ids: ["a1", "a2"] }]);
      expect(sent("sked_delete")).toEqual([]);
    });

    it("have the trash only once the daemon tells them past: a board row ended by this device's clock has none yet", async () => {
      daemon.now.value = Date.parse(at(10));
      const board = [sked("b", { from: at(5), to: at(6) })];
      const wrapper = pane(board, { past: [gone("p1")] });
      expect(pastRows(wrapper)).toHaveLength(2);
      expect(pastRows(wrapper).map((r) => r.find(".xbtn").exists())).toEqual([false, true]);
      expect(pastRows(wrapper)[0]?.find(".sked-actions").exists()).toBe(true);
      await tell(daemon, { skeds: skedsState([], { past: [gone("b", { from: at(5), to: at(6) }), gone("p1")] }) });
      expect(pastRows(wrapper).map((r) => r.find(".xbtn").exists())).toEqual([true, true]);
    });

    it("lose the row the daemon no longer tells, and nothing above it changes", async () => {
      const board = [sked("a"), sked("b", { from: at(5), to: at(6) })];
      const past = [gone("p1", { from: at(-3), to: at(-2) }), gone("p2"), gone("p3", { from: at(-9), to: at(-8) })];
      const wrapper = pane(board, { past });
      const before = [...rows(wrapper), ...pastRows(wrapper)].map((r) => r.element);
      await pastRows(wrapper)[1]?.find(".xbtn").trigger("click");
      await pastRows(wrapper)[1]?.find(".xbtn").trigger("click");
      expect(sent("sked_past_delete")).toEqual([{ cmd: "sked_past_delete", ids: ["p2"] }]);
      await tell(daemon, { skeds: skedsState(board, { past: [past[0], past[2]] }) });
      const after = [...rows(wrapper), ...pastRows(wrapper)].map((r) => r.element);
      expect(after).toEqual([before[0], before[1], before[2], before[4]]);
      expect(wrapper.find(".boardpane").element.lastElementChild).toBe(wrapper.find("fieldset.sked-past").element);
      expect(pastRows(wrapper).map((r) => r.find(".xbtn").classes("armed"))).toEqual([false, false]);
    });

    it("list the newest first, twenty at most", () => {
      const many = Array.from({ length: 21 }, (_, n) => gone(`p${n}`, { from: at(-2 * n - 3), to: at(-2 * n - 1) }));
      const wrapper = pane([], { past: [...many].reverse() });
      expect(pastRows(wrapper)).toHaveLength(20);
      expect(pastRows(wrapper)[0]?.find(".sked-when strong").text()).toBe("Wed 21 Oct 09:00 to 11:00 UTC");
    });

    it("take a test that ends by the page's clock off the board at once", async () => {
      const wrapper = pane([sked("run", { from: at(-1), to: at(1) }), sked("b", { from: at(5), to: at(6) })]);
      expect(pastRows(wrapper)).toHaveLength(0);
      await tell(daemon, { now: NOW + 2 * 3_600_000 });
      expect(rows(wrapper)).toHaveLength(1);
      expect(pastRows(wrapper)).toHaveLength(1);
      expect(pastRows(wrapper)[0]?.find(".sked-when strong").text()).toBe("Wed 21 Oct 11:00 to 13:00 UTC");
    });

    it("stay while the board cannot be reached, and are not there while it is off or not told", () => {
      expect(pastRows(pane([], { state: "offline", past: [gone("a")] }))).toHaveLength(1);
      expect(pane([], { state: "offline" }).find(".sked-past").exists()).toBe(false);
      expect(pane([], { state: "off" }).find(".sked-past").exists()).toBe(false);
      expect(pane([], { state: "closed" }).find(".sked-past .empty").exists()).toBe(true);
    });
  });

  describe("the state of the board", () => {
    it("says the board is empty when it was read, and when it is closed", () => {
      expect(pane().find(".empty").text()).toBe("No tests planned.");
      expect(pane([], { state: "closed" }).find(".empty").text()).toBe("No tests planned.");
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

    it("shows the board without Plan a test for a closed board, and with it otherwise", () => {
      const closed = pane([sked("a")], { state: "closed" });
      expect(plan(closed).exists()).toBe(false);
      expect(closed.findAll(".sked")).toHaveLength(1);
      for (const state of ["ok", "offline", "off"] as const) expect(plan(pane([], { state })).exists()).toBe(true);
    });

    it("shows Plan a test again when the board opens", async () => {
      const wrapper = pane([], { state: "closed" });
      expect(plan(wrapper).exists()).toBe(false);
      await tell(daemon, { skeds: skedsState([]) });
      expect(plan(wrapper).exists()).toBe(true);
    });
  });
});

describe("the tab on a phone", () => {
  it("is one scrolling column of the board, the past tests, Plan a test and the chat, so that neither squeezes the board", () => {
    const wrapper = pane([sked("a")]);
    expect(wrapper.classes()).toEqual(expect.arrayContaining(["boardwrap", "skedswrap"]));
    expect(cssRule(".size-phone .skedswrap")).toMatch(/overflow-y:\s*auto/);
    expect(cssRule(".size-phone .skedswrap > *")).toMatch(/flex:\s*none/);
    expect(cssRule(".size-phone .skedswrap > .boardpane")).toMatch(/overflow:\s*visible/);
    // the field scrolled into view above the keyboard brings its counter and Send with it
    expect(cssRule(".size-phone .skedswrap .chat-compose .compose-text")).toMatch(/scroll-margin-bottom:\s*\d+px/);
  });
});

describe("Plan a test", () => {
  it("is one button in the place of the form, with no form in the pane until it is pressed", async () => {
    const wrapper = pane();
    expect(plan(wrapper).text()).toBe("Plan a test");
    expect(document.querySelector("form.sked-compose")).toBeNull();
    await plan(wrapper).trigger("click");
    expect(dialog()?.getAttribute("role")).toBe("dialog");
    expect(dialog()?.getAttribute("aria-modal")).toBe("true");
    expect(dialog()?.querySelector("h2")?.textContent).toBe("Plan a test");
    expect(dialog()?.querySelector("form.sked-compose")).not.toBeNull();
    expect(dialog()?.querySelector("legend")).toBeNull();
  });

  it("closes with its cross, with Cancel, with Escape and with a press beside it, and gives the focus back to the button", async () => {
    const wrapper = pane();
    const close = async (how: () => void | Promise<unknown>) => {
      await plan(wrapper).trigger("click");
      await flushPromises();
      expect(dialog()?.contains(document.activeElement)).toBe(true);
      await how();
      await flushPromises();
      expect(dialog()).toBeNull();
      expect(document.activeElement).toBe(plan(wrapper).element);
    };
    await close(() => dialog()?.querySelector<HTMLButtonElement>("header .xbtn")?.click());
    await close(() =>
      [...(dialog()?.querySelectorAll("button") ?? [])].find((b) => b.textContent?.trim() === "Cancel")?.click(),
    );
    await close(() => {
      dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    await close(() => {
      const backdrop = document.querySelector(".skeddialog-backdrop");
      backdrop?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    });
  });

  it("closes when the daemon has the post, and stays open with what it shows when the post is refused", async () => {
    const wrapper = pane();
    await plan(wrapper).trigger("click");
    await setField("sked-note", "Mercury");
    await post();
    const [command] = sent("sked_post") as { from: string; to: string; dial: string }[];
    await tell(daemon, { lastError: toastOf("sked_post: the board said no", "other") });
    expect(dialog()).not.toBeNull();
    expect(field<HTMLInputElement>("sked-note")?.value).toBe("Mercury");
    expect(dialog()?.querySelector<HTMLButtonElement>("button[type='submit']")?.disabled).toBe(false);
    await post();
    await tell(daemon, {
      skeds: skedsState([sked("y", { ours: true, from: command?.from, to: command?.to, dial: command?.dial })]),
    });
    expect(dialog()).toBeNull();
    await plan(wrapper).trigger("click");
    expect(field<HTMLInputElement>("sked-note")?.value).toBe("");
  });

  it("keeps what was chosen and typed when it is closed without posting and opened again", async () => {
    const wrapper = pane();
    await plan(wrapper).trigger("click");
    await setField("sked-from", "18:30");
    await setField("sked-frequency", "28.1800 MHz USB");
    await setField("sked-note", "FT8 first");
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    await tell(daemon, { skeds: skedsState() });
    await plan(wrapper).trigger("click");
    expect([field("sked-from")?.value, field("sked-frequency")?.value, field("sked-note")?.value]).toEqual([
      "18:30",
      "28.1800 MHz USB",
      "FT8 first",
    ]);
  });

  it("asks the daemon to look at the project's dials again when it opens, at most once a minute, and when the socket opens if it was not open", async () => {
    const wrapper = pane();
    expect(sent("frequencies")).toEqual([]);
    await plan(wrapper).trigger("click");
    expect(sent("frequencies")).toEqual([{ cmd: "frequencies" }]);
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    await plan(wrapper).trigger("click");
    expect(sent("frequencies")).toHaveLength(1);
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    document.body.replaceChildren();
    const later = pane();
    daemon.connection.value = "connecting";
    await plan(later).trigger("click");
    expect(sent("frequencies")).toHaveLength(1);
    daemon.connection.value = "open";
    await flushPromises();
    expect(sent("frequencies")).toHaveLength(2);
  });
});
