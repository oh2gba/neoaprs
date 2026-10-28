import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { DAEMON_VERSION, status } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const notesAsked = (sent: unknown[]) => sent.filter((c) => (c as { cmd: string }).cmd === "release_notes");

describe("App: what is new in the version that runs", () => {
  it("opens the window of the update in its notes form from What's new beside the version in Settings → Update check, with the notes of the version that runs", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const line = wrapper.find("#pane-settings .updateline");
    expect(line.find(".updateversion").text()).toBe(`NeoAPRS ${DAEMON_VERSION}`);
    const link = line.find("button.updatenotes");
    expect(link.text()).toBe("What's new");
    expect(line.find("button.btn").exists()).toBe(false);
    await link.trigger("click");
    const box = wrapper.find(".updatedialog");
    expect(box.find("h2").text()).toBe(`What's new in NeoAPRS ${DAEMON_VERSION}`);
    expect(notesAsked(socket.sent)).toEqual([{ cmd: "release_notes", version: DAEMON_VERSION }]);
    socket.say({ type: "release_notes", version: DAEMON_VERSION, since: "", sections: [{ version: DAEMON_VERSION, text: "- The notes." }], problem: "" });
    await flushPromises();
    expect(wrapper.find(".updatedialog-notes li").text()).toBe("The notes.");
    expect(wrapper.find(".updatedialog-go").exists()).toBe(false);
    await wrapper.find(".updatedialog button[aria-label=Close]").trigger("click");
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
  });

  it("keeps the link beside the version while an update is out, and the Update button still opens the update itself", async () => {
    const { wrapper, socket } = await open();
    socket.say(status({ update: { version: "9.0.0", url: "", message: "" } }));
    await flushPromises();
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(wrapper.find("#pane-settings .updateline button.updatenotes").exists()).toBe(true);
    await wrapper.find("#pane-settings .updateline button.btn").trigger("click");
    expect(wrapper.find(".updatedialog h2").text()).toBe("NeoAPRS 9.0.0 is available");
    expect(notesAsked(socket.sent)).toEqual([{ cmd: "release_notes", version: "9.0.0" }]);
  });

  it("says once after an update that it was, with What's new opening the notes of every version since the one this browser saw before", async () => {
    localStorage.setItem("NeoAPRS.seen-version", "1.0.0");
    const { wrapper, socket } = await open();
    const toast = wrapper.find(".toast.notice");
    expect(toast.text()).toContain(`Updated to NeoAPRS ${DAEMON_VERSION}`);
    await toast.find("button.whatsnew-open").trigger("click");
    expect(wrapper.find(".toast").exists()).toBe(false);
    expect(wrapper.find(".updatedialog h2").text()).toBe(`What's new in NeoAPRS ${DAEMON_VERSION}`);
    expect(wrapper.find(".updatedialog-installed").text()).toBe("Since NeoAPRS 1.0.0");
    expect(notesAsked(socket.sent)).toEqual([{ cmd: "release_notes", version: DAEMON_VERSION, since: "1.0.0" }]);
    expect(localStorage.getItem("NeoAPRS.seen-version")).toBe(DAEMON_VERSION);
    wrapper.unmount();
    expect((await open()).wrapper.find(".toast").exists()).toBe(false);
  });

  it("has no line on a first visit, and none again once it is dismissed", async () => {
    const first = await open();
    expect(first.wrapper.find(".toast").exists()).toBe(false);
    expect(localStorage.getItem("NeoAPRS.seen-version")).toBe(DAEMON_VERSION);
    first.wrapper.unmount();
    localStorage.setItem("NeoAPRS.seen-version", "1.2.2");
    const { wrapper } = await open();
    await wrapper.find(".toast.notice button[aria-label=Dismiss]").trigger("click");
    expect(wrapper.find(".toast").exists()).toBe(false);
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
    wrapper.unmount();
    expect((await open()).wrapper.find(".toast").exists()).toBe(false);
  });
});
