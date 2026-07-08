/**
 * Smoke tests for frontend/src/lib/api.js
 *
 * We verify:
 *  - successful JSON responses are returned as parsed objects
 *  - non-OK responses throw ApiError with the right status
 *  - the Authorization header is attached when a token exists in localStorage
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { api, ApiError } from "../lib/api.js";

// ── fetch mock helpers ───────────────────────────────────────────────────────

function makeFetch(status, body, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: () => Promise.resolve(body),
  });
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── tests ────────────────────────────────────────────────────────────────────

describe("api()", () => {
  it("returns parsed JSON on a 200 response", async () => {
    global.fetch = makeFetch(200, { hello: "world" });
    const result = await api("/api/status");
    expect(result).toEqual({ hello: "world" });
  });

  it("throws ApiError on a non-OK response", async () => {
    global.fetch = makeFetch(401, { detail: "Unauthorized" });
    await expect(api("/api/me")).rejects.toBeInstanceOf(ApiError);
  });

  it("includes the error status on ApiError", async () => {
    global.fetch = makeFetch(404, { detail: "Not found" });
    try {
      await api("/api/items");
    } catch (err) {
      expect(err.status).toBe(404);
      expect(err.message).toMatch(/Not found/);
    }
  });

  it("attaches Authorization header when a token is stored", async () => {
    localStorage.setItem("televault_token", "tok_abc123");
    global.fetch = makeFetch(200, { ok: true });
    await api("/api/me");
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBe("Bearer tok_abc123");
  });

  it("omits Authorization header when no token is stored", async () => {
    global.fetch = makeFetch(200, { ok: true });
    await api("/api/status");
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBeUndefined();
  });

  it("sets Content-Type: application/json for JSON bodies", async () => {
    global.fetch = makeFetch(200, { token: "t" });
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: "alice", password: "supersecret" }),
    });
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });
});
