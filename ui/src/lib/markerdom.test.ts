import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildMarkerDom, paintMarker } from "@/lib/markerdom";
import { cssRule } from "@/test/css";
import { station, weatherStation } from "@/test/fixtures";

describe("the marker of a station", () => {
  it("shows the call as text and the symbol as sprite layers", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("<b>OH2PU-9</b>"), { fade: 0, selected: false, direct: false });
    expect(dom.label.textContent).toBe("<b>OH2PU-9</b>");
    expect(dom.label.children).toHaveLength(0);
    expect(dom.icon.querySelectorAll(".stn-layer")).toHaveLength(1);
  });
  it("stacks the overlay character over the alternate symbol", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("OH2RDG", { symbol_table: "N", symbol_code: "#" }), { fade: 0, selected: false, direct: false });
    expect(dom.icon.querySelectorAll(".stn-layer")).toHaveLength(2);
  });
  it("is a plain dot without a symbol", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("X", { symbol_table: "", symbol_code: "" }), { fade: 0, selected: false, direct: false });
    expect(dom.icon.classList.contains("stn-plain")).toBe(true);
  });
  it("tells our own station, the selected one and how faded it is by classes", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("ME", { is_me: true }), { fade: 0, selected: true, direct: false });
    expect([...dom.root.classList]).toEqual(expect.arrayContaining(["stn--me", "stn--selected"]));
    expect([...dom.root.classList].some((c) => c.startsWith("stn--fade"))).toBe(false);
    paintMarker(dom, station("A"), { fade: 1, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--fade-1")).toBe(true);
    expect(dom.root.classList.contains("stn--me")).toBe(false);
    paintMarker(dom, station("A"), { fade: 3, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--fade-3")).toBe(true);
    expect(dom.root.classList.contains("stn--fade-1")).toBe(false);
    paintMarker(dom, station("A"), { fade: 0, selected: false, direct: false });
    expect([...dom.root.classList].some((c) => c.startsWith("stn--fade"))).toBe(false);
  });
  it("marks an object of ours by a class and says so in its name", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("LEADER", { kind: "object", own: true }), { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--own")).toBe(true);
    expect(dom.root.classList.contains("stn--me")).toBe(false);
    expect(dom.root.getAttribute("aria-label")).toBe("LEADER: Car (ours)");
    paintMarker(dom, station("LEADER", { kind: "object", own: false }), { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--own")).toBe(false);
  });
  it("puts a ring on a station heard direct and says so in its name", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("OH2PU-9"), { fade: 0, selected: false, direct: true });
    expect(dom.root.classList.contains("stn--direct")).toBe(true);
    expect(dom.root.getAttribute("aria-label")).toBe("OH2PU-9: Car, heard direct");
    paintMarker(dom, station("OH2PU-9"), { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--direct")).toBe(false);
    expect(dom.root.getAttribute("aria-label")).toBe("OH2PU-9: Car");
  });
  it("draws a station known from the internet alone with its own class, and says so in its name; one also heard on the radio is drawn as any other", () => {
    const dom = buildMarkerDom();
    const net = station("OH2NET", { heard_rf: 0, heard_is: 3, last_rf_at: null, last_is_at: "2026-10-21T11:59:00Z" });
    paintMarker(dom, net, { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--net")).toBe(true);
    expect(dom.root.getAttribute("aria-label")).toBe("OH2NET: Car, heard over the internet");
    paintMarker(dom, { ...net, heard_rf: 1 }, { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--net")).toBe(false);
    expect(dom.root.getAttribute("aria-label")).toBe("OH2NET: Car");
    paintMarker(dom, { ...net, heard_rf: 0, heard_rf_gated: 1, heard_is: 0 }, { fade: 0, selected: false, direct: false });
    expect(dom.root.classList.contains("stn--net")).toBe(false);
  });
  it("has a dotted outline and an italic call for the class of the internet, in colours of both themes, and lets the selected marker be drawn as any other", () => {
    const icon = cssRule(".stn--net .stn-icon");
    expect(icon).toMatch(/outline:\s*2px dotted var\(--muted\)/);
    expect(icon).toMatch(/background:\s*var\(--map-halo\)/);
    expect(cssRule(".stn--net .stn-label")).toMatch(/font-style:\s*italic/);
    expect(cssRule(".stn--selected .stn-icon")).toMatch(/outline:\s*2px solid #ff6d00/);
    const tokens = readFileSync(resolve(__dirname, "../styles/tokens.css"), "utf8");
    const dark = tokens.slice(tokens.indexOf("prefers-color-scheme: dark"));
    expect(tokens.slice(0, tokens.indexOf("prefers-color-scheme: dark"))).toMatch(/--muted:/);
    expect(dark).toMatch(/--muted:/);
    expect(dark).toMatch(/--map-halo:/);
  });
  it("shows the characters of a signpost over its symbol, as text, and nothing for a station that is none", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("I91 3N", { kind: "item", symbol_table: "\\", symbol_code: "m", sign: "<55>" }), { fade: 0, selected: false, direct: false });
    expect(dom.sign.textContent).toBe("<55>");
    expect(dom.sign.children).toHaveLength(0);
    expect(dom.root.classList.contains("stn--sign")).toBe(true);
    paintMarker(dom, station("OH2PU-9"), { fade: 0, selected: false, direct: false });
    expect(dom.sign.textContent).toBe("");
    expect(dom.root.classList.contains("stn--sign")).toBe(false);
  });
  it("keeps the weather symbol of a weather station and puts its temperature in its name", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, weatherStation("OH2MUI"), { fade: 0, selected: false, direct: false });
    expect(dom.icon.querySelectorAll(".stn-layer")).toHaveLength(1);
    expect(dom.root.getAttribute("aria-label")).toBe("OH2MUI: Weather station, 10.0 °C");
  });
  it("makes the layers again only when the symbol changes", () => {
    const dom = buildMarkerDom();
    paintMarker(dom, station("A"), { fade: 0, selected: false, direct: false });
    const first = dom.icon.firstElementChild;
    paintMarker(dom, station("A", { lat: 61 }), { fade: 0, selected: false, direct: false });
    expect(dom.icon.firstElementChild).toBe(first);
    paintMarker(dom, station("A", { symbol_code: "-" }), { fade: 0, selected: false, direct: false });
    expect(dom.icon.firstElementChild).not.toBe(first);
  });
});
