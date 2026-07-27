#!/usr/bin/env python3
"""
Exhaustive opening analysis: score every legal first move by playout win rate.
No per-move budget cap — same sims for each of the 81 cells.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

from ultimate_ttt_bot import State, estimate_x_win_chance, format_move

SIMS_PER_MOVE = 20_000
SEED = 42
WORKERS = 4


def eval_move(args):
    board, cell, sims, seed = args
    rng = random.Random(seed + board * 9 + cell + 17)
    s = State.new()
    s.apply(board, cell)
    p_win, p_draw, p_loss = estimate_x_win_chance(s, rng, n_sims=sims)
    return (board, cell, p_win, p_draw, p_loss)


def cell_kind(i: int) -> str:
    if i == 4:
        return "center"
    if i in (0, 2, 6, 8):
        return "corner"
    return "edge"


def main() -> None:
    s0 = State.new()
    moves = s0.legal_moves()
    assert len(moves) == 81
    print(f"Evaluating {len(moves)} opening moves × {SIMS_PER_MOVE} playouts each")
    print(f"Total playouts: {len(moves) * SIMS_PER_MOVE:,}")
    print(f"Workers: {WORKERS}, seed base: {SEED}")
    t0 = time.perf_counter()

    tasks = [(b, c, SIMS_PER_MOVE, SEED) for b, c in moves]
    results = []
    done = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(eval_move, t) for t in tasks]
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 9 == 0 or done == len(tasks):
                elapsed = time.perf_counter() - t0
                print(f"  {done}/{len(tasks)} done ({elapsed:.1f}s)", flush=True)

    results.sort(key=lambda r: (r[2], r[3]), reverse=True)
    elapsed = time.perf_counter() - t0

    print()
    print(f"Finished in {elapsed:.1f}s")
    print()
    print("Top 15 openings (by estimated X win rate after first move, O to play):")
    print(f"{'rank':>4}  {'move':>5}  {'X win%':>8}  {'draw%':>8}  {'O win%':>8}")
    for i, (b, c, pw, pd, pl) in enumerate(results[:15], 1):
        print(
            f"{i:4d}  {format_move(b, c):>5}  "
            f"{100 * pw:7.2f}%  {100 * pd:7.2f}%  {100 * pl:7.2f}%"
        )

    print()
    print("Bottom 10 openings:")
    print(f"{'rank':>4}  {'move':>5}  {'X win%':>8}  {'draw%':>8}  {'O win%':>8}")
    start_rank = len(results) - 9
    for i, (b, c, pw, pd, pl) in enumerate(results[-10:], start_rank):
        print(
            f"{i:4d}  {format_move(b, c):>5}  "
            f"{100 * pw:7.2f}%  {100 * pd:7.2f}%  {100 * pl:7.2f}%"
        )

    best_pw = results[0][2]
    bests = [r for r in results if r[2] >= best_pw - 0.005]
    print()
    print(f"Best win rate: {100 * best_pw:.2f}%")
    print(f"Moves within 0.5% of best ({len(bests)}):")
    for b, c, pw, pd, pl in bests:
        print(
            f"  {format_move(b, c)}  X={100 * pw:.2f}%  D={100 * pd:.2f}%  "
            f"O={100 * pl:.2f}%  (board={cell_kind(b)}, cell={cell_kind(c)})"
        )

    by_cell: dict = defaultdict(list)
    by_board: dict = defaultdict(list)
    for b, c, pw, pd, pl in results:
        by_cell[c].append(pw)
        by_board[b].append(pw)

    print()
    print("Average X win% by local cell (1-9 layout):")
    for c in range(9):
        avg = sum(by_cell[c]) / len(by_cell[c])
        print(f"  cell {c + 1}: {100 * avg:.2f}%")
    print("Average X win% by local board (1-9):")
    for b in range(9):
        avg = sum(by_board[b]) / len(by_board[b])
        print(f"  board {b + 1}: {100 * avg:.2f}%")

    out = "/Users/eliascalderon/utt_opening_analysis.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"sims_per_move={SIMS_PER_MOVE} seed={SEED} elapsed_s={elapsed:.1f}\n")
        f.write("rank,move,board,cell,x_win,draw,o_win\n")
        for i, (b, c, pw, pd, pl) in enumerate(results, 1):
            f.write(
                f"{i},{format_move(b, c)},{b + 1},{c + 1},"
                f"{pw:.6f},{pd:.6f},{pl:.6f}\n"
            )
    print()
    print(f"Full ranking saved to {out}")


if __name__ == "__main__":
    main()
