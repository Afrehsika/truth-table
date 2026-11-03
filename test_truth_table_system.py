"""Unit tests for the Truth Table to Logic Circuit Synthesis System."""

import unittest
from truth_table_system import (
    create_custom_block,
    design_circuit,
    parse_truth_table,
)


class TestTruthTableSynthesis(unittest.TestCase):
    def test_xor_with_nand_only_optimal_4_gates(self):
        sol = design_circuit(
            input_names=["A", "B"],
            output_names="Y",
            table_data=[0, 1, 1, 0],
            building_blocks=["NAND"],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 4)
        self.assertEqual(sol.gate_count_by_type(), {"NAND": 4})
        routing = sol.get_input_routing()
        self.assertEqual(len(routing["A"]), 2)
        self.assertEqual(len(routing["B"]), 2)

    def test_xor_with_nor_only_optimal_5_gates(self):
        sol = design_circuit(
            input_names=["A", "B"],
            output_names="Y",
            table_data=[0, 1, 1, 0],
            building_blocks=["NOR"],
        )
        self.assertTrue(sol.is_verified)
        self.assertLessEqual(sol.total_gate_count, 5)
        self.assertEqual(set(sol.gate_count_by_type().keys()), {"NOR"})

    def test_full_adder_multi_output_5_gates(self):
        fa_rows = [
            [0, 0, 0, 0, 0],
            [0, 0, 1, 1, 0],
            [0, 1, 0, 1, 0],
            [0, 1, 1, 0, 1],
            [1, 0, 0, 1, 0],
            [1, 0, 1, 0, 1],
            [1, 1, 0, 0, 1],
            [1, 1, 1, 1, 1],
        ]
        sol = design_circuit(
            input_names=["A", "B", "Cin"],
            output_names=["Sum", "Cout"],
            table_data=fa_rows,
            building_blocks=["AND", "OR", "XOR"],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 5)

    def test_dont_care_reduction(self):
        # Truth table where Y = A when Don't Cares 'X' are exploited
        sol = design_circuit(
            input_names=["A", "B"],
            output_names="Y",
            table_data=[0, "X", 1, 1],
            building_blocks=["AND", "OR", "NOT"],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 0)
        self.assertEqual(sol.output_drivers["Y"], "A")

    def test_mux2_building_block(self):
        # 2-input XOR using a single MUX2 and NOT
        sol = design_circuit(
            input_names=["A", "B"],
            output_names="Y",
            table_data=[0, 1, 1, 0],
            building_blocks=["MUX2", "NOT"],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 2)
        self.assertEqual(sol.gate_count_by_type(), {"NOT": 1, "MUX2": 1})

    def test_custom_building_block(self):
        # Define a custom 3-input Majority gate MAJ3
        maj3 = create_custom_block(
            name="MAJ3",
            pin_names=("x", "y", "z"),
            truth_table_or_func=lambda x, y, z: 1 if (x + y + z) >= 2 else 0,
            is_symmetric=True,
        )
        sol = design_circuit(
            input_names=["A", "B", "C"],
            output_names="M",
            table_data=[0, 0, 0, 1, 0, 1, 1, 1],
            building_blocks=[maj3],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 1)
        self.assertEqual(sol.gate_count_by_type(), {"MAJ3": 1})

    def test_5_input_quine_mccluskey_scaling(self):
        # 5 inputs: Y = (A & B) | (C & D & ~E)
        rows = []
        for idx in range(32):
            a = (idx >> 4) & 1
            b = (idx >> 3) & 1
            c = (idx >> 2) & 1
            d = (idx >> 1) & 1
            e = idx & 1
            y = (a & b) | (c & d & (1 - e))
            rows.append(y)
        sol = design_circuit(
            input_names=["A", "B", "C", "D", "E"],
            output_names="Y",
            table_data=rows,
            building_blocks=["AND", "OR", "NOT"],
        )
        self.assertTrue(sol.is_verified)
        self.assertEqual(sol.total_gate_count, 5)

    def test_auto_simplest_circuit_selection(self):
        from truth_table_system import design_circuit_auto

        # 1. 2-input XOR: AUTO picks the 1-gate XOR solution
        sol_xor = design_circuit_auto(
            input_names=["A", "B"],
            output_names="Y",
            table_data=[0, 1, 1, 0],
        )
        self.assertTrue(sol_xor.is_verified)
        self.assertEqual(sol_xor.total_gate_count, 1)

        # 2. Full Adder: AUTO picks optimal 5-gate circuit
        fa_rows = [
            [0, 0, 0, 0, 0],
            [0, 0, 1, 1, 0],
            [0, 1, 0, 1, 0],
            [0, 1, 1, 0, 1],
            [1, 0, 0, 1, 0],
            [1, 0, 1, 0, 1],
            [1, 1, 0, 0, 1],
            [1, 1, 1, 1, 1],
        ]
        sol_fa = design_circuit_auto(
            input_names=["A", "B", "Cin"],
            output_names=["Sum", "Cout"],
            table_data=fa_rows,
        )
        self.assertTrue(sol_fa.is_verified)
        self.assertLessEqual(sol_fa.total_gate_count, 5)


if __name__ == "__main__":
    unittest.main()

