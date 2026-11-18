import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RadioStatus from "@/components/RadioStatus.vue";
import { clockText } from "@/lib/format";
import { NOW, ago, fmRow, radioRow } from "@/test/fixtures";

const lines = (...texts: string[]) => texts.map((text, i) => ({ at: new Date(NOW - (texts.length - i) * 1000).toISOString(), text }));
const radio = (row: ReturnType<typeof fmRow>) => mount(RadioStatus, { props: { row, now: NOW } });

describe("RadioStatus", () => {
  it("has the state and one plain line in the heading of a fold, the line and the counters as its hover title, and no Reconnect", () => {
    const wrapper = radio(fmRow());
    const head = wrapper.find("summary.statushead");
    expect(head.find(".statetext").text()).toBe("connected");
    expect(head.find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(head.find(".tncstatus").attributes("title")).toBe("Last packet 30 s ago\n11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(head.find("button").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Reconnect");
    for (const word of ["Opened", "Bytes", "Frames", "Keep-alive", "Speed", "Last error", "Details"]) expect(wrapper.text()).not.toContain(word);
  });

  it("keeps the Terminal and what is given for the fold behind its arrow, closed unless the radio is not connected", async () => {
    const wrapper = mount(RadioStatus, { props: { row: fmRow(), now: NOW }, slots: { default: "<p class='fields'>the fields</p>" } });
    const fold = wrapper.find<HTMLDetailsElement>("details.radiostatus");
    expect(fold.element.open).toBe(false);
    expect(fold.find(".fields").exists()).toBe(true);
    expect(wrapper.findAll("summary").map((s) => s.find("button").exists())).toEqual([false, false]);
    expect(wrapper.findAll("summary")[1]?.text()).toBe("Terminal");
    expect(wrapper.findAll<HTMLDetailsElement>("details").map((d) => d.element.open)).toEqual([false, false]);
    await wrapper.setProps({ open: true });
    expect(fold.element.open).toBe(true);
    expect(mount(RadioStatus, { props: { row: fmRow(), now: NOW, open: true } }).find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(true);
  });

  it("says why it is not connected in the line, in the page's words of the daemon's code", () => {
    const wrapper = radio(
      fmRow({ state: "waiting", problem: { code: "radio.resource_held", params: { resource: "serial", holder: "Mercury 2", held_by: 2 } } }),
    );
    expect(wrapper.find(".statetext").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).not.toBe("");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("says since when a silent radio has said nothing", () => {
    const wrapper = radio(fmRow({ state: "silent", problem: { code: "radio.silent", params: { since: ago(7 * 60) } } }));
    expect(wrapper.find(".statetext").text()).toBe("silent");
    expect(wrapper.find(".statetext").classes()).toContain("tnc-silent");
    expect(wrapper.find(".tncstatus").text()).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says it is searching, and has nothing behind a click but the Terminal", () => {
    const wrapper = radio(fmRow({ state: "waiting", problem: { code: "radio.searching", params: {} } }));
    expect(wrapper.find(".tncstatus").text()).toBe("Searching for the radio…");
    expect(
      radio(fmRow())
        .findAll("details details")
        .map((d) => d.find("summary").text()),
    ).toEqual(["Terminal"]);
  });

  it("shows the lines of the terminal with their time in the viewer's time", () => {
    const at = new Date(NOW - 20_000).toISOString();
    const wrapper = radio(fmRow({ lines: [{ at, text: "NeoAPRS: opened /dev/brainbox_3" }] }));
    expect(wrapper.find(".tnclines").text()).toBe(`${clockText(at)}  NeoAPRS: opened /dev/brainbox_3`);
  });

  it("follows the end of the lines, unless they were scrolled up", async () => {
    const wrapper = mount(RadioStatus, { props: { row: fmRow(), now: NOW }, attachTo: document.body });
    const box = wrapper.find<HTMLElement>(".tnclines").element;
    Object.defineProperty(box, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(box, "clientHeight", { value: 100, configurable: true });
    box.scrollTop = 900;
    await wrapper.setProps({ row: fmRow({ lines: lines("a", "b", "c") }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(1000);
    box.scrollTop = 100;
    await wrapper.setProps({ row: fmRow({ lines: lines("a", "b", "c", "d") }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(100);
    wrapper.unmount();
  });

  it("says in a muted pill and in words that the Dummy radio's traffic is made up and nothing goes on the air", () => {
    const wrapper = radio(radioRow(1, "dummy"));
    expect(wrapper.find(".statetext").text()).toBe("Dummy");
    expect(wrapper.find(".statetext").classes()).toContain("tnc-dummy");
    expect(wrapper.find(".statetext").classes()).not.toContain("tnc-connected");
    expect(wrapper.find(".tncstatus").text()).toBe("Dummy radio: made-up traffic, nothing goes on the air");
  });

  it("is the Dummy's pill and line only while its line is open: before that it is a radio like the others", () => {
    const wrapper = radio(radioRow(1, "dummy", { state: "connecting" }));
    expect(wrapper.find(".statetext").text()).toBe("connecting");
    expect(wrapper.find(".tncstatus").text()).toBe("Connecting…");
  });

  it("has the terminal of the Dummy radio like any radio's", () => {
    const wrapper = radio(
      radioRow(1, "dummy", { lines: lines("NeoAPRS: opened the dummy radio", "Q1ABC>APRS:=6010.95N/02458.58E-Home station  ->  position") }),
    );
    expect(wrapper.find("pre.tnclines").text()).toContain("Q1ABC>APRS");
  });

  it("has no terminal for a radio whose type says it has none", () => {
    const row = radioRow(1, "kiss", { lines: lines("NeoAPRS: opened /dev/ttyUSB0") });
    expect(
      radio({ ...row, can: { ...row.can, terminal: false } })
        .find("pre.tnclines")
        .exists(),
    ).toBe(false);
    expect(radio(row).find("pre.tnclines").exists()).toBe(true);
  });
});
