// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { setup as source } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Record<keyof typeof source, Message> = {
  "setup.title": "セットアップ",
  "setup.step.call": "コールサイン",
  "setup.step.position": "位置",
  "setup.step.symbol": "シンボル",
  "setup.step.radio": "無線機",
  "setup.step.map": "地図",
  "setup.step_label": "{n} {title}",
  "setup.done": "完了",
  "setup.close": "閉じる",
  "setup.back": "戻る",
  "setup.next": "次へ",
  "setup.saving": "保存中...",
  "setup.finish": "完了",

  "setup.call.label": "あなたのコールサイン",
  "setup.locator.label": "ロケーター",
  "setup.enter_coordinates": "座標またはロケーターを入力",
  "setup.not_locator": "ロケーターではありません",
  "setup.port_automatic": "自動",
  "setup.symbols": "シンボル",
  "setup.more": "その他...",
  "setup.symbol.house": "住宅",
  "setup.symbol.car": "自動車",
  "setup.symbol.truck": "トラック",
  "setup.symbol.van": "バン",
  "setup.symbol.motorcycle": "バイク",
  "setup.symbol.bike": "自転車",
  "setup.symbol.walker": "徒歩",
  "setup.symbol.boat": "船",
  "setup.symbol.digipeater": "デジピーター",
  "setup.symbol.weather_station": "気象局",
  "setup.symbol.portable": "ポータブル",
  "setup.symbol.antenna": "アンテナ",

  "setup.beacon_every": "ビーコンは{minutes}分ごと",
  "setup.beacon_tip_label": "ビーコンについて",
  "setup.beacon_tip1": "NeoAPRSはこの間隔で位置を送信し、ほかの局の地図にあなたが表示されます。",
  "setup.beacon_tip2": "間隔の変更やオフは「ビーコン」タブで行えます。",
};
