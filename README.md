# The 7/8 quasi-Riemann hypothesis in Lean

This public repository isolates the Riemann zeta result from
[openai/math](https://github.com/openai/math/tree/adc7f1241b42e322a6451854ab7e4b4c146bf78a).
The copied Lean sources and Comparator challenge are unchanged.

**Comparator verification is pending.** The presence of sources or a workflow
does not establish that the proof passes. Check the
[Quasi-Riemann Comparator workflow](https://github.com/CoolRmal/quasi-riemann-seven-eighths/actions/workflows/comparator.yml)
and its uploaded logs for the result.

The target theorem states:

$$
\operatorname{Re}(s)>\frac78\quad\Longrightarrow\quad\zeta(s)\ne0.
$$

The proof entry point is
[`OAI/NumberTheory/DirichletL/Nonvanishing.lean`](OAI/NumberTheory/DirichletL/Nonvanishing.lean).
Its theorem is `OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re`.
The independently stated target is
[`ComparatorChallenges/QuasiRiemannHypothesis.lean`](ComparatorChallenges/QuasiRiemannHypothesis.lean).
The challenge contains an intentional placeholder proof; Comparator checks the
actual solution theorem against that statement.

This repository's Comparator target is the Riemann zeta theorem. The imported
solution module also contains a Dirichlet L-function theorem, but that theorem
is not a target of this run.

## Verification

The Linux workflow runs [Comparator](https://github.com/leanprover/comparator)
with the unchanged upstream
[`QuasiRiemannHypothesis.json`](ComparatorChallenges/QuasiRiemannHypothesis.json).
It permits only the standard axioms `propext`, `Quot.sound`, and `Classical.choice`,
with no definition holes. Comparator compares the target statement, checks
dependencies and axioms, and replays solution declarations through Lean's kernel.
The configuration does not enable the optional Nanoda kernel.

The workflow installs the project's pinned Lean and Mathlib versions, builds
the pinned verification tools, prepares the Rellich and PrimeNumberTheoremAnd
dependencies with unchanged upstream compatibility patches, and downloads
Mathlib's trusted cache. It then
runs Comparator on a disposable Linux runner, after verifying that the process
is unprivileged, Unix sockets are blocked, the source is read-only inside the
real Landrun sandbox, and build output is writable. The source modules are not
compiled before Comparator starts.

The run emits `Comparator starting: QuasiRiemannHypothesis` immediately before
launching Comparator and records the UTC start time in
`verification/comparator-started.txt`. Logs, environment details, the start
timestamp, and a machine-readable result are uploaded as a workflow artifact.

The pinned tool revisions are:

| Tool | Revision |
| --- | --- |
| Comparator | `d03acab154d269c06e60e4de7e4cc85deebff94b` |
| lean4export | `076e8e57707e813375e8f9da8bf989799ace9680` |
| Landrun | `811cfff51ceaf3d9843708aa6d22e9b84ccac8b4` |

## Provenance

The repository copies the full transitive closure of local imports of the proof
entry point, the upstream challenge/configuration, and the Apache 2.0 license.
The upstream commit is `adc7f1241b42e322a6451854ab7e4b4c146bf78a`.
Lean is pinned to version 4.34.1 and Mathlib to the upstream revision. The
provenance manifest records source file hashes so the extraction can be checked
against the original commit.

The external Rellich and PrimeNumberTheoremAnd packages use the exact upstream
Git revisions and the unchanged upstream Lean 4.34.1 compatibility patches in
[`patches/`](patches/). Dependency preparation verifies each package's origin,
commit, and patch state, and runs before Lake resolves their configurations.

To prepare a Linux checkout locally, run:

```sh
bash scripts/setup-comparator.sh
bash scripts/prepare-dependencies.sh
lake exe cache get
sudo systemd-run --wait --pipe --collect \
  --uid="$(id -u)" --gid="$(id -g)" \
  --property=NoNewPrivileges=yes --property=CapabilityBoundingSet= \
  --property=SystemCallArchitectures=native \
  --property=RestrictAddressFamilies=~AF_UNIX \
  --setenv="PATH=$PATH" --setenv="HOME=$HOME" \
  --working-directory="$PWD" \
  /bin/bash "$PWD/scripts/run-comparator-service.sh"
```
