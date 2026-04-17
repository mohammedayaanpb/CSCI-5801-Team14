#!/usr/bin/env python3
"""
Minimal GUI: play Human vs Stockfish using python-chess + Qt (PySide6).

Controls:
- Click a piece square, then click a destination square.
- New Game resets.

Requires:
- Stockfish installed (e.g. `brew install stockfish`)
- PySide6 installed in the venv (`pip install PySide6`)

Run:
  ./.venv/bin/python gui_play_vs_stockfish_qt.py
  ./.venv/bin/python gui_play_vs_stockfish_qt.py --human black --time 0.2 --skill 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
from PySide6 import QtCore, QtGui, QtWidgets

from spell_logic import SpellChessGame, squares_in_3x3


# Board colors (cream + brown)
BOARD_LIGHT = "#f0d9b5"
BOARD_DARK = "#b58863"


def piece_svg_path(piece: chess.Piece) -> Path:
    code = ("w" if piece.color == chess.WHITE else "b") + {
        chess.PAWN: "P",
        chess.KNIGHT: "N",
        chess.BISHOP: "B",
        chess.ROOK: "R",
        chess.QUEEN: "Q",
        chess.KING: "K",
    }[piece.piece_type]
    return Path(__file__).with_name("assets") / "pieces" / "cburnett" / f"{code}.svg"


@dataclass(frozen=True)
class Config:
    engine_cmd: str
    human_color: chess.Color
    think_time_s: float
    skill: int | None
    mode: str  # "pvc" or "pvp"
    variant: str  # fixed to "spell" (we no longer expose Classic)
    white_name: str
    black_name: str
    human_name: str
    engine_name: str
    analyse: bool
    analyse_time_s: float


def parse_args(argv: list[str]) -> Config:
    p = argparse.ArgumentParser(description="GUI Human vs Engine (python-chess + Qt).")
    p.add_argument(
        "--mode",
        choices=["pvc", "pvp"],
        default="pvc",
        help="pvc = player vs computer (default), pvp = player vs player.",
    )
    p.add_argument("--engine", default="stockfish", help="UCI engine command or full path.")
    p.add_argument("--human", choices=["white", "black"], default="white", help="Your side.")
    p.add_argument("--time", type=float, default=0.2, help="Engine think time per move (sec).")
    p.add_argument("--skill", type=int, default=None, help="Optional Stockfish skill (0-20).")
    p.add_argument(
        "--analysis",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show analysis sidebar (default: enabled). Use --no-analysis to disable.",
    )
    p.add_argument(
        "--analysis-time",
        type=float,
        default=0.2,
        help="Analysis think time per position in seconds (default: 0.2).",
    )
    a = p.parse_args(argv)
    # Names are filled by the startup dialog. We still provide defaults so
    # CLI usage remains possible.
    human_color = chess.WHITE if a.human == "white" else chess.BLACK
    engine_name = "Stockfish" if a.engine == "stockfish" else a.engine
    if a.mode == "pvc":
        human_name = "Human"
        if human_color == chess.WHITE:
            white_name, black_name = human_name, engine_name
        else:
            white_name, black_name = engine_name, human_name
    else:
        human_name = ""
        white_name, black_name = "White", "Black"

    return Config(
        engine_cmd=a.engine,
        human_color=human_color,
        think_time_s=a.time,
        skill=a.skill,
        mode=a.mode,
        variant="spell",
        white_name=white_name,
        black_name=black_name,
        human_name=human_name,
        engine_name=engine_name,
        analyse=a.analysis,
        analyse_time_s=a.analysis_time,
    )


def resolve_engine_cmd(cmd: str) -> str | None:
    if "/" in cmd or " " in cmd:
        return cmd
    return shutil.which(cmd)


def default_stats_path() -> Path:
    """
    Cross-platform, per-user persistent location.

    Uses Qt's standard app data location (no hard-coded OS paths).
    """
    base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppDataLocation)
    d = Path(base) / "python-chess-gui"
    d.mkdir(parents=True, exist_ok=True)
    return d / "stats.json"


def normalize_player_name(name: str, fallback: str) -> str:
    cleaned = " ".join((name or "").strip().split())
    return cleaned if cleaned else fallback


class StartDialog(QtWidgets.QDialog):
    def __init__(self, defaults: Config, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Start game")

        self.mode_pvc = QtWidgets.QRadioButton("Player vs Computer (PvC)")
        self.mode_pvp = QtWidgets.QRadioButton("Player vs Player (PvP)")
        (self.mode_pvc if defaults.mode == "pvc" else self.mode_pvp).setChecked(True)

        mode_box = QtWidgets.QGroupBox("Game")
        mode_layout = QtWidgets.QVBoxLayout(mode_box)
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        mode_layout.addWidget(self.mode_pvc)
        mode_layout.addWidget(self.mode_pvp)

        # PvC options
        self.human_name = QtWidgets.QLineEdit(defaults.human_name or "Human")
        self.human_color = QtWidgets.QComboBox()
        self.human_color.addItems(["White", "Black"])
        self.human_color.setCurrentText("White" if defaults.human_color == chess.WHITE else "Black")
        self.engine_name = QtWidgets.QLineEdit(defaults.engine_name or "Stockfish")

        pvc_box = QtWidgets.QGroupBox("PvC settings")
        pvc_form = QtWidgets.QFormLayout(pvc_box)
        pvc_form.addRow("Your name:", self.human_name)
        pvc_form.addRow("You play as:", self.human_color)
        pvc_form.addRow("Computer name:", self.engine_name)

        # PvP options
        self.white_name = QtWidgets.QLineEdit(defaults.white_name or "Player 1")
        self.black_name = QtWidgets.QLineEdit(defaults.black_name or "Player 2")

        pvp_box = QtWidgets.QGroupBox("PvP settings")
        pvp_form = QtWidgets.QFormLayout(pvp_box)
        pvp_form.addRow("White player:", self.white_name)
        pvp_form.addRow("Black player:", self.black_name)

        self._pvc_box = pvc_box
        self._pvp_box = pvp_box

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(mode_box)
        layout.addWidget(pvc_box)
        layout.addWidget(pvp_box)
        layout.addWidget(buttons)

        self.mode_pvc.toggled.connect(self._sync_visibility)
        self._sync_visibility()

    def _sync_visibility(self) -> None:
        is_pvc = self.mode_pvc.isChecked()
        self._pvc_box.setVisible(is_pvc)
        self._pvp_box.setVisible(not is_pvc)

    def get_selection(self) -> dict:
        variant = "spell"
        is_pvc = self.mode_pvc.isChecked()
        if is_pvc:
            human = normalize_player_name(self.human_name.text(), "Human")
            engine = normalize_player_name(self.engine_name.text(), "Stockfish")
            human_color = chess.WHITE if self.human_color.currentText() == "White" else chess.BLACK
            if human_color == chess.WHITE:
                white_name, black_name = human, engine
            else:
                white_name, black_name = engine, human
            return {
                "mode": "pvc",
                "variant": variant,
                "human_color": human_color,
                "human_name": human,
                "engine_name": engine,
                "white_name": white_name,
                "black_name": black_name,
            }

        white = normalize_player_name(self.white_name.text(), "Player 1")
        black = normalize_player_name(self.black_name.text(), "Player 2")
        return {
            "mode": "pvp",
            "variant": variant,
            "human_color": chess.WHITE,
            "human_name": "",
            "engine_name": "",
            "white_name": white,
            "black_name": black,
        }


class BoardButton(QtWidgets.QPushButton):
    def __init__(self, square: chess.Square, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.square = square
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setIconSize(QtCore.QSize(64, 64))


class GameTab(QtWidgets.QWidget):
    """
    A background-painted container for the board, so the game tab looks polished.
    Draws a dark gradient + subtle chess watermark behind the centered board.
    """

    def __init__(self, board_widget: QtWidgets.QWidget, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._board_widget = board_widget
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(board_widget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Background gradient
        r = self.rect()
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0.0, QtGui.QColor("#1f1f22"))
        grad.setColorAt(1.0, QtGui.QColor("#2c2c31"))
        p.fillRect(r, grad)

        # Subtle watermark (chess knight)
        side = min(r.width(), r.height())
        font = QtGui.QFont()
        font.setPointSizeF(max(80.0, side * 0.55))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(255, 255, 255, 18))
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "♞")

        super().paintEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.game = SpellChessGame()
        self.board = self.game.board
        self.selected_from: chess.Square | None = None
        self.last_move: chess.Move | None = None
        self._result_recorded_for_game: tuple[str, int] | None = None  # (fen, ply)
        self.engine: chess.engine.SimpleEngine | None = None
        self.engine_busy = False
        self.setWindowTitle("python-chess GUI")

        self.stats_path = default_stats_path()
        # migrate old stats file if present
        old = Path(__file__).with_name(".gui_stats.json")
        if not self.stats_path.exists() and old.exists():
            try:
                self.stats_path.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        self.stats = self._load_stats()

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(22)

        self.new_game_btn = QtWidgets.QPushButton("New Game")
        self.new_game_btn.clicked.connect(self.new_game)

        self.freeze_btn = QtWidgets.QPushButton("Freeze")
        self.freeze_btn.clicked.connect(self._toggle_freeze_targeting)
        self.freeze_btn.setVisible(True)

        self.freeze_info = QtWidgets.QLabel("")
        self.freeze_info.setMinimumHeight(22)
        self.freeze_info.setVisible(True)

        self.jump_btn = QtWidgets.QPushButton("Jump")
        self.jump_btn.clicked.connect(self._toggle_jump_targeting)
        self.jump_btn.setVisible(True)

        self.jump_info = QtWidgets.QLabel("")
        self.jump_info.setMinimumHeight(22)
        self.jump_info.setVisible(True)

        self._jump_targeting: bool = False
        self.jump_source: chess.Square | None = None

        self.analysis_help_btn = QtWidgets.QPushButton("What is this?")
        self.analysis_help_btn.clicked.connect(self._show_analysis_help)
        self.analysis_help_btn.setEnabled(self.cfg.analyse)

        self.auto_analyse_cb = QtWidgets.QCheckBox("Auto-analyse")
        self.auto_analyse_cb.setChecked(self.cfg.analyse)
        self.auto_analyse_cb.setEnabled(self.cfg.analyse)

        self.analysis_time = QtWidgets.QDoubleSpinBox()
        self.analysis_time.setDecimals(2)
        self.analysis_time.setSingleStep(0.1)
        self.analysis_time.setRange(0.05, 10.0)
        self.analysis_time.setValue(self.cfg.analyse_time_s)
        self.analysis_time.setSuffix(" s")
        self.analysis_time.setEnabled(self.cfg.analyse)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.new_game_btn)
        top.addWidget(self.freeze_btn)
        top.addWidget(self.freeze_info)
        top.addWidget(self.jump_btn)
        top.addWidget(self.jump_info)
        top.addWidget(self.analysis_help_btn)
        top.addWidget(self.auto_analyse_cb)
        top.addWidget(QtWidgets.QLabel("Analysis:"))
        top.addWidget(self.analysis_time)
        top.addStretch(1)
        top.addWidget(self.status, 1)

        # Board grid
        self.board_grid = QtWidgets.QGridLayout()
        self.board_grid.setSpacing(0)
        self.board_grid.setContentsMargins(0, 0, 0, 0)

        self.board_widget = QtWidgets.QWidget()
        self.board_widget.setLayout(self.board_grid)
        self.board_widget.setContentsMargins(0, 0, 0, 0)

        # Board frame adds coordinates around the board (a-h / 1-8).
        self.board_frame = QtWidgets.QWidget()
        frame = QtWidgets.QGridLayout(self.board_frame)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(4)

        coord_font = QtGui.QFont()
        coord_font.setPointSize(11)
        coord_font.setBold(True)

        # Top letters (a-h)
        for file in range(8):
            lbl = QtWidgets.QLabel(chr(ord("a") + file))
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(coord_font)
            lbl.setStyleSheet("color: rgba(255,255,255,0.75);")
            frame.addWidget(lbl, 0, file + 1)

        # Bottom letters (a-h)
        for file in range(8):
            lbl = QtWidgets.QLabel(chr(ord("a") + file))
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(coord_font)
            lbl.setStyleSheet("color: rgba(255,255,255,0.75);")
            frame.addWidget(lbl, 9, file + 1)

        # Left ranks (8-1) and right ranks (8-1)
        for r in range(8):
            rank_label = str(8 - r)
            left = QtWidgets.QLabel(rank_label)
            left.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            left.setFont(coord_font)
            left.setStyleSheet("color: rgba(255,255,255,0.75);")
            frame.addWidget(left, r + 1, 0)

            right = QtWidgets.QLabel(rank_label)
            right.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            right.setFont(coord_font)
            right.setStyleSheet("color: rgba(255,255,255,0.75);")
            frame.addWidget(right, r + 1, 9)

        # Center board
        frame.addWidget(self.board_widget, 1, 1, 8, 8)

        # Corners (spacers)
        for (rr, cc) in [(0, 0), (0, 9), (9, 0), (9, 9)]:
            spacer = QtWidgets.QLabel("")
            frame.addWidget(spacer, rr, cc)

        # Tooltip guide
        self.board_frame.setToolTip(
            "Board coordinates:\n"
            "- Columns are a–h (left to right)\n"
            "- Rows are 1–8 (bottom to top)\n"
            "Example: e4 means column 'e' and row '4'."
        )

        # Game tab container (centers a perfectly square board + paints background)
        self.game_tab = GameTab(self.board_frame)
        # Keep square sizes uniform on resize (event filter uses this widget).
        self.game_tab.installEventFilter(self)

        # Analysis tab UI (table like a sheet)
        self.analysis_eval = QtWidgets.QLabel("Eval (White): —")
        self.analysis_eval.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.analysis_eval.setMinimumHeight(22)
        self.analysis_pv = QtWidgets.QLabel("Best line: —")
        self.analysis_pv.setWordWrap(True)
        self.analysis_pv.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.analysis_pv.setMinimumHeight(44)

        self.analysis_table = QtWidgets.QTableWidget(0, 3)
        self.analysis_table.setHorizontalHeaderLabels(["Move", "White", "Black"])
        self.analysis_table.verticalHeader().setVisible(False)
        self.analysis_table.setShowGrid(True)
        self.analysis_table.setAlternatingRowColors(True)
        self.analysis_table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.analysis_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.analysis_table.horizontalHeader().setStretchLastSection(True)
        self.analysis_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.analysis_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.analysis_table.setStyleSheet(
            "QTableWidget { gridline-color: rgba(255,255,255,0.14); }"
            "QHeaderView::section { background-color: #2f2f2f; padding: 6px; border: 1px solid rgba(255,255,255,0.12); }"
        )

        analysis_tab = QtWidgets.QWidget()
        at = QtWidgets.QVBoxLayout(analysis_tab)
        at.addWidget(self.analysis_eval)
        at.addWidget(self.analysis_pv)
        at.addWidget(self.analysis_table, 1)

        # Stats tab
        self.stats_header = QtWidgets.QLabel("")
        self.stats_header.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stats_header.setMinimumHeight(22)

        self.reset_stats_btn = QtWidgets.QPushButton("Reset stats")
        self.reset_stats_btn.clicked.connect(self._reset_stats)

        self.show_stats_path_btn = QtWidgets.QPushButton("Show data location")
        self.show_stats_path_btn.clicked.connect(self._show_stats_path)

        self.stats_table = QtWidgets.QTableWidget(0, 8)
        self.stats_table.setHorizontalHeaderLabels(
            ["Player", "Mode", "Games", "W", "L", "D", "As White", "As Black"]
        )
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setShowGrid(True)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.stats_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.stats_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.stats_table.setSortingEnabled(True)
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        for col in range(2, 8):
            self.stats_table.horizontalHeader().setSectionResizeMode(
                col, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        self.stats_table.setStyleSheet(
            "QTableWidget { gridline-color: rgba(255,255,255,0.14); }"
            "QHeaderView::section { background-color: #2f2f2f; padding: 6px; border: 1px solid rgba(255,255,255,0.12); }"
        )

        stats_tab = QtWidgets.QWidget()
        st = QtWidgets.QVBoxLayout(stats_tab)
        st.addWidget(self.stats_header)
        st.addWidget(self.stats_table, 1)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.show_stats_path_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.reset_stats_btn)
        st.addLayout(btn_row)
        st.addStretch(1)

        # Tabs like a browser (click inside same window)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.game_tab, "Game")
        if self.cfg.analyse:
            self.tabs.addTab(analysis_tab, "Analysis")
        self.tabs.addTab(stats_tab, "Stats")

        root = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(root)
        v.addLayout(top)
        v.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

        self.buttons: dict[chess.Square, BoardButton] = {}
        self._build_board_grid()
        self._update_square_sizes()

        if self.cfg.mode == "pvc" or self.cfg.analyse:
            self._start_engine()

        self.last_analysis_eval_text: str = "—"
        self.last_analysis_pv_text: str = "—"
        self._on_turn_start()  # initialize per-turn state/cooldowns
        self._refresh()

        # If engine should move first.
        if self.cfg.mode == "pvc":
            QtCore.QTimer.singleShot(0, self._maybe_engine_move)
        if self.cfg.analyse and self.auto_analyse_cb.isChecked():
            QtCore.QTimer.singleShot(0, self._analyse_now)
        self._refresh_stats_ui()
        # Do NOT auto-open analysis; user can click the tab.

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            if self.engine is not None:
                self.engine.quit()
        except Exception:
            pass
        super().closeEvent(event)

    def _build_board_grid(self) -> None:
        # rank 8 at top row 0
        for rank in range(7, -1, -1):
            for file in range(8):
                sq = chess.square(file, rank)
                btn = BoardButton(sq)
                btn.clicked.connect(lambda _=False, s=sq: self.on_square_clicked(s))
                self.buttons[sq] = btn
                row = 7 - rank
                col = file
                self.board_grid.addWidget(btn, row, col)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.game_tab and event.type() == QtCore.QEvent.Type.Resize:
            self._update_square_sizes()
        return super().eventFilter(obj, event)

    def _update_square_sizes(self) -> None:
        # Make the board perfectly square and each of the 64 squares equal sized.
        rect = self.game_tab.contentsRect()
        w = max(1, rect.width())
        h = max(1, rect.height())
        # Account for coordinate frame spacing and labels; board itself remains 8x8 squares.
        square = max(24, min(w, h) // 10)
        icon = max(16, int(square * 0.9))

        # Force the board area to be exactly 8x8 squares (prevents any gaps).
        self.board_widget.setFixedSize(square * 8, square * 8)

        for btn in self.buttons.values():
            btn.setFixedSize(square, square)
            btn.setIconSize(QtCore.QSize(icon, icon))

    def _start_engine(self) -> None:
        cmd = resolve_engine_cmd(self.cfg.engine_cmd)
        if not cmd:
            QtWidgets.QMessageBox.critical(
                self,
                "Engine not found",
                "Could not find 'stockfish' on PATH.\n\n"
                "Install it with:\n  brew install stockfish\n\n"
                "Or run with:\n  --engine /full/path/to/stockfish",
            )
            raise SystemExit(2)

        self.engine = chess.engine.SimpleEngine.popen_uci(cmd)
        if self.cfg.skill is not None:
            try:
                self.engine.configure({"Skill Level": self.cfg.skill})
            except chess.engine.EngineError:
                pass

    def new_game(self) -> None:
        self._maybe_record_result()
        self.game.new_game()
        self.board = self.game.board
        self.selected_from = None
        self.last_move = None
        self._result_recorded_for_game = None
        self._on_turn_start()
        self._refresh()
        if self.cfg.mode == "pvc":
            QtCore.QTimer.singleShot(0, self._maybe_engine_move)
        if self.cfg.analyse and self.auto_analyse_cb.isChecked():
            QtCore.QTimer.singleShot(0, self._analyse_now)

    def on_square_clicked(self, square: chess.Square) -> None:
        if self.board.is_game_over(claim_draw=True):
            return
        if self.engine_busy:
            return

        # Spell Chess: Freeze targeting (cast before moving)
        if self.cfg.variant == "spell" and self.game.freeze_targeting:
            self._cast_freeze(center=square)
            return

        # Spell Chess: Jump targeting (two clicks: piece then destination)
        if self.cfg.variant == "spell" and self._jump_targeting:
            if self.jump_source is None:
                piece = self.board.piece_at(square)
                if piece and piece.color == self.board.turn:
                    self.jump_source = square
                    self._set_status(f"Jump: piece selected. Now click an empty destination.")
                else:
                    self._set_status("Jump: click one of your own pieces first.")
                self._refresh()
                return
            else:
                if self.game.cast_jump(self.jump_source, square):
                    self._set_status("Jump cast. Now make your move.")
                else:
                    self._set_status("Jump failed — invalid destination.")
                self.jump_source = None
                self._jump_targeting = False
                self._refresh()
                return

        if self.cfg.mode == "pvc" and self.board.turn != self.cfg.human_color:
            return

        if self.selected_from is None:
            piece = self.board.piece_at(square)
            if not piece:
                return
            if self.cfg.mode == "pvc" and piece.color != self.cfg.human_color:
                return
            if self.cfg.variant == "spell" and self.game.is_frozen(square, self.board.turn):
                self._set_status("That piece is frozen this turn.")
                return
            self.selected_from = square
            self._refresh()
            return

        # Second click: try to make a move.
        from_sq = self.selected_from
        self.selected_from = None

        if not self.game.make_move(from_sq, square):
            self._set_status("Illegal move.")
            self._refresh()
            return

        self.last_move = self.board.move_stack[-1] if self.board.move_stack else None
        self._refresh()
        if self.cfg.mode == "pvc":
            QtCore.QTimer.singleShot(0, self._maybe_engine_move)
        if self.cfg.analyse and self.auto_analyse_cb.isChecked():
            QtCore.QTimer.singleShot(0, self._analyse_now)

    def _set_status(self, msg: str) -> None:
        self.status.setText(msg)

    def _refresh(self) -> None:
        light = BOARD_LIGHT
        dark = BOARD_DARK
        # Highlights (kept subtle)
        selected = "#cdd26a"
        lastmove = "#f6f669"
        legal = "#e8ed8a"
        freeze_active = (
            self.game.freeze_effect_color is not None and self.game.freeze_effect_plies_left > 0
        )

        legal_to: set[chess.Square] = set()
        can_move_now = (not self.engine_busy) and (
            self.cfg.mode == "pvp" or self.board.turn == self.cfg.human_color
        )
        if self.selected_from is not None and can_move_now:
            for m in self.board.legal_moves:
                if m.from_square == self.selected_from:
                    if self.cfg.variant == "spell" and self.game.is_frozen(m.from_square, self.board.turn):
                        continue
                    legal_to.add(m.to_square)

        for sq, btn in self.buttons.items():
            is_light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 0
            piece = self.board.piece_at(sq)

            bg = light if is_light else dark
            frozen_here = freeze_active and (sq in self.game.freeze_effect_squares)

            if self.last_move is not None and sq in (self.last_move.from_square, self.last_move.to_square):
                bg = lastmove
            if sq in legal_to:
                bg = legal
            if self.selected_from == sq:
                bg = selected

            # Spell Chess: frozen ("spelled") area indicator
            # Keep legal/selected/lastmove colors visible: use a subtle border always,
            # and apply only a *light* tint when not conflicting with other highlights.
            border_css = "border: 1px solid rgba(0,0,0,0.08);"
            if frozen_here:
                border_alpha = 0.70 if self.game.freeze_effect_color == self.board.turn else 0.40
                border_css = f"border: 2px solid rgba(120, 180, 255, {border_alpha});"

                # Only tint if this square isn't already a move/selection highlight.
                is_last = self.last_move is not None and sq in (
                    self.last_move.from_square,
                    self.last_move.to_square,
                )
                if (not is_last) and (sq not in legal_to) and (self.selected_from != sq):
                    tint_alpha = 0.22 if self.game.freeze_effect_color == self.board.turn else 0.12
                    bg = f"rgba(120, 180, 255, {tint_alpha})"

            if piece is None:
                btn.setIcon(QtGui.QIcon())
            else:
                svg = piece_svg_path(piece)
                if svg.exists():
                    btn.setIcon(QtGui.QIcon(str(svg)))
                else:
                    btn.setIcon(QtGui.QIcon())

            btn.setStyleSheet(
                "QPushButton {"
                f"background-color: {bg};"
                f"{border_css}"
                "}"
                "QPushButton:pressed { border: 2px solid rgba(0,0,0,0.35); }"
            )

        # Status line.
        if self.board.is_game_over(claim_draw=True):
            outcome = self.board.outcome(claim_draw=True)
            if outcome is None:
                self._set_status("Game over.")
            else:
                if outcome.winner is None:
                    res = "Draw"
                elif outcome.winner == chess.WHITE:
                    res = "White wins"
                else:
                    res = "Black wins"
                self._set_status(f"Game over: {outcome.termination.name} — {res}")
            self._maybe_record_result()
        else:
            turn = "White" if self.board.turn == chess.WHITE else "Black"
            you = "White" if self.cfg.human_color == chess.WHITE else "Black"
            check = " (check)" if self.board.is_check() else ""
            if self.cfg.mode == "pvp":
                self._set_status(f"Mode: PvP. Turn: {turn}{check}.")
            else:
                self._set_status(f"Mode: PvC. Turn: {turn}{check}. You are: {you}.")

        if self.cfg.analyse:
            self._refresh_analysis_table()

        self._refresh_spell_ui()

    def _movelist_rows(self) -> list[tuple[int, str, str]]:
        """
        Returns rows: (move_number, white_san, black_san) where black_san can be "".
        """
        b = chess.Board()
        rows: list[tuple[int, str, str]] = []
        move_no = 1
        white_san = ""
        for mv in self.board.move_stack:
            san = b.san(mv)
            if b.turn == chess.WHITE:
                white_san = san
            else:
                rows.append((move_no, white_san, san))
                move_no += 1
                white_san = ""
            b.push(mv)
        if white_san:
            rows.append((move_no, white_san, ""))
        return rows

    def _format_score(self, score: chess.engine.PovScore) -> str:
        # Always show from White's perspective.
        s = score.white()
        mate = s.mate()
        if mate is not None:
            return f"M{mate}"
        cp = s.score(mate_score=100000)
        if cp is None:
            return "—"
        return f"{cp/100.0:+.2f}"

    def _pv_to_san(self, pv: list[chess.Move]) -> str:
        b = self.board.copy(stack=False)
        san_moves: list[str] = []
        for mv in pv[:12]:
            try:
                san_moves.append(b.san(mv))
            except Exception:
                san_moves.append(mv.uci())
            b.push(mv)
        return " ".join(san_moves)

    def _analyse_now(self) -> None:
        if not self.cfg.analyse:
            return
        if self.engine is None:
            return
        if self.engine_busy:
            return
        if self.board.is_game_over(claim_draw=True):
            self.last_analysis_eval_text = "—"
            self.last_analysis_pv_text = "—"
            self.analysis_eval.setText("Eval (White): — (game over)")
            self.analysis_pv.setText("Best line: —")
            return

        self.engine_busy = True
        try:
            self.analysis_eval.setText("Eval (White): …")
            self.analysis_pv.setText("Best line: …")
            QtWidgets.QApplication.processEvents()

            limit = chess.engine.Limit(time=float(self.analysis_time.value()))
            info = self.engine.analyse(self.board, limit)
            score = info.get("score")
            pv = info.get("pv", [])
            if score is not None:
                self.last_analysis_eval_text = self._format_score(score)
            else:
                self.last_analysis_eval_text = "—"
            self.last_analysis_pv_text = self._pv_to_san(pv) if pv else "—"
            self.analysis_eval.setText(f"Eval (White): {self.last_analysis_eval_text}")
            self.analysis_pv.setText(f"Best line: {self.last_analysis_pv_text}")
        except Exception as e:
            self.last_analysis_eval_text = "—"
            self.last_analysis_pv_text = f"(error: {e})"
            self.analysis_eval.setText(f"Eval (White): {self.last_analysis_eval_text}")
            self.analysis_pv.setText(f"Best line: {self.last_analysis_pv_text}")
        finally:
            self.engine_busy = False

    def _show_analysis_help(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "How to read analysis",
            "Here’s what the analysis means:\n\n"
            "- Eval (White): how good the position is for White.\n"
            "  +0.90 means White is better by about 0.9 pawns.\n"
            "  -1.20 means Black is better by about 1.2 pawns.\n"
            "  M3 / M-3 means checkmate in 3 moves (for the side indicated).\n\n"
            "- Best line: Stockfish’s suggested next moves (a short sequence).\n"
            "  Example: 'd5 c4' means it recommends ...d5, then White might play c4.\n\n"
            "- Moves: the moves played so far in standard chess notation.\n\n"
            "Tip: Increase 'Analysis' time to get stronger/more stable evaluations.",
        )

    def _load_stats(self) -> dict:
        default = {"version": 2, "players": {}}
        try:
            if self.stats_path.exists():
                data = json.loads(self.stats_path.read_text(encoding="utf-8"))
                data.setdefault("version", 2)
                data.setdefault("players", {})
                return data
        except Exception:
            pass
        return default

    def _save_stats(self) -> None:
        try:
            self.stats_path.write_text(json.dumps(self.stats, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _reset_stats(self) -> None:
        self.stats = {"version": 2, "players": {}}
        self._save_stats()
        self._refresh_stats_ui()

    def _ensure_player(self, name: str) -> dict:
        players = self.stats.setdefault("players", {})
        name = normalize_player_name(name, "Player")
        p = players.setdefault(
            name,
            {
                "pvp": {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0},
                "pvc": {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0},
                "spell_pvp": {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0},
                "spell_pvc": {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0},
            },
        )
        p.setdefault("pvp", {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0})
        p.setdefault("pvc", {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0})
        p.setdefault("spell_pvp", {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0})
        p.setdefault("spell_pvc", {"games": 0, "wins": 0, "losses": 0, "draws": 0, "as_white": 0, "as_black": 0})
        return p

    def _refresh_stats_ui(self) -> None:
        players = self.stats.get("players", {}) or {}
        mode_title = "PvP" if self.cfg.mode == "pvp" else "PvC"
        variant_title = "Spell" if self.cfg.variant == "spell" else "Classic"
        self.stats_header.setText(
            f"Current game: {variant_title} {mode_title} — White: {self.cfg.white_name} vs Black: {self.cfg.black_name}"
        )

        # Build rows: one per (player, mode)
        rows: list[tuple[str, str, dict]] = []
        for player_name, pdata in sorted(players.items(), key=lambda kv: kv[0].lower()):
            for mode_key in ("spell_pvp", "spell_pvc"):
                m = pdata.get(mode_key)
                if not isinstance(m, dict):
                    continue
                rows.append((player_name, mode_key, m))

        self.stats_table.setSortingEnabled(False)
        self.stats_table.setRowCount(len(rows))
        highlight_players = {self.cfg.white_name, self.cfg.black_name}

        def mode_label(m: str) -> str:
            return {
                "spell_pvp": "Spell PvP",
                "spell_pvc": "Spell PvC",
            }.get(m, m)

        for i, (player_name, mode_key, m) in enumerate(rows):
            def cell(text: str) -> QtWidgets.QTableWidgetItem:
                it = QtWidgets.QTableWidgetItem(text)
                it.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
                return it

            def num(n: int) -> QtWidgets.QTableWidgetItem:
                it = QtWidgets.QTableWidgetItem(str(int(n)))
                it.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                return it

            self.stats_table.setItem(i, 0, cell(player_name))
            self.stats_table.setItem(i, 1, cell(mode_label(mode_key)))
            self.stats_table.setItem(i, 2, num(m.get("games", 0)))
            self.stats_table.setItem(i, 3, num(m.get("wins", 0)))
            self.stats_table.setItem(i, 4, num(m.get("losses", 0)))
            self.stats_table.setItem(i, 5, num(m.get("draws", 0)))
            self.stats_table.setItem(i, 6, num(m.get("as_white", 0)))
            self.stats_table.setItem(i, 7, num(m.get("as_black", 0)))

            if player_name in highlight_players:
                for c in range(8):
                    it = self.stats_table.item(i, c)
                    if it is not None:
                        it.setBackground(QtGui.QColor(255, 255, 255, 18))

        self.stats_table.setSortingEnabled(True)

    def _show_stats_path(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Stats data location",
            f"Stats are stored here (per user):\n\n{self.stats_path}\n\n"
            "This path is not hard-coded; it uses the OS standard app data folder.",
        )

    def _maybe_record_result(self) -> None:
        if not self.board.is_game_over(claim_draw=True):
            return
        outcome = self.board.outcome(claim_draw=True)
        if outcome is None:
            return

        # Prevent double counting on multiple refreshes.
        key = (self.board.fen(), len(self.board.move_stack))
        if self._result_recorded_for_game == key:
            return
        self._result_recorded_for_game = key

        stats_mode = f"spell_{self.cfg.mode}"

        white_player = self._ensure_player(self.cfg.white_name)
        black_player = self._ensure_player(self.cfg.black_name)
        wm = white_player[stats_mode]
        bm = black_player[stats_mode]

        wm["games"] = int(wm.get("games", 0)) + 1
        bm["games"] = int(bm.get("games", 0)) + 1
        wm["as_white"] = int(wm.get("as_white", 0)) + 1
        bm["as_black"] = int(bm.get("as_black", 0)) + 1

        if outcome.winner is None:
            wm["draws"] = int(wm.get("draws", 0)) + 1
            bm["draws"] = int(bm.get("draws", 0)) + 1
        elif outcome.winner == chess.WHITE:
            wm["wins"] = int(wm.get("wins", 0)) + 1
            bm["losses"] = int(bm.get("losses", 0)) + 1
        else:
            bm["wins"] = int(bm.get("wins", 0)) + 1
            wm["losses"] = int(wm.get("losses", 0)) + 1

        self._save_stats()
        self._refresh_stats_ui()

    def _refresh_analysis_table(self) -> None:
        if not self.cfg.analyse:
            return
        rows = self._movelist_rows()
        self.analysis_table.setRowCount(len(rows))
        for i, (move_no, w, b) in enumerate(rows):
            self.analysis_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(move_no)))
            self.analysis_table.setItem(i, 1, QtWidgets.QTableWidgetItem(w))
            self.analysis_table.setItem(i, 2, QtWidgets.QTableWidgetItem(b))
        self.analysis_eval.setText(f"Eval (White): {self.last_analysis_eval_text}")
        self.analysis_pv.setText(f"Best line: {self.last_analysis_pv_text}")

    # -----------------------
    # Spell Chess: Freeze
    # -----------------------
    def _refresh_spell_ui(self) -> None:
        self.freeze_info.setText(self.game.freeze_info_text())
        self.jump_info.setText(self.game.jump_info_text())
        turn = self.board.turn
        rem = self.game.freeze_remaining.get(turn, 0)
        cd = self.game.freeze_cooldown.get(turn, 0)
        if cd > 0:
            self.freeze_btn.setEnabled(False)
        else:
            self.freeze_btn.setEnabled((rem > 0) and (not self.game.spell_casted_this_turn))
        j_rem = self.game.jump_remaining.get(turn, 0)
        j_cd = self.game.jump_cooldown.get(turn, 0)
        if j_cd > 0:
            self.jump_btn.setEnabled(False)
        else:
            self.jump_btn.setEnabled((j_rem > 0) and (not self.game.jump_casted_this_turn))

    def _toggle_freeze_targeting(self) -> None:
        if self.cfg.variant != "spell":
            return
        if self.board.is_game_over(claim_draw=True):
            return
        if self.engine_busy:
            return
        if self.game.spell_casted_this_turn:
            return
        if self.game.freeze_cooldown.get(self.board.turn, 0) > 0:
            return
        if self.game.freeze_remaining.get(self.board.turn, 0) <= 0:
            return

        self.game.freeze_targeting = not self.game.freeze_targeting
        if self.game.freeze_targeting:
            self.selected_from = None
            self._set_status("Freeze: click a square to freeze its 3×3 area (affects opponent next turn).")
        else:
            self._set_status("")
        self._refresh()

    def _cast_freeze(self, center: chess.Square) -> None:
        if self.game.cast_freeze(center):
            self._set_status("Freeze cast. Now make your move.")
        self._refresh()

    def _toggle_jump_targeting(self) -> None:
        if self.cfg.variant != "spell":
            return
        if self.board.is_game_over(claim_draw=True):
            return
        if self.engine_busy:
            return
        if self.game.jump_casted_this_turn:
            return
        if self.game.jump_cooldown.get(self.board.turn, 0) > 0:
            return
        if self.game.jump_remaining.get(self.board.turn, 0) <= 0:
            return

        if self._jump_targeting:
            self._jump_targeting = False
            self.jump_source = None
            self._set_status("")
        else:
            self.selected_from = None
            self.game.freeze_targeting = False
            self._jump_targeting = True
            self.jump_source = None
            self._set_status("Jump: click one of your pieces, then click an empty destination.")
        self._refresh()

    def _on_turn_start(self) -> None:
        if self.cfg.variant == "spell":
            self.game.on_turn_start()
            self._refresh_spell_ui()

    def _maybe_engine_move(self) -> None:
        if self.cfg.mode != "pvc":
            return
        if self.engine is None:
            return
        if self.board.is_game_over(claim_draw=True):
            return
        if self.board.turn == self.cfg.human_color:
            return
        if self.engine_busy:
            return

        self.engine_busy = True
        try:
            self._set_status("Engine thinking…")
            self._refresh()
            QtWidgets.QApplication.processEvents()

            if self.cfg.variant == "spell" and self.game.freeze_effect_color == self.board.turn and self.game.freeze_effect_plies_left > 0:
                legal = self.game.get_legal_moves()
                if legal:
                    # Ask engine for a move, but if it picks a frozen piece (rare), fall back.
                    limit = chess.engine.Limit(time=self.cfg.think_time_s)
                    result = self.engine.play(self.board, limit)
                    if result.move in legal:
                        move = result.move
                    else:
                        move = legal[0]
                else:
                    # Should be extremely rare; fall back to normal engine move.
                    limit = chess.engine.Limit(time=self.cfg.think_time_s)
                    move = self.engine.play(self.board, limit).move
            else:
                limit = chess.engine.Limit(time=self.cfg.think_time_s)
                move = self.engine.play(self.board, limit).move

            self.board.push(move)
            self.last_move = move
            self.game.after_move_pushed()
        except Exception as e:
            self._set_status(f"Engine error: {e}")
        finally:
            self.engine_busy = False
            self._refresh()

 


def main(argv: list[str]) -> int:
    defaults = parse_args(argv)
    app = QtWidgets.QApplication([])

    # Always ask at startup (as requested), but prefill from CLI defaults.
    dlg = StartDialog(defaults)
    if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
        return 0
    sel = dlg.get_selection()

    cfg = Config(
        engine_cmd=defaults.engine_cmd,
        human_color=sel["human_color"],
        think_time_s=defaults.think_time_s,
        skill=defaults.skill,
        mode=sel["mode"],
        variant=sel["variant"],
        white_name=sel["white_name"],
        black_name=sel["black_name"],
        human_name=sel["human_name"],
        engine_name=sel["engine_name"],
        analyse=defaults.analyse,
        analyse_time_s=defaults.analyse_time_s,
    )

    w = MainWindow(cfg)
    w.resize(640, 700)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


