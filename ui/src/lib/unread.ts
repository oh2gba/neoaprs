// When the user can be said to have seen what came, and how the count of what was not is shown. A message counts as seen only while its conversation is open (useConversations) and the Messages tab is the
// tab on show, the panel is not folded away and the page itself is visible (a page in a background browser tab, or a minimised window, keeps counting); a message from the email gateway is seen while the Email tab is on show in the same way (useEmail); a bulletin is seen while the Bulletins tab is
// on show (useBulletins). The rest of the rules (which message is unread) are in lib/messages.ts, `conversations`.
import { t } from "@/i18n";
import type { TabId } from "@/lib/layout";

export interface PanelView {
  tab: TabId;
  collapsed: boolean;
  /** document.visibilityState is not "hidden" */
  visible: boolean;
}

/** Whether the tab is in front of the user's eyes: it is the tab on show, the panel is open and the page is visible. */
export function isViewingTab(view: PanelView, tab: TabId): boolean {
  return view.tab === tab && !view.collapsed && view.visible;
}

/** The title of the browser tab: "(2) NeoAPRS" with two messages not seen, plain "NeoAPRS" with none. */
export function titleText(unread: number): string {
  return unread > 0 ? `(${unread}) NeoAPRS` : "NeoAPRS";
}

/** What a badge says of the messages not seen: "1 message not seen yet". */
export function unreadText(unread: number): string {
  return t("unread.not_seen", { n: unread });
}

/** What the badge of a tab says: the messages not seen, or the bulletins that are new since the tab was last on show. */
export function badgeText(tab: TabId, count: number): string {
  return tab === "bulletins" ? t("unread.new_bulletins", { n: count }) : unreadText(count);
}
