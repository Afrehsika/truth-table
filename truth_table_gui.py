"""
Pygame Graphical User Interface (GUI) for the Truth Table to Logic Circuit System
=================================================================================
An interactive 60-FPS Digital Logic CAD & Synthesis Workbench built with Pygame.

Features:
  - Screen-Aware Window Sizing (fits 1366x768, 1280x720, and 1080p+ screens cleanly
    above the Windows taskbar without cutting off bottom buttons or right-side outputs)
  - Auto-Fitting Circuit Schematic (automatically scales horizontal & vertical spacing
    so all Primary Inputs, Gate Levels, and Primary Outputs fit inside the viewport)
  - Auto-Fitting Truth Table Grid (fits all 16 rows of 4 inputs + 8+ outputs like
    a,b,c,d -> s,a,b,c,d,e,f,g without needing to scroll)
  - Zero broken Unicode/emoji boxes (uses crisp vector-drawn checkmarks & ASCII labels)
  - Multiple fast ways to change Truth Table values:
      * Left-click any output cell to toggle 0 -> 1 -> X
      * Click & drag across output cells to paint values rapidly
      * Hover over any cell and press '0', '1', or 'X' on the keyboard
"""

from __future__ import annotations
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import pygame

from truth_table_system import (
    CircuitSolution,
    GateInstance,
    design_circuit,
    design_circuit_auto,
)

# Gates that AUTO mode may additionally use when ticked (the basic 2-input libraries are chosen by the system)
AUTO_EXTRA_GATES = ["MUX2", "AND3", "OR3", "NAND3", "NOR3", "XOR3", "AND4", "OR4", "IMP"]


# ============================================================================
# COLOR PALETTE (Modern Hardware CAD Dark Theme)
# ============================================================================
COL_BG = (15, 23, 42)            # Slate 900
COL_PANEL = (30, 41, 59)         # Slate 800
COL_CARD = (39, 52, 73)          # Slate 750
COL_HEADER = (11, 17, 32)        # Deep Navy
COL_BORDER = (71, 85, 105)       # Slate 600
COL_TEXT = (248, 250, 252)       # Slate 50
COL_MUTED = (148, 163, 184)      # Slate 400
COL_ACCENT = (59, 130, 246)      # Blue 500
COL_HIGH = (34, 197, 94)         # Emerald 500 (Logic 1)
COL_HIGH_BG = (20, 83, 45)       # Emerald 900
COL_LOW = (100, 116, 139)        # Slate 500 (Logic 0)
COL_LOW_BG = (30, 41, 59)
COL_DC = (245, 158, 11)          # Amber 500 (Don't Care X)
COL_DC_BG = (120, 53, 15)

GATE_FILL_COLORS: Dict[str, Tuple[int, int, int]] = {
    "AND": (30, 58, 138),
    "AND3": (30, 58, 138),
    "AND4": (30, 58, 138),
    "OR": (49, 46, 129),
    "OR3": (49, 46, 129),
    "OR4": (49, 46, 129),
    "NOT": (112, 26, 117),
    "BUF": (88, 28, 135),
    "NAND": (120, 53, 15),
    "NAND3": (120, 53, 15),
    "NAND4": (120, 53, 15),
    "NOR": (124, 45, 18),
    "NOR3": (124, 45, 18),
    "NOR4": (124, 45, 18),
    "XOR": (6, 95, 70),
    "XOR3": (6, 95, 70),
    "XNOR": (17, 94, 89),
    "MUX2": (88, 28, 135),
    "IMP": (55, 65, 81),
}


@dataclass
class UIButton:
    rect: pygame.Rect
    label: str
    callback: Callable[[], None]
    bg_color: Tuple[int, int, int] = COL_CARD
    fg_color: Tuple[int, int, int] = COL_TEXT
    border_color: Tuple[int, int, int] = COL_BORDER
    active: bool = False
    small: bool = False
    has_check: Optional[bool] = None


@dataclass
class GateNodeVisual:
    gate: GateInstance
    rect: pygame.Rect
    pin_positions: List[Tuple[int, int]]  # Input pin coordinates (left edge)
    out_position: Tuple[int, int]         # Output pin coordinate (right edge)


class PygameTruthTableApp:
    """Interactive Pygame GUI for Truth Table Synthesis, Gate Count & Wiring."""

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        # Center window on desktop and keep it comfortably above the OS taskbar
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        pygame.init()
        info = pygame.display.Info()
        desk_w = info.current_w if info.current_w > 0 else 1366
        desk_h = info.current_h if info.current_h > 0 else 768

        if width is None:
            width = min(1260, max(1000, desk_w - 60))
        if height is None:
            height = min(690, max(620, desk_h - 86))

        pygame.display.set_caption(
            "Truth Table to Logic Circuit Synthesizer — Gate Count, Input Routing & Wiring"
        )
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        # Fonts (clean standard fonts without broken emoji glyphs)
        self.font_title = pygame.font.SysFont("segoeui", 17, bold=True)
        self.font_sec = pygame.font.SysFont("segoeui", 13, bold=True)
        self.font_ui = pygame.font.SysFont("segoeui", 12)
        self.font_ui_bold = pygame.font.SysFont("segoeui", 12, bold=True)
        self.font_small = pygame.font.SysFont("segoeui", 11)
        self.font_tiny = pygame.font.SysFont("consolas", 11, bold=True)
        self.font_mono = pygame.font.SysFont("consolas", 12)
        self.font_mono_bold = pygame.font.SysFont("consolas", 13, bold=True)
        self.font_kpi = pygame.font.SysFont("segoeui", 18, bold=True)

        # Logic State
        self.input_names: List[str] = ["A", "B", "Cin"]
        self.output_names: List[str] = ["Sum", "Cout"]
        self.in_text_str: str = "A, B, Cin"
        self.out_text_str: str = "Sum, Cout"
        self.active_textbox: Optional[str] = None  # "inputs" or "outputs"

        self.available_gates: List[str] = [
            "AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "MUX2",
            "AND3", "OR3", "NAND3", "NOR3", "XOR3", "AND4", "OR4", "IMP",
        ]
        self.selected_blocks: Dict[str, bool] = {
            g: (g in ("AND", "OR", "NOT", "XOR")) for g in self.available_gates
        }

        # table_values[row_idx][out_idx] in {"0", "1", "X"}
        self.table_values: List[List[str]] = []
        self.tt_scroll_y: int = 0
        self.full_tt_scroll_y: int = 0
        self.wiring_scroll_y: int = 0
        self.report_scroll_y: int = 0

        # Active Right-Panel Tab:
        # 0 = Schematic, 1 = Wiring & Routing Tables, 2 = Full Truth Table Editor, 3 = Full Report
        self.active_tab: int = 0
        self.status_banner: str = (
            "Ready — Click or drag output cells (or press 0, 1, X while hovering) to edit truth table."
        )
        self.status_color: Tuple[int, int, int] = COL_ACCENT

        # Paint-drag state for fast multi-cell editing in Truth Table
        self.painting_value: Optional[str] = None
        self.painted_cells: set = set()
        self.hovered_cell: Optional[Tuple[int, int]] = None

        # Synthesis & Simulation State
        self.current_solution: Optional[CircuitSolution] = None
        self.cached_routing: Dict[str, List[str]] = {}
        self.cached_loads: Dict[str, List[str]] = {}
        self.cached_exprs: Dict[str, str] = {}
        self.cached_report_lines: List[str] = []
        self.sim_inputs: Dict[str, int] = {}
        self.anim_phase: float = 0.0

        # AUTO mode: the system chooses the gate library that gives the fewest gates
        self.auto_mode: bool = True
        self._synth_lock = threading.Lock()
        self._synth_gen: int = 0
        self._synth_busy: bool = False
        self._pending_job: Optional[Dict] = None
        self._synth_result: Optional[Tuple[int, Dict]] = None

        # Schematic Layout & Dragging State
        self.gate_visuals: Dict[str, GateNodeVisual] = {}
        self.input_node_rects: Dict[str, pygame.Rect] = {}
        self.input_out_pos: Dict[str, Tuple[int, int]] = {}
        self.output_node_rects: Dict[str, pygame.Rect] = {}
        self.output_in_pos: Dict[str, Tuple[int, int]] = {}
        self.dragging_gate_id: Optional[str] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.schem_pan: List[int] = [0, 0]
        self.panning_schem: bool = False
        self.pan_start: Tuple[int, int] = (0, 0)
        self.hovered_gate_id: Optional[str] = None

        # Interactive hitboxes rebuilt per frame
        self.buttons: List[UIButton] = []
        self.tt_cell_rects: List[Tuple[pygame.Rect, int, int]] = []
        self.tt_row_in_rects: List[Tuple[pygame.Rect, int]] = []
        self.in_box_rect = pygame.Rect(0, 0, 0, 0)
        self.out_box_rect = pygame.Rect(0, 0, 0, 0)
        self.tt_viewport_rect = pygame.Rect(0, 0, 0, 0)
        self.Sidebar_w = 435
        self.right_viewport_rect = pygame.Rect(
            self.Sidebar_w + 18, 138, self.width - self.Sidebar_w - 26, self.height - 164
        )

        # Load initial demo circuit (blocking so the window opens with a circuit already drawn)
        self.load_example("full_adder", blocking=True)

    # ========================================================================
    # EXAMPLE PRESETS & TABLE MANAGEMENT
    # ========================================================================

    def load_example(self, name: str, blocking: bool = False) -> None:
        if name == "full_adder":
            self.input_names = ["A", "B", "Cin"]
            self.output_names = ["Sum", "Cout"]
            vals = [
                ["0", "0"], ["1", "0"], ["1", "0"], ["0", "1"],
                ["1", "0"], ["0", "1"], ["0", "1"], ["1", "1"],
            ]
            blocks = ["AND", "OR", "NOT", "XOR"]
            msg = "Loaded 1-Bit Full Adder (Inputs: A, B, Cin -> Outputs: Sum, Cout)"
        elif name == "nand_xor":
            self.input_names = ["A", "B"]
            self.output_names = ["Y"]
            vals = [["0"], ["1"], ["1"], ["0"]]
            blocks = ["NAND"]
            msg = "Loaded 2-Input XOR synthesized using ONLY 2-input NAND gates (4 gates)"
        elif name == "majority3":
            self.input_names = ["A", "B", "C"]
            self.output_names = ["M"]
            vals = [["0"], ["0"], ["0"], ["1"], ["0"], ["1"], ["1"], ["1"]]
            blocks = ["AND", "OR", "NOT"]
            msg = "Loaded 3-Input Majority Voter (Inputs: A, B, C -> Output: M)"
        elif name == "seven_seg":
            self.input_names = ["a", "b", "c", "d"]
            self.output_names = ["s", "a", "b", "c", "d", "e", "f", "g"]
            vals = [
                ["1", "1", "1", "1", "1", "1", "1", "0"],  # 0
                ["1", "0", "1", "1", "0", "0", "0", "0"],  # 1
                ["1", "1", "1", "0", "1", "1", "0", "1"],  # 2
                ["1", "1", "1", "1", "1", "0", "0", "1"],  # 3
                ["1", "0", "1", "1", "0", "0", "1", "1"],  # 4
                ["1", "1", "0", "1", "1", "0", "1", "1"],  # 5
                ["1", "1", "0", "1", "1", "1", "1", "1"],  # 6
                ["1", "1", "1", "1", "0", "0", "0", "0"],  # 7
                ["1", "1", "1", "1", "1", "1", "1", "1"],  # 8
                ["1", "1", "1", "1", "1", "0", "1", "1"],  # 9
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 10
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 11
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 12
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 13
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 14
                ["0", "X", "X", "X", "X", "X", "X", "X"],  # 15
            ]
            blocks = ["AND", "OR", "NOT"]
            msg = "Loaded 4-Input 8-Output 7-Segment Decoder (Inputs: a,b,c,d -> Outputs: s,a,b,c,d,e,f,g)"
        elif name == "dont_care":
            self.input_names = ["A", "B", "C"]
            self.output_names = ["Y"]
            vals = [["0"], ["0"], ["1"], ["X"], ["0"], ["0"], ["1"], ["1"]]
            blocks = ["AND", "OR", "NOT"]
            msg = "Loaded Truth Table with Don't Care ('X') optimization"
        else:
            return

        self.in_text_str = ", ".join(self.input_names)
        self.out_text_str = ", ".join(self.output_names)
        # Demos let the system pick the simplest gates, except the NAND-only XOR demo
        self.auto_mode = (name != "nand_xor")
        self.set_block_preset(blocks, auto_synth=False, manual=False)
        self.table_values = vals
        self.tt_scroll_y = 0
        self.full_tt_scroll_y = 0
        self.sim_inputs = {inp: 0 for inp in self.input_names}
        self.synthesize_circuit(blocking=blocking)
        if blocking:
            self.status_banner = msg
            self.status_color = COL_ACCENT

    def apply_io_names(self) -> None:
        in_raw = [x.strip() for x in self.in_text_str.replace(",", " ").split() if x.strip()]
        out_raw = [x.strip() for x in self.out_text_str.replace(",", " ").split() if x.strip()]
        if not in_raw:
            self.status_banner = "Error: Please enter at least 1 input variable name."
            self.status_color = COL_DC
            return
        if len(in_raw) > 6:
            self.status_banner = "Warning: Max 6 inputs supported in GUI table (64 rows)."
            self.status_color = COL_DC
            return
        if not out_raw:
            out_raw = ["Y"]

        same_dims = (len(in_raw) == len(self.input_names)) and (len(out_raw) == len(self.output_names))
        old_vals = self.table_values
        self.input_names = in_raw
        self.output_names = out_raw
        self.in_text_str = ", ".join(self.input_names)
        self.out_text_str = ", ".join(self.output_names)

        num_rows = 1 << len(self.input_names)
        n_out = len(self.output_names)
        if same_dims and len(old_vals) == num_rows:
            self.table_values = [list(r) for r in old_vals]
        else:
            # Start fresh with all '0' when changing number of inputs or outputs
            self.table_values = [["0" for _ in range(n_out)] for _ in range(num_rows)]

        self.tt_scroll_y = 0
        self.full_tt_scroll_y = 0
        self.sim_inputs = {inp: 0 for inp in self.input_names}
        self.synthesize_circuit()

    def _on_click_synthesize_button(self) -> None:
        """When user clicks the big Synthesize button, switch to Schematic tab if on full editor."""
        if self.active_tab == 2:
            self.active_tab = 0
        self.synthesize_circuit()

    def set_block_preset(self, gates: Sequence[str], auto_synth: bool = True, manual: bool = True) -> None:
        upper = {g.upper() for g in gates}
        for g in self.available_gates:
            self.selected_blocks[g] = g.upper() in upper
        if manual:
            self.auto_mode = False  # choosing gates yourself switches AUTO off
        if auto_synth:
            self.synthesize_circuit()

    def toggle_auto_mode(self) -> None:
        self.auto_mode = not self.auto_mode
        self.synthesize_circuit()

    def quick_fill_outputs(self, mode: str) -> None:
        for r in range(len(self.table_values)):
            for j in range(len(self.output_names)):
                curr = self.table_values[r][j]
                if mode == "INV":
                    self.table_values[r][j] = "1" if curr == "0" else ("0" if curr == "1" else "X")
                else:
                    self.table_values[r][j] = mode
        self.synthesize_circuit()

    # ========================================================================
    # CIRCUIT SYNTHESIS & AUTO-FITTING SCHEMATIC LAYOUT
    # ========================================================================

    def synthesize_circuit(self, blocking: bool = False) -> None:
        """
        Start synthesis. By default it runs in a background thread so the window never freezes;
        the finished circuit is picked up by `_poll_synthesis()` every frame.
        With `blocking=True` it runs immediately (used at start-up and in tests).
        """
        if not self.auto_mode:
            blocks = [g for g, enabled in self.selected_blocks.items() if enabled]
            if not blocks:
                self.status_banner = "Select at least one Building Block gate (or turn AUTO on)!"
                self.status_color = COL_DC
                return
        else:
            blocks = []

        table_data: List[Union[str, List[str]]] = []
        for row in self.table_values:
            if len(self.output_names) == 1:
                table_data.append(row[0])
            else:
                table_data.append(list(row))

        job = {
            "inputs": list(self.input_names),
            "outputs": list(self.output_names),
            "table": table_data,
            "auto": self.auto_mode,
            "blocks": blocks,
            "extras": [g for g in AUTO_EXTRA_GATES if self.selected_blocks.get(g, False)],
        }

        if blocking:
            self._synth_gen += 1
            job["gen"] = self._synth_gen
            self._apply_synthesis_result(job["gen"], self._run_synthesis_job(job))
            return

        with self._synth_lock:
            self._synth_gen += 1
            job["gen"] = self._synth_gen
            self._pending_job = job
            start_worker = not self._synth_busy
            if start_worker:
                self._synth_busy = True
        self.status_banner = (
            "Searching for the simplest circuit (trying several gate libraries)..."
            if self.auto_mode
            else "Synthesizing circuit..."
        )
        self.status_color = COL_ACCENT
        if start_worker:
            threading.Thread(target=self._synthesis_worker, daemon=True).start()

    @staticmethod
    def _run_synthesis_job(job: Dict) -> Dict:
        """Runs in a worker thread (or inline): do all the heavy work, touch no pygame objects."""
        t0 = time.perf_counter()
        try:
            if job["auto"]:
                sol = design_circuit_auto(
                    job["inputs"], job["outputs"], job["table"],
                    extra_blocks=job["extras"], time_budget=3.0,
                )
            else:
                sol = design_circuit(
                    input_names=job["inputs"],
                    output_names=job["outputs"],
                    table_data=job["table"],
                    building_blocks=job["blocks"],
                    time_budget=1.5,
                )
            return {
                "ok": True,
                "sol": sol,
                "routing": sol.get_input_routing(),
                "loads": sol.get_signal_load_map(),
                "exprs": sol.get_boolean_expressions(),
                "report": sol.format_report(include_mermaid=True).splitlines(),
                "seconds": time.perf_counter() - t0,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "seconds": time.perf_counter() - t0}

    def _synthesis_worker(self) -> None:
        while True:
            with self._synth_lock:
                job = self._pending_job
                self._pending_job = None
                if job is None:
                    self._synth_busy = False
                    return
            result = self._run_synthesis_job(job)
            with self._synth_lock:
                self._synth_result = (job["gen"], result)

    def _poll_synthesis(self) -> None:
        """Main thread: apply a finished background result (ignored if a newer job was requested)."""
        with self._synth_lock:
            item = self._synth_result
            if item is None or item[0] != self._synth_gen:
                return
            self._synth_result = None
        self._apply_synthesis_result(item[0], item[1])

    def _apply_synthesis_result(self, gen: int, result: Dict) -> None:
        if not result["ok"]:
            self.status_banner = f"Synthesis Error: {result['error']}"
            self.status_color = (239, 68, 68)
            return
        sol: CircuitSolution = result["sol"]
        self.current_solution = sol
        self.cached_routing = result["routing"]
        self.cached_loads = result["loads"]
        self.cached_exprs = result["exprs"]
        self.cached_report_lines = result["report"]
        self.schem_pan = [0, 0]
        self._build_schematic_layout(sol)
        self.status_banner = (
            f"Synthesized in {result['seconds']:.2f}s: {sol.total_gate_count} gate(s), "
            f"{sol.max_logic_depth} level(s) [{sol.synthesis_method}]"
        )
        self.status_color = COL_HIGH

    def _build_schematic_layout(self, sol: CircuitSolution) -> None:
        """
        Compute positions of Primary Inputs, Gate Nodes by Level, and Primary Outputs
        so that the entire circuit fits cleanly inside `self.right_viewport_rect`.
        """
        self.gate_visuals.clear()
        self.input_node_rects.clear()
        self.input_out_pos.clear()
        self.output_node_rects.clear()
        self.output_in_pos.clear()

        vp = self.right_viewport_rect
        pad_x = 18
        top_y = vp.top + 38
        avail_w = max(420, vp.width - 2 * pad_x)
        avail_h = max(300, vp.height - 52)

        max_lvl = sol.max_logic_depth
        total_cols = max_lvl + 2  # Col 0 = Inputs, Cols 1..max_lvl = Gates, Col max_lvl+1 = Outputs

        in_box_w = 82
        out_box_w = 96
        gate_w = min(110, max(82, (avail_w - in_box_w - out_box_w) // max(2, total_cols)))

        # Center x of Column 0 (Inputs) and Final Column (Outputs) guaranteed inside vp!
        left_cx = vp.left + pad_x + in_box_w // 2
        right_cx = vp.right - pad_x - out_box_w // 2
        col_span = max(120, right_cx - left_cx)

        def col_center_x(col_idx: int) -> int:
            if total_cols <= 1:
                return left_cx
            return int(left_cx + (col_idx / (total_cols - 1)) * col_span)

        # Column 0: Primary Inputs (+ constants if used)
        used_consts = sorted(
            {sig for g in sol.gates for sig in g.input_signals if sig in ("0", "1")}
            | {drv for drv in sol.output_drivers.values() if drv in ("0", "1")}
        )
        col0_items = list(sol.spec.input_names) + used_consts
        n_in_items = max(1, len(col0_items))
        in_step_y = min(72, max(38, avail_h // n_in_items))
        in_box_h = min(36, max(26, in_step_y - 8))

        for idx, name in enumerate(col0_items):
            cx = col_center_x(0)
            cy = top_y + in_box_h // 2 + idx * in_step_y
            rect = pygame.Rect(cx - in_box_w // 2, cy - in_box_h // 2, in_box_w, in_box_h)
            self.input_node_rects[name] = rect
            self.input_out_pos[name] = (rect.right, rect.centery)

        # Columns 1 .. max_level: Gate Instances
        gates_by_lvl: Dict[int, List[GateInstance]] = {lvl: [] for lvl in range(1, max_lvl + 1)}
        for g in sol.gates:
            gates_by_lvl.setdefault(g.level, []).append(g)

        for lvl in range(1, max_lvl + 1):
            g_list = gates_by_lvl.get(lvl, [])
            if not g_list:
                continue
            cx = col_center_x(lvl)
            n_g = len(g_list)
            g_step_y = min(88, max(46, avail_h // max(1, n_g)))
            for g_idx, g in enumerate(g_list):
                h = min(g_step_y - 6, max(40, 18 * len(g.input_signals) + 12))
                cy = top_y + h // 2 + g_idx * g_step_y
                rect = pygame.Rect(cx - gate_w // 2, cy - h // 2, gate_w, h)
                vis = self._compute_gate_pins(g, rect)
                self.gate_visuals[g.gate_id] = vis

        # Final Column: Primary Outputs
        out_cx = col_center_x(max_lvl + 1)
        n_out = max(1, len(sol.spec.output_names))
        out_step_y = min(72, max(36, avail_h // n_out))
        out_box_h = min(38, max(26, out_step_y - 6))
        for o_idx, out_name in enumerate(sol.spec.output_names):
            cy = top_y + out_box_h // 2 + o_idx * out_step_y
            rect = pygame.Rect(out_cx - out_box_w // 2, cy - out_box_h // 2, out_box_w, out_box_h)
            self.output_node_rects[out_name] = rect
            self.output_in_pos[out_name] = (rect.left, rect.centery)

    def _compute_gate_pins(self, g: GateInstance, rect: pygame.Rect) -> GateNodeVisual:
        n_pins = len(g.input_signals)
        pins: List[Tuple[int, int]] = []
        for i in range(n_pins):
            py = int(rect.top + (i + 1) * rect.height / (n_pins + 1))
            pins.append((rect.left, py))
        out_pos = (rect.right, rect.centery)
        return GateNodeVisual(gate=g, rect=rect, pin_positions=pins, out_position=out_pos)

    def _evaluate_live_signals(self, sol: CircuitSolution) -> Dict[str, int]:
        signals: Dict[str, int] = {
            inp: int(self.sim_inputs.get(inp, 0)) for inp in sol.spec.input_names
        }
        signals["0"] = 0
        signals["1"] = 1
        for g in sol.gates:
            in_vals = [signals[s] for s in g.input_signals]
            signals[g.output_signal] = int(g.block.func(*in_vals))
        return signals

    # ========================================================================
    # DRAWING & RENDERING (60 FPS)
    # ========================================================================

    def draw(self) -> None:
        self.screen.fill(COL_BG)
        self.buttons.clear()
        self.tt_cell_rects.clear()
        self.tt_row_in_rects.clear()

        self._draw_top_header()
        self._draw_left_sidebar()
        self._draw_right_workspace()
        self._draw_status_bar()

        mx, my = pygame.mouse.get_pos()
        self.hovered_cell = None
        for rect, r, j in self.tt_cell_rects:
            if rect.collidepoint((mx, my)):
                self.hovered_cell = (r, j)
                break

        pygame.display.flip()

    def _draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        callback: Callable[[], None],
        bg: Tuple[int, int, int] = COL_CARD,
        fg: Tuple[int, int, int] = COL_TEXT,
        border: Tuple[int, int, int] = COL_BORDER,
        active: bool = False,
        small: bool = False,
        has_check: Optional[bool] = None,
    ) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)
        draw_bg = COL_ACCENT if active else (
            tuple(min(255, c + 22) for c in bg) if hovered else bg
        )
        draw_border = (147, 197, 253) if (active or hovered) else border

        pygame.draw.rect(self.screen, draw_bg, rect, border_radius=5)
        pygame.draw.rect(self.screen, draw_border, rect, width=1, border_radius=5)

        font = self.font_small if small else self.font_ui_bold
        surf = font.render(label, True, fg)

        if has_check is not None:
            # Draw vector checkbox on left side of pill
            box_s = 10
            bx = rect.left + 7
            by = rect.centery - box_s // 2
            chk_rect = pygame.Rect(bx, by, box_s, box_s)
            pygame.draw.rect(self.screen, COL_HEADER, chk_rect, border_radius=2)
            pygame.draw.rect(
                self.screen, COL_HIGH if has_check else COL_MUTED, chk_rect, width=1, border_radius=2
            )
            if has_check:
                pygame.draw.lines(
                    self.screen,
                    (134, 239, 172),
                    False,
                    [(bx + 2, by + 5), (bx + 4, by + 8), (bx + 8, by + 2)],
                    2,
                )
            self.screen.blit(surf, (bx + box_s + 6, rect.centery - surf.get_height() // 2))
        else:
            self.screen.blit(
                surf,
                (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2),
            )
        self.buttons.append(UIButton(rect, label, callback, bg, fg, border, active, small, has_check))

    def _draw_top_header(self) -> None:
        header_rect = pygame.Rect(0, 0, self.width, 42)
        pygame.draw.rect(self.screen, COL_HEADER, header_rect)
        pygame.draw.line(self.screen, COL_BORDER, (0, 42), (self.width, 42), 1)

        # Draw vector lightning bolt icon
        bolt_pts = [(18, 9), (11, 22), (17, 22), (13, 33), (24, 19), (18, 19)]
        pygame.draw.polygon(self.screen, (250, 204, 21), bolt_pts)

        title_surf = self.font_title.render(
            "Truth Table to Logic Circuit Synthesizer (Pygame CAD)", True, COL_TEXT
        )
        self.screen.blit(title_surf, (32, 9))

        examples = [
            ("1-Bit Full Adder", "full_adder"),
            ("XOR (NAND Only)", "nand_xor"),
            ("3-In Majority", "majority3"),
            ("7-Seg (a..d -> s,a..g)", "seven_seg"),
            ("Don't Care (X)", "dont_care"),
        ]
        bx = self.width - 10
        for label, key in reversed(examples):
            bw = self.font_small.size(label)[0] + 14
            bx -= bw
            rect = pygame.Rect(bx, 8, bw, 26)
            self._draw_button(
                rect,
                label,
                callback=lambda k=key: self.load_example(k),
                bg=(30, 41, 59),
                small=True,
            )
            bx -= 5

        lbl = self.font_small.render("Load Demo:", True, COL_MUTED)
        self.screen.blit(lbl, (bx - lbl.get_width() - 4, 13))

    def _draw_left_sidebar(self) -> None:
        sidebar_w = self.Sidebar_w
        sidebar_rect = pygame.Rect(8, 48, sidebar_w, self.height - 76)
        pygame.draw.rect(self.screen, COL_PANEL, sidebar_rect, border_radius=8)
        pygame.draw.rect(self.screen, COL_BORDER, sidebar_rect, width=1, border_radius=8)

        x0 = sidebar_rect.left + 10
        y = sidebar_rect.top + 6
        inner_w = sidebar_w - 20

        # --- SECTION 1: Inputs & Outputs ---
        sec1 = self.font_sec.render("1. Inputs & Outputs (Click Box to Edit)", True, COL_TEXT)
        self.screen.blit(sec1, (x0, y))
        y += 19

        lbl_in = self.font_small.render("Inputs:", True, COL_MUTED)
        self.screen.blit(lbl_in, (x0, y + 3))
        self.in_box_rect = pygame.Rect(x0 + 50, y, inner_w - 126, 22)
        in_active = self.active_textbox == "inputs"
        pygame.draw.rect(self.screen, COL_HEADER, self.in_box_rect, border_radius=4)
        pygame.draw.rect(
            self.screen,
            COL_ACCENT if in_active else COL_BORDER,
            self.in_box_rect,
            width=2 if in_active else 1,
            border_radius=4,
        )
        in_txt = self.in_text_str + ("|" if in_active and (pygame.time.get_ticks() // 500) % 2 == 0 else "")
        self.screen.blit(self.font_mono.render(in_txt, True, COL_TEXT), (self.in_box_rect.x + 6, y + 3))

        y += 24
        lbl_out = self.font_small.render("Outputs:", True, COL_MUTED)
        self.screen.blit(lbl_out, (x0, y + 3))
        self.out_box_rect = pygame.Rect(x0 + 50, y, inner_w - 126, 22)
        out_active = self.active_textbox == "outputs"
        pygame.draw.rect(self.screen, COL_HEADER, self.out_box_rect, border_radius=4)
        pygame.draw.rect(
            self.screen,
            COL_ACCENT if out_active else COL_BORDER,
            self.out_box_rect,
            width=2 if out_active else 1,
            border_radius=4,
        )
        out_txt = self.out_text_str + ("|" if out_active and (pygame.time.get_ticks() // 500) % 2 == 0 else "")
        self.screen.blit(self.font_mono.render(out_txt, True, COL_TEXT), (self.out_box_rect.x + 6, y + 3))

        rebuild_rect = pygame.Rect(x0 + inner_w - 70, y - 24, 70, 46)
        self._draw_button(
            rebuild_rect,
            "Rebuild",
            callback=self.apply_io_names,
            bg=(37, 99, 235),
        )
        y += 26

        pygame.draw.line(self.screen, COL_BORDER, (x0, y), (x0 + inner_w, y), 1)
        y += 5

        # --- SECTION 2: Allowed Building Blocks ---
        sec2 = self.font_sec.render("2. Building Blocks", True, COL_TEXT)
        self.screen.blit(sec2, (x0, y))
        auto_lbl = "AUTO: simplest circuit  [ON]" if self.auto_mode else "AUTO: simplest circuit  [OFF]"
        auto_w = self.font_small.size(auto_lbl)[0] + 18
        auto_rect = pygame.Rect(x0 + inner_w - auto_w, y - 2, auto_w, 20)
        self._draw_button(
            auto_rect,
            auto_lbl,
            callback=self.toggle_auto_mode,
            bg=(22, 101, 52) if self.auto_mode else (51, 65, 85),
            border=COL_HIGH if self.auto_mode else COL_BORDER,
            small=True,
        )
        y += 20

        presets = [
            ("AND/OR/NOT", ["AND", "OR", "NOT"]),
            ("NAND Only", ["NAND"]),
            ("NOR Only", ["NOR"]),
            ("+XOR", ["AND", "OR", "NOT", "XOR", "XNOR"]),
            ("MUX2+NOT", ["MUX2", "NOT"]),
            ("All", self.available_gates),
        ]
        px = x0
        for p_lbl, p_gates in presets:
            pw = self.font_small.size(p_lbl)[0] + 10
            prect = pygame.Rect(px, y, pw, 19)
            self._draw_button(
                prect,
                p_lbl,
                callback=lambda g=p_gates: self.set_block_preset(g),
                bg=(51, 65, 85),
                small=True,
            )
            px += pw + 4
        y += 22

        cols = 4
        cell_w = (inner_w - (cols - 1) * 5) // cols
        cell_h = 20
        for idx, gname in enumerate(self.available_gates):
            r = idx // cols
            c = idx % cols
            gx = x0 + c * (cell_w + 5)
            gy = y + r * (cell_h + 3)
            grect = pygame.Rect(gx, gy, cell_w, cell_h)
            # In AUTO mode the basic gates are chosen by the system; only the extra gates are options
            is_on = self.selected_blocks.get(gname, False)
            if self.auto_mode and gname not in AUTO_EXTRA_GATES:
                is_on = False
                bg_col, fg_col, bd_col = (24, 32, 52), (88, 100, 125), (45, 56, 78)
            else:
                bg_col = (22, 101, 52) if is_on else COL_HEADER
                fg_col = COL_TEXT if is_on else COL_MUTED
                bd_col = COL_HIGH if is_on else COL_BORDER
            self._draw_button(
                grect,
                gname,
                callback=lambda gn=gname: self._toggle_block(gn),
                bg=bg_col,
                fg=fg_col,
                border=bd_col,
                small=True,
                has_check=is_on,
            )
        y += 4 * (cell_h + 3) + 3

        pygame.draw.line(self.screen, COL_BORDER, (x0, y), (x0 + inner_w, y), 1)
        y += 5

        # --- SECTION 3: Auto-Fitting Interactive Truth Table Grid ---
        sec3 = self.font_sec.render("3. Truth Table (Click/Drag or Press 0, 1, X)", True, COL_TEXT)
        self.screen.blit(sec3, (x0, y))

        expand_rect = pygame.Rect(x0 + inner_w - 108, y - 1, 108, 20)
        self._draw_button(
            expand_rect,
            "Full Table View",
            callback=lambda: self._set_tab(2),
            bg=(30, 58, 138),
            small=True,
        )
        y += 20

        qf_items = [("All 0", "0"), ("All 1", "1"), ("All X", "X"), ("Invert", "INV")]
        qx = x0
        for qlbl, qmode in qf_items:
            qw = 54
            qrect = pygame.Rect(qx, y, qw, 19)
            self._draw_button(
                qrect,
                qlbl,
                callback=lambda m=qmode: self.quick_fill_outputs(m),
                bg=(51, 65, 85),
                small=True,
            )
            qx += qw + 5

        hint_s = self.font_small.render("Click row inputs to simulate", True, COL_MUTED)
        self.screen.blit(hint_s, (qx + 4, y + 2))
        y += 22

        # Truth Table Viewport + Synthesize Button guaranteed inside sidebar_rect
        synth_btn_h = 30
        tt_bottom = sidebar_rect.bottom - synth_btn_h - 8
        self.tt_viewport_rect = pygame.Rect(x0, y, inner_w, max(100, tt_bottom - y))
        pygame.draw.rect(self.screen, COL_HEADER, self.tt_viewport_rect, border_radius=5)
        pygame.draw.rect(self.screen, COL_BORDER, self.tt_viewport_rect, width=1, border_radius=5)

        self._draw_truth_table_grid(
            self.tt_viewport_rect,
            scroll_y=self.tt_scroll_y,
            is_full_view=False,
        )

        # Synthesize Button at bottom of sidebar (always above status bar & taskbar)
        synth_rect = pygame.Rect(x0, sidebar_rect.bottom - synth_btn_h - 4, inner_w, synth_btn_h)
        self._draw_button(
            synth_rect,
            "SYNTHESIZE CIRCUIT & WIRING",
            callback=self._on_click_synthesize_button,
            bg=(37, 99, 235),
        )

    def _toggle_block(self, gname: str) -> None:
        self.selected_blocks[gname] = not self.selected_blocks.get(gname, False)
        if gname not in AUTO_EXTRA_GATES:
            self.auto_mode = False  # picking a basic gate yourself switches AUTO off
        self.synthesize_circuit()

    def _draw_truth_table_grid(
        self,
        vp: pygame.Rect,
        scroll_y: int,
        is_full_view: bool = False,
    ) -> None:
        n_in = len(self.input_names)
        n_out = len(self.output_names)
        num_rows = len(self.table_values)

        header_h = 24 if is_full_view else 20
        avail_h = vp.height - header_h - 4
        avail_w = vp.width - 8

        # Dynamically scale row height so all 16 rows fit without scrolling!
        if is_full_view:
            row_h = max(22, min(34, avail_h // max(1, num_rows)))
        else:
            row_h = max(16, min(24, avail_h // max(1, num_rows)))

        idx_col_w = 24 if not is_full_view else 40
        rem_w = avail_w - idx_col_w
        in_col_w = max(20, min(46 if is_full_view else 28, int(rem_w * (n_in / max(1, n_in + n_out * 1.25)))))
        out_col_w = max(24, (rem_w - n_in * in_col_w) // max(1, n_out))

        hx = vp.left + 4
        hy = vp.top + 2

        font_hdr = self.font_ui_bold if is_full_view else self.font_small
        hdr_idx = font_hdr.render("#", True, COL_MUTED)
        self.screen.blit(hdr_idx, (hx + idx_col_w // 2 - hdr_idx.get_width() // 2, hy + 2))

        for i, name in enumerate(self.input_names):
            cx = hx + idx_col_w + i * in_col_w
            s = font_hdr.render(name, True, (147, 197, 253))
            self.screen.blit(s, (cx + in_col_w // 2 - s.get_width() // 2, hy + 2))

        for j, name in enumerate(self.output_names):
            cx = hx + idx_col_w + n_in * in_col_w + j * out_col_w
            lbl = f"Out:{name}" if (is_full_view and out_col_w >= 54) else name
            s = font_hdr.render(lbl, True, (134, 239, 172))
            self.screen.blit(s, (cx + out_col_w // 2 - s.get_width() // 2, hy + 2))

        pygame.draw.line(
            self.screen, COL_BORDER, (vp.left, vp.top + header_h), (vp.right, vp.top + header_h), 1
        )

        rows_clip = pygame.Rect(vp.left + 1, vp.top + header_h + 1, vp.width - 2, vp.height - header_h - 2)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(rows_clip)

        max_scroll = max(0, num_rows * row_h - rows_clip.height)
        if is_full_view:
            self.full_tt_scroll_y = max(0, min(self.full_tt_scroll_y, max_scroll))
            scroll_y = self.full_tt_scroll_y
        else:
            self.tt_scroll_y = max(0, min(self.tt_scroll_y, max_scroll))
            scroll_y = self.tt_scroll_y

        active_sim_row = 0
        for i, name in enumerate(self.input_names):
            active_sim_row = (active_sim_row << 1) | int(self.sim_inputs.get(name, 0))

        font_cell = self.font_mono_bold if (row_h >= 21 or is_full_view) else self.font_tiny

        for r in range(num_rows):
            ry = rows_clip.top + r * row_h - scroll_y
            if ry + row_h < rows_clip.top or ry > rows_clip.bottom:
                continue

            row_rect = pygame.Rect(vp.left + 2, ry, vp.width - 4, row_h - 1)
            if r == active_sim_row:
                pygame.draw.rect(self.screen, (30, 58, 138), row_rect, border_radius=3)
            elif r % 2 == 1:
                pygame.draw.rect(self.screen, (19, 29, 51), row_rect, border_radius=3)

            idx_s = self.font_small.render(str(r), True, COL_MUTED)
            self.screen.blit(
                idx_s,
                (hx + idx_col_w // 2 - idx_s.get_width() // 2, ry + (row_h - idx_s.get_height()) // 2),
            )

            in_group_rect = pygame.Rect(hx + idx_col_w, ry, n_in * in_col_w, row_h - 1)
            self.tt_row_in_rects.append((in_group_rect, r))
            for i in range(n_in):
                bit = (r >> (n_in - 1 - i)) & 1
                cx = hx + idx_col_w + i * in_col_w
                bs = font_cell.render(str(bit), True, COL_HIGH if bit == 1 else COL_TEXT)
                self.screen.blit(
                    bs,
                    (cx + in_col_w // 2 - bs.get_width() // 2, ry + (row_h - bs.get_height()) // 2),
                )

            for j in range(n_out):
                val = self.table_values[r][j]
                cx = hx + idx_col_w + n_in * in_col_w + j * out_col_w
                cell_rect = pygame.Rect(cx + 2, ry + 1, out_col_w - 4, max(12, row_h - 2))
                if val == "1":
                    c_bg, c_fg, c_bd = COL_HIGH_BG, (134, 239, 172), COL_HIGH
                elif val == "0":
                    c_bg, c_fg, c_bd = COL_LOW_BG, COL_TEXT, COL_BORDER
                else:
                    c_bg, c_fg, c_bd = COL_DC_BG, (253, 230, 138), COL_DC

                pygame.draw.rect(self.screen, c_bg, cell_rect, border_radius=3)
                pygame.draw.rect(self.screen, c_bd, cell_rect, width=1, border_radius=3)
                vs = font_cell.render(val, True, c_fg)
                self.screen.blit(
                    vs,
                    (cell_rect.centerx - vs.get_width() // 2, cell_rect.centery - vs.get_height() // 2),
                )
                self.tt_cell_rects.append((cell_rect, r, j))

        if max_scroll > 0:
            sb_h = max(20, int(rows_clip.height * (rows_clip.height / (num_rows * row_h))))
            sb_y = rows_clip.top + int((scroll_y / max_scroll) * (rows_clip.height - sb_h))
            sb_rect = pygame.Rect(vp.right - 5, sb_y, 4, sb_h)
            pygame.draw.rect(self.screen, COL_ACCENT, sb_rect, border_radius=2)

        self.screen.set_clip(old_clip)

    # ========================================================================
    # RIGHT WORKSPACE: KPI BAR + 4 TABS
    # ========================================================================

    def _draw_right_workspace(self) -> None:
        rx = self.Sidebar_w + 16
        rw = self.width - rx - 8
        ry = 48

        sol = self.current_solution
        total_gates = str(sol.total_gate_count) if sol else "-"
        if sol:
            counts = sol.gate_count_by_type()
            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "0 (Direct Wire)"
            depth_str = f"{sol.max_logic_depth} Level(s)"
            ver_str = "PASSED (100%)" if sol.is_verified else "FAILED"
        else:
            breakdown = "-"
            depth_str = "-"
            ver_str = "-"

        kpis = [
            ("TOTAL GATE COUNT", total_gates, COL_ACCENT),
            ("BY BUILDING BLOCK", breakdown, (147, 197, 253)),
            ("LOGIC DEPTH", depth_str, (192, 132, 252)),
            ("VERIFICATION", ver_str, COL_HIGH),
        ]
        card_w = (rw - 3 * 6) // 4
        card_h = 52
        for idx, (title, val, col) in enumerate(kpis):
            cx = rx + idx * (card_w + 6)
            crect = pygame.Rect(cx, ry, card_w, card_h)
            pygame.draw.rect(self.screen, COL_PANEL, crect, border_radius=6)
            pygame.draw.rect(self.screen, COL_BORDER, crect, width=1, border_radius=6)
            ts = self.font_small.render(title, True, COL_MUTED)
            self.screen.blit(ts, (cx + 10, ry + 5))
            font_val = self.font_ui_bold if len(val) > 14 else self.font_kpi
            vs = font_val.render(val, True, col)
            self.screen.blit(vs, (cx + 10, ry + 22))

        ry += card_h + 6

        tabs = [
            ("1. Circuit Schematic", 0),
            ("2. Input Routing & Gate Wiring", 1),
            ("3. Full Truth Table Editor", 2),
            ("4. Full Report", 3),
        ]
        tx = rx
        for t_lbl, t_idx in tabs:
            tw = self.font_ui_bold.size(t_lbl)[0] + 18
            trect = pygame.Rect(tx, ry, tw, 28)
            self._draw_button(
                trect,
                t_lbl,
                callback=lambda idx=t_idx: self._set_tab(idx),
                bg=COL_PANEL,
                active=(self.active_tab == t_idx),
            )
            tx += tw + 5

        if self.active_tab == 0 and sol is not None:
            reset_rect = pygame.Rect(rx + rw - 118, ry + 1, 118, 26)
            self._draw_button(
                reset_rect,
                "Reset Layout",
                callback=lambda: self._reset_schematic_view(sol),
                bg=(51, 65, 85),
                small=True,
            )
        elif self.active_tab in (1, 3) and sol is not None:
            save_rect = pygame.Rect(rx + rw - 132, ry + 1, 132, 26)
            self._draw_button(
                save_rect,
                "Save Report (.txt)",
                callback=self.save_report_to_file,
                bg=(22, 101, 52),
                small=True,
            )

        ry += 32

        new_vp = pygame.Rect(rx, ry, rw, self.height - ry - 28)
        vp_changed = (new_vp.size != self.right_viewport_rect.size)
        self.right_viewport_rect = new_vp
        if vp_changed and sol is not None:
            self._build_schematic_layout(sol)

        pygame.draw.rect(self.screen, COL_HEADER, self.right_viewport_rect, border_radius=8)
        pygame.draw.rect(self.screen, COL_BORDER, self.right_viewport_rect, width=1, border_radius=8)

        if self.active_tab == 2:
            self._draw_full_table_editor_tab(self.right_viewport_rect)
            return

        if sol is None:
            return

        if self.active_tab == 0:
            self._draw_schematic_tab(self.right_viewport_rect, sol)
        elif self.active_tab == 1:
            self._draw_wiring_tables_tab(self.right_viewport_rect, sol)
        elif self.active_tab == 3:
            self._draw_report_tab(self.right_viewport_rect, sol)

    def _reset_schematic_view(self, sol: CircuitSolution) -> None:
        self.schem_pan = [0, 0]
        self._build_schematic_layout(sol)

    def _set_tab(self, idx: int) -> None:
        self.active_tab = idx

    def _draw_full_table_editor_tab(self, vp: pygame.Rect) -> None:
        banner = (
            "FULL-SCREEN TRUTH TABLE MATRIX  —  Left-click or drag across cells to set 0/1/X  |  "
            "Right-click to cycle backwards  |  Hover over any cell & press 0, 1, or X key"
        )
        bs = self.font_small.render(banner, True, (147, 197, 253))
        self.screen.blit(bs, (vp.left + 12, vp.top + 7))

        grid_rect = pygame.Rect(vp.left + 8, vp.top + 28, vp.width - 16, vp.height - 36)
        self._draw_truth_table_grid(grid_rect, scroll_y=self.full_tt_scroll_y, is_full_view=True)

    # ========================================================================
    # TAB 0: INTERACTIVE SCHEMATIC CANVAS + LIVE SIGNAL PULSES
    # ========================================================================

    def _draw_schematic_tab(self, vp: pygame.Rect, sol: CircuitSolution) -> None:
        old_clip = self.screen.get_clip()
        self.screen.set_clip(vp)

        px, py = self.schem_pan
        grid_step = 32
        for gx in range(vp.left + (px % grid_step), vp.right, grid_step):
            pygame.draw.line(self.screen, (19, 28, 49), (gx, vp.top), (gx, vp.bottom), 1)
        for gy in range(vp.top + (py % grid_step), vp.bottom, grid_step):
            pygame.draw.line(self.screen, (19, 28, 49), (vp.left, gy), (vp.right, gy), 1)

        hint = (
            "Click any INPUT box on the left to toggle 0/1 live  |  "
            "Drag any Gate to move  |  Right-click & drag or Scroll Wheel to pan"
        )
        hs = self.font_small.render(hint, True, (147, 197, 253))
        self.screen.blit(hs, (vp.left + 12, vp.top + 8))

        signals = self._evaluate_live_signals(sol)

        source_coords: Dict[str, Tuple[int, int]] = {}
        for name, pos in self.input_out_pos.items():
            source_coords[name] = (pos[0] + px, pos[1] + py)
        for vis in self.gate_visuals.values():
            source_coords[vis.gate.output_signal] = (vis.out_position[0] + px, vis.out_position[1] + py)

        # 1. Draw Wires + Animated Signal Pulses
        wire_idx = 0
        for g in sol.gates:
            vis = self.gate_visuals.get(g.gate_id)
            if not vis:
                continue
            for p_i, sig in enumerate(g.input_signals):
                if sig in source_coords and p_i < len(vis.pin_positions):
                    sx, sy = source_coords[sig]
                    dx, dy = vis.pin_positions[p_i][0] + px, vis.pin_positions[p_i][1] + py
                    is_high = signals.get(sig, 0) == 1
                    highlight = (self.hovered_gate_id == g.gate_id)
                    self._draw_signal_wire(sx, sy, dx, dy, is_high, highlight, wire_idx)
                    wire_idx += 1

        for out_name, drv in sol.output_drivers.items():
            if drv in source_coords and out_name in self.output_in_pos:
                sx, sy = source_coords[drv]
                ox, oy = self.output_in_pos[out_name]
                dx, dy = ox + px, oy + py
                is_high = signals.get(drv, 0) == 1
                self._draw_signal_wire(sx, sy, dx, dy, is_high, False, wire_idx)
                wire_idx += 1

        # 2. Draw Primary Input Switches
        for name, rect in self.input_node_rects.items():
            srect = rect.move(px, py)
            val = signals.get(name, 0)
            is_high = val == 1
            bg = COL_HIGH_BG if is_high else COL_PANEL
            bd = COL_HIGH if is_high else COL_BORDER
            pygame.draw.rect(self.screen, bg, srect, border_radius=6)
            pygame.draw.rect(self.screen, bd, srect, width=2, border_radius=6)

            lbl = f"{name} = {val}" if name in sol.spec.input_names else f"CONST {name}"
            ts = self.font_mono_bold.render(lbl, True, COL_TEXT)
            self.screen.blit(
                ts, (srect.centerx - ts.get_width() // 2, srect.centery - ts.get_height() // 2)
            )
            pygame.draw.circle(self.screen, bd, (srect.right, srect.centery), 4)

        # 3. Draw Logic Gate Nodes
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_gate_id = None
        for g_id, vis in self.gate_visuals.items():
            g = vis.gate
            srect = vis.rect.move(px, py)
            if srect.collidepoint(mouse_pos):
                self.hovered_gate_id = g_id

            out_val = signals.get(g.output_signal, 0)
            is_high = out_val == 1
            fill_col = GATE_FILL_COLORS.get(g.block.name.upper(), COL_CARD)
            bd_col = (134, 239, 172) if self.hovered_gate_id == g_id else (COL_HIGH if is_high else COL_BORDER)

            self._draw_gate_shape(srect, g.block.name.upper(), fill_col, bd_col)

            hdr_s = self.font_ui_bold.render(f"{g.gate_id}: {g.block.name}", True, COL_TEXT)
            self.screen.blit(hdr_s, (srect.centerx - hdr_s.get_width() // 2 + 4, srect.centery - 13))

            net_s = self.font_mono.render(
                f"{g.output_signal}={out_val}",
                True,
                (134, 239, 172) if is_high else COL_MUTED,
            )
            self.screen.blit(net_s, (srect.centerx - net_s.get_width() // 2 + 4, srect.centery + 2))

            for p_i, pin_name in enumerate(g.block.pin_names):
                pin_x, pin_y = vis.pin_positions[p_i][0] + px, vis.pin_positions[p_i][1] + py
                sig = g.input_signals[p_i]
                p_high = signals.get(sig, 0) == 1
                pygame.draw.circle(
                    self.screen, COL_HIGH if p_high else COL_MUTED, (pin_x, pin_y), 4
                )
                ps = self.font_small.render(pin_name, True, COL_MUTED)
                self.screen.blit(ps, (pin_x + 5, pin_y - ps.get_height() // 2))

            ox, oy = vis.out_position[0] + px, vis.out_position[1] + py
            if g.block.name.upper().startswith(("NOT", "NAND", "NOR", "XNOR")):
                pygame.draw.circle(self.screen, COL_HEADER, (ox + 4, oy), 4)
                pygame.draw.circle(self.screen, bd_col, (ox + 4, oy), 4, 2)
            else:
                pygame.draw.circle(self.screen, bd_col, (ox, oy), 4)

        # 4. Draw Primary Output Nodes (Guaranteed inside right edge)
        for out_name, rect in self.output_node_rects.items():
            srect = rect.move(px, py)
            drv = sol.output_drivers[out_name]
            val = signals.get(drv, 0)
            is_high = val == 1
            bg = COL_HIGH_BG if is_high else COL_PANEL
            bd = COL_HIGH if is_high else COL_BORDER
            pygame.draw.rect(self.screen, bg, srect, border_radius=6)
            pygame.draw.rect(self.screen, bd, srect, width=2, border_radius=6)
            pygame.draw.circle(self.screen, bd, (srect.left, srect.centery), 4)

            lbl = f"{out_name} = {val}"
            ts = self.font_mono_bold.render(lbl, True, COL_TEXT)
            self.screen.blit(
                ts, (srect.centerx - ts.get_width() // 2, srect.centery - ts.get_height() // 2)
            )

        # 5. Hover Tooltip
        if self.hovered_gate_id and self.hovered_gate_id in self.gate_visuals:
            g = self.gate_visuals[self.hovered_gate_id].gate
            pins_desc = ", ".join(
                f"{p}<-{s}({signals.get(s, 0)})" for p, s in zip(g.block.pin_names, g.input_signals)
            )
            tip_str = (
                f"[{g.gate_id} {g.block.name} | Level {g.level}]  "
                f"Pins: {pins_desc}  ->  Out {g.output_signal}={signals.get(g.output_signal, 0)}"
            )
            ts = self.font_mono.render(tip_str, True, COL_TEXT)
            tbox = pygame.Rect(vp.left + 12, vp.bottom - 30, ts.get_width() + 18, 24)
            pygame.draw.rect(self.screen, (15, 23, 42), tbox, border_radius=5)
            pygame.draw.rect(self.screen, COL_ACCENT, tbox, width=1, border_radius=5)
            self.screen.blit(ts, (tbox.x + 9, tbox.y + 4))

        self.screen.set_clip(old_clip)

    def _draw_gate_shape(
        self,
        rect: pygame.Rect,
        bname: str,
        fill_col: Tuple[int, int, int],
        bd_col: Tuple[int, int, int],
    ) -> None:
        if bname == "MUX2":
            pts = [
                (rect.left, rect.top),
                (rect.right, rect.top + 10),
                (rect.right, rect.bottom - 10),
                (rect.left, rect.bottom),
            ]
            pygame.draw.polygon(self.screen, fill_col, pts)
            pygame.draw.polygon(self.screen, bd_col, pts, 2)
        else:
            pygame.draw.rect(
                self.screen,
                fill_col,
                rect,
                border_top_left_radius=5,
                border_bottom_left_radius=5,
                border_top_right_radius=20,
                border_bottom_right_radius=20,
            )
            pygame.draw.rect(
                self.screen,
                bd_col,
                rect,
                width=2,
                border_top_left_radius=5,
                border_bottom_left_radius=5,
                border_top_right_radius=20,
                border_bottom_right_radius=20,
            )
            if bname.startswith(("XOR", "XNOR")):
                pygame.draw.line(
                    self.screen,
                    bd_col,
                    (rect.left - 4, rect.top + 4),
                    (rect.left - 4, rect.bottom - 4),
                    2,
                )

    def _draw_signal_wire(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        is_high: bool,
        highlight: bool,
        wire_idx: int,
    ) -> None:
        offset = ((wire_idx % 7) - 3) * 6
        mid_x = (x1 + x2) // 2 + offset
        pts = [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]

        if highlight:
            color = (96, 165, 250)
            width = 3
        elif is_high:
            color = COL_HIGH
            width = 2
        else:
            color = COL_LOW
            width = 2

        pygame.draw.lines(self.screen, color, False, pts, width)

        if is_high:
            seg1 = math.hypot(mid_x - x1, 0)
            seg2 = abs(y2 - y1)
            seg3 = math.hypot(x2 - mid_x, 0)
            total_len = seg1 + seg2 + seg3
            if total_len > 1:
                t = ((self.anim_phase * 140.0 + wire_idx * 25.0) % total_len)
                if t <= seg1:
                    frac = t / max(1.0, seg1)
                    px = x1 + (mid_x - x1) * frac
                    py = float(y1)
                elif t <= seg1 + seg2:
                    frac = (t - seg1) / max(1.0, seg2)
                    px = float(mid_x)
                    py = y1 + (y2 - y1) * frac
                else:
                    frac = (t - seg1 - seg2) / max(1.0, seg3)
                    px = mid_x + (x2 - mid_x) * frac
                    py = float(y2)
                pygame.draw.circle(self.screen, (187, 247, 208), (int(px), int(py)), 3)

    # ========================================================================
    # TAB 1: STRUCTURED INPUT ROUTING & GATE WIRING TABLES
    # ========================================================================

    def _draw_wiring_tables_tab(self, vp: pygame.Rect, sol: CircuitSolution) -> None:
        old_clip = self.screen.get_clip()
        self.screen.set_clip(vp)

        x = vp.left + 14
        y = vp.top + 12 - self.wiring_scroll_y
        w = vp.width - 28

        t1 = self.font_sec.render(
            "1. WHERE EACH INPUT GOES (Primary Input Fan-Out & Gate Pin Routing)", True, (147, 197, 253)
        )
        self.screen.blit(t1, (x, y))
        y += 24

        routing = self.cached_routing
        for inp in sol.spec.input_names:
            dests = routing.get(inp, [])
            row_rect = pygame.Rect(x, y, w, 30)
            pygame.draw.rect(self.screen, COL_PANEL, row_rect, border_radius=5)
            pygame.draw.rect(self.screen, COL_BORDER, row_rect, width=1, border_radius=5)

            b1 = self.font_mono_bold.render(f"Input '{inp}'", True, COL_TEXT)
            b2 = self.font_small.render(f"Fan-Out: {len(dests)}", True, COL_HIGH if dests else COL_MUTED)
            dest_str = "  -->  " + ",   ".join(dests) if dests else "  (Unused — not connected)"
            b3 = self.font_mono.render(dest_str, True, COL_TEXT if dests else COL_MUTED)

            self.screen.blit(b1, (x + 10, y + 6))
            self.screen.blit(b2, (x + 120, y + 8))
            self.screen.blit(b3, (x + 215, y + 6))
            y += 35

        y += 10

        t2 = self.font_sec.render(
            "2. HOW TO CONNECT EACH GATE (Step-by-Step Pin-to-Pin Wiring Guide)", True, (134, 239, 172)
        )
        self.screen.blit(t2, (x, y))
        y += 24

        loads = self.cached_loads
        if not sol.gates:
            s = self.font_ui.render("0 gates required — connect output directly.", True, COL_MUTED)
            self.screen.blit(s, (x + 10, y))
            y += 28
        else:
            for g in sol.gates:
                pin_lines: List[str] = []
                for pin_name, sig in zip(g.block.pin_names, g.input_signals):
                    if sig in sol.spec.input_names:
                        src_desc = f"Primary Input '{sig}'"
                    elif sig in ("0", "1"):
                        src_desc = f"Constant '{sig}'"
                    else:
                        src_g = next((x for x in sol.gates if x.output_signal == sig), None)
                        src_desc = f"{src_g.gate_id} ({src_g.block.name}) out '{sig}'" if src_g else sig
                    pin_lines.append(f"* Connect Pin '{pin_name}'  <--  {src_desc}")

                feeds_str = ", ".join(loads.get(g.output_signal, []))
                card_h = 30 + len(pin_lines) * 18
                crect = pygame.Rect(x, y, w, card_h)
                pygame.draw.rect(self.screen, COL_PANEL, crect, border_radius=6)
                pygame.draw.rect(self.screen, COL_BORDER, crect, width=1, border_radius=6)

                hdr = f"[{g.gate_id}] {g.block.name} Gate   (Level {g.level})   |   Output Net '{g.output_signal}'  -->  Feeds: {feeds_str}"
                self.screen.blit(self.font_ui_bold.render(hdr, True, (253, 230, 138)), (x + 10, y + 6))
                py = y + 26
                for pl in pin_lines:
                    self.screen.blit(self.font_mono.render(pl, True, COL_TEXT), (x + 20, py))
                    py += 18
                y += card_h + 6

        y += 10

        t3 = self.font_sec.render(
            "3. PRIMARY OUTPUT CONNECTIONS & BOOLEAN EQUATIONS", True, (192, 132, 252)
        )
        self.screen.blit(t3, (x, y))
        y += 24

        exprs = self.cached_exprs
        for out_name in sol.spec.output_names:
            drv = sol.output_drivers[out_name]
            src_g = next((x for x in sol.gates if x.output_signal == drv), None)
            drv_str = f"Output of {src_g.gate_id} ({src_g.block.name}, net '{drv}')" if src_g else f"Direct '{drv}'"

            orect = pygame.Rect(x, y, w, 48)
            pygame.draw.rect(self.screen, COL_PANEL, orect, border_radius=6)
            pygame.draw.rect(self.screen, COL_BORDER, orect, width=1, border_radius=6)

            self.screen.blit(
                self.font_ui_bold.render(f"Output '{out_name}'  <--  Driven by: {drv_str}", True, COL_TEXT),
                (x + 10, y + 6),
            )
            self.screen.blit(
                self.font_mono.render(f"Equation:  {out_name} = {exprs.get(out_name, '')}", True, (134, 239, 172)),
                (x + 10, y + 26),
            )
            y += 54

        self.screen.set_clip(old_clip)

    # ========================================================================
    # TAB 3: FULL REPORT & EXPORT
    # ========================================================================

    def _draw_report_tab(self, vp: pygame.Rect, sol: CircuitSolution) -> None:
        old_clip = self.screen.get_clip()
        self.screen.set_clip(vp)

        report_lines = self.cached_report_lines
        line_h = 18
        max_scroll = max(0, len(report_lines) * line_h - vp.height + 24)
        self.report_scroll_y = max(0, min(self.report_scroll_y, max_scroll))

        x = vp.left + 14
        y = vp.top + 10 - self.report_scroll_y
        for line in report_lines:
            if y + line_h >= vp.top and y <= vp.bottom:
                col = (147, 197, 253) if line.startswith(("===", "1.", "2.", "3.", "4.", "5.", "6.")) else COL_TEXT
                s = self.font_mono.render(line, True, col)
                self.screen.blit(s, (x, y))
            y += line_h

        self.screen.set_clip(old_clip)

    def save_report_to_file(self) -> None:
        if not self.current_solution:
            return
        out_path = os.path.abspath("circuit_wiring_report.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.current_solution.format_report(include_mermaid=True))
        self.status_banner = f"Saved full wiring report to: {out_path}"
        self.status_color = COL_HIGH

    def _draw_status_bar(self) -> None:
        bar = pygame.Rect(0, self.height - 22, self.width, 22)
        pygame.draw.rect(self.screen, COL_HEADER, bar)
        pygame.draw.line(self.screen, COL_BORDER, (0, self.height - 22), (self.width, self.height - 22), 1)
        pygame.draw.circle(self.screen, self.status_color, (14, self.height - 11), 4)
        if self._synth_busy:
            # Small spinner while the background search runs
            for k in range(8):
                ang = self.anim_phase * 6.0 + k * math.pi / 4
                shade = 70 + 20 * k
                cx = self.width - 20 + int(math.cos(ang) * 7)
                cy = self.height - 11 + int(math.sin(ang) * 7)
                pygame.draw.circle(self.screen, (shade, shade + 40 if shade < 200 else 255, 255), (cx, cy), 2)
        s = self.font_small.render(self.status_banner, True, COL_TEXT)
        self.screen.blit(s, (24, self.height - 19))

    # ========================================================================
    # EVENT HANDLING & MAIN LOOP
    # ========================================================================

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.VIDEORESIZE:
                self.width = max(980, event.w)
                self.height = max(600, event.h)
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                if self.current_solution is not None:
                    self._build_schematic_layout(self.current_solution)

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if self.tt_viewport_rect.collidepoint((mx, my)):
                    self.tt_scroll_y = max(0, self.tt_scroll_y - event.y * 24)
                elif self.right_viewport_rect.collidepoint((mx, my)):
                    if self.active_tab == 0:
                        self.schem_pan[1] += event.y * 28
                    elif self.active_tab == 1:
                        self.wiring_scroll_y = max(0, self.wiring_scroll_y - event.y * 32)
                    elif self.active_tab == 2:
                        self.full_tt_scroll_y = max(0, self.full_tt_scroll_y - event.y * 28)
                    elif self.active_tab == 3:
                        self.report_scroll_y = max(0, self.report_scroll_y - event.y * 32)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if event.button == 1:
                    self._handle_left_click(mx, my)
                elif event.button == 3:
                    clicked_cell = False
                    for rect, r, j in self.tt_cell_rects:
                        if rect.collidepoint((mx, my)):
                            rev_cycle = {"0": "X", "X": "1", "1": "0"}
                            self.table_values[r][j] = rev_cycle.get(self.table_values[r][j], "0")
                            self.synthesize_circuit()
                            clicked_cell = True
                            break
                    if not clicked_cell and self.active_tab == 0 and self.right_viewport_rect.collidepoint((mx, my)):
                        self.panning_schem = True
                        self.pan_start = (mx - self.schem_pan[0], my - self.schem_pan[1])

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    if self.painting_value is not None:
                        self.painting_value = None
                        self.painted_cells.clear()
                        self.synthesize_circuit()
                    self.dragging_gate_id = None
                elif event.button == 3:
                    self.panning_schem = False

            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                if self.painting_value is not None:
                    for rect, r, j in self.tt_cell_rects:
                        if rect.collidepoint((mx, my)) and (r, j) not in self.painted_cells:
                            self.table_values[r][j] = self.painting_value
                            self.painted_cells.add((r, j))
                            break
                elif self.dragging_gate_id and self.dragging_gate_id in self.gate_visuals:
                    vis = self.gate_visuals[self.dragging_gate_id]
                    new_rect = vis.rect.copy()
                    new_rect.x = mx - self.schem_pan[0] - self.drag_offset[0]
                    new_rect.y = my - self.schem_pan[1] - self.drag_offset[1]
                    self.gate_visuals[self.dragging_gate_id] = self._compute_gate_pins(vis.gate, new_rect)
                elif self.panning_schem:
                    self.schem_pan[0] = mx - self.pan_start[0]
                    self.schem_pan[1] = my - self.pan_start[1]

            elif event.type == pygame.KEYDOWN:
                if self.active_textbox is not None:
                    self._handle_textbox_key(event)
                elif self.hovered_cell is not None:
                    ch = event.unicode.upper() if event.unicode else ""
                    if ch in ("0", "1", "X"):
                        r, j = self.hovered_cell
                        self.table_values[r][j] = ch
                        self.synthesize_circuit()

        return True

    def _handle_left_click(self, mx: int, my: int) -> None:
        if self.in_box_rect.collidepoint((mx, my)):
            self.active_textbox = "inputs"
            return
        if self.out_box_rect.collidepoint((mx, my)):
            self.active_textbox = "outputs"
            return
        self.active_textbox = None

        for btn in self.buttons:
            if btn.rect.collidepoint((mx, my)):
                btn.callback()
                return

        for rect, r, j in self.tt_cell_rects:
            if rect.collidepoint((mx, my)):
                cycle = {"0": "1", "1": "X", "X": "0"}
                nxt = cycle.get(self.table_values[r][j], "0")
                self.table_values[r][j] = nxt
                self.painting_value = nxt
                self.painted_cells = {(r, j)}
                return

        for rect, r in self.tt_row_in_rects:
            if rect.collidepoint((mx, my)):
                n_in = len(self.input_names)
                for i, name in enumerate(self.input_names):
                    self.sim_inputs[name] = (r >> (n_in - 1 - i)) & 1
                self.status_banner = f"Loaded Truth Table Row #{r} into Live Circuit Simulator."
                self.status_color = COL_ACCENT
                return

        if self.active_tab == 0 and self.right_viewport_rect.collidepoint((mx, my)):
            px, py = self.schem_pan
            for name, rect in self.input_node_rects.items():
                if name in self.input_names and rect.move(px, py).collidepoint((mx, my)):
                    self.sim_inputs[name] = 1 - self.sim_inputs.get(name, 0)
                    return
            for g_id, vis in reversed(list(self.gate_visuals.items())):
                srect = vis.rect.move(px, py)
                if srect.collidepoint((mx, my)):
                    self.dragging_gate_id = g_id
                    self.drag_offset = (mx - px - vis.rect.x, my - py - vis.rect.y)
                    return

    def _handle_textbox_key(self, event: pygame.event.Event) -> None:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.active_textbox = None
            self.apply_io_names()
            return
        if event.key == pygame.K_ESCAPE:
            self.active_textbox = None
            return

        target = self.in_text_str if self.active_textbox == "inputs" else self.out_text_str
        if event.key == pygame.K_BACKSPACE:
            target = target[:-1]
        elif event.unicode and (event.unicode.isalnum() or event.unicode in (",", " ", "_")):
            target += event.unicode

        if self.active_textbox == "inputs":
            self.in_text_str = target
        else:
            self.out_text_str = target

    def run(self, max_frames: Optional[int] = None) -> None:
        frames = 0
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            self.anim_phase += dt
            running = self.handle_events()
            self._poll_synthesis()
            self.draw()
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        if max_frames is None:
            pygame.quit()


def launch_gui() -> None:
    app = PygameTruthTableApp()
    app.run()


if __name__ == "__main__":
    launch_gui()
