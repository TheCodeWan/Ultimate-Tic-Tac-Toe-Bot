#!/usr/bin/env python3
"""
Ultimate Tic-Tac-Toe bot.

You are X (first). The bot is O and replies with its strongest move.

Move format: BOARD-SPACE  (e.g. 1-2)
  Boards and spaces numbered 1–9, left-to-right, top-to-bottom:

    1 2 3
    4 5 6
    7 8 9
"""

from __future__ import annotations

import argparse
import io
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

__version__ = "1.5.3"

# Returned by read_player_line() for hotkeys (not move text)
_CMD_UPDATE = "__cmd_update__"
_CMD_UNDO = "__cmd_undo__"
_CMD_QUIT = "__cmd_quit__"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# GitHub repo used for update checks / git pull (private or public)
GITHUB_OWNER = "TheCodeWan"
GITHUB_REPO = "Ultimate-Tic-Tac-Toe-Bot"
GITHUB_BRANCH = "main"

X, O, EMPTY = 1, -1, 0
PLAYER_NAMES = {X: "X", O: "O"}

# 0-based win lines on a 3x3
LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

# Prefer center and corners slightly in playouts / ordering
CELL_WEIGHT = (3, 2, 3, 2, 4, 2, 3, 2, 3)
BOARD_WEIGHT = (3, 2, 3, 2, 4, 2, 3, 2, 3)

MOVE_RE = re.compile(r"^\s*([1-9])\s*[-:,/\s]\s*([1-9])\s*$")


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

@dataclass
class State:
    """
    boards: 9 local boards, each a list of 9 cells (X/O/EMPTY)
    winners: local-board outcome (X, O, or EMPTY if unfinished; EMPTY also if draw)
    drawn: True if that local board is full with no winner
    active: forced local board index 0–8, or None for free choice
    to_move: X or O
    """

    boards: List[List[int]]
    winners: List[int]
    drawn: List[bool]
    active: Optional[int]
    to_move: int

    @staticmethod
    def new() -> "State":
        return State(
            boards=[[EMPTY] * 9 for _ in range(9)],
            winners=[EMPTY] * 9,
            drawn=[False] * 9,
            active=None,  # first move free
            to_move=X,
        )

    def clone(self) -> "State":
        return State(
            boards=[b[:] for b in self.boards],
            winners=self.winners[:],
            drawn=self.drawn[:],
            active=self.active,
            to_move=self.to_move,
        )

    def local_closed(self, b: int) -> bool:
        return self.winners[b] != EMPTY or self.drawn[b]

    def legal_moves(self) -> List[Tuple[int, int]]:
        """Return list of (board, cell) 0-based legal moves."""
        moves: List[Tuple[int, int]] = []
        if self.active is not None and not self.local_closed(self.active):
            b = self.active
            board = self.boards[b]
            for c in range(9):
                if board[c] == EMPTY:
                    moves.append((b, c))
            return moves

        # Free choice: any open cell on any open board
        for b in range(9):
            if self.local_closed(b):
                continue
            board = self.boards[b]
            for c in range(9):
                if board[c] == EMPTY:
                    moves.append((b, c))
        return moves

    def apply(self, board: int, cell: int) -> None:
        """Apply move in place. Assumes legality."""
        player = self.to_move
        self.boards[board][cell] = player

        # Check local win / draw
        if _line_winner(self.boards[board]) == player:
            self.winners[board] = player
        elif all(v != EMPTY for v in self.boards[board]):
            self.drawn[board] = True

        # Next forced board is the cell index; free if closed
        nxt = cell
        self.active = None if self.local_closed(nxt) else nxt
        self.to_move = -player

    def global_winner(self) -> Optional[int]:
        """X, O, or None if game still open; EMPTY-ish draw handled separately."""
        w = _line_winner_from_slots(self.winners)
        if w != EMPTY:
            return w
        return None

    def is_terminal(self) -> bool:
        if self.global_winner() is not None:
            return True
        # No legal moves left → draw
        return not self.legal_moves()

    def outcome(self) -> int:
        """From X's perspective: +1 X win, -1 O win, 0 draw. Terminal only."""
        g = self.global_winner()
        if g is not None:
            return g  # X=1, O=-1
        return 0


def _line_winner(cells: List[int]) -> int:
    for a, b, c in LINES:
        v = cells[a]
        if v != EMPTY and v == cells[b] == cells[c]:
            return v
    return EMPTY


def _line_winner_from_slots(slots: List[int]) -> int:
    """Like _line_winner but drawn boards count as neither (EMPTY)."""
    return _line_winner(slots)


# ---------------------------------------------------------------------------
# Evaluation (for ordered playouts / leaf heuristics)
# ---------------------------------------------------------------------------

def evaluate(state: State) -> float:
    """
    Heuristic score from X's perspective (positive favors X).
    Used to bias rollouts and order moves; MCTS still drives the decision.
    """
    g = state.global_winner()
    if g is not None:
        return 1e6 * g
    if not state.legal_moves():
        return 0.0

    score = 0.0

    # Local board ownership
    for b in range(9):
        w = state.winners[b]
        if w != EMPTY:
            score += 25.0 * BOARD_WEIGHT[b] * w
        else:
            score += _local_shape(state.boards[b]) * BOARD_WEIGHT[b]

    # Global two-in-a-rows / threats using claimed boards
    score += 40.0 * _meta_shape(state.winners)

    # Slight preference: not giving free move to opponent if we can help it
    # (captured implicitly by search; small terminal-mobility term)
    n = len(state.legal_moves())
    if state.to_move == X:
        score += 0.02 * n
    else:
        score -= 0.02 * n

    return score


def _local_shape(cells: List[int]) -> float:
    """Soft score for unfinished local board."""
    s = 0.0
    for a, b, c in LINES:
        line = (cells[a], cells[b], cells[c])
        xs = line.count(X)
        os = line.count(O)
        empties = line.count(EMPTY)
        if xs and os:
            continue
        if xs == 2 and empties == 1:
            s += 3.0
        elif xs == 1 and empties == 2:
            s += 0.4
        if os == 2 and empties == 1:
            s -= 3.0
        elif os == 1 and empties == 2:
            s -= 0.4
    # Cell occupancy
    for i, v in enumerate(cells):
        if v != EMPTY:
            s += 0.15 * CELL_WEIGHT[i] * v
    return s


def _meta_shape(winners: List[int]) -> float:
    s = 0.0
    for a, b, c in LINES:
        line = (winners[a], winners[b], winners[c])
        xs = line.count(X)
        os = line.count(O)
        empties = 3 - xs - os
        if xs and os:
            continue
        if xs == 2 and empties == 1:
            s += 8.0
        elif xs == 1 and empties == 2:
            s += 1.0
        if os == 2 and empties == 1:
            s -= 8.0
        elif os == 1 and empties == 2:
            s -= 1.0
    return s


def strategic_evaluate(state: State) -> float:
    """
    Richer X-perspective score for ranking human moves.
    Emphasizes global structure, threats, send/tempo — not raw mark count.
    """
    g = state.global_winner()
    if g is not None:
        return 1e6 * g
    if not state.legal_moves():
        return 0.0

    score = 0.0

    # --- Global board ownership (only boards that sit on lines matter more) ---
    for b in range(9):
        w = state.winners[b]
        if w != EMPTY:
            score += 30.0 * BOARD_WEIGHT[b] * w

    # --- Global threats / line potential (main "who's winning" signal) ---
    x_threats = 0
    o_threats = 0
    for a, b, c in LINES:
        line = (state.winners[a], state.winners[b], state.winners[c])
        xs = line.count(X)
        os = line.count(O)
        empties = 3 - xs - os
        if xs and os:
            continue
        if xs == 2 and empties == 1:
            x_threats += 1
            score += 120.0  # huge: one move from winning the game
        elif xs == 1 and empties == 2:
            score += 14.0 * BOARD_WEIGHT[[a, b, c][line.index(X)]]
        elif xs == 0 and empties == 3:
            pass
        if os == 2 and empties == 1:
            o_threats += 1
            score -= 120.0
        elif os == 1 and empties == 2:
            score -= 14.0 * BOARD_WEIGHT[[a, b, c][line.index(O)]]

    # Multiple simultaneous threats are especially strong
    if x_threats >= 2:
        score += 80.0
    if o_threats >= 2:
        score -= 80.0

    # --- Local fights on unfinished boards ---
    for b in range(9):
        if state.local_closed(b):
            continue
        local = _local_shape(state.boards[b])
        # Weight by whether this board sits on a contested global line
        line_bonus = 1.0
        for a, mid, c in LINES:
            if b not in (a, mid, c):
                continue
            owners = [state.winners[a], state.winners[mid], state.winners[c]]
            if O not in owners or X not in owners:
                # open global line that still can be pure for someone
                if owners.count(EMPTY) >= 1:
                    line_bonus = 1.6
                    break
        score += local * BOARD_WEIGHT[b] * line_bonus

    # --- Tempo / free choice (side to move has options) ---
    # After a move, state.to_move is the opponent.
    n = len(state.legal_moves())
    if state.active is None:
        # Free choice for the player about to move
        if state.to_move == O:
            score -= 18.0  # you just gave O a free choice
        else:
            score += 18.0
    else:
        # Forced board: fewer replies can be good if the board is bad for them
        if state.to_move == O:
            score -= 0.15 * n  # O has many comfortable replies
        else:
            score += 0.15 * n

    # --- Key global cells still open (center / corners more valuable to contest) ---
    for b in range(9):
        if state.winners[b] != EMPTY or state.drawn[b]:
            continue
        # slight preference for having more presence on important boards
        presence = sum(1 for v in state.boards[b] if v == X) - sum(
            1 for v in state.boards[b] if v == O
        )
        score += 0.8 * BOARD_WEIGHT[b] * presence

    return score


def estimate_x_win_chance(
    state: State,
    rng: random.Random,
    n_sims: int = 1500,
) -> Tuple[float, float, float]:
    """
    Estimate outcome probabilities for X from `state` via heuristic playouts.

    Returns (p_x_win, p_draw, p_o_win) in [0, 1], summing to ~1.
    Draws are separate — "win chance" is pure P(X wins), not win+½draw.
    """
    g = state.global_winner()
    if g == X:
        return 1.0, 0.0, 0.0
    if g == O:
        return 0.0, 0.0, 1.0
    if state.is_terminal():
        return 0.0, 1.0, 0.0

    n_sims = max(1, n_sims)
    x_wins = draws = o_wins = 0
    for _ in range(n_sims):
        outcome = _playout(state.clone(), rng)
        if outcome > 0:
            x_wins += 1
        elif outcome < 0:
            o_wins += 1
        else:
            draws += 1

    total = float(n_sims)
    return x_wins / total, draws / total, o_wins / total


# Wall-clock budget for grading all legal moves (user: up to exactly 5s is fine)
MOVE_SCORE_TIME = 5.0


def rank_player_move(
    state: State,
    chosen: Tuple[int, int],
    rng: random.Random,
    score_time: float = MOVE_SCORE_TIME,
) -> Tuple[int, int, int, List[Tuple[int, int]], bool]:
    """
    Rank `chosen` among all legal moves by simulated win rate.

    Uses a fixed wall-clock budget (default 5.0s) split across every legal
    move via round-robin playouts — so grading takes about that long whether
    there are 3 options or 81 (opening).

    Returns
    -------
    score_1_to_100
        1 = worst legal move, 100 = best (by estimated P(X wins)).
    rank_1_worst_to_n_best
    n_legal
    best_moves
        All moves tied for the best sim win rate (board, cell) 0-based.
    chose_best
        True if ``chosen`` is among ``best_moves``.
    """
    legal = state.legal_moves()
    n = len(legal)
    if n == 0:
        return 1, 1, 0, [], False
    if chosen not in legal:
        raise ValueError("chosen move is not legal")

    if n == 1:
        return 100, 1, 1, [chosen], True

    # Post-move states + outcome tallies (x_wins, draws, o_wins, sims)
    post: List[State] = []
    tallies: List[List[int]] = []
    for m in legal:
        s = state.clone()
        s.apply(*m)
        post.append(s)
        # Instant terminal outcomes: no need to sim further for that move
        g = s.global_winner()
        if g == X:
            tallies.append([1, 0, 0, 1])  # 100% X
        elif g == O:
            tallies.append([0, 0, 1, 1])
        elif s.is_terminal():
            tallies.append([0, 1, 0, 1])  # draw
        else:
            tallies.append([0, 0, 0, 0])

    deadline = time.perf_counter() + max(0.05, score_time)
    # Round-robin so every move gets a fair share of the full time budget
    idx = 0
    sim_indices = [i for i in range(n) if not post[i].is_terminal()]
    if not sim_indices:
        sim_indices = list(range(n))

    while time.perf_counter() < deadline:
        i = sim_indices[idx % len(sim_indices)]
        idx += 1
        outcome = _playout(post[i].clone(), rng)
        if outcome > 0:
            tallies[i][0] += 1
        elif outcome < 0:
            tallies[i][2] += 1
        else:
            tallies[i][1] += 1
        tallies[i][3] += 1

    def rates(i: int) -> Tuple[float, float]:
        xw, dr, ow, sims = tallies[i]
        if sims <= 0:
            return 0.0, 0.0
        return xw / sims, dr / sims

    scored: List[Tuple[Tuple[float, float], Tuple[int, int]]] = [
        (rates(i), legal[i]) for i in range(n)
    ]
    # Ascending: worst first → rank 1; best last → rank n
    scored.sort(key=lambda t: (t[0][0], t[0][1]))

    best_key = scored[-1][0]
    best_moves = [m for key, m in scored if key == best_key]
    chose_best = chosen in best_moves

    ranks: dict = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scored[j + 1][0] == scored[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[scored[k][1]] = avg_rank
        i = j + 1

    rank = ranks[chosen]
    score_100 = int(round(1 + 99 * (rank - 1) / (n - 1)))
    score_100 = max(1, min(100, score_100))
    rank_display = int(round(rank))
    return score_100, rank_display, n, best_moves, chose_best


# ---------------------------------------------------------------------------
# Move ordering helper
# ---------------------------------------------------------------------------

def order_moves(state: State, moves: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Heuristic sort: immediate wins first, then blocks, then center-ish."""
    if len(moves) <= 1:
        return moves

    def key(m: Tuple[int, int]) -> Tuple[int, int, int]:
        b, c = m
        # Immediate local win
        state.boards[b][c] = state.to_move
        won = _line_winner(state.boards[b]) == state.to_move
        state.boards[b][c] = EMPTY
        # Immediate global win after claiming local
        global_win = 0
        if won:
            prev = state.winners[b]
            state.winners[b] = state.to_move
            if state.global_winner() == state.to_move:
                global_win = 1
            state.winners[b] = prev
        return (
            -global_win,
            -int(won),
            -(BOARD_WEIGHT[b] + CELL_WEIGHT[c]),
        )

    return sorted(moves, key=key)


# ---------------------------------------------------------------------------
# Monte Carlo Tree Search
# ---------------------------------------------------------------------------

class Node:
    __slots__ = ("state", "parent", "move", "children", "untried", "wins", "visits")

    def __init__(
        self,
        state: State,
        parent: Optional["Node"] = None,
        move: Optional[Tuple[int, int]] = None,
    ):
        self.state = state
        self.parent = parent
        self.move = move
        self.children: List[Node] = []
        self.untried = order_moves(state, state.legal_moves())
        self.wins = 0.0  # from root player's perspective? use absolute X-perspective
        self.visits = 0

    def fully_expanded(self) -> bool:
        return not self.untried

    def best_child(self, c: float = 1.4) -> "Node":
        # UCB1; score stored from X's perspective → convert for side to move at parent
        # Parent just moved TO this child, so child.state.to_move is opponent.
        # We store outcome from X's view; maximizer is always the player about to move
        # at the parent when choosing among children.
        parent_player = self.state.to_move  # player who will move from this node

        def ucb(ch: Node) -> float:
            if ch.visits == 0:
                return float("inf")
            # Mean score from X view in [-1, 1]
            mean_x = ch.wins / ch.visits
            # Value for the player to move at parent
            mean = mean_x if parent_player == X else -mean_x
            return mean + c * math.sqrt(math.log(self.visits) / ch.visits)

        return max(self.children, key=ucb)


def mcts_best_move(
    root_state: State,
    time_limit: float,
    rng: random.Random,
    max_sims: Optional[int] = None,
) -> Tuple[int, int]:
    """Return best (board, cell) for the side to move.

    Runs simulations until ``time_limit`` seconds elapse, or until
    ``max_sims`` is reached if that is set (optional hard cap).
    """
    root = Node(root_state.clone())
    moves = root.untried
    if not moves:
        raise RuntimeError("No legal moves")
    if len(moves) == 1:
        return moves[0]

    # Instant tactical: take a global win if available (shuffle if several)
    instant_wins = []
    for b, c in moves:
        s = root_state.clone()
        s.apply(b, c)
        if s.global_winner() == root_state.to_move:
            instant_wins.append((b, c))
    if instant_wins:
        rng.shuffle(instant_wins)
        return instant_wins[0]

    deadline = time.perf_counter() + time_limit
    sims = 0
    root_player = root_state.to_move

    while time.perf_counter() < deadline:
        if max_sims is not None and sims >= max_sims:
            break
        node = root
        state = root_state.clone()

        # Selection
        while node.fully_expanded() and node.children and not state.is_terminal():
            node = node.best_child()
            assert node.move is not None
            state.apply(*node.move)

        # Expansion
        if not state.is_terminal() and node.untried:
            b, c = node.untried.pop(0)
            state.apply(b, c)
            child = Node(state.clone(), parent=node, move=(b, c))
            node.children.append(child)
            node = child

        # Simulation (biased random playout)
        outcome = _playout(state, rng)

        # Backprop: outcome from X's perspective in {-1, 0, 1}
        while node is not None:
            node.visits += 1
            node.wins += outcome
            node = node.parent
        sims += 1

    # Pick most visited child; break ties by mean score, then shuffle equals
    def pick_key(ch: Node) -> Tuple[int, float]:
        mean_x = ch.wins / ch.visits if ch.visits else 0.0
        mean = mean_x if root_player == X else -mean_x
        return (ch.visits, mean)

    best_key = max(pick_key(ch) for ch in root.children)
    tied = [ch for ch in root.children if pick_key(ch) == best_key]
    rng.shuffle(tied)
    best = tied[0]
    assert best.move is not None
    return best.move


def _playout(state: State, rng: random.Random) -> int:
    """Play to end with light heuristic bias; return outcome from X view."""
    # Cap playout length (shouldn't exceed 81)
    for _ in range(81):
        if state.is_terminal():
            return state.outcome()
        moves = state.legal_moves()
        if not moves:
            return 0

        # Fast check: any move that wins the global game?
        chosen: Optional[Tuple[int, int]] = None
        player = state.to_move
        for b, c in moves:
            state.boards[b][c] = player
            local_won = _line_winner(state.boards[b]) == player
            state.boards[b][c] = EMPTY
            if local_won:
                prev = state.winners[b]
                state.winners[b] = player
                gw = state.global_winner()
                state.winners[b] = prev
                if gw == player:
                    chosen = (b, c)
                    break
        if chosen is None:
            # Prefer local wins, then weighted random
            local_wins: List[Tuple[int, int]] = []
            for b, c in moves:
                state.boards[b][c] = player
                if _line_winner(state.boards[b]) == player:
                    local_wins.append((b, c))
                state.boards[b][c] = EMPTY
            pool = local_wins if local_wins else moves
            weights = [BOARD_WEIGHT[b] + CELL_WEIGHT[c] for b, c in pool]
            chosen = rng.choices(pool, weights=weights, k=1)[0]

        state.apply(*chosen)

    return state.outcome() if state.is_terminal() else 0


# ---------------------------------------------------------------------------
# Exhaustive alpha-beta for late game (exact best move)
# ---------------------------------------------------------------------------

def alphabeta_best(
    state: State,
    depth: int,
    time_limit: float,
    rng: random.Random,
) -> Optional[Tuple[int, int]]:
    """Negamax alpha-beta for late-game positions."""
    moves = state.legal_moves()
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]

    deadline = time.perf_counter() + time_limit
    best_move = moves[0]

    def negamax(st: State, d: int, alpha: float, beta: float) -> float:
        if time.perf_counter() > deadline:
            raise TimeoutError
        g = st.global_winner()
        if g is not None:
            return 1e5 if g == st.to_move else -1e5
        legals = st.legal_moves()
        if not legals:
            return 0.0
        if d == 0:
            ev = evaluate(st)
            return ev if st.to_move == X else -ev

        value = -1e18
        for b, c in order_moves(st, legals):
            child = st.clone()
            child.apply(b, c)
            score = -negamax(child, d - 1, -beta, -alpha)
            if score > value:
                value = score
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value

    try:
        best_score = -1e18
        best_moves: List[Tuple[int, int]] = []
        for b, c in order_moves(state, moves):
            child = state.clone()
            child.apply(b, c)
            score = -negamax(child, depth - 1, -1e18, 1e18)
            if score > best_score:
                best_score = score
                best_moves = [(b, c)]
            elif score == best_score:
                best_moves.append((b, c))
        rng.shuffle(best_moves)
        return best_moves[0]
    except TimeoutError:
        return best_move


def choose_move(
    state: State,
    time_limit: float,
    rng: random.Random,
    max_sims: Optional[int] = None,
) -> Tuple[int, int]:
    moves = state.legal_moves()
    if not moves:
        raise RuntimeError("No legal moves")
    if len(moves) == 1:
        return moves[0]

    # Instant win (shuffle if several)
    instant_wins = []
    for b, c in moves:
        s = state.clone()
        s.apply(b, c)
        if s.global_winner() == state.to_move:
            instant_wins.append((b, c))
    if instant_wins:
        rng.shuffle(instant_wins)
        return instant_wins[0]

    # Late game: few empty cells → exact-ish alphabeta
    empty = sum(
        1
        for b in range(9)
        if not state.local_closed(b)
        for v in state.boards[b]
        if v == EMPTY
    )
    if empty <= 12:
        ab = alphabeta_best(
            state, depth=min(12, empty), time_limit=time_limit, rng=rng
        )
        if ab is not None:
            return ab

    return mcts_best_move(
        state, time_limit=time_limit, rng=rng, max_sims=max_sims
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def parse_move(text: str) -> Optional[Tuple[int, int]]:
    m = MOVE_RE.match(text)
    if not m:
        return None
    board = int(m.group(1)) - 1
    cell = int(m.group(2)) - 1
    return board, cell


def format_move(board: int, cell: int) -> str:
    return f"{board + 1}-{cell + 1}"


def _script_path() -> str:
    return os.path.abspath(__file__)


def _script_dir() -> str:
    return os.path.dirname(_script_path())


def _raw_bot_url() -> str:
    return (
        f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/ultimate_ttt_bot.py"
    )


def _fetch_remote_bot_source_err(
    timeout: float = 20.0,
) -> Tuple[Optional[str], str]:
    """Download latest ultimate_ttt_bot.py from GitHub. Returns (text, error)."""
    url = _raw_bot_url()
    errors: List[str] = []

    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"ultimate-ttt-bot/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8"), ""
    except Exception as exc:
        errors.append(f"urllib: {exc}")

    # curl often works when macOS Python is missing SSL certificates
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(int(timeout)), url],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if proc.returncode == 0 and proc.stdout and "__version__" in proc.stdout:
            return proc.stdout, ""
        errors.append(
            f"curl: {(proc.stderr or '').strip() or f'exit {proc.returncode}'}"
        )
    except Exception as exc:
        errors.append(f"curl: {exc}")

    return None, "; ".join(errors)


def _parse_version(source: str) -> Optional[str]:
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', source)
    return m.group(1) if m else None


def _version_key(v: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for bit in re.split(r"[^\d]+", v):
        if bit.isdigit():
            parts.append(int(bit))
    return tuple(parts) if parts else (0,)


def check_for_updates(quiet: bool = False) -> Optional[bool]:
    """
    Compare local __version__ to the bot file on GitHub.

    Does **not** require a git clone — only network access.
    Returns True if update available, False if up to date, None if unknown.
    """
    remote_src, err = _fetch_remote_bot_source_err()
    if remote_src is None:
        if not quiet:
            emit(
                f"Update check: could not reach GitHub ({err or 'unknown error'}).",
                file=sys.stderr,
            )
        return None

    remote_ver = _parse_version(remote_src)
    if not remote_ver:
        if not quiet:
            emit("Update check: could not read remote version.", file=sys.stderr)
        return None

    if _version_key(remote_ver) > _version_key(__version__):
        emit(
            f"Update available: you have v{__version__}, latest is v{remote_ver}.",
            file=sys.stderr,
        )
        emit("Press Ctrl+U to download the update.", file=sys.stderr)
        return True

    if not quiet:
        emit(f"Up to date (v{__version__}).", file=sys.stderr)
    return False


def _zip_url() -> str:
    return (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/"
        f"{GITHUB_BRANCH}.zip"
    )


def _download_bytes(url: str, timeout: float = 60.0) -> Tuple[Optional[bytes], str]:
    """Download URL to bytes (urllib, then curl)."""
    errors: List[str] = []
    try:
        import urllib.request

        req = urllib.request.Request(
            url, headers={"User-Agent": f"ultimate-ttt-bot/{__version__}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), ""
    except Exception as exc:
        errors.append(f"urllib: {exc}")
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(int(timeout)), url],
            capture_output=True,
            timeout=timeout + 5,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout, ""
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        errors.append(f"curl: {err or f'exit {proc.returncode}'}")
    except Exception as exc:
        errors.append(f"curl: {exc}")
    return None, "; ".join(errors)


def _install_repo_from_zip(dest_dir: str) -> Tuple[bool, str]:
    """
    Download the full GitHub repo zip and copy its files into dest_dir.
    Returns (ok, message).
    """
    data, err = _download_bytes(_zip_url(), timeout=90.0)
    if data is None:
        return False, err or "download failed"

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not names:
                return False, "empty zip"
            # GitHub zips are rooted at Repo-branch/...
            root_prefix = names[0].split("/")[0] + "/"
            with tempfile.TemporaryDirectory() as tmp:
                zf.extractall(tmp)
                src_root = os.path.join(tmp, root_prefix.rstrip("/"))
                if not os.path.isdir(src_root):
                    # Fallback: first directory under tmp
                    subs = [
                        os.path.join(tmp, n)
                        for n in os.listdir(tmp)
                        if os.path.isdir(os.path.join(tmp, n))
                    ]
                    if not subs:
                        return False, "could not find extracted project folder"
                    src_root = subs[0]

                # Copy all files from repo into dest (overwrite)
                for dirpath, _dirnames, filenames in os.walk(src_root):
                    rel = os.path.relpath(dirpath, src_root)
                    # Skip nested .git from zip (there usually isn't one)
                    if rel == ".git" or rel.startswith(".git" + os.sep):
                        continue
                    target_dir = dest_dir if rel == "." else os.path.join(dest_dir, rel)
                    os.makedirs(target_dir, exist_ok=True)
                    for name in filenames:
                        if name in {".DS_Store"}:
                            continue
                        shutil.copy2(
                            os.path.join(dirpath, name),
                            os.path.join(target_dir, name),
                        )
        return True, dest_dir
    except Exception as exc:
        return False, str(exc)


def apply_update() -> bool:
    """
    Download the **whole repository** (not just this script).

    - If this folder is a git clone: ``git pull``.
    - Otherwise: download the GitHub zip of main and overwrite project files
      in this script's directory.

    Restart the program after a successful update.
    """
    dest = _script_dir()

    if _is_git_checkout():
        emit("Updating full repository (git pull)...", style="cyan")
        code, _, err = _run_git(
            ["fetch", "--quiet", "origin", GITHUB_BRANCH], timeout=60.0
        )
        if code != 0:
            emit(
                f"git fetch failed ({err or 'error'}). Trying zip download instead...",
                file=sys.stderr,
                style="yellow",
            )
        else:
            code, out, err = _run_git(
                ["pull", "--ff-only", "origin", GITHUB_BRANCH], timeout=60.0
            )
            if code == 0:
                if out:
                    emit(out, style="dim")
                emit(f"Repository updated in:", style="green")
                emit(f"  {dest}", style="green")
                emit(
                    "Press Ctrl+Q to quit, then run the script again to use the new version.",
                    style="bold",
                )
                return True
            emit(
                f"git pull failed ({err or out or 'error'}). Trying zip download instead...",
                file=sys.stderr,
                style="yellow",
            )

    emit("Downloading full repository from GitHub...", style="cyan")
    ok, msg = _install_repo_from_zip(dest)
    if not ok:
        emit(f"Update failed: {msg}", file=sys.stderr, style="bold red")
        return False

    # Report new version if we can read it from the replaced file
    new_ver = "?"
    try:
        with open(_script_path(), encoding="utf-8") as f:
            new_ver = _parse_version(f.read()) or "?"
    except Exception:
        pass

    emit(f"Full repo installed (bot v{new_ver}):", style="green")
    emit(f"  {dest}", style="green")
    emit(
        "Press Ctrl+Q to quit, then run the script again to use the new version.",
        style="bold",
    )
    return True


def _run_git(args: List[str], timeout: float = 15.0) -> Tuple[int, str, str]:
    """Run a git command in the script directory. Returns (code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_script_dir(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", "git timed out"
    except Exception as exc:
        return 1, "", str(exc)


def _is_git_checkout() -> bool:
    code, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"], timeout=5.0)
    return code == 0 and out == "true"


# Optional Rich console (prettier output). Falls back to plain print.
_rich_stdout = None  # Console | False | None (uninitialized)
_rich_stderr = None


def _rich_console(stderr: bool = False):
    """Lazy-load Rich Console; False means 'tried and unavailable'."""
    global _rich_stdout, _rich_stderr
    if stderr:
        if _rich_stderr is None:
            try:
                from rich.console import Console

                _rich_stderr = Console(stderr=True, highlight=False)
            except Exception:
                _rich_stderr = False
        return _rich_stderr if _rich_stderr is not False else None
    if _rich_stdout is None:
        try:
            from rich.console import Console

            _rich_stdout = Console(highlight=False)
        except Exception:
            _rich_stdout = False
    return _rich_stdout if _rich_stdout is not False else None


def emit(*args, file=None, style: Optional[str] = None, **kwargs) -> None:
    """Print a message, then a blank line (extra spacing in the terminal)."""
    if file is None:
        file = sys.stdout
    text = " ".join(str(a) for a in args) if args else ""
    use_stderr = file in (sys.stderr,)
    console = _rich_console(stderr=use_stderr)
    if console is not None and file in (sys.stdout, sys.stderr):
        if style:
            console.print(text, style=style)
        else:
            console.print(text)
        console.print()
        return
    kwargs.setdefault("flush", True)
    print(text, file=file, **kwargs)
    print(file=file, flush=True)


def emit_title(title: str, subtitle: str = "", file=None) -> None:
    """
    Print a larger-looking title line, then a blank line.

    Uses VT100 double-height characters (supported by many terminals including
    macOS Terminal and iTerm2). Falls back to bold bright text if needed.
    """
    if file is None:
        file = sys.stderr
    # Bold bright cyan; double-height top half (#3) + bottom half (#4)
    # Plain text only in the double-height lines (no Rich markup).
    main = title if not subtitle else f"{title}  {subtitle}"
    # \033#3 = double-height top, \033#4 = double-height bottom
    top = f"\033[1;96m\033#3{main}\033[0m\n"
    bot = f"\033[1;96m\033#4{main}\033[0m\n"
    try:
        file.write(top)
        file.write(bot)
        file.write("\n")
        file.flush()
    except Exception:
        emit(f"[bold bright_cyan]{main}[/]", file=file)


def _read_player_line_unix() -> str:
    """
    Read one line of input in near-raw terminal mode (macOS / Linux).

    Same idea as full-screen TUIs (Grok Build, kilo editor, etc.): disable
    canonical/line editing so Ctrl+letter arrives as a single byte we can
    handle immediately, instead of being eaten by the shell/readline.

      Ctrl+U (\\x15) → update
      Ctrl+B (\\x02) → undo
      Ctrl+Q (\\x11) → quit
      Enter          → submit the typed move
      Backspace      → edit the buffer
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf: List[str] = []
    try:
        # cbreak: char-at-a-time, no line buffering; keep Ctrl+C as interrupt
        tty.setcbreak(fd)
        # Also disable software flow control so Ctrl+Q is not XON/XOFF
        new = termios.tcgetattr(fd)
        new[0] = new[0] & ~(termios.IXON | termios.IXOFF | termios.IXANY)
        # Disable ISIG if we want Ctrl+C raw too — keep ISIG so Ctrl+C still works
        termios.tcsetattr(fd, termios.TCSADRAIN, new)

        # Bold golden-yellow prompt + typed text (ANSI; works in raw mode)
        # Truecolor gold ≈ #FFC107; falls back fine on most modern terminals
        GOLD = "\033[1;38;2;255;193;7m"
        RESET = "\033[0m"
        sys.stdout.write(f"{GOLD}X move: ")
        sys.stdout.flush()

        while True:
            ch = sys.stdin.read(1)
            if not ch:
                sys.stdout.write(RESET)
                sys.stdout.flush()
                return _CMD_QUIT

            code = ord(ch)

            # Hotkeys (control characters)
            # End the input line, then leave a blank line before the next message
            if code == 0x15:  # Ctrl+U
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
                return _CMD_UPDATE
            if code == 0x02:  # Ctrl+B
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
                return _CMD_UNDO
            if code == 0x11:  # Ctrl+Q
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
                return _CMD_QUIT
            if code == 0x03:  # Ctrl+C
                sys.stdout.write(RESET)
                sys.stdout.flush()
                raise KeyboardInterrupt
            if code == 0x04 and not buf:  # Ctrl+D on empty line → quit
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
                return _CMD_QUIT

            # Enter — newline ends the typed move, blank line before next output
            if ch in ("\n", "\r"):
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
                return "".join(buf)

            # Backspace / Delete
            if code in (0x7F, 0x08):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            # Ignore other control chars
            if code < 32:
                continue

            # Printable (stay bold gold)
            buf.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()
    finally:
        sys.stdout.write("\033[0m")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_player_line_windows() -> str:
    """Character-at-a-time input on Windows (msvcrt)."""
    import msvcrt  # type: ignore

    buf: List[str] = []
    GOLD, RESET = "\033[1;38;2;255;193;7m", "\033[0m"
    sys.stdout.write(f"{GOLD}X move: ")
    sys.stdout.flush()
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            # Function/arrow key prefix — discard the next code
            msvcrt.getwch()
            continue
        code = ord(ch)
        if code == 0x15:  # Ctrl+U
            sys.stdout.write(f"{RESET}\n\n")
            sys.stdout.flush()
            return _CMD_UPDATE
        if code == 0x02:  # Ctrl+B
            sys.stdout.write(f"{RESET}\n\n")
            sys.stdout.flush()
            return _CMD_UNDO
        if code == 0x11:  # Ctrl+Q
            sys.stdout.write(f"{RESET}\n\n")
            sys.stdout.flush()
            return _CMD_QUIT
        if code == 0x03:
            sys.stdout.write(RESET)
            sys.stdout.flush()
            raise KeyboardInterrupt
        if ch in ("\r", "\n"):
            sys.stdout.write(f"{RESET}\n\n")
            sys.stdout.flush()
            return "".join(buf)
        if code in (0x08, 0x7F):
            if buf:
                buf.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if code < 32:
            continue
        buf.append(ch)
        sys.stdout.write(ch)
        sys.stdout.flush()


def read_player_line() -> str:
    """
    Read a move or hotkey. Prefer raw terminal mode so Ctrl shortcuts work
    (readline bindings are unreliable / fight the shell).
    """
    if not sys.stdin.isatty():
        # Piped input / non-interactive: fall back to normal line read
        line = sys.stdin.readline()
        if line == "":
            return _CMD_QUIT
        return line.rstrip("\n\r")

    if sys.platform == "win32":
        try:
            return _read_player_line_windows()
        except Exception:
            return input().rstrip("\n\r")

    try:
        return _read_player_line_unix()
    except Exception:
        # Last resort
        return input().rstrip("\n\r")


def format_pct(p: float) -> str:
    """
    Format a probability in [0, 1] for display.

    - one decimal place normally (e.g. 15.2%)
    - if 0 < p < 0.1%, show "<0.1%" (not 0.0%)
    - true zero stays "0.0%"
    """
    if p <= 0.0:
        return "0.0%"
    if p < 0.001:  # less than 0.1%
        return "<0.1%"
    if p >= 1.0:
        return "100.0%"
    return f"{100.0 * p:.1f}%"


def _record_chances(
    history: List[Dict[str, float]],
    p_win: float,
    p_draw: float,
    p_loss: float,
) -> None:
    """Append one sample after a full exchange (bot has moved)."""
    history.append(
        {
            "turn": float(len(history) + 1),
            "x_win": float(p_win),
            "draw": float(p_draw),
            "o_win": float(p_loss),
        }
    )


def save_chance_chart(
    history: List[Dict[str, float]],
    path_base: str,
    title: str = "Estimated outcome chances over the game",
    subtitle: str = "",
) -> List[str]:
    """
    Write chart files for the chance history.

    Primary output is a matplotlib PNG (opens cleanly in Preview).
    Also writes CSV. SVG only as fallback if matplotlib is missing.

    Returns list of created file paths.
    """
    if not history:
        return []

    created: List[str] = []
    base = path_base
    if base.endswith(".png") or base.endswith(".svg") or base.endswith(".csv"):
        base = base.rsplit(".", 1)[0]

    csv_path = base + ".csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("turn,x_win_pct,draw_pct,o_win_pct\n")
        for row in history:
            f.write(
                f"{int(row['turn'])},"
                f"{100.0 * row['x_win']:.2f},"
                f"{100.0 * row['draw']:.2f},"
                f"{100.0 * row['o_win']:.2f}\n"
            )
    created.append(csv_path)

    png_path = base + ".png"
    if _write_chance_png(history, png_path, title=title, subtitle=subtitle):
        created.append(png_path)
    else:
        # Fallback only if matplotlib isn't available
        svg_path = base + ".svg"
        _write_chance_svg(history, svg_path, title=title, subtitle=subtitle)
        created.append(svg_path)
        print(
            "Note: matplotlib not found; wrote SVG fallback. "
            "Install with:  python3 -m pip install matplotlib",
            file=sys.stderr,
        )

    return created


def _write_chance_svg(
    history: List[Dict[str, float]],
    path: str,
    title: str,
    subtitle: str = "",
) -> None:
    """SVG fallback with non-overlapping title + legend layout."""
    w, h = 960, 580
    ml, mr, mt, mb = 72, 36, 88, 64
    plot_w = w - ml - mr
    plot_h = h - mt - mb
    xs = [row["turn"] for row in history]
    x_min, x_max = min(xs), max(xs)
    if x_max <= x_min:
        x_max = x_min + 1.0

    def sx(turn: float) -> float:
        return ml + (turn - x_min) / (x_max - x_min) * plot_w

    def sy(pct: float) -> float:
        return mt + (1.0 - pct) * plot_h

    def poly(key: str) -> str:
        return " ".join(
            f"{sx(row['turn']):.1f},{sy(row[key]):.1f}" for row in history
        )

    grid = []
    for g in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(g)
        grid.append(
            f'<line x1="{ml}" y1="{y:.1f}" x2="{w - mr}" y2="{y:.1f}" '
            f'stroke="#e0e0e0" stroke-width="1"/>'
            f'<text x="{ml - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="system-ui,sans-serif" font-size="12" fill="#555">'
            f"{int(g * 100)}%</text>"
        )

    xticks = []
    step = 1 if len(history) <= 20 else max(1, len(history) // 12)
    for row in history:
        t = int(row["turn"])
        if t == 1 or t == int(x_max) or t % step == 0:
            xticks.append(
                f'<text x="{sx(float(t)):.1f}" y="{h - mb + 22}" '
                f'text-anchor="middle" font-family="system-ui,sans-serif" '
                f'font-size="11" fill="#555">{t}</text>'
            )

    full_title = title if not subtitle else f"{title} — {subtitle}"
    # Title on its own row; legend on the next row (no overlap)
    header = (
        f'<text x="{w / 2:.0f}" y="28" text-anchor="middle" '
        f'font-family="system-ui,sans-serif" font-size="17" font-weight="600" '
        f'fill="#111">{_xml_escape(full_title)}</text>'
        f'<line x1="{ml}" y1="48" x2="{ml + 28}" y2="48" stroke="#1f77b4" stroke-width="3"/>'
        f'<text x="{ml + 34}" y="52" font-family="system-ui,sans-serif" font-size="13" fill="#222">You (X) win</text>'
        f'<line x1="{ml + 160}" y1="48" x2="{ml + 188}" y2="48" stroke="#2ca02c" stroke-width="3"/>'
        f'<text x="{ml + 194}" y="52" font-family="system-ui,sans-serif" font-size="13" fill="#222">Draw</text>'
        f'<line x1="{ml + 280}" y1="48" x2="{ml + 308}" y2="48" stroke="#d62728" stroke-width="3"/>'
        f'<text x="{ml + 314}" y="52" font-family="system-ui,sans-serif" font-size="13" fill="#222">Bot (O) win</text>'
    )

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="#fafafa"/>
  {header}
  <rect x="{ml}" y="{mt}" width="{plot_w}" height="{plot_h}" fill="#fff" stroke="#ccc"/>
  {"".join(grid)}
  <polyline fill="none" stroke="#1f77b4" stroke-width="2.5" points="{poly("x_win")}"/>
  <polyline fill="none" stroke="#2ca02c" stroke-width="2.5" points="{poly("draw")}"/>
  <polyline fill="none" stroke="#d62728" stroke-width="2.5" points="{poly("o_win")}"/>
  {"".join(xticks)}
  <text x="{w / 2:.0f}" y="{h - 16}" text-anchor="middle"
        font-family="system-ui,sans-serif" font-size="13" fill="#333">After bot move #</text>
  <text x="20" y="{mt + plot_h / 2:.0f}" text-anchor="middle"
        font-family="system-ui,sans-serif" font-size="13" fill="#333"
        transform="rotate(-90 20 {mt + plot_h / 2:.0f})">Estimated chance</text>
</svg>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_chance_png(
    history: List[Dict[str, float]],
    path: str,
    title: str,
    subtitle: str = "",
) -> bool:
    """matplotlib PNG for Preview. Returns True if written."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    turns = [row["turn"] for row in history]
    x_win = [100.0 * row["x_win"] for row in history]
    draw = [100.0 * row["draw"] for row in history]
    o_win = [100.0 * row["o_win"] for row in history]

    # Wider figure when there are many moves so every x-label stays readable
    n = max(1, len(turns))
    fig_w = max(12.0, 0.45 * n + 3.0)
    fig, ax = plt.subplots(figsize=(fig_w, 7.0))

    # Clean lines only (no per-point dots).
    # Thickness: blue (you) > red (bot) > green (draw).
    # Draw order: thicker first (behind), thinner last (in front) so overlaps stay visible.
    ax.plot(
        turns,
        x_win,
        color="#1f77b4",
        linestyle="-",
        linewidth=5.0,
        marker=None,
        antialiased=True,
        label="You (X) win",
        zorder=1,
        solid_capstyle="round",
        solid_joinstyle="round",
    )
    ax.plot(
        turns,
        o_win,
        color="#d62728",
        linestyle="-",
        linewidth=4.0,
        marker=None,
        antialiased=True,
        label="Bot (O) win",
        zorder=2,
        solid_capstyle="round",
        solid_joinstyle="round",
    )
    ax.plot(
        turns,
        draw,
        color="#2ca02c",
        linestyle="-",
        linewidth=3.0,
        marker=None,
        antialiased=True,
        label="Draw",
        zorder=3,
        solid_capstyle="round",
        solid_joinstyle="round",
    )

    # Light pad past 0% / 100% so edge lines aren't clipped (~1.3% each side)
    ax.set_ylim(-1.3, 101.3)
    ax.set_xlim(min(turns) - 0.4, max(turns) + 0.4)
    ax.set_xlabel("After bot move #", fontsize=12)
    ax.set_ylabel("Estimated chance (%)", fontsize=12)

    if subtitle:
        ax.set_title(f"{title}\n{subtitle}", fontsize=14, fontweight="bold", pad=12)
    else:
        ax.set_title(title, fontsize=15, fontweight="bold", pad=12)

    # X: label every bot move (no skipping)
    ax.set_xticks(turns)
    ax.set_xticklabels([str(int(t)) for t in turns], fontsize=9)

    # Y: major labels every 10%; minor grid every 0.1% (tenth of a percent)
    import numpy as np

    ax.set_yticks(np.arange(0, 100.0 + 1e-9, 10.0))
    ax.set_yticklabels([f"{int(v)}" for v in np.arange(0, 100.0 + 1e-9, 10.0)])
    ax.set_yticks(np.arange(0, 100.0 + 1e-9, 0.1), minor=True)

    # Keep plot background white; only darken the major X/Y grid lines
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.grid(True, which="major", axis="both", alpha=0.65, linestyle="-",
            linewidth=0.9, color="#444444")
    # Fine 0.1% guides stay light so they don't gray out the chart
    ax.grid(True, which="minor", axis="y", alpha=0.10, linestyle="-",
            linewidth=0.3, color="#bbbbbb")
    ax.set_axisbelow(True)

    # Legend below the plot; fixed order You / Draw / Bot regardless of draw order
    handles, labels = ax.get_legend_handles_labels()
    order = [labels.index("You (X) win"), labels.index("Draw"), labels.index("Bot (O) win")]
    ax.legend(
        [handles[i] for i in order],
        [labels[i] for i in order],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=3,
        frameon=True,
        fontsize=11,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)
    # High DPI so Preview is sharp (not fuzzy)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def play_loop(
    time_limit: float,
    seed: Optional[int],
    win_sims: int = 5000,
    max_sims: Optional[int] = None,
    chart_path: str = "utt_chances",
    check_updates: bool = True,
) -> None:
    rng = random.Random(seed)
    state = State.new()
    chance_history: List[Dict[str, float]] = []
    # Snapshots before each of your turns (for Ctrl+B undo of your move + bot reply)
    checkpoints: List[Tuple[State, List[Dict[str, float]]]] = []

    # Leading blank line, then larger title
    print(file=sys.stderr)
    emit_title(
        "Ultimate Tic-Tac-Toe Bot",
        subtitle=f"v{__version__}  (you = X, bot = O)",
        file=sys.stderr,
    )
    emit(
        "Moves: [bold]BOARD-SPACE[/]  e.g. [green]5-5[/] for center of center",
        file=sys.stderr,
    )
    emit("Shortcuts (work while typing a move):", file=sys.stderr)
    emit(
        "  [bold]Ctrl+U[/] = update    [bold]Ctrl+B[/] = undo last turn    "
        "[bold]Ctrl+Q[/] = quit",
        file=sys.stderr,
    )

    if check_updates:
        # emit() already leaves one blank line after the version message
        check_for_updates(quiet=False)

    def finish(reason: str = "end") -> None:
        if state.is_terminal():
            _announce_end(state)
        elif reason == "quit":
            emit("Game stopped early.", file=sys.stderr)
        _emit_chance_chart(chance_history, chart_path, state)

    while True:
        if state.is_terminal():
            finish()
            return

        if state.to_move == X:
            try:
                raw = read_player_line()
            except EOFError:
                emit("", file=sys.stderr)
                finish("quit")
                return
            except KeyboardInterrupt:
                emit("", file=sys.stderr)
                finish("quit")
                return

            token = raw.strip()
            # Hotkeys from raw terminal reader
            if token == _CMD_QUIT:
                finish("quit")
                return
            if token == _CMD_UPDATE:
                apply_update()
                continue
            if token == _CMD_UNDO:
                if not checkpoints:
                    emit("Nothing to undo.", file=sys.stderr)
                else:
                    state, chance_history = checkpoints.pop()
                    emit(
                        "Undid your last move and the bot’s reply.",
                        file=sys.stderr,
                    )
                continue

            parsed = parse_move(raw)
            if parsed is None:
                emit(
                    "Invalid format. Use BOARD-SPACE with digits 1-9, e.g. 1-2",
                    file=sys.stderr,
                    style="bold red",
                )
                continue
            b, c = parsed
            legal = state.legal_moves()
            if (b, c) not in legal:
                emit("Illegal move.", file=sys.stderr, style="bold red")
                if state.active is not None and not state.local_closed(state.active):
                    emit(
                        f"You must play in local board {state.active + 1}.",
                        file=sys.stderr,
                        style="yellow",
                    )
                else:
                    emit(
                        "That cell is not available.",
                        file=sys.stderr,
                        style="yellow",
                    )
                continue

            # Save board before this turn (for undo of your move + bot reply)
            checkpoints.append(
                (state.clone(), [dict(row) for row in chance_history])
            )

            # Grade the human move by simulated win rate (~MOVE_SCORE_TIME seconds)
            quality, rank, n_legal, best_moves, chose_best = rank_player_move(
                state, (b, c), rng
            )
            score_style = (
                "bold green"
                if quality >= 80
                else ("yellow" if quality >= 50 else "bold red")
            )
            emit(
                f"Your move score: [{score_style}]{quality}/100[/]  "
                f"(rank {rank} of {n_legal}; 1=worst, {n_legal}=best)",
            )
            if not chose_best and best_moves:
                best_str = ", ".join(format_move(bb, cc) for bb, cc in best_moves)
                if len(best_moves) == 1:
                    emit(f"Best move would have been: [bold cyan]{best_str}[/]")
                else:
                    emit(f"Best moves would have been: [bold cyan]{best_str}[/]")

            state.apply(b, c)

            if state.is_terminal():
                # You ended the game on your move (win or rare draw)
                g = state.global_winner()
                if g == X:
                    p_win, p_draw, p_loss = 1.0, 0.0, 0.0
                    emit(f"Estimated win chance: {format_pct(p_win)}  (you won)")
                elif g == O:
                    p_win, p_draw, p_loss = 0.0, 0.0, 1.0
                    emit(f"Estimated win chance: {format_pct(p_win)}  (bot won)")
                else:
                    p_win, p_draw, p_loss = 0.0, 1.0, 0.0
                    emit(f"Estimated win chance: {format_pct(p_win)}  (draw)")
                _record_chances(chance_history, p_win, p_draw, p_loss)
                finish()
                return

            # O's reply
            emit("Thinking...", style="dim")
            bot_b, bot_c = choose_move(state, time_limit, rng, max_sims=max_sims)
            state.apply(bot_b, bot_c)
            emit(f"[bold orange1]O move:[/] {format_move(bot_b, bot_c)}")

            if state.is_terminal():
                g = state.global_winner()
                if g == X:
                    p_win, p_draw, p_loss = 1.0, 0.0, 0.0
                    emit(
                        f"Estimated win chance: [bold green]{format_pct(p_win)}[/]  (you won)"
                    )
                elif g == O:
                    p_win, p_draw, p_loss = 0.0, 0.0, 1.0
                    emit(
                        f"Estimated win chance: [bold orange1]{format_pct(p_win)}[/]  (O won)"
                    )
                else:
                    p_win, p_draw, p_loss = 0.0, 1.0, 0.0
                    emit(
                        f"Estimated win chance: [bold]{format_pct(p_win)}[/]  (draw)"
                    )
                _record_chances(chance_history, p_win, p_draw, p_loss)
                finish()
                return

            # Win chance for X after the bot has replied (you to move next).
            p_win, p_draw, p_loss = estimate_x_win_chance(
                state, rng, n_sims=win_sims
            )
            emit(
                f"Estimated win chance: [bold blue]{format_pct(p_win)}[/]  "
                f"(draw {format_pct(p_draw)}, O win {format_pct(p_loss)})"
            )
            _record_chances(chance_history, p_win, p_draw, p_loss)
        else:
            # Should not happen in normal loop (bot moves immediately after X)
            emit("Thinking...", style="dim")
            bot_b, bot_c = choose_move(state, time_limit, rng, max_sims=max_sims)
            state.apply(bot_b, bot_c)
            emit(f"[bold orange1]O move:[/] {format_move(bot_b, bot_c)}")


def _announce_end(state: State) -> None:
    g = state.global_winner()
    if g == X:
        emit("Game over: X wins.", file=sys.stderr)
    elif g == O:
        emit("Game over: O wins.", file=sys.stderr)
    else:
        emit("Game over: draw.", file=sys.stderr)


def _emit_chance_chart(
    history: List[Dict[str, float]],
    chart_path: str,
    state: State,
) -> None:
    if not history:
        emit("No chance samples to chart.", file=sys.stderr)
        return

    g = state.global_winner() if state.is_terminal() else None
    if g == X:
        subtitle = "Final result: you won"
    elif g == O:
        subtitle = "Final result: bot won"
    elif state.is_terminal():
        subtitle = "Final result: draw"
    else:
        subtitle = "Game stopped early"

    title = "Estimated outcome chances over the game"
    paths = save_chance_chart(
        history, chart_path, title=title, subtitle=subtitle
    )
    emit("Chance chart saved:", file=sys.stderr)
    for p in paths:
        emit(f"  {os.path.abspath(p)}", file=sys.stderr)

    # Prefer PNG in Preview (not Safari SVG)
    preferred = None
    for p in paths:
        if p.endswith(".png"):
            preferred = p
            break
    if preferred is None:
        for p in paths:
            if p.endswith(".svg"):
                preferred = p
                break
    if preferred and sys.platform == "darwin":
        try:
            emit("Opening chance chart in Preview in 5 seconds...")
            time.sleep(5.0)
            if preferred.endswith(".png"):
                # Force Preview for the image
                os.system(f'open -a Preview "{preferred}"')  # noqa: S605
            else:
                os.system(f'open "{preferred}"')  # noqa: S605
        except Exception:
            pass


def _require_matplotlib() -> None:
    """Exit with install instructions if matplotlib is missing."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        # Match whatever launcher the user used (python / python3 / full path)
        launcher = sys.executable or "python3"
        print(
            "This program needs matplotlib (for the end-of-game chance chart).\n"
            "\n"
            "It is not installed for this Python. In your terminal, run:\n"
            "\n"
            f"  {launcher} -m pip install matplotlib\n"
            "\n"
            "Or install everything from this folder:\n"
            "\n"
            f"  {launcher} -m pip install -r requirements.txt\n"
            "\n"
            "Then start the bot again.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ultimate Tic-Tac-Toe bot (O)")
    parser.add_argument(
        "--version",
        action="version",
        version=f"ultimate_ttt_bot {__version__}",
    )
    parser.add_argument(
        "--time",
        type=float,
        default=2.0,
        help="Seconds of search per bot move; runs as many sims as fit (default: 2.0)",
    )
    parser.add_argument(
        "--sims",
        type=int,
        default=0,
        help="Optional max MCTS simulations per move (0 = unlimited, time only; default: 0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible playouts",
    )
    parser.add_argument(
        "--win-sims",
        type=int,
        default=5000,
        help="Playouts for estimated win chance after bot moves (default: 5000)",
    )
    parser.add_argument(
        "--chart",
        type=str,
        default="utt_chances",
        help="Output path base for end-of-game chance chart (default: utt_chances)",
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Skip checking GitHub/git for a newer version on startup",
    )
    args = parser.parse_args()
    _require_matplotlib()
    play_loop(
        time_limit=args.time,
        seed=args.seed,
        win_sims=args.win_sims,
        max_sims=(args.sims if args.sims > 0 else None),
        chart_path=args.chart,
        check_updates=not args.no_update_check,
    )


if __name__ == "__main__":
    main()
