import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useToast } from "./Toast.jsx";

// ── OAuth token ingestion ────────────────────────────────────────────────────
// After an OAuth redirect the backend appends the token to the URL fragment:
//   /#oauth_token=...&user_id=...&username=...
// We read it once on mount, store it, and clear the fragment so it doesn't
// linger in the address bar or browser history.
function consumeOAuthFragment() {
  const hash = window.location.hash.slice(1); // strip leading "#"
  if (!hash) return null;

  const params = new URLSearchParams(hash);
  const token = params.get("oauth_token");
  const error = params.get("oauth_error");

  // Always strip the fragment to prevent token leakage via Referer headers.
  window.history.replaceState(null, "", window.location.pathname + window.location.search);

  if (error) return { error };
  if (!token) return null;

  return {
    token,
    user: {
      id: Number(params.get("user_id")),
      username: params.get("username") || "",
    },
  };
}

// ── Google / GitHub SVG icons ────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg viewBox="0 0 48 48" className="h-4 w-4" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23A11.51 11.51 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.29-1.552 3.297-1.23 3.297-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.605-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState({ google: false, github: false });
  const toast = useToast();

  // On mount: consume an OAuth redirect fragment if present, and fetch which
  // providers are enabled so we only render buttons for configured providers.
  useEffect(() => {
    const fragment = consumeOAuthFragment();
    if (fragment?.error) {
      toast(`OAuth sign-in failed: ${fragment.error}`, "error");
    } else if (fragment?.token) {
      localStorage.setItem("televault_token", fragment.token);
      localStorage.setItem("televault_user", JSON.stringify(fragment.user));
      onAuthenticated(fragment.user);
      return; // avoid fetching providers — we're already authenticated
    }

    api("/api/auth/providers")
      .then((data) => setProviders(data))
      .catch(() => {}); // non-critical — OAuth buttons just won't show
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await api(`/api/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem("televault_token", data.token);
      localStorage.setItem("televault_user", JSON.stringify(data.user));
      onAuthenticated(data.user);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function startOAuth(provider) {
    // A full-page navigation — the backend returns a 302 to the provider.
    window.location.href = `/api/auth/oauth/${provider}`;
  }

  const hasOAuth = providers.google || providers.github;

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-lg border border-brass-dim/60 bg-vault-panel font-display text-brass text-lg">
            TV
          </div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">TeleVault</h1>
          <p className="mt-1 text-sm text-vault-muted">Zero-knowledge storage, sealed behind Telegram.</p>
        </div>

        <div className="panel p-5">
          {/* ── OAuth buttons ── */}
          {hasOAuth && (
            <div className="mb-4 space-y-2">
              {providers.google && (
                <button
                  type="button"
                  onClick={() => startOAuth("google")}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-vault-line bg-vault-panel py-2 text-sm text-vault-text transition-colors hover:bg-vault-line"
                >
                  <GoogleIcon />
                  Continue with Google
                </button>
              )}
              {providers.github && (
                <button
                  type="button"
                  onClick={() => startOAuth("github")}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-vault-line bg-vault-panel py-2 text-sm text-vault-text transition-colors hover:bg-vault-line"
                >
                  <GitHubIcon />
                  Continue with GitHub
                </button>
              )}
              <div className="relative my-3 flex items-center">
                <div className="flex-grow border-t border-vault-line" />
                <span className="mx-3 shrink-0 text-xs text-vault-muted">or</span>
                <div className="flex-grow border-t border-vault-line" />
              </div>
            </div>
          )}

          {/* ── Local login / register tabs ── */}
          <div className="mb-4 flex rounded-md border border-vault-line p-1 text-sm">
            {["login", "register"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`flex-1 rounded py-1.5 capitalize transition-colors ${
                  mode === m ? "bg-brass text-vault-bg" : "text-vault-muted hover:text-vault-text"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label htmlFor="auth-username" className="eyebrow mb-1 block">Username</label>
              <input
                id="auth-username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                required
                autoComplete="username"
              />
            </div>
            <div>
              <label htmlFor="auth-password" className="eyebrow mb-1 block">Password</label>
              <input
                id="auth-password"
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>
            <button className="btn-primary w-full" disabled={busy}>
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>
        <p className="mt-4 text-center text-xs text-vault-muted">
          Your account password only unlocks the app. It never derives your encryption key —
          set a separate vault passphrase after signing in.
        </p>
      </div>
    </div>
  );
}
