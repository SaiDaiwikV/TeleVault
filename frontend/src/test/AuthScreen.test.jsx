/**
 * Smoke tests for AuthScreen component.
 *
 * We verify:
 *  - the component renders without crashing
 *  - login / register tab switching works
 *  - successful login stores the token and calls onAuthenticated
 *  - failed login shows an error toast (not a crash)
 *  - OAuth buttons are rendered when providers are enabled
 *  - OAuth buttons are hidden when providers are disabled
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the Toast provider so AuthScreen can call useToast()
vi.mock("../components/Toast.jsx", () => ({
  useToast: () => vi.fn(),
}));

// Mock the api module so we control backend responses
vi.mock("../lib/api.js", () => ({
  api: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(msg, status) {
      super(msg);
      this.status = status;
    }
  },
}));

import { api } from "../lib/api.js";
import AuthScreen from "../components/AuthScreen.jsx";

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  // Default: no OAuth providers enabled, no token fragment
  window.location.hash = "";
  api.mockResolvedValue({ google: false, github: false });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── render smoke test ────────────────────────────────────────────────────────

describe("AuthScreen", () => {
  it("renders without crashing", async () => {
    render(<AuthScreen onAuthenticated={() => {}} />);
    expect(screen.getByRole("heading", { name: /TeleVault/i })).toBeInTheDocument();
  });

  it("shows login and register tabs", async () => {
    render(<AuthScreen onAuthenticated={() => {}} />);
    expect(screen.getByRole("button", { name: /login/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /register/i })).toBeInTheDocument();
  });

  it("switches to register mode when the register tab is clicked", async () => {
    render(<AuthScreen onAuthenticated={() => {}} />);
    const registerBtn = screen.getByRole("button", { name: /register/i });
    await userEvent.click(registerBtn);
    // The submit button label changes to "Create account" in register mode
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("calls onAuthenticated and stores token on successful login", async () => {
    const onAuthenticated = vi.fn();
    // First call is /api/auth/providers (returns no oauth), second is /api/auth/login
    api
      .mockResolvedValueOnce({ google: false, github: false }) // providers fetch
      .mockResolvedValueOnce({ token: "tok_xyz", user: { id: 1, username: "alice" } }); // login

    render(<AuthScreen onAuthenticated={onAuthenticated} />);

    await userEvent.type(screen.getByLabelText(/username/i), "alice");
    await userEvent.type(screen.getByLabelText(/password/i), "supersecret");
    fireEvent.submit(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ id: 1, username: "alice" }));
    expect(localStorage.getItem("televault_token")).toBe("tok_xyz");
  });

  it("does not crash on login failure", async () => {
    const { ApiError } = await import("../lib/api.js");
    api
      .mockResolvedValueOnce({ google: false, github: false }) // providers
      .mockRejectedValueOnce(new ApiError("Invalid username or password", 401));

    render(<AuthScreen onAuthenticated={() => {}} />);

    await userEvent.type(screen.getByLabelText(/username/i), "bad");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpassword");
    fireEvent.submit(screen.getByRole("button", { name: /sign in/i }));

    // No crash — sign-in button should reappear (not in loading state)
    await waitFor(() => expect(screen.getByRole("button", { name: /sign in/i })).not.toBeDisabled());
  });

  it("renders Google button when google provider is enabled", async () => {
    api.mockResolvedValueOnce({ google: true, github: false });
    render(<AuthScreen onAuthenticated={() => {}} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /continue with google/i })).toBeInTheDocument()
    );
  });

  it("renders GitHub button when github provider is enabled", async () => {
    api.mockResolvedValueOnce({ google: false, github: true });
    render(<AuthScreen onAuthenticated={() => {}} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /continue with github/i })).toBeInTheDocument()
    );
  });

  it("hides OAuth buttons when no providers are configured", async () => {
    api.mockResolvedValueOnce({ google: false, github: false });
    render(<AuthScreen onAuthenticated={() => {}} />);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /continue with google/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /continue with github/i })).not.toBeInTheDocument();
    });
  });
});
