import os
import sys
import json
import random
import argparse
import subprocess
from cirfix import DEBUG, WEIGHTS_FILE
from pyverilog.vparser.parser import parse

NUM_VECTORS = 100

def extract_module_name(verilog_file):
    try:
        ast, _ = parse([verilog_file])
        for module in ast.description.definitions:
            if module.__class__.__name__ == "ModuleDef":
                return module.name
    except Exception as e:
        print(f"Error: Could not parse module information from '{verilog_file}': {e}", file=sys.stderr)
        sys.exit(1)
    return None

def generate_fuzzed_inputs(interface, output_file, settings, num_vectors=NUM_VECTORS):
    excluded = {settings["clock"], settings["reset"]}
    input_ports = [port for port in interface 
                   if port["direction"] == "input" and port["name"] not in excluded]
    
    with open(output_file, "w") as f:
        header = ",".join([port["name"] for port in input_ports])
        f.write(header + "\n")
        for _ in range(num_vectors):
            values = []
            for port in input_ports:
                width = port["width"]
                rand_val = bin(random.getrandbits(width))[2:].zfill(width)
                values.append(rand_val)
            f.write(",".join(values) + "\n")
    
    if DEBUG:
        print(f"Generated {num_vectors} fuzzed vector(s) in '{output_file}'.")

def generate_testbench(interface, settings, inputs_filename, outputs_filename, tb_filename, prog):
    dut_module = extract_module_name(prog)
    if not dut_module:
        print("Error: Could not determine the DUT module name.", file=sys.stderr)
        sys.exit(1)
    
    excluded = {settings["clock"], settings["reset"]}
    csv_inputs = [port for port in interface 
                  if port["direction"] == "input" and port["name"] not in excluded]
    outputs = [port for port in interface if port["direction"] == "output"]
    try:
        with open(inputs_filename, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error: could not read '{inputs_filename}': {e}", file=sys.stderr)
        sys.exit(1)
    
    if len(lines) < 2:
        print("Error: No stimulus vectors found in CSV file.", file=sys.stderr)
        sys.exit(1)
    
    header = lines[0].split(",")
    stimulus_vectors = [line.split(",") for line in lines[1:]]
    
    with open(tb_filename, "w") as tb:
        tb.write("module tb_fuzz;\n\n")
        
        # Clock and Reset signals
        tb.write(f"    reg {settings['clock']};\n")
        tb.write(f"    reg {settings['reset']};\n\n")
        
        # Other input signals (driven by CSV stimulus)
        for port in csv_inputs:
            name = port["name"]
            width = port["width"]
            if width == 1:
                tb.write(f"    reg {name};\n")
            else:
                tb.write(f"    reg [{width-1}:0] {name};\n")
        tb.write("\n")
        
        # Output signals
        for port in outputs:
            name = port["name"]
            width = port["width"]
            if width == 1:
                tb.write(f"    wire {name};\n")
            else:
                tb.write(f"    wire [{width-1}:0] {name};\n")
        tb.write("\n")
        
        # Instantiate the DUT
        tb.write(f"    {dut_module} dut (\n")
        port_names = [port["name"] for port in interface]
        for idx, pname in enumerate(port_names):
            sep = "," if idx < len(port_names)-1 else ""
            tb.write(f"        .{pname}({pname}){sep}\n")
        tb.write("    );\n\n")
        
        # Clock generation
        tb.write("    initial begin\n")
        tb.write(f"        {settings['clock']} = 0;\n")
        tb.write("        forever #5 {0} = ~{0};\n".format(settings['clock']))
        tb.write("    end\n\n")
        
        # Reset generation
        tb.write("    initial begin\n")
        if settings["reset_polarity"] == "active_low":
            tb.write(f"        {settings['reset']} = 0;\n")
            tb.write("        #10;\n")  # Delay after reset assertion
            tb.write(f"        {settings['reset']} = 1;\n")
            tb.write("        #10;\n")  # Wait time after de-assertion
        else: 
            # Default to active_high if not specified correctly
            tb.write(f"        {settings['reset']} = 1;\n")
            tb.write("        #10;\n")
            tb.write(f"        {settings['reset']} = 0;\n")
            tb.write("        #10;\n")
        tb.write("    end\n\n")
        
        # File I/O for dumping simulation outputs
        tb.write("    integer output_file;\n")
        tb.write("    initial begin\n")
        tb.write(f"        output_file = $fopen(\"{outputs_filename}\", \"w\");\n")
        tb.write("        if (output_file == 0) begin\n")
        tb.write(f"            $display(\"Error: Could not open file {outputs_filename}.\");\n")
        tb.write("            $finish;\n")
        tb.write("        end\n")
        
        # Write header to the output file
        tb.write("        $fwrite(output_file, \"Time")
        for port in outputs:
            tb.write(f", {port['name']}")
        tb.write("\\n\");\n")
        
        # Apply stimulus from CSV file (fuzzed inputs)
        tb.write("        #20;\n")
        delay_between = 10
        for vec in stimulus_vectors:
            for col_idx, port in enumerate(csv_inputs):
                csv_name = header[col_idx].strip()
                if csv_name != port["name"]:
                    print(f"Warning: CSV header '{csv_name}' does not match expected signal '{port['name']}'.", file=sys.stderr)
                value = vec[col_idx].strip()
                if port["width"] == 1:
                    tb.write(f"        {port['name']} = 1'b{value};\n")
                else:
                    tb.write(f"        {port['name']} = {port['width']}'b{value};\n")
            tb.write(f"        #{delay_between};\n")
            
            # Write time and output signal values to file
            tb.write("        #0;\n")
            # Build the format string for $fwrite
            format_str = "%0t"
            for _ in outputs:
                format_str += ", %b"
            format_str += "\\n"
            
            tb.write(f"        $fwrite(output_file, \"{format_str}\", $time")
            for port in outputs:
                tb.write(f", {port['name']}")
            tb.write(");\n")
        
        # Close the output file after the simulation
        tb.write("        $fclose(output_file);\n")
        
        tb.write("        $finish;\n")
        tb.write("    end\n")
        tb.write("endmodule\n")
    
    try:
        os.remove("simv")
    except FileNotFoundError:
        pass

    compile_proc = subprocess.run([
        "iverilog", "-g2001",
        tb_filename, prog,
        "-o", "simv"
    ])
    if compile_proc.returncode != 0:
        print("Error: iverilog compilation failed.", file=sys.stderr)
        sys.exit(1)
    
    sim_proc = subprocess.run(["vvp", "simv"], capture_output=True, text=True)
    if sim_proc.returncode != 0:
        print("Error: simulation (vvp) failed.", file=sys.stderr)
        sys.exit(1)

def load_json(file_json):
    try:
        with open(file_json, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: '{file_json}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from '{file_json}': {e}", file=sys.stderr)
        sys.exit(1)

def run_testbench(prog, tb_file, k):
    for iteration in range(k):
        try:
            os.remove("simv")
        except FileNotFoundError:
            pass
        compile_proc = subprocess.run([
            "iverilog", "-g2001",
            tb_file, prog,
            "-o", "simv"
        ])
        if compile_proc.returncode != 0:
            print(f"Iteration {iteration}: iverilog compilation failed.", file=sys.stderr)
            continue
        sim_proc = subprocess.run(["vvp", "simv"])
        if sim_proc.returncode != 0:
            print(f"Iteration {iteration}: simulation (vvp) failed.", file=sys.stderr)
            continue
        os.remove("simv")

def strip_items(items):
    return [item.strip() for item in items]

def is_bit_variable(bits):
    return any(bits[i] != bits[i + 1] for i in range(len(bits) - 1))

def get_differing_degree(bits):
    num_bits = len(bits)
    zeros = bits.count("0")
    ones = bits.count("1")
    return abs((zeros / num_bits) - (ones / num_bits))

def get_weights(results):
    header = strip_items(results[0].split(","))
    var_names = header[1:]
    data = [strip_items(line.split(","))[1:] for line in results[1:]]
    weights = {}
    for col, var in enumerate(var_names):
        values = [row[col] for row in data]
        transposed_bits = list(zip(*values))
        bit_width = len(transposed_bits)
        bit_weights = []
        for i in range(bit_width):
            bits = list(transposed_bits[i])
            if not is_bit_variable(bits):
                weight = 1
            else:
                degree = get_differing_degree(bits)
                weight = 2 * (1 / (2 ** degree))
            bit_weights.append(weight)
        weights[var] = bit_weights
    return weights

def main():
    parser = argparse.ArgumentParser(description="Fuzzing-based bit weight analysis.")
    parser.add_argument("prog", help="Path to the Verilog program")
    parser.add_argument("interface", help="Path to JSON description of interface")
    parser.add_argument("settings", help="Path to the file of settings")
    parser.add_argument("k", nargs="?", type=int, default=3, help="Number of test iterations")
    parser.add_argument("-o", "--output", help="Specify the path of the output file.", type=str, default=None)
    args = parser.parse_args()

    tb_filename = "tb_fuzz.v"
    inputs_filename = "fuzz_inputs.csv"
    outputs_filename = "fuzz_outputs.csv"
    settings = load_json(args.settings)
    interface = load_json(args.interface)
    generate_fuzzed_inputs(interface, inputs_filename, settings)
    generate_testbench(interface, settings, inputs_filename, outputs_filename, tb_filename, args.prog)
    run_testbench(args.prog, tb_filename, args.k)
    try:
        with open(outputs_filename) as f:
            results = f.readlines()
    except FileNotFoundError:
        print(f"Error: Fuzzing outputs {outputs_filename} not found.", file=sys.stderr)
        sys.exit(1)
    weights = get_weights(results)
    outfile_name = args.output if args.output else WEIGHTS_FILE
    with open(outfile_name, "w") as outfile:
        json.dump(weights, outfile, indent=4)

if __name__ == "__main__":
    main()
