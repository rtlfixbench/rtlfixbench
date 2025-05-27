# Copyright 2022-2023 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import sys
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from pyverilog.vparser.parser import parse
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator

_root_dir = Path(__file__).parent.parent.parent
_utils_dir = _root_dir / "resources" / "utils"
sys.path.append(str(_utils_dir))

import env

@dataclass
class Repair:
    filename: Path
    diff: Path = None
    manual: Path = None # manually ported patch
    meta: dict = field(default_factory=dict)

@dataclass
class Result:
    name: str
    tool: str
    project_name: str
    bug_name: str
    success: bool
    seconds: float
    buggy: Path = None
    original: Path = None
    repairs: list[Repair] = field(default_factory=list)
    custom: dict = field(default_factory=dict)

def collect_repair_meta(dd: dict) -> dict:
    return {k: v for k, v in dd.items() if k not in {'name', 'diff', 'manual'}}

def write_result(proj: Path, bug_name: str, success: bool, repaired: list, seconds: float, tool_name: str, custom: dict=None):
    """ Writes the results to the working directory. """
    proj_name = env.get_proj_name(proj)
    results_dir = env.get_results_dir(proj)
    settings = env.get_settings(proj)
    bugs_dir = env.get_bugs_dir(proj)
    bug = settings['bugs'][bug_name][0]
   
    with open(results_dir / "result.toml", 'w') as ff:
        print("[result]", file=ff)
        print(f'tool="{tool_name}"', file=ff)
        print(f'name="{proj_name}"', file=ff)
        print(f'bug="{bug_name}"', file=ff)
        print(f'success={str(success).lower()}', file=ff)
        print(f'seconds={seconds}', file=ff)

        # print file names relative to the working dir
        def print_filename(key: str, filename: Path):
            print(f'{key}="{filename.relative_to(proj)}"', file=ff)

        # these files should have been created by the `create_buggy_and_original_diff` function
        original = proj / bug['original']
        buggy = bugs_dir / bug['buggy']
        if buggy.exists():
            print_filename("buggy", buggy)
        if original and original.exists():
            print_filename("original", original)

        # do we have a repaired file?
        if success: assert len(repaired) > 0, f"Successful, but a repair is missing!"

        for rep_info in repaired:
            print("\n[[repairs]]", file=ff)
            if isinstance(rep_info, Path):
                rep_file, meta_data = rep_info, None
            else:
                rep_file, meta_data = rep_info
            print_filename("name", rep_file)
            if buggy.exists():
                repair_diff = results_dir / f"{rep_file.stem}_diff.txt" #############
                do_diff(buggy, rep_file, repair_diff)
                print_filename("diff", repair_diff)
            if meta_data:
                print("# tool specific meta-data", file=ff)
                _print_custom_key_values(meta_data, ff)

        if custom is not None and len(custom) > 0:
            print("\n[custom]", file=ff)
            _print_custom_key_values(custom, ff)

def _print_custom_key_values(cc: dict, ff):
    for kk, vv in cc.items():
        print(f'{kk}={_to_toml_str(vv)}', file=ff)

def _to_toml_str(value) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, float):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_to_toml_str(ii) for ii in value) + "]"
    # turn into json string by default
    return f'"""{json.dumps(value)}"""'

def create_buggy_and_original_diff(proj: Path, bug_name: str, bug_file: Path):
    """
        - copies the buggy file to the working directory with the Verilog reformatted with PyVerilog
        - if the original file (i.e. the ground truth) is available, that is copies as well with PyVerilog formatting,
          and we also create a bug diff between the two files
    """
    results_dir = env.get_results_dir(proj)
    buggy_copy = results_dir / f"{bug_name}.ast"
    parse_and_serialize_to(bug_file, buggy_copy)

_codegen = ASTCodeGenerator()

def parse_and_serialize_to(src: Path, dst: Path, include=None, define=None):
    """ Makes a "copy" of the source file by parsing it with PyVerilog and serializing the AST to the destination file """
    ast, _ = parse([src], preprocess_include=include, preprocess_define=define)
    with open(dst, 'w') as ff:
        ff.write(_codegen.visit(ast))

def do_diff(file_a: Path, file_b: Path, output_file: Path):
    """ Calls the `diff` tool to compare two files and writes the result to a third file. """
    cmd = "diff"
    r = subprocess.run(["which", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode == 0:
        with open(output_file, 'wb') as f:
            subprocess.run(["diff", str(file_a.resolve()), str(file_b.resolve())], stdout=f)
