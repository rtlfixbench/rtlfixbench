import os
import sys
import time
import json
import shutil
import subprocess
import pandas as pd
from pathlib import Path

TIMEOUT_COMPILE = 10
TIMEOUT_SIMULATE = 20

INFO = True
DEBUG_INFO = True
SHOW_EVAL_CANDIDATE = False

_utils_dir = Path(__file__).parent.resolve()
_root_dir = _utils_dir.parent.parent
_rtlrepair_dir = _root_dir / 'tools' / 'rtlrepair'

def get_proj_name(proj: Path):
    return os.path.basename(proj)

def get_interface_file(proj: Path):
    return os.path.join(proj, 'interface.json')

def get_output_file(proj: Path):
    return os.path.join(proj, 'output.csv')

def get_oracle_file(proj: Path):
    return proj / 'oracle.csv'

def get_testbench_file(proj: Path):
    return proj / 'tb.v'

def get_result_file(proj: Path):
    return proj / 'result.csv'

def get_testbench_spec(proj: Path):
    return proj / 'tb.csv'

def get_spec_file(proj: Path):
    return proj / 'spec.toml'

def get_candidate_file(proj: Path, original: str=None):
    if original == None:
        return proj / 'cand.v'
    else:
        return proj / f'cand_{original}'

def get_minimized_file(proj: Path):
    return proj / 'minimized.v'

def get_project_file(proj: Path):
    return proj / 'project.json'

def get_results_dir(proj: Path):
    return proj / 'results'

def get_bugs_dir(proj: Path):
    return proj / 'bugs'

def get_bug_path(proj: Path, bug_file: Path):
    return get_bugs_dir(proj) / bug_file

def get_file_list(proj: Path, bug_list: list, sources: list, modify: bool=False):
    file_list = []
    bugs_dir = get_bugs_dir(proj)
    for src in sources:
        for bug in bug_list:
            if bug['original'] == src:
                if not modify:
                    src_file = bugs_dir / bug['buggy']
                else:
                    src_file = proj / get_candidate_file(proj, bug['original'])
            else:
                src_file = proj / src
            if not os.path.exists(src_file):
                err(f"The file {src_file} was not found in the project '{get_proj_name(proj)}'.")
            file_list.append(src_file)
    return file_list

def get_signal_file(proj: Path, bug_name: str):
    results_dir = get_results_dir(proj)
    return results_dir / f'{bug_name}.signals'

def get_wave_file(proj: Path, bug_name: str = None):
    name = get_proj_name(proj) if bug_name == None else bug_name
    results_dir = get_results_dir(proj)
    return results_dir / f'{name}.vcd'

def get_osdd_output_file(proj: Path, bug_name: str):
    results_dir = get_results_dir(proj)
    return results_dir / f'{bug_name}_osdd.toml'

def get_osdd(proj: Path, bug_name: str):
    gt_wave = get_wave_file(proj)
    buggy_wave = get_wave_file(proj, bug_name)
    signal_file = get_signal_file(proj, bug_name)
    osdd_file = _rtlrepair_dir / 'osdd' / 'target' / 'release' / 'osdd'
    for i in [gt_wave, buggy_wave, signal_file, osdd_file]:
        if not os.path.exists(i):
            raise Exception(f'failed to find {i}')
    cmd = [osdd_file,
        f'--gt-wave={gt_wave}',
        f'--buggy-wave={buggy_wave}',
        f'--signals={signal_file}']
    r = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)
    first_state, first_output = [int(p) for p in r.stdout.decode('utf-8').split(',')]
    return first_state, first_output

def get_settings(proj: Path, absolute_path: bool = False):
    settings = {}
    project_file = get_project_file(proj)
    if os.path.exists(project_file):
        with open(project_file) as f:
            settings = json.loads(f.read())
    if absolute_path:
        sources = settings['sources']
        settings['sources'] = [proj / i for i in sources]
    return settings

def get_other_sources(proj: Path, bug_name: str, bug_file: Path = None):
    settings = get_settings(proj)
    sources = settings["sources"].copy()
    bug = settings["bugs"][bug_name][0]
    if bug_file:
        assert bug_file.name == bug['buggy']
    match = False
    for i in range(len(sources)):
        if sources[i] == bug["original"]:
            del sources[i]
            match = True
            break
    if not match:
        raise Exception(f'failed to find {bug["original"]} in sources')
    return [proj / i for i in sources]

def move_file(src: Path, dst_dir: Path, new_name: Path):
    if os.path.exists(src):
        os.makedirs(dst_dir, exist_ok=True)
        shutil.move(src, dst_dir / new_name)

def save_fixed_module(proj: Path, bug_name: str, file_candidate: Path=None, file_minimized: Path=None):
    results_dir = get_results_dir(proj)
    if file_candidate != None:
        os.makedirs(results_dir, exist_ok=True)
        move_file(file_candidate, results_dir, f"{bug_name}_fixed.v")
    if file_minimized != None:
        if os.path.exists(file_minimized):
            os.remove(file_minimized)

def check_output(proj: Path):
    oracle_file = get_oracle_file(proj)
    with open(oracle_file) as f:
        oracle = f.readlines()
    output_file = get_output_file(proj)
    with open(output_file) as f:
        output = f.readlines()
    fields = oracle[0].split(",")[1:]
    mismatch_info = ''
    for cycle_index in range(1, len(oracle)):
        oracle_fields = [field.strip() for field in oracle[cycle_index].split(",")[1:]]
        output_fields = [field.strip() for field in output[cycle_index].split(",")[1:]]
        
        if len(oracle_fields) != len(output_fields):
            raise Exception(f'invalid output cycles of {proj}')
        
        for field_index in range(len(oracle_fields)):
            oracle_signal = oracle_fields[field_index]
            output_signal = output_fields[field_index]
            width_oracle_signal = len(oracle_signal)
            width_output_signnal = len(output_signal)
            assert(width_oracle_signal >= width_output_signnal)
            for bit_index in range(width_output_signnal):
                if bit_index < width_output_signnal:
                    oracle_bit = oracle_signal[bit_index]
                    output_bit = output_signal[bit_index]
                    ignore = oracle_bit.lower() in ('x', 'z')
                    if oracle_bit != output_bit and not ignore:
                        mismatch_info = f'Mismatch in {fields[field_index].strip()} at cycle {oracle[cycle_index].split(",")[0]}: expected {oracle_signal}, got {output_signal}'
                        return False, mismatch_info
                else:
                    if oracle_signal[bit_index] != '0':
                        mismatch_info = f'Mismatch in {fields[field_index].strip()} at cycle {oracle[cycle_index].split(",")[0]}: expected 1, got 0'
                        return False, mismatch_info
    return True, mismatch_info

def get_err_report(proj: Path):
    spec = get_testbench_spec(proj)
    spec_df = pd.read_csv(spec)
    output_file = get_output_file(proj)
    output_df = pd.read_csv(output_file)
    spec_df.update(output_df)
    result_file = get_result_file(proj)
    spec_df.to_csv(result_file, index=False)
    
    with open(result_file) as f:
        result = f.read()

    with open(spec) as f:
        oracle = f.read()

    err = f"""

Actual input/output signals (CSV format):
=============================
{result}

Expected input/output signals (CSV format; signals marked with 'x' are undefined or irrelevant for the corresponding cycle and should not be considered during comparison):
=============================
{oracle}"""
    
    return err

def simulate(proj: Path, file_name: Path):
    output_file = get_output_file(proj)
    if os.path.exists(output_file):
        os.remove(output_file)
    sim_start_time = time.time()
    err_compile, err_simulate = tb_eval(proj, [file_name])
    if not err_compile and not err_simulate:
        success, mismatch_info = check_output(proj)
        if not success:
            err_simulate = get_err_report(proj)
            err_simulate = f'{mismatch_info} \n {err_simulate}'
    sim_end_time = time.time()
    return err_compile, err_simulate, sim_end_time - sim_start_time

def tb_eval(proj: Path, file_list: list, tb_file: str = "tb.v", bug_name: str = None):
    original_directory = os.getcwd()
    simv_path = proj / "simv"
    vcd_path = get_wave_file(proj)
    compile_command = ["iverilog", "-o", "simv", tb_file] + file_list
    simulate_command = ["vvp", "simv"]
    err_simulate = ""
    err_compile = ""
    try:
        os.chdir(proj)
        compile_result = subprocess.run(
            compile_command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_COMPILE
        )
        if compile_result.returncode == 0:
            if SHOW_EVAL_CANDIDATE:
                print("Compilation successful.")
                print("Compilation Output:")
                print(compile_result.stdout)
            simulate_result = subprocess.run(
                simulate_command,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TIMEOUT_SIMULATE
            )
            if SHOW_EVAL_CANDIDATE:
                print("Simulation Output:")
                print(simulate_result.stdout)
            if simulate_result.returncode != 0:
                err_simulate = simulate_result.stderr
        else:
            if SHOW_EVAL_CANDIDATE:
                print("Compilation failed.")
                print("Compilation Error Output:")
                print(compile_result.stderr)
            err_compile = compile_result.stderr
    except subprocess.TimeoutExpired as e:
        if SHOW_EVAL_CANDIDATE:
            print(f"Command timed out after {e.timeout} seconds.")
            print("Error output:")
            print(e.stderr)
    except subprocess.CalledProcessError as e:
        if SHOW_EVAL_CANDIDATE:
            print("Command failed with return code:", e.returncode)
            print("Error output:")
            print(e.stderr)
    except FileNotFoundError as e:
        print("Command not found:", e)
    finally:
        os.chdir(original_directory)
        if simv_path.exists():
            try:
                os.remove(simv_path)
            except Exception as e:
                print(f"Failed to remove {simv_path}: {e}")
        if bug_name and vcd_path.exists():
            buggy_wave = get_wave_file(proj, bug_name)
            shutil.move(vcd_path, buggy_wave)
        return err_compile, err_simulate

def err(text: str):
    print(f'Error: {text}')
    sys.exit(1)

def info(text: str):
    if INFO:
        print(text)

def debug_info(text: str):
    if DEBUG_INFO:
        print(text)
