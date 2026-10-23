// A fetch the tests drive by hand: it answers every request with `status` (0: the request fails, as with no network) and keeps what was asked.
export class FakeFetch {
  calls: { url: string; method: string; body: string; cache: string }[] = [];

  constructor(public status = 204) {}

  /** Passed where the code takes a fetch, or put in the global one with vi.stubGlobal. */
  fetch: typeof fetch = (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    this.calls.push({ url, method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : "", cache: init?.cache ?? "default" });
    return this.status === 0 ? Promise.reject(new TypeError("network")) : Promise.resolve(new Response(null, { status: this.status }));
  };
}
