import { describe, expect, it } from "vitest";
import { TAB_IDS } from "@/lib/layout";
import { badgeText, foldedText, isViewingTab, titleText, unreadText, type PanelView } from "@/lib/unread";

const view = (extra: Partial<PanelView> = {}): PanelView => ({ tab: "messages", collapsed: false, visible: true, ...extra });

describe("isViewingTab", () => {
  it("is true only with the tab on show, the panel open and the page visible", () => {
    expect(isViewingTab(view(), "messages")).toBe(true);
    expect(isViewingTab(view({ collapsed: true }), "messages")).toBe(false);
    expect(isViewingTab(view({ visible: false }), "messages")).toBe(false);
    expect(isViewingTab(view({ collapsed: true, visible: false }), "messages")).toBe(false);
  });

  it("is false for every other tab", () => {
    for (const tab of TAB_IDS.filter((t) => t !== "messages")) expect(isViewingTab(view({ tab }), "messages"), tab).toBe(false);
    expect(isViewingTab(view({ tab: "bulletins" }), "bulletins")).toBe(true);
  });

  it("is true for the Email tab only while it is on show, the panel open and the page visible", () => {
    expect(isViewingTab(view({ tab: "email" }), "email")).toBe(true);
    expect(isViewingTab(view({ tab: "email", collapsed: true }), "email")).toBe(false);
    expect(isViewingTab(view({ tab: "email", visible: false }), "email")).toBe(false);
    expect(isViewingTab(view({ tab: "messages" }), "email")).toBe(false);
    expect(isViewingTab(view({ tab: "email" }), "messages")).toBe(false);
  });
});

describe("titleText", () => {
  it("has the count in front when there are messages not seen, and is plain without", () => {
    expect(titleText(2)).toBe("(2) NeoAPRS");
    expect(titleText(1)).toBe("(1) NeoAPRS");
    expect(titleText(120)).toBe("(120) NeoAPRS");
    expect(titleText(0)).toBe("NeoAPRS");
  });
});

describe("unreadText", () => {
  it("counts in words", () => {
    expect(unreadText(1)).toBe("1 message not seen yet");
    expect(unreadText(3)).toBe("3 messages not seen yet");
  });
});

describe("badgeText and foldedText", () => {
  it("say what a badge counts: messages not seen, bulletins that are new", () => {
    expect(badgeText("messages", 2)).toBe("2 messages not seen yet");
    expect(badgeText("email", 2)).toBe("2 messages not seen yet");
    expect(badgeText("bulletins", 1)).toBe("1 new bulletin");
    expect(badgeText("bulletins", 3)).toBe("3 new bulletins");
  });

  it("put the badges of the tabs together and leave out a tab with none", () => {
    expect(foldedText({ messages: 3, bulletins: 1 })).toBe("3 messages not seen yet, 1 new bulletin");
    expect(foldedText({ messages: 0, bulletins: 2 })).toBe("2 new bulletins");
    expect(foldedText({})).toBe("");
  });
});
