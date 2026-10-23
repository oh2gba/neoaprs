import { describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import type { Catalogue } from "@/i18n/catalogue";
import { LOCALES, type LocaleInfo } from "@/i18n/locales";
import {
  agoWords,
  ageSeconds,
  ageText,
  bearingText,
  bytesText,
  clockText,
  compassPoint,
  dateTimeText,
  distanceText,
  pathText,
  positionText,
  processText,
  processTextShort,
  silentText,
  speedText,
  untilText,
} from "@/lib/format";
import { NOW, ago } from "@/test/fixtures";

describe("untilText", () => {
  const later = (s: number): string => new Date(NOW + s * 1000).toISOString();
  it("counts seconds, minutes, hours and days ahead, rounding up", () => {
    expect(untilText(later(12), NOW)).toBe("in 12 s");
    expect(untilText(later(61), NOW)).toBe("in 2 min");
    expect(untilText(later(3600 + 1), NOW)).toBe("in 2 h");
    expect(untilText(later(2 * 86400), NOW)).toBe("in 2 d");
  });
  it("is now for a time that has come, and a dash for none", () => {
    expect(untilText(later(0), NOW)).toBe("now");
    expect(untilText(later(-30), NOW)).toBe("now");
    expect(untilText(null, NOW)).toBe("-");
  });
});

describe("silentText", () => {
  it("says since when in the viewer's time and how long ago", () => {
    expect(silentText(ago(5 * 3600 + 100), NOW)).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)$/);
    expect(silentText(ago(17 * 60), NOW)).toMatch(/\(17 min\)$/);
  });
  it("says only that nothing was heard when the time is not known", () => {
    expect(silentText(null, NOW)).toBe("nothing heard");
  });
});

describe("ageText", () => {
  it("counts seconds, minutes, hours and days", () => {
    expect(ageText(ago(12), NOW)).toBe("12 s");
    expect(ageText(ago(3 * 60 + 20), NOW)).toBe("3 min");
    expect(ageText(ago(5 * 3600 + 100), NOW)).toBe("5 h");
    expect(ageText(ago(2 * 86400 + 5), NOW)).toBe("2 d");
  });
  it("is a dash for no time and zero for a time in the future", () => {
    expect(ageText(null, NOW)).toBe("-");
    expect(ageText("not a time", NOW)).toBe("-");
    expect(ageText(ago(-30), NOW)).toBe("0 s");
  });
  it("has the age in seconds, infinite for none", () => {
    expect(ageSeconds(ago(90), NOW)).toBe(90);
    expect(ageSeconds(null, NOW)).toBe(Infinity);
  });
});

describe("numbers", () => {
  it("writes a distance with a decimal under ten", () => {
    expect(distanceText(0.74)).toBe("0.7");
    expect(distanceText(25.4)).toBe("25");
    expect(distanceText(null)).toBe("-");
  });
  it("names the compass point of a bearing", () => {
    expect(compassPoint(0)).toBe("N");
    expect(compassPoint(258)).toBe("WSW");
    expect(compassPoint(259)).toBe("W");
    expect(compassPoint(359)).toBe("N");
    expect(compassPoint(-90)).toBe("W");
    expect(bearingText(150)).toBe("150° SSE");
    expect(bearingText(null)).toBe("-");
  });
  it("writes a position with the hemispheres", () => {
    expect(positionText(60.17, 24.94)).toBe("60.17000 N 24.94000 E");
    expect(positionText(-33.5, -70.25)).toBe("33.50000 S 70.25000 W");
    expect(positionText(null, 24)).toBe("-");
  });
  it("writes speed, path and bytes", () => {
    expect(speedText(12.6)).toBe("13 km/h");
    expect(pathText(["A*", "B"])).toBe("A*,B");
    expect(pathText([])).toBe("-");
    expect(bytesText(512)).toBe("512 B");
    expect(bytesText(2048)).toBe("2.0 kB");
    expect(bytesText(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("times", () => {
  it("writes a time of the wire in the viewer's time", () => {
    const iso = "2026-10-21T12:34:56Z";
    const d = new Date(iso);
    const pad = (n: number): string => String(n).padStart(2, "0");
    expect(clockText(iso)).toBe(`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`);
    expect(dateTimeText(iso)).toContain(String(d.getFullYear()));
    expect(dateTimeText(null)).toBe("-");
    expect(clockText("nope")).toBe("-");
  });
});

describe("processTextShort", () => {
  it("says the share and the memory only", () => {
    expect(processTextShort(0.3, 42.4)).toBe("0.3 % · 42 MB");
    expect(processTextShort(12, 100.6)).toBe("12.0 % · 101 MB");
  });
});

describe("processText", () => {
  it("says the share, the memory and the time up, in the units of the page", () => {
    expect(processText(0.3, 42.4, 3 * 3600 + 120)).toBe("0.3 % · 42 MB · up 3 h");
    expect(processText(12, 100.6, 45)).toBe("12.0 % · 101 MB · up 45 s");
    expect(processText(0, 9, 90)).toBe("0.0 % · 9 MB · up 1 min");
    expect(processText(1.25, 9, 3 * 86400)).toBe("1.3 % · 9 MB · up 3 d");
  });
  it("does not count a negative time up", () => {
    expect(processText(0, 9, -5)).toBe("0.0 % · 9 MB · up 0 s");
  });
});

describe("the numbers and words of another language", () => {
  it("write the decimal point of the language and the words of its catalogue", () => {
    const list = LOCALES as LocaleInfo[];
    list.push({ code: "de", name: "Deutsch", messages: { "time.ago": "vor {span}", "time.span.min": "{n} Min." } as unknown as Catalogue });
    try {
      setLocale("de");
      expect(positionText(60.17, -24.94)).toBe("60,17000 N 24,94000 W");
      expect(distanceText(1.25)).toBe("1,3");
      expect(bytesText(1536)).toBe("1,5 kB");
      expect(agoWords(ago(120), NOW)).toBe("vor 2 Min.");
      expect(ageText(ago(7200), NOW)).toBe("2 h");
    } finally {
      list.pop();
    }
  });
});
