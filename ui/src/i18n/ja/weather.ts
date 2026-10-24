// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { weather as source } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Record<keyof typeof source, Message> = {
  "weather.label": "気象",
  "weather.temperature": "気温",
  "weather.wind": "風",
  "weather.wind_from": "{bearing}から",
  "weather.gusts": "突風 {speed}",
  "weather.humidity": "湿度",
  "weather.pressure": "気圧",
  "weather.rain_1h": "雨量 1時間",
  "weather.rain_24h": "雨量 24時間",
  "weather.rain_today": "雨量 今日",
  "weather.light": "日射",
  "weather.snow_24h": "降雪 24時間",
  "weather.none": "気象データはまだ受信していません。",
  "weather.period": "グラフの期間",
  "weather.span.days": { other: "{n}日" },
  "weather.loading": "観測データを読み込み中…",
  "weather.no_observations": "この期間の観測データはありません。",
  "weather.chart.wind": "風と突風",
  "weather.chart.rain": "雨量(直近1時間)",
  "weather.chart.label": "{title}、{unit}",
};
