# Download janitor

Downloads turns into a junk drawer. This sits in the Windows tray and files things away:

`Downloads/2026-10/pdf`, `.../images`, `.../zips`, `.../video`, `.../audio`, `.../docs`, `.../other`

It waits until a file looks finished (not `.crdownload`, not touched in the last couple minutes) so Chrome can finish saving first.

## Undo / “what did it do?”

Every move is logged.

- Tray → **What it did (last run)** — a text file: old path → new path
- Tray → **Undo last run** — moves those files back, but only if they’re still where the janitor put them
- Full history: `moves.jsonl` next to the script (not uploaded)

Nothing is deleted. Worst case you undo.

## Run

```
copy config.example.json config.json
START.bat
```

`downloads` in config can stay empty (uses your user Downloads folder).

Tray: ON/OFF, **Start with Windows**, run once, last run, undo, quit.

Python 3 + `pip install -r requirements.txt`.
