# Truth Table to Logic Circuit Synthesis System

A zero-dependency Python tool that takes any **Truth Table** (inputs, outputs, and optional Don't Cares `X`) along with your **Allowed Building Blocks** (logic gates or custom blocks) and generates:
1. **Total Gate Count** (broken down by gate type and logic depth/levels)
2. **Where Each Input Goes** (input fan-out and exact gate/pin routing)
3. **How to Connect Each Gate** (step-by-step pin-to-pin wiring instructions)
4. **Boolean Equations & Mermaid Circuit Diagram**
5. **100% Truth Table Simulation & Verification**

---

## Requirements

- **Python 3.8+** (uses only the Python standard library — no `pip install` needed).

---

## Quick Start: 6 Ways to Run It

Open a terminal (PowerShell or Command Prompt) in `c:\Users\Administrator\truth table`.

### 1. Launch the Desktop GUI
Run the interactive 60-FPS workbench with clickable Truth Table editor, Building Block selector, Wiring Tables, and Live Animated Circuit Schematic:
```powershell
python truth_table_gui.py
```
*(or `python truth_table_system.py --gui`)*

---

### 2. Automatic Simplest Circuit CLI (`--auto`)
Let the system automatically test multiple gate libraries (`AND/OR/NOT`, `AND/OR/XOR`, `NAND only`, `NOR only`, etc.), compare SOP vs POS forms, extract shared terms, and configure the **simplest possible circuit** (fewest gates):
```powershell
python truth_table_system.py --inputs "A,B" --outputs "Y" --values "0,1,1,0" --auto
```

Multi-output example (Full Adder `Sum, Cout`):
```powershell
python truth_table_system.py --inputs "A,B,Cin" --outputs "Sum,Cout" --values "0,0,1,0,1,0,0,1,1,0,0,1,0,1,1,1" --auto
```

---

### 3. Interactive Step-by-Step Wizard
If you want the program to prompt you for your inputs, outputs, building blocks, and truth table rows one by one:
```powershell
python truth_table_system.py --interactive
```
*(or `python truth_table_system.py -i`)*

Example session:
```text
Enter input variable names separated by commas (e.g. A, B, C): A, B
Enter output variable name(s) separated by commas (e.g. Y or Sum, Cout): Y
Enter building blocks, preset, or 'AUTO' (default: AUTO): AUTO
  Row  0 [A=0 B=0] -> Y = 0
  Row  1 [A=0 B=1] -> Y = 1
  Row  2 [A=1 B=0] -> Y = 1
  Row  3 [A=1 B=1] -> Y = 0
```

---

### 4. Built-in Demonstration Circuits
See three complete examples (1-Bit Full Adder, NAND-only XOR, and 3-Input Majority Voter):
```powershell
python truth_table_system.py --demo
```

---

### 5. Run Directly from Command-Line Arguments

Pass `--inputs`, `--outputs`, `--values` (truth table outputs in binary counting order `00..0` to `11..1`), and optional `--blocks` or `--auto`:

- **Example A: 2-input XOR using ONLY `NAND` gates**
  ```powershell
  python truth_table_system.py --inputs "A,B" --outputs "Y" --values "0,1,1,0" --blocks "NAND"
  ```

- **Example B: 3-input Majority Circuit using `AND, OR, NOT`**
  ```powershell
  python truth_table_system.py --inputs "A,B,C" --outputs "M" --values "0,0,0,1,0,1,1,1" --blocks "AND,OR,NOT"
  ```

- **Example C: Truth Table with Don't Care (`X`) values**
  ```powershell
  python truth_table_system.py --inputs "A,B,C" --outputs "Y" --values "0,0,1,X,0,1,1,1" --blocks "AND,OR,NOT"
  ```

- **Example D: Multi-Output Circuit (Half Adder: `Sum` and `Carry`)**
  For 2 outputs across 4 rows, list the pairs in order (`0,0`, `1,0`, `1,0`, `0,1`):
  ```powershell
  python truth_table_system.py --inputs "A,B" --outputs "Sum,Carry" --values "0,0,1,0,1,0,0,1" --blocks "XOR,AND"
  ```

---

### 6. Run from a JSON File

Create a file (e.g., `my_circuit.json`):
```json
{
  "inputs": ["A", "B", "Cin"],
  "outputs": ["Sum", "Cout"],
  "blocks": ["XOR", "AND", "OR"],
  "table": [
    [0, 0, 0,  0, 0],
    [0, 0, 1,  1, 0],
    [0, 1, 0,  1, 0],
    [0, 1, 1,  0, 1],
    [1, 0, 0,  1, 0],
    [1, 0, 1,  0, 1],
    [1, 1, 0,  0, 1],
    [1, 1, 1,  1, 1]
  ]
}
```
Then run:
```powershell
python truth_table_system.py --json my_circuit.json
```

---

## Using It in Your Own Python Script

Import `design_circuit` (and optionally `create_custom_block`) from `truth_table_system.py`:

```python
from truth_table_system import design_circuit, create_custom_block

# 1. Provide Truth Table + Building Blocks
solution = design_circuit(
    input_names=["A", "B", "Cin"],
    output_names=["Sum", "Cout"],
    table_data=[
        # A, B, Cin, Sum, Cout
        [0, 0, 0, 0, 0],
        [0, 0, 1, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 1, 1, 0, 1],
        [1, 0, 0, 1, 0],
        [1, 0, 1, 0, 1],
        [1, 1, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ],
    building_blocks=["XOR", "AND", "OR"],
)

# 2. Print the Full Wiring & Gate Count Report
print(solution.format_report())

# 3. Access Data Programmatically
print("Total Gate Count:", solution.total_gate_count)
print("Gate Breakdown  :", solution.gate_count_by_type())
print("Input Routing   :", solution.get_input_routing())
print("Equations       :", solution.get_boolean_expressions())
```

### Supported `table_data` Formats in Python
1. **Output list** (for binary rows `00..0` to `11..1`):
   `table_data=[0, 1, 1, 0]` (or `[(0, 0), (1, 0), (1, 0), (0, 1)]` for multiple outputs)
2. **Full rows `[inputs..., outputs...]`**:
   `table_data=[[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]]`
3. **Dictionary `{input_tuple: output}`**:
   `table_data={(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): "X"}`

---

## Available Building Blocks

| Category | Names | Description |
| :--- | :--- | :--- |
| **1-Input Gates** | `NOT`, `BUF` | Inverter (`~A`), Buffer (`A`) |
| **2-Input Gates** | `AND`, `OR`, `NAND`, `NOR`, `XOR`, `XNOR`, `IMP`, `NIMP` | Standard 2-input logic gates |
| **3-Input Gates** | `AND3`, `OR3`, `NAND3`, `NOR3`, `XOR3` | 3-input wide gates |
| **4-Input Gates** | `AND4`, `OR4`, `NAND4`, `NOR4` | 4-input wide gates |
| **Multiplexer** | `MUX2` | 2:1 Mux (`S`, `D0`, `D1` where `out = D1 if S=1 else D0`) |
| **Presets** | `basic`, `standard`, `nand_only`, `nor_only`, `mux`, `mux_only` | Shorthand groups of gates |

### Defining a Custom Building Block
You can also define your own custom chip/module and pass it in `building_blocks`:
```python
from truth_table_system import create_custom_block, design_circuit

# Custom 3-input Majority Gate (outputs 1 when at least 2 inputs are 1)
maj3 = create_custom_block(
    name="MAJ3",
    pin_names=("in1", "in2", "in3"),
    truth_table_or_func=lambda a, b, c: 1 if (a + b + c) >= 2 else 0,
    is_symmetric=True,
)

sol = design_circuit(
    input_names=["A", "B", "C"],
    output_names="M",
    table_data=[0, 0, 0, 1, 0, 1, 1, 1],
    building_blocks=[maj3],
)
print(sol.format_report())
```

---

## Understanding the Output Report

Every synthesis run prints 6 sections:
1. **1. GATE COUNT SUMMARY**: Total number of gates, logic depth (number of levels on the critical path), and exact count of each building block type.
2. **2. WHERE EACH INPUT GOES (INPUT ROUTING TABLE)**: Lists every primary input (`A`, `B`, ...), its fan-out count, and the exact gate & pin it connects to (e.g., `Input 'A' -> U1.in1 (NAND), U2.in1 (NAND)`).
3. **3. HOW TO CONNECT EACH GATE (STEP-BY-STEP WIRING GUIDE)**: Lists every gate (`U1`, `U2`, ...), which signal connects to each of its input pins, and what its output net (`n1`, `n2`, ...) feeds next.
4. **4. PRIMARY OUTPUT CONNECTIONS & BOOLEAN EQUATIONS**: Shows which gate output (or input/constant) drives each final output pin and its Boolean formula.
5. **5. TRUTH TABLE VERIFICATION**: Compares Expected (`Exp`) vs. Simulated (`Sim`) outputs across all rows.
6. **6. MERMAID CIRCUIT SCHEMATIC**: A flowchart schematic that renders in Markdown/GitHub/VS Code.

---

## Running Unit Tests

To run the automated test suite:
```powershell
python -m unittest discover -v
```
