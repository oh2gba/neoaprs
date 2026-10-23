import { describe, expect, it } from "vitest";
import { login, probe, renewKey } from "@/lib/access";
import { FakeFetch } from "@/test/fakefetch";

describe("probe", () => {
  it("says locked for a 401 and open for anything else, even no answer", async () => {
    expect(await probe(new FakeFetch(401).fetch)).toBe("locked");
    expect(await probe(new FakeFetch(204).fetch)).toBe("open");
    expect(await probe(new FakeFetch(404).fetch)).toBe("open");
    expect(await probe(new FakeFetch(0).fetch)).toBe("open");
  });

  it("asks the daemon beside the page, and keeps no answer", async () => {
    const daemon = new FakeFetch(204);
    await probe(daemon.fetch);
    expect(daemon.calls).toEqual([{ url: "http://127.0.0.1:7303/access", method: "GET", body: "", cache: "no-store" }]);
  });
});

describe("login", () => {
  it("sends the key as JSON and is empty when the device is let in", async () => {
    const daemon = new FakeFetch(204);
    expect(await login("k7m2-x9pq-4hrt", daemon.fetch)).toBe("");
    expect(daemon.calls).toHaveLength(1);
    expect(daemon.calls[0]).toMatchObject({ url: "http://127.0.0.1:7303/access", method: "POST" });
    expect(JSON.parse(daemon.calls[0]?.body ?? "")).toEqual({ key: "k7m2-x9pq-4hrt" });
  });

  it("tells a wrong key, too many tries, and no answer, each in a few words", async () => {
    expect(await login("x", new FakeFetch(403).fetch)).toBe("Wrong key.");
    expect(await login("x", new FakeFetch(429).fetch)).toBe("Too many tries. Wait a few minutes.");
    expect(await login("x", new FakeFetch(500).fetch)).toBe("No answer from the daemon.");
    expect(await login("x", new FakeFetch(0).fetch)).toBe("No answer from the daemon.");
  });
});

describe("renewKey", () => {
  it("posts to access/new and is empty when the key was made", async () => {
    const daemon = new FakeFetch(204);
    expect(await renewKey(daemon.fetch)).toBe("");
    expect(daemon.calls).toEqual([{ url: "http://127.0.0.1:7303/access/new", method: "POST", body: "", cache: "no-store" }]);
    expect(await renewKey(new FakeFetch(401).fetch)).toBe("No answer from the daemon.");
  });
});
