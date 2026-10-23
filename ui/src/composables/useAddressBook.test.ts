import { beforeEach, describe, expect, it } from "vitest";
import { useAddressBook } from "@/composables/useAddressBook";

beforeEach(() => localStorage.clear());

describe("useAddressBook", () => {
  it("starts empty and remembers the newest first, in the browser", () => {
    const book = useAddressBook();
    expect(book.addresses.value).toEqual([]);
    book.remember("me");
    book.remember("jane@example.com");
    book.remember("me");
    expect(book.addresses.value).toEqual(["me", "jane@example.com"]);
    expect(JSON.parse(localStorage.getItem("NeoAPRS.emailto") ?? "null")).toEqual(["me", "jane@example.com"]);
  });

  it("is there again in the next page, and forgets one for good", () => {
    useAddressBook().remember("me");
    useAddressBook().remember("a@b.c");
    const again = useAddressBook();
    expect(again.addresses.value).toEqual(["a@b.c", "me"]);
    again.forget("a@b.c");
    expect(again.addresses.value).toEqual(["me"]);
    expect(useAddressBook().addresses.value).toEqual(["me"]);
  });

  it("starts empty from a stored text that is no list", () => {
    localStorage.setItem("NeoAPRS.emailto", "{broken");
    expect(useAddressBook().addresses.value).toEqual([]);
  });
});
