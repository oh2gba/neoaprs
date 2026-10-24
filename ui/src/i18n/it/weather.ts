import type { weather as en } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Readonly<Record<keyof typeof en, Message>> = {
  "weather.label": "Meteo",
  "weather.temperature": "Temperatura",
  "weather.wind": "Vento",
  "weather.wind_from": "da {bearing}",
  "weather.gusts": "raffiche {speed}",
  "weather.humidity": "Umidità",
  "weather.pressure": "Pressione",
  "weather.rain_1h": "Pioggia 1 h",
  "weather.rain_24h": "Pioggia 24 h",
  "weather.rain_today": "Pioggia oggi",
  "weather.light": "Luce",
  "weather.snow_24h": "Neve 24 h",
  "weather.none": "Ancora nessun rapporto meteo ricevuto.",
  "weather.period": "Periodo dei grafici",
  "weather.span.days": { one: "{n} giorno", other: "{n} giorni" },
  "weather.loading": "Caricamento delle osservazioni…",
  "weather.no_observations": "Nessuna osservazione in questo periodo.",
  "weather.chart.wind": "Vento e raffiche",
  "weather.chart.rain": "Pioggia, ultima ora",
  "weather.chart.label": "{title}, {unit}",
};
