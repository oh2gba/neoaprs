// The rule of the Settings tab: an action button that is a row of its own (Download map, Check now, Download logs) sits in the control column of a labelled row, first, with its (i) after it and the quiet lines of its outcome under it.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ActionRow from "@/components/ActionRow.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { mapState } from "@/test/fixtures";

describe("ActionRow", () => {
  it("is a labelled row of the form's grid: the label for the button, the slot, the (i), and the notes in their own cell", () => {
    const wrapper = mount(ActionRow, {
      props: { id: "go", label: "Go", tipLabel: "About go" },
      slots: { default: '<button id="go" class="btn">Go now</button>', tip: "<span>what it does</span>", notes: "<p>done</p>" },
    });
    const row = wrapper.get(".field.action-row");
    expect(row.get("label").attributes("for")).toBe("go");
    expect(row.get(".field-control").element.firstElementChild?.id).toBe("go");
    expect(row.get(".field-control").element.lastElementChild?.classList.contains("infotip")).toBe(true);
    expect(row.get(".action-notes").text()).toBe("done");
    expect(row.element.children[2]).toBe(row.get(".action-notes").element);
  });
});

describe("the action rows of the Settings tab", () => {
  const form = () => mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(fakeDaemon({ map: mapState() })) });

  it.each([
    ["Detailed map", "Download map"],
    ["New version", "Check now"],
    ["Logs", "Download logs"],
  ])("%s has its button, %s, first in the control column of its own row, with an (i) after it", (label, button) => {
    const row = form()
      .findAll(".field.action-row")
      .find((r) => r.get("label").text() === label);
    expect(row, label).toBeDefined();
    const control = row?.get(".field-control").element;
    expect(control?.firstElementChild?.textContent?.trim()).toBe(button);
    expect(control?.querySelector(".infotip")).not.toBeNull();
    expect(row?.get("label").attributes("for")).toBe(control?.firstElementChild?.id);
  });

  it("has no other button of a row of its own: the rest sit beside the field they belong to (the Test of the command, Refresh of the port)", () => {
    const rows = form().findAll(".field.action-row");
    expect(rows.map((r) => r.get("label").text())).toEqual(["Detailed map", "New version", "Logs"]);
  });
});
