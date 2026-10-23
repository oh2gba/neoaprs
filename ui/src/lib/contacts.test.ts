import { describe, expect, it } from "vitest";
import { contactsOf } from "@/lib/contacts";
import { incoming, message } from "@/test/fixtures";

type Extra = Parameters<typeof message>[1];
const sent = (id: number, text: string, extra: Extra = {}) => message(id, { to_call: "EMAIL-2", text, state: "acked", attempts: 1, ...extra });
const names = (rows: ReturnType<typeof sent>[]) => contactsOf(rows).map((c) => c.name);

describe("contactsOf: what registers a contact", () => {
  it("is none without messages, and none from mail, from a get, or from a list request", () => {
    expect(contactsOf([])).toEqual([]);
    expect(contactsOf([sent(1, "jane@example.com Hello"), sent(2, "me Hi"), sent(3, "get"), sent(4, "me L")])).toEqual([]);
  });

  it("is a name and an address that was sent: `me jane@example.com`", () => {
    expect(contactsOf([sent(1, "me jane@example.com")])).toEqual([{ name: "me", address: "jane@example.com", state: "confirmed" }]);
  });

  it("is not made by what the gateway sent, even if it looks like a registration", () => {
    expect(contactsOf([incoming(1, "EMAIL-2", { text: "me jane@example.com" })])).toEqual([]);
  });

  it("is not made by a mail to an address whose text is an address, or by a name that is not letters and digits", () => {
    expect(contactsOf([sent(1, "jane@example.com bob@example.com"), sent(2, "my-friend bob@example.com")])).toEqual([]);
  });

  it("keeps the blanks round it out of the name and the address", () => {
    expect(contactsOf([sent(1, "  me   jane@example.com  ")])).toMatchObject([{ name: "me", address: "jane@example.com" }]);
  });
});

describe("contactsOf: changes", () => {
  it("takes the new address when a name is registered again", () => {
    expect(contactsOf([sent(1, "me jane@example.com"), sent(2, "me jane@work.example")])).toEqual([
      { name: "me", address: "jane@work.example", state: "confirmed" },
    ]);
  });

  it("goes by the id, not by the order the rows come in", () => {
    expect(contactsOf([sent(2, "me jane@work.example"), sent(1, "me jane@example.com")])).toMatchObject([{ address: "jane@work.example" }]);
  });

  it("removes a contact with `name R`, and it can be added again", () => {
    expect(names([sent(1, "me jane@example.com"), sent(2, "me R")])).toEqual([]);
    expect(contactsOf([sent(1, "me jane@example.com"), sent(2, "me R"), sent(3, "me bob@example.org")])).toEqual([
      { name: "me", address: "bob@example.org", state: "confirmed" },
    ]);
  });

  it("a removal with an older id than the registration does not remove it", () => {
    expect(names([sent(1, "me R"), sent(2, "me jane@example.com")])).toEqual(["me"]);
  });

  it("removes only the one named, and a removal of a name never added changes nothing", () => {
    expect(names([sent(1, "me jane@example.com"), sent(2, "bob bob@example.org"), sent(3, "bob R"), sent(4, "nobody R")])).toEqual(["me"]);
  });

  it("takes names in any letters as one: the case of the last registration is shown, and R removes whatever the case", () => {
    expect(contactsOf([sent(1, "Me jane@example.com"), sent(2, "ME jane@work.example")])).toEqual([
      { name: "ME", address: "jane@work.example", state: "confirmed" },
    ]);
    expect(names([sent(1, "Me jane@example.com"), sent(2, "ME R")])).toEqual([]);
    expect(names([sent(1, "me jane@example.com"), sent(2, "Me R")])).toEqual([]);
  });

  it("lists them in the order of their names, whatever the case", () => {
    expect(names([sent(1, "zoe z@example.com"), sent(2, "Bob b@example.com"), sent(3, "anna a@example.com")])).toEqual(["anna", "Bob", "zoe"]);
  });
});

describe("contactsOf: what became of the message", () => {
  it("ignores a registration the gateway rejected, and keeps the contact it would have changed", () => {
    expect(names([sent(1, "me jane@example.com", { state: "rejected" })])).toEqual([]);
    expect(contactsOf([sent(1, "me jane@example.com"), sent(2, "me bob@example.org", { state: "rejected" })])).toMatchObject([{ address: "jane@example.com" }]);
  });

  it("ignores a removal that was rejected: the contact stays", () => {
    expect(names([sent(1, "me jane@example.com"), sent(2, "me R", { state: "rejected" })])).toEqual(["me"]);
  });

  it("ignores a message that was cancelled", () => {
    expect(names([sent(1, "me jane@example.com", { state: "cancelled", attempts: 0 })])).toEqual([]);
    expect(names([sent(1, "me jane@example.com"), sent(2, "me R", { state: "cancelled", attempts: 0 })])).toEqual(["me"]);
  });

  it("counts one still being sent, and says it is", () => {
    expect(contactsOf([sent(1, "me jane@example.com", { state: "sending", attempts: 1 })])).toEqual([
      { name: "me", address: "jane@example.com", state: "sending" },
    ]);
    expect(names([sent(1, "me jane@example.com"), sent(2, "me R", { state: "sending", attempts: 0 })])).toEqual([]);
  });

  it("counts one that was not confirmed (unconfirmed, or failed in an old row), and says it was not", () => {
    for (const state of ["unconfirmed", "failed"] as const) {
      expect(contactsOf([sent(1, "me jane@example.com", { state, attempts: 2 })])).toEqual([{ name: "me", address: "jane@example.com", state: "unconfirmed" }]);
    }
    expect(names([sent(1, "me jane@example.com"), sent(2, "me R", { state: "unconfirmed", attempts: 2 })])).toEqual([]);
  });

  it("takes the state of the registration in force: a later one that was not acked leaves the contact not confirmed, a late ack makes it confirmed", () => {
    const first = sent(1, "me jane@example.com");
    expect(contactsOf([first, sent(2, "me bob@example.org", { state: "unconfirmed", attempts: 2 })])).toEqual([
      { name: "me", address: "bob@example.org", state: "unconfirmed" },
    ]);
    expect(contactsOf([sent(1, "me jane@example.com", { state: "unconfirmed", attempts: 2 })])[0]?.state).toBe("unconfirmed");
    expect(contactsOf([sent(1, "me jane@example.com", { state: "acked", attempts: 2 })])[0]?.state).toBe("confirmed");
  });
});
