"use strict";

const $ = (id) => document.getElementById(id);

let accessToken = null;
let refreshToken = null;
let ownerName = null;

const gateScreen = $("gate-screen");
const appScreen = $("app-screen");
const gateForm = $("gate-form");
const gateButton = $("gate-button");
const gateError = $("gate-error");
const nameLabel = $("name-label");
const nameField = $("name-field");
const passField = $("pass-field");
const dropZone = $("drop-zone");
const fileInput = $("file-input");
const stagedBody = $("staged-body");
const stagedTable = $("staged-table");
const stagedNote = $("staged-note");
const fileBody = $("file-body");
const fileTable = $("file-table");
const emptyNote = $("empty-note");
const toastEl = $("toast");

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.remove("hidden");
  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(() => toastEl.classList.add("hidden"), 3500);
}

function formatSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
  return bytes + " B";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set("Authorization", "Bearer " + accessToken);
  const res = await fetch(path, { ...options, headers });
  const xAccess = res.headers.get("X-Access-Token");
  if (xAccess) {
    accessToken = xAccess;
    refreshToken = res.headers.get("X-Refresh-Token");
  }
  if (res.status === 401 && !path.endsWith("/api/login")) {
    showGate(false);
    throw new Error("Session expired");
  }
  return res;
}

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  showGate(!data.owned);
}

function showGate(showSetup) {
  gateScreen.classList.remove("hidden");
  appScreen.classList.add("hidden");
  nameLabel.classList.toggle("hidden", !showSetup);
  nameField.classList.toggle("hidden", !showSetup);
  gateButton.textContent = showSetup ? "Create my locket" : "Open my locket";
  ownerName = showSetup ? null : "owner";
}

async function handleGateSubmit(e) {
  e.preventDefault();
  gateError.classList.add("hidden");
  const isSetup = !nameField.classList.contains("hidden");
  const passphrase = passField.value;
  if (!passphrase) return;

  try {
    if (isSetup) {
      const res = await fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameField.value || null, passphrase }),
      });
      if (res.status === 409) {
        gateError.textContent = "This locket already belongs to someone.";
        gateError.classList.remove("hidden");
        return;
      }
    }
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    });
    if (res.status === 401) {
      gateError.textContent = "That passphrase isn't right. Try again.";
      gateError.classList.remove("hidden");
      return;
    }
    const data = await res.json();
    accessToken = data.access_token;
    refreshToken = data.refresh_token;
    passField.value = "";
    enterApp();
  } catch (err) {
    gateError.textContent = err.message;
    gateError.classList.remove("hidden");
  }
}

function enterApp() {
  gateScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  loadFiles();
}

function fillTable(tbody, rows) {
  tbody.textContent = "";
  for (const f of rows) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = f.name;
    const sizeCell = document.createElement("td");
    sizeCell.textContent = formatSize(f.size);
    row.append(nameCell, sizeCell);
    tbody.appendChild(row);
  }
}

async function loadFiles() {
  const res = await api("/api/files");
  if (!res.ok) return;
  const data = await res.json();

  const hasStaged = data.staged.length > 0;
  stagedNote.classList.toggle("hidden", hasStaged);
  stagedTable.classList.toggle("hidden", !hasStaged);
  fillTable(stagedBody, data.staged);

  const hasLocked = data.locked.length > 0;
  emptyNote.classList.toggle("hidden", hasLocked);
  fileTable.classList.toggle("hidden", !hasLocked);
  fillTable(fileBody, data.locked);
}

async function stageFiles(fileList) {
  if (!fileList.length) return;
  const form = new FormData();
  for (const file of fileList) form.append("files", file, file.name);
  const res = await api("/api/stage", { method: "POST", body: form });
  if (!res.ok) {
    toast("Could not add those files.");
    return;
  }
  const data = await res.json();
  toast(`Added ${data.staged.length} file${data.staged.length > 1 ? "s" : ""} to Locket Files. Press Encrypt all when ready.`);
  loadFiles();
}

async function encryptAll() {
  const res = await api("/api/encrypt", { method: "POST" });
  if (!res.ok) return;
  const data = await res.json();
  const lockedMsg = data.locked.length
    ? `Locked ${data.locked.length} file${data.locked.length > 1 ? "s" : ""}.`
    : "Nothing to lock.";
  const skippedMsg = data.skipped.length
    ? ` Skipped ${data.skipped.length} (already in the locket).`
    : "";
  toast(lockedMsg + skippedMsg);
  loadFiles();
}

async function unloadAll() {
  const res = await api("/api/unload", { method: "POST" });
  if (!res.ok) return;
  const data = await res.json();
  toast(data.unloaded
    ? `Unlocked ${data.unloaded} file${data.unloaded > 1 ? "s" : ""} and opened the folder.`
    : "Nothing to unlock yet.");
}

function logout() {
  accessToken = null;
  refreshToken = null;
  showGate(false);
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragging");
  stageFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => {
  stageFiles(fileInput.files);
  fileInput.value = "";
});

$("encrypt-button").addEventListener("click", encryptAll);
$("unload-button").addEventListener("click", unloadAll);
$("logout-button").addEventListener("click", logout);
gateForm.addEventListener("submit", handleGateSubmit);

loadState();