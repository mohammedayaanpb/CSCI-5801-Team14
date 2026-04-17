#!/usr/bin/env python3
"""
Play "Human vs Computer" in your terminal using python-chess + a UCI engine.

Default engine: `stockfish` (must be on PATH).

Examples:
  ./play_vs_stockfish.py
  ./play_vs_stockfish.py --engine /opt/homebrew/bin/stockfish --time 0.2
  ./play_vs_stockfish.py --skill 5 --human black
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass

import chess
import chess.engine


@dataclass(frozen=True)
class Config:
    engine_cmd: str
    human_color: chess.Color
    think_time_s: float
    skill: int | None


def parse_args(argv: list[str]) -> Config:
    p = argparse.ArgumentParser(description="Play vs a UCI engine (terminal UI).")
    p.add_argument(
        "--engine",
        default="stockfish",
        help="UCI engine command (default: stockfish). Can be a full path.",
    )
    p.add_argument(
        "--human",
        choices=["white", "black"],
        default="white",
        help="Which side you play (default: white).",
    )
    p.add_argument(
        "--time",
        type=float,
        default=0.3,
        help="Engine think time per move in seconds (default: 0.3).",
    )
    p.add_argument(
        "--skill",
        type=int,
        default=None,
        help="Optional Stockfish Skill Level (0-20).",
    )
    args = p.parse_args(argv)

    human_color = chess.WHITE if args.human == "white" else chess.BLACK
    return Config(
        engine_cmd=args.engine,
        human_color=human_color,
        think_time_s=args.time,
        skill=args.skill,
    )


def prompt_human_move(board: chess.Board) -> chess.Move:
    while True:
        raw = input("Your move (SAN like e4 / Nf3, or UCI like e2e4; 'quit'): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise KeyboardInterrupt

        # Try SAN first (more user friendly), then UCI.
        try:
            return board.parse_san(raw)
        except ValueError:
            pass
        try:
            move = chess.Move.from_uci(raw)
            if move in board.legal_moves:
                return move
        except ValueError:
            pass

        print("Invalid move. Try again.")


def print_board(board: chess.Board) -> None:
    print()
    print(board)
    print(f"FEN: {board.fen()}")
    if board.is_check():
        print("Check!")
    print()


def main(argv: list[str]) -> int:
    cfg = parse_args(argv)

    # Resolve engine command.
    engine_cmd = cfg.engine_cmd
    if " " not in engine_cmd and "/" not in engine_cmd:
        found = shutil.which(engine_cmd)
        if not found:
            print(
                "ERROR: Could not find engine on PATH: "
                f"{engine_cmd!r}. Install Stockfish with `brew install stockfish` "
                "or pass --engine /full/path/to/engine.",
                file=sys.stderr,
            )
            return 2
        engine_cmd = found

    board = chess.Board()

    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_cmd)
    except FileNotFoundError:
        print(f"ERROR: Engine not found: {engine_cmd!r}", file=sys.stderr)
        return 2

    try:
        if cfg.skill is not None:
            # Works for Stockfish; other engines may ignore.
            try:
                engine.configure({"Skill Level": cfg.skill})
            except chess.engine.EngineError:
                pass

        print("Starting game. Type 'quit' to exit.")
        print(f"Human: {'White' if cfg.human_color == chess.WHITE else 'Black'}")
        print(f"Engine: {engine_cmd}")

        while not board.is_game_over(claim_draw=True):
            print_board(board)

            if board.turn == cfg.human_color:
                move = prompt_human_move(board)
                board.push(move)
                continue

            # Engine move.
            result = engine.play(board, chess.engine.Limit(time=cfg.think_time_s))
            board.push(result.move)
            try:
                print(f"Engine plays: {board.san(result.move)}")
            except Exception:
                print(f"Engine plays: {result.move.uci()}")

        print_board(board)
        outcome = board.outcome(claim_draw=True)
        if outcome is None:
            print("Game over.")
        else:
            print(f"Game over: {outcome.termination.name}")
            if outcome.winner is None:
                print("Result: 1/2-1/2")
            elif outcome.winner == chess.WHITE:
                print("Result: 1-0 (White wins)")
            else:
                print("Result: 0-1 (Black wins)")
        return 0
    except KeyboardInterrupt:
        print("\nBye.")
        return 0
    finally:
        try:
            engine.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


