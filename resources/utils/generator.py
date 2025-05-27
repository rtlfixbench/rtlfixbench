import json
import pandas as pd

CYCLE_PERIOD = 10

TB_TEMPLATE = """\
module testbench;
    {top_module} dut (
        {dut_instantiation}
    );

    {input_declarations}
    {output_declarations}
    reg {clk_name};

    parameter CLK_PERIOD = {clk_period};
    
    integer csv_file;
    initial begin
        csv_file = $fopen("{output_csv}", "w");
        $fwrite(csv_file, "time,{output_csv_header}\\n");
        {vcd_dump_commands}
    end
    
    always #(CLK_PERIOD/2) {clk_name} = ~{clk_name};
    
    initial begin
        {clk_name} = 0;
    end
    
    integer cycle;
    initial begin
        {input_init};
        for (cycle = 0; cycle < {total_cycles}; cycle = cycle + 1) begin
            @(posedge {clk_name});
            case(cycle)
{input_application}
                default: begin end
            endcase
            $fwrite(csv_file, "{time_format},{output_csv_format}\\n", $time, {output_signals});
        end
        
        $fclose(csv_file);
        $finish;
    end
endmodule
"""

def convert_value(val):
    try:
        # Check if the value is a binary string
        if isinstance(val, str) and all(c in '01' for c in val):
            bit_width = len(val)
            return f"{bit_width}'b{val}"
        
        # Convert decimal integers to binary with an inferred bit width
        num = int(val)
        if num >= 0:
            bit_width = max(1, num.bit_length())
            binary_repr = bin(num)[2:]  # Get binary representation without '0b'
            return f"{bit_width}'b{binary_repr}"
        else:
            raise ValueError("Negative values are not supported.")
    
    except ValueError:
        return val

def generate_testbench(
        top_module,
        clk_name,
        interface_json,
        tb_csv,
        oracle_csv,
        output_csv,
        output_tb,
        clk_period=CYCLE_PERIOD,
        vcd_file=None):
    
    # Load port definitions from JSON
    with open(interface_json) as f:
        ports = json.load(f)
    
    # Read CSV file using pandas
    df = pd.read_csv(tb_csv)
    if 'time' not in df.columns:
        raise ValueError("CSV file must contain a 'time' column.")
    
    # Filter input and output ports, excluding clock and reset signals
    input_ports = [p['name'] for p in ports 
                   if p['direction'] == 'input' 
                   and p['name'] not in [clk_name, 'time']]
    output_ports = [p['name'] for p in ports if p['direction'] == 'output']

    # Extract bit-widths for input and output ports
    input_bit_widths = {p['name']: p.get('width', 1) for p in ports if p['direction'] == 'input'}
    output_bit_widths = {p['name']: p.get('width', 1) for p in ports if p['direction'] == 'output'}

    
    # Build DUT instantiation list
    dut_instantiation = ', '.join([f'.{p["name"]}({p["name"]})' for p in ports])

    # Generate input declarations
    input_declarations = '\n    '.join(
        [f'reg [{input_bit_widths[port]-1}:0] {port};' if input_bit_widths[port] > 1 else f'reg {port};' for port in input_ports]
    )
    
    # Generate output declarations
    output_declarations = '\n    '.join(
        [f'wire [{output_bit_widths[port]-1}:0] {port};' if output_bit_widths[port] > 1 else f'wire {port};' for port in output_ports]
    )
    
    # Create CSV header and format strings for output logging
    output_csv_header = ','.join(output_ports)
    output_csv_format = ','.join([f'%0{output_bit_widths[port]}b' for port in output_ports])
    time_format = "%0d"

    # Initialize inputs to zero
    input_init = '; '.join(
        [f"{port} = {input_bit_widths[port]}'b0" if input_bit_widths[port] > 1 else f'{port} = 0'
         for port in input_ports]
    )
    
    # Generate the case statement for input application using CSV rows
    input_application_lines = []
    for idx, row in df.iterrows():
        assignments = []
        for port in input_ports:
            if port in row:
                value = convert_value(row[port])
                assignments.append(f'                    {port} = {value};')
        case_branch = f'                {idx}: begin\n' + '\n'.join(assignments) + '\n                end'
        input_application_lines.append(case_branch)
    
    input_application = '\n'.join(input_application_lines)
    
    # Extract oracle outputs and save to CSV
    oracle_columns = ['time'] + output_ports if 'time' in df.columns else output_ports
    df[oracle_columns].to_csv(oracle_csv, index=False)
    
    if vcd_file:
        vcd_dump_commands = f"""
        $dumpfile("{vcd_file}");
        $dumpvars(0, testbench);
        """
    else:
        vcd_dump_commands = ""
    
    template_data = {
        'top_module': top_module,
        'dut_instantiation': dut_instantiation,
        'input_declarations': input_declarations,
        'output_declarations': output_declarations,
        'output_csv': output_csv,
        'output_csv_header': output_csv_header,
        'output_csv_format': output_csv_format,
        'time_format': time_format,
        'output_signals': ', '.join(output_ports),
        'input_init': input_init,
        'total_cycles': len(df),
        'input_application': input_application,
        'clk_name': clk_name,
        'clk_period': clk_period,
        'vcd_dump_commands': vcd_dump_commands.strip()
    }
    
    with open(output_tb, 'w') as f:
        f.write(TB_TEMPLATE.format(**template_data))
