# digital-locket

A personal file lockbox you keep on a USB. Encrypt your files with a passphrase, store them in a vault, and shred the originals — then open them back anytime, on any machine, as long as you remember the passphrase.

## Why a "locket"?

It started as a way to lock files. Then the name clicked: a locket is something personal you carry close to you — a photo, a lock of hair, a secret. `digital-locket` is that idea for your files. It's your USB stick wearing a tiny vault: plug it in, open your browser, and your files are there — behind your passphrase, and only behind your passphrase.

No tech skills needed. No terminal. No "install Python" steps. FastAPI runs the whole thing — the web page you look at **and** the encryption engine behind it — in one app.

## How it feels to use

1. **First run** — open the app, set your passphrase. The vault is now yours.
2. **Drag & drop** — drop files in. They're encrypted on the spot and the originals are securely shredded.
3. **Later runs** — type your passphrase. See your files, preview or download them, drop in more.
4. Done for the day? Just close the tab. The session locks itself — if you stop touching the app, it signs you out on its own.

## Security model

- Files are encrypted with **Fernet** (AES-128-CBC + HMAC), keyed from your passphrase via **Argon2id** — the same KDF the industry trusts.
- Every file gets a fresh random salt, so the same file never encrypts to the same bytes twice.
- The passphrase is the only key. It's never stored — not in the vault, not in the config. The owner marker is a decryption check, not a copy of your passphrase.
- Access uses short-lived opaque tokens: 5-minute access + 30-minute refresh. If nothing touches the app, the session expires by itself.
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

## The end goal: plug-and-play

The long-term plan is a USB "digital locket": Python and this app bundled onto the stick itself, auto-starting when you plug it in. No installation, no setup — your files follow you, protected by one thing you keep in your head. Windows-first for now; other platforms later.

## Current status

Early stage. Working today: owner setup, passphrase login with expiring sessions, drag-and-drop encryption, file listing, and in-browser preview/download. Not yet done: the USB auto-start packaging and hardened error handling.

## Tech stack

- **FastAPI** — API + serving the single-page UI
- **Argon2-cffi** + **cryptography (Fernet)** — key derivation and encryption
- **Vanilla HTML/CSS/JS** — the UI (no build step)
- **uv** — dependency management

> ⚠️ Encryption is destructive: locked files are overwritten with random data and deleted. Always test with copies of files you don't mind losing, not real data.
