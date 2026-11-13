// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "スケジュールについて",
  "skeds.about1": "スケジュールは、いつどの周波数で運用するかを知らせるもので、ほかの局がそこで落ち合えます。",
  "skeds.about2": "掲示板は公開で、neo.oh2gba.eu にあります。無線では送信されません。",

  "skeds.empty": "予定のスケジュールはありません。",
  "skeds.when": "{from}〜{to} UTC",
  "skeds.local": "現地時間: {from}〜{to}",
  "skeds.ours": "自局",
  "skeds.join": "参加",
  "skeds.join_title": "同じ時間・同じ周波数で自局のスケジュールを投稿",
  "skeds.join_label": "{calls}のスケジュールに参加、{when}",
  "skeds.delete_title": "削除(掲示板から外す)",
  "skeds.delete_label": "自局のスケジュールを削除、{when}",

  "skeds.post_label": "スケジュールを投稿",
  "skeds.day": "日",
  "skeds.time": "時刻 (UTC)",
  "skeds.from": "開始",
  "skeds.to": "終了",
  "skeds.until": "〜",
  "skeds.frequency": "周波数",
  "skeds.frequency_other": "その他",
  "skeds.dial": "ダイヤル",
  "skeds.note": "備考",
  "skeds.post": "neo.oh2gba.eu に投稿",
} as const;
