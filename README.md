# digital-locket

A personal file lockbox you keep on a USB. Encrypt your files and folders with a passphrase, store them in a vault, and shred the originals — then open them back anytime, on any machine, as long as you remember the passphrase.

## Why a "locket"?

It started as a way to lock files. Then the name clicked: a locket is something personal you carry close to you — a photo, a lock of hair, a secret. `digital-locket` is that idea for your files. It's your USB stick wearing a tiny vault: plug it in, open your browser, and your files are there — behind your passphrase, and only behind your passphrase.

No tech skills needed. No terminal. No "install Python" steps. FastAPI runs the whole thing — the web page you look at **and** the encryption engine behind it — in one app.

## How it feels to use

1. **First run** — open the app, set your passphrase. The vault is now yours.
2. **Add files or folders** — drag & drop them in (whole folders work), or pick files with the file chooser and folders with the **Choose a folder** button. They land in your **Locket Files** folder (on the USB, right next to the app) and wait there.
3. **Encrypt all** — one button. Everything in the folder is encrypted into the vault, and only after each item succeeds is the original securely shredded. The vault always ends up holding exactly what was in the folder at that moment.
4. **Later runs** — type your passphrase, see what's locked, and press **Open vault folder** to decrypt everything back into the Locket Files folder (Explorer opens right there). If the folder already has files, you're asked first and can choose to clear it so the freshly unloaded files always land.
5. **Done for the day?** Just close the tab. Your browser keeps you signed in while the app keeps running, and the session expires on its own — and any restart of the machine locks everything again, so it stays protected even if the stick is lost.

The top bar always shows the state of the locket: **Open** means the folder is your editable working area, **Locked** means everything is sealed in the vault. While locked, the app blocks new drops and pickers and keeps the vault list in front — the vault is the source of truth.

### Where your files live

```
USB root (E:\)
├── Locket Files\      ← your working files: dropped here, edited here, unloaded back here
└── digital-locket\    ← the app (you never need to open this)
    └── vaults\        ← the encrypted store
        ├── .owner.json   (ownership marker)
        ├── .index.json   (original file sizes for the list)
        ├── .state.json   (open / locked status)
        ├── <name>.enc            ← one encrypted file each
        └── folders\<name>.enc    ← one encrypted folder each
```

The Locket Files folder is your working area — you can even browse it directly on the USB, no UI needed. Files you place there by hand get locked on the next Encrypt all. While the locket is locked the vault wins: opening the vault folder asks first and can clear the folder so the decrypted files always come back fresh.

## How folders behave

- A dropped folder appears as **one item** — its top-most name. Nested files and subfolders are never listed individually.
- On **Encrypt all**, a folder is archived to a single encrypted blob, and the whole original folder is shredded.
- On **Open vault folder**, the folder is restored intact — contents and inner structure — and extracted atomically (a temp copy first, then moved into place), so a failed unload never leaves a half-written folder.
- Empty subfolders are preserved when you drag & drop (browsers that support it). If your browser can't drag folders in (Firefox), the app shows a note pointing you to the **Choose a folder** button.

## Security model

- Files are encrypted with **Fernet** (AES-128-CBC + HMAC), keyed from your passphrase via **Argon2id** — the same KDF the industry trusts.
- Every encrypt uses a fresh random salt, so the same file never encrypts to the same bytes twice.
- The passphrase is the only key. It's never stored on disk — it lives only in an in-memory TTL cache that dies with the app process. The owner marker is a decryption check, not a copy of your passphrase.
- Sessions ride on short-lived opaque tokens stored in **HttpOnly cookies**: a 5-minute access token and a 30-minute refresh token. When the access expires, the refresh silently rotates both — and once 30 minutes pass without activity, the app quietly denies entry with a strict `401` and asks for the passphrase again. A wrong passphrase is always rejected with `401`.
- Because the passphrase cache is in-memory only, any machine shutdown (or a different OS user) invalidates every session — a stolen USB + laptop stays locked.
- The server binds to `127.0.0.1` — localhost only. Nothing on your network can reach it.

## Running it (for developers)

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12).

```powershell
uv sync          # install dependencies
uv run python main.py
```

Open http://127.0.0.1:8000 in your browser.

### Commands

| Action | Command |
|---|---|
| Run the app | `uv run python main.py` |
| Run with auto-reload | `uv run uvicorn main:app --reload` |
| Lint | `uv run ruff check .` |

### Architecture notes

- **API** (`app/routers/vault.py`): `GET /api/state` (public), `POST /api/setup`, `POST /api/login` (sets HttpOnly session cookies), `POST /api/stage` (multipart files with sanitized relative paths + `dirs` for empty folders; blocked with `409` while locked), `POST /api/encrypt` (locks folder → vault, vault mirrors the folder), `GET /api/files` (`staged` + `locked`, each tagged `kind: file|folder`, plus `status`), `POST /api/unload?clean=true` (empties the folder first, decrypts, opens Explorer). Every route except `state`/`setup`/`login` requires a valid session.
- **Encrypt is always fresh**: re-encrypting overwrites any previous blob and removes stale ones whose file is gone from the folder — the vault is a mirror, never a cache of old versions. An empty folder is a no-op and never wipes the vault. Failed items stay in the folder, never shredded.
- **Auth** (`app/core/tokens.py`): in-memory LRU `TokenStore` — the only place the passphrase ever lives. Access 5 min, refresh 30 min, rotation on access expiry; tokens travel in HttpOnly `SameSite=Lax` cookies (`dl_access`/`dl_refresh`).
- **Status** (`vaults/.state.json`): `open` = editable working area, `locked` = everything sealed. `setup` and `unload` set `open`; a non-empty `encrypt` sets `locked`.
- **UI** (`app/static/`): plain vanilla JS, no build step. Reloads stay signed in while the process is alive; the topbar badge shows Open/Locked; while locked, drag & drop and pickers are blocked.

## The end goal: plug-and-play

The long-term plan is a USB "digital locket": Python and this app bundled onto the stick itself, auto-starting when you plug it in. No installation, no setup — your files follow you, protected by one thing you keep in your head. Windows-first for now; other platforms later.

## Current status

Working today: owner setup, passphrase login with expiring HttpOnly-cookie sessions, files **and folders** staging (drag & drop + picker), one-button fresh encryption with mirror cleanup, folder-aware file listing, clean-before-unload, and vault unload that opens Explorer. Not yet done: the USB auto-start packaging and hardened error handling.

## Tech stack

- **FastAPI** — API + serving the single-page UI
- **Argon2-cffi** + **cryptography (Fernet)** — key derivation and encryption
- **Vanilla HTML/CSS/JS** — the UI (no build step)
- **uv** — dependency management

> ⚠️ Encryption is destructive: locked files are overwritten with random data and deleted. Always test with copies of files you don't mind losing, not real data.