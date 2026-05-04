"""
Unit tests for Spell Chess game logic.

Run with:
    pytest test_spell_logic.py -v

These tests verify the Spell Chess rules described in SPELL_CHESS_RULES.md.
Each test creates a fresh SpellChessGame, sets up a position, performs an
action, and checks that the result matches the specification.
"""

import chess
from spell_logic import SpellChessGame, squares_in_3x3, squares_in_jump_range


# ------------------------------------------------------------------ #
#  Demo tests — provided to students as examples                      #
# ------------------------------------------------------------------ #

class TestFreezeTarget:
    """Casting Freeze should mark the opponent's color as frozen."""

    def test_freeze_affects_opponent_not_caster(self):
        game = SpellChessGame()
        # White casts freeze
        game.cast_freeze(chess.E5)
        # The frozen color should be Black (the opponent), not White
        assert game.freeze_effect_color == chess.BLACK

    def test_opponents_pieces_cannot_move_when_frozen(self):
        #TC-FRZ-04, TC-FRZ-05a - Freeze prevents pieces in the area from moving on opponent's next turn
        game = SpellChessGame()
        # White casts freeze
        game.cast_freeze(chess.D7)
        # White makes a move
        game.make_move(chess.E2,chess.E4)
        # Black Pieces within 3x3 of D7 should not be able to move
        move_success = game.make_move(chess.D7, chess.D5)
        assert move_success is False
    def test_freeze_lasts_one_move(self):
        #TC-FRZ-05b - Freeze duration = 1 opponent turn
        game = SpellChessGame()
        # White casts freeze
        game.cast_freeze(chess.D7)
        # White makes a move
        game.make_move(chess.E2,chess.E4)
        # Black Pieces within 3x3 of D7 should not be able to move
        move_success = game.make_move(chess.D7, chess.D5)
        assert move_success is False
        # Black moves then white moves
        game.make_move(chess.H7,chess.H6)
        game.make_move(chess.H4,chess.H5)
        # Now black should be able to move the D7 pawn
        move_success = game.make_move(chess.D7, chess.D5)
        assert move_success is True
        
    def test_frozen_piece_still_gives_check(self):
        #TC-FRZ-07a - Frozen pieces still give check
        game = SpellChessGame()
        # Setup: Black Rook at E8, White King at E1
        # FEN: White King on e1, Black Rook on e8, others empty
        game.board.set_fen("4r3/8/8/8/8/8/8/4K3 w - - 0 1")
        
        # White casts freeze on the Rook at E8
        game.cast_freeze(chess.E8)
        
        assert game.board.is_check() is True, "White King should be in check from the frozen Rook"
        
        move = game.prepare_move(chess.E1, chess.E2)
        assert move not in game.board.legal_moves, "White should not be able to move into/stay in check"
    def test_frozen_piece_still_blocks_squares(self):
        #TC-FRZ-07b - Frozen pieces still block squares
        game = SpellChessGame()
        # Setup: White Pawn at E2, Black Pawn at E3 
        game.board.set_fen("8/8/8/8/8/4p3/4P3/8 w - - 0 1")
        
        # White freezes the Black Pawn at E3
        game.cast_freeze(chess.E3)
        
        # White attempts to move E2 to E3
        move_attempt = game.make_move(chess.E2, chess.E3)
        assert move_attempt is False, "White pawn should be blocked by the frozen Black pawn"
    
    def test_no_valid_moves_if_possible_moves_come_from_frozen_square(self):
        #TC-FRZ-07c - If all of a player's legal moves originate from frozen squares, there should be no valid moves available
        game = SpellChessGame()
        # Setup : White Pawn E2 Black Pawn E5
        game.board.set_fen("8/8/8/4p3/8/8/4P3/8 w - - 0 1")

        # White freezes the Black Pawn at E4
        game.cast_freeze(chess.E4)

        # White moves
        game.make_move(chess.E2,chess.E3)
        # Black attempts to move and they should be able to because their piece is frozen
        assert game.board.turn == chess.BLACK, "Turn should be Black's"
        black_moves = game.get_legal_moves()
        assert len(black_moves) == 0, "Black should have 0 legal moves because their only piece is frozen"

class TestFreezeCharges:
    def test_each_side_starts_with_correct_number_freeze_spells(self):
        # TC-FRZ-01a - Each side begins with 5 freeze charges
        game = SpellChessGame()
        assert game.freeze_remaining[chess.WHITE] == 5
        assert game.freeze_remaining[chess.BLACK] == 5
    def test_each_cast_costs_one_charge(self):
        #TC-FRZ-01b - Each freeze cast costs 1 charge
        game = SpellChessGame()
        # White starts with 5 freeze spells
        assert game.freeze_remaining[chess.WHITE] == 5
        # White uses one freeze spell
        game.cast_freeze(chess.E4)
        # There should be 4 left now
        assert game.freeze_remaining[chess.WHITE] == 4
    def test_cannot_freeze_with_zero_charges(self):
        # TC-FRZ-01c - Cannot cast Freeze when charges = 0
        game = SpellChessGame()
        game.freeze_remaining[chess.WHITE] = 0 
        assert game.cast_freeze(chess.E4) is False

class TestFreezeCasting:
    def test_cannot_freeze_twice_in_one_turn(self):
        #TC-FRZ-02a - Freeze may be cast at most once per turn
        game = SpellChessGame()
        
        # the first cast should succeed
        first_cast = game.cast_freeze(chess.E4)
        assert first_cast is True
        
        #the second cast in the same turn should fail
        second_cast = game.cast_freeze(chess.D7)
        assert second_cast is False, "Should not be able to cast Freeze twice in one turn"
    
    def test_cannot_freeze_after_move(self):
        # TC-FRZ-02b - Freeze cannot be cast after move
        game = SpellChessGame()

        # make a move
        game.make_move(chess.E2,chess.E4)

        # attempt to cast spell. Black should be the one using this spell since white's turn is over
        success = game.cast_freeze(chess.D7)

        assert game.freeze_remaining[chess.WHITE] == 5, "White should have all 5 freeze spells"

    def test_freeze_targets_correct_3x3_area(self):
        #TC-FRZ-03a - Freeze affects a 3×3 area centered on chosen square (includes center)
        game = SpellChessGame()
        
        game.cast_freeze(chess.E4)
        
        expected_squares = [
            chess.D3, chess.E3, chess.F3,
            chess.D4, chess.E4, chess.F4,
            chess.D5, chess.E5, chess.F5
        ]
        
        for sq in expected_squares:
            assert sq in game.freeze_effect_squares, f"Square {chess.square_name(sq)} should be frozen"
            
        assert chess.A1 not in game.freeze_effect_squares, "Square A1 should NOT be frozen"


    def test_freeze_squares_in_center(self):
        #TC-FRZ-03b - Freeze 3×3 area covers 9 squares for an interior center
        game = SpellChessGame()
        game.cast_freeze(chess.E4)

        assert len(game.freeze_effect_squares) == 9

    def test_freeze_squares_in_corner(self):
        #TC-FRZ-03c - Freeze 3×3 area covers 4 squares for a corner center
        game = SpellChessGame()
        game.cast_freeze(chess.A8)

        assert len(game.freeze_effect_squares) == 4

    def test_freeze_squares_in_edge(self):
        # TC-FRZ-03d - Freeze 3×3 area covers 6 squares for an edge center
        game = SpellChessGame()
        game.cast_freeze(chess.A4)

        assert len(game.freeze_effect_squares) == 6


class TestFreezeCooldown:
    def test_size_cooldown_after_freeze(self):
        # TC-FRZ-06a - Caster freeze cooldown = 3 turns after a successful cast
        game = SpellChessGame()

        #White uses a freeze and cool down should be 3
        game.cast_freeze(chess.D7)

        assert game.freeze_cooldown[chess.WHITE] == 3
    
    def test_cooldown_decrement_on_turn(self):
        # TC-FRZ-06b - Freeze cooldown decrements at start of caster's turn
        game = SpellChessGame()

        game.cast_freeze(chess.D7)

        init_cooldown = game.freeze_cooldown[chess.WHITE]

        # make a move so that its back to white's turn and we can check if cooldown went down
        game.make_move(chess.E2,chess.E4)
        game.make_move(chess.E7,chess.E6)

        assert game.freeze_cooldown[chess.WHITE] == (init_cooldown - 1)

    def test_caster_waits_for_cooldown_to_freeze(self):
        #TC-FRZ-06c - Caster cannot cast freeze again until cooldown reaches 0
        game = SpellChessGame()

        # white uses freeze
        game.cast_freeze(chess.D7)

        # move goes back to white and white should not be able to use freeze again
        game.make_move(chess.E2,chess.E4)
        game.make_move(chess.E7,chess.E6)

        success = game.cast_freeze(chess.A8)

        assert success == False, "White needs to wait for cooldown to reach 0"

        # make two more moves and white should be able to cast freeze again
        game.make_move(chess.D2,chess.D4)
        game.make_move(chess.D7,chess.D6)

        game.make_move(chess.C2,chess.C3)
        game.make_move(chess.C7,chess.C6)

        assert game.freeze_cooldown[chess.WHITE] == 0
        assert game.cast_freeze(chess.A8) == True







        








class TestNewGameResetsBoard:
    """Calling new_game() should bring the board back to the starting position."""

    def test_board_resets_after_moves(self):
        game = SpellChessGame()
        game.board.push_san("e4")
        game.new_game()
        assert game.board.fen() == chess.STARTING_FEN


# ------------------------------------------------------------------ #
#  YOUR TESTS GO BELOW                                                #
#  Write tests that check the rules from SPELL_CHESS_RULES.md.        #
#  If a test fails, you've found a bug — document it!                 #
# ------------------------------------------------------------------ #



#  JUMP SPELL TESTS  —  Owner: Ayaan Mohammed


class TestJumpCharges:
    """Spec: Each side starts with 3 jump charges; each cast costs 1;
    cannot cast at 0 charges. Sprint task: SB-13."""

    def test_starting_charges_are_three_per_side(self):
        """TC-JMP-01a — Both sides start with exactly 3 jump charges."""
        game = SpellChessGame()
        assert game.jump_remaining[chess.WHITE] == 3
        assert game.jump_remaining[chess.BLACK] == 3

    def test_charges_decrement_after_successful_cast(self):
        """TC-JMP-01b — A successful cast reduces caster's charges by 1."""
        game = SpellChessGame()
        before = game.jump_remaining[chess.WHITE]
        result = game.cast_jump(chess.B1, chess.A3)
        assert result is True
        assert game.jump_remaining[chess.WHITE] == before - 1

    def test_cannot_cast_at_zero_charges(self):
        """TC-JMP-01c — With 0 charges, cast returns False, state unchanged."""
        game = SpellChessGame()
        game.jump_remaining[chess.WHITE] = 0
        result = game.cast_jump(chess.B1, chess.A3)
        assert result is False
        assert game.jump_remaining[chess.WHITE] == 0


class TestJumpOncePerTurn:
    """Spec: Jump may be cast at most once per turn. Sprint task: SB-15."""

    def test_second_cast_in_same_turn_returns_false(self):
        """TC-JMP-02 — Second cast in same turn rejected; charges only decrement once."""
        game = SpellChessGame()
        before = game.jump_remaining[chess.WHITE]
        first = game.cast_jump(chess.B1, chess.A3)
        second = game.cast_jump(chess.G1, chess.H3)
        assert first is True
        assert second is False
        assert game.jump_remaining[chess.WHITE] == before - 1

class TestJumpKingRestriction:
    """Spec: King cannot be jumped — only non-King pieces eligible.
    Sprint task: SB-10."""

    def test_cannot_jump_the_king(self):
        """TC-JMP-03 — Attempting to jump the King returns False."""
        game = SpellChessGame()
        before_charges = game.jump_remaining[chess.WHITE]
        before_cd = game.jump_cooldown[chess.WHITE]
        result = game.cast_jump(chess.E1, chess.E3)
        assert result is False
        assert game.jump_remaining[chess.WHITE] == before_charges
        assert game.jump_cooldown[chess.WHITE] == before_cd
        assert game.board.piece_at(chess.E1) is not None
        assert game.board.piece_at(chess.E1).piece_type == chess.KING


class TestJumpRange:
    """Spec: Destination within Chebyshev distance ≤ 2.
    Sprint task: SB-11."""

    def test_distance_two_boundary_succeeds(self):
        """TC-JMP-04a — Destination at Chebyshev distance 2 is allowed."""
        game = SpellChessGame()
        result = game.cast_jump(chess.B1, chess.A3)
        assert result is True
        assert game.board.piece_at(chess.A3) is not None
        assert game.board.piece_at(chess.A3).piece_type == chess.KNIGHT
        assert game.board.piece_at(chess.B1) is None

    def test_distance_three_fails(self):
        """TC-JMP-04b — Destination at Chebyshev distance 3 is rejected."""
        game = SpellChessGame()
        before = game.jump_remaining[chess.WHITE]
        result = game.cast_jump(chess.B1, chess.B4)
        assert result is False
        assert game.jump_remaining[chess.WHITE] == before
        assert game.board.piece_at(chess.B1) is not None


class TestJumpEmptyDestination:
    """Spec: Destination must be empty — no capture by Jump.
    Sprint task: SB-12."""

    def test_jump_to_occupied_square_returns_false(self):
        """TC-JMP-05 — Cannot jump onto a square containing a piece."""
        game = SpellChessGame()
        # B2 has White's pawn in the starting position
        assert game.board.piece_at(chess.B2) is not None
        result = game.cast_jump(chess.B1, chess.B2)
        assert result is False
        assert game.board.piece_at(chess.B1).piece_type == chess.KNIGHT
        assert game.board.piece_at(chess.B2).piece_type == chess.PAWN

class TestJumpCooldown:
    """Spec: 2-turn cooldown after a successful cast; decrements at start
    of caster's next turn. Sprint task: SB-13."""

    def test_cooldown_set_to_two_after_cast(self):
        """TC-JMP-06a — Cooldown is set to 2 immediately after successful cast."""
        game = SpellChessGame()
        result = game.cast_jump(chess.B1, chess.A3)
        assert result is True
        assert game.jump_cooldown[chess.WHITE] == 2
        assert game.jump_cooldown[chess.BLACK] == 0

    def test_cooldown_decrements_after_full_round(self):
        """TC-JMP-06b — Cooldown decrements at start of caster's next turn."""
        game = SpellChessGame()
        game.cast_jump(chess.B1, chess.A3)
        # Make White's move and Black's move; cooldown should decrement once
        game.make_move(chess.E2, chess.E4)
        game.make_move(chess.E7, chess.E5)
        assert game.jump_cooldown[chess.WHITE] == 1

class TestNewGame:
    """Spec: Starting a new game resets everything.
    Sprint tasks: SB-14, SB-15, SB-16, SB-17."""

    def test_board_resets_to_starting_position(self):
        """TC-NG-01 — Board returns to standard starting FEN."""
        game = SpellChessGame()
        game.make_move(chess.E2, chess.E4)

        game.new_game()

        assert game.board.fen() == chess.STARTING_FEN

    def test_freeze_charges_reset(self):
        """TC-NG-02 — Freeze charges reset to 5 for both sides."""
        game = SpellChessGame()
        game.freeze_remaining[chess.WHITE] = 2
        game.freeze_remaining[chess.BLACK] = 0

        game.new_game()

        assert game.freeze_remaining[chess.WHITE] == 5
        assert game.freeze_remaining[chess.BLACK] == 5

    def test_jump_charges_reset(self):
        """TC-NG-03 — Jump charges reset to 3 for both sides."""
        game = SpellChessGame()
        game.jump_remaining[chess.WHITE] = 1
        game.jump_remaining[chess.BLACK] = 0

        game.new_game()

        assert game.jump_remaining[chess.WHITE] == 3
        assert game.jump_remaining[chess.BLACK] == 3

    def test_all_cooldowns_reset(self):
        """TC-NG-04 — Freeze and Jump cooldowns reset to 0."""
        game = SpellChessGame()
        game.freeze_cooldown[chess.WHITE] = 3
        game.freeze_cooldown[chess.BLACK] = 2
        game.jump_cooldown[chess.WHITE] = 2
        game.jump_cooldown[chess.BLACK] = 1

        game.new_game()

        assert game.freeze_cooldown[chess.WHITE] == 0
        assert game.freeze_cooldown[chess.BLACK] == 0
        assert game.jump_cooldown[chess.WHITE] == 0
        assert game.jump_cooldown[chess.BLACK] == 0

    def test_active_effects_cleared(self):
        """TC-NG-05 — All active freeze effects are removed."""
        game = SpellChessGame()
        game.freeze_effect_color = chess.BLACK
        game.freeze_effect_squares = {chess.E4, chess.E5}
        game.freeze_effect_plies_left = 1

        game.new_game()

        assert game.freeze_effect_color is None
        assert game.freeze_effect_squares == set()
        assert game.freeze_effect_plies_left == 0
