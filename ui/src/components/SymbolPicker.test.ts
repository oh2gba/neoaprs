import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SymbolPicker from "@/components/SymbolPicker.vue";
import { ALL_SYMBOLS } from "@/lib/symbolpicker";

function picker(table = "/", code = "-") {
  const host = document.createElement("div");
  document.body.appendChild(host);
  return mount(SymbolPicker, { props: { table, code }, attachTo: host });
}

const names = (wrapper: ReturnType<typeof picker>) => wrapper.findAll(".sympick-symbol").map((b) => b.text());

describe("SymbolPicker", () => {
  it("is a dialog with a search box that has the focus, the usual symbols first and then all of them with their pictures", () => {
    const wrapper = picker();
    expect(wrapper.find(".sympick").attributes("role")).toBe("dialog");
    expect(wrapper.find(".sympick").attributes("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(wrapper.find("input[type=search]").element);
    expect(wrapper.findAll("h3").map((h) => h.text())).toEqual(["Usual", "All"]);
    const usual = wrapper.findAll("[aria-label='Usual symbols'] .sympick-symbol");
    expect(usual).toHaveLength(12);
    expect(usual.slice(0, 2).map((b) => b.text())).toEqual(["House", "Car"]);
    const all = wrapper.findAll("[aria-label='All symbols'] .sympick-symbol");
    expect(all).toHaveLength(ALL_SYMBOLS.length);
    expect(all.every((b) => b.find(".symicon .stn-layer").exists())).toBe(true);
    wrapper.unmount();
  });

  it("lists the whole primary and the whole alternate table, without the codes that are reserved", () => {
    expect(ALL_SYMBOLS.filter((s) => s.table === "/").length).toBeGreaterThanOrEqual(85);
    expect(ALL_SYMBOLS.filter((s) => s.table === "\\").length).toBeGreaterThanOrEqual(75);
    expect(ALL_SYMBOLS.some((s) => s.name === "reserved" || s.name === "TNC stream switch")).toBe(false);
    expect(ALL_SYMBOLS.find((s) => s.table === "/" && s.code === "-")?.name).toBe("House");
    expect(ALL_SYMBOLS.find((s) => s.table === "\\" && s.code === "#")?.name).toBe("Digipeater");
  });

  it("marks the symbol in use, in the usual symbols and in all of them", () => {
    const wrapper = picker("/", "-");
    const marked = wrapper.findAll(".sympick-symbol[aria-pressed='true']");
    expect(marked.map((b) => b.text())).toEqual(["House", "House"]);
    wrapper.unmount();
    const alternate = picker("S", "#");
    expect(alternate.findAll(".sympick-symbol[aria-pressed='true']").map((b) => b.text())).toEqual(["Digipeater"]);
    expect(alternate.find(".sympick-symbol[aria-pressed='true']").element.closest("[aria-label='All symbols']")).not.toBeNull();
    alternate.unmount();
  });

  it("finds a symbol by a word of its name and hides the usual ones while it searches", async () => {
    const wrapper = picker();
    const search = wrapper.find<HTMLInputElement>("input[type=search]");
    await search.setValue("house");
    expect(names(wrapper)).toEqual(expect.arrayContaining(["House", "House (HF)"]));
    expect(names(wrapper).every((n) => n.toLowerCase().includes("house"))).toBe(true);
    expect(wrapper.findAll("h3")).toHaveLength(0);
    await search.setValue("car");
    expect(names(wrapper)).toContain("Car");
    await search.setValue("digi");
    expect(names(wrapper)).toEqual(["Digipeater", "Digipeater"]);
    await search.setValue("wx");
    expect(names(wrapper)).toContain("Weather station");
    await search.setValue("  ");
    expect(wrapper.findAll("h3")).toHaveLength(2);
    wrapper.unmount();
  });

  it("says so when no symbol is like that", async () => {
    const wrapper = picker();
    await wrapper.find("input[type=search]").setValue("zzzz");
    expect(names(wrapper)).toEqual([]);
    expect(wrapper.find(".empty").text()).toBe("No symbol like that.");
    wrapper.unmount();
  });

  it("chooses a symbol with the table and the code underneath", async () => {
    const wrapper = picker();
    await wrapper.find("input[type=search]").setValue("house (hf)");
    await wrapper.find(".sympick-symbol").trigger("click");
    expect(wrapper.emitted("pick")).toEqual([["\\", "-"]]);
    wrapper.unmount();
  });

  it("closes with Esc, with the Close button and with a click outside, and not with a click inside", async () => {
    const wrapper = picker();
    await wrapper.find(".sympick").trigger("pointerdown");
    expect(wrapper.emitted("close")).toBeUndefined();
    await wrapper.find(".sympick-backdrop").trigger("pointerdown");
    expect(wrapper.emitted("close")).toHaveLength(1);
    await wrapper.find("input[type=search]").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("close")).toHaveLength(2);
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Close")
      ?.trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(3);
    wrapper.unmount();
  });
});
