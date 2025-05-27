# Copyright 2022 The Regents of the University of California
# released under BSD 3-Clause License
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import sys
from pathlib import Path
import pyverilog.vparser.ast as vast

_rtlrepair_dir = Path(__file__).parent.parent
sys.path.append(str(_rtlrepair_dir))

from utils import Namespace
from repair import RepairTemplate
from analysis import AnalysisResults, VarInfo

def replace_literals(ast: vast.Source, analysis: AnalysisResults):
    namespace = Namespace(ast)
    repl = LiteralReplacer(analysis.vars, analysis.widths)
    repl.apply(namespace, ast)

class LiteralReplacer(RepairTemplate):
    def __init__(self, vars: dict[str, VarInfo], widths: dict[vast.Node, int]):
        super().__init__(name="literal")
        self.vars = vars
        self.widths = widths
        self.in_proc = False

    def visit_Always(self, node: vast.Always):
        self.in_proc = True
        node = self.generic_visit(node)
        self.in_proc = False
        return node

    def visit_IfStatement(self, node: vast.IfStatement):
        if self.in_proc:
            node.cond = self.visit(node.cond)
        node.true_statement = self.visit(node.true_statement)
        node.false_statement = self.visit(node.false_statement)
        return node

    def visit_Identifier(self, node: vast.Identifier):
        var = self.vars[node.name]
        if var.is_const:
            # we treat parameters like constants
            new_const = vast.Identifier(self.make_synth_var(var.width))
            choice = self.make_change(new_const, node)
            return choice
        else:
            return node

    def visit_IntConst(self, node: vast.IntConst):
        bits = self.widths[node]
        new_const = vast.Identifier(self.make_synth_var(bits))
        choice = self.make_change(new_const, node)
        return choice
