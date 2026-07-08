import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(() => {});

export function useToast() {
  return useContext(ToastContext);
}

const TONE_STYLES = {
  error: "border-danger/50 text-danger",
  success: "border-teal/50 text-teal",
  info: "",
};

const TONE_ICON = {
  error: "✕",
  success: "✓",
  info: "•",
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    // Flip to `leaving` so the exit animation plays, then unmount.
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 160);
  }, []);

  const push = useCallback(
    (message, tone = "info") => {
      const id = Math.random().toString(36).slice(2);
      setToasts((prev) => [...prev, { id, message, tone, leaving: false }]);
      window.setTimeout(() => dismiss(id), 4000);
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            onClick={() => dismiss(t.id)}
            className={`panel pointer-events-auto flex cursor-pointer items-center gap-2.5 px-4 py-2.5 text-sm shadow-seal ${
              t.leaving ? "animate-slide-down-out" : "animate-slide-up"
            } ${TONE_STYLES[t.tone] || ""}`}
          >
            <span className="font-mono text-xs opacity-80">{TONE_ICON[t.tone] || "•"}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
