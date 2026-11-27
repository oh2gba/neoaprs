// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "HFテストについて",
  "skeds.about1":
    "HFでAPRSを試している局のための掲示板です。いつどの周波数で運用するかを知らせると、ほかの局が一緒にテストできます。",
  "skeds.about2": "掲示板は公開で、neo.oh2gba.eu にあります。無線では送信されません。",

  "skeds.empty": "予定のテストはありません。",
  "skeds.past_title": "過去のテスト",
  "skeds.past_empty": "過去のテストはありません。",
  "skeds.when": "{from}〜{to} UTC",
  "skeds.local": "現地時間: {from}〜{to}",
  "skeds.ours": "自局",
  "skeds.join": "参加",
  "skeds.join_title": "同じ時間・同じ周波数で自局のテストを予定",
  "skeds.join_label": "{calls}のテストに参加、{when}",
  "skeds.delete_title": "削除(掲示板から外す)",
  "skeds.delete_label": "自局のテストを削除、{when}",

  "skeds.post_label": "テストの予定",
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
