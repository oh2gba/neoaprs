// The groups of the Settings tab fold by the arrow in their legend, the state is kept per browser, and a group that must be seen opens by itself.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SettingsGroup from "@/components/SettingsGroup.vue";
import { attend } from "@/lib/attention";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, toastOf } from "@/test/fixtures";

const mounted: { unmount: () => void }[] = [];
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  localStorage.clear();
  vi.restoreAllMocks();
});

const KEY = (id: string) => `NeoAPRS.settings.fold.${id}`;
const group = (props: Record<string, unknown> = {}) => {
  const wrapper = mount(SettingsGroup, {
    props: { id: "digi", title: "Digipeater", ...props },
    slots: { default: '<input id="inside" />' },
    attachTo: document.body,
  });
  mounted.push(wrapper);
  return wrapper;
};
const arrow = (wrapper: ReturnType<typeof group>) => wrapper.get("legend button.groupfold");
const bodyShown = (wrapper: ReturnType<typeof group>) => (wrapper.get(".group-body").element as HTMLElement).style.display !== "none";

function form() {
  const daemon = fakeDaemon({ config: configValues({ "digi/enabled": "true" }) });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
  mounted.push(wrapper);
  const named = (title: string) => wrapper.findAll("form > fieldset").find((f) => f.find("legend").text() === title);
  return { wrapper, daemon, named };
}
const shown = (fieldset: ReturnType<ReturnType<typeof form>["named"]>) => (fieldset?.get(".group-body").element as HTMLElement).style.display !== "none";

describe("a group of the Settings tab", () => {
  it("is open, with its name as the button of the arrow in its legend, which says what it opens", () => {
    const wrapper = group();
    expect(wrapper.get("legend").text()).toBe("Digipeater");
    expect(arrow(wrapper).attributes("type")).toBe("button");
    expect(arrow(wrapper).attributes("aria-expanded")).toBe("true");
    expect(arrow(wrapper).attributes("aria-controls")).toBe(wrapper.get(".group-body").attributes("id"));
    expect(bodyShown(wrapper)).toBe(true);
  });

  it("folds and opens by its arrow, and keeps the legend as it is", async () => {
    const wrapper = group();
    const legend = wrapper.get("legend").html();
    await arrow(wrapper).trigger("click");
    expect(arrow(wrapper).attributes("aria-expanded")).toBe("false");
    expect(bodyShown(wrapper)).toBe(false);
    expect(wrapper.get("fieldset").classes()).toContain("folded");
    expect(wrapper.get("legend").text()).toBe("Digipeater");
    expect(
      wrapper
        .get("legend")
        .html()
        .replace(/aria-expanded="\w+"/, ""),
    ).toBe(legend.replace(/aria-expanded="\w+"/, ""));
    await arrow(wrapper).trigger("click");
    expect(arrow(wrapper).attributes("aria-expanded")).toBe("true");
    expect(bodyShown(wrapper)).toBe(true);
  });

  it("keeps what is under the legend on the page while it is folded", async () => {
    const wrapper = group();
    await arrow(wrapper).trigger("click");
    expect(document.getElementById("inside")).not.toBeNull();
  });

  it("is remembered in this browser for each group, and is still folded in a new page", async () => {
    const first = group();
    await arrow(first).trigger("click");
    expect(localStorage.getItem(KEY("digi"))).toBe("folded");
    first.unmount();
    const again = group();
    expect(arrow(again).attributes("aria-expanded")).toBe("false");
    expect(bodyShown(again)).toBe(false);
    const other = group({ id: "map", title: "Map" });
    expect(arrow(other).attributes("aria-expanded")).toBe("true");
    await arrow(again).trigger("click");
    again.unmount();
    expect(arrow(group()).attributes("aria-expanded")).toBe("true");
  });

  it("is open when what was kept is nothing it knows", () => {
    localStorage.setItem(KEY("digi"), "perhaps");
    expect(arrow(group()).attributes("aria-expanded")).toBe("true");
  });

  it("works when the browser keeps nothing: it folds and opens, and nothing is thrown", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const wrapper = group();
    expect(arrow(wrapper).attributes("aria-expanded")).toBe("true");
    await arrow(wrapper).trigger("click");
    expect(bodyShown(wrapper)).toBe(false);
    await arrow(wrapper).trigger("click");
    expect(bodyShown(wrapper)).toBe(true);
  });

  it("opens by itself when it is told it has something to be seen, and a person can fold it again", async () => {
    localStorage.setItem(KEY("digi"), "folded");
    const wrapper = group();
    expect(bodyShown(wrapper)).toBe(false);
    await wrapper.setProps({ show: true });
    expect(bodyShown(wrapper)).toBe(true);
    expect(localStorage.getItem(KEY("digi"))).toBe("open");
    await arrow(wrapper).trigger("click");
    expect(bodyShown(wrapper)).toBe(false);
  });

  it("opens before the page goes to a control inside it", async () => {
    localStorage.setItem(KEY("digi"), "folded");
    const wrapper = group();
    expect(await attend("inside")).toBe(true);
    await nextTick();
    expect(bodyShown(wrapper)).toBe(true);
    expect(document.activeElement?.id).toBe("inside");
    wrapper.unmount();
  });

  it("is a plain group box, with no arrow and nothing hidden, where it does not fold", () => {
    localStorage.setItem(KEY("digi"), "folded");
    const wrapper = group({ fold: false });
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.get("legend").text()).toBe("Digipeater");
    expect(bodyShown(wrapper)).toBe(true);
    expect(wrapper.get(".group-body").attributes("id")).toBeUndefined();
  });
});

describe("the Settings tab", () => {
  it("folds every group: the name of each is the button of its arrow, and the groups of the My station tab do not fold", () => {
    const { wrapper } = form();
    const titles = wrapper.findAll("form > fieldset").map((f) => f.get("legend").text());
    expect(titles).toContain("Radio");
    expect(titles).toContain("Digipeater");
    expect(titles).toContain("Notifications");
    expect(titles).toContain("Help");
    expect(titles).toContain("About");
    expect(wrapper.findAll("form > fieldset > legend > button.groupfold")).toHaveLength(titles.length);
    const station = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(fakeDaemon({ config: configValues() })) });
    expect(station.findAll("button.groupfold")).toHaveLength(0);
    wrapper.unmount();
  });

  it("remembers the folded groups after the page is made again", async () => {
    const first = form();
    await first.named("Digipeater")?.get("button.groupfold").trigger("click");
    await first.named("Update check")?.get("button.groupfold").trigger("click");
    expect(shown(first.named("Digipeater"))).toBe(false);
    first.wrapper.unmount();
    const again = form();
    expect(shown(again.named("Digipeater"))).toBe(false);
    expect(shown(again.named("Update check"))).toBe(false);
    expect(shown(again.named("Map"))).toBe(true);
    expect(shown(again.named("About"))).toBe(true);
    again.wrapper.unmount();
  });

  it("opens a group by itself when the daemon refuses a setting in it", async () => {
    localStorage.setItem(KEY("serial"), "folded");
    const { wrapper, daemon, named } = form();
    expect(shown(named("Radio"))).toBe(false);
    await wrapper.find("#set-tnc-profile").setValue("kiss");
    await tell(daemon, { lastError: toastOf("set_config: tnc/profile: KISS TNC is too much") });
    expect(shown(named("Radio"))).toBe(true);
    expect(wrapper.find("#set-tnc-profile").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("KISS TNC is too much");
    wrapper.unmount();
  });

  it("opens the group of a control the page leads to", async () => {
    localStorage.setItem(KEY("serial"), "folded");
    const { wrapper, named } = form();
    expect(shown(named("Radio"))).toBe(false);
    expect(await attend("set-station-transmit")).toBe(true);
    await nextTick();
    expect(shown(named("Radio"))).toBe(true);
    expect(document.activeElement?.id).toBe("set-station-transmit");
    wrapper.unmount();
  });

  it("works when the browser keeps nothing", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { wrapper, named } = form();
    expect(shown(named("Digipeater"))).toBe(true);
    await named("Digipeater")?.get("button.groupfold").trigger("click");
    expect(shown(named("Digipeater"))).toBe(false);
    wrapper.unmount();
  });
});
