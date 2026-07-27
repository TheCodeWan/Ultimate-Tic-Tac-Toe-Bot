# Ultimate Tic-Tac-Toe Bot

A **terminal** Ultimate Tic-Tac-Toe opponent.

- **You** play **X** and go first  
- The **bot** plays **O** and searches for a strong reply  
- Moves use a simple `board-space` notation (the script does not draw a board — track it yourself)

Meant to be run in a normal developer terminal that already has tools like **Python 3** and (if you use git) **git** — e.g. **macOS Terminal**, **Windows Terminal** / PowerShell / cmd, or Linux.

**Version:** see `__version__` in `ultimate_ttt_bot.py` (currently **1.0.0**).

---

## Requirements

- A terminal / command prompt  
- **Python 3.10+** recommended (`python3 --version` or `python --version` on Windows)  
- Optional but recommended: **matplotlib** (end-of-game chance chart as a PNG)

```bash
cd ultimate-ttt-bot
python3 -m pip install -r requirements.txt
```

On some Windows setups the launcher is `python` instead of `python3`:

```bash
python -m pip install -r requirements.txt
```

---

## How to run

```bash
python3 ultimate_ttt_bot.py
```

(or `python ultimate_ttt_bot.py` on Windows if that’s what you use)

Useful flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--time` | `2.0` | Seconds the bot may think per move (uses as many MCTS sims as fit) |
| `--sims` | `0` | Optional hard cap on MCTS sims (`0` = unlimited, time only) |
| `--win-sims` | `5000` | Playouts for the win-chance estimate after the bot moves |
| `--seed` | none | RNG seed for reproducible random playouts / tie-breaks |
| `--chart` | `utt_chances` | Base path for the end-of-game chart (`utt_chances.png`, `.csv`) |

Examples:

```bash
# Think up to 10 seconds per bot move
python3 ultimate_ttt_bot.py --time 10

# Faster / noisier win estimates
python3 ultimate_ttt_bot.py --time 5 --win-sims 1000

# Reproducible session
python3 ultimate_ttt_bot.py --time 5 --seed 42
```

Type a move and press Enter. Type `quit` to stop early.

---

## Move notation

Boards and cells are numbered **1–9**, left → right, top → bottom:

```text
1 2 3
4 5 6
7 8 9
```

A move is:

```text
BOARD-SPACE
```

Examples:

| Move | Meaning |
|------|---------|
| `5-5` | Center of the **center** mini-board |
| `1-2` | Top-left mini-board, top-center cell |
| `9-9` | Bottom-right mini-board, bottom-right cell |

Also accepted: `5:5`, `5 5`, `5/5` (digits 1–9 only).

---

## How Ultimate Tic-Tac-Toe works

The big board is a **3×3 of mini tic-tac-toe boards** (9 local boards × 9 cells = 81 spots).

### Goal

1. Win a **local** board by getting three in a row in that mini-board (normal tic-tac-toe).  
2. Win the **game** by winning **three local boards in a row** on the big board.

### Forced board (the main rule)

- **First move:** X may play **anywhere**.  
- After that: the **cell** you play in decides which **local board** the opponent must use next.

Example: you play in the **bottom-right cell** of some mini-board → opponent must play in the **bottom-right local board** of the big board.

### Closed boards

If a local board is **already won** or **full** (draw), no more moves go there.

If you are sent to a closed board, you get a **free choice** of any still-open local board.

### Draws

If no one has three local boards in a row and nothing playable remains, the game is a **draw**.

### Strategy note

Winning many mini-boards does **not** guarantee a win. Only a **line of three local boards** wins. Sending the opponent (and free choices) often matters more than raw board count.

---

## What the bot prints

| Output | Meaning |
|--------|---------|
| `Your move score: 73/100 (rank …)` | How good **this** move was vs other **legal** moves right now (by simulated win rate). Uses about **5 seconds** of grading. |
| `Best move would have been: 5-5` | Shown only if your move was **not** best (or tied for best). |
| `Thinking...` | Bot is searching. |
| `bot move: 5-3` | Bot’s reply. |
| `Estimated win chance: 15.2% (draw …, O win …)` | Rough forecast for **you (X)** after the bot moved. Values between 0 and 0.1% show as `<0.1%`. |
| End-of-game chart | PNG of win/draw/bot chances over the game (if matplotlib is installed). |

**Move score** = quality of your choice among options.  
**Win chance** = how the whole match looks afterward.  
You can play a “best” move and still see win chance drop if the position is bad or the bot replies well.

### Charts (optional)

- Files are written next to where you run the script (e.g. `utt_chances.png`, `utt_chances.csv`).  
- On **macOS**, the PNG is opened in **Preview** after a short delay.  
- On **Windows / Linux**, open the PNG yourself in any image viewer (File Explorer, Photos, etc.).

---

## Install / update with git

First time:

```bash
git clone <repo-url>
cd ultimate-ttt-bot
python3 -m pip install -r requirements.txt
```

Later, get updates:

```bash
cd ultimate-ttt-bot
git pull
```

---

## Extra: opening analysis (optional)

`utt_opening_search.py` scores all 81 first moves with many playouts (slow; research tool, not needed to play).

```bash
python3 utt_opening_search.py
```

---

## License

Use and share freely for personal / educational play. No warranty — the bot’s estimates are approximations, not solved perfect play.
