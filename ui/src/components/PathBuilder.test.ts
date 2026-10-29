// The path builder on its own (PathBuilder.vue with its dialog): it opens from its button over the page, starts from the field's path, makes the aliases from the Hops choice and the tick of home digipeaters, draws the path as
// what it means with its hops in all, marks one of more hops than the network usually allows and refuses one that is no path, builds a path from the digipeaters we hear and the ones next to them in the routes, from a
// station's route turned round and from what is typed, holds it to the field's rule, and gives it to the field only on Use.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import PathBuilder from "@/components/PathBuilder.vue";
import type { StationRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station } from "@/test/fixtures";

const quiet = (call: string, extra: Partial<StationRow> = {}): StationRow =>
  station(call, { heard_via: [], last_route: "", best_route: "", route_marks: [], suggested_path: null, ...extra });
/** OH2RDK-7 is heard direct (it repeated OH2DPN's packets for us), and OH2DPN's packets came by OH2RCH-2 then OH2RDK-7. */
const STATIONS = new Map(
  [
    quiet("OH2DPN", { heard_via: [["OH2RDK-7", 12]], best_route: "via OH2RCH-2 → OH2RDK-7", suggested_path: "OH2RDK-7,OH2RCH-2" }),
    quiet("OH2RDK-7", { symbol_code: "#", heard_direct: 4, last_direct_at: ago(120), distance_km: 3.2 }),
    quiet("OH2RCH-2", { symbol_code: "#", distance_km: 14 }),
    quiet("OH2NEW"),
  ].map((row) => [row.call, row]),
);

type Props = { value?: string; usual?: string; check?: (path: string) => string; station?: string };

function make(props: Props = {}) {
  const wrapper = mount(PathBuilder, {
    props: { value: "", usual: "WIDE1-1,WIDE2-1", ...props },
    global: withDaemon(fakeDaemon({ stations: STATIONS })),
    attachTo: document.body,
  });
  return wrapper;
}

const dialog = (): HTMLElement | null => document.body.querySelector<HTMLElement>(".pathbuild");
const all = (selector: string): HTMLElement[] => [...(dialog()?.querySelectorAll<HTMLElement>(selector) ?? [])];
const text = (element: Element | null | undefined): string => (element?.textContent ?? "").trim();
const button = (label: string): HTMLButtonElement | undefined => all("button").find((b) => text(b) === label) as HTMLButtonElement | undefined;
const result = (): string => text(dialog()?.querySelector("output"));
const count = (): HTMLElement | null => dialog()?.querySelector<HTMLElement>(".pathbuild-count") ?? null;
const pressed = (): string[] => all(".pathbuild-seg button[aria-pressed='true']").map(text);
const tick = (): HTMLInputElement | null => dialog()?.querySelector<HTMLInputElement>(".pathbuild-home input") ?? null;
/** The nodes of the picture between you and the stations around: who takes each hop. */
const nodes = (): string[] => all(".pathbuild-node .pathbuild-kind").map(text);
/** Each element of the path as the picture writes it under its nodes ("" for a call, which is its node's label). */
const texts = (): string[] => all(".pathbuild-chip").map((chip) => text(chip.querySelector(".pathbuild-text .mono")));
const choices = (): string[] => all(".pathbuild-choice .pathbuild-call").map(text);
const heading = (): string => text(dialog()?.querySelector(".pathbuild-heading"));
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function open(wrapper: ReturnType<typeof make>): Promise<void> {
  await wrapper.find("button.pathbuild-open").trigger("click");
  await flush();
}

async function click(target: HTMLElement | null | undefined): Promise<void> {
  target?.click();
  await flush();
}

async function type(typed: string): Promise<void> {
  const input = dialog()?.querySelector<HTMLInputElement>(".pathbuild-type input");
  if (!input) throw new Error("no field to type a hop into");
  input.value = typed;
  input.dispatchEvent(new Event("input"));
  await flush();
}

afterEach(() => (document.body.innerHTML = ""));

describe("the path builder", () => {
  it("is a button beside the field that opens a dialog over the page, starting from the field's path", async () => {
    const wrapper = make({ value: "OH2RDK-7,OH2RCH-2" });
    expect(wrapper.find("button.pathbuild-open").attributes("aria-label")).toBe("Build the path");
    expect(dialog()).toBeNull();
    await open(wrapper);
    expect(dialog()?.getAttribute("aria-modal")).toBe("true");
    expect(dialog()?.parentElement?.parentElement).toBe(document.body);
    expect(nodes()).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    expect(text(count())).toBe("2 hops");
    expect(document.activeElement).toBe(dialog());
  });

  it("starts from the path in force when the field is empty, and shows no digipeater as Direct", async () => {
    const wrapper = make({ value: "", usual: "WIDE2-1" });
    await open(wrapper);
    expect(result()).toBe("WIDE2-1");
    await click(button("Direct"));
    expect(nodes()).toEqual([]);
    expect(text(dialog()?.querySelector(".pathbuild-direct"))).toBe("Direct");
    expect(result()).toBe("DIRECT");
    expect(text(count())).toBe("0 hops");
    expect(pressed()).toEqual(["Direct"]);
  });

  it("makes the aliases from the hops chosen, each choice titled with the path it makes, and Use gives the path to the field", async () => {
    const wrapper = make();
    await open(wrapper);
    expect(pressed()).toEqual(["2"]);
    expect(tick()?.checked).toBe(true);
    expect(all(".pathbuild-seg button").map((b) => [text(b), b.title])).toEqual([
      ["Direct", "No digipeater: only the stations that hear you"],
      ["1", "1 hop in all: WIDE1-1"],
      ["2", "2 hops in all: WIDE1-1,WIDE2-1"],
      ["3", "3 hops in all: WIDE1-1,WIDE2-2"],
    ]);
    await click(button("3"));
    expect(result()).toBe("WIDE1-1,WIDE2-2");
    await click(tick());
    expect(result()).toBe("WIDE3-3");
    await click(button("1"));
    expect(result()).toBe("WIDE2-1");
    await click(button("Direct"));
    expect(tick()?.disabled).toBe(false);
    await click(button("2"));
    expect(result()).toBe("WIDE2-2");
    await click(tick());
    expect(result()).toBe("WIDE1-1,WIDE2-1");
    await click(tick());
    await click(button("Use"));
    expect(wrapper.emitted("use")).toEqual([["WIDE2-2"]]);
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(wrapper.find("button.pathbuild-open").element);
  });

  it("lets home digipeaters take the first hop as the path does, else as the usual path does, else it does", async () => {
    for (const [value, usual, on] of [
      ["WIDE2-2", "WIDE1-1,WIDE2-1", false],
      ["OH2RDK-7", "WIDE2-1", false],
      ["", "WIDE2-1", false],
      ["", "WIDE1-1,WIDE2-1", true],
      ["DIRECT", "", true],
    ] as const) {
      const wrapper = make({ value, usual });
      await open(wrapper);
      await click(button("Direct"));
      await click(button("1"));
      expect(result(), `${value} / ${usual}`).toBe(on ? "WIDE1-1" : "WIDE2-1");
      wrapper.unmount();
    }
  });

  it("draws the path as who takes each hop, with the element as it is written under its hops", async () => {
    const cases: [string, string[], string[], string][] = [
      ["WIDE1-1,WIDE2-1", ["any digi", "wide digi"], ["WIDE1-1", "WIDE2-1"], "2 hops"],
      ["WIDE2-2", ["wide digi", "wide digi"], ["WIDE2-2"], "2 hops"],
      ["WIDE3-3", ["wide digi", "wide digi", "wide digi"], ["WIDE3-3"], "3 hops"],
      ["OH2RDK-7,WIDE2-1", ["OH2RDK-7", "wide digi"], ["", "WIDE2-1"], "2 hops"],
    ];
    for (const [value, labels, written, hops] of cases) {
      const wrapper = make({ value });
      await open(wrapper);
      expect([nodes(), texts(), text(count())], value).toEqual([labels, written, hops]);
      wrapper.unmount();
    }
    const wrapper = make({ value: "OH2RDK-7,WIDE2-2" });
    await open(wrapper);
    expect(all(".pathbuild-node").map((node) => node.title)).toEqual([
      "Hop 1: OH2RDK-7, and no other digipeater",
      "Hop 2: a wide-area digipeater; home (fill-in) ones leave it",
      "Hop 3: a wide-area digipeater; home (fill-in) ones leave it",
    ]);
    expect(all(".pathbuild-text .mono")[0]?.title).toBe("WIDE2-2: n = 2 hops asked for, N = 2 still to go; each digipeater takes one off N");
    expect(all(".pathbuild-node").map((node) => node.classList.contains("over"))).toEqual([false, false, true]);
    expect(all(".pathbuild-end").map((end) => end.title)).toEqual(["Your station sends the packet", "The stations that hear the last hop get it"]);
    await click(button("1"));
    expect(all(".pathbuild-node")[0]?.title).toBe("Hop 1: OH2RDK-7, and no other digipeater");
    await click(button("Direct"));
    await click(button("1"));
    expect(all(".pathbuild-node")[0]?.title).toBe("Hop 1: any digipeater that hears it, a home (fill-in) one as well as a wide one");
  });

  it("marks a path of more hops than the network usually allows in amber, and still lets it be used", async () => {
    const wrapper = make({ value: "WIDE1-1,WIDE2-1" });
    await open(wrapper);
    expect(count()?.classList.contains("tag-neutral")).toBe(true);
    expect(count()?.title).toBe("");
    await click(button("3"));
    expect(count()?.classList.contains("tag-warn")).toBe(true);
    expect(count()?.title).toBe("3 hops: more than the 2 that most networks allow");
    expect(button("Use")?.disabled).toBe(false);
    await click(button("Use"));
    expect(wrapper.emitted("use")).toEqual([["WIDE1-1,WIDE2-2"]]);
  });

  it("refuses an alias that is no path, typed in lower case, in red with the reason in the titles", async () => {
    const wrapper = make({ value: "DIRECT" });
    await open(wrapper);
    await type("wide1-2");
    await click(button("Add"));
    const reason = "WIDE1-2 is no path: N (2) is never more than n (1); home digipeaters answer only WIDE1-1";
    expect(result()).toBe("WIDE1-2");
    expect(nodes()).toEqual(["no hop"]);
    expect(all(".pathbuild-chip")[0]?.classList.contains("bad")).toBe(true);
    expect(all(".pathbuild-node")[0]?.title).toBe(reason);
    expect(count()?.classList.contains("tag-bad")).toBe(true);
    expect(count()?.title).toBe(reason);
    expect(button("Use")?.disabled).toBe(true);
    expect(button("Use")?.title).toBe(reason);
    expect(pressed()).toEqual([]);
    expect(tick()?.disabled).toBe(true);
    expect(tick()?.closest("label")?.title).toBe("Choose 1, 2 or 3 hops first");
    await click(all(".pathbuild-x")[0]);
    expect(button("Use")?.disabled).toBe(false);
    await type("wide2-2");
    await click(button("Add"));
    expect([result(), ...nodes()]).toEqual(["WIDE2-2", "wide digi", "wide digi"]);
  });

  it("puts a digipeater we hear first, in the place of an alias hop, then one seen after it in the routes, and the hops chosen go after them", async () => {
    const wrapper = make({ value: "WIDE1-1,WIDE2-1" });
    await open(wrapper);
    expect(heading()).toBe("Digipeaters heard");
    expect(choices()).toEqual(["OH2RDK-7"]);
    await click(all(".pathbuild-choice")[0]);
    expect(result()).toBe("OH2RDK-7,WIDE2-1");
    expect(pressed()).toEqual(["2"]);
    expect(tick()?.disabled).toBe(true);
    expect(tick()?.checked).toBe(false);
    expect(tick()?.closest("label")?.title).toBe("The first hop is OH2RDK-7");
    expect(heading()).toBe("Next to OH2RDK-7");
    await click(all(".pathbuild-choice")[0]);
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    await click(button("3"));
    expect(result()).toBe("OH2RDK-7,OH2RCH-2,WIDE2-1");
    expect(text(count())).toBe("3 hops");
    await click(button("1"));
    expect(result()).toBe("OH2RDK-7");
  });

  it("builds a path through a digipeater we hear, then one seen after it in the routes", async () => {
    const wrapper = make({ value: "DIRECT" });
    await open(wrapper);
    expect(heading()).toBe("Digipeaters heard");
    expect(choices()).toEqual(["OH2RDK-7"]);
    expect(all(".pathbuild-choice .pathbuild-num").map(text)).toEqual(["12", "2 min", "3.2 km"]);
    await click(all(".pathbuild-choice")[0]);
    expect(heading()).toBe("Next to OH2RDK-7");
    expect(choices()).toEqual(["OH2RCH-2"]);
    expect(all(".pathbuild-choice .pathbuild-num")[0]?.title).toBe("Next to OH2RDK-7 in the routes of 1 station");
    await click(all(".pathbuild-choice")[0]);
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    await click(button("Use"));
    expect(wrapper.emitted("use")).toEqual([["OH2RDK-7,OH2RCH-2"]]);
  });

  it("offers a station's route its packets come by, turned round, for its Route only, and not when none is known", async () => {
    const plain = make();
    await open(plain);
    expect(button("As its packets come")).toBeUndefined();
    plain.unmount();
    const route = make({ station: "OH2DPN" });
    await open(route);
    expect(button("As its packets come")?.title).toBe("OH2RDK-7,OH2RCH-2");
    await click(button("As its packets come"));
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    route.unmount();
    const none = make({ station: "OH2NEW" });
    await open(none);
    expect(button("As its packets come")?.disabled).toBe(true);
    expect(button("As its packets come")?.title).toBe("No route of its packets is known");
  });

  it("adds a hop that is typed, with Add or Enter, and refuses what is no call or alias", async () => {
    const wrapper = make({ value: "OH2RDK-7" });
    await open(wrapper);
    await type("oh2rch-2");
    await click(button("Add"));
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    await type("WIDE2-1");
    dialog()
      ?.querySelector(".pathbuild-type input")
      ?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flush();
    expect(result()).toBe("OH2RDK-7,OH2RCH-2,WIDE2-1");
    await type("OH2 RCH");
    expect(button("Add")?.disabled).toBe(true);
    await type("DIRECT");
    expect(button("Add")?.disabled).toBe(true);
    await type("A1,B2,C3,D4,E5,F6");
    expect(button("Add")?.disabled).toBe(true);
    await type("A1,B2,C3,D4,E5");
    expect(button("Add")?.disabled).toBe(false);
    await click(button("Add"));
    expect(all(".pathbuild-chip")).toHaveLength(8);
    await type("G7");
    expect(button("Add")?.disabled).toBe(true);
  });

  it("takes an element out with its ×", async () => {
    const wrapper = make({ value: "OH2RDK-7,WIDE2-2" });
    await open(wrapper);
    await click(all(".pathbuild-x")[0]);
    expect(result()).toBe("WIDE2-2");
    expect(all(".pathbuild-x")[0]?.getAttribute("aria-label")).toBe("Remove WIDE2-2");
  });

  it("holds the path to the field's own rule: Use is off with the reason in its title while it finds something", async () => {
    const wrapper = make({ value: "OH2RDK-7,OH2RCH-2", check: (path) => (path.includes("OH2RCH-2") ? "not that one" : "") });
    await open(wrapper);
    expect(button("Use")?.disabled).toBe(true);
    expect(button("Use")?.title).toBe("not that one");
    expect(dialog()?.querySelector("output")?.classList.contains("invalid")).toBe(true);
    await click(all(".pathbuild-x")[1]);
    expect(button("Use")?.disabled).toBe(false);
  });

  it("is checked as calls separated by commas, at most 8, when the field gives no rule of its own", async () => {
    const wrapper = make({ value: "A1,B2,C3,D4,E5,F6,G7,H8,J9" });
    await open(wrapper);
    expect(button("Use")?.disabled).toBe(true);
    expect(button("Use")?.title).toBe("Calls separated by commas, at most 8");
  });

  it("leaves the field as it is on Cancel, the cross, Esc and a press beside it", async () => {
    const wrapper = make({ value: "OH2RDK-7" });
    for (const close of [
      () => click(button("Cancel")),
      () => click(all(".updatedialog-head .xbtn")[0]),
      async () => {
        dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        await flush();
      },
      async () => {
        document.body.querySelector(".pathbuild-backdrop")?.dispatchEvent(new Event("pointerdown", { bubbles: true }));
        await flush();
      },
    ]) {
      await open(wrapper);
      await click(button("2"));
      await close();
      expect(dialog()).toBeNull();
    }
    expect(wrapper.emitted("use")).toBeUndefined();
  });

  it("keeps the Esc it takes from what it was opened from, and a press in it from the page", async () => {
    const wrapper = make();
    const heard: string[] = [];
    const listen = (event: Event) => heard.push(event.type);
    document.addEventListener("keydown", listen);
    document.addEventListener("pointerdown", listen);
    await open(wrapper);
    dialog()?.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flush();
    document.removeEventListener("keydown", listen);
    document.removeEventListener("pointerdown", listen);
    expect(heard).toEqual([]);
    expect(dialog()).toBeNull();
  });

  it("has one (i) in its header, a short guide to WIDEn-N, whose note Esc and a press elsewhere in the dialog close first", async () => {
    const wrapper = make();
    await open(wrapper);
    expect(all(".info-toggle")).toHaveLength(1);
    const toggle = dialog()?.querySelector<HTMLButtonElement>(".updatedialog-head .info-toggle");
    expect(toggle?.getAttribute("aria-label")).toBe("About WIDEn-N");
    await click(toggle);
    expect(all(".info-line").map(text)[0]).toMatch(/^WIDEn-N: n is how many hops/);
    expect(all(".info-line")).toHaveLength(4);
    toggle?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flush();
    expect(all(".info-line")).toHaveLength(0);
    expect(dialog()).not.toBeNull();
    await click(toggle);
    all(".pathbuild-seg button")[0]?.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await flush();
    expect(all(".info-line")).toHaveLength(0);
    expect(dialog()).not.toBeNull();
  });
});
