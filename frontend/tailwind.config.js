/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        vault: {
          bg: "#0B0F14",
          panel: "#111823",
          panel2: "#151E2B",
          line: "#232B38",
          text: "#E7ECF3",
          muted: "#8793A3",
        },
        brass: {
          DEFAULT: "#C89B3C",
          soft: "#E4C875",
          dim: "#8A6C2C",
        },
        teal: {
          DEFAULT: "#2FBF8F",
        },
        danger: {
          DEFAULT: "#E2574C",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        seal: "0 0 0 1px rgba(200,155,60,0.25), 0 8px 24px -8px rgba(0,0,0,0.6)",
      },
      // ── Motion ────────────────────────────────────────────────────────
      // Refined, purposeful micro-interactions (150–300ms). Every animation
      // here is disabled wholesale by the prefers-reduced-motion guard in
      // index.css, so we never need per-utility reduced-motion variants.
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-out": {
          from: { opacity: "1" },
          to: { opacity: "0" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down-out": {
          from: { opacity: "1", transform: "translateY(0)" },
          to: { opacity: "0", transform: "translateY(8px)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "translateY(6px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "scale-out": {
          from: { opacity: "1", transform: "translateY(0) scale(1)" },
          to: { opacity: "0", transform: "translateY(6px) scale(0.98)" },
        },
        // Row reveal: a touch of lateral drift so a freshly rendered ledger
        // reads as "settling into place" rather than blinking in.
        "row-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Wax-seal reveal: the sha256 fingerprint "presses" onto the ledger.
        "seal-in": {
          "0%": { opacity: "0", transform: "scale(0.4) rotate(-12deg)" },
          "60%": { opacity: "1", transform: "scale(1.08) rotate(2deg)" },
          "100%": { opacity: "1", transform: "scale(1) rotate(0deg)" },
        },
        // Moving sheen across the upload progress bar while bytes are sealing.
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        // Skeleton loader pulse.
        "skeleton-pulse": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.75" },
        },
        // Dropzone breathing while a file is dragged over it.
        "drag-pulse": {
          "0%, 100%": { borderColor: "rgba(200,155,60,0.9)", boxShadow: "0 0 0 0 rgba(200,155,60,0.0)" },
          "50%": { borderColor: "rgba(228,200,117,1)", boxShadow: "0 0 0 4px rgba(200,155,60,0.12)" },
        },
        // Status dot heartbeat (Telegram-connected indicator).
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgba(47,191,143,0.5)" },
          "70%": { boxShadow: "0 0 0 6px rgba(47,191,143,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(47,191,143,0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out both",
        "fade-out": "fade-out 150ms ease-in both",
        "slide-up": "slide-up 240ms cubic-bezier(0.22,1,0.36,1) both",
        "slide-down-out": "slide-down-out 160ms ease-in both",
        "scale-in": "scale-in 220ms cubic-bezier(0.22,1,0.36,1) both",
        "scale-out": "scale-out 150ms ease-in both",
        "row-in": "row-in 260ms cubic-bezier(0.22,1,0.36,1) both",
        "seal-in": "seal-in 420ms cubic-bezier(0.34,1.56,0.64,1) both",
        shimmer: "shimmer 1.4s linear infinite",
        "skeleton-pulse": "skeleton-pulse 1.2s ease-in-out infinite",
        "drag-pulse": "drag-pulse 1.4s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2s ease-out infinite",
      },
    },
  },
  plugins: [],
};
