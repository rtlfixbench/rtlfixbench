# Copyright 2022 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import sys
import json
import subprocess
import pyverilog.vparser.ast as vast
from utils import serialize, Status, status_name_to_enum
from dataclasses import dataclass
from yosys import to_btor
from pathlib import Path

_bin_rel = Path("target") / "release" / "synth"
_synthesizer_dir = Path(__file__).parent / "synth"
_bin = _synthesizer_dir / _bin_rel

_root_dir = Path(__file__).parent.parent.parent
_utils_dir = _root_dir / "resources" / "utils"
sys.path.append(str(_utils_dir))

import env

@dataclass
class SynthOptions:
    solver: str
    init: str
    incremental: bool
    verbose: bool
    past_k_step_size: int = None

@dataclass
class SynthStats:
    solver_time_ns: int
    past_k: int
    future_k: int

def _check_bin():
    assert _bin.exists(), f"Failed to find synth binary, did you run cargo build --release?\n{_bin}"

def _run_synthesizer(working_dir: Path, design: Path, testbench: Path, opts: SynthOptions) -> dict:
    assert design.exists(), f"{design=} does not exist"
    assert testbench.exists(), f"{testbench=} does not exist"
    _check_bin()
    args = ["--design", str(design), "--testbench", str(testbench), "--solver", opts.solver, "--init", opts.init]
    if opts.incremental:
        args += ["--incremental"]
    if opts.verbose:
        args += ["--verbose"]
    if opts.past_k_step_size:
        args += ["--past-k-step-size", str(opts.past_k_step_size)]
    args += ["--max-incorrect-solutions-per-window-size", str(4)]
    cmd = [_bin]
    cmd += args
    cmd_str = ' '.join(str(p) for p in cmd)  # for debugging

    # write command to file in order to be able to reproduce the failed synthesis command
    with open(working_dir / "run_synth.sh", 'w') as ff:
        print("#!/usr/bin/env bash", file=ff)
        print(cmd_str, file=ff)

    r = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)
    output = r.stdout.decode('utf-8')
    # command write output to file for debugging
    with open(working_dir / "synth.txt", 'w') as ff:
        print(cmd_str, file=ff)
        ff.write(output)
    try:
        # the JSON output follows the needle
        needle = "== RESULT ==\n"
        return json.loads(output.split(needle)[-1])
    except json.JSONDecodeError as e:
        print("Failed to parse synthesizer output as JSON:")
        print(r.stdout)
        raise e

class Synthesizer:
    """ generates assignments to synthesis variables which fix the design according to a provided testbench """
    def __init__(self):
        pass

    def run(self, proj: Path, working_dir: Path, opts: SynthOptions, instrumented_ast: vast.Source, bug_name: str) -> (Status, list, SynthStats):
        # save instrumented AST to disk so that we can call yosys
        synth_filename = working_dir / f"{bug_name}_instrumented.v"
        with open(synth_filename, "w") as f:
            f.write(serialize(instrumented_ast))

        # convert file and run synthesizer
        settings = env.get_settings(proj)
        testbench_file = env.get_testbench_spec(proj)
        additional_sources = env.get_other_sources(proj, bug_name)
        btor_filename = to_btor(working_dir, working_dir / (synth_filename.stem + ".btor"),
                                [synth_filename] + additional_sources, settings['top_module'],
                                script_out=working_dir / "to_btor.sh")
        result = _run_synthesizer(working_dir, btor_filename, testbench_file, opts)

        status = status_name_to_enum[result['status']]
        solutions = []
        if status == Status.Success:
            solutions = [s['assignment'] for s in result['solutions']]

        stats = SynthStats(solver_time_ns=result['solver-time'], past_k=result['past-k'], future_k=result['future-k'])
        return status, solutions, stats
