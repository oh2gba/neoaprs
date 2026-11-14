// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { weather as source } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Record<keyof typeof source, Message> = {
  "weather.label": "Weer",
  "weather.temperature": "Temperatuur",
  "weather.wind": "Wind",
  "weather.wind_from": "uit {bearing}",
  "weather.gusts": "windstoten {speed}",
  "weather.humidity": "Vochtigheid",
  "weather.pressure": "Luchtdruk",
  "weather.rain_1h": "Regen 1 h",
  "weather.rain_24h": "Regen 24 h",
  "weather.rain_today": "Regen vandaag",
  "weather.light": "Zonnestraling",
  "weather.snow_24h": "Sneeuw 24 h",
  "weather.none": "Nog geen weerrapport gehoord.",
  "weather.period": "Periode van de grafieken",
  "weather.span.days": { one: "{n} dag", other: "{n} dagen" },
  "weather.loading": "Waarnemingen laden…",
  "weather.no_observations": "Geen waarnemingen in deze periode.",
  "weather.chart.wind": "Wind en windstoten",
  "weather.chart.rain": "Regen, afgelopen uur",
  "weather.chart.label": "{title}, {unit}",
};
