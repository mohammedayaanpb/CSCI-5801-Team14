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
        game = SpellChessGame()
        # White casts freeze
        game.cast_freeze(chess.D7)
        # White makes a move
        game.make_move(chess.E2,chess.E4)
        # Black Pieces within 3x3 of D7 should not be able to move
        move_success = game.make_move(chess.D7, chess.D5)
        assert move_success is False
    def test_freeze_lasts_one_move(self):
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
        game = SpellChessGame()
        # Setup: White Pawn at E2, Black Pawn at E3 
        game.board.set_fen("8/8/8/8/8/4p3/4P3/8 w - - 0 1")
        
        # White freezes the Black Pawn at E3
        game.cast_freeze(chess.E3)
        
        # White attempts to move E2 to E3
        move_attempt = game.make_move(chess.E2, chess.E3)
        assert move_attempt is False, "White pawn should be blocked by the frozen Black pawn"
    
    def test_no_valid_moves_if_possible_moves_come_from_frozen_square(self):
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
        game = SpellChessGame()
        assert game.freeze_remaining[chess.WHITE] == 5
        assert game.freeze_remaining[chess.BLACK] == 5
    def test_each_cast_costs_one_charge(self):
        game = SpellChessGame()
        # White starts with 5 freeze spells
        assert game.freeze_remaining[chess.WHITE] == 5
        # White uses one freeze spell
        game.cast_freeze(chess.E4)
        # There should be 4 left now
        assert game.freeze_remaining[chess.WHITE] == 4
    def test_cannot_freeze_with_zero_charges(self):
        game = SpellChessGame()
        game.freeze_remaining[chess.WHITE] = 0 
        assert game.cast_freeze(chess.E4) is False

class TestFreezeCasting:
    def test_cannot_freeze_twice_in_one_turn(self):
        game = SpellChessGame()
        
        # the first cast should succeed
        first_cast = game.cast_freeze(chess.E4)
        assert first_cast is True
        
        #the second cast in the same turn should fail
        second_cast = game.cast_freeze(chess.D7)
        assert second_cast is False, "Should not be able to cast Freeze twice in one turn"
    
    def test_cannot_freeze_after_move(self):
        game = SpellChessGame()

        # make a move
        game.make_move(chess.E2,chess.E4)

        # attempt to cast spell. Black should be the one using this spell since white's turn is over
        success = game.cast_freeze(chess.D7)

        assert game.freeze_remaining[chess.WHITE] == 5, "White should have all 5 freeze spells"

    def test_freeze_targets_correct_3x3_area(self):
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

    def test_freeze_squares_in_corner(self):
        game = SpellChessGame()
        game.cast_freeze(chess.A8)

        assert len(game.freeze_effect_squares) == 4

    def test_freeze_squares_in_edge(self):
        game = SpellChessGame()
        game.cast_freeze(chess.A4)

        assert len(game.freeze_effect_squares) == 6


class TestFreezeCooldown:
    def test_size_cooldown_after_freeze(self):
        game = SpellChessGame()

        #White uses a freeze and cool down should be 3
        game.cast_freeze(chess.D7)

        assert game.freeze_cooldown[chess.WHITE] == 3
    
    def test_cooldown_decrement_on_turn(self):
        game = SpellChessGame()

        game.cast_freeze(chess.D7)

        init_cooldown = game.freeze_cooldown[chess.WHITE]

        # make a move so that its back to white's turn and we can check if cooldown went down
        game.make_move(chess.E2,chess.E4)
        game.make_move(chess.E7,chess.E6)

        assert game.freeze_cooldown[chess.WHITE] == (init_cooldown - 1)

    def test_caster_waits_for_cooldown_to_freeze(self):
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
