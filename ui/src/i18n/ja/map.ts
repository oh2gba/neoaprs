// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { map as source } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Record<keyof typeof source, Message> = {
  "map.label": "局の地図",
  "map.zoom_in": "拡大",
  "map.zoom_out": "縮小",
  "map.download": "ダウンロード",
  "map.note.no_basemap": "ベースマップなし",
  "map.note.no_detail": "詳細地図なし",
  "map.note.no_engine": "地図を読み込めませんでした",
  "map.note.unreadable": "地図ファイルを読み取れません",
  "map.follow_me": "現在地を追従",
  "map.aloha": "ALOHA サークル: {km} km",

  "map.credits.hide": "クレジットを隠す",
  "map.credits.show": "地図とシンボルのクレジット",
  "map.credits.symbols": "APRSシンボル: Heikki Hannikainen, OH7LZB によるaprs.fiセット(github.com/hessu/aprs-symbols)",
  "map.credits.devices": "機器名: Hessu, OH7LZB による APRS機器識別リスト(github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "地図",
  "map.menu.copy_position": "位置 {place} をコピー",
  "map.menu.copy_locator": "ロケーター {locator} をコピー",
  "map.menu.stats": "統計",
  "map.menu.replay": "リプレイ",
  "map.replay.label": "地図のリプレイ",
  "map.replay.play": "再生",
  "map.replay.pause": "一時停止",
  "map.replay.time": "リプレイの時刻",
  "map.replay.speed": "速度",
  "map.replay.speed_n": "{n}倍",
  "map.replay.span": "期間",
  "map.replay.when_paused": "{what}：一時停止中に変更できます",
  "map.replay.close": "リプレイを閉じる",
  "map.replay.none": "過去 {span} に受信した位置はありません",
  "map.pick.tap": "地図上の場所をタップ",
  "map.pick.cancel": "キャンセル",
};
