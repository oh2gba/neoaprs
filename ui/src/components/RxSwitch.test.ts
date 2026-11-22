import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import RxSwitch from "@/components/RxSwitch.vue";
import type { RxSwitch as RxSwitchState } from "@/lib/rxswitch";

const TX: RxSwitchState = { face: "tx", act: "toggle", title: "header.rx.tx_title", focus: "" };
const RX: RxSwitchState = { face: "rx", act: "toggle", title: "header.rx.rx_title", focus: "" };
const OFFLINE: RxSwitchState = { face: "rx", act: "none", title: "pill.daemon_offline_title", focus: "" };

const make = (rx: RxSwitchState) => mount(RxSwitch, { props: { rx } });
const button = (wrapper: ReturnType<typeof make>) => wrapper.find("#rx-switch");
/** The three faces, in order: the spans of the TwoWords that hold words, not another TwoWords. */
const faces = (wrapper: ReturnType<typeof make>) =>
  button(wrapper)
    .findAll(".twowords > span")
    .filter((span) => !span.find(".twowords").exists());
/** The words shown: the face that no hidden span is round. */
const face = (wrapper: ReturnType<typeof make>): string =>
  faces(wrapper)
    .filter((span) => span.element.closest(".twowords-off") === null)
    .map((span) => span.text())
    .join("");
/** The words a screen reader reads: the button without what is aria-hidden. */
function spoken(wrapper: ReturnType<typeof make>): string {
  const copy = button(wrapper).element.cloneNode(true) as HTMLElement;
  for (const hidden of copy.querySelectorAll("[aria-hidden='true']")) hidden.remove();
  return copy.textContent ?? "";
}

afterEach(() => vi.useRealTimers());

describe("the RX only switch", () => {
  it("sends RX only with one press", async () => {
    const wrapper = make(TX);
    expect(face(wrapper)).toBe("RX + TX");
    expect(button(wrapper).classes()).toContain("tag-neutral");
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toEqual([[false]]);
  });

  it("asks sure? before transmitting again", async () => {
    vi.useFakeTimers();
    const wrapper = make(RX);
    expect(face(wrapper)).toBe("RX only");
    expect(button(wrapper).classes()).toContain("tag-warn");
    await button(wrapper).trigger("click");
    expect(face(wrapper)).toBe("sure?");
    expect(wrapper.emitted("transmit")).toBeUndefined();
    vi.advanceTimersByTime(600);
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toEqual([[true]]);
    expect(face(wrapper)).toBe("RX only");
    await button(wrapper).trigger("click");
    vi.advanceTimersByTime(5000);
    await wrapper.vm.$nextTick();
    expect(face(wrapper)).toBe("RX only");
    expect(wrapper.emitted("transmit")).toHaveLength(1);
  });

  it("takes a double click or a double tap for one press: it arms and sends nothing", async () => {
    vi.useFakeTimers();
    const wrapper = make(RX);
    await button(wrapper).trigger("click");
    await button(wrapper).trigger("click");
    vi.advanceTimersByTime(499);
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toBeUndefined();
    expect(face(wrapper)).toBe("sure?");
    vi.advanceTimersByTime(101);
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toEqual([[true]]);
  });

  it("does nothing more while a key is held after its first press, and takes the next press once it is let go", async () => {
    vi.useFakeTimers();
    const wrapper = make(RX);
    const hold = async (key: string) => {
      await button(wrapper).trigger("keydown", { key });
      await button(wrapper).trigger("click");
      for (let n = 0; n < 40; n++) {
        vi.advanceTimersByTime(30);
        await button(wrapper).trigger("keydown", { key, repeat: true });
        await button(wrapper).trigger("click");
      }
    };
    await hold("Enter");
    expect(face(wrapper)).toBe("sure?");
    expect(wrapper.emitted("transmit")).toBeUndefined();
    await button(wrapper).trigger("keyup", { key: "Enter" });
    await hold(" ");
    expect(wrapper.emitted("transmit")).toEqual([[true]]);
    await button(wrapper).trigger("keyup", { key: " " });
    const tx = make(TX);
    await button(tx).trigger("keydown", { key: "Enter" });
    await button(tx).trigger("click");
    await button(tx).trigger("keydown", { key: "Enter", repeat: true });
    await button(tx).trigger("click");
    expect(tx.emitted("transmit")).toEqual([[false]]);
  });

  it("renders every face at once and keeps the same element", async () => {
    const wrapper = make(TX);
    const element = button(wrapper).element;
    const off = () => faces(wrapper).map((span) => span.element.closest(".twowords-off") !== null);
    expect(faces(wrapper).map((span) => span.text())).toEqual(["RX + TX", "RX only", "sure?"]);
    expect(off()).toEqual([false, true, true]);
    await wrapper.setProps({ rx: RX });
    expect(off()).toEqual([true, false, true]);
    await button(wrapper).trigger("click");
    expect(off()).toEqual([true, true, false]);
    expect(button(wrapper).element).toBe(element);
  });

  it("stays armed when the same state arrives again as a new object", async () => {
    const wrapper = make(RX);
    await button(wrapper).trigger("click");
    await wrapper.setProps({ rx: { ...RX } });
    expect(face(wrapper)).toBe("sure?");
  });

  it("disarms when the state changes from outside", async () => {
    const wrapper = make(RX);
    await button(wrapper).trigger("click");
    expect(face(wrapper)).toBe("sure?");
    await wrapper.setProps({ rx: TX });
    await wrapper.setProps({ rx: RX });
    expect(face(wrapper)).toBe("RX only");
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toBeUndefined();
    // the socket goes while it is armed: disarmed and disabled
    await wrapper.setProps({ rx: OFFLINE });
    expect(face(wrapper)).toBe("RX only");
    expect(button(wrapper).attributes("disabled")).toBeDefined();
  });

  it("leaves no timer behind when it is unmounted while armed", async () => {
    vi.useFakeTimers();
    const wrapper = make(RX);
    await button(wrapper).trigger("click");
    expect(vi.getTimerCount()).toBe(1);
    wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("is a disabled button with the daemon's title while the socket is not open", async () => {
    const wrapper = make(OFFLINE);
    expect(button(wrapper).attributes("disabled")).toBeDefined();
    expect(button(wrapper).attributes("title")).toBe("NeoAPRS does not answer. The page connects again by itself");
    expect(face(wrapper)).toBe("RX only");
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("transmit")).toBeUndefined();
    expect(wrapper.emitted("open")).toBeUndefined();
  });

  it("leads to the radio's box while no radio that is on can send", async () => {
    const wrapper = make({ face: "rx", act: "open", title: "pill.rx_title_radios", focus: "set-radio-3-enabled" });
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("open")).toEqual([["settings", "set-radio-3-enabled"]]);
    expect(wrapper.emitted("transmit")).toBeUndefined();
  });

  it("names itself by the face shown, and tells a screen reader the new face once it changes", async () => {
    const wrapper = make(TX);
    const live = () => wrapper.find("[role='status']");
    expect(button(wrapper).attributes("aria-pressed")).toBeUndefined();
    expect(button(wrapper).attributes("aria-label")).toBeUndefined();
    expect(spoken(wrapper)).toBe("RX + TX");
    expect(live().text()).toBe("");
    await wrapper.setProps({ rx: RX });
    expect(spoken(wrapper)).toBe("RX only");
    expect(live().text()).toBe("RX only");
    await button(wrapper).trigger("click");
    expect(spoken(wrapper)).toBe("sure?");
    expect(live().text()).toBe("RX only");
  });
});
