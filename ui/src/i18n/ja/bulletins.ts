// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { bulletins as source } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Record<keyof typeof source, Message> = {
  "bulletins.section.announcement": "お知らせ",
  "bulletins.section.bulletin": "掲示",
  "bulletins.section.group": "グループ宛て",
  "bulletins.section.nws": "気象機関",

  "bulletins.empty": "掲示板は空です。",
  "bulletins.about_label": "掲示について",
  "bulletins.about1": "掲示は全員宛てのメッセージで、すべての局の掲示板に表示されます。",
  "bulletins.about2": "ネットの時間、イベント、警告などに使います。",
  "bulletins.delete_title": "削除(送信を停止)",
  "bulletins.delete_own": "自局の掲示 {slot} を削除",
  "bulletins.delete": "{sender}の掲示 {slot} を削除",
  "bulletins.to": "宛先",
  "bulletins.ours": "自局",
  "bulletins.posted": "{time}に掲示",
  "bulletins.heard_title": "初回受信 {first}、最終受信 {last}",
  "bulletins.heard": { other: "{n}回受信、最終は{span}前" },

  "bulletins.post_label": "掲示を出す",
  "bulletins.kind": "種類",
  "bulletins.kind_name.bulletin": "掲示",
  "bulletins.kind_name.announcement": "お知らせ",
  "bulletins.kind_name.group": "グループ掲示",
  "bulletins.sent_for": "送信期間",
  "bulletins.group": "グループ",
  "bulletins.group_placeholder": "名前",
  "bulletins.text": "本文",
  "bulletins.tip.hours": { other: "{n}時間" },
  "bulletins.tip.days": { other: "{n}日間" },
  "bulletins.tip.kinds1":
    "掲示とお知らせは、受信したすべての局が表示します。掲示はいま大事なこと、お知らせは何日も変わらないことに使います。",
  "bulletins.tip.kinds2":
    "グループ掲示は1つのグループ向けで、運用者が他のグループを選んでいない限り、すべての局が表示します。",
  "bulletins.tip.sent_for": "最初のパケットから数えて、掲示を繰り返し送る期間です。",
  "bulletins.tip.group1":
    "名前は宛先の一部で(BLN3HAMS のように)、すべての局が掲示を受信して表示します。運用者が他のグループを選んでいる場合は表示されません。",
  "bulletins.tip.group2": "NeoAPRS は受信したすべてのグループの掲示を、グループ宛てに表示します。",
  "bulletins.tip.text1": "最大{max}文字、印字できる文字で、{forbidden}は使えません。",
  "bulletins.tip.text_repeat": "無線の1パケットで送信され、「送信期間」で選んだ時間のあいだ繰り返されます。",
  "bulletins.post": "掲示",
};
