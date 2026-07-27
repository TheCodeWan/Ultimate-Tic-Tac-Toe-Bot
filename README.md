# Ultimate Tic-Tac-Toe Bot

Play **Ultimate Tic-Tac-Toe** in your terminal against a computer.

- **You** are **X** (you go first)  
- The **bot** is **O**  
- You type moves; the bot answers  

Works on **Mac, Windows, or Linux** in a normal terminal that has **Python**.  
**Git** is optional (only if you want `git clone` / `git pull`).

You also need:

- **matplotlib** — end-of-game chart (required; bot exits with install instructions if missing)  
- **rich** — prettier colored terminal text (recommended; falls back to plain text if missing)

---

## Quick start

```bash
git clone https://github.com/TheCodeWan/Ultimate-Tic-Tac-Toe-Bot.git
cd Ultimate-Tic-Tac-Toe-Bot
python3 -m pip install -r requirements.txt
python3 ultimate_ttt_bot.py
```

On Windows, if `python3` doesn’t work, try `python` instead.

If matplotlib is missing, you’ll see something like:

```text
python3 -m pip install matplotlib
```

(Use the command the bot prints — it matches the Python you’re running.)

---

## How the game works (simple)

Imagine normal tic-tac-toe, but **each square is itself a full tic-tac-toe board**.

1. Win a **small board** by getting 3-in-a-row inside it.  
2. Win the **whole game** by winning **3 small boards in a row** on the big board.

### The important rule

Wherever you play **inside** a small board sends your opponent to that **matching** small board on the big grid.

Example: you play in the **bottom-right cell** of any small board → they must play in the **bottom-right small board**.

If that board is already finished, they may play **anywhere** still open.

**Tip:** Having more small boards than the bot does **not** always mean you’re winning. Only a **line of three small boards** wins the game.

---

## How to type a move

You’ll see a prompt like:

```text
X move: 
```

The big board is **9 small boards**, numbered like this:

```text
1 2 3
4 5 6
7 8 9
```

Each small board has **9 cells**, numbered the same way.

Type:

```text
BOARD-SPOT
```

Examples:

- `5-5` — middle of the middle board  
- `1-2` — top-left board, top-middle cell  
- `9-9` — bottom-right board, bottom-right cell  

Then press **Enter**.

---

## Keyboard shortcuts

These work **while the `X move:` prompt is waiting** (the bot reads keys directly, like a small terminal app):

| Shortcut | What it does |
|----------|----------------|
| **Ctrl+U** | Download the latest bot script from GitHub |
| **Ctrl+B** | Undo your last move **and** the bot’s reply |
| **Ctrl+Q** | Quit |

There are no typed commands like `quit` or `update` — use the shortcuts.

Run the bot in a normal terminal (Terminal.app, iTerm, Windows Terminal, etc.). Some apps that wrap the terminal may steal Ctrl keys.

---

## What the bot tells you

After **your** move:

- **Score out of 100** — how good that move was vs your other legal options right then (about 5 seconds of grading)  
- Sometimes **“Best move would have been…”** if there was a better choice  

After the **bot** moves:

- **`Bot move: 5-3`** (example)  
- **Win chance** — rough odds you’ll still win (plus draw / bot win). Values under 0.1% show as `<0.1%`.  

At the **end** of the game:

- A **chart** of how those chances changed (`utt_chances.png`)  
  - **Mac:** opens in Preview after a few seconds  
  - **Windows / Linux:** open the PNG yourself  

**Move score** = quality of this choice.  
**Win chance** = how the whole game looks.  
You can play a great move and still see win chance drop if the position is tough or the bot answers well.

---

## Optional flags

```bash
python3 ultimate_ttt_bot.py --time 10
```

| Flag | Meaning |
|------|---------|
| `--time 10` | Bot may think up to 10 seconds per move |
| `--win-sims 1000` | Fewer sims → faster, noisier win-chance estimates |
| `--seed 42` | Same randomness every run (for testing) |
| `--no-update-check` | Don’t check GitHub for updates on startup |
| `--chart NAME` | Base name for the chart files |
| `--version` | Print version number |

---

## Updates

**Ctrl+U downloads the whole repository**, not just one file.

1. On startup the bot checks GitHub for a newer version.  
2. If one exists, it tells you.  
3. Press **Ctrl+U**:
   - If this folder is a **git clone** → `git pull`  
   - Otherwise → downloads the full project **zip** from GitHub and overwrites files here  
4. Press **Ctrl+Q**, then run the script again so the new code loads.

Needs internet.

You can still update manually with git:

```bash
cd Ultimate-Tic-Tac-Toe-Bot
git pull
```

---

## Optional tools

- `utt_opening_search.py` — slow tool that scores all 81 opening moves (curiosity only; not needed to play)

---

## License

Personal and educational use. No warranty — the bot is strong but not perfect play.
