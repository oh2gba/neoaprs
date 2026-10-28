import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import UpdateDialog from "@/components/UpdateDialog.vue";
import type { ReleaseNotesMessage, UpdateState } from "@/protocol/protocol";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { status } from "@/test/fixtures";

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

const job: UpdateState = { supported: true, state: "idle", version: "", percent: null, downloaded: 0, total: null, problem: "", detail: "" };
const notesOf = (since: string, versions: string[]): ReleaseNotesMessage => ({
  type: "release_notes",
  version: "0.12.0",
  since,
  sections: versions.map((version) => ({ version, text: `- In ${version}.` })),
  problem: "",
});
const dialog = (given: Given = {}, since?: string) => {
  const daemon = fakeDaemon({ install: { kind: "appimage", appimage: "", service: false, arch: "" }, version: "0.12.0", selfUpdate: job, ...given });
  const wrapper = mount(UpdateDialog, { props: { version: "0.12.0", notesOnly: true, since }, global: withDaemon(daemon), attachTo: document.body });
  return { wrapper, daemon };
};

describe("UpdateDialog, the notes form", () => {
  it("is the same modal window headed What's new in the version that runs, asking the daemon for that version's notes alone: no note of the version page, no update, no steps", async () => {
    const { wrapper, daemon } = dialog({ status: status({ update: { version: "0.13.0", url: "", message: "Fixes the map download" } }) });
    expect(wrapper.find("[role=dialog]").attributes("aria-modal")).toBe("true");
    expect(wrapper.find("#updatedialog-title").text()).toBe("What's new in NeoAPRS 0.12.0");
    expect(wrapper.find(".updatedialog-installed").exists()).toBe(false);
    expect(daemon.send).toHaveBeenCalledExactlyOnceWith({ cmd: "release_notes", version: "0.12.0" });
    expect(wrapper.find(".updatedialog-news [role=status]").text()).toBe("Fetching what is new…");
    expect(wrapper.text()).not.toContain("Fixes the map download");
    expect(wrapper.find(".updatedialog-news h3").exists()).toBe(false);
    for (const gone of [".updatedialog-go", ".updatedialog-now", ".updatedialog-hand", ".updatedialog-foot"]) expect(wrapper.find(gone).exists()).toBe(false);
    await vi.waitFor(() => expect(document.activeElement).toBe(wrapper.find("[role=dialog]").element));
  });

  it("shows the notes of the version that runs when they come, and not an answer to another question", () => {
    const update = dialog({ releaseNotes: { ...notesOf("", ["0.12.0", "0.11.1"]), version: "0.13.0" } });
    expect(update.wrapper.find(".updatedialog-notes").exists()).toBe(false);
    update.wrapper.unmount();
    const ranged = dialog({ releaseNotes: notesOf("0.11.0", ["0.12.0"]) });
    expect(ranged.wrapper.find(".updatedialog-notes").exists()).toBe(false);
    ranged.wrapper.unmount();
    const { wrapper } = dialog({ releaseNotes: notesOf("", ["0.12.0"]) });
    expect(wrapper.find(".updatedialog-notes li").text()).toBe("In 0.12.0.");
    expect(wrapper.find(".updatedialog-notes h4").exists()).toBe(false);
  });

  it("with `since`, says so under the title, asks for every version after it and heads each one", () => {
    const { wrapper, daemon } = dialog({ releaseNotes: notesOf("0.10.2", ["0.12.0", "0.11.0"]) }, "0.10.2");
    expect(wrapper.find(".updatedialog-installed").text()).toBe("Since NeoAPRS 0.10.2");
    expect(daemon.send).not.toHaveBeenCalled();
    expect(wrapper.findAll(".updatedialog-notes h4").map((h) => h.text())).toEqual(["0.12.0", "0.11.0"]);
    wrapper.unmount();
    expect(dialog({}, "0.10.2").daemon.send).toHaveBeenCalledWith({ cmd: "release_notes", version: "0.12.0", since: "0.10.2" });
  });

  it("offers the release page of the version that runs when the notes could not be fetched (offline)", () => {
    const { wrapper } = dialog({ releaseNotes: { ...notesOf("", []), problem: "the release notes could not be fetched" } });
    expect(wrapper.find(".updatedialog-news .muted").text()).toBe("What is new could not be fetched; the release page has it:");
    expect(wrapper.find(".updatedialog-news a.btn").attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.12.0");
  });

  it("closes with Escape and the cross", async () => {
    const { wrapper } = dialog();
    await wrapper.find("button[aria-label=Close]").trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("close")).toHaveLength(2);
  });
});
