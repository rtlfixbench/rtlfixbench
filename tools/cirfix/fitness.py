import os
import sys
import json
import argparse

DEBUG = False
X_WEIGHT = 2
WEIGHTS_FILE = 'weights.json'

def get_weights(proj_dir=None):
    try:
        file_name = WEIGHTS_FILE if not proj_dir else os.path.join(proj_dir, WEIGHTS_FILE)
        with open(file_name) as f:
            weights = json.loads(f.read())
    except IOError as e:
        sys.exit(f"Error reading weighting file: {e}")
    return weights

def resize_sim(oracle, sim):
    oracle_len = len(oracle)
    sim_len = len(sim)
    num_bits = len(oracle[0].split(",")) - 1
    if len(oracle) > 2:
        clk_len = float(oracle[2].split(",")[0]) - float(oracle[1].split(",")[0])
        last_clk = eval(oracle[oracle_len - 1].split(",")[0])
    else:
        clk_len = 100 # arbirtray clk_len, doesn't matter anyways
        last_clk = 0
    
    if oracle_len > sim_len:
        for i in range(oracle_len - sim_len):
            tmp_str = str(last_clk + (i + 1) * clk_len)
            for i in range(num_bits):
                tmp_str += ",x"
            tmp_str += "\n"
            sim.append(tmp_str)
    elif oracle_len < sim_len:
        for i in range(sim_len - oracle_len):
            sim.pop()
    return oracle, sim

def resize_clkcycle_outputs(tmp_oracle, tmp_sim):
    if len(tmp_oracle) > len(tmp_sim):
        diff = len(tmp_oracle) - len(tmp_sim)
        for _ in range(diff):
            tmp_sim.append('x')
    else:
        diff = len(tmp_sim) - len(tmp_oracle)
        for _ in range(diff):
            tmp_oracle.pop()
    return tmp_oracle, tmp_sim

def calculate_fitness(oracle, sim, weighting=False, proj_dir=None):
    weights = None
    if weighting:
        w = get_weights(proj_dir)
        if DEBUG:
            print(f"Loaded weights: {w}")
        header = [i.strip() for i in oracle[0].split(",")]
        var_names = header[1:]
        weights = []
        for var in var_names:
            if var in w:
                weights.append(w[var])
            else:
                print(f"Error: '{var}' not found in weights.")
                sys.exit(1)
    
    if len(oracle) != len(sim):
        oracle, sim = resize_sim(oracle, sim)
    
    fitness = 0
    total_possible = 0
    for cycle_index in range(1, len(oracle)):
        oracle_fields = [field.strip() for field in oracle[cycle_index].split(",")[1:]]
        sim_fields = [field.strip() for field in sim[cycle_index].split(",")[1:]]
        
        if len(oracle_fields) != len(sim_fields):
            oracle_fields, sim_fields = resize_clkcycle_outputs(oracle_fields, sim_fields)
        
        for field_index in range(len(oracle_fields)):
            oracle_signal = oracle_fields[field_index]
            sim_signal = sim_fields[field_index]
            
            if len(oracle_signal) != len(sim_signal):
                max_len = max(len(oracle_signal), len(sim_signal))
                oracle_signal = oracle_signal.rjust(max_len, '0')
                sim_signal = sim_signal.rjust(max_len, '0')

            for bit_index in range(len(oracle_signal)):
                weight = weights[field_index][bit_index] if weights else 1
                o_bit = oracle_signal[bit_index]
                s_bit = sim_signal[bit_index]
                ignore = o_bit.lower() in ('x', 'z')
                multiplier = X_WEIGHT if ignore else 1
                if o_bit == s_bit or ignore:
                    fitness += weight * multiplier
                    total_possible += weight * multiplier
                else:
                    fitness -= weight * multiplier
                    total_possible += weight * multiplier
    
    return fitness, total_possible

def main():
    parser = argparse.ArgumentParser(description="Compute fitness from oracle and output files.")
    parser.add_argument("oracle", help="Path to the CSV file containing oracle data. This file serves as the reference dataset for fitness computation.")
    parser.add_argument("output", help="Path to the CSV file containing simulation outputs. These results will be compared against the oracle data.")
    args = parser.parse_args()

    try:
        with open(args.oracle, "r") as f:
            oracle_lines = f.readlines()
    except IOError as e:
        sys.exit(f"Error reading oracle file: {e}")

    try:
        with open(args.output, "r") as f:
            sim_lines = f.readlines()
    except IOError as e:
        sys.exit(f"Error reading output file: {e}")

    weighting = os.path.exists(WEIGHTS_FILE)
    fitness, total_possible = calculate_fitness(oracle_lines, sim_lines, weighting)
    ff = max(fitness / total_possible, 0)
    print(f"Fitness score: {ff}")

if __name__ == "__main__":
    main()
