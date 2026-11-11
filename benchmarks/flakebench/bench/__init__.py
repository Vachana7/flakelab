"""FlakeBench: fixtures whose causes of flakiness are known by construction.

Each test file plants one kind of cause. `expected.json` lists the ground truth.
These are deliberately designed tests: results on them show whether FlakeLab
works as intended, not how it performs on real-world projects.
"""
