# CUAD attribution

This evaluation asset uses the Contract Understanding Atticus Dataset (CUAD)
v1, an English public contract benchmark.

- Repository: https://github.com/The-Atticus-Project/cuad
- Fixed repository commit: `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`
- Data archive Git blob SHA: `1ae94ff0a9b70b2e3b9b8d215737c8bfae460ddc`
- DOI: `10.5281/zenodo.4595826`
- License: CC BY 4.0
- Language: English

The archive SHA-256 is recorded in
`evaluation/datasets/manifests/cuad-v1.yaml` after download. The Git blob SHA
is an object identifier and is not a substitute for the downloaded archive
SHA-256.

The CUAD repository does not clearly provide a software license for its
repository code. This project does not copy `evaluate.py` or other repository
code. The span matching implementation in `evaluation/metrics/` is an
independent implementation of the public metric definition.

CUAD may have large-model pretraining contamination risk. It is evidence for
English clause/span extraction only. It cannot establish the product's six
Chinese contract categories, seven complete product fields, or Chinese
contract risk metrics.
