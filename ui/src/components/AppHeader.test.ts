import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import AppHeader from "@/components/AppHeader.vue";
import { t } from "@/i18n";
import { headerPills } from "@/lib/pills";
import { cssRule, mediaRule } from "@/test/css";
import { gpsState, igateState } from "@/test/fixtures";

const header = (props: Partial<InstanceType<typeof AppHeader>["$props"]> = {}) => mount(AppHeader, { props: { call: "OH2GBA", unread: 0, ...props } });

describe("AppHeader", () => {
  it("has the title as a link to the project page that opens in a new tab and cannot reach back to the page", () => {
    const link = header().find("h1 a");
    expect(link.text()).toBe("NeoAPRS");
    expect(link.attributes("href")).toBe("https://oh2gba.github.io/neoaprs/");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener");
  });

  it("makes the link look like the title: its colour and weight, no underline, an underline on hover and a ring for the keyboard", () => {
    expect(header().find("h1 a").classes()).toContain("brand");
    const rule = cssRule(".brand");
    expect(rule).toMatch(/color:\s*inherit/);
    expect(rule).toMatch(/font-weight:\s*inherit/);
    expect(rule).toMatch(/text-decoration:\s*none/);
    expect(cssRule(".brand:hover")).toMatch(/text-decoration:\s*underline/);
    expect(cssRule(".brand:focus-visible")).toMatch(/outline:\s*2px solid var\(--accent\)/);
  });

  it("does not show our call, the radio, the version or an update: those are in the footer of the panel", () => {
    const wrapper = header({ unread: 3 });
    expect(wrapper.find(".call").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("OH2GBA");
    expect(wrapper.text()).not.toMatch(/radio|daemon|update|v\d/i);
    expect(wrapper.find(".status").exists()).toBe(false);
    expect(wrapper.find(".version").exists()).toBe(false);
    expect(wrapper.find(".update").exists()).toBe(false);
  });

  it("shows the number of messages not seen as a button of its own, and a click asks for them", async () => {
    const wrapper = header({ unread: 2 });
    const mail = wrapper.find("button.headmail");
    expect(mail.text()).toContain("2");
    expect(mail.attributes("title")).toBe("2 messages not seen yet: open the messages");
    expect(mail.find(".sr-only").text()).toBe("2 messages not seen yet");
    expect(mail.element.parentElement).toBe(wrapper.element);
    await mail.trigger("click");
    expect(wrapper.emitted("messages")).toHaveLength(1);
  });

  it("shows nothing when all are seen", () => {
    expect(header().find(".headmail").exists()).toBe(false);
  });

  it("puts the badge at the right of the line, away from the title", () => {
    expect(cssRule(".headmail.badge")).toMatch(/margin:\s*0 0 0 auto/);
  });

  it('shows an amber button "no call set" while the call is empty, and a click asks for the setup guide', async () => {
    const wrapper = header({ call: "" });
    const button = wrapper.find(".nocall");
    expect(button.text()).toBe("no call set");
    await button.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(header().find(".nocall").exists()).toBe(false);
    expect(header({ call: null }).find(".nocall").exists()).toBe(false);
  });

  const pills = (values: Record<string, string>, gps: Parameters<typeof headerPills>[1] = null, igate: Parameters<typeof headerPills>[2] = null) =>
    headerPills(values, gps, igate);

  it("shows the marks before the count of messages, in the one TagMark style, each a button with a hover title", () => {
    const wrapper = header({ unread: 2, pills: pills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()) });
    const marks = wrapper.findAll(".headpills .tag");
    expect(marks.map((m) => m.text())).toEqual(["RX only", "Internet", "GPS"]);
    expect(marks.every((m) => m.element.tagName === "BUTTON" && m.classes().includes("tag"))).toBe(true);
    expect(marks.every((m) => (m.attributes("title") ?? "") !== "")).toBe(true);
    expect(wrapper.find(".headpills").element.nextElementSibling?.classList.contains("headmail")).toBe(true);
    expect(wrapper.find(".headpills").element.previousElementSibling?.tagName).toBe("H1");
  });

  it("has RX only in warn while transmitting is off, and the others as they are: Beacon off neutral only while transmitting is on, Internet info, GPS ok with a fix and warn without", () => {
    const rx = header({ pills: pills({ "station/transmit": "false", "beacon/interval_min": "0" }) }).findAll(".headpills .tag");
    expect(rx.map((m) => m.text())).toEqual(["RX only"]);
    expect(rx[0]?.classes()).toContain("tag-warn");
    expect(rx[0]?.classes()).toContain("rxonly");
    const off = header({ pills: pills({ "station/transmit": "true", "beacon/interval_min": "0" }) }).findAll(".headpills .tag");
    expect(off.map((m) => m.text())).toEqual(["Beacon off"]);
    expect(off[0]?.classes()).toContain("tag-neutral");
    const net = header({ pills: pills({}, null, igateState()) }).findAll(".headpills .tag");
    expect(net.map((m) => [m.text(), m.classes().includes("tag-info")])).toEqual([["Internet", true]]);
    const fix = header({ pills: pills({ "gps/source": "gpsd" }, gpsState({ state: "fix" })) }).find(".headpills .pill-gps");
    expect(fix.classes()).toContain("tag-ok");
    const none = header({ pills: pills({ "gps/source": "gpsd" }, gpsState({ state: "no_fix" })) }).find(".headpills .pill-gps");
    expect(none.classes()).toContain("tag-warn");
    expect(header({ pills: [] }).find(".headpills").exists()).toBe(false);
  });

  it("opens the place where a mark is set when it is clicked: Settings for RX only and Internet, the Beacon tab for Beacon off and GPS", async () => {
    const wrapper = header({ pills: pills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()) });
    for (const mark of wrapper.findAll(".headpills .tag")) await mark.trigger("click");
    expect(wrapper.emitted("open")).toEqual([["settings"], ["settings"], ["beacon"]]);
  });

  it("says in the hover title what a mark means and where it is set, in a few words", () => {
    const titles = Object.fromEntries(headerPills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()).map((p) => [p.id, t(p.title)]));
    expect(titles.rx).toBe("Nothing is sent. Settings → Radio → RX only");
    expect(titles.internet).toContain("Settings → Internet");
    expect(titles.gps).toContain("Beacon tab");
  });

  it("lets the marks fold as whole marks and never pushes the count off: the row is one mark high and wraps, Internet is the first to fold, the count does not shrink", () => {
    expect(cssRule(".headpills")).toMatch(/overflow:\s*hidden/);
    expect(cssRule(".headpills")).toMatch(/min-width:\s*0/);
    expect(cssRule(".headpills")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".headpills")).toMatch(/height:\s*18px/);
    expect(cssRule(".headpill")).toMatch(/flex:\s*none/);
    expect(cssRule(".headpill.pill-internet")).toMatch(/order:\s*1/);
    expect(cssRule(".headmail")).toMatch(/flex:\s*none/);
  });

  it("has no hit area of a finger around the badge of the count only where a mark is", () => {
    expect(mediaRule("(pointer: coarse)", ".nocall::after")).toContain("inset");
  });

  it("is as high with a badge and a button as without them", () => {
    expect(cssRule(".appheader")).toMatch(/min-height:\s*34px/);
  });
});
