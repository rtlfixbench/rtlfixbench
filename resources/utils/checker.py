import os
import sys
from pathlib import Path

_utils_dir = Path(__file__).parent.resolve()
sys.path.append(str(_utils_dir))
_benchmarks_dir = _utils_dir.parent.parent / "benchmarks"

import env
from env import err
from parser import extract_interface
from generator import generate_testbench

def check_project(checker, category, name, track=False, vcd=False, ground_truth=False):
    proj = category / name
    if os.path.isdir(proj):
        bugs_dir = proj / "bugs"
        if bugs_dir.exists():
            settings = env.get_settings(proj)
            if settings.get("ignore"):
                return
            init = False
            bugs = settings.get("bugs", [])
            oracle_file = env.get_oracle_file(proj)
            output_fiile = env.get_output_file(proj)
            interface_file = env.get_interface_file(proj)
            testbench_spec = env.get_testbench_spec(proj)
            testbench_file = env.get_testbench_file(proj)
            if not os.path.exists(testbench_spec):
                err(f"{testbench_spec} is not found.")
            top_module = settings.get("top_module", name)
            top_file = settings.get("top_file", f"{top_module}.v")
            sources = settings.get("sources", [])
            if not sources:
                 err(f"The sources were not found in the project '{name}'.")
            if track:
                checker(proj, bugs=bugs, top_module=top_module, top_file=Path(top_file), sources=[proj / i for i in [sources]])
                return
            file_path = os.path.join(proj, top_file)
            if not os.path.exists(file_path):
                err(f"The file {top_file} of top module was not found in the project '{name}'.")
            top_file = file_path
            for bug_name in bugs:
                name = env.get_proj_name(proj)
                if os.path.exists(output_fiile):
                    os.remove(output_fiile)
                if not init:
                    results_dir = env.get_results_dir(proj)
                    os.makedirs(results_dir, exist_ok=True)
                    vcd_file = env.get_wave_file(proj) if vcd else None
                    extract_interface(name, top_file, interface_file)
                    generate_testbench(
                        top_module,
                        settings.get("clock", "clk"),
                        interface_file,
                        testbench_spec,
                        oracle_file,
                        output_fiile,
                        testbench_file,
                        vcd_file=vcd_file)
                    if ground_truth:
                        checker(proj, name, [top_file])
                        break
                    init = True
                bug_list = bugs[bug_name]
                bugs_dir = env.get_bugs_dir(proj)
                file_list = env.get_file_list(proj, bug_list, sources)
                checker(proj, bug_name, file_list)

def add_checker(checker, track=False, vcd=False, ground_truth=False):
    for i in os.listdir(_benchmarks_dir):
        check_project(checker, _benchmarks_dir, i, track, vcd, ground_truth)

def get_projects():
    projects = {}
    def checker(proj, **args):
        projects[proj] = args
    add_checker(checker, track=True)
    return projects
