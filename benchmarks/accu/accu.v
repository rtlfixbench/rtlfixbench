`timescale 1ns/1ns

module accu(
    input               clk,   
    input               rst_n,
    input       [7:0]   data_in,
    input               valid_in,
    output  reg         valid_out,
    output  reg [9:0]   data_out
);
    
    reg [1:0] count;
    reg [9:0] accum;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0;
            accum <= 0;
            valid_out <= 0;
            data_out <= 0;
        end else begin
            valid_out <= 0;
            
            if (valid_in) begin
                if (count == 2'd3) begin
                    count <= 0;
                    data_out <= accum + data_in;
                    valid_out <= 1;
                end else begin
                    count <= count + 1;
                end
                
                accum <= (count == 0) ? data_in : (accum + data_in);
            end
        end
    end
endmodule