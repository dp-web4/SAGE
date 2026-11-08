#!/usr/bin/env python3
"""
Perceptron forward pass: verify the sigmoid output.
Original exercise parameters: x1=0.5, x2=0.3, w1=1.2, w2=-0.8, bias=0.1
z = 0.6 + (-0.24) + 0.1 = 0.46
sigmoid(0.46) = 0.6130141761393355
Verification: sigmoid(1.2) = 1/(1+e^-1.2) = 1/(1+0.301194) = 0.768525
"""
import math

def sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)

def forward(x1: float, x2: float, w1: float, w2: float, bias: float) -> float:
    """Single-layer perceptron: z = w1*x1 + w2*x2 + bias, then sigmoid(z)."""
    z = w1 * x1 + w2 * x2 + bias
    return sigmoid(z)

if __name__ == "__main__":
    # Original exercise parameters
    x1, x2 = 0.5, 0.3
    w1, w2 = 1.2, -0.8
    bias = 0.1
    
    # Print each product on its own line
    print(f"Input x1={x1}, x2={x2}, w1={w1}, w2={w2}, bias={bias}")
    print(f"w1 * x1 = {w1} * {x1} = {w1 * x1}")
    print(f"w2 * x2 = {w2} * {x2} = {w2 * x2}")
    print(f"z = w1*x1 + w2*x2 + bias = {w1*x1 + w2*x2 + bias}")
    print(f"sigmoid(z) = {sigmoid(w1 * x1 + w2 * x2 + bias)}")
    print()
    print("Verification: sigmoid(1.2) = 1/(1+e^-1.2) = 1/(1+0.301194) = 0.768525")
