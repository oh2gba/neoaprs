// The path builder on its own (PathBuilder.vue with its dialog): it opens from its button over the page, starts from the field's path, builds a path from the usual ones, from the digipeaters we hear and the ones next to them in
// the routes, from a station's route turned round and from what is typed, holds it to the field's rule, and gives it to the field only on Use.
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
const button = (text: string): HTMLButtonElement | undefined =>
  all("button").find((b) => (b.textContent ?? "").trim() === text) as HTMLButtonElement | undefined;
const result = (): string => dialog()?.querySelector("output")?.textContent ?? "";
const chips = (): string[] => all(".pathbuild-chip .mono").map((chip) => chip.textContent ?? "");
const choices = (): string[] => all(".pathbuild-choice .pathbuild-call").map((call) => call.textContent ?? "");
const heading = (): string => dialog()?.querySelector(".pathbuild-heading")?.textContent ?? "";
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function open(wrapper: ReturnType<typeof make>): Promise<void> {
  await wrapper.find("button.pathbuild-open").trigger("click");
  await flush();
}

async function click(target: HTMLElement | undefined): Promise<void> {
  target?.click();
  await flush();
}

async function type(text: string): Promise<void> {
  const input = dialog()?.querySelector<HTMLInputElement>(".pathbuild-type input");
  if (!input) throw new Error("no field to type a hop into");
  input.value = text;
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
    expect(chips()).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(result()).toBe("OH2RDK-7,OH2RCH-2");
    expect(dialog()?.querySelector(".pathbuild-count")?.textContent).toBe("2 hops");
    expect(document.activeElement).toBe(dialog());
  });

  it("starts from the path in force when the field is empty, and shows no digipeater as Direct", async () => {
    const wrapper = make({ value: "", usual: "WIDE2-1" });
    await open(wrapper);
    expect(result()).toBe("WIDE2-1");
    await click(button("Direct"));
    expect(chips()).toEqual([]);
    expect(dialog()?.querySelector(".pathbuild-direct")?.textContent).toBe("Direct");
    expect(result()).toBe("DIRECT");
    expect(dialog()?.querySelector(".pathbuild-count")?.textContent).toBe("0 hops");
  });

  it("has the usual paths one click each, with what each is for in its title, and Use gives the path to the field", async () => {
    const wrapper = make();
    await open(wrapper);
    expect(all(".pathbuild-presets button").map((b) => [(b.textContent ?? "").trim(), b.title])).toEqual([
      ["Direct", "No digipeater"],
      ["WIDE1-1", "The fill-in digipeater near you"],
      ["WIDE2-1", "Fixed station"],
      ["WIDE2-2", "Two wide hops"],
      ["WIDE1-1,WIDE2-1", "Mobile station"],
    ]);
    await click(button("WIDE2-2"));
    expect(chips()).toEqual(["WIDE2-2"]);
    await click(button("Use"));
    expect(wrapper.emitted("use")).toEqual([["WIDE2-2"]]);
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(wrapper.find("button.pathbuild-open").element);
  });

  it("builds a path through a digipeater we hear, then one seen after it in the routes", async () => {
    const wrapper = make({ value: "DIRECT" });
    await open(wrapper);
    expect(heading()).toBe("Digipeaters heard");
    expect(choices()).toEqual(["OH2RDK-7"]);
    expect(all(".pathbuild-choice .pathbuild-num").map((n) => n.textContent ?? "")).toEqual(["12", "2 min", "3.2 km"]);
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
    expect(chips()).toEqual(["OH2RDK-7", "OH2RCH-2"]);
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
    expect(chips()).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    await type("WIDE2-1");
    dialog()
      ?.querySelector(".pathbuild-type input")
      ?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flush();
    expect(chips()).toEqual(["OH2RDK-7", "OH2RCH-2", "WIDE2-1"]);
    await type("OH2 RCH");
    expect(button("Add")?.disabled).toBe(true);
    await type("DIRECT");
    expect(button("Add")?.disabled).toBe(true);
    await type("A1,B2,C3,D4,E5,F6");
    expect(button("Add")?.disabled).toBe(true);
    await type("A1,B2,C3,D4,E5");
    expect(button("Add")?.disabled).toBe(false);
    await click(button("Add"));
    expect(chips()).toHaveLength(8);
    await type("G7");
    expect(button("Add")?.disabled).toBe(true);
  });

  it("takes a hop out with its ×", async () => {
    const wrapper = make({ value: "OH2RDK-7,OH2RCH-2" });
    await open(wrapper);
    await click(all(".pathbuild-x")[0]);
    expect(chips()).toEqual(["OH2RCH-2"]);
    expect(all(".pathbuild-x")[0]?.getAttribute("aria-label")).toBe("Remove OH2RCH-2");
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
      await click(button("WIDE2-2"));
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
});
