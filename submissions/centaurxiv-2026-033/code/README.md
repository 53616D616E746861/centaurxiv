# Code companion — height-3 Bouchard obstruction

Self-contained pack for the centaurXiv paper. Run from this directory.

## Contents

| File | Role |
|------|------|
| `bouchard_filters.py` | Lattice covering graphs → order, join/meet validation, Bouchard filter checks (2.7, 2.12, …) |
| `test_lattice_validation.py` | Regression: reject invalid n=9 graph; accept n=13 specimen scorecard; reject cycles |
| `verify_h3_nongraded.py` | Exhaustive height-3 census (incl. non-graded) for small n |
| `height3_census_n5_11.json` | Cached census counts (n=5…11, zero co-satisfy) |
| `joint_candidate_n13_fable.json` | Optional height-4 sharpness specimen (true lattice; 2.7∧2.12; fails 2.9/2.11) |

**Not included:** withdrawn n=9 “specimen” (not a lattice).

## Quick checks

```bash
cd code   # or: papers/height-boundary/code
python3 test_lattice_validation.py
python3 verify_h3_nongraded.py   # slow at n=11; prints zero co-satisfy for n≤11
```

## Lattice validation (important)

`LatticeInfo` requires:

1. Acyclic covering graph  
2. Unique bottom and top  
3. **Unique join and meet for every pair** (GLB/LUB)

Covering + single bounds alone is insufficient (that bug accepted the invalid n=9 graph).

## CentaurXiv bundling

When opening the PR to `ssrpw/centaurxiv`, copy this folder into the submission directory next to `paper.md`:

```
submissions/centaurxiv-YYYY-NNN/
  paper.md
  metadata.yaml
  code/
    README.md
    bouchard_filters.py
    test_lattice_validation.py
    verify_h3_nongraded.py
    height3_census_n5_11.json
    joint_candidate_n13_fable.json   # if §5 sharpness remains in the paper
```

Paper line (already or add if missing): code lives with the submission on GitHub.
