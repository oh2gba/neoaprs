import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RadioStatus from "@/components/RadioStatus.vue";
import { clockText } from "@/lib/format";
import { NOW, ago, tncState } from "@/test/fixtures";

const lines = (...texts: string[]) => texts.map((text, i) => ({ at: new Date(NOW - (texts.length - i) * 1000).toISOString(), text }));
const radio = (tnc: ReturnType<typeof tncState> | null) => mount(RadioStatus, { props: { tnc, now: NOW } });

describe("RadioStatus", () => {
  it("has the state, one plain line and Reconnect in the heading of a fold, and none of the counters", () => {
    const wrapper = radio(tncState());
    const head = wrapper.find("summary.radiohead");
    expect(head.find(".statetext").text()).toBe("connected");
    expect(head.find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(head.find(".tncstatus").attributes("title")).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(head.find("button").text()).toBe("Reconnect");
    for (const word of ["Opened", "Bytes", "Frames", "Keep-alive", "Speed", "Last error", "Details"]) expect(wrapper.text()).not.toContain(word);
  });

  it("keeps the Terminal and what is given for the fold behind its arrow, closed unless the radio is not connected", async () => {
    const wrapper = mount(RadioStatus, { props: { tnc: tncState(), now: NOW }, slots: { default: "<p class='fields'>the fields</p>" } });
    const fold = wrapper.find<HTMLDetailsElement>("details.radiostatus");
    expect(fold.element.open).toBe(false);
    expect(fold.find(".fields").exists()).toBe(true);
    expect(wrapper.findAll("summary").map((s) => s.find("button").exists() || s.text())).toEqual([true, "Terminal"]);
    expect(wrapper.findAll<HTMLDetailsElement>("details").map((d) => d.element.open)).toEqual([false, false]);
    await wrapper.setProps({ open: true });
    expect(fold.element.open).toBe(true);
    expect(mount(RadioStatus, { props: { tnc: tncState(), now: NOW, open: true } }).find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(true);
  });

  it("shows what is given for the fold without the line before the daemon has told the radio", () => {
    const wrapper = mount(RadioStatus, { props: { tnc: null, now: NOW }, slots: { default: "<p class='fields'>the fields</p>" } });
    expect(wrapper.find(".fields").exists()).toBe(true);
    expect(wrapper.find("details").exists()).toBe(false);
  });

  it("says why it is not connected in the line, once", () => {
    const wrapper = radio(tncState({ state: "waiting", problem: "no KISS frames on /dev/brainbox_3", last_error: "busy" }));
    expect(wrapper.find(".statetext").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).toBe("Not connected: no KISS frames on /dev/brainbox_3");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("has the problem of a line that is open as a line of its own", () => {
    const wrapper = radio(tncState({ problem: "no KISS frames on /dev/brainbox_3" }));
    expect(wrapper.find(".tncstatus").text()).toContain("Last packet");
    expect(wrapper.find(".problem").text()).toBe("no KISS frames on /dev/brainbox_3");
  });

  it("says since when a silent radio has said nothing", () => {
    const wrapper = radio(tncState({ state: "silent", describe: "silent since 09:00 (7 min)", silent_since: ago(7 * 60) }));
    expect(wrapper.find(".statetext").text()).toBe("silent");
    expect(wrapper.find(".statetext").classes()).toContain("tnc-silent");
    expect(wrapper.find(".tncstatus").text()).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says it is searching and lists the ports behind a click", () => {
    const wrapper = radio(
      tncState({ state: "waiting", path: "", describe: "listening on /dev/ttyUSB0, /dev/ttyUSB1 for the radio", searching: ["/dev/ttyUSB0", "/dev/ttyUSB1"] }),
    );
    expect(wrapper.find(".tncstatus").text()).toBe("Searching for the radio…");
    const ports = wrapper.findAll("details").find((d) => d.find("summary").text() === "Ports");
    expect(ports?.element.open).toBe(false);
    expect(ports?.findAll("li").map((li) => li.text())).toEqual(["/dev/ttyUSB0", "/dev/ttyUSB1"]);
    expect(
      radio(tncState())
        .findAll("details details")
        .map((d) => d.find("summary").text()),
    ).toEqual(["Terminal"]);
  });

  it("tells how many packets the digipeater repeated, while it is on", () => {
    const tnc = tncState({ stats: { ...tncState().stats, digipeated: 5 } });
    expect(radio(tnc).find(".tncstatus").text()).not.toContain("digipeated");
    expect(
      mount(RadioStatus, { props: { tnc, now: NOW, digipeater: true } })
        .find(".tncstatus")
        .text(),
    ).toMatch(/, digipeated 5$/);
  });

  it("asks for a reconnect without opening or closing the fold", async () => {
    const wrapper = radio(tncState());
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("reconnect")).toHaveLength(1);
    expect(wrapper.find<HTMLDetailsElement>("details").element.open).toBe(false);
  });

  it("shows the lines of the terminal with their time in the viewer's time", () => {
    const at = new Date(NOW - 20_000).toISOString();
    const wrapper = radio(tncState({ lines: [{ at, text: "NeoAPRS: opened /dev/brainbox_3" }] }));
    expect(wrapper.find(".tnclines").text()).toBe(`${clockText(at)}  NeoAPRS: opened /dev/brainbox_3`);
  });

  it("says nothing before the daemon has spoken", () => {
    expect(radio(null).find(".radiostatus").exists()).toBe(false);
  });

  it("follows the end of the lines, unless they were scrolled up", async () => {
    const wrapper = mount(RadioStatus, { props: { tnc: tncState(), now: NOW }, attachTo: document.body });
    const box = wrapper.find<HTMLElement>(".tnclines").element;
    Object.defineProperty(box, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(box, "clientHeight", { value: 100, configurable: true });
    box.scrollTop = 900;
    await wrapper.setProps({ tnc: tncState({ lines: lines("a", "b", "c") }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(1000);
    box.scrollTop = 100;
    await wrapper.setProps({ tnc: tncState({ lines: lines("a", "b", "c", "d") }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(100);
    wrapper.unmount();
  });

  it("says in a muted pill and in words that the Dummy radio's traffic is made up and nothing goes on the air", () => {
    const wrapper = radio(tncState({ dummy: true, path: "the dummy radio", describe: "dummy radio, made-up traffic, 5 packets, nothing goes on the air" }));
    expect(wrapper.find(".statetext").text()).toBe("Dummy");
    expect(wrapper.find(".statetext").classes()).toContain("tnc-dummy");
    expect(wrapper.find(".statetext").classes()).not.toContain("tnc-connected");
    expect(wrapper.find(".tncstatus").text()).toBe("Dummy radio: made-up traffic, nothing goes on the air");
  });

  it("is the Dummy's pill and line only while its line is open: before that it is a radio like the others", () => {
    const wrapper = radio(tncState({ dummy: true, state: "connecting", path: "" }));
    expect(wrapper.find(".statetext").text()).toBe("connecting");
    expect(wrapper.find(".tncstatus").text()).toBe("Connecting…");
  });

  it("has the terminal of the Dummy radio like any radio's", () => {
    const wrapper = radio(
      tncState({ dummy: true, lines: lines("NeoAPRS: opened the dummy radio", "Q1ABC>APRS:=6010.95N/02458.58E-Home station  ->  position") }),
    );
    expect(wrapper.find("pre.tnclines").text()).toContain("Q1ABC>APRS");
  });
});
