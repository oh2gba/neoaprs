import type { weather as en } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Readonly<Record<keyof typeof en, Message>> = {
  "weather.label": "Meteorología",
  "weather.temperature": "Temperatura",
  "weather.wind": "Viento",
  "weather.wind_from": "de {bearing}",
  "weather.gusts": "rachas {speed}",
  "weather.humidity": "Humedad",
  "weather.pressure": "Presión",
  "weather.rain_1h": "Lluvia 1 h",
  "weather.rain_24h": "Lluvia 24 h",
  "weather.rain_today": "Lluvia hoy",
  "weather.light": "Luz",
  "weather.snow_24h": "Nieve 24 h",
  "weather.none": "Aún no se ha escuchado ningún informe meteorológico.",
  "weather.period": "Período de los gráficos",
  "weather.span.days": { one: "{n} día", other: "{n} días" },
  "weather.loading": "Cargando las observaciones…",
  "weather.no_observations": "Sin observaciones en este período.",
  "weather.chart.wind": "Viento y rachas",
  "weather.chart.rain": "Lluvia, última hora",
  "weather.chart.label": "{title}, {unit}",
};
