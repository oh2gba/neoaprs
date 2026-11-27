import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import PairInfo from "@/components/PairInfo.vue";

const mounted: { unmount(): void }[] = [];
function info(slow: string[] = [], first = "Packet", second = "HF 40 m") {
  const wrapper = mount(PairInfo, { props: { first, second, call: "OH2GBA-15", slow }, attachTo: document.body });
  mounted.push(wrapper);
  return wrapper;
}
const dialog = () => document.querySelector<HTMLElement>("[role='dialog']");
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = "";
});

describe("PairInfo", () => {
  it("is the notes' (i): a label for screen readers and no hover text", () => {
    const button = info().find("button.info-toggle");
    expect(button.text()).toBe("i");
    expect(button.attributes("aria-label")).toBe("How passing between Packet and HF 40 m works");
    expect(button.attributes("title")).toBeUndefined();
    expect(dialog()).toBeNull();
  });

  it("opens a dialog titled by the two radios, with the pair's call in both pictures", async () => {
    await info().find("button").trigger("click");
    const shown = dialog() as HTMLElement;
    expect(document.getElementById(shown.getAttribute("aria-labelledby") ?? "")?.textContent).toBe(
      "Between Packet and HF 40 m",
    );
    const [main, stop] = [...shown.querySelectorAll("svg.pairpic")] as SVGElement[];
    expect(main?.getAttribute("role")).toBe("img");
    expect(main?.getAttribute("aria-label")).toContain("OH2GBA-15");
    const drawn = main?.textContent ?? "";
    for (const words of [
      "OH2GBA-15,WIDE2-2",
      "OH2GBA-15*,WIDE2-2",
      "a station",
      "Packet",
      "stations",
      "HF 40 m",
      "your station",
    ])
      expect(drawn).toContain(words);
    expect(stop?.textContent).toContain("WIDE2-2");
    expect(stop?.textContent).not.toContain("OH2GBA-15");
  });

  it("says in three lines what crosses and what does not", async () => {
    await info().find("button").trigger("click");
    const lines = [...(dialog() as HTMLElement).querySelectorAll("p")].map((p) => p.textContent);
    expect(lines).toEqual([
      "A station that puts OH2GBA-15 in its path is sent on once on the other radio. It works both ways.",
      "A position, a status, a message or an ack crosses.",
      "Nothing crosses without OH2GBA-15 in the path, and a message addressed to you stays with you.",
    ]);
  });

  it("says the limit of a slow radio only for a pair that has one", async () => {
    await info(["HF 40 m"]).find("button").trigger("click");
    expect(dialog()?.textContent).toContain("Onto HF 40 m, at most 4 packets in 5 minutes.");
    mounted.splice(0).forEach((w) => w.unmount());
    await info([], "Packet", "Packet 2").find("button").trigger("click");
    expect(dialog()?.textContent).not.toContain("at most");
  });

  it("cuts a long radio name in the picture, never in the title", async () => {
    await info([], "Packet", "Kenwood TM-D710").find("button").trigger("click");
    expect(document.getElementById(dialog()?.getAttribute("aria-labelledby") ?? "")?.textContent).toBe(
      "Between Packet and Kenwood TM-D710",
    );
    expect(dialog()?.querySelector("svg.pairpic")?.textContent).toContain("Kenwood TM…");
  });

  it("closes on Esc and on the cross, and gives the focus back to the (i)", async () => {
    const wrapper = info();
    const button = wrapper.find("button");
    await button.trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(dialog());
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(button.element);
    await button.trigger("click");
    await flushPromises();
    document.querySelector<HTMLButtonElement>("[role='dialog'] .xbtn")?.click();
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(button.element);
  });
});
