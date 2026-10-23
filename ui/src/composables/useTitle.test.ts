import { afterEach, describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useTitle } from "@/composables/useTitle";

afterEach(() => {
  document.title = "NeoAPRS";
});

describe("useTitle", () => {
  it("puts the count of messages not seen in the title of the browser tab, and takes it out", async () => {
    const unread = ref(2);
    useTitle(unread);
    expect(document.title).toBe("(2) NeoAPRS");
    unread.value = 5;
    await nextTick();
    expect(document.title).toBe("(5) NeoAPRS");
    unread.value = 0;
    await nextTick();
    expect(document.title).toBe("NeoAPRS");
  });
});
