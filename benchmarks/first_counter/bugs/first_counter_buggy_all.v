module first_counter (
    input  wire        clk,
    input  wire        reset,
    input  wire        enable,
    output reg  [3:0]  counter_out,
    output reg         overflow_out
);

    always @(posedge clk) begin
        if (reset == 1'b1) begin
            counter_out <= #1 4'b0000;
            overflow_out <= #1 1'b1;
        end
        else if (enable == 1'b1) begin
            counter_out <= #1 counter_out + 2;
        end
        if (counter_out >= 4'b1110) begin
            overflow_out <= 1'b1;
        end
    end

endmodule
