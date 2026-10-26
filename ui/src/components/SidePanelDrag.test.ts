import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import SidePanel from "@/components/SidePanel.vue";
import { PANEL_MIN, panelMax } from "@/lib/layout";

// The handle at the panel's left edge is dragged with the pointer: the width is the window's width less where the pointer is, held between the least and the most the window allows, and the capture ends with the button.
const slots = { stations: "<p>stations pane</p>" };
const innerWidth = window.innerWidth;
const captured: number[] = [];

beforeEach(() => {
  window.innerWidth = 1200;
  captured.length = 0;
  HTMLElement.prototype.setPointerCapture = (id: number) => void captured.push(id);
});
afterEach(() => {
  window.innerWidth = innerWidth;
});

function pointer(type: string, x: number, id = 7): Event {
  const event = new Event(type, { bubbles: true });
  Object.assign(event, { clientX: x, pointerId: id });
  return event;
}

function open(width = 400) {
  const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width }, slots, attachTo: document.body });
  return { wrapper, handle: wrapper.find("[role='separator']").element as HTMLElement };
}

describe("SidePanel drag", () => {
  it("takes the pointer when the handle is pressed and gives the width as the pointer moves", () => {
    const { wrapper, handle } = open();
    handle.dispatchEvent(pointer("pointerdown", 800));
    expect(captured).toEqual([7]);
    handle.dispatchEvent(pointer("pointermove", 800));
    handle.dispatchEvent(pointer("pointermove", 760));
    expect(wrapper.emitted("update:width")).toEqual([[400], [440]]);
    wrapper.unmount();
  });

  it("holds the width between the least and the most the window allows", () => {
    const { wrapper, handle } = open();
    handle.dispatchEvent(pointer("pointerdown", 800));
    handle.dispatchEvent(pointer("pointermove", 1190));
    handle.dispatchEvent(pointer("pointermove", 5));
    expect(wrapper.emitted("update:width")).toEqual([[PANEL_MIN], [panelMax(1200)]]);
    wrapper.unmount();
  });

  it.each(["pointerup", "pointercancel"])("is done with the moves when the pointer is let go (%s): they change nothing after it", (end) => {
    const { wrapper, handle } = open();
    handle.dispatchEvent(pointer("pointerdown", 800));
    handle.dispatchEvent(pointer("pointermove", 790));
    handle.dispatchEvent(pointer(end, 790));
    handle.dispatchEvent(pointer("pointermove", 700));
    expect(wrapper.emitted("update:width")).toEqual([[410]]);
    wrapper.unmount();
  });

  it("does not start a drag the window cannot do (a handle that is not an element) and is not a handle on a tablet or a phone", () => {
    const tablet = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400, size: "tablet" }, slots });
    expect(tablet.find("[role='separator']").exists()).toBe(false);
    const { wrapper, handle } = open();
    const press = pointer("pointerdown", 800);
    Object.defineProperty(press, "currentTarget", { value: null });
    expect(() => handle.dispatchEvent(press)).not.toThrow();
    wrapper.unmount();
  });
});

describe("SidePanel keys on the handle", () => {
  it("leaves every key but the arrows alone: no new width, and the key is not held back from the page", () => {
    const { wrapper } = open();
    const event = new KeyboardEvent("keydown", { key: "a", bubbles: true, cancelable: true });
    wrapper.find("[role='separator']").element.dispatchEvent(event);
    expect(wrapper.emitted("update:width")).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
    const arrow = new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true, cancelable: true });
    wrapper.find("[role='separator']").element.dispatchEvent(arrow);
    expect(arrow.defaultPrevented).toBe(true);
    expect(wrapper.emitted("update:width")).toEqual([[424]]);
    wrapper.unmount();
  });
});
