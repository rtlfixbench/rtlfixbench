import os
import sys
import copy
import time
import json
import random
import inspect
import fitness
import argparse
from pathlib import Path
from datetime import datetime
import pyverilog.vparser.ast as vast
from pyverilog.vparser.plyparser import ParseError
from pyverilog.vparser.parser import parse, NodeNumbering
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator

AST_CLASSES = []
for name, obj in inspect.getmembers(vast):
    if inspect.isclass(obj):
        AST_CLASSES.append(obj)

REPLACE_TARGETS = {} # dict from class to list of classes that are okay to substituite for the original class
for i in range(len(AST_CLASSES)):
    REPLACE_TARGETS[AST_CLASSES[i]] = []
    REPLACE_TARGETS[AST_CLASSES[i]].append(AST_CLASSES[i]) # can always replace with a node of the same type
    for j in range(len(AST_CLASSES)):
        # get the immediate parent classes of both classes, and if the parent if not Node, the two classes can be swapped
        if i != j and inspect.getmro(AST_CLASSES[i])[1] == inspect.getmro(AST_CLASSES[j])[1] and inspect.getmro(AST_CLASSES[j])[1] != vast.Node:
            REPLACE_TARGETS[AST_CLASSES[i]].append(AST_CLASSES[j])

"""
Valid targets for the delete and insert operators.
"""
DELETE_TARGETS = ["IfStatement", "NonblockingSubstitution", "BlockingSubstitution", "ForStatement", "Always", "Case", "CaseStatement", "DelayStatement", "Localparam", "Assign", "Block"]
INSERT_TARGETS = ["IfStatement", "NonblockingSubstitution", "BlockingSubstitution", "ForStatement", "Always", "Case", "CaseStatement", "DelayStatement", "Localparam", "Assign"]
TEMPLATE_MUTATIONS = { "increment_by_one": ("Identifier", "Plus"), "decrement_by_one": ("Identifier", "Minus"), 
                        "negate_equality": ("Eq", "NotEq"), "negate_inequality": ("NotEq", "Eq"), "negate_ulnot": ("Ulnot", "Ulnot"),
                        "sens_to_negedge": ("Sens", "Sens"), "sens_to_posedge": ("Sens", "Sens"), "sens_to_level": ("Sens", "Sens"), "sens_to_all": ("Sens", "Sens"),
                        "blocking_to_nonblocking": ("BlockingSubstitution", "NonblockingSubstitution"), "nonblocking_to_blocking": ("NonblockingSubstitution", "BlockingSubstitution")}
                        # "sll_to_sla": ("Sll", "Sla"), "sla_to_sll": ("Sla", "Sll"), 
                        # "srl_to_sra": ("Srl", "Sra"), "sra_to_srl": ("Sra", "Srl")}
                        # TODO: stmt to stmt in a block?
                        # TODO: empty if then somewhere? with like a random identifier for cond?
                        # TODO: use only registers for inc and dec by one?

LOG = False
INFO = True
FAULT_LOC = True
CONTROL_FLOW = True
LIMIT_TRANSITIVE_DEPENDENCY_SET = False

ORACLE = None
OUTPUT = None
SRC_FILE = None
SETTINGS = None
PROJ_DIR = None
CANDIDATE = None
MINIMIZED = None
TEST_BENCH = None

GENS = 5
POPSIZE = 200
RESTARTS = 1
DEPENDENCY_SET_MAX = 5

DELETION_RATE = 1 / 3
MUTATION_RATE = 1 / 2
INSERTION_RATE = 1 / 3
CROSSOVER_RATE = 1 / 2
REPLACEMENT_RATE = 1 / 3

SEED = "None"
FITNESS_MODE = "outputwires"

FITNESS_EVAL_TIMES = []
GENOME_FITNESS_CACHE = {}

_cirfix_dir = Path(__file__).parent.resolve()
_root_dir = _cirfix_dir.parent.parent
_resources_dir = _root_dir / "resources"
_settings_file = _resources_dir / "configs" / "cirfix" / "settings.json"
_utils_dir = _resources_dir / "utils"

DEBUG = fitness.DEBUG
WEIGHTS_FILE = fitness.WEIGHTS_FILE

SHOW_FITNESS = False
SHOW_FAILURES = False
SHOW_EVAL_CANDIDATE = False

sys.path.append(str(_utils_dir))

import env
from env import info
from checker import add_checker

with open(_settings_file, 'r') as f:
    config = json.load(f)

SEED = config.get("seed", SEED)
FITNESS_MODE = config.get("fitness_mode", FITNESS_MODE)
FAULT_LOC = bool(config.get("fault_loc", FAULT_LOC))
CONTROL_FLOW = bool(config.get("control_flow", CONTROL_FLOW))
LIMIT_TRANSITIVE_DEPENDENCY_SET = bool(config.get("limit_transitive_dependency_set", LIMIT_TRANSITIVE_DEPENDENCY_SET))
GENS = int(config.get("gens", GENS))
POPSIZE = int(config.get("popsize", POPSIZE))
RESTARTS = int(config.get("restarts", RESTARTS))
DEPENDENCY_SET_MAX = int(config.get("dependency_set_max", DEPENDENCY_SET_MAX))
INSERTION_RATE = float(config.get("insertion_rate", INSERTION_RATE))
MUTATION_RATE = float(config.get("mutation_rate", MUTATION_RATE))
CROSSOVER_RATE = float(config.get("crossover_rate", CROSSOVER_RATE))
DELETION_RATE = float(config.get("deletion_rate", DELETION_RATE))
REPLACEMENT_RATE = float(config.get("replacement_rate", REPLACEMENT_RATE))

if DEBUG:
    info(f"Using SEED = {SEED}")
    info(f"Using FITNESS_MODE = {FITNESS_MODE}")
    info(f"Using FAULT_LOC = {int(FAULT_LOC)}")
    info(f"Using CONTROL_FLOW = {int(CONTROL_FLOW)}")
    info(f"Using LIMIT_TRANSITIVE_DEPENDENCY_SET = {int(LIMIT_TRANSITIVE_DEPENDENCY_SET)}")
    info(f"Using GENS = {GENS}")
    info(f"Using POPSIZE = {POPSIZE}")
    info(f"Using RESTARTS = {RESTARTS}")
    info(f"Using DEPENDENCY_SET_MAX = {DEPENDENCY_SET_MAX}")
    info(f"Using INSERTION_RATE = {INSERTION_RATE:.6f}")
    info(f"Using MUTATION_RATE = {MUTATION_RATE:.6f}")
    info(f"Using CROSSOVER_RATE = {CROSSOVER_RATE:.6f}")
    info(f"Using DELETION_RATE = {DELETION_RATE:.6f}")
    info(f"Using REPLACEMENT_RATE = {REPLACEMENT_RATE:.6f}")

if REPLACEMENT_RATE + INSERTION_RATE + DELETION_RATE != 1.0:
    info("Error: The mutation operator rates should add up to 1.")
    exit(1)
elif CROSSOVER_RATE + MUTATION_RATE != 1.0:
    info("Error: The mutation operator and crossover rates should add up to 1.")
    exit(1)
elif FITNESS_MODE not in ["outputwires", "testcases"]:
    info("Error: FITNESS_MODE incorrectly specified. Please check the configuration file.")
    exit(1)
elif FITNESS_MODE == "testcases" and FAULT_LOC == True:
    info("Error: Cannot use fault localization unless output wires are being used for fitness metrics. Turning off fault localization.")
    exit(1)

TIME_NOW = datetime.today().strftime("%Y-%m-%d-%H:%M:%S")
if SEED == "None":
    SEED = "repair_%s" % TIME_NOW

SEED_CTR = 0
def inc_seed():
    global SEED_CTR
    SEED_CTR += 1
    return SEED + str(SEED_CTR)

class MutationOp(ASTCodeGenerator):
    def __init__(self, popsize, fault_loc, control_flow):
        self.numbering = NodeNumbering()
        self.popsize = popsize
        self.fault_loc = fault_loc
        self.control_flow = control_flow
        self.fault_loc_set = set()
        self.new_vars_in_fault_loc = dict()
        self.wires_brought_in = dict()
        self.implicated_lines = set()
        self.tmp_node = None 
        self.deletable_nodes = []
        self.insertable_nodes = []
        self.replaceable_nodes = []
        self.node_class_to_replace = None
        self.nodes_by_class = []
        self.stmt_nodes = []
        self.max_node_id = -1

    """ 
    Replaces the node corresponding to old_node_id with new_node.
    """
    def replace_with_node(self, ast, old_node_id, new_node):
        attr = vars(ast)
        for key in attr: # loop through all attributes of this AST
            if attr[key].__class__ in AST_CLASSES: # for each attribute that is also an AST
                if attr[key].node_id == old_node_id:
                    attr[key] = copy.deepcopy(new_node)
                    return
            elif attr[key].__class__ in [list, tuple]: # for attributes that are lists or tuples
                for i in range(len(attr[key])): # loop through each AST in that list or tuple
                    tmp = attr[key][i]
                    if tmp.__class__ in AST_CLASSES and tmp.node_id == old_node_id:
                        attr[key][i] = copy.deepcopy(new_node)
                        return

        for c in ast.children():
            if c:
                self.replace_with_node(c, old_node_id, new_node)
    
    """
    Deletes the node with the node_id provided, if such a node exists.
    """
    def delete_node(self, ast, node_id):
        attr = vars(ast)
        for key in attr: # loop through all attributes of this AST
            if attr[key].__class__ in AST_CLASSES: # for each attribute that is also an AST
                if attr[key].node_id == node_id and attr[key].__class__.__name__ in DELETE_TARGETS:
                    attr[key] = None
            elif attr[key].__class__ in [list, tuple]: # for attributes that are lists or tuples
                for i in range(len(attr[key])): # loop through each AST in that list or tuple
                    tmp = attr[key][i]
                    if tmp.__class__ in AST_CLASSES and tmp.node_id == node_id and tmp.__class__.__name__ in DELETE_TARGETS:
                        attr[key][i] = None

        for c in ast.children():
            if c:
                self.delete_node(c, node_id)
    
    """
    Inserts node with node_id after node with after_id.
    """
    def insert_stmt_node(self, ast, node, after_id): 
        if ast.__class__.__name__ == "Block":
            if after_id == ast.node_id:
                ast.statements.insert(0, copy.deepcopy(node))
                return
            else:
                insert_point = -1
                for i in range(len(ast.statements)):
                    stmt = ast.statements[i]
                    if stmt and stmt.node_id == after_id:
                        insert_point = i + 1
                        break
                if insert_point != -1:
                    ast.statements.insert(insert_point, copy.deepcopy(node))
                    return

        for c in ast.children():
            if c:
                self.insert_stmt_node(c, node, after_id)
    
    """
    Gets the node matching the node_id provided, if one exists, by storing it in the temporary node variable.
    Used by the insert and replace operators.
    """    
    def get_node_from_ast(self, ast, node_id):
        if ast.node_id == node_id:
            self.tmp_node = ast
        
        for c in ast.children():
            if c:
                self.get_node_from_ast(c, node_id)

    """ 
    Gets all the line numbers for the code implicated by the FL.
    """    
    def collect_lines_for_fl(self, ast):
        if ast.node_id in self.fault_loc_set:
            self.implicated_lines.add(ast.lineno)
        
        for c in ast.children():
            if c:
                self.collect_lines_for_fl(c)

    """
    Gets a list of all nodes that can be deleted.
    """
    def get_deletable_nodes(self, ast):
        # with fault localization, make sure that any node being deleted is also in DELETE_TARGETS
        if self.fault_loc and len(self.fault_loc_set) > 0:
            if ast.node_id in self.fault_loc_set and ast.__class__.__name__ in DELETE_TARGETS:
                self.deletable_nodes.append(ast.node_id)
        else:
            if ast.__class__.__name__ in DELETE_TARGETS:
                self.deletable_nodes.append(ast.node_id)

        for c in ast.children():
            if c:
                self.get_deletable_nodes(c) 

    """
    Gets a list of all nodes that can be inserted into to a begin ... end block.
    """
    def get_insertable_nodes(self, ast):
        # with fault localization, make sure that any node being used is also in INSERT_TARGETS (to avoid inserting, e.g., overflow+1 into a block statement)
        if self.fault_loc and len(self.fault_loc_set) > 0: 
            if ast.node_id in self.fault_loc_set and ast.__class__.__name__ in INSERT_TARGETS:
                self.insertable_nodes.append(ast.node_id)
        else:        
            if ast.__class__.__name__ in INSERT_TARGETS:
                self.insertable_nodes.append(ast.node_id)

        for c in ast.children():
            if c:
                self.get_insertable_nodes(c) 
    
    """
    Gets the class of the node being replaced in a replace operation. 
    This class is used to find potential sources for the replacement.
    """
    def get_node_to_replace_class(self, ast, node_id):
        if ast.node_id == node_id:
            self.node_class_to_replace = ast.__class__

        for c in ast.children():
            if c:
                self.get_node_to_replace_class(c, node_id)
    
    """
    Gets all nodes that compatible to be replaced with a node of the given class type. 
    These nodes are potential sources for replace operations.
    """
    def get_replaceable_nodes_by_class(self, ast, node_type):
        if ast.__class__ in REPLACE_TARGETS[node_type]:
            self.replaceable_nodes.append(ast.node_id)

        for c in ast.children():
            if c:
                self.get_replaceable_nodes_by_class(c, node_type)
    
    """
    Gets all nodes that are of the given class type. 
    These nodes are used for applying mutation templates.
    """
    # TODO: do this only for fault loc set?
    def get_nodes_by_class(self, ast, node_type):
        if ast.__class__.__name__ == node_type:
            self.nodes_by_class.append(ast.node_id)

        for c in ast.children():
            if c:
                self.get_nodes_by_class(c, node_type)

    """
    Gets all nodes that are found within a begin ... end block. 
    These nodes are potential destinations for insert operations.
    """
    def get_nodes_in_block_stmt(self, ast):
        if ast.__class__.__name__ == "Block":
            if len(ast.statements) == 0: # if empty block, return the node id for the block (so that a node can be inserted into the empty block)
                self.stmt_nodes.append(ast.node_id)
            else:
                for c in ast.statements:
                    if c:
                        self.stmt_nodes.append(c.node_id)
        
        for c in ast.children():
            if c: self.get_nodes_in_block_stmt(c)

    """
    Control dependency analysis of the given program branch.
    """
    def analyze_program_branch(self, ast, cond_list, mismatch_set, uniq_headers):
        if ast:
            if ast.__class__.__name__ == "Identifier" and (ast.name in mismatch_set or ast.name in tuple(self.new_vars_in_fault_loc.values())):
                for cond in cond_list:
                    if cond:
                        self.add_node_and_children_to_fault_loc(cond, mismatch_set, uniq_headers, ast)

            for c in ast.children():
                self.analyze_program_branch(c, cond_list, mismatch_set, uniq_headers)

    """
    Add node and its immediate children to the fault loc set.    
    """
    def add_node_and_children_to_fault_loc(self, ast, mismatch_set, uniq_headers, parent=None):
        self.fault_loc_set.add(ast.node_id)
        if parent and parent.__class__.__name__ == "Identifier" and parent.name not in self.wires_brought_in: self.wires_brought_in[parent.name] = set()
        if ast.__class__.__name__ == "Identifier" and ast.name not in mismatch_set and ast.name not in uniq_headers:
            if not LIMIT_TRANSITIVE_DEPENDENCY_SET or len(self.wires_brought_in[parent.name]) < DEPENDENCY_SET_MAX:
                self.wires_brought_in[parent.name].add(ast.name)
                self.new_vars_in_fault_loc[ast.node_id] = ast.name
        for c in ast.children():
            if c:
                self.fault_loc_set.add(c.node_id) 
                # add all children identifiers to depedency set
                if c.__class__.__name__ == "Identifier" and c.name not in mismatch_set and c.name not in uniq_headers:
                    if not LIMIT_TRANSITIVE_DEPENDENCY_SET or len(self.wires_brought_in[parent.name]) < DEPENDENCY_SET_MAX: 
                        self.wires_brought_in[parent.name].add(c.name)
                        self.new_vars_in_fault_loc[c.node_id] = c.name

    """
    Given a set of output wires that mismatch with the oracle, get a list of node IDs that are potential fault localization targets.
    """
    # TODO: add decl to fault loc targets?
    def get_fault_loc_targets(self, ast, mismatch_set, uniq_headers, parent=None, include_all_subnodes=False):
        # data dependency analysis
        if ast.__class__.__name__ in ["BlockingSubstitution", "NonblockingSubstitution", "Assign"]: # for assignment statements =, <=
            if ast.left and ast.left.__class__.__name__ == "Lvalue" and ast.left.var:
                if ast.left.var.__class__.__name__ == "Identifier" and ast.left.var.name in mismatch_set: # single assignment
                    include_all_subnodes = True
                    parent = ast.left.var
                    if parent and not parent.name in self.wires_brought_in:
                        self.wires_brought_in[parent.name] = set()
                    self.add_node_and_children_to_fault_loc(ast, mismatch_set, uniq_headers, parent)
                elif ast.left.var.__class__.__name__ == "LConcat": # l-concat / multiple assignments
                    for v in ast.left.var.list: 
                        if v.__class__.__name__ == "Identifier" and v.name in mismatch_set:
                            if not v.name in self.wires_brought_in:
                                self.wires_brought_in[v.name] = set()
                            include_all_subnodes = True
                            parent = v
                            self.add_node_and_children_to_fault_loc(ast, mismatch_set, uniq_headers, parent)
        
        # control dependency analysis
        elif self.control_flow and ast.__class__.__name__ == "IfStatement":
            self.analyze_program_branch(ast.true_statement, [ast.cond], mismatch_set, uniq_headers)
            self.analyze_program_branch(ast.false_statement, [ast.cond], mismatch_set, uniq_headers)
        elif self.control_flow and ast.__class__.__name__ == "CaseStatement":
            for c in ast.caselist: 
                if c: 
                    cond_list = [ast.comp]
                    if c.cond: 
                        for tmp_var in c.cond:
                            cond_list.append(tmp_var)
                    self.analyze_program_branch(c.statement, cond_list, mismatch_set, uniq_headers)
        elif self.control_flow and ast.__class__.__name__ == "ForStatement":
            cond_list = []
            if ast.pre:
                cond_list.append(ast.pre)
            if ast.cond:
                cond_list.append(ast.cond)
            if ast.post:
                cond_list.append(ast.post)
            self.analyze_program_branch(ast.statement, cond_list, mismatch_set, uniq_headers)

        if include_all_subnodes: # recurisvely ensure all children of a fault loc target are also included in the fault loc set
            self.fault_loc_set.add(ast.node_id)
            if ast.__class__.__name__ == "Identifier" and ast.name not in mismatch_set and ast.name not in uniq_headers:
                if parent and parent.__class__.__name__ == "Identifier":
                    if not LIMIT_TRANSITIVE_DEPENDENCY_SET or len(self.wires_brought_in[parent.name]) < DEPENDENCY_SET_MAX: 
                        self.wires_brought_in[parent.name].add(ast.name)
                        self.new_vars_in_fault_loc[ast.node_id] = ast.name

        for c in ast.children():
            if c:
                self.get_fault_loc_targets(c, mismatch_set, uniq_headers, parent, include_all_subnodes)
        # TODO: for sdram_controller, control_flow + limit gives smaller fl set than no control_flow + limit. why? is this a bug?
    
    """
    The delete, insert, and replace operators to be called from outside the class.
    Note: node_id, with_id, and after_id would not be none if we are trying to regenerate AST from patch list, and would be none for a random mutation.
    """
    def delete(self, ast, patch_list, node_id=None):
        self.deletable_nodes = [] # reset deletable nodes for the next delete operation, in case previous delete returned early
        if node_id == None:
            self.get_deletable_nodes(ast) # get all nodes that can be deleted without breaking the AST / syntax
            if len(self.deletable_nodes) == 0: # if no nodes can be deleted, return without attepmting delete
                if DEBUG:
                    info("Delete operation not possible. Returning with no-op.")
                return patch_list, ast
            
            random.seed(inc_seed())
            node_id = random.choice(self.deletable_nodes) # choose a random node_id to delete
            if DEBUG:
                info(f"Deleting node with id {node_id}\n")

        self.delete_node(ast, node_id) # delete the node corresponding to node_id
        self.numbering.renumber(ast) # renumber nodes
        self.max_node_id = self.numbering.c # reset max_node_id
        self.numbering.c = -1
        self.deletable_nodes = [] # reset deletable nodes for the next delete operation

        child_patchlist = copy.deepcopy(patch_list)
        child_patchlist.append(f"delete({node_id})") # update patch list
        return child_patchlist, ast
    
    def insert(self, ast, patch_list, node_id=None, after_id=None):
        self.insertable_nodes = [] # reset the temporary variables, in case previous insert returned early
        self.tmp_node = None
        if node_id == None and after_id == None:
            self.get_insertable_nodes(ast) # get all nodes with a type that is suited to insertion in block statements -> src
            self.get_nodes_in_block_stmt(ast) # get all nodes within a block statement -> dest
            if len(self.insertable_nodes) == 0 or len(self.stmt_nodes) == 0: # if no insertable nodes exist, exit gracefully
                if DEBUG:
                    info("Insert operation not possible. Returning with no-op.")
                return patch_list, ast
            random.seed(inc_seed())
            after_id = random.choice(self.stmt_nodes) # choose a random src and dest
            random.seed(inc_seed())
            node_id = random.choice(self.insertable_nodes)
            if DEBUG:
                info(f"Inserting node with id {node_id} after node with id {after_id}\n")
        self.get_node_from_ast(ast, node_id) # get the node associated with the src node id
        self.insert_stmt_node(ast, self.tmp_node, after_id) # perform the insertion
        self.numbering.renumber(ast) # renumber nodes
        self.max_node_id = self.numbering.c # reset max_node_id
        self.numbering.c = -1
        child_patchlist = copy.deepcopy(patch_list)
        child_patchlist.append(f"insert({node_id}, {after_id})") # update patch list
        return child_patchlist, ast
    
    def replace(self, ast, patch_list, node_id=None, with_id=None):
        self.tmp_node = None # reset the temporary variables (in case previous replace returned sooner)
        self.replaceable_nodes = []
        self.node_class_to_replace = None

        if node_id == None:
            if self.max_node_id == -1: # if max_id is not know yet, traverse the AST to find the number of nodes -- needed to pick a random id to replace
                self.numbering.renumber(ast)
                self.max_node_id = self.numbering.c
                self.numbering.c = -1 # reset the counter for numbering
            if self.fault_loc and len(self.fault_loc_set) > 0:
                random.seed(inc_seed())
                node_id = random.choice(tuple(self.fault_loc_set)) # get a fault loc target if fault localization is being used
            else:      
                random.seed(inc_seed())      
                node_id = random.randint(0,self.max_node_id) # get random node id to replace
            if DEBUG:
                info(f"Node to replace id: {node_id}")

        self.get_node_to_replace_class(ast, node_id) # get the class of the node associated with the random node id
        if DEBUG:
            info(f"Node to replace class: {self.node_class_to_replace}")
        if self.node_class_to_replace == None: # if the node does not exist, return with no-op
            return patch_list, ast
        
        if with_id == None:       
            self.get_replaceable_nodes_by_class(ast, self.node_class_to_replace) # get all valid nodes that have a class that could be substituted for the original node's class
            if len(self.replaceable_nodes) == 0: # if no replaceable nodes exist, exit gracefully
                if DEBUG:
                    info("Replace operation not possible. Returning with no-op.")
                return patch_list, ast
            if DEBUG:
                info(f"Replaceable nodes: {self.replaceable_nodes}")
            random.seed(inc_seed())
            with_id = random.choice(self.replaceable_nodes) # get a random node id from the replaceable nodes
            if DEBUG:
                info(f"Replacing node id {node_id} with node id {with_id}")
        self.get_node_from_ast(ast, with_id) # get the node associated with with_id

        # safety guard: this could happen if crossover makes the GA think a node is actually suitable for replacement when in reality it is not....    
        if self.tmp_node.__class__ not in REPLACE_TARGETS[self.node_class_to_replace]:
            if DEBUG:
                info(self.tmp_node.__class__)
                info(REPLACE_TARGETS[self.node_class_to_replace])
            return patch_list, ast  

        self.replace_with_node(ast, node_id, self.tmp_node) # perform the replacement
        self.tmp_node = None # reset the temporary variables
        self.replaceable_nodes = []
        self.node_class_to_replace = None
        self.numbering.renumber(ast) # renumber nodes
        self.max_node_id = self.numbering.c # update max_node_id
        self.numbering.c = -1
        
        child_patchlist = copy.deepcopy(patch_list)
        child_patchlist.append(f"replace({node_id}, {with_id})") # update patch list
        return child_patchlist, ast
    
    def weighted_template_choice(self, templates):
        random.seed(inc_seed())
        p = random.random()
        if p <= 0.3:
            random.seed(inc_seed())
            return random.choice(["increment_by_one", "decrement_by_one"])
        elif p <= 0.6:
            random.seed(inc_seed())
            return random.choice(["negate_equality", "negate_inequality", "negate_ulnot"])
        elif p <= 0.8:
            random.seed(inc_seed())
            return random.choice(["nonblocking_to_blocking", "blocking_to_nonblocking"])
        else:
            random.seed(inc_seed())
            return random.choice(["sens_to_negedge", "sens_to_posedge", "sens_to_level", "sens_to_all"])

    # TODO: make sure ast is a deepcopy
    def apply_template(self, ast, patch_list, template=None, node_id=None):
        self.tmp_node = None # reset the temporary variables, in case the previous template operator returned early
        self.nodes_by_class = []

        if template == None:
            template = self.weighted_template_choice(list(TEMPLATE_MUTATIONS.keys()))
            node_type = TEMPLATE_MUTATIONS[template][0]
            self.get_nodes_by_class(ast, node_type)
            if len(self.nodes_by_class) == 0:
                if DEBUG:
                    info(f"Template {template} cannot be applied to AST. Returning with no-op.")
                return patch_list, ast # no-op
            random.seed(inc_seed())
            node_id = random.choice(self.nodes_by_class)

        self.get_node_from_ast(ast, node_id)

        # safety guards: the following can be caused by crossover operations splitting a patchlist
        if self.tmp_node == None:
            if DEBUG:
                info(f"Node with id {node_id} does not exist. Returning with no-op.")
            return patch_list, ast # no-op
        elif not (self.tmp_node.__class__.__name__ == TEMPLATE_MUTATIONS[template][0]):
            if DEBUG:
                info("Node classes do not match for template. This could have been caused by a crossover operation. Returning with no-op.")
                info("Node class was %s whereas expected class was %s..." % (self.tmp_node.__class__.__name__, TEMPLATE_MUTATIONS[template][0]))
            return patch_list, ast # no-op

        if DEBUG:
            info(f"\nApplying template {template} to node {node_id}\nOld:")
            self.tmp_node.show()
        
        child_patchlist = copy.deepcopy(patch_list)
        if template == "increment_by_one":
            new_node = vast.Plus(copy.deepcopy(self.tmp_node), vast.IntConst(1, copy.deepcopy(self.tmp_node.lineno)), copy.deepcopy(self.tmp_node.lineno))
            new_node.node_id = node_id
        elif template == "decrement_by_one":
            new_node = vast.Minus(copy.deepcopy(self.tmp_node), vast.IntConst(1, copy.deepcopy(self.tmp_node.lineno)), copy.deepcopy(self.tmp_node.lineno))
        elif template == "negate_equality":
            new_node = vast.NotEq(copy.deepcopy(self.tmp_node.left), copy.deepcopy(self.tmp_node.right), copy.deepcopy(self.tmp_node.lineno))
        elif template == "negate_inequality":
            new_node = vast.Eq(copy.deepcopy(self.tmp_node.left), copy.deepcopy(self.tmp_node.right), copy.deepcopy(self.tmp_node.lineno))
        elif template == "negate_ulnot":
            new_node = vast.Ulnot(copy.deepcopy(self.tmp_node.right), copy.deepcopy(self.tmp_node.lineno))
        elif template == "sens_to_negedge":
            new_node = copy.deepcopy(self.tmp_node)
            new_node.type = "negedge"
        elif template == "sens_to_posedge":
            new_node = copy.deepcopy(self.tmp_node)
            new_node.type = "posedge"
        elif template == "sens_to_level":
            new_node = copy.deepcopy(self.tmp_node)
            new_node.type = "level"
        elif template == "sens_to_all":
            new_node = copy.deepcopy(self.tmp_node)
            new_node.type = "all"
        elif template == "nonblocking_to_blocking":
            new_node = vast.BlockingSubstitution(copy.deepcopy(self.tmp_node.left), copy.deepcopy(self.tmp_node.right), copy.deepcopy(self.tmp_node.ldelay), copy.deepcopy(self.tmp_node.rdelay), copy.deepcopy(self.tmp_node.lineno))
        elif template == "blocking_to_nonblocking":
            new_node = vast.NonblockingSubstitution(copy.deepcopy(self.tmp_node.left), copy.deepcopy(self.tmp_node.right), copy.deepcopy(self.tmp_node.ldelay), copy.deepcopy(self.tmp_node.rdelay), copy.deepcopy(self.tmp_node.lineno))
        new_node.node_id = node_id
        if DEBUG:
            info("New:")
            new_node.show()
        self.replace_with_node(ast, node_id, new_node) # replace with new template node
        child_patchlist.append(f"template({template}, {node_id})")
        self.numbering.renumber(ast) # renumber nodes
        self.max_node_id = self.numbering.c # update max_node_id
        self.numbering.c = -1
        if DEBUG:
            ast.show()
        self.tmp_node = None # reset the temporary variables
        self.nodes_by_class = []
        return child_patchlist, ast

    def get_crossover_children(self, parent_1, parent_2):
        if len(parent_1) < 1 or len(parent_2) < 1:
            return parent_1, parent_2
        random.seed(inc_seed())
        sp_1 = random.randint(0, len(parent_1))
        random.seed(inc_seed())
        sp_2 = random.randint(0, len(parent_2))
        parent_1_half_1 = copy.deepcopy(parent_1)[:sp_1]
        parent_1_half_2 = copy.deepcopy(parent_1)[sp_1:]
        parent_2_half_1 = copy.deepcopy(parent_2)[:sp_2]
        parent_2_half_2 = copy.deepcopy(parent_2)[sp_2:]
        if DEBUG:
            info(parent_1, parent_2)
            info(sp_1, sp_2)
            info(parent_1_half_1, parent_1_half_2)
            info(parent_2_half_1, parent_2_half_2)
        parent_1_half_1.extend(parent_2_half_2)
        parent_2_half_1.extend(parent_1_half_2)
        if DEBUG:
            info(parent_1_half_1, parent_2_half_1)
        return parent_1_half_1, parent_2_half_1 
    
    def crossover(self, ast, parent_1, parent_2):
        child_1, child_2 = self.get_crossover_children(parent_1, parent_2)
        child_1_ast = self.ast_from_patchlist(copy.deepcopy(ast), child_1)
        child_2_ast = self.ast_from_patchlist(copy.deepcopy(ast), child_2)
        return child_1, child_2, child_1_ast, child_2_ast
    
    def ast_from_patchlist(self, ast, patch_list):
        for m in patch_list:
            operator = m.split('(')[0]
            operands = m.split('(')[1].replace(')','').split(',')
            if operator == "replace":
                _, ast = self.replace(ast, patch_list, int(operands[0]), int(operands[1]))
            elif operator == "insert":
                _, ast = self.insert(ast, patch_list, int(operands[0]), int(operands[1]))
            elif operator == "delete":
                _, ast = self.delete(ast, patch_list, int(operands[0]))
            elif operator == "template":
                _, ast = self.apply_template(ast, patch_list, operands[0], int(operands[1]))
            else:
                info(f"Invalid operator in patch list: {m}")
        return ast

def is_interesting(mutation_op, ast, codegen, patch_list):
    tmp_ast = mutation_op.ast_from_patchlist(copy.deepcopy(ast), patch_list)
    with open(MINIMIZED, "w") as f:
        f.write(codegen.visit(tmp_ast))
    ff, _ = calc_candidate_fitness([MINIMIZED])
    if ff == 1:
        if DEBUG:
            info(f"Patch {patch_list} still has a fitness of 1.0 --> interesting")
        return True
    else:
        if DEBUG:
            info(f"Patch {patch_list} has a fitness < 1.0 --> not interesting")
        return False

"""
Delta debugging for patch minimization.
"""
def minimize_patch(mutation_op, ast, codegen, prefix, patch_list, suffix):
    mid = len(patch_list) // 2
    if mid == 0:
        return patch_list

    left = patch_list[:mid]
    if is_interesting(mutation_op, ast, codegen, prefix + left + suffix):
        return minimize_patch(mutation_op, ast, codegen, prefix, left, suffix)

    right = patch_list[mid:]
    if is_interesting(mutation_op, ast, codegen, prefix + right + suffix):
        return minimize_patch(mutation_op, ast, codegen, prefix, right, suffix)

    left = minimize_patch(mutation_op, ast, codegen, prefix, left, right + suffix)
    right = minimize_patch(mutation_op, ast, codegen, prefix + left, right, suffix)
    return left + right

def tournament_selection(mutation_op, codegen, orig_ast, popn):
    # Choose 5 random candidates for parent selection
    pool = copy.deepcopy(popn)
    while len(pool) > 5:
        random.seed(inc_seed())
        r = random.choice(pool)
        pool.remove(r)

    # generate ast from patchlist for each candidate, compute fitness for each candidate
    max_fitness = -1
    for parent_patchlist in pool:
        parent_fitness = GENOME_FITNESS_CACHE[str(parent_patchlist)]
        if parent_fitness > max_fitness:
            max_fitness = parent_fitness
            winner_patchlist = parent_patchlist
    
    winner_ast = copy.deepcopy(orig_ast)
    winner_ast = mutation_op.ast_from_patchlist(winner_ast, winner_patchlist)
    return copy.deepcopy(winner_patchlist), winner_ast

def calc_candidate_fitness(file_list: list):
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)
    if DEBUG:
        info("Running simulation ...")
    t_start = time.time()
    env.tb_eval(PROJ_DIR, file_list)
    if not os.path.exists(OUTPUT):
        t_finish = time.time()
        return 0, t_finish - t_start
    
    with open(ORACLE) as f:
        oracle_lines = f.readlines()
    
    with open(OUTPUT) as f:
        sim_lines = f.readlines()
    
    score = 0
    if FITNESS_MODE == "outputwires":
        ff, total_possible = fitness.calculate_fitness(oracle_lines, sim_lines)
        score = ff / total_possible
        if score < 0:
            score = 0
    elif FITNESS_MODE == "testcases": # experimental
        total_possible = len(sim_lines)
        count = 0
        for l in sim_lines:
            if "pass" in l.lower():
                count += 1
        if DEBUG:
            info(f"{count} out of {total_possible} testcases pass")
        score = count / total_possible
    t_finish = time.time()
    if DEBUG:
        info(f"Candidate fitness: {fitness}")
    return score, t_finish - t_start

def get_elite_parents(popn, pop_size):
    elite_size = int(5 / 100 * pop_size)
    elite = []
    for parent in popn:
        elite.append((parent, GENOME_FITNESS_CACHE[str(parent)]))
    elite.sort(key = lambda x: x[1])
    return elite[-elite_size:]

def strip_bits(bits):
    for i in range(len(bits)):
        bits[i] = bits[i].strip()
    return bits

def get_output_mismatch():
    with open(ORACLE) as f:
        oracle = f.readlines()

    with open(OUTPUT) as f:
        sim = f.readlines()

    diff_bits = []
    headers = strip_bits(oracle[0].split(","))

    if len(oracle) != len(sim): # if the output and oracle are not the same length, all output wires are defined to be mismatched
        diff_bits = headers[1:] # don't include time...
    else:
        for i in range(1, len(oracle)):
            # clk = oracle[i].split(",")[0]
            tmp_oracle = strip_bits(oracle[i].split(",")[1:])
            tmp_sim = strip_bits(sim[i].split(",")[1:])
            for b in range(len(tmp_oracle)):
                if tmp_oracle[b] != tmp_sim[b]:
                    diff_bits.append(headers[b + 1]) # offset by 1 since clk is also a header and is not an actual output

    res = set()
    for i in range(len(diff_bits)):
        tmp = diff_bits[i]
        if "[" in tmp:
            res.add(tmp.split("[")[0])
        else:
            res.add(tmp)

    uniq_headers = set()
    for i in range(len(headers)):
        tmp = headers[i]
        if "[" in tmp:
            uniq_headers.add(tmp.split("[")[0])
        else:
            uniq_headers.add(tmp)
    return res, uniq_headers

def seed_popn(ast, mutation_op, codegen, log_file):
    seeded = []
    start_time = time.time()
    while len(seeded) < 999:
        child, new_ast = mutation_op.apply_template(copy.deepcopy(ast), [])
        code = codegen.visit(new_ast)
        if DEBUG:
            info(f"{child}\n{code}\n")
        if str(child) not in GENOME_FITNESS_CACHE:
            with open(CANDIDATE, "w") as f:
                f.write(code)
            child_fitness = -1
            # re-parse the written candidate to check for syntax errors -> zero fitness if the candidate does not compile
            try:
                parse([CANDIDATE])
            except ParseError:
                child_fitness = 0
            # if the child fitness was not 0, i.e. the parser did not throw syntax errors
            if child_fitness == -1:
                child_fitness, sim_time = calc_candidate_fitness([CANDIDATE])
                global FITNESS_EVAL_TIMES
                FITNESS_EVAL_TIMES.append(sim_time)
                if os.path.exists(OUTPUT):
                    os.remove(OUTPUT)
            GENOME_FITNESS_CACHE[str(child)] = child_fitness
            if SHOW_FITNESS:
                info(f'Child fitness: {child_fitness}')
            if LOG and log_file:
                log_file.write("\t%s --template_seeding--> %s\t\t%s\n" % ("[]", str(child), "{:.17g}".format(child_fitness)))
            if child_fitness == 1.0:
                total_time = time.time() - start_time
                info(f"######## REPAIR FOUND WHILE SEEDING INITIAL POPN ########")
                if DEBUG:
                    info(f"{code}\n{child}")
                info(f"TOTAL TIME TAKEN TO FIND REPAIR = {total_time}")
                if LOG and log_file: 
                    log_file.write(f"\n\n######## REPAIR FOUND ########\n\t\t{child}\n")
                    log_file.write(f"TOTAL TIME TAKEN TO FIND REPAIR = {total_time}\n")
                minimized = minimize_patch(mutation_op, ast, codegen, [], child, [])
                if DEBUG:
                    info(f"\n\nMinimized patch: {minimized}")
                if LOG and log_file:
                    log_file.write(f"Minimized patch: {minimized}\n")
                    log_file.close()
                return []
        else: # not a unique seed, log it anyways
            if LOG and log_file:
                log_file.write("\t%s --template_seeding--> %s\t\t%s\n" % ("[]", str(child), "{:.17g}".format(GENOME_FITNESS_CACHE[str(child)])))
        seeded.append(child)
    if DEBUG:
        info(GENOME_FITNESS_CACHE)
        info(len(GENOME_FITNESS_CACHE))
    return seeded

def extended_fl_for_study(fl_lines, delta):
    extended_fl = set()
    for i in range(max(fl_lines) + delta):
        if i in fl_lines:
            extended_fl.add(i)
        else:
            for j in range(1, delta + 1):
                if i + j in fl_lines or i - j in fl_lines:
                    extended_fl.add(i)
    return extended_fl

def repair():
    log_file = None
    start_time = time.time()
    codegen = ASTCodeGenerator()
    ast, _ = parse([SRC_FILE])
    if DEBUG:
        ast.show()
    src_code = codegen.visit(ast)
    if DEBUG:
        info(f"{src_code}\n\n")
    mutation_op = MutationOp(POPSIZE, FAULT_LOC, CONTROL_FLOW)

    # calculate fitness of the original buggy program
    orig_fitness, sim_time = calc_candidate_fitness([SRC_FILE])
    global FITNESS_EVAL_TIMES
    FITNESS_EVAL_TIMES.append(sim_time)
    GENOME_FITNESS_CACHE[str([])] = orig_fitness

    if SHOW_FITNESS:
        info(f"Original fitness: {orig_fitness}")
    
    if FITNESS_MODE == "outputwires":
        mismatch_set, uniq_headers = get_output_mismatch()
        if DEBUG:
            info(mismatch_set)
    
    if LOG:
        log_entries = [
            ("seed", SEED),
            ("fitness_mode", FITNESS_MODE),
            ("gens", GENS),
            ("popsize", POPSIZE),
            ("mutation_rate", MUTATION_RATE),
            ("crossover_rate", CROSSOVER_RATE),
            ("replacement_rate", REPLACEMENT_RATE),
            ("insertion_rate", INSERTION_RATE),
            ("deletion_rate", DELETION_RATE),
            ("restarts", RESTARTS),
            ("fault_loc", FAULT_LOC),
            ("control_flow", CONTROL_FLOW),
            ("limit_transitive_dependency_set", LIMIT_TRANSITIVE_DEPENDENCY_SET),
            ("dependency_set_max", DEPENDENCY_SET_MAX),
        ]
        log_dir = os.path.join(PROJ_DIR, "log")
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)
            if DEBUG:
                info(f"Log dir: {log_dir}")
        log_file = open(os.path.join(log_dir, f"repair_{TIME_NOW}.log"), "w+")
        for label, value in log_entries:
            if isinstance(value, (int, float)):
                log_file.write(f"\t{label}={value}\n")
            else:
                log_file.write(f"{label}:\n\t{value}\n")
    
    best_patches = dict()
    comp_failures = 0
    for restart_attempt in range(RESTARTS):
        popn = []
        popn.append([])
        # seed initial population using repair templates
        seeds = seed_popn(copy.deepcopy(ast), mutation_op, codegen, log_file)
        if not seeds:
            return True
        popn.extend(seeds)
        tmp_cnts = {}
        for i in popn:
            if str(i) in tmp_cnts: 
                tmp_cnts[str(i)] += 1
            else: 
                tmp_cnts[str(i)] = 1
        if DEBUG:
            info(f"Seeded popn:\n{tmp_cnts}\n")
        for i in range(GENS):
            if DEBUG:
                info(f"IN GENERATION {i} OF ATTEMPT {restart_attempt}\n")
            if LOG:
                log_file.write(f"IN GENERATION {i} OF ATTEMPT {restart_attempt}\n")
            time.sleep(1)
            _children = []
            if i > 0: 
                elite_parents = get_elite_parents(popn, POPSIZE)
                for parent in elite_parents:
                    _children.append(parent[0])
                    if LOG:
                        log_file.write("\t%s --elitism--> %s\t\t%f\n" % (str(parent[0]), str(parent[0]), parent[1]))

            while len(_children) < POPSIZE:
                parent_patchlist, parent_ast = tournament_selection(mutation_op, codegen, ast, popn)
                if DEBUG:
                    info(parent_patchlist)
                if mutation_op.fault_loc:
                    tmp_mismatch_set = copy.deepcopy(mismatch_set)
                    mutation_op.get_fault_loc_targets(parent_ast, tmp_mismatch_set, uniq_headers) # compute fault localization for the parent
                    if DEBUG:
                        info(f"\nInitial Fault Localization: {mutation_op.fault_loc_set}")
                    while len(mutation_op.new_vars_in_fault_loc) > 0:
                        new_mismatch_set = set(mutation_op.new_vars_in_fault_loc.values())
                        if DEBUG:
                            info(f"New vars in fault loc: {new_mismatch_set}")
                        mutation_op.new_vars_in_fault_loc = dict()
                        tmp_mismatch_set = tmp_mismatch_set.union(new_mismatch_set)
                        mutation_op.get_fault_loc_targets(parent_ast, tmp_mismatch_set, uniq_headers)
                        if DEBUG:
                            info(f"Fault Localization: {mutation_op.fault_loc_set}")
                    if DEBUG:
                        info(f"Final mismatch set: {tmp_mismatch_set}")
                        info(f"Final Fault Localization: {mutation_op.fault_loc_set}")
                        info(len(mutation_op.fault_loc_set))
                mutation_op.implicated_lines = set()
                mutation_op.collect_lines_for_fl(parent_ast)
                if DEBUG:
                    info(f"Lines implicated by FL: {mutation_op.implicated_lines}")
                    info(f"Number of lines implicated by FL: {len(mutation_op.implicated_lines)}")

                mutation_op.implicated_lines = set()
                random.seed(inc_seed())
                p = random.random()
                _tmp_children = []
                if p <= 0.2: # apply templates 20% of the time
                    child, child_ast = mutation_op.apply_template(copy.deepcopy(parent_ast), copy.deepcopy(parent_patchlist))
                    _tmp_children.append((child, child_ast))
                    if LOG:
                        log_file.write("\t%s --template--> %s\t\t" % (str(parent_patchlist), str(child)))
                else:
                    random.seed(inc_seed())
                    p = random.random()
                    if i > 1 and 0 <= p and p < CROSSOVER_RATE and len(_children) <= POPSIZE - 2: # the last condition ensures that crossover does not result in a popn larger than popsize 
                        # crossover
                        parent_2_patchlist, _ = tournament_selection(mutation_op, codegen, ast, popn)
                        child_1, child_2, child_1_ast, child_2_ast = mutation_op.crossover(ast, parent_patchlist, parent_2_patchlist)
                        _tmp_children.append((child_1, child_1_ast))
                        _tmp_children.append((child_2, child_2_ast))
                        if LOG:
                            log_file.write("\t%s + %s --crossover--> %s + %s\t\t" % (str(parent_patchlist), str(parent_2_patchlist), str(child_1), str(child_2)))
                        if DEBUG:
                            info(child_1, child_2)
                    else:
                        # mutation
                        random.seed(inc_seed())
                        p = random.random()
                        if 0 <= p and p <= REPLACEMENT_RATE:
                            # TODO: optimization -> don't return ast from parent selection; compute it later (crossover doesn't need it)
                            child, child_ast = mutation_op.replace(parent_ast, parent_patchlist)
                            if LOG:
                                log_file.write("\t%s --mutation--> %s\t\t" % (str(parent_patchlist), str(child)))
                        elif REPLACEMENT_RATE < p and p <= REPLACEMENT_RATE + DELETION_RATE:
                            child, child_ast = mutation_op.delete(parent_ast, parent_patchlist)
                            if LOG:
                                log_file.write("\t%s --mutation--> %s\t\t" % (str(parent_patchlist), str(child)))
                        else:
                            child, child_ast = mutation_op.insert(parent_ast, parent_patchlist)
                            if LOG:
                                log_file.write("\t%s --mutation--> %s\t\t" % (str(parent_patchlist), str(child)))
                        _tmp_children.append((child, child_ast))
                        if DEBUG:
                            info(f"\n{child}")
                # calculate children fitness
                for (child_patchlist, child_ast) in _tmp_children:
                    if str(child_patchlist) in GENOME_FITNESS_CACHE:
                        child_fitness = GENOME_FITNESS_CACHE[str(child_patchlist)]
                        if SHOW_FITNESS:
                            info(f"Fitness: {child_fitness}")
                    else:
                        code = codegen.visit(child_ast)
                        with open(CANDIDATE, "w") as f:
                            f.write(code)
                        child_fitness = -1
                        # re-parse the written candidate to check for syntax errors -> zero fitness if the candidate does not compile
                        try:
                            parse([CANDIDATE])
                        except ParseError:
                            child_fitness = 0
                            comp_failures += 1
                        # if the child fitness was not 0, i.e. the parser did not throw syntax errors
                        if child_fitness == -1:
                            child_fitness, sim_time = calc_candidate_fitness([CANDIDATE])
                            FITNESS_EVAL_TIMES.append(sim_time)
                            if os.path.exists(OUTPUT):
                                os.remove(OUTPUT)
                        GENOME_FITNESS_CACHE[str(child_patchlist)] = child_fitness
                        if SHOW_FITNESS:
                            info(f'Fitness: {child_fitness}')
                    if LOG:
                        log_file.write("%s " % "{:.17g}".format(child_fitness))
                    if DEBUG:
                        info("\n\n#################\n\n")
                    if child_fitness == 1.0:
                        total_time = time.time() - start_time
                        fitness_times = sum(FITNESS_EVAL_TIMES)
                        info(f"######## REPAIR FOUND ########")
                        if DEBUG:
                            info(f'{code}\n{child_patchlist}')
                        info(f"TOTAL TIME TAKEN TO FIND REPAIR = {total_time}")
                        info(f"TOTAL TIME SPENT ON FITNESS EVALS = {fitness_times}")
                        if LOG: 
                            log_file.write(f"\n\n######## REPAIR FOUND ########\n\t\t{child_patchlist}\n")
                            log_file.write(f"TOTAL TIME TAKEN TO FIND REPAIR = {total_time}\n")
                        minimized = minimize_patch(mutation_op, ast, codegen, [], child_patchlist, [])
                        if DEBUG:
                            info(f"Minimized patch: {minimized}")
                        if LOG:
                            log_file.write(f"Minimized patch: {minimized}\n")
                            log_file.close()
                        return True
                    _children.append(child_patchlist)
                if LOG:
                    log_file.write("\n")
                if mutation_op.fault_loc:
                    mutation_op.fault_loc_set = set() # reset the fault localization data structures for the next parent
                    mutation_op.new_vars_in_fault_loc = dict()
                    mutation_op.wires_brought_in = dict()
                if SHOW_FAILURES:
                    info(f"NUMBER OF COMPILATION FAILURES SO FAR: {comp_failures}")
            popn = copy.deepcopy(_children)
            if DEBUG:
                info(*popn, sep='\n')
        best_patches[restart_attempt] = get_elite_parents(popn, POPSIZE)
    total_time = time.time() - start_time
    fitness_times = sum(FITNESS_EVAL_TIMES)
    info(f"######## NO REPAIR FOUND ########")
    info(f"TOTAL TIME TAKEN = {total_time}")
    info(f"TOTAL TIME SPENT ON FITNESS EVALS = {fitness_times}")
    if LOG:
        log_file.write(f"\n\n\nTOTAL TIME TAKEN = {total_time}\n\n")
        log_file.write("BEST PATCHES:\n")
    for attempt in best_patches:
        if DEBUG:
            info(f"Attempt number {attempt}")
        if LOG:
            log_file.write(f"\tAttempt number {attempt}:\n")
            for candidate in best_patches[attempt]:
                log_file.write(f"\t\t{candidate}\n")
        if DEBUG:
            info(*best_patches[attempt], sep='\n')
    if LOG:
        log_file.close()
    return False

def cirfix_checker(proj: Path, bug_name: str, file_list: list):
    assert(len(file_list) == 1)
    bug_file = file_list[0]
    
    global ORACLE
    global OUTPUT
    global SRC_FILE
    global PROJ_DIR
    global CANDIDATE
    global MINIMIZED

    PROJ_DIR = proj
    SRC_FILE = bug_file
    ORACLE = env.get_oracle_file(proj)
    OUTPUT = env.get_output_file(proj)
    CANDIDATE = env.get_candidate_file(proj)
    MINIMIZED = env.get_minimized_file(proj)
    
    info(f'Repairing {bug_name} ...')
    if repair():
        env.save_fixed_module(proj, bug_name, CANDIDATE, MINIMIZED)

def main():
    global LOG
    parser = argparse.ArgumentParser(description="CirFix")
    parser.add_argument("--log", action="store_true", help="Enable detailed logging for better debugging.")
    
    args = parser.parse_args()

    LOG = args.log
    add_checker(checker=cirfix_checker)

if __name__ == "__main__":
    main()
