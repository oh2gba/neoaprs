import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailContacts from "@/components/EmailContacts.vue";
import type { Contact } from "@/lib/contacts";

const contacts: Contact[] = [
  { name: "me", address: "jane@example.com", state: "confirmed" },
  { name: "bob", address: "bob@example.org", state: "unconfirmed" },
  { name: "zoe", address: "zoe@example.net", state: "sending" },
];

function panel(connected = true, list: Contact[] = contacts) {
  return mount(EmailContacts, { props: { connected, contacts: list } });
}
type Panel = ReturnType<typeof panel>;
const rows = (wrapper: Panel) => wrapper.findAll(".contact");
const button = (row: ReturnType<Panel["find"]>, label: string) => {
  const found = row.findAll("button").find((b) => b.text() === label || (label === "Remove" && b.text() === "sure?"));
  if (found === undefined) throw new Error(`no button ${label}`);
  return found;
};
const add = (wrapper: Panel) => wrapper.find<HTMLButtonElement>("button[type='submit']");
const fill = async (wrapper: Panel, name: string, address: string) => {
  await wrapper.find("#contact-name").setValue(name);
  await wrapper.find("#contact-address").setValue(address);
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("EmailContacts: the list", () => {
  it("has a row for each contact with its name and address", () => {
    const wrapper = panel();
    expect(rows(wrapper).map((r) => [r.find(".contact-name").text(), r.find(".contact-address").text()])).toEqual([
      ["me", "jane@example.com"],
      ["bob", "bob@example.org"],
      ["zoe", "zoe@example.net"],
    ]);
  });

  it("has Mail, Email me the list and Remove on each row", () => {
    const wrapper = panel();
    for (const r of rows(wrapper)) expect(r.findAll("button").map((b) => b.text())).toEqual(["Mail", "Email me the list", "Remove"]);
  });

  it("says Not confirmed on a contact whose registration was never acked, and Sending on one being sent, and nothing on the others", () => {
    const wrapper = panel();
    expect(rows(wrapper).map((r) => (r.find(".contact-state").exists() ? r.find(".contact-state").text() : null))).toEqual([null, "Not confirmed", "Sending"]);
    expect(rows(wrapper)[1]?.find(".contact-state").attributes("title")).toContain("iGate");
  });

  it("says there are no contacts yet", () => {
    const wrapper = panel(true, []);
    expect(wrapper.find(".empty").text()).toBe("No contacts yet.");
    expect(wrapper.find(".contact-list").exists()).toBe(false);
    expect(wrapper.find("form").exists()).toBe(true);
  });
});

describe("EmailContacts: Mail, Email me the list, Remove", () => {
  it("passes up the name for Mail, with the TNC connected or not", async () => {
    const wrapper = panel(false);
    await button(rows(wrapper)[1], "Mail").trigger("click");
    expect(wrapper.emitted("mail")).toEqual([["bob"]]);
  });

  it("passes up the name for Email me the list, with the command as its title", async () => {
    const wrapper = panel();
    const list = button(rows(wrapper)[0], "Email me the list");
    expect(list.attributes("title")).toBe("Sends 'me L': the gateway emails the list of your contacts to jane@example.com");
    await list.trigger("click");
    expect(wrapper.emitted("list")).toEqual([["me"]]);
  });

  it("removes a contact only after a second click, and forgets the first after 5 seconds", async () => {
    const wrapper = panel();
    const row = () => rows(wrapper)[0];
    expect(button(row(), "Remove").attributes("title")).toBe("Sends 'me R': the gateway forgets me");
    await button(row(), "Remove").trigger("click");
    expect(button(row(), "Remove").text()).toBe("sure?");
    expect(button(row(), "Remove").classes()).toContain("danger");
    expect(rows(wrapper)[1]?.text()).not.toContain("sure?");
    expect(wrapper.emitted("remove")).toBeUndefined();
    vi.advanceTimersByTime(5000);
    await wrapper.vm.$nextTick();
    expect(button(row(), "Remove").text()).toBe("Remove");
    await button(row(), "Remove").trigger("click");
    await button(row(), "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["me"]]);
    expect(button(row(), "Remove").text()).toBe("Remove");
  });

  it("asks twice for the contact it was pressed on: another contact's Remove does not finish it", async () => {
    const wrapper = panel();
    await button(rows(wrapper)[0], "Remove").trigger("click");
    await button(rows(wrapper)[1], "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    await button(rows(wrapper)[1], "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["bob"]]);
  });

  it("has Email me the list and Remove off while the TNC is not connected, and says why", () => {
    const wrapper = panel(false);
    for (const r of rows(wrapper)) {
      for (const label of ["Email me the list", "Remove"]) {
        expect(button(r, label).attributes("disabled")).toBeDefined();
        expect(button(r, label).attributes("title")).toBe("The TNC is not connected");
      }
      expect(button(r, "Mail").attributes("disabled")).toBeUndefined();
    }
  });
});

describe("EmailContacts: Add contact", () => {
  it("has Name and Address, the buttons Close and Add contact", () => {
    const wrapper = panel();
    expect(wrapper.find("label[for='contact-name']").text()).toBe("Name");
    expect(wrapper.find("#contact-name").attributes("placeholder")).toBe("john");
    expect(wrapper.find("label[for='contact-address']").text()).toBe("Address");
    expect(wrapper.find("#contact-address").attributes("placeholder")).toBe("name@example.com");
    expect(
      wrapper
        .find("form")
        .findAll("button")
        .map((b) => b.text()),
    ).toEqual(["Close", "Add contact"]);
  });

  it("is off until the name is letters and digits and the address is an address that fits with it in 67 characters", async () => {
    const wrapper = panel();
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    await fill(wrapper, "john", "");
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    await fill(wrapper, "not a name", "jane@example.com");
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    await fill(wrapper, "john", "jane");
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    await fill(wrapper, "john", `${"x".repeat(60)}@example.com`);
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    await fill(wrapper, "john", "jane@example.com");
    expect(add(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("passes up the name and the address as typed, empties both and stays open", async () => {
    const wrapper = panel();
    await fill(wrapper, " john ", " jane@example.com ");
    expect(add(wrapper).attributes("title")).toBe("Sends 'john jane@example.com': the gateway keeps the address under the name");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("add")).toEqual([["john", "jane@example.com"]]);
    expect(wrapper.find<HTMLInputElement>("#contact-name").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("#contact-address").element.value).toBe("");
    expect(wrapper.emitted("close")).toBeUndefined();
  });

  it("sends nothing while the TNC is not connected, and says why", async () => {
    const wrapper = panel(false);
    await fill(wrapper, "john", "jane@example.com");
    expect(add(wrapper).attributes("disabled")).toBeDefined();
    expect(add(wrapper).attributes("title")).toBe("The TNC is not connected");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("add")).toBeUndefined();
  });

  it("closes with Close and with Esc", async () => {
    const wrapper = panel();
    await wrapper.findAll("form button")[0]?.trigger("click");
    await wrapper.find("section").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("close")).toHaveLength(2);
  });
});
