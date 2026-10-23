import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { useLayout } from "@/composables/useLayout";
import { usePanel } from "@/composables/usePanel";

const mounted: { unmount: () => void }[] = [];

function window_(width: number, height: number): void {
  window.innerWidth = width;
  window.innerHeight = height;
  window.dispatchEvent(new Event("resize"));
}

function setUp(width = 390, height = 844) {
  window.innerWidth = width;
  window.innerHeight = height;
  const guideOpen = ref(false);
  const picking = ref(false);
  let made!: { panel: ReturnType<typeof usePanel>; layout: ReturnType<typeof useLayout> };
  mounted.push(
    mount(
      defineComponent({
        setup() {
          const panel = usePanel();
          made = { panel, layout: useLayout(panel, guideOpen, picking) };
          return () => h("div");
        },
      }),
    ),
  );
  return { ...made, guideOpen, picking };
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("useLayout: the size", () => {
  it("is the size class of the window, and follows it when the window is resized or turned", async () => {
    const { layout } = setUp(390, 844);
    expect([layout.size.value, layout.phone.value, layout.capacity.value]).toEqual(["phone", true, 1]);
    window_(844, 390);
    await nextTick();
    expect(layout.size.value).toBe("phone"); // (held sideways)
    window_(768, 1024);
    await nextTick();
    expect([layout.size.value, layout.phone.value, layout.capacity.value]).toEqual(["tablet", false, 2]);
    window_(1280, 800);
    await nextTick();
    expect([layout.size.value, layout.capacity.value]).toEqual(["desktop", 4]);
    window_(1920, 1080);
    await nextTick();
    expect(layout.capacity.value).toBe(6);
  });

  it("puts the size, the view of a phone and the guide on the root of the page", async () => {
    const { layout, guideOpen } = setUp();
    expect(layout.rootClass.value).toEqual(["size-phone", "view-map", ""]);
    guideOpen.value = true;
    expect(layout.rootClass.value).toEqual(["size-phone", "view-map", "guide-open"]);
    window_(1280, 800);
    await nextTick();
    expect(layout.rootClass.value).toEqual(["size-desktop", "", "guide-open"]);
  });
});

describe("useLayout: what a phone shows", () => {
  it("starts on the map, and remembers the view it was left in", async () => {
    const { layout } = setUp();
    expect(layout.showing.value).toBe("map");
    layout.view.value = "panel";
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.view")).toBe("panel");
    expect(setUp().layout.showing.value).toBe("panel");
  });

  it("brings the panel when the page asks for a tab (the unread mail, a card's Message), and the map when it is asked for", async () => {
    const { layout, panel } = setUp();
    panel.show("messages");
    await nextTick();
    expect(layout.showing.value).toBe("panel");
    layout.showMap();
    expect(layout.showing.value).toBe("map");
  });

  it("shows the map while the first-run guide is open, and the view it was in when the guide is closed", () => {
    const { layout, guideOpen } = setUp();
    layout.view.value = "panel";
    guideOpen.value = true;
    expect(layout.showing.value).toBe("map");
    guideOpen.value = false;
    expect(layout.showing.value).toBe("panel");
  });

  it("shows the map for a place to pick, and brings the tab back when the place is picked or the picking cancelled", async () => {
    const { layout, picking } = setUp();
    layout.view.value = "panel";
    picking.value = true;
    await nextTick();
    expect(layout.showing.value).toBe("map");
    picking.value = false; // the click on the map
    await nextTick();
    expect(layout.showing.value).toBe("panel");
    // from the map itself there is no tab to go back to
    layout.view.value = "map";
    picking.value = true;
    await nextTick();
    picking.value = false;
    await nextTick();
    expect(layout.showing.value).toBe("map");
  });

  it("does not take the view away from a tablet or a desktop, where the map and the panel are both there", async () => {
    const { layout, picking } = setUp(1280, 800);
    layout.view.value = "panel";
    picking.value = true;
    await nextTick();
    picking.value = false;
    await nextTick();
    expect(layout.view.value).toBe("panel");
    expect(layout.phone.value).toBe(false);
  });
});
