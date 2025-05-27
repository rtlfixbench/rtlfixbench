`timescale 1ns/1ns

module tff (
    input  wire clk,
    input  wire rstn,
    input  wire t,
    output reg  q
);

    always @(posedge clk) begin
        if (!rstn)
            q <= 1'b0;
        else if (t)
            q <= ~q;
        else
            q <= q;
    end

endmodule
