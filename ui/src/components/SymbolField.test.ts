import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import SymbolField from "@/components/SymbolField.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues } from "@/test/fixtures";

describe("SymbolField", () => {
  it("is the symbol's picture and name as one button, named Change symbol, and no other button", () => {
    const wrapper = mount(SymbolField, { props: { id: "s", symbol: "/-" } });
    const buttons = wrapper.findAll("button:not(.info-toggle)");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]?.attributes("aria-label")).toBe("Change symbol");
    expect(buttons[0]?.attributes("title")).toBe("Change symbol");
    expect(buttons[0]?.find(".symicon").exists()).toBe(true);
    expect(buttons[0]?.find(".symbolfield-name").text()).toBe("House");
    expect(buttons[0]?.attributes("aria-describedby")).toBe(buttons[0]?.find(".symbolfield-name").attributes("id"));
    expect(wrapper.text()).not.toMatch(/Change|More/);
  });

  it("opens the picker on a click and gives the focus back to the symbol when it closes", async () => {
    const wrapper = mount(SymbolField, { props: { id: "s", symbol: "/-" }, attachTo: document.body });
    await wrapper.find("#s-change").trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(true);
    await wrapper.find(".sympick-head .btn").trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(false);
    await wrapper.vm.$nextTick();
    expect(document.activeElement).toBe(wrapper.find("#s-change").element);
    wrapper.unmount();
  });

  it("says no symbol for a symbol that is none, and still opens the picker", async () => {
    const wrapper = mount(SymbolField, { props: { id: "s", symbol: "" } });
    expect(wrapper.find(".symbolfield-name").text()).toBe("No symbol");
    await wrapper.find("#s-change").trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(true);
  });

  it("is the same control, opened by a click on the symbol, in the Beacon tab, the Objects form and the first-run guide", async () => {
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon(fakeDaemon({ config: configValues() })) });
    const objects = mount(ObjectForm, {
      props: {
        form: useOwnObjects(new Map(), ref({ lat: 60.17, lon: 24.94 }), () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel),
        fallbackPath: "",
      },
    });
    const config = ref(configValues());
    const guide = useSetupGuide(config, ref(null), ref(null), () => true);
    guide.show();
    guide.step = 2;
    const setup = mount(SetupGuide, { global: withDaemon(fakeDaemon({ config, guide })) });
    for (const wrapper of [beacon, objects, setup]) {
      const button = wrapper.find(".symbolfield button.symbolbtn");
      expect(button.attributes("aria-label")).toBe("Change symbol");
      expect(wrapper.findAll(".symbolfield button:not(.symbolbtn):not(.info-toggle)")).toHaveLength(0);
      await button.trigger("click");
      expect(wrapper.find(".sympick").exists()).toBe(true);
      await wrapper.find(".sympick-symbol").trigger("click");
      expect(wrapper.find(".sympick").exists()).toBe(false);
    }
  });
});
