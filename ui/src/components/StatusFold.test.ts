import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { rxOnlyLink } from "@/lib/settinglink";
import { cssRule } from "@/test/css";

const fold = (slot?: string, props: Record<string, unknown> = {}) =>
  mount(StatusFold, {
    props: { state: "off", tone: "tnc-waiting", line: "RX only: nothing is sent", ...props },
    slots: slot === undefined ? {} : { default: slot },
  });

describe("StatusFold", () => {
  it("is one row: the state in its tone, then the quiet detail", () => {
    const wrapper = fold();
    expect(wrapper.find(".statetext").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).toBe("RX only: nothing is sent");
  });

  it("has the arrow, and opens, only when something is behind it", async () => {
    const wrapper = fold("<p>the details</p>");
    expect(wrapper.find("details.statusfold > summary.statushead").exists()).toBe(true);
    expect(wrapper.find<HTMLDetailsElement>("details").element.open).toBe(false);
    await wrapper.setProps({ open: true });
    expect(wrapper.find<HTMLDetailsElement>("details").element.open).toBe(true);
  });

  it("is a plain row with no arrow and nothing to click when the fold is empty: no slot, an empty one, blanks, a v-if that is false", () => {
    const hidden = ref(false);
    const quiet = defineComponent({
      render: () =>
        h(
          StatusFold,
          { state: "on", tone: "beacon-on", line: "No beacon sent yet · next in 38 min" },
          { default: () => [hidden.value ? h("p", "x") : null, hidden.value ? h("p", "y") : null, " "] },
        ),
    });
    for (const wrapper of [fold(), fold(""), fold("   "), mount(quiet)]) {
      expect(wrapper.find("details").exists()).toBe(false);
      expect(wrapper.find("summary").exists()).toBe(false);
      expect(wrapper.find(".statusflat").exists()).toBe(true);
      expect(wrapper.find(".statetext").exists()).toBe(true);
    }
  });

  it("keeps the room of the arrow in a row without one, so that the words stay under each other, and draws no arrow in it", () => {
    expect(cssRule(".statusflat::before")).toMatch(/border-color:\s*transparent/);
    expect(cssRule(".statushead::before")).toMatch(/border-width:\s*5px 0 5px 8px/);
  });

  it("opens a fold whose content comes later: the arrow appears with it", async () => {
    const content = ref(false);
    const wrapper = mount(
      defineComponent({
        render: () => h(StatusFold, { state: "on", tone: "beacon-on", line: "x" }, { default: () => (content.value ? h("p", "later") : null) }),
      }),
    );
    expect(wrapper.find("details").exists()).toBe(false);
    content.value = true;
    await wrapper.vm.$nextTick();
    expect(wrapper.find("details.statusfold").exists()).toBe(true);
  });

  it("makes the line a link to the setting it explains, in a row with a fold as in one without, and a click goes there without opening the fold", async () => {
    const show = vi.fn();
    const global = { provide: { [DAEMON_KEY as symbol]: { panel: { show } } } };
    for (const slot of [undefined, "<p>behind</p>"]) {
      show.mockClear();
      const wrapper = mount(StatusFold, {
        props: { state: "off", tone: "tnc-waiting", line: "RX only: nothing is sent", link: rxOnlyLink() },
        slots: slot === undefined ? {} : { default: slot },
        global,
      });
      const link = wrapper.find(".tncstatus button.linkbutton");
      expect(link.text()).toBe("RX only: nothing is sent");
      expect(link.attributes("title")).toBe("Nothing is sent. Settings → Radio → RX only");
      await link.trigger("click");
      expect(show).toHaveBeenCalledWith("settings");
      if (slot !== undefined) expect(wrapper.find<HTMLDetailsElement>("details").element.open).toBe(false);
    }
  });

  it("is plain words where there is no page to go to, and where the row has no link", () => {
    expect(fold(undefined, { link: rxOnlyLink() }).find("button").exists()).toBe(false);
    expect(fold().find("button").exists()).toBe(false);
  });
});
