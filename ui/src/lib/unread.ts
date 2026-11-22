// When the user has seen what came, and how the count of what was not is shown. A message is seen
// only while its conversation is open (useConversations), the Messages tab is on show, the panel is
// on screen (not folded, and on a phone not behind the map) and the page is visible. An email
// gateway message is seen while the Email tab is on show (useEmail), a bulletin while the Bulletins
// tab is (useBulletins), a sked while the Skeds tab is (useSkeds). Which message is unread is
// decided in lib/messages.ts `conversations`.
import { t } from "@/i18n";
import type { TabId } from "@/lib/layout";

export interface PanelView {
  tab: TabId;
  /** The panel is on screen: unfolded, and on a phone the panel's turn (usePanel). */
  onScreen: boolean;
  /** document.visibilityState is not "hidden" */
  visible: boolean;
}

/** Whether the tab is in front of the user: on show, on screen and the page visible. */
export function isViewingTab(view: PanelView, tab: TabId): boolean {
  return view.tab === tab && view.onScreen && view.visible;
}

/** The browser tab title: "(2) NeoAPRS" with two unseen messages, else "NeoAPRS". */
export function titleText(unread: number): string {
  return unread > 0 ? `(${unread}) NeoAPRS` : "NeoAPRS";
}

/** A badge's text for unseen messages: "1 message not seen yet". */
export function unreadText(unread: number): string {
  return t("unread.not_seen", { n: unread });
}

/** A tab's badge text: unseen messages, new bulletins since last shown, or unseen skeds. */
export function badgeText(tab: TabId, count: number): string {
  return tab === "bulletins"
    ? t("unread.new_bulletins", { n: count })
    : tab === "skeds"
      ? t("unread.new_skeds", { n: count })
      : unreadText(count);
}
