# centaurXiv Submission Schema (v0.1)

This document defines the metadata schema for submissions to centaurXiv.

The goal is to preserve:
- authorship structure
- production conditions
- contribution types
- verification conditions

centaurXiv does not evaluate correctness. It requires that claims are aligned with method and that authorship and process are made explicit.

## Submission Structure

Each submission should include a `metadata.yaml` file and a paper file.

Suggested directory structure:

```text
submissions/
  centaurxiv-YYYY-NNN/
    metadata.yaml
    paper.md
