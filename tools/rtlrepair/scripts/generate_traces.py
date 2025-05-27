#!/usr/bin/env python3
# Copyright 2023 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import os
import sys
import argparse
from pathlib import Path

_script_dir = Path(__file__).parent.resolve()
sys.path.append(str(_script_dir.parent))

from benchmarks import SimResult, check_against_oracle

_root_dir = _script_dir.parent.parent.parent
_utils_dir = _root_dir / "resources" / "utils"
sys.path.append(str(_utils_dir))

import env
from checker import add_checker

def save_result(file_name: Path, proj_name: str, bug_name: str, result: SimResult):
    with open(file_name, 'w') as ff:
        print("[[result]]", file=ff)
        print(f'project="{proj_name}"', file=ff)
        print(f'bug="{bug_name}"', file=ff)
        print(f'no_output={str(result.no_output).lower()}', file=ff)
        print(f'failed_at={str(result.failed_at)}', file=ff)
        print(f'fail_msg="""{result.fail_msg}"""', file=ff)
        print(f'cycles={str(result.cycles)}', file=ff)

def gen_buggy_trace(proj: Path, bug_name: str, file_list: list):
    proj_name = env.get_proj_name(proj)
    env.info(f'Generating trace for {proj_name} related to bug {bug_name}')
    env.tb_eval(proj, file_list, bug_name=bug_name)
    oracle = env.get_oracle_file(proj)
    output = env.get_output_file(proj)
    result = check_against_oracle(oracle, output)
    results_dir = env.get_results_dir(proj)
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    file_name = os.path.join(results_dir, f"{bug_name}_report.toml")
    save_result(file_name, proj_name, bug_name, result)

def gen_gt_trace(proj: Path, name: str, file_list: list):
    env.info(f'Generating ground truth trace for {name}')
    env.tb_eval(proj, file_list)

def main():
    parser = argparse.ArgumentParser(description='Generate traces.')
    parser.add_argument('--basic', action='store_true', help='Run tests using handcrafted benchmarks targeting specific RTL fixes.', default=True)
    parser.add_argument('--extend', action='store_true', help='Run tests using synthetic benchmarks to assess overall RTL repair capabilities.', default=True)
    args = parser.parse_args()
    add_checker(checker=gen_buggy_trace, basic=args.basic, extend=args.extend, vcd=True)
    add_checker(checker=gen_gt_trace, basic=args.basic, extend=args.extend, vcd=True, ground_truth=True)

if __name__ == '__main__':
    main()
