import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectForm from "@/components/ObjectForm.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Command, OwnObjectRow } from "@/protocol/protocol";
import { ownObject } from "@/test/fixtures";

function form(rows: OwnObjectRow[] = []) {
  const table = new Map(rows.map((r) => [r.name, r]));
  const sent: Command[] = [];
  const view = useOwnObjects(table, ref({ lat: 60.17, lon: 24.94 }), (command) => (sent.push(command), true), { show: vi.fn() } as unknown as Panel);
  view.start();
  const wrapper = mount(ObjectForm, { props: { form: view, fallbackPath: "WIDE1-1,WIDE2-1" } });
  const field = (label: string) => wrapper.findAll(".field:not(.location-field)").find((f) => f.find("label").text() === label);
  const input = (label: string) => field(label)?.find<HTMLInputElement>("input");
  return { wrapper, view, sent, field, input, table };
}

describe("ObjectForm", () => {
  it("has the fields a label each and no sentence of help", () => {
    const { wrapper } = form();
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual(["Name", "Symbol", "Latitude", "Longitude", "Comment", "Course", "Speed", "Path"]);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("starts at the place we are, with the car and the path of the beacon as the placeholder", () => {
    const { input, field } = form();
    expect(input("Latitude")?.element.value).toBe("60.17");
    expect(input("Longitude")?.element.value).toBe("24.94");
    expect(field("Symbol")?.find(".symbolfield-name").text()).toBe("Car");
    expect(input("Path")?.attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect(input("Path")?.element.value).toBe("");
  });

  it("says (default) in the path when the beacon has none", () => {
    const view = useOwnObjects(new Map(), ref(null), () => true, { show: vi.fn() } as unknown as Panel);
    view.start();
    const wrapper = mount(ObjectForm, { props: { form: view, fallbackPath: "" } });
    expect(wrapper.find("input[placeholder='(default)']").exists()).toBe(true);
  });

  it("has Save off until the draft is ready, and Cancel", async () => {
    const { wrapper, input } = form();
    const save = wrapper.find<HTMLButtonElement>("button[type='submit']");
    expect(save.text()).toBe("Save");
    expect(save.element.disabled).toBe(true);
    await input("Name")?.setValue("LEADER");
    expect(save.element.disabled).toBe(false);
    expect(wrapper.findAll("button").find((b) => b.text() === "Cancel")).toBeDefined();
  });

  it("takes a name of nine characters at the most, and offers an object or an item", () => {
    const { wrapper, input } = form();
    expect(input("Name")?.attributes("maxlength")).toBe("9");
    expect(
      wrapper
        .find("select[aria-label='Kind']")
        .findAll("option")
        .map((o) => o.text()),
    ).toEqual(["Object", "Item"]);
  });

  it("marks a field that is wrong, with what is wrong in its title, and has Save off", async () => {
    const { wrapper, input, field } = form();
    await input("Name")?.setValue("LEADER");
    await input("Latitude")?.setValue("95");
    expect(field("Latitude")?.classes()).toContain("invalid");
    expect(field("Latitude")?.attributes("title")).toBe("Between -90 and 90");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(true);
    await input("Latitude")?.setValue("60.1");
    expect(field("Latitude")?.classes()).not.toContain("invalid");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
    await input("Name")?.setValue("A!");
    expect(field("Name")?.classes()).toContain("invalid");
    await field("Name")?.find("select").setValue("item");
    await input("Name")?.setValue("AB");
    expect(field("Name")?.attributes("title")).toBe("An item has 3 to 9 characters");
  });

  it("counts the characters the comment has left beside the buttons, fewer behind a course or a speed", async () => {
    const { wrapper, input, field } = form();
    const counter = () => wrapper.find(".composebar-foot .compose-left");
    expect(counter().text()).toBe("43 left");
    expect(field("Comment")?.find(".compose-left").exists()).toBe(false);
    await input("Comment")?.setValue("Rescue 1");
    expect(counter().text()).toBe("35 left");
    await input("Speed")?.setValue("40");
    expect(counter().text()).toBe("28 left");
    await input("Comment")?.setValue("x".repeat(40));
    expect(counter().text()).toBe("4 over");
    expect(counter().classes()).toContain("over");
    expect(field("Comment")?.classes()).toContain("invalid");
  });

  it("shows the symbol as a picture and a name and sets it from the picker, with no table or code to type", async () => {
    const { wrapper, field, view } = form();
    expect(field("Symbol")?.find("input").exists()).toBe(false);
    expect(field("Symbol")?.find(".symicon .stn-layer").exists()).toBe(true);
    await field("Symbol")?.find("button").trigger("click");
    const house = wrapper.findAll(".sympick-symbol").find((b) => b.text() === "House");
    await house?.trigger("click");
    expect(view.draft.symbol).toBe("/-");
    expect(field("Symbol")?.find(".symbolfield-name").text()).toBe("House");
    expect(wrapper.find(".sympick").exists()).toBe(false);
  });

  it("has the Location row of the Beacon tab: Location in the label column, Choose on map in the input column, the place in one line and Enter coordinates under it", () => {
    const { wrapper } = form();
    const row = wrapper.find(".location-field");
    expect(row.classes()).toContain("field");
    expect(row.element.previousElementSibling?.querySelector(".symbolfield, .symbolfield-name")).not.toBeNull(); // (after the symbol, before the comment)
    expect(row.element.nextElementSibling?.querySelector("label")?.textContent).toBe("Comment");
    expect([...row.element.children].map((c) => c.className.split(" ")[0])).toEqual(["field-label", "field-control"]);
    expect(row.find(".field-label").text()).toBe("Location");
    expect([...row.find(".field-control").element.children].map((c) => c.className.split(" ")[0])).toEqual(["btn", "location-line", "disclosure"]);
    expect(row.find(".location-line").text()).toBe("60.17 N, 24.94 E · KP20le");
    expect(row.find("summary").text()).toBe("Enter coordinates");
    expect(row.find<HTMLDetailsElement>("details").element.open).toBe(false);
    expect(row.findAll("input")).toHaveLength(2);
    expect(wrapper.find(".composebar-aside button").exists()).toBe(false);
  });

  it("opens Enter coordinates while there is no place or a coordinate is wrong, and says Not set", async () => {
    const { wrapper, input, view } = form();
    const details = () => wrapper.find<HTMLDetailsElement>(".location-field details").element;
    expect(details().open).toBe(false);
    await input("Latitude")?.setValue("95");
    expect(details().open).toBe(true);
    expect(wrapper.find(".location-line").text()).toBe("Not set");
    expect(wrapper.find(".location-line").classes()).toContain("muted");
    view.cancel();
  });

  it("has Choose on map, which asks for a click on the map and says Cancel while it waits", async () => {
    const { wrapper, view } = form();
    const place = wrapper.find<HTMLButtonElement>("button.location-pick");
    expect(place.text()).toBe("Choose on map");
    expect(place.attributes("aria-pressed")).toBe("false");
    await place.trigger("click");
    expect(view.picking).toBe(true);
    expect(place.attributes("aria-pressed")).toBe("true");
    expect(place.text()).toBe("Cancel");
    view.place(61.5, 25.5);
    await wrapper.vm.$nextTick();
    expect(wrapper.find<HTMLInputElement>("input[inputmode='decimal']").element.value).toBe("61.5");
    expect(wrapper.find(".location-line").text()).toMatch(/^61\.5 N, 25\.5 E · [A-R]{2}\d\d[a-x]{2}$/);
    expect(place.attributes("aria-pressed")).toBe("false");
    expect(place.text()).toBe("Choose on map");
  });

  it("saves what was typed", async () => {
    const { wrapper, input, sent } = form();
    await input("Name")?.setValue("LEADER");
    await input("Comment")?.setValue("Rescue 1");
    await input("Course")?.setValue("88");
    await input("Speed")?.setValue("40");
    await input("Path")?.setValue("wide2-1");
    await wrapper.find("form").trigger("submit");
    expect(sent).toEqual([
      {
        cmd: "object_set",
        name: "LEADER",
        kind: "object",
        lat: 60.17,
        lon: 24.94,
        symbol_table: "/",
        symbol_code: ">",
        comment: "Rescue 1",
        course_deg: 88,
        speed_kmh: 40,
        path: "WIDE2-1",
      },
    ]);
  });

  it("keeps the name of an object that is being changed", () => {
    const { view, wrapper } = form([ownObject("LEADER", { comment: "Rescue 1" })]);
    view.edit("LEADER");
    return wrapper.vm.$nextTick().then(() => {
      const name = wrapper.find<HTMLInputElement>("input[maxlength='9']");
      expect(name.element.value).toBe("LEADER");
      expect(name.attributes("readonly")).toBeDefined();
    });
  });

  it("closes with Cancel and sends nothing", async () => {
    const { wrapper, view, sent } = form();
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Cancel")
      ?.trigger("click");
    expect(view.open).toBe(false);
    expect(sent).toEqual([]);
  });
});
