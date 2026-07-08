/**
 * App-level smoke test.
 *
 * Verifies that the top-level <App> component mounts without errors and
 * shows the AuthScreen when no session token is in localStorage (the default
 * state for a new user).
 *
 * Heavy app internals (Telegram polling, file upload/download) are not
 * exercised here — that's intentional.  The goal is just to confirm the
 * component tree renders without uncaught exceptions.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ── lightweight mocks ────────────────────────────────────────────────────────
// AuthScreen fetches /api/auth/providers on mount; stub it out.
vi.mock("../lib/api.js", () => ({
  api: vi.fn().mockResolvedValue({ google: false, github: false }),
  apiBlob: vi.fn(),
  API_BASE: "",
  ApiError: class ApiError extends Error {
    constructor(msg, status) {
      super(msg);
      this.status = status;
    }
  },
}));

// crypto.js uses the Web Crypto API which is not available in jsdom.
vi.mock("../lib/crypto.js", () => ({
  encryptFile: vi.fn(),
  decryptBlob: vi.fn(),
  triggerDownload: vi.fn(),
}));

import App from "../App.jsx";

beforeEach(() => {
  localStorage.clear();
  window.location.hash = "";
});

// ── tests ────────────────────────────────────────────────────────────────────

describe("<App /> smoke", () => {
  it("renders without throwing", () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it("shows AuthScreen (login/register) when no user is stored", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /TeleVault/i })).toBeInTheDocument()
    );
    // Sign-in button confirms we're on AuthScreen (not the vault file browser)
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders the sign-in button", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument()
    );
  });
});
