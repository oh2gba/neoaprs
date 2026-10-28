import { nextTick, ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { useWhatsNew } from "@/composables/useWhatsNew";
import { compareVersions } from "@/lib/releasenotes";

beforeEach(() => localStorage.clear());

const seen = (): string | null => localStorage.getItem("NeoAPRS.seen-version");

describe("useWhatsNew", () => {
  it("on a first visit only remembers the version, when it is known", async () => {
    const version = ref("");
    const whatsNew = useWhatsNew(version);
    expect(seen()).toBeNull();
    version.value = "0.12.0";
    await nextTick();
    expect(whatsNew.updatedFrom.value).toBeNull();
    expect(seen()).toBe("0.12.0");
  });

  it("has the line after an update, from the version this browser saw before, until it is dismissed; then not again for that version", () => {
    localStorage.setItem("NeoAPRS.seen-version", "0.10.2");
    const first = useWhatsNew(ref("0.12.0"));
    expect(first.updatedFrom.value).toBe("0.10.2");
    expect(seen()).toBe("0.10.2");
    expect(useWhatsNew(ref("0.12.0")).updatedFrom.value).toBe("0.10.2");
    first.dismiss();
    expect(first.updatedFrom.value).toBeNull();
    expect(seen()).toBe("0.12.0");
    expect(useWhatsNew(ref("0.12.0")).updatedFrom.value).toBeNull();
  });

  it("opens the notes of every version since the one seen before from the line, which goes; and the notes of this version alone from Settings", () => {
    localStorage.setItem("NeoAPRS.seen-version", "0.11.0");
    const whatsNew = useWhatsNew(ref("0.12.0"));
    whatsNew.showUpdate();
    expect(whatsNew.open.value).toEqual({ version: "0.12.0", since: "0.11.0" });
    expect(whatsNew.updatedFrom.value).toBeNull();
    expect(seen()).toBe("0.12.0");
    whatsNew.close();
    expect(whatsNew.open.value).toBeNull();
    whatsNew.show();
    expect(whatsNew.open.value).toEqual({ version: "0.12.0", since: "" });
  });

  it("has no line for the same version, an older one (a copy put back) or a remembered text that is no version, and remembers the one that runs", () => {
    for (const before of ["0.12.0", "0.13.0", "nonsense"]) {
      localStorage.setItem("NeoAPRS.seen-version", before);
      expect(useWhatsNew(ref("0.12.0")).updatedFrom.value).toBeNull();
      expect(seen()).toBe("0.12.0");
    }
  });
});

describe("compareVersions", () => {
  it("compares as the daemon does: by number, a missing part as 0, a candidate before its release", () => {
    expect(compareVersions("0.10.0", "0.9.0")).toBe(1);
    expect(compareVersions("0.9.0", "0.10.0")).toBe(-1);
    expect(compareVersions("1.0", "1.0.0")).toBe(0);
    expect(compareVersions("1.0.0-rc1", "1.0.0")).toBe(-1);
    expect(compareVersions("1.0.0-rc2", "1.0.0-rc1")).toBe(1);
  });
});
