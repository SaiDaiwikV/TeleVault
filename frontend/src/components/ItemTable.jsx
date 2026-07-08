import SealBadge from "./SealBadge.jsx";
import { formatBytes, formatDate, shortHash } from "../lib/format.js";

const ICON_FOLDER = "▤";

export default function ItemTable({
  folders,
  files,
  onOpenFolder,
  onRenameFolder,
  onDeleteFolder,
  onDownloadFile,
  onRenameFile,
  onMoveFile,
  onDeleteFile,
  onShareFile,
}) {
  const empty = folders.length === 0 && files.length === 0;

  if (empty) {
    return (
      <div className="panel flex animate-fade-in flex-col items-center gap-2 py-16 text-center text-sm text-vault-muted">
        <span className="font-display text-3xl text-vault-line">◇</span>
        <p>Nothing here yet.</p>
        <p className="text-xs">Upload a file or create a folder to get started.</p>
      </div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="ledger-line text-left text-xs uppercase tracking-wide text-vault-muted">
            <th className="px-4 py-2.5 font-medium">Name</th>
            <th className="px-4 py-2.5 font-medium">Size</th>
            <th className="px-4 py-2.5 font-medium">Chunks</th>
            <th className="px-4 py-2.5 font-medium">Added</th>
            <th className="px-4 py-2.5 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {folders.map((folder, i) => (
            <tr
              key={`f${folder.id}`}
              style={{ "--row-index": i }}
              className="stagger-row ledger-line animate-row-in transition-colors duration-150 last:border-b-0 hover:bg-vault-panel2"
            >
              <td className="px-4 py-2.5">
                <button
                  onClick={() => onOpenFolder(folder)}
                  className="flex items-center gap-2 text-left hover:text-brass-soft"
                >
                  <span className="text-brass-dim">{ICON_FOLDER}</span>
                  {folder.name}
                </button>
              </td>
              <td className="px-4 py-2.5 text-vault-muted">—</td>
              <td className="px-4 py-2.5 text-vault-muted">—</td>
              <td className="px-4 py-2.5 text-vault-muted">{formatDate(folder.created_at)}</td>
              <td className="px-4 py-2.5">
                <div className="flex justify-end gap-3 text-xs text-vault-muted">
                  <button onClick={() => onRenameFolder(folder)} className="transition-colors hover:text-brass-soft">
                    Rename
                  </button>
                  <button onClick={() => onDeleteFolder(folder)} className="transition-colors hover:text-danger">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {files.map((file, i) => (
            <tr
              key={`file${file.id}`}
              style={{ "--row-index": folders.length + i }}
              className="stagger-row ledger-line animate-row-in transition-colors duration-150 last:border-b-0 hover:bg-vault-panel2"
            >
              <td className="px-4 py-2.5">
                <div className="flex items-center gap-2.5">
                  <SealBadge sha256={file.sha256} title={`sha256:${file.sha256}\nclick Details to inspect`} />
                  <div>
                    <p className="leading-tight">{file.name}</p>
                    <p className="font-mono text-[11px] text-vault-muted">
                      {file.encrypted ? "AES-256-GCM" : "plaintext"} · {shortHash(file.sha256)}
                    </p>
                  </div>
                </div>
              </td>
              <td className="px-4 py-2.5 text-vault-muted">{formatBytes(file.size)}</td>
              <td className="px-4 py-2.5 text-vault-muted">{file.chunks.length}</td>
              <td className="px-4 py-2.5 text-vault-muted">{formatDate(file.created_at)}</td>
              <td className="px-4 py-2.5">
                <div className="flex justify-end gap-3 text-xs text-vault-muted">
                  <button onClick={() => onDownloadFile(file)} className="transition-colors hover:text-brass-soft">
                    Download
                  </button>
                  <button onClick={() => onShareFile(file)} className="transition-colors hover:text-brass-soft">
                    Share
                  </button>
                  <button onClick={() => onRenameFile(file)} className="transition-colors hover:text-brass-soft">
                    Rename
                  </button>
                  <button onClick={() => onMoveFile(file)} className="transition-colors hover:text-brass-soft">
                    Move
                  </button>
                  <button onClick={() => onDeleteFile(file)} className="transition-colors hover:text-danger">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
