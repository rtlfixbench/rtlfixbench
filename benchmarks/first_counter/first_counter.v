`timescale 1ns/1ps

module first_counter (
    input  wire        clk,          // Clock signal
    input  wire        reset,        // Synchronous active-high reset
    input  wire        enable,       // Active-high enable signal
    output reg  [3:0]  counter_out,  // 4-bit counter output
    output reg         overflow_out  // Overflow flag
);

    // Counter process
    always @(posedge clk) begin
        // Synchronous reset
        if (reset == 1'b1) begin
            counter_out <= #1 4'b0000;
            overflow_out <= #1 1'b0;
        end
        // Increment counter when enabled
        else if (enable == 1'b1) begin
            counter_out <= #1 counter_out + 1;
        end
        // Overflow detection
        if (counter_out == 4'b1111) begin
            overflow_out <= 1'b1;
        end
    end

endmodule
