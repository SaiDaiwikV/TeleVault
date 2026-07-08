import { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import { api, API_BASE } from "../lib/api.js";
import { useToast } from "./Toast.jsx";

export default function ShareModal({ file, onClose }) {
  const [links, setLinks] = useState([]);
  const [hours, setHours] = useState(24);
  const [maxDownloads, setMaxDownloads] = useState("");
  const [creating, setCreating] = useState(false);
  const [freshToken, setFreshToken] = useState(null);
  const toast = useToast();

  async function refresh() {
    try {
      setLinks(await api(`/api/files/${file.id}/shares`));
    } catch (err) {
      toast(err.message, "error");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

  async function create() {
    setCreating(true);
    try {
      const payload = { expires_in_hours: Number(hours) || 24 };
      if (maxDownloads) payload.max_downloads = Number(maxDownloads);
      const link = await api(`/api/files/${file.id}/share`, { method: "POST", body: JSON.stringify(payload) });
      setFreshToken(`${window.location.origin}${API_BASE}${link.url}`);
      refresh();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id) {
    try {
      await api(`/api/shares/${id}`, { method: "DELETE" });
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  return (
    <Modal title={`Share "${file.name}"`} onClose={onClose}>
      <p className="text-xs text-vault-muted">
        Anyone with the link can download the <span className="text-brass-soft">ciphertext</span>. Share your vault
        passphrase separately — it's never included in the link.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="eyebrow mb-1 block">Expires in (hours)</label>
          <input type="number" min={1} className="input" value={hours} onChange={(e) => setHours(e.target.value)} />
        </div>
        <div>
          <label className="eyebrow mb-1 block">Max downloads</label>
          <input
            type="number"
            min={1}
            placeholder="Unlimited"
            className="input"
            value={maxDownloads}
            onChange={(e) => setMaxDownloads(e.target.value)}
          />
        </div>
      </div>
      <button className="btn-primary w-full" onClick={create} disabled={creating}>
        {creating ? "Creating…" : "Create share link"}
      </button>

      {freshToken && (
        <div className="rounded-md border border-teal/30 bg-teal/5 p-2.5 text-xs">
          <p className="mb-1 text-teal">Link created — copy it now, it won't be shown again:</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate font-mono">{freshToken}</code>
            <button
              className="btn-ghost !py-1 !px-2"
              onClick={() => {
                navigator.clipboard.writeText(freshToken);
                toast("Copied to clipboard", "success");
              }}
            >
              Copy
            </button>
          </div>
        </div>
      )}

      {links.length > 0 && (
        <div>
          <p className="eyebrow mb-1.5">Active links</p>
          <ul className="space-y-1.5">
            {links.map((l) => (
              <li key={l.id} className="flex items-center justify-between rounded-md border border-vault-line px-2.5 py-1.5 text-xs">
                <span className={l.revoked ? "text-vault-muted line-through" : ""}>
                  {l.download_count}
                  {l.max_downloads ? `/${l.max_downloads}` : ""} downloads · expires{" "}
                  {l.expires_at ? new Date(l.expires_at).toLocaleDateString() : "never"}
                </span>
                {!l.revoked && (
                  <button className="text-danger hover:underline" onClick={() => revoke(l.id)}>
                    Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
