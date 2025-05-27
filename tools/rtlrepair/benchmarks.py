# Copyright 2022-2023 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import sys
from pathlib import Path
from dataclasses import dataclass

_src_dir = Path(__file__).parent.resolve()
_root_dir = _src_dir.parent.parent
_utils_dir = _root_dir / "resources" / "utils"
sys.path.append(str(_utils_dir))

from env import get_proj_name

@dataclass
class Bug:
    name: str
    files: list

@dataclass
class Design:
    top_file: Path
    top_module: str
    directory: Path
    sources: list[Path]

@dataclass
class Project:
    name: str
    design: Design
    bugs: list[Bug]

@dataclass
class SimResult:
    no_output: bool = False
    failed_at: int = -1
    fail_msg: str = ""
    cycles: int = 0

    @property
    def is_success(self): return self.failed_at == -1 and not self.no_output

def load_project(proj: Path, bugs: dict, top_module: str, top_file: Path, sources: list[Path]) -> Project:
    bugs = [Bug(name=name, files=bugs[name]) for name in bugs]
    sources = [proj / i for i in sources]
    design = Design(top_module=top_module, top_file=top_file, directory=proj, sources=sources)
    return Project(name=get_proj_name(proj), design=design, bugs=bugs)

def check_against_oracle(oracle_filename: Path, output_filename: Path) -> SimResult:
    with open(oracle_filename) as f:
        oracle = f.readlines()
    
    with open(output_filename) as f:
        output = f.readlines()
    
    cycles = len(oracle) - 1
    nr_lines = len(output) - 1
    header = oracle[0].split(",")[1:] 
    if oracle[0] != output[0]:
        raise Exception(f"Header mismatch between files: '{oracle_filename}' and '{output_filename}'")

    for cycle_index in range(1, len(oracle)):
        if cycle_index > nr_lines:
            msg = f"Output stopped at {cycle_index - 1}. Expected {cycles - nr_lines} more lines."
            return SimResult(failed_at=cycle_index - 1, fail_msg=msg, cycles=cycles)

        oracle_fields = [field.strip() for field in oracle[cycle_index].split(",")[1:]]
        output_fields = [field.strip() for field in output[cycle_index].split(",")[1:]]
        
        if len(oracle_fields) != len(output_fields):
            raise Exception(f"Mismatch in output cycles between files: '{oracle_filename}' and '{output_filename}'")
        
        msg = []
        for field_index in range(len(oracle_fields)):
            oracle_signal = oracle_fields[field_index]
            output_signal = output_fields[field_index]
            
            if len(oracle_signal) != len(output_signal):
                raise Exception(f'detect invalid output signal of {oracle_fields[field_index]}')

            for bit_index in range(len(oracle_signal)):
                oracle_bit = oracle_signal[bit_index]
                output_bit = output_signal[bit_index]
                ignore = oracle_bit.lower() in ('x', 'z')
                if oracle_bit != output_bit and not ignore:
                    msg.append(f'{header[field_index].strip()}@{cycle_index - 1}: {output_signal} != {oracle_signal} (expected)')
                    break
        if msg:
            return SimResult(failed_at=cycle_index - 1, fail_msg='\n'.join(msg), cycles=cycles)
    
    return SimResult(cycles=cycles)
