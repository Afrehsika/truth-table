"""
Truth Table to Logic Circuit Synthesis System
=============================================
Provide:
  1. Inputs & Outputs (Truth Table rows, dict, list, or expression, with optional Don't Cares 'X')
  2. Allowed Building Blocks (e.g. ['AND', 'OR', 'NOT'], ['NAND'], ['XOR', 'AND', 'OR'], ['MUX2'], or custom blocks)

Produces:
  - Total Gate Count & breakdown by gate type + logic depth
  - Input Routing Table ("Where each input goes" - exact gate & pin destinations)
  - Gate-to-Gate Wiring Guide ("How to connect each gate" - step-by-step pin connections)
  - Equivalent Boolean Expressions & Mermaid / ASCII schematic
  - Automated Truth-Table Verification
"""

from __future__ import annotations
from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import argparse
import json
import sys


# ============================================================================
# 1. BUILDING BLOCK DEFINITIONS
# ============================================================================

@dataclass(frozen=True)
class BuildingBlock:
    """Represents a logic gate or functional building block."""
    name: str
    arity: int
    pin_names: Tuple[str, ...]
    func: Callable[..., int]
    is_symmetric: bool = False
    cost: int = 1
    description: str = ""

    def eval_bitvectors(self, inputs: Sequence[int], mask: int) -> int:
        """Evaluate the building block across full truth-table bitvectors."""
        # Fast bitwise evaluation for standard gates, fallback to row-by-row for custom blocks
        name_upper = self.name.upper()
        if name_upper == "NOT" and len(inputs) == 1:
            return (~inputs[0]) & mask
        if name_upper == "BUF" and len(inputs) == 1:
            return inputs[0] & mask
        if name_upper.startswith("AND"):
            res = mask
            for x in inputs:
                res &= x
            return res & mask
        if name_upper.startswith("OR"):
            res = 0
            for x in inputs:
                res |= x
            return res & mask
        if name_upper.startswith("NAND"):
            res = mask
            for x in inputs:
                res &= x
            return (~res) & mask
        if name_upper.startswith("NOR"):
            res = 0
            for x in inputs:
                res |= x
            return (~res) & mask
        if name_upper.startswith("XOR"):
            res = 0
            for x in inputs:
                res ^= x
            return res & mask
        if name_upper.startswith("XNOR"):
            res = 0
            for x in inputs:
                res ^= x
            return (~res) & mask
        if name_upper == "MUX2" and len(inputs) == 3:
            # pin_names: (S, D0, D1) -> (~S & D0) | (S & D1)
            s, d0, d1 = inputs
            return (((~s) & d0) | (s & d1)) & mask
        if name_upper == "IMP" and len(inputs) == 2:
            # A -> B == (~A) | B
            return ((~inputs[0]) | inputs[1]) & mask
        if name_upper == "NIMP" and len(inputs) == 2:
            # A & ~B
            return (inputs[0] & (~inputs[1])) & mask

        # General row-by-row evaluation for custom building blocks
        num_rows = mask.bit_length()
        out = 0
        for row in range(num_rows):
            bits = [((inp >> row) & 1) for inp in inputs]
            if self.func(*bits):
                out |= (1 << row)
        return out & mask


def create_custom_block(
    name: str,
    pin_names: Sequence[str],
    truth_table_or_func: Union[Callable[..., int], Dict[Tuple[int, ...], int], Sequence[int]],
    is_symmetric: bool = False,
    cost: int = 1,
    description: str = "Custom building block",
) -> BuildingBlock:
    """Create a custom building block from a function, dict, or output column list."""
    arity = len(pin_names)
    if callable(truth_table_or_func):
        func = truth_table_or_func
    elif isinstance(truth_table_or_func, dict):
        table = {tuple(int(b) for b in k): int(v) for k, v in truth_table_or_func.items()}
        func = lambda *bits: table[tuple(bits)]
    else:
        seq = [int(v) for v in truth_table_or_func]
        if len(seq) != (1 << arity):
            raise ValueError(f"Custom block '{name}' with {arity} inputs requires {1 << arity} truth table entries.")
        func = lambda *bits: seq[sum(b << (arity - 1 - i) for i, b in enumerate(bits))]

    return BuildingBlock(
        name=name,
        arity=arity,
        pin_names=tuple(pin_names),
        func=func,
        is_symmetric=is_symmetric,
        cost=cost,
        description=description,
    )


STANDARD_BLOCKS: Dict[str, BuildingBlock] = {
    "NOT": BuildingBlock("NOT", 1, ("in",), lambda a: 1 - a, is_symmetric=True, description="Inverter (NOT gate)"),
    "BUF": BuildingBlock("BUF", 1, ("in",), lambda a: a, is_symmetric=True, description="Buffer"),
    "AND": BuildingBlock("AND", 2, ("in1", "in2"), lambda a, b: a & b, is_symmetric=True, description="2-input AND gate"),
    "OR": BuildingBlock("OR", 2, ("in1", "in2"), lambda a, b: a | b, is_symmetric=True, description="2-input OR gate"),
    "NAND": BuildingBlock("NAND", 2, ("in1", "in2"), lambda a, b: 1 - (a & b), is_symmetric=True, description="2-input NAND gate"),
    "NOR": BuildingBlock("NOR", 2, ("in1", "in2"), lambda a, b: 1 - (a | b), is_symmetric=True, description="2-input NOR gate"),
    "XOR": BuildingBlock("XOR", 2, ("in1", "in2"), lambda a, b: a ^ b, is_symmetric=True, description="2-input XOR gate"),
    "XNOR": BuildingBlock("XNOR", 2, ("in1", "in2"), lambda a, b: 1 - (a ^ b), is_symmetric=True, description="2-input XNOR gate"),
    "AND3": BuildingBlock("AND3", 3, ("in1", "in2", "in3"), lambda a, b, c: a & b & c, is_symmetric=True, description="3-input AND gate"),
    "OR3": BuildingBlock("OR3", 3, ("in1", "in2", "in3"), lambda a, b, c: a | b | c, is_symmetric=True, description="3-input OR gate"),
    "NAND3": BuildingBlock("NAND3", 3, ("in1", "in2", "in3"), lambda a, b, c: 1 - (a & b & c), is_symmetric=True, description="3-input NAND gate"),
    "NOR3": BuildingBlock("NOR3", 3, ("in1", "in2", "in3"), lambda a, b, c: 1 - (a | b | c), is_symmetric=True, description="3-input NOR gate"),
    "XOR3": BuildingBlock("XOR3", 3, ("in1", "in2", "in3"), lambda a, b, c: a ^ b ^ c, is_symmetric=True, description="3-input XOR gate"),
    "AND4": BuildingBlock("AND4", 4, ("in1", "in2", "in3", "in4"), lambda a, b, c, d: a & b & c & d, is_symmetric=True, description="4-input AND gate"),
    "OR4": BuildingBlock("OR4", 4, ("in1", "in2", "in3", "in4"), lambda a, b, c, d: a | b | c | d, is_symmetric=True, description="4-input OR gate"),
    "NAND4": BuildingBlock("NAND4", 4, ("in1", "in2", "in3", "in4"), lambda a, b, c, d: 1 - (a & b & c & d), is_symmetric=True, description="4-input NAND gate"),
    "NOR4": BuildingBlock("NOR4", 4, ("in1", "in2", "in3", "in4"), lambda a, b, c, d: 1 - (a | b | c | d), is_symmetric=True, description="4-input NOR gate"),
    "MUX2": BuildingBlock("MUX2", 3, ("S", "D0", "D1"), lambda s, d0, d1: d1 if s else d0, is_symmetric=False, description="2:1 Multiplexer (out = D1 if S=1 else D0)"),
    "IMP": BuildingBlock("IMP", 2, ("A", "B"), lambda a, b: (1 - a) | b, is_symmetric=False, description="Implication gate (~A | B)"),
    "NIMP": BuildingBlock("NIMP", 2, ("A", "B"), lambda a, b: a & (1 - b), is_symmetric=False, description="Inhibit gate (A & ~B)"),
}

BLOCK_PRESETS: Dict[str, List[str]] = {
    "basic": ["AND", "OR", "NOT"],
    "standard": ["AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"],
    "nand_only": ["NAND"],
    "nor_only": ["NOR"],
    "mux": ["MUX2", "NOT"],
    "mux_only": ["MUX2"],
    "aoi": ["AND", "OR", "NOT", "NAND", "NOR"],
}


def resolve_building_blocks(
    blocks: Sequence[Union[str, BuildingBlock]]
) -> List[BuildingBlock]:
    """Convert block names, preset names, or BuildingBlock objects into a list of BuildingBlocks."""
    resolved: List[BuildingBlock] = []
    seen: Set[str] = set()
    for item in blocks:
        if isinstance(item, BuildingBlock):
            if item.name not in seen:
                resolved.append(item)
                seen.add(item.name)
        elif isinstance(item, str):
            key_lower = item.strip().lower()
            key_upper = item.strip().upper()
            if key_lower in BLOCK_PRESETS:
                for sub in BLOCK_PRESETS[key_lower]:
                    if sub not in seen:
                        resolved.append(STANDARD_BLOCKS[sub])
                        seen.add(sub)
            elif key_upper in STANDARD_BLOCKS:
                if key_upper not in seen:
                    resolved.append(STANDARD_BLOCKS[key_upper])
                    seen.add(key_upper)
            else:
                valid = ", ".join(sorted(STANDARD_BLOCKS.keys()))
                presets = ", ".join(sorted(BLOCK_PRESETS.keys()))
                raise ValueError(
                    f"Unknown building block '{item}'. Valid gates: [{valid}] or presets: [{presets}]"
                )
        else:
            raise TypeError(f"Unsupported building block specification: {item!r}")
    if not resolved:
        raise ValueError("At least one building block must be specified.")
    return resolved


# ============================================================================
# 2. TRUTH TABLE PARSING & NORMALIZATION
# ============================================================================

@dataclass
class TruthTableSpec:
    """Normalized representation of a multi-output truth table."""
    input_names: List[str]
    output_names: List[str]
    # table_rows: list of (input_tuple, output_tuple_with_0_1_or_X)
    rows: List[Tuple[Tuple[int, ...], Tuple[Union[int, str], ...]]]
    # Bitvector targets and care masks for each output (length 2^N bits)
    target_vectors: Dict[str, int]
    care_masks: Dict[str, int]

    @property
    def num_inputs(self) -> int:
        return len(self.input_names)

    @property
    def num_rows(self) -> int:
        return 1 << len(self.input_names)

    @property
    def full_mask(self) -> int:
        return (1 << self.num_rows) - 1


def parse_truth_table(
    input_names: Sequence[str],
    output_names: Union[str, Sequence[str]],
    table_data: Union[
        Sequence[Sequence[Union[int, str]]],
        Dict[Tuple[int, ...], Union[int, str, Sequence[Union[int, str]]]],
        Sequence[Union[int, str]],
    ],
) -> TruthTableSpec:
    """
    Parse flexible truth table formats into a normalized TruthTableSpec.

    Supported `table_data` formats:
      1. List of output values in standard binary order (00..0 to 11..1):
         e.g. [0, 1, 1, 0] for 1 output, or [(0, 0), (0, 1), (0, 1), (1, 0)] for 2 outputs.
      2. List of full rows [in1, in2, ..., out1, out2, ...]:
         e.g. [[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]]
      3. Dict mapping input tuple (0, 1, ...) -> output value or output tuple:
         e.g. {(0,0): 0, (0,1): 1, (1,0): 1, (1,1): 0}
      Values can be 0, 1, '0', '1', or 'X'/'-'/None for Don't Care.
    """
    in_names = [str(x).strip() for x in input_names]
    if isinstance(output_names, str):
        out_names = [output_names.strip()]
    else:
        out_names = [str(x).strip() for x in output_names]

    n_in = len(in_names)
    n_out = len(out_names)
    num_rows = 1 << n_in

    def norm_val(v: Union[int, str, None]) -> Union[int, str]:
        if v is None:
            return "X"
        if isinstance(v, str):
            s = v.strip().upper()
            if s in ("X", "-", "?"):
                return "X"
            if s in ("0", "FALSE", "LOW", "L"):
                return 0
            if s in ("1", "TRUE", "HIGH", "H"):
                return 1
            raise ValueError(f"Invalid truth table value: {v!r}")
        if v in (0, 1):
            return int(v)
        raise ValueError(f"Invalid truth table value: {v!r}")

    row_map: Dict[Tuple[int, ...], Tuple[Union[int, str], ...]] = {}

    if isinstance(table_data, dict):
        for k, v in table_data.items():
            if isinstance(k, str):
                bits = tuple(int(c) for c in k.replace(" ", "").replace(",", ""))
            else:
                bits = tuple(int(b) for b in k)
            if len(bits) != n_in:
                raise ValueError(f"Input key {k} has length {len(bits)}, expected {n_in}.")
            if isinstance(v, (list, tuple)):
                outs = tuple(norm_val(x) for x in v)
            else:
                outs = (norm_val(v),)
            if len(outs) != n_out:
                raise ValueError(f"Output for {k} has length {len(outs)}, expected {n_out}.")
            row_map[bits] = outs
    else:
        seq = list(table_data)
        if len(seq) == num_rows and all(
            not isinstance(item, (list, tuple)) or len(item) == n_out for item in seq
        ):
            # Format 1: Ordered output values for standard binary counting 0..(2^N - 1)
            for idx, item in enumerate(seq):
                bits = tuple((idx >> (n_in - 1 - b)) & 1 for b in range(n_in))
                if isinstance(item, (list, tuple)):
                    outs = tuple(norm_val(x) for x in item)
                else:
                    outs = (norm_val(item),)
                if len(outs) != n_out:
                    raise ValueError(f"Row {idx} output length {len(outs)} != expected {n_out}.")
                row_map[bits] = outs
        else:
            # Format 2: Full rows [in1, ..., inN, out1, ..., outM]
            for idx, row in enumerate(seq):
                if not isinstance(row, (list, tuple)) or len(row) != n_in + n_out:
                    raise ValueError(
                        f"Row {idx} ({row!r}) must have {n_in} inputs + {n_out} outputs = {n_in + n_out} elements."
                    )
                bits = tuple(int(norm_val(x)) for x in row[:n_in])
                outs = tuple(norm_val(x) for x in row[n_in:])
                row_map[bits] = outs

    # Fill missing rows as Don't Care 'X'
    ordered_rows: List[Tuple[Tuple[int, ...], Tuple[Union[int, str], ...]]] = []
    target_vectors: Dict[str, int] = {name: 0 for name in out_names}
    care_masks: Dict[str, int] = {name: 0 for name in out_names}

    for idx in range(num_rows):
        bits = tuple((idx >> (n_in - 1 - b)) & 1 for b in range(n_in))
        outs = row_map.get(bits, tuple("X" for _ in range(n_out)))
        ordered_rows.append((bits, outs))
        for o_idx, o_name in enumerate(out_names):
            val = outs[o_idx]
            if val != "X":
                care_masks[o_name] |= (1 << idx)
                if val == 1:
                    target_vectors[o_name] |= (1 << idx)

    return TruthTableSpec(
        input_names=in_names,
        output_names=out_names,
        rows=ordered_rows,
        target_vectors=target_vectors,
        care_masks=care_masks,
    )


# ============================================================================
# 3. CIRCUIT DATA STRUCTURES & WIRING / CONNECTION REPORTING
# ============================================================================

@dataclass
class GateInstance:
    """A single instantiated building block in the synthesized circuit."""
    gate_id: str                 # e.g. "U1", "U2"
    block: BuildingBlock         # BuildingBlock type (e.g. NAND, XOR, MUX2)
    input_signals: Tuple[str, ...]  # Signal names connected to pin_names[0], pin_names[1], ...
    output_signal: str           # Net name driven by this gate, e.g. "n1" or output name
    level: int                   # Logic depth level (1-based)


@dataclass
class CircuitSolution:
    """Complete synthesized circuit with routing, wiring, expressions, and verification."""
    spec: TruthTableSpec
    allowed_blocks: List[BuildingBlock]
    gates: List[GateInstance]
    # Maps output_name -> signal_name driving that output (could be a gate output, primary input, or constant '0'/'1')
    output_drivers: Dict[str, str]
    synthesis_method: str
    is_verified: bool = True

    @property
    def total_gate_count(self) -> int:
        return len(self.gates)

    @property
    def max_logic_depth(self) -> int:
        return max((g.level for g in self.gates), default=0)

    def gate_count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for g in self.gates:
            counts[g.block.name] = counts.get(g.block.name, 0) + 1
        return counts

    def get_input_routing(self) -> Dict[str, List[str]]:
        """
        Return where each primary input goes:
        Maps input_name -> list of destination descriptions (e.g. "U1.in1 (XOR)", "Output Y (direct)")
        """
        routing: Dict[str, List[str]] = {inp: [] for inp in self.spec.input_names}
        # Also track constants if used
        for g in self.gates:
            for pin_name, sig in zip(g.block.pin_names, g.input_signals):
                if sig in routing:
                    routing[sig].append(f"{g.gate_id}.{pin_name} ({g.block.name})")
        for out_name, driver in self.output_drivers.items():
            if driver in routing:
                routing[driver].append(f"Output {out_name} (direct wire)")
        return routing

    def get_signal_load_map(self) -> Dict[str, List[str]]:
        """Maps every signal/net name -> list of pins/outputs it feeds."""
        loads: Dict[str, List[str]] = {}
        for g in self.gates:
            for pin_name, sig in zip(g.block.pin_names, g.input_signals):
                loads.setdefault(sig, []).append(f"{g.gate_id}.{pin_name} ({g.block.name})")
        for out_name, driver in self.output_drivers.items():
            loads.setdefault(driver, []).append(f"PRIMARY OUTPUT [{out_name}]")
        return loads

    def get_boolean_expressions(self) -> Dict[str, str]:
        """Return human-readable Boolean/functional expressions for every output."""
        expr_map: Dict[str, str] = {inp: inp for inp in self.spec.input_names}
        expr_map["0"] = "0"
        expr_map["1"] = "1"
        for g in self.gates:
            sub = [expr_map.get(sig, sig) for sig in g.input_signals]
            bname = g.block.name.upper()
            if bname == "NOT":
                expr_map[g.output_signal] = f"~({sub[0]})" if len(sub[0]) > 2 else f"~{sub[0]}"
            elif bname == "BUF":
                expr_map[g.output_signal] = sub[0]
            elif bname.startswith("AND"):
                expr_map[g.output_signal] = "(" + " & ".join(sub) + ")"
            elif bname.startswith("OR"):
                expr_map[g.output_signal] = "(" + " | ".join(sub) + ")"
            elif bname.startswith("NAND"):
                expr_map[g.output_signal] = "~(" + " & ".join(sub) + ")"
            elif bname.startswith("NOR"):
                expr_map[g.output_signal] = "~(" + " | ".join(sub) + ")"
            elif bname.startswith("XOR"):
                expr_map[g.output_signal] = "(" + " ^ ".join(sub) + ")"
            elif bname.startswith("XNOR"):
                expr_map[g.output_signal] = "~(" + " ^ ".join(sub) + ")"
            elif bname == "MUX2":
                expr_map[g.output_signal] = f"MUX2(S={sub[0]}, D0={sub[1]}, D1={sub[2]})"
            else:
                args = ", ".join(f"{p}={s}" for p, s in zip(g.block.pin_names, sub))
                expr_map[g.output_signal] = f"{g.block.name}({args})"
        return {out: expr_map.get(driver, driver) for out, driver in self.output_drivers.items()}

    def simulate_row(self, input_bits: Sequence[int]) -> Dict[str, int]:
        """Simulate the synthesized gate netlist for a single input combination."""
        signals: Dict[str, int] = {
            name: int(bit) for name, bit in zip(self.spec.input_names, input_bits)
        }
        signals["0"] = 0
        signals["1"] = 1
        for g in self.gates:
            in_vals = [signals[s] for s in g.input_signals]
            signals[g.output_signal] = int(g.block.func(*in_vals))
        return {out: signals[driver] for out, driver in self.output_drivers.items()}

    def verify(self) -> Tuple[bool, List[str]]:
        """Verify that the synthesized circuit satisfies every care row of the truth table."""
        errors: List[str] = []
        for bits, expected_outs in self.spec.rows:
            actual = self.simulate_row(bits)
            for out_name, exp in zip(self.spec.output_names, expected_outs):
                if exp != "X" and actual[out_name] != exp:
                    errors.append(
                        f"Mismatch at inputs {dict(zip(self.spec.input_names, bits))} "
                        f"for output '{out_name}': expected {exp}, got {actual[out_name]}"
                    )
        return (len(errors) == 0, errors)

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart diagram showing inputs, gates, and outputs."""
        lines = ["flowchart LR"]
        for inp in self.spec.input_names:
            lines.append(f'    IN_{inp}(["Input {inp}"])')
        used_consts = {
            sig for g in self.gates for sig in g.input_signals if sig in ("0", "1")
        } | {drv for drv in self.output_drivers.values() if drv in ("0", "1")}
        for c in sorted(used_consts):
            lines.append(f'    CONST_{c}(["Const {c}"])')

        for g in self.gates:
            lines.append(f'    {g.gate_id}["{g.gate_id}: {g.block.name}<br/>(out: {g.output_signal})"]')

        for out in self.spec.output_names:
            lines.append(f'    OUT_{out}(("Output {out}"))')

        gate_by_out = {g.output_signal: g.gate_id for g in self.gates}

        def node_ref(sig: str) -> str:
            if sig in self.spec.input_names:
                return f"IN_{sig}"
            if sig in ("0", "1"):
                return f"CONST_{sig}"
            return gate_by_out[sig]

        for g in self.gates:
            for pin, sig in zip(g.block.pin_names, g.input_signals):
                src = node_ref(sig)
                lines.append(f'    {src} -->|"{sig} -> {pin}"| {g.gate_id}')

        for out, drv in self.output_drivers.items():
            src = node_ref(drv)
            lines.append(f'    {src} -->|"{drv}"| OUT_{out}')

        return "\n".join(lines)

    def format_report(self, include_mermaid: bool = True) -> str:
        """Format a clear, comprehensive hardware connection report."""
        lines: List[str] = []
        sep = "=" * 76
        subsep = "-" * 76

        lines.append(sep)
        lines.append("DIGITAL LOGIC SYNTHESIS & WIRING REPORT")
        lines.append(sep)
        lines.append(f"Inputs ({len(self.spec.input_names)})          : {', '.join(self.spec.input_names)}")
        lines.append(f"Outputs ({len(self.spec.output_names)})         : {', '.join(self.spec.output_names)}")
        lines.append(f"Building Blocks   : {', '.join(b.name for b in self.allowed_blocks)}")
        lines.append(f"Synthesis Engine  : {self.synthesis_method}")
        lines.append(f"Verification      : {'PASSED (100% Truth Table Match)' if self.is_verified else 'FAILED'}")
        lines.append("")

        # 1. Gate Count Summary
        lines.append("1. GATE COUNT SUMMARY")
        lines.append(subsep)
        lines.append(f"  Total Gate Count : {self.total_gate_count}")
        lines.append(f"  Logic Levels     : {self.max_logic_depth}")
        counts = self.gate_count_by_type()
        if counts:
            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            lines.append(f"  By Gate Type     : {breakdown}")
        else:
            lines.append("  By Gate Type     : 0 gates required (direct wire / constant)")
        lines.append("")

        # 2. Where Each Input Goes (Input Fan-out / Pin Routing)
        lines.append("2. WHERE EACH INPUT GOES (INPUT ROUTING TABLE)")
        lines.append(subsep)
        routing = self.get_input_routing()
        for inp in self.spec.input_names:
            dests = routing.get(inp, [])
            if dests:
                lines.append(f"  Input '{inp}' (fan-out = {len(dests)}) connects to:")
                for d in dests:
                    lines.append(f"    -> {d}")
            else:
                lines.append(f"  Input '{inp}' (fan-out = 0): Unused (output does not depend on '{inp}')")
        lines.append("")

        # 3. How to Connect Each Gate (Step-by-Step Netlist Wiring)
        lines.append("3. HOW TO CONNECT EACH GATE (STEP-BY-STEP WIRING GUIDE)")
        lines.append(subsep)
        loads = self.get_signal_load_map()
        if not self.gates:
            lines.append("  No logic gates needed. Connect primary outputs directly:")
        else:
            for g in self.gates:
                lines.append(
                    f"  [{g.gate_id}] {g.block.name} Gate (Level {g.level}, Output Net: '{g.output_signal}')"
                )
                for pin_name, sig in zip(g.block.pin_names, g.input_signals):
                    if sig in self.spec.input_names:
                        src_desc = f"Primary Input '{sig}'"
                    elif sig in ("0", "1"):
                        src_desc = f"Logic Constant '{sig}' ({'VCC/HIGH' if sig == '1' else 'GND/LOW'})"
                    else:
                        # Find source gate
                        src_gate = next((x for x in self.gates if x.output_signal == sig), None)
                        src_desc = (
                            f"Output of {src_gate.gate_id} ({src_gate.block.name}, net '{sig}')"
                            if src_gate
                            else f"Net '{sig}'"
                        )
                    lines.append(f"    * Pin '{pin_name}'  <--  Connect to {src_desc}")
                out_dests = loads.get(g.output_signal, [])
                lines.append(f"    * Output '{g.output_signal}' -->  Feeds: {', '.join(out_dests)}")
                lines.append("")

        # 4. Primary Output Connections
        lines.append("4. PRIMARY OUTPUT CONNECTIONS & BOOLEAN EQUATIONS")
        lines.append(subsep)
        exprs = self.get_boolean_expressions()
        for out_name in self.spec.output_names:
            drv = self.output_drivers[out_name]
            if drv in self.spec.input_names:
                drv_desc = f"Direct wire from Primary Input '{drv}'"
            elif drv in ("0", "1"):
                drv_desc = f"Tied to Constant Logic '{drv}'"
            else:
                src_gate = next((x for x in self.gates if x.output_signal == drv), None)
                drv_desc = (
                    f"Output pin of {src_gate.gate_id} ({src_gate.block.name}, net '{drv}')"
                    if src_gate
                    else f"Net '{drv}'"
                )
            lines.append(f"  Output '{out_name}':")
            lines.append(f"    * Driven by : {drv_desc}")
            lines.append(f"    * Equation  : {out_name} = {exprs[out_name]}")
        lines.append("")

        # 5. Truth Table Verification Table
        lines.append("5. TRUTH TABLE VERIFICATION")
        lines.append(subsep)
        header_in = " ".join(f"{name:>3}" for name in self.spec.input_names)
        header_out = " ".join(f"{name:>4}(Exp/Sim)" for name in self.spec.output_names)
        lines.append(f"  {header_in} | {header_out}")
        lines.append("  " + "-" * (len(header_in) + 3 + len(header_out)))
        for bits, exp_outs in self.spec.rows:
            sim_outs = self.simulate_row(bits)
            in_str = " ".join(f"{b:>3}" for b in bits)
            out_Parts = []
            for o_name, exp in zip(self.spec.output_names, exp_outs):
                sim_v = sim_outs[o_name]
                cell = f"{exp}/{sim_v}"
                out_Parts.append(f"{cell:>13}")
            lines.append(f"  {in_str} | {' '.join(out_Parts)}")
        lines.append("")

        if include_mermaid:
            lines.append("6. MERMAID CIRCUIT SCHEMATIC")
            lines.append(subsep)
            lines.append(self.to_mermaid())
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)


# ============================================================================
# 4. SYNTHESIS ENGINE A: EXACT MINIMUM-GATE SYNTHESIZER (BFS / DAG SEARCH)
# ============================================================================

@dataclass(frozen=True)
class _SynthNode:
    """Internal node in exact synthesis table."""
    bitvector: int
    expr_id: str
    block: Optional[BuildingBlock]
    inputs: Tuple[str, ...]
    gate_set: FrozenSet[Tuple[str, str, Tuple[str, ...]]]  # Set of (id, block_name, input_ids)
    level: int


def _exact_synthesize_single_or_multi(
    spec: TruthTableSpec,
    allowed_blocks: List[BuildingBlock],
    max_gates: int = 7,
    max_states: int = 12000,
    allow_constants: bool = False,
) -> Optional[CircuitSolution]:
    """
    Search for an exact minimum-gate circuit using only `allowed_blocks`.

    Uses a strict operation budget (`max_ops`) and bounded backtracking (`max_dag_steps`)
    so synthesis always finishes in a few milliseconds and never freezes.
    """
    mask = spec.full_mask
    n_in = spec.num_inputs

    # Compute bitvector for each primary input
    input_bvs: Dict[str, int] = {}
    for i, name in enumerate(spec.input_names):
        bv = 0
        for row in range(spec.num_rows):
            bit = (row >> (n_in - 1 - i)) & 1
            if bit:
                bv |= (1 << row)
        input_bvs[name] = bv

    # Check if any output is trivial constant 0 or 1 on its care mask
    has_const_target = False
    for out_name in spec.output_names:
        cm = spec.care_masks[out_name]
        tv = spec.target_vectors[out_name] & cm
        if tv == 0 or tv == cm:
            has_const_target = True
            break

    min_level: Dict[int, int] = {}
    recipes: Dict[int, List[Tuple[int, Tuple]]] = {}
    layers: List[List[int]] = [[]]

    for name, bv in input_bvs.items():
        if bv not in min_level:
            min_level[bv] = 0
            layers[0].append(bv)
        recipes.setdefault(bv, []).append((0, ("INPUT", name)))

    if allow_constants or has_const_target:
        for c_val, c_bv in [("0", 0), ("1", mask)]:
            if c_bv not in min_level:
                min_level[c_bv] = 0
                layers[0].append(c_bv)
            recipes.setdefault(c_bv, []).append((0, ("CONST", c_val)))

    def matches_target(bv: int, out_name: str) -> bool:
        cm = spec.care_masks[out_name]
        tv = spec.target_vectors[out_name]
        return (bv & cm) == (tv & cm)

    def all_outputs_solved() -> bool:
        for out_name in spec.output_names:
            if not any(matches_target(bv, out_name) for bv in min_level):
                return False
        return True

    max_depth = min(max_gates, 4 if n_in <= 3 else 3)
    max_recipes_per_bv = 28 if n_in <= 3 else 8
    max_ops = max_states  # Hard cap on inner-loop gate evaluations (~5 ms max)
    ops_count = 0

    for depth in range(1, max_depth + 1):
        # Stop as soon as all outputs are solved (only allow 1 extra level at depth==3 for 2-input NAND XOR)
        if all_outputs_solved():
            if n_in > 2 or depth > 3:
                break
        if ops_count >= max_ops:
            break

        layers.append([])
        all_prev = [bv for d in range(depth) for bv in layers[d]]
        latest = set(layers[depth - 1])
        if not latest:
            break

        def record_recipe(out_bv: int, block: BuildingBlock, children: Tuple[int, ...]) -> None:
            if out_bv in children:
                return
            if out_bv in min_level and min_level[out_bv] == 0:
                return
            if out_bv not in min_level:
                min_level[out_bv] = depth
                layers[depth].append(out_bv)
            if depth <= min_level[out_bv] + 1:
                lst = recipes.setdefault(out_bv, [])
                if len(lst) < max_recipes_per_bv:
                    op = ("GATE", block, children)
                    if (depth, op) not in lst:
                        lst.append((depth, op))

        for block in allowed_blocks:
            if ops_count >= max_ops:
                break
            arity = block.arity
            if arity == 1:
                for u in layers[depth - 1]:
                    ops_count += 1
                    out_bv = block.eval_bitvectors((u,), mask)
                    record_recipe(out_bv, block, (u,))
            elif arity == 2:
                pool2 = all_prev[:64]
                if block.is_symmetric:
                    for i, u in enumerate(pool2):
                        u_in_latest = u in latest
                        for j in range(i, len(pool2)):
                            v = pool2[j]
                            if not (u_in_latest or (v in latest)):
                                continue
                            ops_count += 1
                            out_bv = block.eval_bitvectors((u, v), mask)
                            record_recipe(out_bv, block, (u, v))
                            if ops_count >= max_ops:
                                break
                        if ops_count >= max_ops:
                            break
                else:
                    for u in pool2:
                        u_in_latest = u in latest
                        for v in pool2:
                            if not (u_in_latest or (v in latest)):
                                continue
                            ops_count += 1
                            out_bv = block.eval_bitvectors((u, v), mask)
                            record_recipe(out_bv, block, (u, v))
                            if ops_count >= max_ops:
                                break
                        if ops_count >= max_ops:
                            break
            elif arity == 3:
                # Cap pool for 3-input gates so triple loop is fast
                pool3 = all_prev[:18]
                if block.is_symmetric:
                    for i, u in enumerate(pool3):
                        for j in range(i, len(pool3)):
                            v = pool3[j]
                            for k in range(j, len(pool3)):
                                w = pool3[k]
                                if not ((u in latest) or (v in latest) or (w in latest)):
                                    continue
                                ops_count += 1
                                out_bv = block.eval_bitvectors((u, v, w), mask)
                                record_recipe(out_bv, block, (u, v, w))
                                if ops_count >= max_ops:
                                    break
                            if ops_count >= max_ops:
                                break
                        if ops_count >= max_ops:
                            break
                else:
                    pool3_asym = all_prev[:12]
                    for u in pool3_asym:
                        for v in pool3_asym:
                            for w in pool3_asym:
                                if not ((u in latest) or (v in latest) or (w in latest)):
                                    continue
                                ops_count += 1
                                out_bv = block.eval_bitvectors((u, v, w), mask)
                                record_recipe(out_bv, block, (u, v, w))
                                if ops_count >= max_ops:
                                    break
                            if ops_count >= max_ops:
                                break
                        if ops_count >= max_ops:
                            break
            else:
                # Cap pool for >=4-input gates at 10 signals (max 210 combinations)
                pool4 = all_prev[:10]
                combos = (
                    combinations(pool4, arity)
                    if block.is_symmetric
                    else product(pool4[:6], repeat=arity)
                )
                for tup in combos:
                    if not any(x in latest for x in tup):
                        continue
                    ops_count += 1
                    out_bv = block.eval_bitvectors(tup, mask)
                    record_recipe(out_bv, block, tuple(tup))
                    if ops_count >= max_ops:
                        break

    if not all_outputs_solved():
        return None

    # Branch-and-bound search over recipes with a strict step limit (`max_dag_steps`)
    max_cands = 4 if len(spec.output_names) == 1 else (2 if len(spec.output_names) == 2 else 1)
    candidates_per_output: List[List[int]] = []
    for out_name in spec.output_names:
        cands = [bv for bv in min_level if matches_target(bv, out_name)]
        cands.sort(key=lambda b: min_level[b])
        candidates_per_output.append(cands[:max_cands])

    best_choice_map: Optional[Dict[int, Tuple[int, Tuple]]] = None
    best_target_bvs: Optional[Tuple[int, ...]] = None
    best_cost_pair = (10**9, 10**9)
    dag_steps = 0
    max_dag_steps = 2000

    for target_combo in product(*candidates_per_output):
        if dag_steps >= max_dag_steps:
            break

        def creates_cycle(root: int, children: Tuple[int, ...], chosen: Dict[int, Tuple[int, Tuple]]) -> bool:
            stack = list(children)
            visited: Set[int] = set()
            while stack:
                node = stack.pop()
                if node == root:
                    return True
                if node in visited:
                    continue
                visited.add(node)
                if node in chosen:
                    _, node_op = chosen[node]
                    if node_op[0] == "GATE":
                        stack.extend(node_op[2])
            return False

        def search_dag(
            pending: List[int],
            chosen: Dict[int, Tuple[int, Tuple]],
            gate_count: int,
            max_lvl: int,
        ) -> None:
            nonlocal best_choice_map, best_target_bvs, best_cost_pair, dag_steps
            dag_steps += 1
            if dag_steps >= max_dag_steps or (gate_count, max_lvl) >= best_cost_pair:
                return
            while pending and pending[-1] in chosen:
                pending.pop()
            if not pending:
                best_cost_pair = (gate_count, max_lvl)
                best_choice_map = dict(chosen)
                best_target_bvs = target_combo
                return

            curr_bv = pending[-1]
            cand_recipes = recipes[curr_bv]
            scored_recipes = sorted(
                cand_recipes,
                key=lambda r: (
                    0 if r[1][0] != "GATE" else sum(1 for c in r[1][2] if c not in chosen and min_level.get(c, 1) > 0),
                    r[0],
                ),
            )
            for lvl, op in scored_recipes[:8]:
                if dag_steps >= max_dag_steps:
                    break
                if op[0] == "GATE" and creates_cycle(curr_bv, op[2], chosen):
                    continue
                chosen[curr_bv] = (lvl, op)
                if op[0] == "GATE":
                    new_pending = pending[:-1] + [c for c in op[2] if c not in chosen]
                    search_dag(new_pending, chosen, gate_count + 1, max(max_lvl, lvl))
                else:
                    search_dag(pending[:-1], chosen, gate_count, max_lvl)
                del chosen[curr_bv]

        search_dag(list(reversed(target_combo)), {}, 0, 0)

    if best_choice_map is None or best_target_bvs is None:
        return None

    # Topological build of GateInstances from best_choice_map
    bv_to_signal: Dict[int, str] = {}
    bv_to_level: Dict[int, int] = {}
    gates: List[GateInstance] = []

    def build_signal(bv: int) -> str:
        if bv in bv_to_signal:
            return bv_to_signal[bv]
        _, op = best_choice_map[bv]
        if op[0] == "INPUT":
            sig = op[1]
            bv_to_signal[bv] = sig
            bv_to_level[bv] = 0
            return sig
        if op[0] == "CONST":
            sig = op[1]
            bv_to_signal[bv] = sig
            bv_to_level[bv] = 0
            return sig
        _, block, child_bvs = op
        child_sigs = tuple(build_signal(ch) for ch in child_bvs)
        lvl = max((bv_to_level[ch] for ch in child_bvs), default=0) + 1
        gate_idx = len(gates) + 1
        gate_id = f"U{gate_idx}"
        out_sig = f"n{gate_idx}"
        gates.append(
            GateInstance(
                gate_id=gate_id,
                block=block,
                input_signals=child_sigs,
                output_signal=out_sig,
                level=lvl,
            )
        )
        bv_to_signal[bv] = out_sig
        bv_to_level[bv] = lvl
        return out_sig

    output_drivers: Dict[str, str] = {}
    for out_name, bv in zip(spec.output_names, best_target_bvs):
        output_drivers[out_name] = build_signal(bv)

    sol = CircuitSolution(
        spec=spec,
        allowed_blocks=allowed_blocks,
        gates=gates,
        output_drivers=output_drivers,
        synthesis_method="Exact Minimum-Gate DAG Search",
    )
    ok, _ = sol.verify()
    sol.is_verified = ok
    return sol


# ============================================================================
# 5. SYNTHESIS ENGINE B: QUINE-McCLUSKEY + TECHNOLOGY MAPPER
#    (Scales to arbitrary truth tables & maps into allowed building blocks)
# ============================================================================

def _qm_primes(
    num_vars: int, care_on: Set[int], dc_set: Set[int]
) -> List[Tuple[int, int]]:
    """Return every prime implicant (value_bits, dash_mask) of the function ON=care_on, DC=dc_set."""
    all_minterms = care_on | dc_set
    if not care_on:
        return []
    if len(all_minterms) == (1 << num_vars):
        return [(0, (1 << num_vars) - 1)]

    current_group: Set[Tuple[int, int]] = {(m, 0) for m in all_minterms}
    primes: Set[Tuple[int, int]] = set()
    while current_group:
        next_group: Set[Tuple[int, int]] = set()
        used: Set[Tuple[int, int]] = set()
        items = sorted(current_group)
        by_mask: Dict[int, List[int]] = {}
        for v, m in items:
            by_mask.setdefault(m, []).append(v)
        for m, vals in by_mask.items():
            vset = set(vals)
            for v in vals:
                bit = 1
                while bit < (1 << num_vars):
                    if not (m & bit) and not (v & bit) and (v | bit) in vset:
                        used.add((v, m))
                        used.add((v | bit, m))
                        next_group.add((v, m | bit))
                    bit <<= 1
        for item in current_group:
            if item not in used:
                primes.add(item)
        current_group = next_group
    return sorted(primes)


def _qm_cover(
    primes: Sequence[Tuple[int, int]],
    on_set: Set[int],
    preferred: Optional[Set[Tuple[int, int]]] = None,
) -> List[Tuple[int, int]]:
    """Pick a small set of prime implicants covering `on_set` (essentials first, then greedy).
    Implicants in `preferred` (already built for another output) get a bonus so they are shared."""
    if not on_set:
        return []
    preferred = preferred or set()
    cov: Dict[Tuple[int, int], Set[int]] = {}
    for pi in primes:
        v, m = pi
        c = {mt for mt in on_set if (mt & ~m) == v}
        if c:
            cov[pi] = c
    uncovered = set(on_set)
    selected: List[Tuple[int, int]] = []

    progress = True
    while uncovered and progress:
        progress = False
        for mt in sorted(uncovered):
            if mt not in uncovered:
                continue
            covering = [pi for pi, c in cov.items() if mt in c]
            if len(covering) == 1:
                ess = covering[0]
                if ess not in selected:
                    selected.append(ess)
                uncovered -= cov[ess]
                progress = True

    while uncovered:
        def score(pi: Tuple[int, int]) -> Tuple[float, int, Tuple[int, int]]:
            gain = len(cov[pi] & uncovered)
            bonus = 1.6 if (pi in preferred and gain > 0) else 0.0
            return (gain + bonus, bin(pi[1]).count("1"), pi)

        best = max((pi for pi in cov if cov[pi] & uncovered), key=score)
        selected.append(best)
        uncovered -= cov[best]

    # Drop redundant implicants (all their minterms covered by the others)
    changed = True
    while changed:
        changed = False
        for pi in list(selected):
            others: Set[int] = set()
            for q in selected:
                if q != pi:
                    others |= cov[q]
            if on_set <= others:
                selected.remove(pi)
                changed = True
                break
    return selected


def _quine_mccluskey_minimize(
    num_vars: int, on_set: Set[int], dc_set: Set[int]
) -> List[Tuple[Optional[int], ...]]:
    """Minimize a Boolean function (Quine-McCluskey). Returns implicants as tuples of 0/1/None."""
    if not on_set:
        return []
    primes = _qm_primes(num_vars, on_set, dc_set)
    result: List[Tuple[Optional[int], ...]] = []
    for v, m in _qm_cover(primes, on_set):
        term: List[Optional[int]] = []
        for bit_idx in range(num_vars):
            shift = num_vars - 1 - bit_idx
            term.append(None if (m >> shift) & 1 else (v >> shift) & 1)
        result.append(tuple(term))
    return result


class _TechMapperBuilder:
    """Builds a deduplicated gate netlist mapped strictly into `allowed_blocks`."""

    def __init__(self, spec: TruthTableSpec, allowed_blocks: List[BuildingBlock]):
        self.spec = spec
        self.allowed_blocks = allowed_blocks
        self.block_map: Dict[str, BuildingBlock] = {b.name.upper(): b for b in allowed_blocks}
        self.gates: List[GateInstance] = []
        self.sig_level: Dict[str, int] = {inp: 0 for inp in spec.input_names}
        self.sig_level["0"] = 0
        self.sig_level["1"] = 0
        self.memo: Dict[Tuple[str, Tuple[str, ...]], str] = {}
        self.inv: Dict[str, str] = {}  # signal <-> its inverse (removes double inversions)

    def reduce_groups(self, groups: Sequence[Sequence[str]], kind: str, share: bool) -> List[str]:
        """
        Combine every group of signals with AND (kind="AND") or OR (kind="OR").
        With `share=True`, signal pairs that occur in several groups are built once and reused,
        which lowers the total gate count. Remaining signals are combined shallowest-first and
        use wide (3/4-input) gates when the library has them.
        """
        op2 = self.make_and2 if kind == "AND" else self.make_or2
        wide_names = ("AND4", "AND3") if kind == "AND" else ("OR4", "OR3")

        keys = [frozenset(g) for g in groups]
        work: Dict[frozenset, set] = {k: set(k) for k in keys}

        if share:
            while True:
                counts: Dict[Tuple[str, str], int] = {}
                for s in work.values():
                    if len(s) < 2:
                        continue
                    items = sorted(s)
                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            pair = (items[i], items[j])
                            counts[pair] = counts.get(pair, 0) + 1
                if not counts:
                    break
                (a, b), cnt = max(
                    counts.items(),
                    key=lambda kv: (
                        kv[1],
                        -(self.sig_level.get(kv[0][0], 0) + self.sig_level.get(kv[0][1], 0)),
                        kv[0],
                    ),
                )
                if cnt < 2:
                    break
                new_sig = op2(a, b)
                for s in work.values():
                    if a in s and b in s:
                        s.discard(a)
                        s.discard(b)
                        s.add(new_sig)

        results: Dict[frozenset, str] = {}
        for k, s in work.items():
            items = list(s)
            if not items:
                results[k] = self.make_const(1 if kind == "AND" else 0)
                continue
            while len(items) > 1:
                items.sort(key=lambda x: (self.sig_level.get(x, 0), x))
                merged = False
                for wname in wide_names:
                    w = self.block_map.get(wname)
                    if w is not None and len(items) >= w.arity:
                        chunk = items[: w.arity]
                        items = items[w.arity:] + [self._emit(w, chunk)]
                        merged = True
                        break
                if not merged:
                    a, b = items[0], items[1]
                    items = items[2:] + [op2(a, b)]
            results[k] = items[0]
        return [results[k] for k in keys]

    def _emit(self, block: BuildingBlock, inputs: Sequence[str]) -> str:
        norm_inputs = tuple(inputs)
        if block.is_symmetric:
            key = (block.name, tuple(sorted(norm_inputs)))
        else:
            key = (block.name, norm_inputs)
        if key in self.memo:
            return self.memo[key]
        lvl = max((self.sig_level.get(s, 0) for s in norm_inputs), default=0) + 1
        idx = len(self.gates) + 1
        gate_id = f"U{idx}"
        out_sig = f"n{idx}"
        self.gates.append(
            GateInstance(
                gate_id=gate_id,
                block=block,
                input_signals=norm_inputs,
                output_signal=out_sig,
                level=lvl,
            )
        )
        self.sig_level[out_sig] = lvl
        self.memo[key] = out_sig
        return out_sig

    def make_const(self, val: int) -> str:
        """Synthesize a logic 0 or 1 from available blocks if needed, or return '0'/'1'."""
        ref_in = self.spec.input_names[0]
        if val == 0:
            if "XOR" in self.block_map:
                return self._emit(self.block_map["XOR"], (ref_in, ref_in))
            if "AND" in self.block_map and ("NOT" in self.block_map or "NAND" in self.block_map or "NOR" in self.block_map):
                inv = self.make_not(ref_in)
                return self._emit(self.block_map["AND"], (ref_in, inv))
            if "NAND" in self.block_map:
                inv = self.make_not(ref_in)
                nand_out = self._emit(self.block_map["NAND"], (ref_in, inv))
                return self.make_not(nand_out)
            if "NOR" in self.block_map:
                inv = self.make_not(ref_in)
                return self._emit(self.block_map["NOR"], (ref_in, inv))
            return "0"
        else:
            if "XNOR" in self.block_map:
                return self._emit(self.block_map["XNOR"], (ref_in, ref_in))
            if "OR" in self.block_map and ("NOT" in self.block_map or "NAND" in self.block_map or "NOR" in self.block_map):
                inv = self.make_not(ref_in)
                return self._emit(self.block_map["OR"], (ref_in, inv))
            if "NAND" in self.block_map:
                inv = self.make_not(ref_in)
                return self._emit(self.block_map["NAND"], (ref_in, inv))
            if "NOR" in self.block_map:
                zero = self.make_const(0)
                return self.make_not(zero)
            return "1"

    def make_not(self, sig: str) -> str:
        """~sig, reusing an existing inverse (so NOT(NOT(x)) is just x)."""
        if sig in self.inv:
            return self.inv[sig]
        out = self._make_not_raw(sig)
        self.inv[sig] = out
        self.inv.setdefault(out, sig)
        return out

    def _make_not_raw(self, sig: str) -> str:
        """Synthesize ~sig using NOT, NAND, NOR, XOR, XNOR, MUX2, or fallback NOT."""
        if "NOT" in self.block_map:
            return self._emit(self.block_map["NOT"], (sig,))
        if "NAND" in self.block_map:
            return self._emit(self.block_map["NAND"], (sig, sig))
        if "NOR" in self.block_map:
            return self._emit(self.block_map["NOR"], (sig, sig))
        for k, b in self.block_map.items():
            if k.startswith("NAND") or k.startswith("NOR"):
                return self._emit(b, tuple(sig for _ in range(b.arity)))
        if "XOR" in self.block_map:
            return self._emit(self.block_map["XOR"], (sig, "1"))
        if "XNOR" in self.block_map:
            return self._emit(self.block_map["XNOR"], (sig, "0"))
        if "MUX2" in self.block_map:
            return self._emit(self.block_map["MUX2"], (sig, "1", "0"))
        if "IMP" in self.block_map:
            return self._emit(self.block_map["IMP"], (sig, "0"))
        # Fallback to standard NOT gate if user selected only non-inverting gates (e.g. AND/OR)
        return self._emit(STANDARD_BLOCKS["NOT"], (sig,))

    def make_and2(self, a: str, b: str) -> str:
        """Synthesize 2-input AND using available blocks."""
        if a == b:
            return a
        if "AND" in self.block_map:
            return self._emit(self.block_map["AND"], (a, b))
        if "NAND" in self.block_map:
            nand_ab = self._emit(self.block_map["NAND"], (a, b))
            return self.make_not(nand_ab)
        if "NOR" in self.block_map:
            na = self.make_not(a)
            nb = self.make_not(b)
            return self._emit(self.block_map["NOR"], (na, nb))
        if "OR" in self.block_map:
            na = self.make_not(a)
            nb = self.make_not(b)
            or_ab = self._emit(self.block_map["OR"], (na, nb))
            return self.make_not(or_ab)
        if "MUX2" in self.block_map:
            return self._emit(self.block_map["MUX2"], (a, "0", b))
        if "AND3" in self.block_map:
            return self._emit(self.block_map["AND3"], (a, b, b))
        if "NAND3" in self.block_map:
            t = self._emit(self.block_map["NAND3"], (a, b, b))
            return self.make_not(t)
        raise ValueError(
            f"Cannot synthesize AND operation with the given building blocks: {[b.name for b in self.allowed_blocks]}"
        )

    def make_or2(self, a: str, b: str) -> str:
        """Synthesize 2-input OR using available blocks."""
        if a == b:
            return a
        if "OR" in self.block_map:
            return self._emit(self.block_map["OR"], (a, b))
        if "NOR" in self.block_map:
            nor_ab = self._emit(self.block_map["NOR"], (a, b))
            return self.make_not(nor_ab)
        if "NAND" in self.block_map:
            na = self.make_not(a)
            nb = self.make_not(b)
            return self._emit(self.block_map["NAND"], (na, nb))
        if "AND" in self.block_map:
            na = self.make_not(a)
            nb = self.make_not(b)
            and_ab = self._emit(self.block_map["AND"], (na, nb))
            return self.make_not(and_ab)
        if "MUX2" in self.block_map:
            return self._emit(self.block_map["MUX2"], (a, b, "1"))
        if "OR3" in self.block_map:
            return self._emit(self.block_map["OR3"], (a, b, b))
        if "NOR3" in self.block_map:
            t = self._emit(self.block_map["NOR3"], (a, b, b))
            return self.make_not(t)
        raise ValueError(
            f"Cannot synthesize OR operation with the given building blocks: {[b.name for b in self.allowed_blocks]}"
        )

    def make_multi_and(self, sigs: Sequence[str]) -> str:
        items = list(sigs)
        if not items:
            return self.make_const(1)
        if len(items) == 1:
            return items[0]
        # Use wide AND gates if available
        while len(items) > 1:
            if len(items) >= 4 and "AND4" in self.block_map:
                chunk, rest = items[:4], items[4:]
                items = [self._emit(self.block_map["AND4"], chunk)] + rest
            elif len(items) >= 3 and "AND3" in self.block_map:
                chunk, rest = items[:3], items[3:]
                items = [self._emit(self.block_map["AND3"], chunk)] + rest
            else:
                # Balanced binary tree reduction for minimum logic depth
                next_level: List[str] = []
                for i in range(0, len(items), 2):
                    if i + 1 < len(items):
                        next_level.append(self.make_and2(items[i], items[i + 1]))
                    else:
                        next_level.append(items[i])
                items = next_level
        return items[0]

    def make_multi_or(self, sigs: Sequence[str]) -> str:
        items = list(sigs)
        if not items:
            return self.make_const(0)
        if len(items) == 1:
            return items[0]
        while len(items) > 1:
            if len(items) >= 4 and "OR4" in self.block_map:
                chunk, rest = items[:4], items[4:]
                items = [self._emit(self.block_map["OR4"], chunk)] + rest
            elif len(items) >= 3 and "OR3" in self.block_map:
                chunk, rest = items[:3], items[3:]
                items = [self._emit(self.block_map["OR3"], chunk)] + rest
            else:
                next_level: List[str] = []
                for i in range(0, len(items), 2):
                    if i + 1 < len(items):
                        next_level.append(self.make_or2(items[i], items[i + 1]))
                    else:
                        next_level.append(items[i])
                items = next_level
        return items[0]


def _assemble_plans(
    spec: TruthTableSpec,
    allowed_blocks: List[BuildingBlock],
    plans: Sequence[Tuple],
    share: bool,
) -> Tuple["_TechMapperBuilder", Dict[str, str]]:
    """Turn per-output plans into one shared gate netlist."""
    b = _TechMapperBuilder(spec, allowed_blocks)
    n = spec.num_inputs
    names = spec.input_names

    def cube_group(cube: Tuple[int, int], flip: bool) -> List[str]:
        v, m = cube
        sigs: List[str] = []
        for idx in range(n):
            shift = n - 1 - idx
            if (m >> shift) & 1:
                continue
            val = (v >> shift) & 1
            if flip:
                val ^= 1
            sigs.append(names[idx] if val == 1 else b.make_not(names[idx]))
        return sigs

    # Stage 1: build every cube (AND-terms for AO plans, OR-clauses for OA plans)
    and_groups: List[List[str]] = []
    or_groups: List[List[str]] = []
    slots: List[Optional[Tuple[str, int, int]]] = []  # (kind, start, count) per output
    for plan in plans:
        if plan[0] != "P":
            slots.append(None)
            continue
        _, cubes, form, _inv = plan
        if form == "AO":
            slots.append(("AND", len(and_groups), len(cubes)))
            and_groups.extend(cube_group(c, False) for c in cubes)
        else:
            slots.append(("OR", len(or_groups), len(cubes)))
            or_groups.extend(cube_group(c, True) for c in cubes)

    and_sigs = b.reduce_groups(and_groups, "AND", share)
    or_sigs = b.reduce_groups(or_groups, "OR", share)

    # Stage 2: combine the cubes of each output (OR of AND-terms, or AND of OR-clauses)
    stage2_or: List[List[str]] = []
    stage2_and: List[List[str]] = []
    where: List[Optional[Tuple[str, int]]] = []
    for plan, slot in zip(plans, slots):
        if slot is None:
            where.append(None)
            continue
        kind, start, count = slot
        if kind == "AND":
            where.append(("OR", len(stage2_or)))
            stage2_or.append(and_sigs[start:start + count])
        else:
            where.append(("AND", len(stage2_and)))
            stage2_and.append(or_sigs[start:start + count])

    final_or = b.reduce_groups(stage2_or, "OR", share)
    final_and = b.reduce_groups(stage2_and, "AND", share)

    drivers: Dict[str, str] = {}
    for out_name, plan, loc in zip(spec.output_names, plans, where):
        if plan[0] == "C0":
            drivers[out_name] = b.make_const(0)
        elif plan[0] == "C1":
            drivers[out_name] = b.make_const(1)
        else:
            kind, idx = loc  # type: ignore[misc]
            sig = final_or[idx] if kind == "OR" else final_and[idx]
            if plan[3]:
                sig = b.make_not(sig)
            drivers[out_name] = sig
    return b, drivers


def _qm_technology_map(
    spec: TruthTableSpec,
    allowed_blocks: List[BuildingBlock],
    time_budget: float = 1.0,
) -> CircuitSolution:
    """
    Multi-output logic minimisation + technology mapping into `allowed_blocks`.

    For every output it considers four realisations (sum-of-products, product-of-sums and the
    inverted forms of both, using the ON-set or the OFF-set cover), prefers prime implicants
    that other outputs already use, extracts shared sub-terms, and runs a coordinate-descent
    search that keeps whichever combination gives the fewest gates in total.
    """
    import time as _time

    deadline = _time.perf_counter() + max(0.05, time_budget)
    n = spec.num_inputs
    rows = spec.num_rows

    data: List[Dict] = []
    for out_name in spec.output_names:
        tv = spec.target_vectors[out_name]
        cm = spec.care_masks[out_name]
        on = {r for r in range(rows) if ((cm >> r) & 1) and ((tv >> r) & 1)}
        off = {r for r in range(rows) if ((cm >> r) & 1) and not ((tv >> r) & 1)}
        dc = {r for r in range(rows) if not ((cm >> r) & 1)}
        entry: Dict = {"on": on, "off": off, "dc": dc}
        if not on:
            entry["const"] = ("C0",)
        elif not off:
            entry["const"] = ("C1",)
        else:
            entry["primes_on"] = _qm_primes(n, on, dc)
            entry["primes_off"] = _qm_primes(n, off, dc)
        data.append(entry)

    def lit_count(cube: Tuple[int, int]) -> int:
        return n - bin(cube[1] & ((1 << n) - 1)).count("1")

    def estimate(plan: Tuple) -> int:
        if plan[0] != "P":
            return 0
        _, cubes, _form, invert = plan
        return (
            sum(max(0, lit_count(c) - 1) for c in cubes)
            + max(0, len(cubes) - 1)
            + (1 if invert else 0)
        )

    def typed_plans(i: int, pref_ao: Set, pref_oa: Set) -> List[Tuple]:
        """Exactly four plans: SOP, inverted-SOP-of-complement, POS, inverted-POS."""
        d = data[i]
        return [
            ("P", tuple(_qm_cover(d["primes_on"], d["on"], pref_ao)), "AO", False),
            ("P", tuple(_qm_cover(d["primes_off"], d["off"], pref_ao)), "AO", True),
            ("P", tuple(_qm_cover(d["primes_off"], d["off"], pref_oa)), "OA", False),
            ("P", tuple(_qm_cover(d["primes_on"], d["on"], pref_oa)), "OA", True),
        ]

    def candidate_plans(i: int, pref_ao: Set, pref_oa: Set) -> List[Tuple]:
        d = data[i]
        if "const" in d:
            return [d["const"]]
        uniq: List[Tuple] = []
        for p in typed_plans(i, pref_ao, pref_oa):
            if p not in uniq:
                uniq.append(p)
        return uniq

    wide_present = any(
        nm in {b.name.upper() for b in allowed_blocks}
        for nm in ("AND3", "AND4", "OR3", "OR4")
    )
    share_modes = [True, False] if wide_present else [True]

    def search(share: bool, budget_end: float):
        cache: Dict[Tuple, Tuple[int, int]] = {}

        def evaluate(plans: Sequence[Tuple]) -> Tuple[int, int]:
            key = tuple(plans)
            if key in cache:
                return cache[key]
            b, drv = _assemble_plans(spec, allowed_blocks, plans, share)
            used_depth = max((g.level for g in b.gates), default=0)
            cache[key] = (len(b.gates), used_depth)
            return cache[key]

        # Starting points: cheapest-by-estimate per output, then "everything is SOP/POS/..." seeds
        seeds: List[List[Tuple]] = []
        seeds.append([min(candidate_plans(i, set(), set()), key=estimate) for i in range(len(data))])
        for k in range(4):
            seeds.append([
                data[i]["const"] if "const" in data[i] else typed_plans(i, set(), set())[k]
                for i in range(len(data))
            ])

        overall_cost: Optional[Tuple[int, int]] = None
        overall_plans: List[Tuple] = seeds[0]
        for seed in seeds:
            current = list(seed)
            best_cost = evaluate(current)
            for _pass in range(4):
                improved = False
                for i in range(len(data)):
                    if "const" in data[i]:
                        continue
                    pref_ao = {
                        c for j, p in enumerate(current)
                        if j != i and p[0] == "P" and p[2] == "AO" for c in p[1]
                    }
                    pref_oa = {
                        c for j, p in enumerate(current)
                        if j != i and p[0] == "P" and p[2] == "OA" for c in p[1]
                    }
                    for plan in candidate_plans(i, pref_ao, pref_oa) + candidate_plans(i, set(), set()):
                        if plan == current[i]:
                            continue
                        if _time.perf_counter() > budget_end:
                            break
                        trial = current[:i] + [plan] + current[i + 1:]
                        cost = evaluate(trial)
                        if cost < best_cost:
                            best_cost = cost
                            current = trial
                            improved = True
                if not improved or _time.perf_counter() > budget_end:
                    break
            if overall_cost is None or best_cost < overall_cost:
                overall_cost, overall_plans = best_cost, current
            if _time.perf_counter() > budget_end:
                break
        assert overall_cost is not None
        return overall_cost, overall_plans

    best_overall: Optional[Tuple[Tuple[int, int], List[Tuple], bool]] = None
    for k, share in enumerate(share_modes):
        slice_end = _time.perf_counter() + (deadline - _time.perf_counter()) / (len(share_modes) - k)
        cost, plans = search(share, slice_end)
        if best_overall is None or cost < best_overall[0]:
            best_overall = (cost, plans, share)

    assert best_overall is not None
    _cost, best_plans, best_share = best_overall
    builder, drivers = _assemble_plans(spec, allowed_blocks, best_plans, best_share)

    method = "Multi-Output Quine-McCluskey (SOP/POS, shared terms) + Technology Mapper"
    allowed_names = {b.name.upper() for b in allowed_blocks}
    if any(g.block.name.upper() not in allowed_names for g in builder.gates):
        method += " [library had no inverter: NOT gates were added]"

    sol = CircuitSolution(
        spec=spec,
        allowed_blocks=allowed_blocks,
        gates=builder.gates,
        output_drivers=drivers,
        synthesis_method=method,
    )
    ok, _ = sol.verify()
    sol.is_verified = ok
    return sol


# ============================================================================
# 6. UNIFIED PUBLIC SYNTHESIS API
# ============================================================================

def design_circuit(
    input_names: Sequence[str],
    output_names: Union[str, Sequence[str]],
    table_data: Union[
        Sequence[Sequence[Union[int, str]]],
        Dict[Tuple[int, ...], Union[int, str, Sequence[Union[int, str]]]],
        Sequence[Union[int, str]],
    ],
    building_blocks: Sequence[Union[str, BuildingBlock]] = ("AND", "OR", "NOT"),
    max_exact_gates: int = 7,
    allow_constants: bool = False,
    time_budget: float = 1.0,
) -> CircuitSolution:
    """
    Main entry point: Given a truth table and allowed building blocks, synthesize
    the best logic circuit, returning gate counts, input routing, and gate connections.

    Strategy:
      1. Try Exact Minimum-Gate DAG synthesis first (for <= 4 inputs and up to `max_exact_gates`).
      2. Also run Quine-McCluskey + Technology Mapping (when applicable) and pick the verified
         solution with the strictly smaller gate count (and shallower depth on ties).
    """
    spec = parse_truth_table(input_names, output_names, table_data)
    blocks = resolve_building_blocks(building_blocks)

    block_names_upper = {b.name.upper() for b in blocks}
    use_consts = allow_constants or ("MUX2" in block_names_upper and len(blocks) == 1)

    candidates: List[CircuitSolution] = []

    # 1. Exact synthesis for <= 3 inputs (or 4 inputs with <= 2 outputs)
    if spec.num_inputs <= 3 or (spec.num_inputs == 4 and len(spec.output_names) <= 2):
        state_cap = 10000 if spec.num_inputs <= 3 else 3000
        exact_sol = _exact_synthesize_single_or_multi(
            spec,
            blocks,
            max_gates=max_exact_gates,
            max_states=state_cap,
            allow_constants=use_consts,
        )
        if exact_sol is not None and exact_sol.is_verified:
            candidates.append(exact_sol)

    # 2. Quine-McCluskey + Tech Mapper fallback / comparison
    try:
        qm_sol = _qm_technology_map(spec, blocks, time_budget=time_budget)
        if qm_sol.is_verified:
            candidates.append(qm_sol)
    except ValueError:
        # Allowed blocks might be a custom or non-universal set (e.g. XOR-only for linear functions)
        pass

    if not candidates:
        # Try deeper exact search if initial budget wasn't enough
        deeper_sol = _exact_synthesize_single_or_multi(
            spec,
            blocks,
            max_gates=max(max_exact_gates + 1, 6),
            max_states=15000,
            allow_constants=True,
        )
        if deeper_sol is not None and deeper_sol.is_verified:
            candidates.append(deeper_sol)

    if not candidates:
        raise RuntimeError(
            f"Could not synthesize the target truth table using only building blocks "
            f"{[b.name for b in blocks]}. Check if the building block set is functionally complete "
            f"for this truth table."
        )

    candidates.sort(key=lambda s: (s.total_gate_count, s.max_logic_depth))
    return candidates[0]


# Gate libraries the AUTO mode chooses between (all built from 2-input gates + inverters).
AUTO_LIBRARIES: List[Tuple[str, List[str]]] = [
    ("AND / OR / NOT", ["AND", "OR", "NOT"]),
    ("AND / OR / XOR", ["AND", "OR", "XOR"]),
    ("AND / OR / NOT / XOR / XNOR", ["AND", "OR", "NOT", "XOR", "XNOR"]),
    ("NAND only", ["NAND"]),
    ("NOR only", ["NOR"]),
    ("NAND / NOR / NOT", ["NAND", "NOR", "NOT"]),
    ("AND / OR / NAND / NOR / NOT / XOR / XNOR", ["AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR"]),
]


def design_circuit_auto(
    input_names: Sequence[str],
    output_names: Union[str, Sequence[str]],
    table_data: Union[
        Sequence[Sequence[Union[int, str]]],
        Dict[Tuple[int, ...], Union[int, str, Sequence[Union[int, str]]]],
        Sequence[Union[int, str]],
    ],
    extra_blocks: Sequence[Union[str, BuildingBlock]] = (),
    time_budget: float = 3.0,
) -> CircuitSolution:
    """
    Let the system pick the gate library itself: synthesize with several candidate
    libraries (see AUTO_LIBRARIES, optionally widened by `extra_blocks` such as MUX2 or AND3)
    and return the circuit with the fewest gates (ties: fewest logic levels).
    """
    per_lib = max(0.1, time_budget / len(AUTO_LIBRARIES))
    best: Optional[CircuitSolution] = None
    best_name = ""
    errors: List[str] = []
    for lib_name, gates in AUTO_LIBRARIES:
        try:
            sol = design_circuit(
                input_names,
                output_names,
                table_data,
                building_blocks=list(gates) + list(extra_blocks),
                time_budget=per_lib,
            )
        except Exception as exc:  # a library may be unable to build this function
            errors.append(f"{lib_name}: {exc}")
            continue
        if not sol.is_verified:
            continue
        if best is None or (sol.total_gate_count, sol.max_logic_depth) < (
            best.total_gate_count,
            best.max_logic_depth,
        ):
            best, best_name = sol, lib_name
    if best is None:
        raise RuntimeError("AUTO mode could not synthesize this truth table: " + "; ".join(errors))
    extra = (
        " + " + ", ".join(b if isinstance(b, str) else b.name for b in extra_blocks)
        if extra_blocks
        else ""
    )
    best.synthesis_method = f"AUTO (best library: {best_name}{extra}) | {best.synthesis_method}"
    return best


# ============================================================================
# 7. CLI & INTERACTIVE MODE
# ============================================================================

def run_interactive_wizard() -> None:
    """Interactive command-line prompt for entering a truth table and building blocks."""
    print("=" * 76)
    print("INTERACTIVE TRUTH TABLE TO LOGIC CIRCUIT DESIGNER")
    print("=" * 76)
    in_raw = input("Enter input variable names separated by commas (e.g. A, B, C): ").strip()
    input_names = [x.strip() for x in in_raw.replace(",", " ").split() if x.strip()]
    if not input_names:
        print("Error: At least one input name is required.")
        return

    out_raw = input("Enter output variable name(s) separated by commas (e.g. Y or Sum, Cout): ").strip()
    output_names = [x.strip() for x in out_raw.replace(",", " ").split() if x.strip()]
    if not output_names:
        output_names = ["Y"]

    print("\nAvailable Building Blocks:")
    print(f"  Gates   : {', '.join(sorted(STANDARD_BLOCKS.keys()))}")
    print(f"  Presets : {', '.join(f'{k}={v}' for k, v in BLOCK_PRESETS.items())}")
    print("  Auto    : Type 'AUTO' to let the system pick the library with fewest gates")
    bb_raw = input("Enter building blocks, preset, or 'AUTO' (default: AUTO): ").strip()
    if not bb_raw or bb_raw.upper() == "AUTO":
        building_blocks = "AUTO"
    else:
        building_blocks = [x.strip() for x in bb_raw.replace(",", " ").split() if x.strip()]

    num_rows = 1 << len(input_names)
    print(f"\nEnter output value(s) ({', '.join(output_names)}) for each of the {num_rows} rows (use 0, 1, or X for Don't Care):")
    rows_data: List[List[Union[int, str]]] = []
    for r in range(num_rows):
        bits = [(r >> (len(input_names) - 1 - i)) & 1 for i in range(len(input_names))]
        bit_str = " ".join(f"{name}={b}" for name, b in zip(input_names, bits))
        while True:
            ans = input(f"  Row {r:2d} [{bit_str}] -> {', '.join(output_names)} = ").strip()
            vals = ans.replace(",", " ").split()
            if len(vals) == len(output_names):
                rows_data.append(bits + vals)
                break
            print(f"    Please enter {len(output_names)} value(s) (0, 1, or X).")

    print("\nSynthesizing simplest circuit...\n")
    if building_blocks == "AUTO":
        solution = design_circuit_auto(
            input_names=input_names,
            output_names=output_names,
            table_data=rows_data,
        )
    else:
        solution = design_circuit(
            input_names=input_names,
            output_names=output_names,
            table_data=rows_data,
            building_blocks=building_blocks,
        )
    print(solution.format_report())


def run_demos() -> None:
    """Run built-in demonstration examples showing different truth tables & building blocks."""
    print("\n>>> DEMO 1: 1-Bit Full Adder (Inputs: A, B, Cin -> Outputs: Sum, Cout) using [XOR, AND, OR]")
    fa_rows = [
        # A, B, Cin, Sum, Cout
        [0, 0, 0, 0, 0],
        [0, 0, 1, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 1, 1, 0, 1],
        [1, 0, 0, 1, 0],
        [1, 0, 1, 0, 1],
        [1, 1, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ]
    sol1 = design_circuit(
        input_names=["A", "B", "Cin"],
        output_names=["Sum", "Cout"],
        table_data=fa_rows,
        building_blocks=["XOR", "AND", "OR"],
    )
    print(sol1.format_report())

    print("\n>>> DEMO 2: XOR Function (Inputs: A, B -> Output: Y) built using ONLY [NAND] gates")
    sol2 = design_circuit(
        input_names=["A", "B"],
        output_names=["Y"],
        table_data=[0, 1, 1, 0],
        building_blocks=["NAND"],
    )
    print(sol2.format_report())

    print("\n>>> DEMO 3: 3-Input Majority Voting Circuit (Inputs: A, B, C -> Output: M) using [AND, OR, NOT]")
    sol3 = design_circuit(
        input_names=["A", "B", "C"],
        output_names=["M"],
        table_data=[0, 0, 0, 1, 0, 1, 1, 1],
        building_blocks=["AND", "OR", "NOT"],
    )
    print(sol3.format_report())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Truth Table to Logic Gate Synthesizer (Gate Count, Input Routing & Netlist Connections)"
    )
    parser.add_argument(
        "--gui",
        "-g",
        action="store_true",
        help="Launch the Graphical User Interface (GUI) with interactive schematic & truth table editor",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run built-in demonstration circuits (Full Adder, NAND-only XOR, 3-Input Majority)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch interactive step-by-step truth table entry wizard",
    )
    parser.add_argument(
        "--inputs",
        type=str,
        help="Comma-separated input names, e.g. 'A,B,C'",
    )
    parser.add_argument(
        "--outputs",
        type=str,
        default="Y",
        help="Comma-separated output names, e.g. 'Y' or 'Sum,Cout'",
    )
    parser.add_argument(
        "--values",
        type=str,
        help="Comma-separated truth-table output values in binary order (00..0 to 11..1), e.g. '0,1,1,0'",
    )
    parser.add_argument(
        "--blocks",
        type=str,
        default="AND,OR,NOT",
        help="Comma-separated allowed building blocks or preset (e.g. 'AND,OR,NOT', 'NAND', 'NOR', 'XOR,AND,OR', 'MUX2,NOT')",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically configure the simplest circuit by testing multiple gate libraries and picking the one with the fewest gates",
    )
    parser.add_argument(
        "--json",
        type=str,
        help="Path to a JSON specification file with {'inputs': [...], 'outputs': [...], 'blocks': [...], 'table': [...]}",
    )

    args = parser.parse_args()

    if args.gui:
        from truth_table_gui import launch_gui
        launch_gui()
        return

    if args.demo:
        run_demos()
        return

    if args.interactive:
        run_interactive_wizard()
        return

    if args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if args.auto or cfg.get("auto", False):
            sol = design_circuit_auto(
                input_names=cfg["inputs"],
                output_names=cfg.get("outputs", ["Y"]),
                table_data=cfg["table"],
                extra_blocks=cfg.get("extra_blocks", ()),
            )
        else:
            sol = design_circuit(
                input_names=cfg["inputs"],
                output_names=cfg.get("outputs", ["Y"]),
                table_data=cfg["table"],
                building_blocks=cfg.get("blocks", ["AND", "OR", "NOT"]),
            )
        print(sol.format_report())
        return

    if args.inputs and args.values:
        in_names = [x.strip() for x in args.inputs.split(",") if x.strip()]
        out_names = [x.strip() for x in args.outputs.split(",") if x.strip()]
        blocks = [x.strip() for x in args.blocks.split(",") if x.strip()]
        raw_vals = [x.strip() for x in args.values.split(",") if x.strip()]
        if len(out_names) == 1:
            table_data = raw_vals
        else:
            n_out = len(out_names)
            table_data = [raw_vals[i : i + n_out] for i in range(0, len(raw_vals), n_out)]

        if args.auto:
            sol = design_circuit_auto(
                input_names=in_names,
                output_names=out_names,
                table_data=table_data,
            )
        else:
            sol = design_circuit(
                input_names=in_names,
                output_names=out_names,
                table_data=table_data,
                building_blocks=blocks,
            )
        print(sol.format_report())
        return

    # Default if no flags passed: show usage + run demos
    parser.print_help()
    print("\nRunning built-in demos (pass -i for interactive mode, or --inputs/--values/--blocks):\n")
    run_demos()


if __name__ == "__main__":
    main()
