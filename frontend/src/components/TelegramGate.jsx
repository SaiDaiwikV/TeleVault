export default function TelegramGate({ check, onRetry }) {
  if (!check) {
    return (
      <div className="panel mb-4 flex animate-fade-in items-center gap-3 px-4 py-3 text-sm text-vault-muted">
        <span className="h-2 w-2 animate-pulse rounded-full bg-brass" />
        Checking Telegram configuration…
      </div>
    );
  }

  if (check.ok) {
    return (
      <div className="mb-4 flex animate-slide-up items-center justify-between rounded-lg border border-teal/30 bg-teal/5 px-4 py-2.5 text-sm">
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 animate-pulse-ring rounded-full bg-teal" /> Telegram connected as{" "}
          <span className="font-mono">{check.account}</span> · channel{" "}
          <span className="font-mono">{check.channel_title}</span> · {check.session_pool?.length || 1} session
          {(check.session_pool?.length || 1) > 1 ? "s" : ""} pooled
        </span>
      </div>
    );
  }

  return (
    <div className="mb-4 animate-slide-up rounded-lg border border-danger/40 bg-danger/5 px-4 py-3 text-sm">
      <div className="flex items-center justify-between">
        <span>
          <span className="text-danger">●</span> Telegram is not configured ({check.reason}). Uploads and
          downloads are disabled until this is fixed.
        </span>
        <button className="btn-ghost !py-1 !px-2 text-xs" onClick={onRetry}>
          Recheck
        </button>
      </div>
      <p className="mt-1.5 text-xs text-vault-muted">
        {check.detail} — run <code className="font-mono text-brass-soft">python scripts/check_telegram_config.py</code>{" "}
        from the project root to diagnose and log in.
      </p>
    </div>
  );
}
