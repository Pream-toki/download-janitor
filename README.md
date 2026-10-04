# Download janitor

Sorts finished files in Downloads into month + type folders, e.g. `Downloads\2026-10\pdf`.

It **moves** files. It does not delete them.

## Setup (once)

1. Python 3 on PATH.
2. `copy config.example.json config.json` (or just run `START.bat`; it will create config).
3. Leave `"downloads": ""` to use your normal Downloads folder. Only change that if you really mean another folder.
4. Double-click `START.bat`. Blue folder icon in the tray.

## Use, carefully

- Leave it **ON** and it waits ~2 minutes after a download finishes, then files it.
- **Run once now** skips the wait — don’t click that while a big file is still saving.
- **What it did (last run)** — read this before you panic. Old path → new path.
- **Undo last run** — puts that batch back, but only if the files are still where the janitor put them. If you already moved them by hand, undo can’t guess.
- Full history: `moves.jsonl` (local, not on GitHub).
- **Start with Windows** is optional. Uncheck it if you don’t want night sorting.

If the first run sorted more than you wanted: **Undo last run** once, then turn **Janitor OFF** until you’re ready.
