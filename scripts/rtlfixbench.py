import sys
import argparse
import subprocess
from verbose import *
from defaults import *

def call_script(script, args):
    script_dir = os.path.dirname(script)
    if script_dir == '':
        script_dir = '.'
    
    result = subprocess.run(
        [sys.executable, script] + args,
        cwd=script_dir,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Script exited with return code {result.returncode}", file=sys.stderr)

def evaluate(tool, args):
    script = os.path.join(PATH_TOOLS, tool, CMD[tool])
    call_script(script, args)

def main():
    parser = argparse.ArgumentParser(description='RTL Bug Fixing Benchmark Suite.')
    parser.add_argument('-t', '--type', type=str, help='Specify the name of the RTL bug fixing tool under evaluation.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--basic', action='store_true', help='Run with handcrafted benchmarks designed for testing specific RTL fixes.')
    group.add_argument('--extend', action='store_true', help='Run with synthetic benchmarks designed to evaluate general RTL repair capabilities.')
    args = parser.parse_args()
    tool = args.type if args.type else TOOL_DEFAULT
    tool_args = []
    if args.basic:
        info('Using handcrafted benchmarks.')
        tool_args.append('--basic')
    elif args.extend:
        info('Using synthetic benchmarks.')
        tool_args.append('--extend')
    if tool not in TOOLS:
        err(f'The tool "{tool}" is not supported. Please choose from the following supported tools: {", ".join(TOOLS)}.')
    info(f'RTL bug fixing tool {tool}')
    evaluate(tool, tool_args)

if __name__ == "__main__":
    main()