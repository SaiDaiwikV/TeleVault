import { sealCells } from "../lib/crypto.js";

export default function SealBadge({ sha256, size = 22, title }) {
  const cells = sealCells(sha256);
  const cell = size / 4;
  return (
    <div
      className="grid shrink-0 animate-seal-in overflow-hidden rounded-[3px] shadow-seal transition-transform duration-200 hover:scale-110"
      style={{ width: size, height: size, gridTemplateColumns: `repeat(4, ${cell}px)` }}
      title={title || (sha256 ? `sha256:${sha256}` : "no hash yet")}
    >
      {cells.map((color, i) => (
        <div key={i} style={{ backgroundColor: color, width: cell, height: cell }} />
      ))}
    </div>
  );
}
