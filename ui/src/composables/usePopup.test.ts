import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import { usePopup, type PopupOptions } from "@/composables/usePopup";

/** A button that opens a box, with a second button outside it; the popup is wired as the options say. */
function make(options: Partial<Pick<PopupOptions, "focusAway" | "stopEscape" | "escapeAnywhere">> = {}) {
  const parent: string[] = [];
  const Popup = defineComponent({
    setup() {
      const open = ref(false);
      const root = ref<HTMLElement | null>(null);
      const trigger = ref<HTMLElement | null>(null);
      const popup = usePopup({ open, root, trigger, close: () => (open.value = false), ...options });
      return () =>
        h("div", { onKeydown: (event: KeyboardEvent) => parent.push(event.key) }, [
          h("div", { ref: root, class: "box", onKeydown: popup.onEscape }, [
            h("button", { ref: trigger, class: "trigger", onClick: () => (open.value = !open.value) }, "open"),
            open.value ? h("input", { class: "inside" }) : null,
          ]),
          h("button", { class: "outside" }, "elsewhere"),
        ]);
    },
  });
  const wrapper = mount(Popup, { attachTo: document.body });
  const opened = () => wrapper.find(".inside").exists();
  return { wrapper, parent, opened };
}

afterEach(() => document.body.replaceChildren());

describe("usePopup", () => {
  it("closes on a press outside, and not on one inside", async () => {
    const { wrapper, opened } = make();
    await wrapper.find(".trigger").trigger("click");
    expect(opened()).toBe(true);
    wrapper.find(".inside").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(opened()).toBe(true);
    wrapper.find(".outside").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(opened()).toBe(false);
  });

  it("closes when the focus moves outside, unless it is told the focus may go", async () => {
    const away = make();
    await away.wrapper.find(".trigger").trigger("click");
    away.wrapper.find(".outside").element.dispatchEvent(new Event("focusin", { bubbles: true }));
    await away.wrapper.vm.$nextTick();
    expect(away.opened()).toBe(false);
    const stays = make({ focusAway: false });
    await stays.wrapper.find(".trigger").trigger("click");
    stays.wrapper.find(".outside").element.dispatchEvent(new Event("focusin", { bubbles: true }));
    await stays.wrapper.vm.$nextTick();
    expect(stays.opened()).toBe(true);
  });

  it("closes on Esc in the popup and puts the focus on the button, and passes the key on only when it is not told to stop it", async () => {
    const passed = make();
    await passed.wrapper.find(".trigger").trigger("click");
    await passed.wrapper.find(".inside").trigger("keydown", { key: "Escape" });
    expect(passed.opened()).toBe(false);
    expect(document.activeElement).toBe(passed.wrapper.find(".trigger").element);
    expect(passed.parent).toEqual(["Escape"]);
    const stopped = make({ stopEscape: true });
    await stopped.wrapper.find(".trigger").trigger("click");
    await stopped.wrapper.find(".inside").trigger("keydown", { key: "Escape" });
    expect(stopped.opened()).toBe(false);
    expect(stopped.parent).toEqual([]);
  });

  it("does nothing with another key, or with Esc while it is closed", async () => {
    const { wrapper, opened } = make({ stopEscape: true });
    await wrapper.find(".trigger").trigger("keydown", { key: "Escape" });
    await wrapper.find(".trigger").trigger("click");
    await wrapper.find(".inside").trigger("keydown", { key: "a" });
    expect(opened()).toBe(true);
  });

  it("hears Esc anywhere on the page when it is told to, and no longer once it is unmounted", async () => {
    const { wrapper, opened } = make({ escapeAnywhere: true });
    await wrapper.find(".trigger").trigger("click");
    wrapper.find(".outside").element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(opened()).toBe(false);
    await wrapper.find(".trigger").trigger("click");
    wrapper.unmount();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    document.dispatchEvent(new Event("pointerdown"));
  });
});
