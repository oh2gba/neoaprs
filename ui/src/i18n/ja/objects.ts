// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { objects as source } from "@/i18n/en/objects";
import type { Message } from "@/i18n/message";

export const objects: Record<keyof typeof source, Message> = {
  "schedule.sent": { "=0": "未送信", other: "{n}回送信" },
  "schedule.ended": { other: "{n}回送信、終了" },
  "schedule.next": { "=0": "未送信、次回 {when}", other: "{n}回送信、次回 {when}" },
  "schedule.waiting": { "=0": "未送信、待機中", other: "{n}回送信、待機中" },
  "schedule.killing": { "=0": "キル中、未送信", other: "キル中、{n}回送信" },
  "schedule.on_request": "要求があったときだけ送信",

  "objects.new": "新規",
  "objects.none": "オブジェクトはありません。",
  "objects.edit": "編集",
  "objects.edit_label": "{name}を編集",
  "objects.delete_title": "削除(電波でキル)",
  "objects.delete_label": { select: "kind", object: "オブジェクト{name}を削除", item: "アイテム{name}を削除", other: "オブジェクト{name}を削除" },
  "objects.kind_word": { select: "kind", object: "オブジェクト", item: "アイテム", other: "オブジェクト" },
  "objects.in_group": "QRUグループ {group}",

  "objects.form.new": "新規オブジェクト",
  "objects.field.name": "名前",
  "objects.field.lat": "緯度",
  "objects.field.lon": "経度",
  "objects.field.comment": "コメント",
  "objects.field.course": "進行方向",
  "objects.field.speed": "速度",
  "objects.field.moving": "移動中",
  "objects.field.path": "パス",
  "objects.field.qru": "QRUグループ",
  "objects.field.on_request": "要求があったときだけ送る",
  "objects.unit.deg": "度",
  "objects.form.cancel": "キャンセル",
  "objects.form.save": "保存",

  "objects.problem.name_chars": "両端に空白不可、! _ | ~ は使えません",
  "objects.problem.at_most": "最大{max}文字",
  "objects.problem.item_name": "アイテムは{min}〜{max}文字です",
  "objects.problem.not_number": "数値ではありません",
  "objects.problem.between": "-{max}〜{max}の範囲",
  "objects.problem.comment_chars": "表示可能なASCII、| と ~ は不可",
  "objects.problem.course": "0〜{max}度",
  "objects.problem.speed": "0〜{max} km/h",
  "objects.problem.qru_group": "英数字{max}文字まで。INFO と NEXT は不可",
};
