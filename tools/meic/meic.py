import os
import sys
import json
import time
import argparse
from pathlib import Path
from gpt import DebugGPT, ScoreGPT

_meic_dir = Path(__file__).parent.resolve()
_root_dir = _meic_dir.parent.parent
_resources_dir = _root_dir / "resources"
_settings_file = _resources_dir / "configs" / "meic" / "settings.json"
_utils_dir = _resources_dir / "utils"

sys.path.append(str(_utils_dir))

import env
from env import info, debug_info
from checker import add_checker

DEBUG_ROUNDS = 10
DEBUG_RETRY_MAX = 3

with open(_settings_file, 'r') as f:
    config = json.load(f)

def minimum_lines(code_lines):
    return code_lines * 2 / 5 + 2

def can_accept(design_score, fixed_score):
    return int(fixed_score) + 10 >= int(design_score)

def start_debug(proj, bug_file):
    sim_time_list = []
    debug_time_list = []
    score_time_list = []
    debug_gpt = DebugGPT(config) 
    score_gpt = ScoreGPT(config)
    spec_file = env.get_spec_file(proj)
    bug_file_name = os.path.basename(bug_file)
    candidate_file = env.get_candidate_file(proj)
    with open(spec_file) as f:
        spec = f.read()
    with open(bug_file) as f:
        design_code = f.read()
    debug_start_time = time.time()
    err_compile, err_simulate, sim_time = env.simulate(proj, bug_file)
    if err_compile:
        debug_info(f'\n[Compile]\n{err_compile}')
    if err_simulate:
        debug_info(f'\n[Simulation]\n{err_simulate}')
    sim_time_list.append(sim_time)
    try:
        success = False
        for _ in range(DEBUG_ROUNDS):
            success = not err_compile and not err_simulate
            if success:
                break
            report_type, report_content = ("compile", err_compile) if err_compile else ("simulation", err_simulate)
            for _ in range(DEBUG_RETRY_MAX):
                try:
                    debug_info(f'\n[Report]\n\n{report_content}')
                    fixed_code, fixing_time = debug_gpt.request(spec, design_code, report_type, report_content)
                    debug_time_list.append(fixing_time)
                    break
                except Exception as e:
                    print(e)
                    continue
            design_filelines = len(design_code.split("\n"))
            if fixed_code:
                fixed_filelines = len(fixed_code.split("\n"))
                if fixed_filelines > minimum_lines(design_filelines):
                    design_score, fixed_score, score_time = score_gpt.request(spec, design_code, fixed_code)
                    debug_info(f'\n[Scores]\ndesign_score={design_score}\nfixed_score={fixed_score}')
                    score_time_list.append(score_time)
                    if can_accept(design_score, fixed_score):
                        with open(candidate_file, 'w') as f:
                            f.write(fixed_code)
                        err_compile, err_simulate, sim_time = env.simulate(proj, candidate_file)
                        if err_compile:
                            debug_info(f'\n[Compile]\n{err_compile}')
                        if err_simulate:
                            debug_info(f'\n[Simulation]\n{err_simulate}')
                        sim_time_list.append(sim_time)
                        design_code = fixed_code
                        debug_info(f'\n[Fixed Code]{fixed_code}')
        debug_end_time = time.time()
        total_time = debug_end_time - debug_start_time
        sim_time = sum(sim_time_list)
        debug_time = sum(debug_time_list)
        score_time = sum(score_time_list)
        info(f'[Results]\ndesign={bug_file_name}\nsim_time={sim_time}\ndebug_time={debug_time}\nscore_time={score_time}\ntotal_time={total_time}\nfixed={success}')
        return success
    except Exception as e:
        print(e)
        return False

def meic_checker(proj: Path, bug_name: str, file_list: list):
    assert(len(file_list) == 1)
    bug_file = file_list[0]
    success = start_debug(proj, bug_file)
    if success:
        candidate_file = env.get_candidate_file(proj)
        env.save_fixed_module(proj, bug_name, candidate_file)

def main():
    global LOG
    parser = argparse.ArgumentParser(description="MEIC")
    parser.add_argument("--log", action="store_true", help="Enable detailed logging for better debugging.")
    
    args = parser.parse_args()
    
    LOG = args.log
    add_checker(checker=meic_checker)

if __name__ == "__main__":
    main()
