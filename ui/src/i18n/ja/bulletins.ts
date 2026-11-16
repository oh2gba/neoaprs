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
  "bulletins.kind.bulletin": "掲示({n}時間送信)",
  "bulletins.kind.announcement": "お知らせ({n}日間送信)",
  "bulletins.kind.group": "グループ掲示(特定のグループ宛て、{n}時間送信)",
  "bulletins.letter": "文字",
  "bulletins.number": "番号",
  "bulletins.group": "グループ",
  "bulletins.group_placeholder": "名前",
  "bulletins.text": "本文",
  "bulletins.post": "掲示",
  "bulletins.replace": "置き換え",
};
