# Ultimate Tic-Tac-Toe Bot

Play **Ultimate Tic-Tac-Toe** in your terminal against a computer opponent.

- **You** are **X** (you go first)  
- The **bot** is **O**  
- You type moves; the bot answers  

Works on **Mac, Windows, or Linux** in any normal terminal that has **Python** (and **git** if you want easy updates).

You also need **matplotlib** (for the end-of-game chart). If it’s missing, the bot **stops and tells you exactly what to type** to install it.

---

## Quick start

```bash
git clone https://github.com/TheCodeWan/Ultimate-Tic-Tac-Toe-Bot.git
cd Ultimate-Tic-Tac-Toe-Bot
python3 -m pip install -r requirements.txt
python3 ultimate_ttt_bot.py
```

On Windows, if `python3` doesn’t work, try `python` instead.

If you forget matplotlib, you’ll see something like:

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

The big board is made up of **9 small boards**, laid out like this:

```text
1 2 3
4 5 6
7 8 9
```

Each small board also has **9 cells**, numbered the same way.

Type:

```text
BOARD-SPOT
```

Examples:

- `5-5` — middle of the middle board  
- `1-2` — top-left board, top-middle spot  
- `9-9` — bottom-right board, bottom-right spot  

Then press **Enter**.

Other commands while playing:

| You type | What happens |
|----------|----------------|
| `quit` | Stop the game |
| `update` or `u` | Download the latest version from git |
| **Ctrl+U** | Same as `update` (when the shortcut works in your terminal) |

---

## What the bot tells you

After **your** move:

- **Score out of 100** — how good that move was compared to your other legal options right then  
- Sometimes **“Best move would have been…”** if there was a better choice  

After the **bot** moves:

- **Win chance** — rough odds you’ll still win (plus draw / bot win). Tiny odds show as `<0.1%`.  

At the **end** of the game:

- A **chart** image of how those chances changed (needs matplotlib).  
  - Mac: opens in Preview after a few seconds  
  - Windows/Linux: open `utt_chances.png` yourself  

---

## Flags

You may optionally add flags at the end of the `python3 ultimate_ttt_bot.py` command  to modify certain settings like so:

```bash
python3 ultimate_ttt_bot.py --time 10
```

| Option | Meaning |
|--------|---------|
| `--time` | Bot thinks up to 10 seconds per move |
| `--win-sims` | Faster (less precise) win-chance estimates |
| `--seed` | Same “randomness” every run (for testing) |
| `--no-update-check` | Don’t check for updates when starting |
| `--version` | Print version number |

---

## Updates

You do **not** need a full git clone just to update the bot.

1. Each launch **checks GitHub** for a newer version of `ultimate_ttt_bot.py`.  
2. If one exists, the bot tells you.  
3. Type **`update`** (or **`u`**, or try **Ctrl+U**) to download the new script over the old one.  
4. **Quit and run the script again** so the new code loads.

That works for a single downloaded `.py` file **or** a full repo folder (needs internet).

If you use git for the whole project:

```bash
cd Ultimate-Tic-Tac-Toe-Bot
git pull
```

**Ctrl+U note:** In many terminals Ctrl+U normally clears the line. This program tries to reuse it for “update,” but if that doesn’t work, just type `update` and press Enter.

---

## Optional tools

- `utt_opening_search.py` — slow tool that scores all 81 opening moves (for curiosity, not needed to play)

---

## License

Personal and educational use. No warranty — the bot is strong but not perfect play.
