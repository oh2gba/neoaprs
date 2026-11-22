import { describe, expect, it } from "vitest";
import { effectScope, nextTick, ref, shallowRef } from "vue";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import type { Connection } from "@/lib/hub";

describe("the alert's Test and the socket", () => {
  it("stops waiting when the socket closes: the answer is lost with it", async () => {
    const connection = shallowRef<Connection>("open");
    const scope = effectScope();
    const alert = scope.run(() =>
      useAlertTest(shallowRef(null), shallowRef(null), () => true, { [ALERT_KEY]: "beep" }, ref("beep"), connection),
    );
    if (!alert) throw new Error("no scope");
    alert.test();
    expect(alert.running.value).toBe(true);
    connection.value = "closed";
    await nextTick();
    expect(alert.running.value).toBe(false);
    scope.stop();
  });
});
