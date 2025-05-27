import json
from pyverilog.vparser.parser import parse
from pyverilog.vparser.ast import (ModuleDef, Decl, Input, Output, Inout, Ioport,
                                  Parameter, IntConst, Identifier, Plus, Minus,
                                  Rvalue, Constant)

def get_parameter_value(param_node):
    """Extract parameter value with enhanced constant handling"""
    if not hasattr(param_node, 'value'):
        return None
    
    value_node = param_node.value
    # Unwrap Rvalue wrappers
    while isinstance(value_node, Rvalue):
        value_node = value_node.var
    
    # Handle IntConst with base prefixes (e.g., 2'b00)
    if isinstance(value_node, IntConst):
        val_str = value_node.value
        if "'" in val_str:
            try:
                size_part, base_part = val_str.split("'")
                base = {'b': 2, 'd': 10, 'h': 16}[base_part[0]]
                return int(base_part[1:], base)
            except:
                return None
        return int(val_str)
    
    # Handle Constant nodes
    if isinstance(value_node, Constant):
        if value_node.value.startswith(("'b", "'d", "'h")):
            base = {'b': 2, 'd': 10, 'h': 16}[value_node.value[1]]
            return int(value_node.value[2:], base)
        return int(value_node.value)
    
    return None

def ast_to_string(node):
    """Convert AST nodes to evaluable strings"""
    if isinstance(node, IntConst):
        return node.value
    if isinstance(node, Identifier):
        return node.name
    if isinstance(node, (Plus, Minus)):
        left = ast_to_string(node.left)
        right = ast_to_string(node.right)
        op = '+' if isinstance(node, Plus) else '-'
        return f"({left}{op}{right})"
    if isinstance(node, Rvalue):
        return ast_to_string(node.var)
    return str(node)

def evaluate_width(width_node, params):
    """Calculate width with parameter substitution"""
    if not hasattr(width_node, 'msb') or not hasattr(width_node, 'lsb'):
        return 1, None
    
    msb_expr = ast_to_string(width_node.msb)
    lsb_expr = ast_to_string(width_node.lsb)
    
    try:
        local_vars = {k: v for k, v in params.items()}
        msb = eval(msb_expr, {}, local_vars)
        lsb = eval(lsb_expr, {}, local_vars)
        return abs(msb - lsb) + 1, f"[{msb_expr}:{lsb_expr}]"
    except:
        return None, f"[{msb_expr}:{lsb_expr}]"

def get_port_info(port, params):
    """Extract port information with type checking"""
    if isinstance(port, Ioport):
        inner = port.first
    else:
        inner = port
    
    direction_map = {Input: "input", Output: "output", Inout: "inout"}
    direction = direction_map.get(type(inner))
    if not direction:
        return None
    
    port_info = {
        "name": inner.name,
        "direction": direction,
        "width": 1
    }
    
    if hasattr(inner, 'width') and inner.width:
        width, expr = evaluate_width(inner.width, params)
        port_info["width"] = width if width is not None else 1
    
    return port_info

def extract_interface(module_name, input_verilog, output_json):
    try:
        ast, _ = parse([input_verilog])
    except Exception as e:
        raise RuntimeError(f"Parse error: {e}")
    
    # Find target module
    target_module = next(
        (defn for defn in ast.children()[0].definitions 
         if isinstance(defn, ModuleDef) and defn.name == module_name),
        None
    )
    if not target_module:
        raise ValueError(f"Module {module_name} not found")
    
    params = {}
    
    # Extract parameters from module header
    if hasattr(target_module, 'paramlist') and target_module.paramlist:
        for decl in target_module.paramlist.params:
            if isinstance(decl, Decl):
                for param in decl.list:
                    if isinstance(param, Parameter) and not getattr(param, 'local', False):
                        value = get_parameter_value(param)
                        if value is not None:
                            params[param.name] = value
    
    # Extract parameters from module body
    for item in target_module.items:
        if isinstance(item, Decl):
            for subitem in item.list:
                if isinstance(subitem, Parameter) and not getattr(subitem, 'local', False):
                    value = get_parameter_value(subitem)
                    if value is not None:
                        params[subitem.name] = value
    
    # Process ports
    ports = []
    for port in target_module.portlist.ports:
        port_info = get_port_info(port, params)
        if port_info:
            ports.append(port_info)
    
    # Handle ANSI-style ports if needed
    if not ports:
        port_names = [p.first.name if isinstance(p, Ioport) else p.name 
                      for p in target_module.portlist.ports]
        for item in target_module.items:
            if isinstance(item, Decl):
                for subitem in item.list:
                    if isinstance(subitem, (Input, Output, Inout)):
                        port_info = get_port_info(subitem, params)
                        if port_info and port_info["name"] in port_names:
                            ports.append(port_info)
    
    # Generate output
    with open(output_json, 'w') as f:
        json.dump(ports, f, indent=4)
