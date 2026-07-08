import { useCallback, useEffect, useState } from "react";
import { ToastProvider, useToast } from "./components/Toast.jsx";
import AuthScreen from "./components/AuthScreen.jsx";
import TelegramGate from "./components/TelegramGate.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Breadcrumbs from "./components/Breadcrumbs.jsx";
import ItemTable from "./components/ItemTable.jsx";
import ItemSkeleton from "./components/ItemSkeleton.jsx";
import ShareModal from "./components/ShareModal.jsx";
import PromptModal from "./components/PromptModal.jsx";
import ConfirmModal from "./components/ConfirmModal.jsx";
import { api, apiBlob, API_BASE } from "./lib/api.js";
import { encryptFile, decryptBlob, triggerDownload } from "./lib/crypto.js";

function loadUser() {
  try {
    return JSON.parse(localStorage.getItem("televault_user") || "null");
  } catch {
    return null;
  }
}

function uploadWithProgress(form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/files`);
    const token = localStorage.getItem("televault_token");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else {
        let detail = `Upload failed (${xhr.status})`;
        try {
          detail = JSON.parse(xhr.responseText).detail || detail;
        } catch {
          /* ignore */
        }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(form);
  });
}

function VaultApp({ user, onLogout }) {
  const toast = useToast();
  const [telegramCheck, setTelegramCheck] = useState(null);
  const [passphrase, setPassphrase] = useState("");
  const [folderId, setFolderId] = useState(null);
  const [trail, setTrail] = useState([]);
  const [items, setItems] = useState({ folders: [], files: [] });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [shareTarget, setShareTarget] = useState(null);
  // Single piece of state drives every prompt/confirm modal. `null` = none open.
  const [dialog, setDialog] = useState(null);

  const closeDialog = useCallback(() => setDialog(null), []);

  const runTelegramCheck = useCallback(async () => {
    setTelegramCheck(null);
    try {
      setTelegramCheck(await api("/api/telegram/check"));
    } catch (err) {
      setTelegramCheck({ ok: false, reason: "unreachable", detail: err.message });
    }
  }, []);

  const refreshItems = useCallback(async () => {
    const params = new URLSearchParams();
    if (folderId !== null) params.set("folder_id", folderId);
    if (search) params.set("q", search);
    try {
      setItems(await api(`/api/items?${params.toString()}`));
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }, [folderId, search, toast]);

  useEffect(() => {
    runTelegramCheck();
  }, [runTelegramCheck]);

  useEffect(() => {
    setLoading(true);
    refreshItems();
  }, [refreshItems]);

  function openFolder(folder) {
    setFolderId(folder.id);
    setTrail((prev) => [...prev, folder]);
  }

  function navigate(id, newTrail) {
    setFolderId(id);
    setTrail(newTrail);
  }

  // ── Folder actions ────────────────────────────────────────────────────
  function newFolder() {
    setDialog({
      kind: "prompt",
      title: "New folder",
      label: "Folder name",
      confirmText: "Create",
      defaultValue: "",
      onSubmit: async (name) => {
        closeDialog();
        if (!name?.trim()) return;
        try {
          await api("/api/folders", {
            method: "POST",
            body: JSON.stringify({ name: name.trim(), parent_id: folderId }),
          });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  function renameFolder(folder) {
    setDialog({
      kind: "prompt",
      title: "Rename folder",
      label: "New folder name",
      confirmText: "Rename",
      defaultValue: folder.name,
      onSubmit: async (name) => {
        closeDialog();
        if (!name?.trim() || name === folder.name) return;
        try {
          await api(`/api/folders/${folder.id}/rename`, {
            method: "PATCH",
            body: JSON.stringify({ name: name.trim() }),
          });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  function deleteFolder(folder) {
    setDialog({
      kind: "confirm",
      title: "Delete folder",
      message: `Delete empty folder "${folder.name}"? This can't be undone.`,
      confirmText: "Delete",
      danger: true,
      onConfirm: async () => {
        closeDialog();
        try {
          await api(`/api/folders/${folder.id}`, { method: "DELETE" });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  // ── Upload / download ─────────────────────────────────────────────────
  async function handleUpload(file) {
    if (passphrase.length < 8) {
      toast("Set a vault passphrase (8+ characters) before uploading", "error");
      return;
    }
    setUploading(true);
    setProgress(5);
    try {
      const enc = await encryptFile(file, passphrase);
      setProgress(15);
      const form = new FormData();
      form.append("upload", enc.blob, file.name);
      if (folderId !== null) form.append("folder_id", folderId);
      form.append("encrypted", "true");
      form.append("enc_alg", "AES-256-GCM");
      form.append("enc_salt_b64", enc.saltB64);
      form.append("enc_iv_b64", enc.ivB64);
      form.append("enc_kdf", "PBKDF2-HMAC-SHA256");
      form.append("enc_iterations", String(enc.iterations));
      form.append("original_sha256", enc.originalSha256);
      const result = await uploadWithProgress(form, (p) => setProgress(Math.max(15, p)));
      toast(
        result.deduplicated
          ? "Uploaded (deduplicated — identical file already sealed)"
          : "Encrypted upload complete",
        "success"
      );
      refreshItems();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  async function downloadFile(file) {
    if (file.encrypted && passphrase.length < 8) {
      toast("Enter the vault passphrase to decrypt this file", "error");
      return;
    }
    try {
      const blob = await apiBlob(`/api/files/${file.id}/download`);
      const finalBlob = file.encrypted ? await decryptBlob(blob, file, passphrase) : blob;
      triggerDownload(finalBlob, file.name);
    } catch (err) {
      toast(
        err.message.includes("OperationError") || err.name === "OperationError"
          ? "Decryption failed — check your vault passphrase"
          : err.message,
        "error"
      );
    }
  }

  // ── File actions ──────────────────────────────────────────────────────
  function renameFile(file) {
    setDialog({
      kind: "prompt",
      title: "Rename file",
      label: "New file name",
      confirmText: "Rename",
      defaultValue: file.name,
      onSubmit: async (name) => {
        closeDialog();
        if (!name?.trim() || name === file.name) return;
        try {
          await api(`/api/files/${file.id}/rename`, {
            method: "PATCH",
            body: JSON.stringify({ name: name.trim() }),
          });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  async function moveFile(file) {
    // Fetch the full folder list so the user picks a destination instead of
    // typing a raw folder ID.
    let folders = [];
    try {
      folders = await api("/api/folders/all");
    } catch (err) {
      toast(err.message, "error");
      return;
    }
    const options = [
      { value: "", label: "Vault (root)" },
      ...folders.map((f) => ({ value: String(f.id), label: f.name })),
    ];
    setDialog({
      kind: "prompt",
      title: `Move "${file.name}"`,
      label: "Destination folder",
      confirmText: "Move",
      defaultValue: file.folder_id != null ? String(file.folder_id) : "",
      options,
      onSubmit: async (raw) => {
        closeDialog();
        const folder_id = raw === "" ? null : Number(raw);
        try {
          await api(`/api/files/${file.id}/move`, {
            method: "PATCH",
            body: JSON.stringify({ folder_id }),
          });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  function deleteFile(file) {
    setDialog({
      kind: "confirm",
      title: "Delete file",
      message: `Delete "${file.name}" and its Telegram chunks? This can't be undone.`,
      confirmText: "Delete",
      danger: true,
      onConfirm: async () => {
        closeDialog();
        try {
          await api(`/api/files/${file.id}`, { method: "DELETE" });
          refreshItems();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    });
  }

  const totalItems = items.folders.length + items.files.length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-brass-dim/60 bg-vault-panel font-display text-sm text-brass transition-transform duration-200 hover:rotate-3 hover:scale-105">
            TV
          </div>
          <h1 className="font-display text-xl font-semibold tracking-tight">TeleVault</h1>
        </div>
        <input
          className="input max-w-xs"
          placeholder="Search files & folders"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </header>

      <TelegramGate check={telegramCheck} onRetry={runTelegramCheck} />

      <div className="flex gap-5">
        <Sidebar
          user={user}
          onLogout={onLogout}
          passphrase={passphrase}
          setPassphrase={setPassphrase}
          onNewFolder={newFolder}
          onUpload={handleUpload}
          uploading={uploading}
          progress={progress}
          telegramReady={!!telegramCheck?.ok}
        />

        <main className="flex-1 space-y-3">
          <div className="flex items-center justify-between">
            <Breadcrumbs trail={trail} onNavigate={navigate} />
            <span className="text-xs text-vault-muted">
              {totalItems} item{totalItems === 1 ? "" : "s"}
            </span>
          </div>
          {loading ? (
            <ItemSkeleton rows={5} />
          ) : (
            <ItemTable
              folders={items.folders}
              files={items.files}
              onOpenFolder={openFolder}
              onRenameFolder={renameFolder}
              onDeleteFolder={deleteFolder}
              onDownloadFile={downloadFile}
              onRenameFile={renameFile}
              onMoveFile={moveFile}
              onDeleteFile={deleteFile}
              onShareFile={setShareTarget}
            />
          )}
        </main>
      </div>

      {shareTarget && <ShareModal file={shareTarget} onClose={() => setShareTarget(null)} />}

      {dialog?.kind === "prompt" && (
        <PromptModal
          title={dialog.title}
          label={dialog.label}
          defaultValue={dialog.defaultValue}
          confirmText={dialog.confirmText}
          options={dialog.options}
          helpText={dialog.helpText}
          onSubmit={dialog.onSubmit}
          onClose={closeDialog}
        />
      )}
      {dialog?.kind === "confirm" && (
        <ConfirmModal
          title={dialog.title}
          message={dialog.message}
          confirmText={dialog.confirmText}
          danger={dialog.danger}
          onConfirm={dialog.onConfirm}
          onClose={closeDialog}
        />
      )}
    </div>
  );
}

function AppShell() {
  const [user, setUser] = useState(loadUser);

  function logout() {
    localStorage.removeItem("televault_token");
    localStorage.removeItem("televault_user");
    setUser(null);
  }

  if (!user) return <AuthScreen onAuthenticated={setUser} />;
  return <VaultApp user={user} onLogout={logout} />;
}

export default function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  );
}
