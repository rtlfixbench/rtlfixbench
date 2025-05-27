# Copyright 2022-2024 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import os
import sys
import math
import copy
import time
import json
import signal
import shutil
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass
from benchmarks import Project, load_project
from result import create_buggy_and_original_diff, write_result
from synthesizer import SynthStats, Synthesizer, SynthOptions
from utils import parse_verilog, serialize, Status
from analysis import analyze_ast, AnalysisResults
from preprocess import preprocess
from repair import do_repair
from templates import *

_root_dir = Path(__file__).parent.parent.parent
_resources_dir = _root_dir / "resources"
_utils_dir = _resources_dir / "utils"
sys.path.append(str(_utils_dir))

_settings_file = _resources_dir / "configs" / "rtlrepair" / "settings.json"
with open(_settings_file, 'r') as f:
    config = json.load(f)

import env
from checker import add_checker

_tool_name = "rtl-repair"
_supported_solvers = {'z3', 'cvc4', 'yices2', 'boolector', 'bitwuzla', 'optimathsat', 'btormc'}
_available_templates = {
    'replace_literals': replace_literals,
    'assign_const': assign_const,
    'add_inversions': add_inversions,
    'replace_variables': replace_variables,
    'conditional_overwrite': conditional_overwrite,
    'add_guard': add_guard,
}
_default_templates = ['replace_literals', 'assign_const', 'add_inversions', 'replace_variables', 'conditional_overwrite', 'add_guard']

@dataclass
class Options:
    show_ast: bool
    synth: SynthOptions
    templates: list
    skip_preprocessing: bool
    single_solution: bool=False # restrict the number of solutions to one
    timeout: float=None # set timeout after which rtl-repair terminates
    run_all_templates: bool=True
    per_template_timeout: float=None
    basic: bool=True
    extend: bool=True

@dataclass
class Config:
    project: Project
    bug_name: str
    opts: Options

_default_synth_opts = SynthOptions(solver=config.get("solver", "yices2"), init=config.get("init", "any"), incremental=config.get("incremental", False), verbose=config.get("verbose", False))
_default_opts = Options(show_ast=False, synth=_default_synth_opts, templates=[_available_templates[i] for i in _default_templates], skip_preprocessing=False)

statistics = {}

def parse_args() -> Config:
    available_template_names = ",".join(_available_templates.keys())
    default_template_names = ",".join(_default_templates)
    parser = argparse.ArgumentParser(description='Repair Verilog file')
    parser.add_argument('--project', help='Working directory of project')
    parser.add_argument('--bug', help='bug name')
    parser.add_argument('--solver', dest='solver', help='specify the SMT solver to use', default="yices2")
    parser.add_argument('--init', dest='init', help='how should states be initialized? [any], zero or random',
                        default="any")
    parser.add_argument('--show-ast', dest='show_ast', help='show the ast before applying any transformation',
                        action='store_true')
    parser.add_argument('--incremental', dest='incremental', help='use incremental solver',
                        action='store_true')
    parser.add_argument('--timeout', help='Max time to attempt a repair in seconds')
    
    parser.add_argument('--templates', default=default_template_names,
                        help=f'Specify repair templates to use. ({available_template_names})')
    parser.add_argument('--skip-preprocessing', help='skip the preprocessing step', action='store_true')
    parser.add_argument('--verbose-synthesizer',
                        help='collect verbose output from the synthesizer which will be available in synth.txt',
                        action='store_true')
    parser.add_argument('--run-all-templates',
                        help='Instead of an early exit when a repair is found, this tries to run all templates available.',
                        action='store_true')
    parser.add_argument('--template-timeout', help='Applies a timeout to each individual template.')
    parser.add_argument('--past-k-step-size', help='Step size used in the incremental repair synthesizer.')
    parser.add_argument('--old-synthesizer', help='use the old synthesizer written in Scala',
                        action='store_true')
    
    args = parser.parse_args()

    project = None
    if args.project:
        proj = Path(args.project)
        if not proj.exists():
            raise FileNotFoundError(f'Project directory "{proj}" does not exist. Please provide a valid path.')

        if not args.bug:
            raise ValueError('The bug name is required. Use the "--bug" argument to specify it.')
        
        settings = env.get_settings(proj, absolute_path=True)
        sources = settings['sources']
        project = load_project(proj, settings['bugs'], settings['top_module'], Path(settings['top_file']), sources)
    
    # options
    assert args.solver in _supported_solvers, f"unknown solver {args.solver}, try: {_supported_solvers}"
    assert args.init in {'any', 'zero', 'random'}
    synth_opts = SynthOptions(solver=args.solver, init=args.init, incremental=args.incremental,
                              verbose=args.verbose_synthesizer, past_k_step_size=args.past_k_step_size)
    timeout = None if args.timeout is None else float(args.timeout)
    per_template_timeout = None if args.template_timeout is None else float(args.template_timeout)
    templates = []
    for t in args.templates.split(','):
        t = t.strip()
        assert t in _available_templates, f"Unknown template `{t}`. Try: {available_template_names}"
        templates.append(_available_templates[t])
    opts = Options(show_ast=args.show_ast, synth=synth_opts, timeout=timeout, templates=templates,
                   skip_preprocessing=args.skip_preprocessing, run_all_templates=args.run_all_templates,
                   per_template_timeout=per_template_timeout)

    return Config(project, args.bug, opts)

def find_solver_version(solver: str) -> str:
    arg = ["--version"]
    if solver == "btormc":
        arg += ["-h"] # without this btormc does not terminate
    if solver == 'yices2':
        solver = 'yices-smt2'
    if solver == 'optimathsat':
        arg = ["-version"]
    r = subprocess.run([solver] + arg, check=True, stdout=subprocess.PIPE)
    return r.stdout.decode('utf-8').splitlines()[0].strip()

# return this if the synthesizer did not run or did not run properly (i.e. crashed)
NoSynthStat = SynthStats(solver_time_ns=0, past_k=-1, future_k=-1)

def try_template(proj: Path, bug_name: str, opts: Options, ast, prefix: str, template, statistics: dict, analysis: AnalysisResults, solution_count: int) -> (Status, list):
    if opts.per_template_timeout is not None:
        signal.alarm(int(math.ceil(opts.per_template_timeout)))

    start_time = time.monotonic()
    # create a directory for this particular template
    template_name = template.__name__
    results_dir = env.get_results_dir(proj)
    template_dir = results_dir / (prefix + template_name)
    if template_dir.exists():
        shutil.rmtree(template_dir)
    os.mkdir(template_dir)

    # apply template any try to synthesize a solution
    blockified = template(ast, analysis)

    # try to find a change that fixes the design
    synth_start_time = time.monotonic()
    synth = Synthesizer()

    try:
        status, assignments, synth_stats = synth.run(proj, template_dir, opts.synth, ast, bug_name)
    except TimeoutError as e:
        # is this error for us?
        if opts.per_template_timeout is not None:
            status, assignments, synth_stats = Status.Timeout, [], NoSynthStat
        else:
            assert opts.timeout is not None # global timeout instead!
            raise e # dispatch to top
    except subprocess.CalledProcessError:
        # something crashed, so we cannot repair this bug
        status, assignments, synth_stats = Status.CannotRepair, [], NoSynthStat

    synth_time = time.monotonic() - synth_start_time
    template_time = time.monotonic() - start_time
    solver_time = synth_stats.solver_time_ns / 1000.0 / 1000.0 / 1000.0

    solutions = []
    if status == Status.Success:
        # pick first solution if only one was requested
        if opts.single_solution:
            assignments = assignments[:1]
        for ii, assignment in enumerate(assignments):
            # execute synthesized repair
            changes = do_repair(ast, assignment, blockified)
            prefix = f"{bug_name}_repaired_{ii+solution_count}"
            with open(template_dir / f"{prefix}.changes.txt", "w") as f:
                f.write(f"{template_name}\n")
                f.write(f"{len(changes)}\n")
                f.write('\n'.join(f"{line}: {a} -> {b}" for line, a, b in changes))
                f.write('\n')
            results_dir = env.get_results_dir(proj)
            repaired_filename = results_dir / f"{prefix}.v"
            with open(repaired_filename, "w") as f:
                f.write(serialize(ast))
            # meta info for the solution
            meta = {'changes': len(changes), 'template': template_name, 'synth_time': synth_time,
                    'template_time': template_time,
                    'solver_time': solver_time,
                    'past_k': synth_stats.past_k, 'future_k': synth_stats.future_k,
                    }
            solutions.append((repaired_filename, meta))

    statistics[template_name] = {
        'prefix': prefix, 'solver_time': solver_time,
        'status': status.name, 'synth_time': synth_time, 'template_time': template_time, 'solutions': len(solutions)
    }

    return status, solutions

def try_templates_in_sequence(proj: Path, bug_name: str, opts: Options, ast, statistics: dict, analysis: AnalysisResults) -> (Status, list, dict):
    all_solutions = []
    # instantiate repair templates, one after another
    # note: when  we tried to combine replace_literals and add_inversion, tests started taking a long time
    for ii, template in enumerate(opts.templates):
        prefix = f"{ii + 1}_"
        # we need to deep copy the ast since the template is going to modify it in place!
        ast_copy = copy.deepcopy(ast)
        status, solutions = try_template(proj, bug_name, opts, ast, prefix, template, statistics, analysis, len(all_solutions))

        # early exit if there is nothing to do or if we found a solution and aren't instructed to run all templates
        if status == Status.NoRepair or (not opts.run_all_templates and status == Status.Success):
            if status == Status.Success:
                # keep going if the current solution is pretty large
                min_changes = min(s[1]['changes'] for s in solutions)
                if min_changes <= 3:
                    return status, solutions
                else:
                    all_solutions += solutions
            else:
                return status, solutions
        else:
            all_solutions += solutions
        ast = ast_copy

    status = Status.CannotRepair if len(all_solutions) == 0 else Status.Success
    return status, all_solutions

def repair(proj: Path, bug_name: str, bug_file: Path, opts: Options):
    preprocess_start_time = time.monotonic()
    if opts.skip_preprocessing:
        filename = bug_file
        preprocess_change_count = 0
    else:
        # preprocess the input file to fix some obvious problems that violate coding styles and basic lint rules
        filename, preprocess_change_count = preprocess(proj, bug_name, bug_file)
    statistics['preprocess'] = {'time': time.monotonic() - preprocess_start_time, 'changes': preprocess_change_count}

    ast = parse_verilog(filename)
    if opts.show_ast:
        ast.show()

    # analyze expressions types and dependencies
    analysis = analyze_ast(ast)

    status, solutions = try_templates_in_sequence(proj, bug_name, opts, ast, statistics, analysis)

    # create repaired file in the case where the synthesizer had to make no changes
    if status == Status.NoRepair:
        # make sure we copy over the repaired file
        results_dir = env.get_results_dir(proj)
        repaired_dst = results_dir / f"{bug_name}_repaired.v"
        shutil.copy(src=filename, dst=repaired_dst)
        # if the preprocessor made a change and that resulted in not needing any change to fix the benchmark
        # then we successfully repaired the design with the preprocessor
        if preprocess_change_count > 0:
            solutions = [(repaired_dst, {'template': "preprocess", 'changes': preprocess_change_count})]
            status = Status.Success
        # otherwise the circuit was already correct
        else:
            solutions = [(repaired_dst, {'template': "", 'changes': 0})]

    return status, solutions

def timeout_handler(signum, frame):
    print("timeout")
    raise TimeoutError()

def check_verilator_version(opts: Options):
    """ Makes sure that the major version of verilator is 4 if we are using preprocessing.
        This is important because verilator 5 has significant changes to what it reports as warnings in lint mode.
    """
    if opts.skip_preprocessing: return
    version_out = subprocess.run(["verilator", "-version"], stdout=subprocess.PIPE).stdout
    version = version_out.split()[1]
    major_version = int(version.split(b'.')[0])
    assert major_version == 4, f"Unsupported verilator version {version} detected. " \
                               f"Please provide Verilator 4 on your path instead!"

def main():
    config = parse_args()
    project = config.project
    bug_name = config.bug_name
    assert not (config.opts.timeout and config.opts.per_template_timeout), \
        "timeout and template-timeout options are not compatible!"
    if project:
        proj = project.design.directory
        if bug_name == None:
            bugs = [bug_name]
        else:
            bugs = project.bugs
        proj = project.design.directory
        for i in bugs:
            bug_list = bugs[i]
            file_list = env.get_file_list(proj, bug_list, project.design.sources)
            rtlrepair_checker(proj, i, file_list, opts=config.opts)
    else:
        add_checker(checker=rtlrepair_checker)
    
def rtlrepair_checker(proj: Path, bug_name: str, file_list: list, opts=_default_opts):
    check_verilator_version(opts)
    signal.signal(signal.SIGALRM, timeout_handler)
    if opts.timeout:
        signal.alarm(int(math.ceil(opts.timeout)))
    bug_file = file_list[0]
    create_buggy_and_original_diff(proj, bug_name, bug_file)
    start_time = time.monotonic()
    try:
        status, solutions = repair(proj, bug_name, file_list[0], opts)
    except TimeoutError:
        status, solutions = Status.Timeout, []
    delta_time = time.monotonic() - start_time
    statistics['total_time'] = delta_time
    success = status in {Status.Success, Status.NoRepair}
    write_result(proj, bug_name, success,
                 repaired=solutions, seconds=delta_time, tool_name=_tool_name,
                 custom={'status': status.value, 'statistics': statistics})

if __name__ == '__main__':
    main()
