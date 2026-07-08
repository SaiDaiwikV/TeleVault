/**
 * Placeholder ledger shown while the item list is loading, so navigation and
 * search feel instant instead of flashing an empty panel. Mirrors the real
 * ItemTable's column rhythm. Motion is the global skeleton-pulse, disabled
 * under prefers-reduced-motion.
 */
export default function ItemSkeleton({ rows = 5 }) {
  return (
    <div className="panel animate-fade-in overflow-hidden">
      <div className="ledger-line flex items-center gap-4 px-4 py-2.5">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton ml-auto h-3 w-10" />
        <div className="skeleton h-3 w-10" />
        <div className="skeleton h-3 w-16" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{ "--row-index": i }}
          className="stagger-row ledger-line flex animate-row-in items-center gap-3 px-4 py-3 last:border-b-0"
        >
          <div className="skeleton h-[22px] w-[22px] rounded-[3px]" />
          <div className="flex flex-col gap-1.5">
            <div className="skeleton h-3 w-40" />
            <div className="skeleton h-2 w-24" />
          </div>
          <div className="skeleton ml-auto h-3 w-12" />
          <div className="skeleton h-3 w-8" />
          <div className="skeleton h-3 w-16" />
        </div>
      ))}
    </div>
  );
}
