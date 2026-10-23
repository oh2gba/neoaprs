import { describe, expect, it } from "vitest";
import { CERT_FILE, CERT_PATH, DEVICES, STEPS, deviceOf, secureUrl } from "@/lib/httpshelp";

const ANDROID_CHROME = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36";
const ANDROID_FIREFOX = "Mozilla/5.0 (Android 14; Mobile; rv:140.0) Gecko/140.0 Firefox/140.0";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const IPAD_AS_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";
const FIREFOX_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0";
const FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0";
const EDGE_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0";
const CHROME_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
const CHROME_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";

describe("the device the steps are for", () => {
  it("takes a phone or tablet by its system, whatever the browser", () => {
    expect(deviceOf(ANDROID_CHROME)).toBe("android");
    expect(deviceOf(ANDROID_FIREFOX)).toBe("android");
    expect(deviceOf(IPHONE)).toBe("ios");
    expect(deviceOf(IPAD_AS_MAC, 5)).toBe("ios");
  });

  it("takes a computer by its system, and Firefox on a computer by its own list", () => {
    expect(deviceOf(EDGE_WINDOWS)).toBe("windows");
    expect(deviceOf(CHROME_MAC)).toBe("mac");
    expect(deviceOf(IPAD_AS_MAC, 0)).toBe("mac");
    expect(deviceOf(CHROME_LINUX)).toBe("linux");
    expect(deviceOf(FIREFOX_WINDOWS)).toBe("firefox");
    expect(deviceOf(FIREFOX_LINUX)).toBe("firefox");
    expect(deviceOf("something else")).toBe("linux");
  });

  it("has short steps for every device it offers, and each names the file or the menu", () => {
    for (const device of DEVICES) {
      const steps = STEPS[device.value];
      expect(steps.length, device.label).toBeGreaterThanOrEqual(2);
      expect(steps.length, device.label).toBeLessThanOrEqual(3);
      for (const step of steps) expect(step.length, step).toBeLessThan(170);
    }
  });
});

describe("the addresses", () => {
  it("gives the certificate from the daemon under the name the device saves it as, and the secure page on the host the page was opened at", () => {
    expect(CERT_PATH).toBe("/neoaprs-ca.crt");
    expect(CERT_FILE).toBe("NeoAPRS-CA.crt");
    expect(secureUrl(7304, "192.168.1.20")).toBe("https://192.168.1.20:7304/");
    expect(secureUrl(7304, "[fe80::1]")).toBe("https://[fe80::1]:7304/");
  });
});
