import Modal from "./Modal.jsx";

/**
 * Animated replacement for window.confirm(). `danger` swaps the confirm button
 * to the destructive style — used for delete actions.
 */
export default function ConfirmModal({
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  danger = false,
  onConfirm,
  onClose,
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className="btn-ghost" onClick={onClose}>
            {cancelText}
          </button>
          <button className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirm}>
            {confirmText}
          </button>
        </>
      }
    >
      <p className="text-sm text-vault-muted">{message}</p>
    </Modal>
  );
}
