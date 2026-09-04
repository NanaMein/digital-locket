"use strict";

const $ = (id) => document.getElementById(id);

let currentStatus = "open";
let currentStagedCount = 0;

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
const folderInput = $("folder-input");
const folderButton = $("folder-button");
const dragNote = $("drag-note");
const stagedBody = $("staged-body");
const stagedTable = $("staged-table");
const stagedNote = $("staged-note");
const lockedNote = $("locked-note");
const fileBody = $("file-body");
const fileTable = $("file-table");
const emptyNote = $("empty-note");
const statusBadge = $("status-badge");
const encryptButton = $("encrypt-button");
const unloadButton = $("unload-button");
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

function folderDropSupported() {
  return typeof DataTransferItem !== "undefined" && "webkitGetAsEntry" in DataTransferItem.prototype;
}

function readDir(entry, files, emptyDirs) {
  return new Promise((resolve) => {
    const reader = entry.createReader();
    const readBatch = () => new Promise((res) => reader.readEntries(res, () => res([])));
    (async () => {
      const children = [];
      let batch;
      do {
        batch = await readBatch();
        children.push(...batch);
      } while (batch.length);
      let hadFile = false;
      for (const child of children) {
        if (child.isFile) {
          const file = await new Promise((res) => child.file(res, () => res(null)));
          if (file) {
            files.push({ path: child.fullPath.replace(/^\//, ""), file });
            hadFile = true;
          }
        } else if (child.isDirectory) {
          const sub = await readDir(child, files, emptyDirs);
          if (sub) hadFile = true;
        }
      }
      if (!hadFile) emptyDirs.push(entry.fullPath.replace(/^\//, ""));
      resolve(hadFile);
    })();
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, { ...options });
  if (res.status === 401 && !path.endsWith("/api/login")) {
    showGate(false);
    throw new Error("Session expired");
  }
  return res;
}

function renderStatus(status) {
  currentStatus = status === "locked" ? "locked" : "open";
  statusBadge.textContent = currentStatus === "locked" ? "Locked" : "Open";
  statusBadge.className = "badge " + currentStatus;
  dropZone.classList.toggle("locked", currentStatus === "locked");
  lockedNote.classList.toggle("hidden", currentStatus !== "locked");
  folderButton.disabled = currentStatus === "locked";
}

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  if (!data.owned) {
    showGate(true);
    return;
  }
  try {
    const filesRes = await api("/api/files");
    if (!filesRes.ok) {
      showGate(false);
      return;
    }
    enterApp(await filesRes.json());
  } catch (err) {
    showGate(false);
  }
}

function showGate(showSetup) {
  gateScreen.classList.remove("hidden");
  appScreen.classList.add("hidden");
  nameLabel.classList.toggle("hidden", !showSetup);
  nameField.classList.toggle("hidden", !showSetup);
  gateButton.textContent = showSetup ? "Create my locket" : "Open my locket";
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
    passField.value = "";
    enterApp();
  } catch (err) {
    gateError.textContent = err.message;
    gateError.classList.remove("hidden");
  }
}

function enterApp(files) {
  gateScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  if (files) renderStatus(files.status);
  loadFiles();
}

function fillTable(tbody, rows) {
  tbody.textContent = "";
  for (const f of rows) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = f.kind === "folder" ? f.name + "/" : f.name;
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

  renderStatus(data.status);
  currentStagedCount = data.staged.length;

  const hasStaged = data.staged.length > 0;
  stagedNote.classList.toggle("hidden", hasStaged);
  stagedTable.classList.toggle("hidden", !hasStaged);
  fillTable(stagedBody, data.staged);
  encryptButton.disabled = !hasStaged;

  const hasLocked = data.locked.length > 0;
  emptyNote.classList.toggle("hidden", hasLocked);
  fileTable.classList.toggle("hidden", !hasLocked);
  fillTable(fileBody, data.locked);
  unloadButton.disabled = !hasLocked;
}

async function stageFiles(files, emptyDirs) {
  if (!files.length && !emptyDirs.length) return;
  if (currentStatus === "locked") {
    toast("The locket is locked — open it first to add files.");
    return;
  }
  const form = new FormData();
  for (const { path, file } of files) form.append("files", file, path);
  for (const dir of emptyDirs) form.append("dirs", dir);
  const res = await api("/api/stage", { method: "POST", body: form });
  if (!res.ok) {
    let msg = "Could not add those files.";
    try { const body = await res.json(); if (body.detail) msg = body.detail; } catch (err) { /* ignore */ }
    toast(msg);
    return;
  }
  const data = await res.json();
  const count = data.staged.length + data.dirs.length;
  toast(`Added ${count} item${count > 1 ? "s" : ""} to Locket Files. Press Encrypt all when ready.`);
  loadFiles();
}

async function encryptAll() {
  const res = await api("/api/encrypt", { method: "POST" });
  if (!res.ok) return;
  const data = await res.json();
  const lockedMsg = data.locked.length
    ? `Locked ${data.locked.length} file${data.locked.length > 1 ? "s" : ""}.`
    : "Nothing to lock.";
  const failedMsg = data.failed.length
    ? ` Could not lock ${data.failed.length} (left in folder).`
    : "";
  toast(lockedMsg + failedMsg);
  loadFiles();
}

async function unloadAll() {
  let clean = false;
  if (currentStagedCount > 0) {
    if (!confirm("The Locket Files folder isn't empty. Clear it and replace it with the vault contents?")) {
      return;
    }
    clean = true;
  }
  const url = clean ? "/api/unload?clean=true" : "/api/unload";
  const res = await api(url, { method: "POST" });
  if (!res.ok) return;
  const data = await res.json();
  toast(data.unloaded
    ? `Unlocked ${data.unloaded} file${data.unloaded > 1 ? "s" : ""} and opened the folder.`
    : "Nothing to unlock yet.");
  loadFiles();
}

dropZone.addEventListener("click", () => {
  if (currentStatus === "locked") {
    toast("The locket is locked — open it first.");
    return;
  }
  fileInput.click();
});
dropZone.addEventListener("dragover", (e) => {
  if (currentStatus === "locked") return;
  e.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", async (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragging");
  if (currentStatus === "locked") {
    toast("The locket is locked — open it first.");
    return;
  }
  const files = [];
  const emptyDirs = [];
  const items = e.dataTransfer.items;
  if (items && items.length && typeof items[0].webkitGetAsEntry === "function") {
    for (const item of items) {
      const entry = item.webkitGetAsEntry();
      if (!entry) continue;
      if (entry.isFile) {
        const f = await new Promise((res) => entry.file(res, () => res(null)));
        if (f) files.push({ path: entry.fullPath.replace(/^\//, ""), file: f });
      } else if (entry.isDirectory) {
        await readDir(entry, files, emptyDirs);
      }
    }
  } else {
    for (const f of e.dataTransfer.files) {
      const rel = f.webkitRelativePath || f.name;
      if (f.webkitRelativePath && !rel.includes("/")) continue;
      files.push({ path: rel, file: f });
    }
  }
  await stageFiles(files, emptyDirs);
});
fileInput.addEventListener("change", () => {
  const files = [];
  for (const f of fileInput.files) files.push({ path: f.name, file: f });
  stageFiles(files, []);
  fileInput.value = "";
});
folderInput.addEventListener("change", () => {
  const files = [];
  for (const f of folderInput.files) {
    const rel = f.webkitRelativePath;
    if (!rel || !rel.includes("/")) continue;
    files.push({ path: rel, file: f });
  }
  stageFiles(files, []);
  folderInput.value = "";
});
folderButton.addEventListener("click", () => {
  if (currentStatus === "locked") {
    toast("The locket is locked — open it first.");
    return;
  }
  folderInput.click();
});

encryptButton.addEventListener("click", encryptAll);
unloadButton.addEventListener("click", unloadAll);
gateForm.addEventListener("submit", handleGateSubmit);

if (!folderDropSupported()) dragNote.classList.remove("hidden");

loadState();