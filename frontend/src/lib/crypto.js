// All encryption happens here, client-side, with the Web Crypto API. The
// vault passphrase is never sent to the backend — only ciphertext + the
// public salt/IV needed to decrypt it later are stored server-side.

const PBKDF2_ITERATIONS = 310_000;

function bytesToB64(bytes) {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary);
}

function b64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function deriveKey(passphrase, salt, iterations, usage) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"]
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    usage
  );
}

export async function encryptFile(file, passphrase) {
  const plain = await file.arrayBuffer();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, PBKDF2_ITERATIONS, ["encrypt"]);
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plain);
  return {
    blob: new Blob([encrypted], { type: "application/octet-stream" }),
    byteLength: encrypted.byteLength,
    originalSha256: await sha256Hex(plain),
    saltB64: bytesToB64(salt),
    ivB64: bytesToB64(iv),
    iterations: PBKDF2_ITERATIONS,
  };
}

export async function decryptBlob(blob, fileMeta, passphrase) {
  const salt = b64ToBytes(fileMeta.enc_salt_b64);
  const iv = b64ToBytes(fileMeta.enc_iv_b64);
  const key = await deriveKey(passphrase, salt, fileMeta.enc_iterations, ["decrypt"]);
  const cipher = await blob.arrayBuffer();
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, cipher);
  return new Blob([plain], { type: fileMeta.mime || "application/octet-stream" });
}

export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Deterministic visual "wax seal" for a file: a 4x4 grid of hues derived
 * from its ciphertext SHA-256. Identical ciphertext (e.g. a deduplicated
 * re-upload) always produces an identical seal, so it doubles as an
 * at-a-glance integrity/duplicate signal — not cryptographic proof, just a
 * human-legible fingerprint of the same hash already shown in the details.
 */
export function sealCells(sha256Hex) {
  if (!sha256Hex) return Array(16).fill("#232B38");
  const cells = [];
  for (let i = 0; i < 16; i += 1) {
    const byte = parseInt(sha256Hex.slice(i * 2, i * 2 + 2), 16) || 0;
    const hue = (byte / 255) * 40 + 25; // amber-to-teal-ish arc, stays in-palette
    const light = 28 + (byte % 20);
    cells.push(`hsl(${hue.toFixed(0)}, 55%, ${light}%)`);
  }
  return cells;
}
