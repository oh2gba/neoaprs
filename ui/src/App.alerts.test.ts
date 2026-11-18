import "@/test/mockmap";
import { describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeSocket } from "@/test/fakesocket";
import { APP_WINDOWS, FakeAudioContext, FakeNotification, openedAt, openedInApp, setSeen, stubBrowser } from "@/test/fakealert";
import { MODE_KEY } from "@/lib/alertmode";
import { clockText } from "@/lib/format";
import { hello, incoming, message } from "@/test/fixtures";
import { messages, open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the alert of this browser", () => {
  const patch = (socket: FakeSocket, rev: number, key: string, row: object) =>
    socket.say({ type: "patch", topic: "messages", rev, ops: [{ op: "set", key, value: row }] });

  it("has one Notifications group in the Settings tab: the daemon's own alert, then the choice of this browser with its tests once it is not off", async () => {
    stubBrowser();
    const { wrapper } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const groups = wrapper.findAll("#pane-settings fieldset").filter((g) => g.find("legend").text() === "Notifications");
    expect(groups).toHaveLength(1);
    const boxes = groups[0]?.findAll("fieldset.subbox") ?? [];
    expect(boxes.map((b) => b.find("legend").text().replace(/ i$/, ""))).toEqual(["On the NeoAPRS computer", "In this browser"]);
    expect(boxes[0]?.findAll("label").map((l) => l.text())).toEqual(["Alert", "Command"]);
    expect(boxes[1]?.findAll("label").map((l) => l.text())).toEqual(["Notify me"]); // (the loopback starts unticked: no tests)
    expect(boxes[0]?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test"]);
    expect(boxes[1]?.findAll("button:not(.info-toggle)")).toHaveLength(0);
    await boxes[1]?.find("#alert-mode").setValue(true);
    await flushPromises();
    expect(boxes[1]?.findAll("label").map((l) => l.text())).toEqual(["Notify me", "Sound", "Notification"]);
    expect(boxes[1]?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test sound", "Test notification"]);
    expect(groups[0]?.findAll("h3")).toHaveLength(0);
  });

  /** The Notifications group of the Settings tab in the app's window of `agent`. */
  async function appGroup(agent: string) {
    localStorage.clear();
    stubBrowser();
    openedInApp(agent);
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const group = wrapper.findAll("#pane-settings fieldset").find((g) => g.find("legend").text() === "Notifications");
    return { wrapper, socket, group, boxes: group?.findAll("fieldset.subbox") ?? [] };
  }

  it("in the desktop app's own window on Linux and Windows has one box, On this computer, and no box for the window", async () => {
    for (const name of ["Linux, Qt", "Windows, WebView2", "Linux, WebKitGTK"] as const) {
      const { wrapper, socket, group, boxes } = await appGroup(APP_WINDOWS[name]);
      expect(
        boxes.map((b) => b.find("legend").text().replace(/ i$/, "")),
        name,
      ).toEqual(["On this computer"]);
      expect(boxes[0]?.find("legend").attributes("title"), name).toBe("NeoAPRS's own alert: the command run on this computer");
      expect(
        boxes[0]?.findAll("label").map((l) => l.text()),
        name,
      ).toEqual(["Alert", "Command"]);
      await boxes[0]?.find("legend .info-toggle").trigger("click");
      expect(
        boxes[0]?.findAll(".info-text .info-line").map((l) => l.text()),
        name,
      ).toEqual(["The alert of this computer: it runs the Command for each new message, by default a sound and a notification."]);
      expect(group?.text(), name).not.toMatch(/browser|server|window|pop-up/i);
      expect(FakeNotification.asked, name).toBe(0);
      socket.hangUp();
      wrapper.unmount();
    }
  });

  it("makes no sound in the app's window for a message to us, whatever the window kept earlier: the daemon's alert tells", async () => {
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    stubBrowser();
    openedInApp(APP_WINDOWS["Windows, WebView2"]);
    const { socket } = await open();
    patch(socket, 1, "4", incoming(4, "OH2DPN"));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(0);
  });

  it("in the desktop app's own window on a Mac names this computer and this window, and offers the window's sound with no notification", async () => {
    for (const name of ["macOS, Qt", "macOS, WKWebView"] as const) {
      const { wrapper, socket, group, boxes } = await appGroup(APP_WINDOWS[name]);
      expect(
        boxes.map((b) => b.find("legend").text().replace(/ i$/, "")),
        name,
      ).toEqual(["On this computer", "In this window"]);
      await boxes[1]?.find("#alert-mode").setValue(true);
      await flushPromises();
      expect(
        boxes[1]?.findAll("label").map((l) => l.text()),
        name,
      ).toEqual(["Notify me", "Sound"]);
      expect(
        boxes[1]?.findAll("button:not(.info-toggle)").map((b) => b.text()),
        name,
      ).toEqual(["Test sound"]);
      await boxes[0]?.find("legend .info-toggle").trigger("click");
      expect(
        boxes[0]?.findAll(".info-text .info-line").map((l) => l.text()),
        name,
      ).toEqual([
        "The alert of this computer: it runs the Command for each new message, by default a sound and a notification.",
        "The next group is this window. Use one of the two, or both to be told twice.",
      ]);
      expect(group?.text(), name).not.toMatch(/browser|server|pop-up/i);
      expect(FakeNotification.asked, name).toBe(0);
      socket.hangUp();
      wrapper.unmount();
    }
  });

  it("is off on the loopback: a message to us makes no sound there", async () => {
    stubBrowser();
    const { socket } = await open();
    patch(socket, 1, "4", incoming(4, "OH2DPN"));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(0);
    expect(FakeNotification.shown).toEqual([]);
  });

  it("chimes once for a message to us that arrives after the page loaded, flashes the tab, and not again on a reconnect", async () => {
    stubBrowser({ secure: false });
    openedAt("192.168.1.20");
    setSeen(false);
    const { socket } = await open();
    window.dispatchEvent(new Event("pointerdown"));
    await flushPromises();
    patch(socket, 1, "4", incoming(4, "OH2DPN", { text: "Moi!" }));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    expect(document.title).toBe("✉ OH2DPN");
    patch(socket, 2, "5", incoming(5, "OH2RDG", { state: "overheard", to_call: "OH2XYZ" }));
    patch(socket, 3, "6", message(6, { to_call: "OH2RDG" }));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    socket.hangUp();
    vi.useFakeTimers();
    vi.advanceTimersByTime(1000);
    vi.useRealTimers();
    const again = FakeSocket.last();
    again.say(hello());
    again.say({ type: "state", topic: "messages", rev: 0, value: { ...messages, "4": incoming(4, "OH2DPN", { text: "Moi!" }) } });
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
  });

  it("alerts for an alert set on a station as for a message, with a notification of its own and the toast with the time, and counts no message", async () => {
    stubBrowser();
    FakeNotification.permission = "granted";
    openedAt("192.168.1.20");
    const { wrapper, socket } = await open();
    const at = "2026-10-21T12:03:00Z";
    socket.say({ type: "station_alert", call: "OH2XYZ", kind: "on_air", text: "OH2XYZ is on the air", at, km: null });
    socket.say({ type: "station_alert", call: "OH2XYZ", kind: "direct", text: "OH2XYZ is heard direct", at, km: null });
    await flushPromises();
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([
      ["APRS alert: OH2XYZ", "OH2XYZ is on the air"],
      ["APRS alert: OH2XYZ", "OH2XYZ is heard direct"],
    ]);
    expect(wrapper.find(".toast.notice").text()).toBe(`${clockText(at).slice(0, 5)} OH2XYZ is heard direct`);
    expect(document.title).not.toContain("✉");
  });

  it("shows a notification that opens the conversation when it is clicked", async () => {
    stubBrowser();
    FakeNotification.permission = "granted";
    openedAt("192.168.1.20");
    localStorage.setItem(MODE_KEY, "both"); // (the choice this test is about, stated, not left to the address's default)
    vi.spyOn(window, "focus").mockImplementation(() => undefined);
    const { wrapper, socket } = await open();
    patch(socket, 1, "4", incoming(4, "OH2DPN", { text: "Moi!" }));
    await vi.waitFor(() => expect(FakeNotification.shown.map((n) => n.title)).toEqual(["APRS message from OH2DPN"])); // (under the load of the whole suite the notification comes a moment after one flush)
    FakeNotification.shown[0]?.onclick?.();
    await vi.waitFor(() => expect(tabButton(wrapper, "Messages")?.attributes("aria-selected")).toBe("true"));
    expect(wrapper.find("#pane-messages").text()).toContain("Moi!");
  });
});
