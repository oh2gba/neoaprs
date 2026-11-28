import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import AppHeader from "@/components/AppHeader.vue";
import { t } from "@/i18n";
import { headerPills, type HeaderPill } from "@/lib/pills";
import { cssRule, mediaRule } from "@/test/css";
import { pageRadios } from "@/lib/radios";
import { NOW, gpsState, igateState, radioRow, radiosTopic } from "@/test/fixtures";

const header = (props: Partial<InstanceType<typeof AppHeader>["$props"]> = {}) =>
  mount(AppHeader, { props: { call: "OH2GBA", unread: 0, ...props } });

describe("AppHeader", () => {
  it("gives the marks a row of their own on a phone while no call is set, as wide as the header, so that none is shortened", () => {
    expect(cssRule(".size-phone .appheader:has(> .nocall)")).toMatch(/flex-wrap:\s*wrap/);
    const row = cssRule(".size-phone .appheader:has(> .nocall) > .headpills");
    expect(row).toMatch(/order:\s*1/);
    expect(row).toMatch(/flex-basis:\s*100%/);
  });

  it("has the title as a link to the project page that opens in a new tab and cannot reach back to the page", () => {
    const link = header().find("h1 a");
    expect(link.text()).toBe("NeoAPRS");
    expect(link.attributes("href")).toBe("https://neo.oh2gba.eu/");
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

  it("does not show our call or the version, and no mark of its own: the marks are given to it", () => {
    const wrapper = header({ unread: 3 });
    expect(wrapper.find(".call").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("OH2GBA");
    expect(wrapper.text()).not.toMatch(/radio|daemon|update|v\d/i);
    expect(wrapper.find(".headpills").exists()).toBe(false);
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

  it('shows a button "no call set" on the warn plate while the call is empty, and a click asks for the setup guide', async () => {
    const wrapper = header({ call: "" });
    const button = wrapper.find(".nocall");
    expect(button.text()).toBe("no call set");
    await button.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(header().find(".nocall").exists()).toBe(false);
    expect(header({ call: null }).find(".nocall").exists()).toBe(false);
  });

  const pills = (
    values: Record<string, string>,
    gps: Parameters<typeof headerPills>[1] = null,
    igate: Parameters<typeof headerPills>[2] = null,
  ) => headerPills(values, gps, igate);

  it("shows the marks before the count of messages, in the one TagMark style, each a button with a hover title", () => {
    const wrapper = header({
      unread: 2,
      pills: pills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()),
    });
    const marks = wrapper.findAll(".headpills .tag");
    expect(marks.map((m) => m.text())).toEqual(["GPS", "Internet"]);
    expect(marks.every((m) => m.element.tagName === "BUTTON" && m.classes().includes("tag"))).toBe(true);
    expect(marks.every((m) => (m.attributes("title") ?? "") !== "")).toBe(true);
    expect(wrapper.find(".headpills").element.nextElementSibling?.classList.contains("headmail")).toBe(true);
    expect(wrapper.find(".headpills").element.previousElementSibling?.tagName).toBe("H1");
  });

  it("shows the Daemon mark as a mark that says and does not open, and the Radio mark as a button that opens Settings → Radio with its group flashed", async () => {
    const link = { connection: "closed", now: 0, inApp: false, radios: [], told: false } as const;
    const wrapper = header({ pills: headerPills({}, null, null, null, link) });
    const [daemon, radio] = wrapper.findAll(".headpills .tag");
    expect([
      daemon?.element.tagName,
      daemon?.text(),
      daemon?.classes().includes("tag-bad"),
      daemon?.attributes("role"),
    ]).toEqual(["SPAN", "NeoAPRS: offline", true, "status"]);
    expect([radio?.element.tagName, radio?.text()]).toEqual(["BUTTON", "Radio: waiting…"]);
    await daemon?.trigger("click");
    expect(wrapper.emitted("open")).toBeUndefined();
    await radio?.trigger("click");
    expect(wrapper.emitted("open")).toEqual([["settings", "set-radio-add"]]);
  });

  it("has no RX only mark, and the others as they are: Beacon off neutral whatever RX only is, Internet info, GPS ok with a fix and warn without", () => {
    for (const transmit of ["false", "true"]) {
      const off = header({ pills: pills({ "station/transmit": transmit, "beacon/interval_min": "0" }) }).findAll(
        ".headpills .tag",
      );
      expect(off.map((m) => m.text())).toEqual(["Beacon off"]);
      expect(off[0]?.classes()).toContain("tag-neutral");
    }
    expect(
      header({ pills: pills({ "station/transmit": "false" }) })
        .find(".rxonly")
        .exists(),
    ).toBe(false);
    const net = header({ pills: pills({}, null, igateState()) }).findAll(".headpills .tag");
    expect(net.map((m) => [m.text(), m.classes().includes("tag-info")])).toEqual([["Internet", true]]);
    const fix = header({ pills: pills({ "gps/source": "gpsd" }, gpsState({ state: "fix" })) }).find(
      ".headpills .pill-gps",
    );
    expect(fix.classes()).toContain("tag-ok");
    const none = header({ pills: pills({ "gps/source": "gpsd" }, gpsState({ state: "no_fix" })) }).find(
      ".headpills .pill-gps",
    );
    expect(none.classes()).toContain("tag-warn");
    expect(header({ pills: [] }).find(".headpills").exists()).toBe(false);
  });

  it("opens the place where a mark is set when it is clicked, and says the control to flash: Settings for Internet, the My station tab for GPS", async () => {
    const wrapper = header({ pills: pills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()) });
    for (const mark of wrapper.findAll(".headpills .tag")) await mark.trigger("click");
    expect(wrapper.emitted("open")).toEqual([
      ["beacon", "set-gps-source"],
      ["settings", "set-igate-enabled"],
    ]);
  });

  it("says in the hover title what a mark means and where it is set, in a few words", () => {
    const titles = Object.fromEntries(
      headerPills({ "station/transmit": "false", "gps/source": "gpsd" }, null, igateState()).map((p) => [
        p.id,
        t(p.title),
      ]),
    );
    expect(titles.internet).toContain("Settings → Internet");
    expect(titles.gps).toContain("My station tab");
  });

  it("lets the marks fold as whole marks and never pushes the count off: the row is one mark high and wraps, the last mark, Internet, is the first to fold, the count does not shrink", () => {
    expect(cssRule(".headpills")).toMatch(/overflow:\s*hidden/);
    expect(cssRule(".headpills")).toMatch(/min-width:\s*0/);
    expect(cssRule(".headpills")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".headpills")).toMatch(/height:\s*var\(--tag-h\)/);
    expect(cssRule(".headpill")).toMatch(/flex:\s*none/);
    expect(cssRule(".headmail")).toMatch(/flex:\s*none/);
  });

  it("has no hit area of a finger around the badge of the count only where a mark is", () => {
    expect(mediaRule("(pointer: coarse)", ".nocall::after")).toContain("inset");
  });

  it("keeps the finger areas of the count and the switch apart on a phone, and shortens no call set before the switch", () => {
    const reach = (selector: string, side: "left" | "right"): number => {
      const insets = [...mediaRule("(pointer: coarse)", selector).matchAll(/inset:\s*([^;]+)/g)];
      const parts = (insets.at(-1)?.[1] ?? "").trim().split(/\s+/);
      const four = [parts[0], parts[1] ?? parts[0], parts[2] ?? parts[0], parts[3] ?? parts[1] ?? parts[0]];
      return -parseFloat(four[side === "left" ? 3 : 1] ?? "0");
    };
    const between = parseFloat(/gap:\s*(\d+)px/.exec(cssRule(".size-phone .appheader"))?.[1] ?? "0") + 6;
    expect(cssRule(".headmail ~ .rxswitch")).toMatch(/margin-left:\s*6px/);
    expect(reach(".headmail::after", "right") + reach(".rxswitch::after", "left")).toBeLessThanOrEqual(between);
    expect(cssRule(".nocall")).toMatch(/min-width:\s*0/);
    expect(cssRule(".nocall-text")).toMatch(/text-overflow:\s*ellipsis/);
    expect(header({ call: "" }).find(".nocall .nocall-text").exists()).toBe(true);
  });

  it("has the RX only switch last, after the count, and outside the marks that fold", async () => {
    const rx = { face: "tx", act: "toggle", title: "header.rx.tx_title", focus: "" } as const;
    const wrapper = header({ unread: 2, pills: pills({ "gps/source": "gpsd" }), rx });
    const button = wrapper.find("#rx-switch");
    expect(button.element.parentElement).toBe(wrapper.element);
    expect(wrapper.find(".appheader").element.lastElementChild).toBe(button.element);
    expect(button.element.previousElementSibling?.previousElementSibling?.classList.contains("headmail")).toBe(true);
    expect(wrapper.find(".headpills #rx-switch").exists()).toBe(false);
    expect(cssRule(".rxswitch")).toMatch(/flex:\s*none/);
    expect(cssRule(".headmail ~ .rxswitch")).toMatch(/margin-left:\s*6px/);
    expect(mediaRule("(pointer: coarse)", ".rxswitch::after")).toContain("inset");
    await button.trigger("click");
    expect(wrapper.emitted("transmit")).toEqual([[false]]);
    expect(header().find("#rx-switch").exists()).toBe(false);
  });

  it("is as high with a badge and a button as without them", () => {
    expect(cssRule(".appheader")).toMatch(/min-height:\s*44px/);
  });

  it("draws its marks, the count and the switch larger than the page's other tags: as high as a button, in the body's text size, by the tag's size tokens", () => {
    expect(cssRule(".tag")).toMatch(/height:\s*var\(--tag-h\)/);
    expect(cssRule(".tag")).toMatch(/font-size:\s*var\(--tag-font\)/);
    expect(cssRule(".tag")).toMatch(/padding:\s*0 var\(--tag-pad\)/);
    expect(cssRule(":root")).toMatch(/--tag-h:\s*18px/);
    expect(cssRule(":root")).toMatch(/--tag-font:\s*11px/);
    expect(cssRule(".appheader")).toMatch(/--tag-h:\s*var\(--control-h\)/);
    expect(cssRule(".appheader")).toMatch(/--tag-font:\s*14px/);
    expect(cssRule("body")).toMatch(/font:\s*14px/);
  });
});

describe("the header with any number of radios", () => {
  const SIX = [
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "mercury", {
      name: "20 m",
      number: 2,
      state: "waiting",
      problem: { code: "radio.not_connected", params: {} },
    }),
    radioRow(5, "kantronics", { name: "Portable", number: 3 }),
    radioRow(6, "dummy", { name: "Bench", number: 4 }),
  ];
  const marksOf = (rows = SIX) =>
    headerPills({}, null, null, null, {
      connection: "open",
      now: NOW,
      inApp: true,
      radios: pageRadios(radiosTopic(...rows), null),
      told: true,
    });

  it("has one mark for six radios, which names the one in trouble and opens its box, its title each radio in the words of its own mark", async () => {
    const wrapper = header({ pills: marksOf() });
    const radios = wrapper
      .findAll(".headpill")
      .filter((mark) => mark.classes().some((c) => c.startsWith("pill-radio")));
    expect(radios.map((mark) => [mark.text(), mark.classes()])).toEqual([
      ["20 m: not connected", ["tag", "tag-warn", "headpill", "pill-radios"]],
    ]);
    expect(radios[0]?.attributes("title")).toBe(
      "Packet: connected; Mercury: connected; Shack: connected; 20 m: not connected; Portable: connected; Bench: connected. Settings → Radio",
    );
    await radios[0]?.trigger("click");
    expect(wrapper.emitted("open")).toEqual([["settings", "set-radio-4-enabled"]]);
  });

  it("has two marks by name for two radios, and one by name for one", () => {
    const two = header({ pills: marksOf(SIX.slice(0, 2)) });
    expect(two.findAll(".headpill").map((mark) => mark.text())).toEqual(["Packet", "Mercury"]);
    const named = header({ pills: marksOf([SIX[2], SIX[4]]) });
    expect(named.findAll(".headpill").map((mark) => [mark.text(), mark.attributes("title")])).toEqual([
      ["Shack", "Shack: connected. Settings → Radio"],
      ["Portable", "Portable: connected. Settings → Radio"],
    ]); // a typed name stands before a colon, never inside a sentence
    const one = header({ pills: marksOf([SIX[0]]) });
    expect(one.findAll(".headpill").map((mark) => mark.text())).toEqual(["Packet"]);
    const shack = header({ pills: marksOf([SIX[2]]) });
    expect(shack.findAll(".headpill").map((mark) => [mark.text(), mark.attributes("title")])).toEqual([
      ["Shack", "Shack: connected. Settings → Radio"],
    ]);
  });
});

describe("the marks on a narrow row", () => {
  afterEach(() => vi.restoreAllMocks());

  /** Every mark 80 px wide and the row `room` px, as a browser would measure them. */
  function measured(room: number): void {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const width = this.classList.contains("headpills") ? room : this.classList.contains("tag") ? 80 : 0;
      return { width, height: 32, top: 0, left: 0, right: width, bottom: 32, x: 0, y: 0, toJSON: () => ({}) };
    });
  }
  const mark = (id: HeaderPill["id"], tone: "ok" | "warn" | "bad" | "info", text: HeaderPill["text"]): HeaderPill => ({
    id,
    text,
    title: "pill.daemon_title",
    tone,
    target: null,
    focus: "",
  });
  const shown = (wrapper: ReturnType<typeof header>) => wrapper.findAll(".headpills .headpill").map((m) => m.text());
  const DAEMON = mark("daemon", "ok", "pill.daemon");
  const OFFLINE = mark("daemon", "bad", "pill.daemon_offline");
  const GPS_OK = mark("gps", "ok", "pill.gps");
  const GPS_LOST = mark("gps", "warn", "pill.gps");
  const INTERNET = mark("internet", "info", "pill.internet");

  it("hide the connected NeoAPRS mark first, and keep it while it is offline", async () => {
    measured(100);
    const wrapper = header({ pills: [DAEMON, GPS_OK] });
    await nextTick();
    expect(shown(wrapper)).toEqual(["GPS"]);
    await wrapper.setProps({ pills: [OFFLINE, GPS_OK] });
    expect(shown(wrapper)).toEqual(["NeoAPRS: offline"]);
  });

  it("keep the marks in their order when a state changes, and hide those that are well before those in trouble", async () => {
    measured(2 * 80 + 8);
    const wrapper = header({ pills: [DAEMON, GPS_OK, INTERNET] });
    await nextTick();
    expect(shown(wrapper)).toEqual(["GPS", "Internet"]);
    await wrapper.setProps({ pills: [OFFLINE, GPS_LOST, INTERNET] });
    expect(shown(wrapper)).toEqual(["NeoAPRS: offline", "GPS"]);
    measured(3 * 80 + 2 * 8);
    await wrapper.setProps({ pills: [DAEMON, GPS_LOST, INTERNET] });
    expect(shown(wrapper)).toEqual(["NeoAPRS", "GPS", "Internet"]);
  });

  it("measure the marks in a copy that is hidden from the eye and from a screen reader", () => {
    const wrapper = header({ pills: [DAEMON, GPS_OK] });
    const copy = wrapper.find(".headpills-copy");
    expect(copy.attributes("aria-hidden")).toBe("true");
    expect(copy.findAll(".tag").map((m) => m.text())).toEqual(["NeoAPRS", "GPS"]);
    expect(cssRule(".headpills-copy")).toMatch(/visibility:\s*hidden/);
    expect(cssRule(".headpills-copy")).toMatch(/position:\s*fixed/);
  });
});
