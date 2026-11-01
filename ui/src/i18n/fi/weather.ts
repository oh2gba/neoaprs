// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { weather as source } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Record<keyof typeof source, Message> = {
  "weather.label": "Sää",
  "weather.temperature": "Lämpötila",
  "weather.wind": "Tuuli",
  "weather.wind_from": "suunnasta {bearing}",
  "weather.gusts": "puuskat {speed}",
  "weather.humidity": "Kosteus",
  "weather.pressure": "Ilmanpaine",
  "weather.rain_1h": "Sade 1 h",
  "weather.rain_24h": "Sade 24 h",
  "weather.rain_today": "Sade tänään",
  "weather.light": "Valo",
  "weather.snow_24h": "Lumi 24 h",
  "weather.none": "Säähavaintoja ei ole vielä kuultu.",
  "weather.period": "Kaavioiden jakso",
  "weather.span.days": { one: "{n} päivä", other: "{n} päivää" },
  "weather.loading": "Ladataan havaintoja…",
  "weather.no_observations": "Ei havaintoja tältä jaksolta.",
  "weather.chart.wind": "Tuuli ja puuskat",
  "weather.chart.rain": "Sade, viimeinen tunti",
  "weather.chart.label": "{title}, {unit}",
};
