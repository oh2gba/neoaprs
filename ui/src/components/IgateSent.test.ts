// The lines that Send what I hear has put on APRS-IS, behind the Internet row's arrow (IgateSent.vue):
// shown only with the tick on, asked of the daemon only while the box is open, newest last, followed
// to the end unless scrolled up, in a list of a fixed height whose long lines wrap inside it, and the
// lines other stations' text, never markup.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IgateStatus from "@/components/IgateStatus.vue";
import { clockText } from "@/lib/format";
import { sentAfter, SENT_KEPT } from "@/lib/igatesent";
import type { IgateSentLine, IgateSentMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon, type Given } from "@/test/context";
import { igateState, NOW, radioRow, radiosTopic } from "@/test/fixtures";

const values = { "igate/server": "rotate.aprs2.net:14580", "map/radius_km": "50" };
const at = (seconds: number): string => new Date(NOW + seconds * 1000).toISOString();
const line = (n: number, radio: number | null = 1, text = `OH2AAA-1>APRS,qAO,OH2GBA:>line ${n}`): IgateSentLine => ({
  at: at(n),
  radio,
  line: text,
});

// The list is in view while its box is open: the observer says so at once, and `inView(false)` moves it
// out of view (a tab left).
const watchers: ((entries: { isIntersecting: boolean }[]) => void)[] = [];
const inView = (isIntersecting: boolean): void => watchers.forEach((run) => run([{ isIntersecting }]));

let mounted: VueWrapper | null = null;
beforeEach(() => {
  watchers.length = 0;
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(run: (entries: { isIntersecting: boolean }[]) => void) {
        watchers.push(run);
      }
      observe(): void {
        inView(true);
      }
      disconnect(): void {}
    },
  );
});
afterEach(() => {
  mounted?.unmount();
  vi.unstubAllGlobals();
});

function make(gate = true, given: Given = {}) {
  const daemon = fakeDaemon({
    radios: radiosTopic(radioRow(1, "kenwood-tnc2", { name: "Packet" }), radioRow(2, "mercury", { name: "Mercury" })),
    ...given,
  });
  const wrapper = mount(IgateStatus, {
    props: { igate: igateState({ gate }), values, stations: 3 },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
  mounted = wrapper;
  return { daemon, wrapper };
}

const looks = (daemon: FakeDaemon) =>
  daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === "igate_look");

async function toggle(wrapper: VueWrapper, open: boolean): Promise<void> {
  const details = wrapper.find<HTMLDetailsElement>("details").element;
  details.open = open;
  details.dispatchEvent(new Event("toggle"));
  await flushPromises();
}

describe("the lines put on APRS-IS", () => {
  it("are not there, and not asked for, while Send what I hear is off: no empty frame is left behind", async () => {
    const { daemon, wrapper } = make(false);
    await toggle(wrapper, true);
    expect(wrapper.find(".igatesent").exists()).toBe(false);
    expect(looks(daemon)).toEqual([]);
  });

  it("are asked of the daemon only while the box is open, and no more when it is closed", async () => {
    const { daemon, wrapper } = make();
    await flushPromises();
    expect(looks(daemon)).toEqual([]);
    await toggle(wrapper, true);
    expect(looks(daemon)).toEqual([{ cmd: "igate_look", on: true }]);
    await toggle(wrapper, false);
    expect(looks(daemon)).toEqual([
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: false },
    ]);
  });

  it("are asked again when the socket was opened anew, as the daemon forgets a page that left", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    await tell(daemon, { connection: "closed" });
    await tell(daemon, { connection: "open" });
    expect(looks(daemon)).toEqual([
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: true },
    ]);
  });

  it("are not asked for while the list is out of view, as when another tab is shown", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    inView(false);
    expect(looks(daemon).at(-1)).toEqual({ cmd: "igate_look", on: false });
    inView(true);
    expect(looks(daemon).at(-1)).toEqual({ cmd: "igate_look", on: true });
  });

  it("stop being asked for when the tick goes off while the box is open", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    await wrapper.setProps({ igate: igateState({ gate: false }) });
    expect(wrapper.find(".igatesent").exists()).toBe(false);
    expect(looks(daemon).at(-1)).toEqual({ cmd: "igate_look", on: false });
  });

  it("are listed oldest first with the time, the tag of the radio that heard each and the line; none for our own", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    expect(wrapper.find(".igatesent").text()).toBe("");
    await tell(daemon, {
      igateSent: [line(1, 1), line(2, 2), line(3, null, "OH2GBA>APZNEO,TCPIP*:!6010.00N/02456.00E>")],
    });
    const rows = wrapper.findAll(".igatesent-row");
    expect(rows.map((row) => row.findAll("span")[0]?.text())).toEqual([1, 2, 3].map((n) => clockText(at(n))));
    expect(rows.map((row) => row.find(".igatesent-tag").text())).toEqual(["Packet", "Mercury", ""]);
    expect(rows.map((row) => row.find(".igatesent-line").text())).toEqual([
      "OH2AAA-1>APRS,qAO,OH2GBA:>line 1",
      "OH2AAA-1>APRS,qAO,OH2GBA:>line 2",
      "OH2GBA>APZNEO,TCPIP*:!6010.00N/02456.00E>",
    ]);
  });

  it("follow the end of the list, unless it was scrolled up", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    const box = wrapper.find<HTMLElement>(".igatesent").element;
    Object.defineProperty(box, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(box, "clientHeight", { value: 100, configurable: true });
    box.scrollTop = 900;
    await tell(daemon, { igateSent: [line(1), line(2)] });
    await flushPromises();
    expect(box.scrollTop).toBe(1000);
    box.scrollTop = 100;
    await tell(daemon, { igateSent: [line(1), line(2), line(3)] });
    await flushPromises();
    expect(box.scrollTop).toBe(100);
  });

  it("are shown to the newest when the box is opened", async () => {
    const { wrapper } = make(true, { igateSent: [line(1), line(2)] });
    const box = wrapper.find<HTMLElement>(".igatesent").element;
    Object.defineProperty(box, "scrollHeight", { value: 1000, configurable: true });
    await toggle(wrapper, true);
    expect(box.scrollTop).toBe(1000);
  });

  it("are other stations' text, never markup, and a long one wraps inside a list of its own", async () => {
    const { daemon, wrapper } = make();
    await toggle(wrapper, true);
    const evil = `OH2AAA-1>APRS:>${"x".repeat(400)}<img src=x onerror=alert(1)><b>bold</b>`;
    await tell(daemon, { igateSent: [line(1, 1, evil)] });
    expect(wrapper.find(".igatesent img").exists()).toBe(false);
    expect(wrapper.find(".igatesent b").exists()).toBe(false);
    expect(wrapper.find(".igatesent-line").text()).toBe(evil);
  });
});

describe("the list of lines the page keeps", () => {
  const message = (whole: boolean, ...lines: IgateSentLine[]): IgateSentMessage => ({
    type: "igate_sent",
    whole,
    lines,
  });

  it("is replaced by a message told whole and added to by one that is not", () => {
    const held = sentAfter([], message(true, line(1), line(2)));
    expect(held.map((one) => one.at)).toEqual([at(1), at(2)]);
    expect(sentAfter(held, message(false, line(3))).map((one) => one.at)).toEqual([at(1), at(2), at(3)]);
    expect(sentAfter(held, message(true, line(9))).map((one) => one.at)).toEqual([at(9)]);
  });

  it("keeps the newest ones as the daemon does", () => {
    const many = Array.from({ length: SENT_KEPT }, (_, n) => line(n));
    const held = sentAfter(many, message(false, line(1000)));
    expect(held).toHaveLength(SENT_KEPT);
    expect(held[0]?.at).toBe(at(1));
    expect(held.at(-1)?.at).toBe(at(1000));
  });
});
