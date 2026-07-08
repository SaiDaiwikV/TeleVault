import { useEffect, useRef, useState } from "react";
import Modal from "./Modal.jsx";

/**
 * Animated replacement for window.prompt(). Renders a single labelled input
 * (optionally a <select> when `options` is provided, used by the move-file
 * folder picker) and resolves via onSubmit(value) / onClose().
 */
export default function PromptModal({
  title,
  label,
  defaultValue = "",
  placeholder = "",
  confirmText = "Save",
  helpText,
  options, // optional: [{ value, label }] -> renders a select instead of input
  onSubmit,
  onClose,
}) {
  const [value, setValue] = useState(defaultValue);
  const inputRef = useRef(null);

  useEffect(() => {
    // Focus + select the field once the modal has mounted.
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
      if (inputRef.current?.select) inputRef.current.select();
    }, 60);
    return () => window.clearTimeout(t);
  }, []);

  function submit(e) {
    e?.preventDefault();
    onSubmit(value);
  }

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={submit}>
            {confirmText}
          </button>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-2">
        {label && <label className="eyebrow block">{label}</label>}
        {options ? (
          <select
            ref={inputRef}
            className="input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          >
            {options.map((opt) => (
              <option key={String(opt.value)} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            ref={inputRef}
            className="input"
            value={value}
            placeholder={placeholder}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        {helpText && <p className="text-[11px] text-vault-muted">{helpText}</p>}
        {/* Enables Enter-to-submit without a visible extra button. */}
        <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
      </form>
    </Modal>
  );
}
