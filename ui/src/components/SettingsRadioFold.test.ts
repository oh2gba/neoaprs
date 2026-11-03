// The FM radio's box and the HF radio's box of the Radio group fold by the arrow in their legends, as the groups of the Settings tab do (SettingsBox with a foldId, the fold of composables/useFold.ts): the state is kept in this browser for each box, they are open at
// first, they open by themselves for a complaint of the daemon about one of their settings, for a page that leads to a control inside them and for a radio that is ticked and not connected, and the fold under the status line inside each box is as it was.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { attend } from "@/lib/attention";
import type { TncState } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, hfState, tncState, toastOf } from "@/test/fixtures";

const mounted: { unmount: () => void }[] = [];
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  localStorage.clear();
  vi.restoreAllMocks();
});

const KEY = (id: string) => `NeoAPRS.settings.fold.${id}`;
const BOTH = { "hf/enabled": "true", "mercury/sound_card": "plughw:1,0", "mercury/keying": "vox" };

function make(more: Given = {}, extra: Record<string, string> = BOTH) {
  const daemon = fakeDaemon({ config: configValues(extra), tnc: tncState(), hf: hfState(), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
  mounted.push(wrapper);
  const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Radio");
  if (!group) throw new Error("no Radio group");
  const box = (legend: string) => {
    const found = group.findAll("fieldset.subbox").find((f) => f.find("legend").text() === legend);
    if (!found) throw new Error(`no ${legend} box`);
    return found;
  };
  return { wrapper, daemon, group, fm: () => box("FM radio"), hf: () => box("HF radio") };
}
type Box = ReturnType<ReturnType<typeof make>["fm"]>;
const arrow = (box: Box) => box.get("legend button.groupfold");
const body = (box: Box) => box.get(".box-body");
const shown = (box: Box) => (body(box).element as HTMLElement).style.display !== "none";
const stateOf = (state: TncState["state"]) => tncState({ state });

describe("the boxes of the two radios", () => {
  it("are open at first, with their names as the buttons of arrows in their legends, which say what they open", () => {
    const { fm, hf } = make();
    for (const [box, name] of [
      [fm(), "FM radio"],
      [hf(), "HF radio"],
    ] as const) {
      expect(box.get("legend").text()).toBe(name);
      expect(arrow(box).attributes("type")).toBe("button");
      expect(arrow(box).attributes("aria-expanded")).toBe("true");
      expect(arrow(box).attributes("aria-controls")).toBe(body(box).attributes("id"));
      expect(shown(box)).toBe(true);
      expect(box.classes()).not.toContain("folded");
    }
    expect(arrow(fm()).attributes("aria-controls")).not.toBe(arrow(hf()).attributes("aria-controls"));
  });

  it("fold and open by their arrows, each by itself, and keep the legend as it is", async () => {
    const { fm, hf } = make();
    const legend = fm().get("legend").text();
    await arrow(fm()).trigger("click");
    expect(arrow(fm()).attributes("aria-expanded")).toBe("false");
    expect(shown(fm())).toBe(false);
    expect(fm().classes()).toContain("folded");
    expect(fm().get("legend").text()).toBe(legend);
    expect(shown(hf())).toBe(true);
    await arrow(hf()).trigger("click");
    expect(shown(hf())).toBe(false);
    await arrow(fm()).trigger("click");
    expect(shown(fm())).toBe(true);
    expect(shown(hf())).toBe(false);
  });

  it("have the Enable tickbox and the rest inside what folds, which stays on the page while it is folded", async () => {
    const { fm, hf } = make();
    for (const [box, id] of [
      [fm(), "set-fm-enabled"],
      [hf(), "set-hf-enabled"],
    ] as const) {
      expect(body(box).find(`#${id}`).exists()).toBe(true);
      await arrow(box).trigger("click");
      expect(box.find(`#${id}`).exists()).toBe(true);
      expect(box.find("legend input").exists()).toBe(false);
    }
  });

  it("are remembered in this browser for each box, the keys being settings.fold.fm and settings.fold.hf, and are still folded in a new page", async () => {
    const first = make();
    await arrow(first.fm()).trigger("click");
    expect(localStorage.getItem(KEY("fm"))).toBe("folded");
    expect(localStorage.getItem(KEY("hf"))).toBeNull();
    await arrow(first.hf()).trigger("click");
    expect(localStorage.getItem(KEY("hf"))).toBe("folded");
    first.wrapper.unmount();
    const again = make();
    expect(shown(again.fm())).toBe(false);
    expect(shown(again.hf())).toBe(false);
    await arrow(again.hf()).trigger("click");
    expect(localStorage.getItem(KEY("hf"))).toBe("open");
    again.wrapper.unmount();
    const third = make();
    expect(shown(third.fm())).toBe(false);
    expect(shown(third.hf())).toBe(true);
  });

  it("are open when what was kept is nothing they know, and work when the browser keeps nothing", async () => {
    localStorage.setItem(KEY("fm"), "perhaps");
    expect(shown(make().fm())).toBe(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { fm } = make();
    expect(shown(fm())).toBe(true);
    await arrow(fm()).trigger("click");
    expect(shown(fm())).toBe(false);
  });

  it("do not make a fold of the other boxes of the Settings tab, and the fold under the status line inside each box is as it was", () => {
    const { wrapper, fm, hf } = make();
    expect(wrapper.findAll("fieldset.subbox button.groupfold")).toHaveLength(2);
    for (const box of [fm(), hf()]) expect(box.find("details.radiostatus").exists()).toBe(true);
    expect(fm().get<HTMLDetailsElement>("details.radiostatus").element.open).toBe(false);
  });
});

describe("a box that is folded opens by itself", () => {
  it("for a complaint of the daemon about one of its settings, and a person can fold it again", async () => {
    localStorage.setItem(KEY("hf"), "folded");
    localStorage.setItem(KEY("fm"), "folded");
    const { wrapper, daemon, fm, hf } = make();
    expect(shown(hf())).toBe(false);
    await wrapper.find("#set-mercury-keying").setValue("rts:/dev/ttyUSB0");
    await tell(daemon, { lastError: toastOf("set_config: mercury/keying: that port is not there") });
    expect(shown(hf())).toBe(true);
    expect(shown(fm())).toBe(false);
    expect(localStorage.getItem(KEY("hf"))).toBe("open");
    await arrow(hf()).trigger("click");
    expect(shown(hf())).toBe(false);
  });

  it("for a complaint about a setting of the FM radio", async () => {
    localStorage.setItem(KEY("fm"), "folded");
    localStorage.setItem(KEY("hf"), "folded");
    const { wrapper, daemon, fm, hf } = make();
    await wrapper.find("#set-tnc-profile").setValue("kiss");
    await tell(daemon, { lastError: toastOf("set_config: tnc/profile: KISS TNC is too much") });
    expect(shown(fm())).toBe(true);
    expect(shown(hf())).toBe(false);
  });

  it("when the page leads to a control inside it", async () => {
    localStorage.setItem(KEY("fm"), "folded");
    localStorage.setItem(KEY("hf"), "folded");
    const { fm, hf } = make();
    expect(await attend("set-hf-enabled")).toBe(true);
    await nextTick();
    expect(shown(hf())).toBe(true);
    expect(shown(fm())).toBe(false);
    expect(document.activeElement?.id).toBe("set-hf-enabled");
    expect(await attend("set-fm-enabled")).toBe(true);
    await nextTick();
    expect(shown(fm())).toBe(true);
  });

  it("and the group it is in opens with it, when that is folded too", async () => {
    localStorage.setItem(KEY("serial"), "folded");
    localStorage.setItem(KEY("hf"), "folded");
    const { group, hf } = make();
    expect((group.get(".group-body").element as HTMLElement).style.display).toBe("none");
    expect(await attend("set-hf-enabled")).toBe(true);
    await nextTick();
    expect((group.get(".group-body").element as HTMLElement).style.display).not.toBe("none");
    expect(shown(hf())).toBe(true);
  });

  it("when its radio is ticked and not connected, and not when it is connected, nor when it is not ticked", () => {
    localStorage.setItem(KEY("fm"), "folded");
    localStorage.setItem(KEY("hf"), "folded");
    const waiting = make({ tnc: stateOf("waiting"), hf: stateOf("connected") });
    expect(shown(waiting.fm())).toBe(true);
    expect(shown(waiting.hf())).toBe(false);
    waiting.wrapper.unmount();
    localStorage.setItem(KEY("fm"), "folded");
    localStorage.setItem(KEY("hf"), "folded");
    const hfDown = make({ tnc: stateOf("connected"), hf: { ...hfState(), state: "connecting" } });
    expect(shown(hfDown.hf())).toBe(true);
    expect(shown(hfDown.fm())).toBe(false);
    hfDown.wrapper.unmount();
    localStorage.setItem(KEY("hf"), "folded");
    const off = make({ hf: stateOf("stopped") }, { "hf/enabled": "false" });
    expect(shown(off.fm())).toBe(false);
    off.wrapper.unmount();
  });

  it("when the radio turns unconnected after the page is up, and stays open when it connects again", async () => {
    localStorage.setItem(KEY("fm"), "folded");
    const { daemon, fm } = make();
    expect(shown(fm())).toBe(false);
    await tell(daemon, { tnc: stateOf("waiting") });
    expect(shown(fm())).toBe(true);
    await tell(daemon, { tnc: stateOf("connected") });
    expect(shown(fm())).toBe(true);
  });
});
