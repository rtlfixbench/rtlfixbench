#!/usr/bin/env python3
# Copyright 2022-2023 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import sys
import argparse
from pathlib import Path
from dataclasses import dataclass

_script_dir = Path(__file__).parent.resolve()
sys.path.append(str(_script_dir))

from find_state import find_state_and_outputs

_root_dir = _script_dir.parent.parent.parent
_utils_dir = _root_dir / "resources" / "utils"
sys.path.append(str(_utils_dir))

import env
from checker import add_checker

@dataclass
class Result:
    project: str
    bug: str
    delta: int
    first_output_disagreement: int
    ground_truth_testbench_cycles: int
    notes: str
    warnings: list[str]

def write_osdd_toml(filename: Path, res: Result):
    with open(filename, 'w') as ff:
        print("[[osdd]]", file=ff)
        print(f'project="{res.project}"', file=ff)
        print(f'bug="{res.bug}"', file=ff)
        print(f'delta={res.delta}', file=ff)
        print(f'first_output_disagreement={res.first_output_disagreement}', file=ff)
        print(f'ground_truth_testbench_cycles={res.ground_truth_testbench_cycles}', file=ff)
        print(f'notes="{res.notes}"', file=ff)
        warnings = "[ " + ", ".join(f'"{w}"' for w in res.warnings) + " ]"
        print(f'warnings={warnings}', file=ff)

def common_list(a: list, b: list) -> list:
    return sorted(list(set(a) & set(b)))

def filer_mem_regs(states: list) -> list:
    """ yosys will generate some registers that serve to hold memory read or write signals, we chose to ignore these here """
    return [st for st in states if '/' not in st[0]]

def compare_traces(proj: Path, bug_name: str, file_list: list):
    settings = env.get_settings(proj, absolute_path=True)
    sources = settings["sources"]
    proj_name = env.get_proj_name(proj)
    top_module = settings['top_module']
    res = Result(project=proj_name, bug=bug_name,
                 delta=-1, first_output_disagreement=-1, ground_truth_testbench_cycles=-1,
                 notes="", warnings=[])
    
    # extract state and outputs from ground truth design
    gt_states, gt_outputs = find_state_and_outputs(proj, sources, top_module, "gt")
    gt_states = filer_mem_regs(gt_states)

    # extract state and outputs from buggy design
    buggy_states, buggy_outputs = find_state_and_outputs(proj, file_list, top_module, "buggy")
    buggy_states = filer_mem_regs(buggy_states)

    # if there is no state in the design, OSDD is always 0
    gt_no_state, buggy_no_state = len(gt_states) == 0, len(buggy_states) == 0
    if gt_no_state and buggy_no_state:
        res.delta = 0
        res.notes = "no state => delta=0"
        return res

    # compare states, see if they are the same
    if not gt_states == buggy_states:
        # if the buggy design adds state, we can try to see if (i.e. hope that) the same signal
        # exists in the ground truth design as a signal wire
        # TODO: how is the repair for something like this represented in the synthesized design
        #       with change templates applied?
        only_additional_buggy_states = set(gt_states).issubset(set(buggy_states))
        if only_additional_buggy_states:
            gt_states = buggy_states
        else:
            states_missing_from_buggy = set(gt_states) - set(buggy_states)
            print(f"WARN: states are not the same!\nMissing states in buggy design: {states_missing_from_buggy}")
            res.warnings.append("states are not the same!")
            res.warnings.append(f"Missing states in buggy design: {states_missing_from_buggy}")
            buggy_states = gt_states

    # display warning if outputs are not the same
    if not gt_outputs == buggy_outputs:
        print(f"WARN: outputs are not the same")
        print(f"Missing in buggy: {list(set(gt_outputs) - set(buggy_outputs))}")
        print(f"Additional in buggy: {list(set(buggy_outputs) - set(gt_outputs))}")
        res.warnings.append("outputs are not the same")
        res.warnings.append(f"Missing in buggy: {list(set(gt_outputs) - set(buggy_outputs))}")
        res.warnings.append(f"Additional in buggy: {list(set(buggy_outputs) - set(gt_outputs))}")

    # we are only interested in signals that are contained in both circuits, but the widths are allowed to differ
    interesting_states = common_list([n for n, _ in gt_states], [n for n, _ in buggy_states])
    interesting_outputs = common_list([n for n, _ in gt_outputs], [n for n, _ in buggy_outputs])

    # write signals to file
    signal_file = env.get_signal_file(proj, bug_name)
    with open(signal_file, 'w') as f:
        print(", ".join(interesting_states), file=f)
        print(", ".join(interesting_outputs), file=f)

    first_state, first_output = env.get_osdd(proj, bug_name)
    if first_output == -1:
        res.notes = "no disagreement found"
    else:
        assert first_state <= first_output
        res.first_output_disagreement = first_output
        if first_state == -1:
            delta = 0
        else:
            delta = first_output - first_state + 1
        res.delta = delta
    osdd_output_file = env.get_osdd_output_file(proj, bug_name)
    write_osdd_toml(osdd_output_file, res)

def main():
    parser = argparse.ArgumentParser(description='Generate traces.')
    parser.add_argument('--basic', action='store_true', help='Run tests using handcrafted benchmarks targeting specific RTL fixes.', default=True)
    parser.add_argument('--extend', action='store_true', help='Run tests using synthetic benchmarks to assess overall RTL repair capabilities.', default=True)
    args = parser.parse_args()
    add_checker(checker=compare_traces, basic=args.basic, extend=args.extend, vcd=True)

if __name__ == '__main__':
    main()
