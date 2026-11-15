---
name: test-coverage-assessment
description: Method for judging whether tests would catch a defect and for proposing missing test cases (boundaries, equivalence classes, state changes, consumers of shared data, flaky tests). Load it for bug reports with green tests, CI failures, and pull requests that add or change behaviour.
---

# Test coverage assessment

A test suite is judged by the defects it would catch, not by how many tests it has.

1. **Ask of every relevant test: what bug would make this fail?** Read the assertion, not the test name.
   Assertions on counts or lengths pass for wrong content. Assertions on round numbers pass for wrong rounding.
2. **Boundaries.** For every threshold or limit in the code or the spec, there must be tests just below, exactly at,
   and just above it. Compare the operator in the code (`>`, `>=`) with the words in the spec ("or more", "more than").
3. **Equivalence classes.** Zero, one, many; empty; maximum; negative; values with odd cents for money.
4. **State.** What rows can exist that the happy path never creates (removed items, voided payments, inactive
   codes)? Each needs a test in every function that reads that table.
5. **Consumers.** When a change alters what a value means, list every function that computes or displays that value
   (`search_code`) and check each has a test. Two code paths computing "the same" number need a test that compares them.
6. **Failing tests.** `get_test_results`: read the assertion message and the run metadata (time, runner, trigger).
   A test that fails only at certain times or on certain machines depends on the clock, the timezone, ordering or
   shared state; say which.

## Output

- Why the existing tests did not catch the problem, citing the assertion.
- A list of test cases to add, each as "given / when / then" in one line, most valuable first.
- For a flaky test: the dependency that makes it flaky and the smallest change that removes it.
