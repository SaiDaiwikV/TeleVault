const state = {
  token: localStorage.getItem("televault_token"),
  user: JSON.parse(localStorage.getItem("televault_user") || "null"),
  mode: "login",
  folderId: null,
  search: "",
};

const $ = (id) => document.getElementById(id);

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function setAuthMode(mode) {
  state.mode = mode;
  $("loginMode").classList.toggle("active", mode === "login");
  $("registerMode").classList.toggle("active", mode === "register");
}

function showApp() {
  $("authPanel").classList.add("hidden");
  $("appPanel").classList.remove("hidden");
  $("userName").textContent = state.user?.username || "";
  refreshItems();
}

function showAuth() {
  $("authPanel").classList.remove("hidden");
  $("appPanel").classList.add("hidden");
}

function formatBytes(bytes) {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function b64(bytes) {
  let binary = "";
  bytes.forEach((byte) => (binary += String.fromCharCode(byte)));
  return btoa(binary);
}

function b64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function deriveKey(passphrase, salt, iterations) {
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
    ["encrypt", "decrypt"]
  );
}

async function encryptFile(file, passphrase) {
  const plain = await file.arrayBuffer();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const iterations = 310000;
  const key = await deriveKey(passphrase, salt, iterations);
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plain);
  return {
    blob: new Blob([encrypted], { type: "application/octet-stream" }),
    originalSha256: await sha256Hex(plain),
    saltB64: b64(salt),
    ivB64: b64(iv),
    iterations,
  };
}

async function decryptBlob(blob, file, passphrase) {
  const salt = b64ToBytes(file.enc_salt_b64);
  const iv = b64ToBytes(file.enc_iv_b64);
  const key = await deriveKey(passphrase, salt, file.enc_iterations);
  const cipher = await blob.arrayBuffer();
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, cipher);
  return new Blob([plain], { type: file.mime || "application/octet-stream" });
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function refreshItems() {
  const params = new URLSearchParams();
  if (state.folderId !== null) params.set("folder_id", state.folderId);
  if (state.search) params.set("q", state.search);
  const data = await api(`/api/items?${params.toString()}`);
  const total = data.folders.length + data.files.length;
  $("itemCount").textContent = `${total} item${total === 1 ? "" : "s"}`;
  const body = $("itemsBody");
  body.innerHTML = "";

  for (const folder of data.folders) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><button class="name-button" data-open-folder="${folder.id}">/${folder.name}</button></td>
      <td><span class="tag">Folder</span></td>
      <td>-</td>
      <td>-</td>
      <td class="actions-cell">
        <button data-rename-folder="${folder.id}">Rename</button>
        <button class="danger" data-delete-folder="${folder.id}">Delete</button>
      </td>`;
    body.appendChild(row);
  }

  for (const file of data.files) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${file.name}</td>
      <td><span class="tag">${file.encrypted ? "Encrypted" : "Plain"}</span></td>
      <td>${formatBytes(file.size)}</td>
      <td>${file.chunks.length}</td>
      <td class="actions-cell">
        <button data-download-file="${file.id}">Download</button>
        <button data-rename-file="${file.id}">Rename</button>
        <button data-move-file="${file.id}">Move</button>
        <button class="danger" data-delete-file="${file.id}">Delete</button>
      </td>`;
    body.appendChild(row);
  }

  body.querySelectorAll("[data-open-folder]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.folderId = Number(btn.dataset.openFolder);
      $("folderTitle").textContent = btn.textContent;
      refreshItems().catch((err) => toast(err.message));
    });
  });
  body.querySelectorAll("[data-download-file]").forEach((btn) => {
    btn.addEventListener("click", () => {
      downloadFile(Number(btn.dataset.downloadFile), data.files).catch((err) => toast(err.message));
    });
  });
  body.querySelectorAll("[data-rename-file]").forEach((btn) => {
    btn.addEventListener("click", () => renameFile(Number(btn.dataset.renameFile)).catch((err) => toast(err.message)));
  });
  body.querySelectorAll("[data-move-file]").forEach((btn) => {
    btn.addEventListener("click", () => moveFile(Number(btn.dataset.moveFile)).catch((err) => toast(err.message)));
  });
  body.querySelectorAll("[data-delete-file]").forEach((btn) => {
    btn.addEventListener("click", () => deleteFile(Number(btn.dataset.deleteFile)).catch((err) => toast(err.message)));
  });
  body.querySelectorAll("[data-rename-folder]").forEach((btn) => {
    btn.addEventListener("click", () => renameFolder(Number(btn.dataset.renameFolder)).catch((err) => toast(err.message)));
  });
  body.querySelectorAll("[data-delete-folder]").forEach((btn) => {
    btn.addEventListener("click", () => deleteFolder(Number(btn.dataset.deleteFolder)).catch((err) => toast(err.message)));
  });
}

async function uploadSelectedFile() {
  const file = $("fileInput").files[0];
  const passphrase = $("vaultPassphrase").value;
  if (!file) return toast("Choose a file first");
  if (passphrase.length < 8) return toast("Use an encryption passphrase with at least 8 characters");
  $("uploadProgress").value = 10;
  const encrypted = await encryptFile(file, passphrase);
  $("uploadProgress").value = 45;
  const form = new FormData();
  form.append("upload", encrypted.blob, file.name);
  if (state.folderId !== null) form.append("folder_id", state.folderId);
  form.append("encrypted", "true");
  form.append("enc_alg", "AES-256-GCM");
  form.append("enc_salt_b64", encrypted.saltB64);
  form.append("enc_iv_b64", encrypted.ivB64);
  form.append("enc_kdf", "PBKDF2-HMAC-SHA256");
  form.append("enc_iterations", String(encrypted.iterations));
  form.append("original_sha256", encrypted.originalSha256);
  await api("/api/files", { method: "POST", body: form });
  $("uploadProgress").value = 100;
  $("fileInput").value = "";
  toast("Encrypted upload complete");
  await refreshItems();
}

async function downloadFile(id, files) {
  const file = files.find((item) => item.id === id);
  const passphrase = $("vaultPassphrase").value;
  if (!file) return;
  if (file.encrypted && passphrase.length < 8) return toast("Enter the encryption passphrase");
  const res = await fetch(`/api/files/${id}/download`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!res.ok) return toast("Download failed");
  const blob = await res.blob();
  const finalBlob = file.encrypted ? await decryptBlob(blob, file, passphrase) : blob;
  downloadBlob(finalBlob, file.name);
}

async function renameFile(id) {
  const name = prompt("New file name");
  if (!name) return;
  await api(`/api/files/${id}/rename`, { method: "PATCH", body: JSON.stringify({ name }) });
  await refreshItems();
}

async function moveFile(id) {
  const raw = prompt("Destination folder ID. Leave blank for Root.");
  if (raw === null) return;
  const folder_id = raw.trim() === "" ? null : Number(raw);
  if (folder_id !== null && Number.isNaN(folder_id)) return toast("Folder ID must be a number");
  await api(`/api/files/${id}/move`, { method: "PATCH", body: JSON.stringify({ folder_id }) });
  await refreshItems();
}

async function deleteFile(id) {
  if (!confirm("Delete this file and its Telegram chunks?")) return;
  await api(`/api/files/${id}`, { method: "DELETE" });
  await refreshItems();
}

async function renameFolder(id) {
  const name = prompt("New folder name");
  if (!name) return;
  await api(`/api/folders/${id}/rename`, { method: "PATCH", body: JSON.stringify({ name }) });
  await refreshItems();
}

async function deleteFolder(id) {
  if (!confirm("Delete this empty folder?")) return;
  await api(`/api/folders/${id}`, { method: "DELETE" });
  await refreshItems();
}

async function init() {
  const status = await api("/api/status");
  $("status").textContent = status.telegram_ready ? "Telegram configured" : "Telegram credentials missing";
  if (state.token && state.user) showApp();
  else showAuth();
}

$("loginMode").addEventListener("click", () => setAuthMode("login"));
$("registerMode").addEventListener("click", () => setAuthMode("register"));
$("authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      username: $("username").value,
      password: $("password").value,
    };
    const data = await api(`/api/auth/${state.mode}`, { method: "POST", body: JSON.stringify(payload) });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("televault_token", state.token);
    localStorage.setItem("televault_user", JSON.stringify(state.user));
    showApp();
  } catch (err) {
    toast(err.message);
  }
});
$("logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("televault_token");
  localStorage.removeItem("televault_user");
  state.token = null;
  state.user = null;
  showAuth();
});
$("rootBtn").addEventListener("click", () => {
  state.folderId = null;
  $("folderTitle").textContent = "Root";
  refreshItems().catch((err) => toast(err.message));
});
$("newFolderBtn").addEventListener("click", async () => {
  const name = prompt("Folder name");
  if (!name) return;
  try {
    await api("/api/folders", {
      method: "POST",
      body: JSON.stringify({ name, parent_id: state.folderId }),
    });
    await refreshItems();
  } catch (err) {
    toast(err.message);
  }
});
$("uploadBtn").addEventListener("click", () => uploadSelectedFile().catch((err) => toast(err.message)));
$("searchInput").addEventListener("input", (event) => {
  state.search = event.target.value.trim();
  refreshItems().catch((err) => toast(err.message));
});

init().catch((err) => {
  $("status").textContent = "Backend unavailable";
  toast(err.message);
});
