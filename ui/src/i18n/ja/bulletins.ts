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
  "bulletins.kind.bulletin": "掲示",
  "bulletins.kind.announcement": "お知らせ",
  "bulletins.kind.group": "グループ宛ての掲示",
  "bulletins.kinds_help_label": "種類について",
  "bulletins.kinds_help": "掲示は全員に見え、応答確認はありません。グループ掲示は、そのグループ名を受信する局向けです。",
  "bulletins.letter": "文字",
  "bulletins.number": "番号",
  "bulletins.group": "グループ",
  "bulletins.group_placeholder": "名前",
  "bulletins.text": "本文",
  "bulletins.slot_tip": "掲示板での位置です。同じ位置にもう一度投稿すると置き換わります。",
  "bulletins.group_tip": "宛先のグループです（英数字{max}文字まで）。その名前を受信する局に表示されます。",
  "bulletins.text_tip": "ブレティンの本文です。カウンターに残りの文字数が出ます。",
  "bulletins.post": "掲示",
};
