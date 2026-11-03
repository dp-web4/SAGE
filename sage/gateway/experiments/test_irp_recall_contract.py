"""Synthetic integration controls for the current IRP runner, not a recall implementation."""
import unittest

from sage.irp.base import IRPPlugin, IRPState


class _Probe(IRPPlugin):
    def __init__(self, config):
        super().__init__(config)
        self.project_calls = 0
        self.step_inputs = []

    def init_state(self, x0, task_ctx):
        return IRPState(x=x0)

    def energy(self, state):
        return 1.0

    def step(self, state, noise_schedule=None):
        self.step_inputs.append(state.x)
        return IRPState(x=state.x)

    def project(self, state):
        self.project_calls += 1
        return IRPState(x="projected")


class RunnerContractTests(unittest.TestCase):
    def test_initial_halt_returns_state_without_calling_project(self):
        probe = _Probe({"max_iterations": 1})
        state, history = probe.refine("synthetic-candidate")
        self.assertEqual(state.x, "synthetic-candidate")
        self.assertEqual(probe.project_calls, 0)
        self.assertEqual(len(history), 1)

    def test_first_step_receives_initial_state_before_projection(self):
        probe = _Probe({"max_iterations": 2})
        state, history = probe.refine("synthetic-candidate")
        self.assertEqual(probe.step_inputs, ["synthetic-candidate"])
        self.assertEqual(probe.project_calls, 1)
        self.assertEqual(state.x, "projected")
        self.assertEqual(len(history), 2)

    def test_zero_max_steps_does_not_disable_the_existing_runner(self):
        probe = _Probe({"max_iterations": 2})
        probe.refine("synthetic-candidate", max_steps=0)
        self.assertEqual(len(probe.step_inputs), 1)


if __name__ == "__main__":
    unittest.main()
