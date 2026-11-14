# End-to-end validation with upstream PR #5

[Successful Actions run](https://github.com/jimbao/blockless-spring-grpc-example/actions/runs/43628966480)
completed on 2026-11-14 in 11m6s. Download `performance-43628966480-1` from
that run for the report, raw measurements, logs, and environment metadata.

- Source: `pjlabs/blockless-spring-grpc-example`, PR #5 (Blockless 0.1.9 → 0.2.1).
- Baseline: `ff71d1bef01a8a3617f7103fde7ceace2e26ddf3`.
- PR and proposed merge: `87ca775ad4e6313922cab2be3ae3a08941ac9db7`
  (the merge was a fast-forward).
- Both Maven builds succeeded; all 14 scenarios ran five times for each build.
- Inspected artifact: 140 measured JSON files and 140 warmup JSON files;
  positive request counts and latencies in every measured run.
- Measured requests: base 142,267; candidate 141,759. Zero non-OK gRPC responses.
- Report generation, workflow summary, and artifact upload succeeded.

This used **smoke mode** (1s warmup / 2s measurement). It validates pipeline
execution, not performance improvements or regressions. The normal profile still
uses 10s warmup / 20s measurement and requires a separate run for performance conclusions.

The fork validation intentionally skipped the PR comment step because its token
cannot write to the upstream PR. Comment creation/update has not been verified
end to end by this run.

The initial CI run exposed a missing `rg` executable on the hosted runner. Runtime
checks now use `grep`. The workflow also supports an explicit source repository so
a fork can benchmark upstream PR refs. These fixes are on `ci/performance-comparison`.
