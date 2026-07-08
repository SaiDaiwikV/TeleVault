import { useCallback, useRef, useState } from "react";

export default function Sidebar({
  user,
  onLogout,
  passphrase,
  setPassphrase,
  onNewFolder,
  onUpload,
  uploading,
  progress,
  telegramReady,
}) {
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef(null);

  const handleFiles = useCallback(
    (files) => {
      if (!files || !files.length) return;
      onUpload(files[0]);
    },
    [onUpload]
  );

  return (
    <aside className="panel flex w-72 shrink-0 flex-col gap-5 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow">Signed in</p>
          <p className="font-medium">{user.username}</p>
        </div>
        <button onClick={onLogout} className="text-xs text-vault-muted hover:text-danger">
          Log out
        </button>
      </div>

      <div>
        <label className="eyebrow mb-1 block">Vault passphrase</label>
        <input
          type="password"
          className="input"
          placeholder="Required to encrypt/decrypt"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="off"
        />
        <p className="mt-1 text-[11px] text-vault-muted">
          Never sent to the server. Lose it and your files are unrecoverable — that's the point.
        </p>
      </div>

      <button className="btn-ghost w-full" onClick={onNewFolder}>
        + New folder
      </button>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => telegramReady && !uploading && fileInput.current?.click()}
        className={`group flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center text-sm transition-all duration-200 ${
          !telegramReady
            ? "cursor-not-allowed border-vault-line text-vault-muted opacity-50"
            : dragOver
            ? "animate-drag-pulse scale-[1.02] cursor-pointer border-brass bg-brass/5 text-brass-soft"
            : "cursor-pointer border-vault-line text-vault-muted hover:border-brass-dim hover:text-brass-soft"
        }`}
      >
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
          disabled={!telegramReady || uploading}
        />
        <span
          className={`font-display text-2xl transition-transform duration-200 ${
            dragOver ? "scale-125" : "group-hover:scale-110"
          }`}
        >
          ＋
        </span>
        <span>{telegramReady ? "Drop a file or click to encrypt & upload" : "Fix Telegram config to upload"}</span>
      </div>

      {uploading && (
        <div className="animate-fade-in">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-vault-line">
            <div
              className="bg-shimmer h-full animate-shimmer rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] text-vault-muted">{progress}% — encrypting &amp; sealing chunks…</p>
        </div>
      )}
    </aside>
  );
}
