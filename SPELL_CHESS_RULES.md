# Spell Chess — Game Specification

Spell Chess is standard chess with two additions: each player has access to a **Freeze** spell and a **Jump** spell.

---

## Your Task

The game logic in `spell_logic.py` contains bugs. Your job is to:

1. Read this specification carefully — it describes how the game **should** work.
2. Write unit tests in `test_spell_logic.py` that check the rules from this document.
3. When a test fails, you have found a bug. Document each bug you find.

You only need to work with three files:

- `**SPELL_CHESS_RULES.md`** (this file) — the specification (source of truth).
- `**spell_logic.py**` — the implementation under test.
- `**test_spell_logic.py**` — where you write your tests.

### Install dependencies

```bash
pip install chess pytest
```

### Run the unit tests

```bash
# Run all tests
python -m pytest test_spell_logic.py -v

# Run a specific test class
python -m pytest test_spell_logic.py::TestFreezeTarget -v
```

---

## Example Unit Tests

Below are two complete unit tests to show you the pattern. These are already included in `test_spell_logic.py`. Study them, then write more tests that cover the rest of the specification.

### Example 1 — Freeze should target the opponent

The spec says: *"The freeze affects the opponent (not the caster)."*

A test for this rule:

```python
class TestFreezeTarget:
    """Casting Freeze should mark the opponent's color as frozen."""

    def test_freeze_affects_opponent_not_caster(self):
        game = SpellChessGame()
        # White casts freeze
        game.cast_freeze(chess.E5)
        # The frozen color should be Black (the opponent), not White
        assert game.freeze_effect_color == chess.BLACK
```

### Example 2 — New Game resets the board

The spec says: *"Starting a new game resets everything: the board returns to the standard starting position…"*

A test for this rule:

```python
class TestNewGameResetsBoard:
    """Calling new_game() should bring the board back to the starting position."""

    def test_board_resets_after_moves(self):
        game = SpellChessGame()
        game.board.push_san("e4")
        game.new_game()
        assert game.board.fen() == chess.STARTING_FEN
```

---

## Standard Chess Rules

All standard chess rules apply: piece movement, captures, check, checkmate, stalemate, castling, en passant, pawn promotion, etc. When a pawn reaches the last rank (rank 8 for White, rank 1 for Black) it can be promoted to a Queen, Rook, Bishop, or Knight.

## The Freeze Spell

### Charges

- Each side begins the game with **5 freeze charges**.
- Each cast costs **1 charge**.
- When a player has 0 charges remaining, they cannot cast Freeze.

### Casting

- A player may cast Freeze **once per turn**, and it must be done **before** making their move.
- To cast, the player selects any square on the board as the **center** of a **3×3 area**.
- The 3×3 area includes the center square and all squares within 1 step horizontally, vertically, or diagonally (up to 9 squares in the middle of the board, fewer on edges/corners).

### Effect

- The freeze affects the **opponent** (not the caster).
- All opponent pieces whose square falls inside the frozen area **cannot be moved** on the opponent's next turn.
- Duration: the freeze lasts for exactly **1 of the opponent's turns**. After the opponent completes one move, the freeze expires and those squares are free again.
- Frozen pieces still give check, block squares, etc. — they just cannot be selected as the piece to move.
- If all of a player's legal moves originate from frozen squares, the game should recognize that the player has no valid moves available.

### Cooldown

- After casting Freeze, the caster enters a **3-turn cooldown**.
- The cooldown decrements by 1 at the **start of each of the caster's turns**.
- The caster cannot cast Freeze again until the cooldown reaches 0.

### New Game

- Starting a new game resets **everything**: the board returns to the standard starting position, both sides get 5 freeze charges and 3 jump charges, all cooldowns reset to 0, and any active freeze effect is cleared.

## The Jump Spell

### Charges

- Each side begins the game with **3 jump charges**.
- Each cast costs **1 charge**.
- When a player has 0 charges remaining, they cannot cast Jump.

### Casting

- A player may cast Jump **once per turn**, and it must be done **before** making their move.
- To cast, the player selects one of their **own pieces** and an **empty** destination square.
- The **King cannot be jumped** — only non-King pieces may be selected.
- The destination must be within **Chebyshev distance 2** of the piece (at most 2 squares in any direction — horizontally, vertically, or diagonally).

### Effect

- The selected piece **teleports** to the destination square, ignoring any pieces in between.
- The piece can only land on an **empty square** — it cannot capture via Jump.

### Cooldown

- After casting Jump, the caster enters a **2-turn cooldown**.
- The cooldown decrements by 1 at the **start of each of the caster's turns**.
- The caster cannot cast Jump again until the cooldown reaches 0.

### New Game

- Starting a new game resets jump charges to 3 for both sides and clears jump cooldowns.

## Game State Display

- The game shows whose turn it is and whether the current side is in check.
- The freeze label shows the **current player's** remaining charges.
- When the current player is on cooldown, the label shows the remaining cooldown turns.
- When the current player's pieces are frozen, the label includes a note that pieces in the area are frozen.

## Summary of Key Numbers


| Rule                             | Value                  |
| -------------------------------- | ---------------------- |
| Freeze starting charges per side | 5                      |
| Freeze area                      | 3×3 (up to 9 squares)  |
| Freeze duration                  | 1 opponent turn        |
| Freeze cooldown after casting    | 3 turns                |
| Freeze casts per turn            | 1 maximum              |
| Jump starting charges per side   | 3                      |
| Jump range                       | Chebyshev distance ≤ 2 |
| Jump cooldown after casting      | 2 turns                |
| Jump casts per turn              | 1 maximum              |
| Jump restriction                 | Cannot jump the King   |


## API Reference (for testing)

The game logic lives in `spell_logic.py`. Key class: `SpellChessGame`.

### Creating a game

```python
from spell_logic import SpellChessGame, squares_in_3x3, squares_in_jump_range
import chess

game = SpellChessGame()
```

### Casting Freeze

```python
success = game.cast_freeze(chess.E4)  # returns True if cast succeeded
```

### Casting Jump

```python
ok = game.cast_jump(chess.B1, chess.C3)  # returns True if jump succeeded
```

### Making a move

```python
ok = game.make_move(chess.E2, chess.E4)  # returns True if legal and pushed
ok = game.make_move(from_sq, to_sq, promotion=chess.ROOK)   # promote to Rook
```

### Querying freeze state

```python
game.freeze_effect_color          # which side is frozen (or None)
game.freeze_effect_squares        # set of frozen squares
game.freeze_effect_plies_left     # turns remaining on current freeze
game.freeze_remaining[chess.WHITE] # charges left for White
game.freeze_cooldown[chess.WHITE]  # cooldown turns left for White
game.spell_casted_this_turn       # whether a spell was cast this turn
game.is_frozen(square, color)     # True if square is frozen for that color
game.get_legal_moves()            # legal moves excluding frozen origins
```

### Querying jump state

```python
game.jump_remaining[chess.WHITE]  # jump charges left for White
game.jump_cooldown[chess.WHITE]   # jump cooldown turns left for White
game.jump_casted_this_turn        # whether Jump was cast this turn
```

### Other helpers

```python
squares_in_3x3(chess.E4)             # set of squares in the 3×3 area
squares_in_jump_range(chess.E4)       # set of squares within jump range
game.new_game()                       # reset everything
game.board                            # the underlying chess.Board
game.current_turn()                   # chess.WHITE or chess.BLACK
game.is_game_over()                   # True if game is over
game.prepare_move(from_sq, to_sq)     # build Move with auto-promotion
game.prepare_move(f, t, chess.ROOK)   # build Move choosing Rook promotion
game.status_text()                    # human-readable status
game.freeze_info_text()               # human-readable freeze label
game.jump_info_text()                 # human-readable jump label
```

