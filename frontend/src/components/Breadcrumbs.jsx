export default function Breadcrumbs({ trail, onNavigate }) {
  return (
    <div className="flex items-center gap-1.5 text-sm text-vault-muted">
      <button onClick={() => onNavigate(null, [])} className="hover:text-brass-soft">
        Vault
      </button>
      {trail.map((folder, i) => (
        <span key={folder.id} className="flex items-center gap-1.5">
          <span className="text-vault-line">/</span>
          <button
            onClick={() => onNavigate(folder.id, trail.slice(0, i + 1))}
            className={i === trail.length - 1 ? "text-vault-text" : "hover:text-brass-soft"}
          >
            {folder.name}
          </button>
        </span>
      ))}
    </div>
  );
}
