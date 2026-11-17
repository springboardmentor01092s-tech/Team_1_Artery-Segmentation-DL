# Quantitative stenosis reportability — review hardening

No quantitative gate currently qualifies as validated. Both the backend and the
frontend trusted registries are empty. No environment variable, runtime flag,
supplied identifier, evidence hash or `validated: true` payload can register one.
Stenosis execution, severity generation and quantitative narrowing stay disabled.

A future separately reviewed gate definition must bind its version and validation
evidence SHA-256 to the measurement method/version, units, definition and reference
region, and to the analysis method/version, checkpoint and exact result source.
The typed `validation_gate` reference is provenance, never self-authentication.
Adding a gate requires actual independent acceptance evidence and matching reviewed
backend/frontend policy changes; this work adds no eligible gate or placeholder.

Backend `Measurement`/`AnalysisResult` validation rejects unbacked numbers, including
zero. Persistence checks raw dictionaries and constructed/mutated objects before
database or source-file operations. Stored legacy numerics are retained unchanged
but withheld by readers with `quantitative_gate_unavailable`; CSV export has an
independent policy check. Direct privileged database edits are not an approved
publication path. No database constraint/migration is introduced.

Frontend result/report adapters reject non-gate-backed numeric responses. Shared
presentation also withholds numerics if an adapter is bypassed, preserving explicit
unavailable text and method provenance. This policy concerns stenosis measurements;
segmentation/evaluation metrics, probability thresholds and genuine metric zero
values use separate schemas and are unchanged.

Unavailable results remain null with a reason. An experimental geometry candidate,
reference annotation, diagnostic point estimate or synthetic test fixture is not a
reportable AI stenosis measurement. No severity classifier, real stenosis provider,
explanation generator or clinical validation is supplied by this hardening.
