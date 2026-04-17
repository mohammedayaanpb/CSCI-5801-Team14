"""
Spell Chess game logic — pure Python, no GUI dependencies.

This module contains the core Spell Chess rules on top of python-chess.
Two spells are implemented: **Freeze** and **Jump**.

Freeze rules
------------
- Each side starts with **5 charges**.
- Casting targets a **3×3 area** centred on any square.
- All *opponent* pieces whose starting square falls inside that area
  cannot move on the opponent's **next turn** (duration = 1 turn).
- After casting there is a **3-turn cooldown** before the same side
  can cast again.
- A player may cast Freeze **at most once per turn**, and must cast
  **before** making their move.

Jump rules
----------
- Each side starts with **3 charges**.
- The caster selects one of their own pieces (except the **King**)
  and an **empty** destination square within **Chebyshev distance 2**
  (at most 2 squares in any direction).
- The piece teleports to the destination, ignoring pieces in between.
- After casting there is a **2-turn cooldown** before the same side
  can cast Jump again.
- A player may cast Jump **at most once per turn**, and must cast
  **before** making their move.
- Freeze and Jump have independent cooldowns and charges.
"""

from __future__ import annotations

import chess


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #

def squares_in_3x3(center: chess.Square) -> set[chess.Square]:
    """Return every square inside the 3×3 area centred on *center*."""
    cf = chess.square_file(center)
    cr = chess.square_rank(center)
    out: set[chess.Square] = set()
    for df in (-1, 0, 1):
        for dr in (-1, 0, 1):
            if df == 0 and dr == 0:
                continue
            f = cf + df
            r = cr + dr
            if 0 <= f < 8 and 0 <= r < 8:
                out.add(chess.square(f, r))
    return out


def squares_in_jump_range(origin: chess.Square) -> set[chess.Square]:
    """Return every square within jump range of *origin*
    (Chebyshev distance ≤ 2, excluding the origin itself)."""
    of = chess.square_file(origin)
    orr = chess.square_rank(origin)
    out: set[chess.Square] = set()
    for df in range(-3, 4):
        for dr in range(-3, 4):
            if df == 0 and dr == 0:
                continue
            f = of + df
            r = orr + dr
            if 0 <= f < 8 and 0 <= r < 8:
                out.add(chess.square(f, r))
    return out


# ------------------------------------------------------------------ #
#  Core game class                                                    #
# ------------------------------------------------------------------ #

class SpellChessGame:
    """
    Manages a single Spell Chess game.

    Wraps a ``chess.Board`` and adds freeze-spell bookkeeping.
    Every public method is free of GUI or engine dependencies so
    the class can be used directly in unit tests.
    """

    def __init__(self) -> None:
        self.board = chess.Board()

        # Freeze spell state
        self.spell_casted_this_turn: bool = False
        self.freeze_targeting: bool = False
        self.freeze_remaining: dict[chess.Color, int] = {
            chess.WHITE: 5,
            chess.BLACK: 5,
        }
        self.freeze_cooldown: dict[chess.Color, int] = {
            chess.WHITE: 0,
            chess.BLACK: 0,
        }
        self.freeze_effect_color: chess.Color | None = None
        self.freeze_effect_squares: set[chess.Square] = set()
        self.freeze_effect_plies_left: int = 0

        # Jump spell state
        self.jump_casted_this_turn: bool = False
        self.jump_remaining: dict[chess.Color, int] = {
            chess.WHITE: 3,
            chess.BLACK: 3,
        }
        self.jump_cooldown: dict[chess.Color, int] = {
            chess.WHITE: 0,
            chess.BLACK: 0,
        }

    # ----- reset -----

    def new_game(self) -> None:
        """Reset the board and all spell state to the starting position."""
        self.spell_casted_this_turn = False
        self.freeze_targeting = False
        self.freeze_remaining = {chess.WHITE: 5, chess.BLACK: 5}
        self.freeze_cooldown = {chess.WHITE: 0, chess.BLACK: 0}
        self.freeze_effect_color = None
        self.freeze_effect_squares = set()
        self.freeze_effect_plies_left = 0
        self.jump_casted_this_turn = False
        self.jump_cooldown = {chess.WHITE: 0, chess.BLACK: 0}

    # ----- freeze casting -----

    def cast_freeze(self, center: chess.Square) -> bool:
        """
        Attempt to cast the Freeze spell centred on *center*.

        Returns ``True`` if the cast succeeded, ``False`` otherwise
        (already cast this turn, on cooldown, or no charges left).
        """
        if self.spell_casted_this_turn:
            return False
        turn = self.board.turn
        if self.freeze_cooldown.get(turn, 0) > 0:
            return False
        if self.freeze_remaining.get(turn, 0) <= 0:
            return False

        squares = squares_in_3x3(center)
        opponent = not turn

        self.freeze_effect_color = turn
        self.freeze_effect_squares = squares
        self.freeze_effect_plies_left = 2

        self.freeze_cooldown[turn] = 2
        return True

    # ----- jump casting -----

    def cast_jump(self, piece_sq: chess.Square, dest_sq: chess.Square) -> bool:
        """
        Attempt to cast Jump: teleport the piece at *piece_sq*
        to *dest_sq*.

        Returns ``True`` if the jump succeeded, ``False`` otherwise.
        """
        if self.jump_casted_this_turn:
            return False
        turn = self.board.turn
        if self.jump_cooldown.get(turn, 0) > 0:
            return False
        if self.jump_remaining.get(turn, 0) <= 0:
            return False

        piece = self.board.piece_at(piece_sq)
        if piece is None:
            return False
        if piece.color != turn:
            return False

        if dest_sq not in squares_in_jump_range(piece_sq):
            return False

        self.board.remove_piece_at(piece_sq)
        self.board.set_piece_at(dest_sq, piece)

        self.jump_remaining[turn] -= 1
        self.jump_cooldown[turn] = 1
        self.jump_casted_this_turn = True
        return True

    # ----- freeze queries -----

    def is_frozen(self, square: chess.Square, color: chess.Color) -> bool:
        """Return ``True`` if *square* is frozen for *color* this turn."""
        return (
            self.freeze_effect_color == color
            and self.freeze_effect_plies_left > 0
            and square in self.freeze_effect_squares
        )

    def get_legal_moves(self) -> list[chess.Move]:
        """
        Return legal moves for the side to move, excluding moves
        whose origin square is frozen.
        """
        turn = self.board.turn
        return [
            m for m in self.board.legal_moves
            if not self.is_frozen(m.from_square, turn)
        ]

    # ----- turn lifecycle -----

    def on_turn_start(self) -> None:
        """Called at the beginning of a new turn (after the board's
        ``turn`` has already switched)."""
        self.spell_casted_this_turn = False
        self.freeze_targeting = False
        self.jump_casted_this_turn = False
        turn = self.board.turn
        if self.jump_cooldown.get(turn, 0) > 0:
            self.jump_cooldown[turn] -= 1

    def after_move_pushed(self) -> None:
        """Called right after a move is pushed to the board.

        Expires the freeze effect if the frozen side just moved,
        then delegates to ``on_turn_start``.
        """
        if self.freeze_effect_color is not None:
            moved_color = not self.board.turn
            if moved_color == self.freeze_effect_color and self.freeze_effect_plies_left > 0:
                self.freeze_effect_plies_left -= 1
                if self.freeze_effect_plies_left <= 0:
                    self.freeze_effect_color = None
                    self.freeze_effect_squares = set()
                    self.freeze_effect_plies_left = 0
        self.on_turn_start()
        self.board.turn = not self.board.turn

    # ----- making moves -----

    def prepare_move(
        self,
        from_sq: chess.Square,
        to_sq: chess.Square,
        promotion: int = chess.QUEEN,
    ) -> chess.Move:
        """
        Build a ``chess.Move`` from *from_sq* to *to_sq*, adding
        promotion when a pawn reaches the last rank.

        *promotion* can be ``chess.QUEEN``, ``chess.ROOK``,
        ``chess.BISHOP``, or ``chess.KNIGHT``.
        """
        move = chess.Move(from_sq, to_sq)
        piece = self.board.piece_at(from_sq)
        if piece and piece.piece_type == chess.PAWN:
            if chess.square_rank(to_sq) in (0, 7):
                if promotion == chess.KNIGHT:
                    return move
                move = chess.Move(from_sq, to_sq, promotion=promotion)
        return move

    def make_move(
        self,
        from_sq: chess.Square,
        to_sq: chess.Square,
        promotion: int = chess.QUEEN,
    ) -> bool:
        """
        Try to make a move. Returns ``True`` if the move was legal
        and has been pushed, ``False`` otherwise.

        Handles promotion automatically and respects freeze.
        """
        move = self.prepare_move(from_sq, to_sq, promotion)

        piece = self.board.piece_at(from_sq)
        if piece and piece.piece_type == chess.PAWN:
            target = self.board.piece_at(to_sq)
            if target is None and chess.square_file(from_sq) != chess.square_file(to_sq):
                return False

        if move not in self.board.legal_moves:
            return False

        self.board.push(move)
        self.after_move_pushed()
        return True

    # ----- game state queries -----

    def is_game_over(self) -> bool:
        return self.board.is_game_over(claim_draw=True)

    def outcome(self) -> chess.Outcome | None:
        return self.board.outcome(claim_draw=True)

    def current_turn(self) -> chess.Color:
        return self.board.turn

    def status_text(self) -> str:
        """Human-readable status string."""
        if self.is_game_over():
            o = self.outcome()
            if o is None:
                return "Game over."
            if o.winner is None:
                res = "Draw"
            elif o.winner == chess.WHITE:
                res = "White wins"
            else:
                res = "Black wins"
            return f"Game over: {o.termination.name} — {res}"

        turn = "White" if self.board.turn == chess.WHITE else "Black"
        check = " (check)" if self.board.is_check() else ""
        return f"Turn: {turn}{check}."

    def freeze_info_text(self) -> str:
        """Human-readable freeze label for the side to move."""
        turn = self.board.turn
        rem = self.freeze_remaining.get(turn, 0)
        cd = self.freeze_cooldown.get(turn, 0)
        if cd > 0:
            text = f"Freeze: {rem}  (cooldown {cd})"
        else:
            text = f"Freeze: {rem}"

        if self.freeze_effect_color == self.board.turn and self.freeze_effect_plies_left > 0:
            text += "  — pieces in area are frozen"
        return text

    def jump_info_text(self) -> str:
        """Human-readable jump label for the side to move."""
        turn = self.board.turn
        rem = self.jump_remaining.get(turn, 0)
        cd = self.jump_cooldown.get(turn, 0)
        if cd > 0:
            return f"Jump: {rem}  (cooldown {cd})"
        return f"Jump: {rem}"
