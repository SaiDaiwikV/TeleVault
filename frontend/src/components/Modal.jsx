import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Animated, accessible modal.
 *
 * - Enters with a backdrop fade + panel scale-in; exits with the reverse,
 *   driven by a local `closing` state so the unmount waits for the animation.
 * - Escape and backdrop-click both close (routed through the same animated
 *   path via requestClose).
 * - Focus is moved into the dialog on open and the panel traps nothing heavier
 *   than that — enough for a small utility modal without a focus-trap dep.
 * - prefers-reduced-motion is handled globally in index.css (durations ~0),
 *   so the close delay still resolves quickly for those users.
 */
export default function Modal({ title, onClose, children, footer }) {
  const [closing, setClosing] = useState(false);
  const panelRef = useRef(null);

  const requestClose = useCallback(() => {
    setClosing(true);
    // Match the scale-out duration in tailwind.config.js (150ms) before unmount.
    window.setTimeout(onClose, 150);
  }, [onClose]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") requestClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [requestClose]);

  return (
    <div
      className={`fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm ${
        closing ? "animate-fade-out" : "animate-fade-in"
      }`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) requestClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === "string" ? title : undefined}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className={`panel w-full max-w-md p-5 shadow-seal outline-none ${
          closing ? "animate-scale-out" : "animate-scale-in"
        }`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold">{title}</h3>
          <button
            onClick={requestClose}
            className="rounded text-vault-muted transition-colors hover:text-vault-text"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="space-y-3">{children}</div>
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
