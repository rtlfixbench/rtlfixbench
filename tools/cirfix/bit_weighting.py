import os
import sys
import json
import argparse
from cirfix import DEBUG, WEIGHTS_FILE
from pyverilog.vparser.parser import parse
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator

class OutputAnalyzer(ASTCodeGenerator):
    def __init__(self):
        self.output_bits_length = dict()
        self.assignment_counts = dict() # each variable key has a value (<special_assign>,<assignment_count>)

    def visit(self, ast, repeated=1):
        if ast.__class__.__name__ in ("Output", "Inout"):
            if ast.width and ast.width.msb.__class__.__name__ == "IntConst": # TODO: fix this, e.g. X = [Y-1:0]
                self.output_bits_length[ast.name] = int(ast.width.msb.value) - int(ast.width.lsb.value) + 1
            else:
                self.output_bits_length[ast.name] = 1
            self.assignment_counts[ast.name] = (False, 0)

        #TODO: This weighting assigns each bit in a wire uniform widths. Change it to assign individual
        #      bits their own weights. e.g. if op[7] gets more assignments than op[1], the former should
        #      have a higher weight than the latter.
        if ast.__class__.__name__ in ("NonblockingSubstitution", "BlockingSubstitution", "Assign") and ast.right.var:
            if ast.left.var.__class__.__name__ == "LConcat":
                for tmp in ast.left.var.list:
                    if tmp.name in self.assignment_counts:
                        self.assignment_counts[tmp.name] = (ast.__class__.__name__ == "Assign", self.assignment_counts[tmp.name][1] + repeated * 1)
            elif ast.left.var.__class__.__name__ == "Identifier":
                var_name = ast.left.var.name
                if var_name in self.assignment_counts:
                    self.assignment_counts[var_name] = (ast.__class__.__name__ == "Assign", self.assignment_counts[var_name][1] + repeated * 1)
            elif ast.left.var.__class__.__name__ == "Pointer":
                var_name = ast.left.var.var.name
                if var_name in self.assignment_counts:
                    self.assignment_counts[var_name] = (ast.__class__.__name__ == "Assign", self.assignment_counts[var_name][1] + repeated * 1)

        for c in ast.children():
            if c.__class__.__name__ == "ForStatement":
                self.visit(c,self.get_repeated_for(c))
            elif repeated != 1:
                self.visit(c,repeated)
            else:
                self.visit(c)

    #TODO: Only supports the format (i=?; i{<,<=}}x; i=i{op}y). Update if needed.
    #      Also does not support nested for loops. It is only an approximation, does not
    #      need very accurate estimations.
    def get_repeated_for(self, ast):
        ret = 1
        if ast.pre.right.var:
            begin = int(ast.pre.right.var.value)
        if ast.cond.__class__.__name__ == "LessThan":
            end = int(ast.cond.right.value)
        elif ast.cond.__class__.__name__ == "LessEq":
            end = int(ast.cond.right.value) + 1
        if ast.post.right:
            step = int(ast.post.right.var.right.value)
        try:
            ret = (end - begin) // step
        except UnboundLocalError:
            print("Warning: For loop parsing not supported for this Verilog program. Defaulting to a value of 1.")
        return ret

    def get_weigts(self):
        total = 0
        weights = dict()
        inverted_weights = dict()
        for var in self.assignment_counts:
            if self.assignment_counts[var][1] != 0:
                total += self.assignment_counts[var][1]
            if self.assignment_counts[var][0]:
                self.assignment_counts[var] = (True, self.assignment_counts[var][0] * 2)
        for var in self.assignment_counts:
            if self.assignment_counts[var][1] != 0:
                inverted_weights[var] = 1 / (self.assignment_counts[var][1] / total)
        inverted_total = sum(inverted_weights.values())
        for var in inverted_weights:
            weights[var] = [inverted_weights[var] / (inverted_total * self.output_bits_length[var])] * self.output_bits_length[var]
        return weights

def main():
    parser = argparse.ArgumentParser(
        description="Generates bit-level weighting based on assignment frequency in Verilog signal analysis."
    )
    parser.add_argument("prog", help="Path to the Verilog program")
    parser.add_argument("-o", "--output", help="Specify the path of the output file.", type=str, default=None)
    args = parser.parse_args()

    if not os.path.exists(args.prog):
        print(f"Error: File {args.prog} not found")
        sys.exit(1)

    ast, _ = parse([args.prog])
    if DEBUG:
        ast.show()
    
    outputanalyzer = OutputAnalyzer()
    outputanalyzer.visit(ast)
    weights = outputanalyzer.get_weigts()
    outfile_name = args.output if args.output else WEIGHTS_FILE
    with open(outfile_name, "w") as outfile:
        json.dump(weights, outfile, indent=4)
    
    if DEBUG:
        print(outputanalyzer.output_bits_length)
        print(outputanalyzer.assignment_counts)

if __name__ == "__main__":
    main()
