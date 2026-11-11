"""FlakeLab: experimental root-cause investigation for unreliable CI tests.

FlakeLab re-runs a test suite many times under controlled environment
conditions (CPU, memory, network, test order, timezone) and uses statistics
to report which conditions are associated with each test's failures.
"""

__version__ = "0.1.0"
