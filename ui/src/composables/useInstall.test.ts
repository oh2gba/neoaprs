import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import InstallApp from "@/components/InstallApp.vue";
import { listenForInstall, useInstall, type InstallPrompt } from "@/composables/useInstall";

function offer(outcome: "accepted" | "dismissed" = "accepted", fail = false): InstallPrompt {
  const event = new Event("beforeinstallprompt", { cancelable: true }) as InstallPrompt;
  event.prompt = vi.fn(() => (fail ? Promise.reject(new Error("no")) : Promise.resolve()));
  event.userChoice = Promise.resolve({ outcome });
  return event;
}

let stop = (): void => undefined;
afterEach(() => stop());

describe("useInstall", () => {
  it("offers the install only after the browser has said it can", async () => {
    stop = listenForInstall(window);
    const { canInstall, install } = useInstall();
    expect(canInstall.value).toBe(false);
    expect(await install()).toBe("none");
    const event = offer();
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(canInstall.value).toBe(true);
    expect(await install()).toBe("accepted");
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(canInstall.value).toBe(false);
  });

  it("is done with the offer when the person says no, and when the app is installed some other way", async () => {
    stop = listenForInstall(window);
    const { canInstall, install } = useInstall();
    window.dispatchEvent(offer("dismissed"));
    expect(await install()).toBe("dismissed");
    expect(canInstall.value).toBe(false);
    window.dispatchEvent(offer());
    expect(canInstall.value).toBe(true);
    window.dispatchEvent(new Event("appinstalled"));
    expect(canInstall.value).toBe(false);
  });

  it("says dismissed when the browser fails to show its dialog", async () => {
    stop = listenForInstall(window);
    window.dispatchEvent(offer("accepted", true));
    expect(await useInstall().install()).toBe("dismissed");
  });

  it("stops listening", () => {
    listenForInstall(window)();
    window.dispatchEvent(offer());
    expect(useInstall().canInstall.value).toBe(false);
  });
});

describe("the Install app button", () => {
  it("is not there until the browser offers, then installs, then goes", async () => {
    stop = listenForInstall(window);
    const view = mount(InstallApp);
    expect(view.find("#install-app").exists()).toBe(false);
    const event = offer();
    window.dispatchEvent(event);
    await view.vm.$nextTick();
    await view.get("#install-app").trigger("click");
    await vi.waitFor(() => expect(event.prompt).toHaveBeenCalledOnce());
    await vi.waitFor(() => expect(view.find("#install-app").exists()).toBe(false));
  });
});
