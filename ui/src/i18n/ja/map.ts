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
  "map.follow_me": "自分を追う",
  "map.aloha": "ALOHA サークル: {km} km",

  "map.credits.hide": "クレジットを隠す",
  "map.credits.show": "地図とシンボルのクレジット",
  "map.credits.symbols": "APRSシンボル: Heikki Hannikainen, OH7LZB によるaprs.fiセット(github.com/hessu/aprs-symbols)",
  "map.credits.devices": "機器名: Hessu, OH7LZB による APRS機器識別リスト(github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.pick.tap": "地図上の場所をタップ",
  "map.pick.cancel": "キャンセル",
};
