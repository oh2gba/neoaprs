import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectForm from "@/components/ObjectForm.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Command, OwnObjectRow } from "@/protocol/protocol";
import { ownObject } from "@/test/fixtures";

/** The form with a place picked (60.17, 24.94), unless `placed` is false: a new object has none to start with. */
function form(rows: OwnObjectRow[] = [], placed = true) {
  const table = new Map(rows.map((r) => [r.name, r]));
  const sent: Command[] = [];
  const view = useOwnObjects(table, (command) => (sent.push(command), true), {
    show: vi.fn(),
    tab: ref("objects"),
  } as unknown as Panel);
  if (placed) view.place(60.17, 24.94);
  const wrapper = mount(ObjectForm, { props: { form: view, fallbackPath: "WIDE1-1,WIDE2-1" } });
  const field = (label: string) => wrapper.findAll(".field:not(.location-field)").find((f) => f.find("label").text() === label);
  const input = (label: string) => field(label)?.find<HTMLInputElement>("input");
  /** The entry under the place (latitude, longitude, locator), opened by a click on the place. */
  const entry = async () => {
    if (!wrapper.find(".location-entry").exists()) await wrapper.find(".location-place").trigger("click");
    return wrapper.find(".location-entry");
  };
  const coordinate = async (label: "Latitude" | "Longitude" | "Locator") => (await entry()).findAll(".field").find((f) => f.find("label").text() === label);
  return { wrapper, view, sent, field, input, table, entry, coordinate };
}

describe("ObjectForm", () => {
  it("has the fields a label each and no sentence of help", () => {
    const { wrapper } = form();
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual(["Name", "Symbol", "Comment", "Course", "Speed", "Path", "Category"]);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("starts with no place, with the repeater and the path of the beacon as the placeholder", async () => {
    const { wrapper, input, field, coordinate, view } = form([], false);
    expect(wrapper.find(".location-place").text()).toBe("Not set");
    expect(view.draft).toMatchObject({ lat: "", lon: "" });
    expect((await coordinate("Latitude"))?.find("input").element.value).toBe("");
    expect((await coordinate("Longitude"))?.find("input").element.value).toBe("");
    expect((await coordinate("Locator"))?.find("input").element.value).toBe("");
    expect(field("Symbol")?.find(".symbolfield-name").text()).toBe("Antenna");
    expect(input("Path")?.attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect(input("Path")?.element.value).toBe("");
  });

  it("has Add off, with Choose a place first as its title, while there is no place or it is wrong, however much else is filled in", async () => {
    const { wrapper, input, coordinate } = form([], false);
    const main = wrapper.find<HTMLButtonElement>("button[type='submit']");
    await input("Name")?.setValue("MARK");
    expect(main.element.disabled).toBe(true);
    expect(main.attributes("title")).toBe("Choose a place first");
    await (await coordinate("Latitude"))?.find("input").setValue("60.1");
    expect(main.element.disabled).toBe(true); // (a latitude alone is no place)
    expect(main.attributes("title")).toBe("Choose a place first");
    await (await coordinate("Longitude"))?.find("input").setValue("24.9");
    expect(main.element.disabled).toBe(false);
    expect(main.attributes("title")).toBeUndefined();
    await (await coordinate("Longitude"))?.find("input").setValue("240");
    expect(main.element.disabled).toBe(true);
    expect(main.attributes("title")).toBe("Choose a place first");
    await wrapper.find("form").trigger("submit");
  });

  it("clears the whole form of a new object with Cancel, and puts the symbol back", async () => {
    const { wrapper, input, field, view } = form([], false);
    const cancel = () => wrapper.findAll("button").find((b) => b.text() === "Cancel");
    expect(cancel()?.attributes("disabled")).toBeDefined();
    await input("Name")?.setValue("MARK");
    await input("Comment")?.setValue("typed");
    await input("Speed")?.setValue("40");
    await input("Path")?.setValue("WIDE1-1");
    await field("Symbol")?.find("button.symbolbtn").trigger("click");
    await wrapper
      .findAll(".sympick-symbol")
      .find((b) => b.text() === "House")
      ?.trigger("click");
    view.place(61, 25);
    await wrapper.vm.$nextTick();
    expect(cancel()?.attributes("disabled")).toBeUndefined();
    await cancel()?.trigger("click");
    expect(view.draft).toMatchObject({ name: "", comment: "", speed: "", path: "", lat: "", lon: "", symbol: "/r" });
    expect(["Name", "Comment", "Speed", "Path"].map((label) => input(label)?.element.value)).toEqual(["", "", "", ""]);
    expect(wrapper.find(".location-place").text()).toBe("Not set");
    expect(field("Symbol")?.find(".symbolfield-name").text()).toBe("Antenna");
    expect(cancel()?.attributes("disabled")).toBeDefined();
  });

  it("drops the unsaved changes of an object being changed with Cancel, and leaves the form as a new one", async () => {
    const { wrapper, input, view, sent } = form([ownObject("LEADER", { comment: "Rescue 1", path: "WIDE2-1", qru_group: "NET" })], false);
    const cancel = () => wrapper.findAll("button").find((b) => b.text() === "Cancel");
    view.edit("LEADER");
    await wrapper.vm.$nextTick();
    expect(input("Name")?.element.value).toBe("LEADER");
    await input("Comment")?.setValue("changed");
    await cancel()?.trigger("click");
    expect(view.editing).toBeNull();
    expect(input("Name")?.element.value).toBe("");
    expect(input("Comment")?.element.value).toBe("");
    expect(input("Path")?.element.value).toBe("");
    expect(wrapper.find(".location-place").text()).toBe("Not set");
    expect(wrapper.find("button[type='submit']").text()).toBe("Add");
    expect(sent).toEqual([]);
  });

  it("says (default) in the path when the beacon has none", () => {
    const view = useOwnObjects(new Map(), () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
    const wrapper = mount(ObjectForm, { props: { form: view, fallbackPath: "" } });
    expect(wrapper.find("input[placeholder='(default)']").exists()).toBe(true);
  });

  it("has Add, off until the draft is ready, for a new object, and Save for the one that is selected, and a plain Cancel beside it", async () => {
    const { wrapper, input, view } = form([ownObject("LEADER")]);
    const main = wrapper.find<HTMLButtonElement>("button[type='submit']");
    expect(main.text()).toBe("Add");
    expect(main.classes()).toContain("primary");
    expect(main.element.disabled).toBe(true);
    await input("Name")?.setValue("MARK");
    expect(main.element.disabled).toBe(false);
    const cancel = wrapper.findAll("button").find((b) => b.text() === "Cancel");
    expect(cancel?.classes()).not.toContain("primary");
    expect(cancel?.element.nextElementSibling).toBe(main.element);
    view.edit("LEADER");
    await wrapper.vm.$nextTick();
    expect(main.text()).toBe("Save");
    expect(main.classes()).toContain("primary");
    expect(wrapper.find("form").attributes("aria-label")).toBe("Edit LEADER");
    view.cancel();
    await wrapper.vm.$nextTick();
    expect(main.text()).toBe("Add");
    expect(wrapper.find("form").attributes("aria-label")).toBe("Add an object");
  });

  it("takes a name of nine characters at the most, and has no choice of kind", () => {
    const { wrapper, input } = form();
    expect(input("Name")?.attributes("maxlength")).toBe("9");
    expect(wrapper.findAll("select").map((s) => s.attributes("id")?.endsWith("-category"))).toEqual([true]); // (the Category is the only choice; none of the kind)
  });

  it("makes an object, always, for a new one", async () => {
    const { wrapper, input, sent } = form();
    await input("Name")?.setValue("LEADER");
    await wrapper.find("form").trigger("submit");
    expect(sent.map((c) => (c.cmd === "object_set" ? c.kind : null))).toEqual(["object"]);
  });

  it("changes an item of ours as an item, and a new one after it is an object again", async () => {
    const { view, wrapper, input, sent } = form([ownObject("AID", { kind: "item", comment: "First aid" })]);
    view.edit("AID");
    await wrapper.vm.$nextTick();
    await input("Comment")?.setValue("Moved");
    await wrapper.find("form").trigger("submit");
    expect(sent).toMatchObject([{ cmd: "object_set", name: "AID", kind: "item", comment: "Moved" }]);
    view.cancel();
    await wrapper.vm.$nextTick();
    view.place(60.17, 24.94);
    await input("Name")?.setValue("NEWONE");
    await wrapper.find("form").trigger("submit");
    expect(sent[1]).toMatchObject({ cmd: "object_set", name: "NEWONE", kind: "object" });
  });

  it("marks a field that is wrong, with what is wrong in its title (under it, for a coordinate), and has Add off", async () => {
    const { wrapper, input, field, coordinate } = form();
    await input("Name")?.setValue("LEADER");
    const latitude = async () => coordinate("Latitude");
    await (await latitude())?.find("input").setValue("95");
    expect((await latitude())?.classes()).toContain("invalid");
    expect((await latitude())?.find(".field-error").text()).toBe("Between -90 and 90");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(true);
    await (await latitude())?.find("input").setValue("60.1");
    expect((await latitude())?.classes()).not.toContain("invalid");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
    await input("Name")?.setValue("A!");
    expect(field("Name")?.classes()).toContain("invalid");
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
    expect(field("Symbol")?.findAll("button:not(.info-toggle)")).toHaveLength(1); // (the picture and its name are the button: there is no Change)
    await field("Symbol")?.find("button.symbolbtn").trigger("click");
    const house = wrapper.findAll(".sympick-symbol").find((b) => b.text() === "House");
    await house?.trigger("click");
    expect(view.draft.symbol).toBe("/-");
    expect(field("Symbol")?.find(".symbolfield-name").text()).toBe("House");
    expect(wrapper.find(".sympick").exists()).toBe(false);
  });

  it("has the Location row of the My station tab: Location in the label column, Choose on map and the place on one line in the input column", () => {
    const { wrapper } = form();
    const row = wrapper.find(".location-field");
    expect(row.classes()).toContain("field");
    expect(row.element.previousElementSibling?.querySelector(".symbolfield, .symbolfield-name")).not.toBeNull(); // (after the symbol, before the comment)
    expect(row.element.nextElementSibling?.querySelector("label")?.textContent).toBe("Comment");
    expect([...row.element.children].map((c) => c.className.split(" ")[0])).toEqual(["field-label", "field-control"]);
    expect(row.find(".field-label").text()).toBe("Location");
    expect([...row.find(".field-control").element.children].map((c) => c.className.split(" ")[0])).toEqual(["btn", "location-place"]);
    expect(row.find(".btn").classes()).not.toContain("primary");
    expect(row.find(".location-place").text()).toBe("60.17 N, 24.94 E · KP20le");
    expect(row.find(".location-entry").exists()).toBe(false);
    expect(row.find("details").exists()).toBe(false);
    expect(wrapper.find(".composebar-aside button").exists()).toBe(false);
  });

  it("opens the entry (latitude, longitude, locator) by a click on the place, and closes it by another", async () => {
    const { wrapper, coordinate } = form();
    const place = wrapper.find(".location-place");
    expect(place.attributes("aria-expanded")).toBe("false");
    await place.trigger("click");
    expect(place.attributes("aria-expanded")).toBe("true");
    expect(wrapper.findAll(".location-entry label").map((l) => l.text())).toEqual(["Latitude", "Longitude", "Locator"]);
    expect((await coordinate("Locator"))?.find("input").element.value).toBe("KP20le");
    await place.trigger("click");
    expect(wrapper.find(".location-entry").exists()).toBe(false);
  });

  it("keeps the entry closed while there is no place (Not set is the thing to click), and opens by itself when a coordinate is wrong", async () => {
    const { wrapper, view, coordinate } = form([], false);
    expect(wrapper.find(".location-entry").exists()).toBe(false);
    await (await coordinate("Latitude"))?.find("input").setValue("95");
    expect(wrapper.find(".location-place").text()).toBe("Not set");
    expect(wrapper.find(".location-place").classes()).toContain("muted");
    view.cancel();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".location-entry").exists()).toBe(true); // (never closed by the page)
    const blank = form();
    blank.view.draft.lat = "";
    blank.view.draft.lon = "";
    await blank.wrapper.vm.$nextTick();
    expect(blank.wrapper.find(".location-entry").exists()).toBe(false);
    expect(blank.wrapper.find(".location-place").text()).toBe("Not set");
    await blank.wrapper.find(".location-place").trigger("click");
    expect(blank.wrapper.find(".location-entry").exists()).toBe(true);
  });

  it("takes a Maidenhead locator for the place: the centre of its square fills the coordinates, which write the locator again", async () => {
    const { wrapper, view, coordinate } = form();
    await (await coordinate("Locator"))?.find("input").setValue("KP20ie");
    expect(view.draft.lat).toBe("60.1875");
    expect(view.draft.lon).toBe("24.7083");
    expect(wrapper.find(".location-place").text()).toBe("60.1875 N, 24.7083 E · KP20ie");
    expect((await coordinate("Locator"))?.find("input").element.value).toBe("KP20ie"); // (as typed)
    await (await coordinate("Latitude"))?.find("input").setValue("60.17");
    await (await coordinate("Longitude"))?.find("input").setValue("24.94");
    expect((await coordinate("Locator"))?.find("input").element.value).toBe("KP20le");
    await (await coordinate("Locator"))?.find("input").setValue("SS00aa");
    expect((await coordinate("Locator"))?.find(".field-error").text()).toBe("Not a locator");
    expect(view.draft.lat).toBe("60.17"); // (a locator that is none changes nothing)
    await (await coordinate("Locator"))?.find("input").setValue("KP20i");
    expect((await coordinate("Locator"))?.find(".field-error").exists()).toBe(false); // (still being typed)
  });

  it("has Choose on map, which asks for a click on the map and says Cancel while it waits", async () => {
    const { wrapper, view, coordinate } = form();
    const place = wrapper.find<HTMLButtonElement>("button.location-pick");
    expect(place.text()).toBe("Choose on map");
    expect(place.attributes("aria-pressed")).toBe("false");
    await place.trigger("click");
    expect(view.picking).toBe(true);
    expect(place.attributes("aria-pressed")).toBe("true");
    expect(place.text()).toBe("Cancel");
    view.place(61.5, 25.5);
    await wrapper.vm.$nextTick();
    expect((await coordinate("Latitude"))?.find("input").element.value).toBe("61.5");
    expect(wrapper.find(".location-place").text()).toMatch(/^61\.5 N, 25\.5 E · [A-R]{2}\d\d[a-x]{2}$/);
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
        symbol_code: "r",
        comment: "Rescue 1",
        course_deg: 88,
        speed_kmh: 40,
        path: "WIDE2-1",
        qru_group: "",
        on_request: false,
      },
    ]);
  });

  it("offers the standard categories by their plain names with the code as the value, none first and Other last, and sends the code", async () => {
    const { wrapper, field, sent } = form();
    const select = () => field("Category")?.find<HTMLSelectElement>("select");
    const options = select()?.findAll("option");
    expect(options?.map((o) => o.text()).slice(0, 4)).toEqual(["None", "2 m repeater", "70 cm repeater", "6 m repeater"]);
    expect(options?.at(-1)?.text()).toBe("Other…");
    expect(options?.map((o) => o.element.value).slice(0, 3)).toEqual(["", "RP2M", "RP70"]);
    expect(select()?.element.value).toBe("");
    await wrapper.find<HTMLInputElement>("input[maxlength='9']").setValue("PUB");
    await select()?.setValue("FOOD");
    await wrapper.find("form").trigger("submit");
    expect(sent).toMatchObject([{ cmd: "object_set", name: "PUB", qru_group: "FOOD", on_request: false }]);
  });

  it("shows Send only when asked only with a category, and drops its tick with the category", async () => {
    const { wrapper, field, input, sent } = form();
    const select = () => field("Category")?.find<HTMLSelectElement>("select");
    expect(field("Send only when asked")).toBeUndefined();
    await select()?.setValue("RP70");
    expect(input("Send only when asked")?.element.checked).toBe(false);
    await input("Send only when asked")?.setValue(true);
    await select()?.setValue("");
    expect(field("Send only when asked")).toBeUndefined();
    await wrapper.find<HTMLInputElement>("input[maxlength='9']").setValue("PUB");
    await wrapper.find("form").trigger("submit");
    expect(sent).toMatchObject([{ cmd: "object_set", qru_group: "", on_request: false }]);
  });

  it("takes a word of our own with Other…, in capitals, in a field with its (i), and sends it", async () => {
    const { wrapper, input, field, sent } = form();
    const select = () => field("Category")?.find<HTMLSelectElement>("select");
    expect(field("Code")).toBeUndefined();
    await select()?.setValue("other");
    expect(select()?.element.value).toBe("other");
    expect(input("Code")?.attributes("maxlength")).toBe("8");
    await field("Code")?.find(".info-toggle").trigger("click");
    expect(wrapper.find(".info-text .info-line").text()).toBe(
      "Your own category: 8 letters or digits at most, not INFO or NEXT. Stations ask for it by this word.",
    );
    await input("Code")?.setValue("mynet");
    expect(input("Code")?.element.value).toBe("MYNET");
    expect(field("Code")?.classes()).not.toContain("invalid");
    await input("Send only when asked")?.setValue(true);
    await wrapper.find<HTMLInputElement>("input[maxlength='9']").setValue("PUB");
    await wrapper.find("form").trigger("submit");
    expect(sent).toMatchObject([{ cmd: "object_set", name: "PUB", qru_group: "MYNET", on_request: true }]);
  });

  it("marks an own category that is a word the protocol keeps for itself or has a character it cannot, and Save is off", async () => {
    const { wrapper, input, field } = form();
    await input("Name")?.setValue("PUB");
    await field("Category")?.find("select").setValue("other");
    for (const group of ["INFO", "next", "R P", "LIFEBOATS"]) {
      await input("Code")?.setValue(group);
      expect(field("Code")?.classes(), group).toContain("invalid");
      expect(field("Code")?.attributes("title")).toBe("Up to 8 letters and digits, not INFO or NEXT");
      expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(true);
    }
    await input("Code")?.setValue("");
    expect(wrapper.find<HTMLButtonElement>("button[type='submit']").element.disabled).toBe(false);
  });

  it("opens an object being changed with its category and its choice, and one with a code of our own as Other… with the code", async () => {
    const { view, input, field, wrapper } = form([ownObject("PUB", { qru_group: "FOOD", on_request: true }), ownObject("NET", { qru_group: "MYNET" })]);
    view.edit("PUB");
    await wrapper.vm.$nextTick();
    expect(field("Category")?.find<HTMLSelectElement>("select").element.value).toBe("FOOD");
    expect(field("Code")).toBeUndefined();
    expect(input("Send only when asked")?.element.checked).toBe(true);
    view.cancel();
    view.edit("NET");
    await wrapper.vm.$nextTick();
    expect(field("Category")?.find<HTMLSelectElement>("select").element.value).toBe("other");
    expect(input("Code")?.element.value).toBe("MYNET");
  });

  it("keeps Course and Speed behind a closed fold, Moving, for a new object", () => {
    const { wrapper, field } = form();
    const moving = wrapper.findAll<HTMLDetailsElement>("details").find((d) => d.find("summary").text() === "Moving");
    expect(moving?.exists()).toBe(true);
    expect(moving?.element.open).toBe(false);
    expect(moving?.findAll("label").map((l) => l.text())).toEqual(["Course", "Speed"]);
    expect(field("Course")?.element.closest("details")).toBe(moving?.element);
    expect(field("Path")?.element.closest("details")).not.toBe(moving?.element);
  });

  it("keeps Path and Category behind a closed fold, Advanced, as the My station tab does, for a new object", () => {
    const { wrapper, field } = form();
    const folds = wrapper.findAll<HTMLDetailsElement>("details");
    expect(folds.map((d) => d.find("summary").text())).toEqual(["Moving", "Advanced"]);
    const advanced = folds[1];
    expect(advanced.element.open).toBe(false);
    expect(advanced.findAll("label").map((l) => l.text())).toEqual(["Path", "Category"]);
    for (const label of ["Path", "Category"]) expect(field(label)?.element.closest("details")).toBe(advanced.element);
    expect(folds.every((d) => d.classes().includes("disclosure") && d.classes().includes("settings-fold"))).toBe(true);
  });

  it("opens Advanced by itself for an object that has a path, a group or the tick, and keeps it closed for one that has none", async () => {
    const { view, wrapper } = form([
      ownObject("PLAIN"),
      ownObject("ROUTED", { path: "WIDE2-1" }),
      ownObject("GROUP", { qru_group: "FOOD" }),
      ownObject("ASKED", { on_request: true }),
    ]);
    const open = () => wrapper.findAll<HTMLDetailsElement>("details").find((d) => d.find("summary").text() === "Advanced")?.element.open;
    for (const [name, expected] of [
      ["PLAIN", false],
      ["ROUTED", true],
      ["PLAIN", false],
      ["GROUP", true],
      ["PLAIN", false],
      ["ASKED", true],
    ] as const) {
      view.cancel();
      view.edit(name);
      await wrapper.vm.$nextTick();
      expect(open(), name).toBe(expected);
    }
  });

  it("has an (i) after every field that is ours, each of one short line, named About and the field", async () => {
    const { wrapper, field } = form();
    for (const label of ["Name", "Comment", "Course", "Speed", "Path", "Category"]) {
      const tip = field(label)?.find(".info-toggle");
      expect(tip?.attributes("aria-label"), label).toBe(`About ${label}`);
      await tip?.trigger("click");
      expect(wrapper.findAll(".info-text .info-line"), label).toHaveLength(1);
      if (label === "Category")
        expect(wrapper.find(".info-text .info-line").text()).toBe("Give an object a category to offer it to stations that ask for local info.");
      if (label === "Send only when asked")
        expect(wrapper.find(".info-text .info-line").text()).toBe("Not beaconed; sent only to a station that asks with ?APRSO or QRU.");
      await tip?.trigger("click");
    }
  });

  it("opens Moving by itself for an object that has a course or a speed, and keeps it closed for one that has neither", async () => {
    const { view, wrapper } = form([
      ownObject("LEADER", { course_deg: 88, speed_kmh: null }),
      ownObject("FAST", { course_deg: null, speed_kmh: 40 }),
      ownObject("MEET"),
    ]);
    const open = () => wrapper.findAll<HTMLDetailsElement>("details").find((d) => d.find("summary").text() === "Moving")?.element.open;
    view.edit("MEET");
    await wrapper.vm.$nextTick();
    expect(open()).toBe(false);
    view.edit("LEADER");
    await wrapper.vm.$nextTick();
    expect(open()).toBe(true);
    view.cancel();
    view.edit("FAST");
    await wrapper.vm.$nextTick();
    expect(open()).toBe(true);
  });

  it("still sends the course and speed of an object that was changed from behind the fold", async () => {
    const { view, wrapper, sent, input } = form([ownObject("LEADER", { course_deg: 88, speed_kmh: 40 })]);
    view.edit("LEADER");
    await wrapper.vm.$nextTick();
    await input("Comment")?.setValue("Rescue 1");
    await wrapper.find("form").trigger("submit");
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ cmd: "object_set", name: "LEADER", comment: "Rescue 1", course_deg: 88, speed_kmh: 40 });
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

  it("has Cancel off while nothing is selected or typed, and with it leaves the selection, clears the form and sends nothing", async () => {
    const { wrapper, view, sent, input } = form([ownObject("LEADER", { comment: "Rescue 1" })], false);
    const cancel = () => wrapper.findAll<HTMLButtonElement>("button").find((b) => b.text() === "Cancel");
    expect(cancel()?.element.disabled).toBe(true);
    view.edit("LEADER");
    await wrapper.vm.$nextTick();
    expect(cancel()?.element.disabled).toBe(false);
    await input("Comment")?.setValue("Changed");
    await cancel()?.trigger("click");
    expect(view.editing).toBeNull();
    expect(view.dirty).toBe(false);
    expect(input("Name")?.element.value).toBe("");
    expect(input("Comment")?.element.value).toBe("");
    expect(input("Name")?.attributes("readonly")).toBeUndefined();
    expect(cancel()?.element.disabled).toBe(true);
    await input("Name")?.setValue("NEW");
    expect(cancel()?.element.disabled).toBe(false);
    expect(sent).toEqual([]);
  });

  it("steps the course and the speed with Up and Down, by one, with Shift by ten", async () => {
    const { input, view } = form();
    const course = input("Course")!;
    await course.trigger("keydown", { key: "ArrowUp" });
    expect(view.draft.course).toBe("1");
    await course.trigger("keydown", { key: "ArrowUp", shiftKey: true });
    expect(view.draft.course).toBe("11");
    await course.trigger("keydown", { key: "ArrowDown", shiftKey: true });
    await course.trigger("keydown", { key: "ArrowDown" });
    await course.trigger("keydown", { key: "ArrowDown" });
    expect(view.draft.course).toBe("359");
    expect(course.element.value).toBe("359");
    const speed = input("Speed")!;
    await speed.trigger("keydown", { key: "ArrowUp", shiftKey: true });
    await speed.trigger("keydown", { key: "ArrowDown" });
    expect(view.draft.speed).toBe("9");
  });
});
