# Perceptron Exercise Verification

**Date:** 2026-11-01 19:31 UTC

## The Error

The original exercise claimed the expected output is 0.638, but this is **wrong**.

## Correct Computation

```
w1 * x1 = 1.2 * 0.5 = 0.6
w2 * x2 = -0.8 * 0.3 = -0.24
z = 0.6 + (-0.24) + 0.1 = 0.46
sigmoid(0.46) = 0.6130141761393355
```

## Where the Error Occurred

The exercise incorrectly computed:
- 0.6 + (-0.24) + 0.1 = **0.56** (WRONG)

The correct sum is:
- 0.6 + (-0.24) + 0.1 = **0.46** (CORRECT)

## Verification

The Python program confirms:
```
z = 0.45999999999999996  (floating-point representation of 0.46)
sigmoid(z) = 0.6130141761393355
```

## Conclusion

The answer is **sigmoid(0.46) ≈ 0.6130**, not 0.638. The exercise contained an arithmetic error in the intermediate step.

---
*Witnessed: 6b727c44-e204-4d06-902a-d81a5ac1452c*
