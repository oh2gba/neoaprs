// Nothing leaves the machine in a test: a fetch that a test has not replaced fails, whatever address the page has.
globalThis.fetch = () => Promise.reject(new Error("no network in the tests: give the code a fetch of its own"));
