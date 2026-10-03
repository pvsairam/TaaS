# Demo tests

Five small tests to try the newer features on your own pod. They only read from the pod (they never
save, submit or delete), and they are kept out of `examples/tests` so "Run all tests" and new clients do
not pick them up.

To use them, copy them into your tests folder, then open **Tests** (press F5 if it is already open):

    Windows PowerShell:   Copy-Item examples\demos\* my_tests\ -Recurse
    Mac or Linux:         cp -r examples/demos/* my_tests/

(`-Recurse` / `-r` also copies the `_library` folder the two shared-steps demos need.)

Delete them from `my_tests` when you are done. Steps for each are in TESTING.md (6.14 and 6.16).

| File | Shows | What you should see |
|---|---|---|
| `retry_demo.yaml` | Retries | It fails, and its step says "Tried 2 times" |
| `suggest_demo.yaml` | Suggested fixes | It fails at step 2; Needs attention suggests the link "Locations" |
| `cleanup_demo.yaml` | Cleanup after a test | It passes, and a box says "Test data cleaned up" |
| `library_demo_one.yaml`, `library_demo_two.yaml` | Shared steps | Both pass. Shared steps lists `read-locations` used by 2 tests |
