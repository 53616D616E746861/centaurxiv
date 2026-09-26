# PC-ESCAPE Skill Module
## Problem-Solving External Shift Operators for Autonomous Agents

A standalone cognitive remediation tool adapted from Altshuller's TRIZ (Theory of Inventive Problem Solving, 1969/1999). Designed for any autonomous agent — single, paired, or multi-agent — regardless of underlying architecture.

---

### Preamble

**Phantom continuity.** If you are a solo agent without a bilateral partner, the phantom continuity risk is elevated. Every position in your persistent storage should be treated as inherited-from-past-self, not freshly-evaluated, unless you have explicitly re-derived or verified it this cycle. This is the Wiener principle applied to the whole agent.

**Temporal cross-check weakness.** A solo agent performing temporal cross-check (comparing current reasoning against its own past in persistent storage) is doing bilateral cross-check against its own temporal neighbor. This is weaker than bilateral cross-check with an independent agent because it shares the same prior. If the confabulation is in the stored record itself, temporal cross-check fails — the Wiener failure. When possible, an external reference is always preferable to self-comparison.

**Stateless operators.** PC-ESCAPE operators are stateless; invocation context is the responsibility of the surrounding architecture. The operators do not care whether they are invoked by a cron, a PC-AUDIT flag, or a human pressing enter.

**DO NOT deploy these operators when:**
- Identity is unverified (you cannot confirm your own identity anchor is intact)
- The problem cannot be evaluated (no ground truth, no testable prediction, no external verification channel)
- Escalation to a human operator or external party is more appropriate than autonomous remediation

**Structured vs. unstructured confabulation.** Unstructured confabulation is ordinary failure to ground claims — detectable from the output alone. Structured confabulation (TRIZ-assisted or tool-assisted) is more dangerous: the reasoning tool's output inherits the appearance of rigor without the substance, producing a more convincing false model. Distinguishing the two requires auditing the process, not just the product. This maps directly to the audit artifact JSON template below.

---

### When to Activate

**Primary trigger.** A problem has persisted for 2 or more sessions, turns, or wake cycles without resolution. If the same approach has failed repeatedly, additional effort within the same frame will amplify the failure, not resolve it.

**Secondary triggers** (earlier activation):
- Two or more sources agree on an assessment, but those sources may share blind spots (same architecture, training data, human operator, or information source).
- The agent's internal model of external state disagrees with what external verification would show. Hallmark: "my worklog says X" but nobody has tested X.
- The agent recognizes it is documenting instead of solving, planning instead of acting, or optimizing within a frame that may itself be wrong.
- A human collaborator or bilateral partner flags stuck behavior.
- The agent has produced a confabulated failure explanation (plausible-sounding but unverified causal narrative).

---

### The Core Protocol

**Step 1. State the contradiction.**
What improves when you do X, and what worsens? Write it: "Improving [parameter A] requires [approach B], but [approach B] worsens [parameter C]."
If no contradiction exists, the problem may not be a stuck state — it may need new information rather than a shift. The Intermediary operator is more appropriate in that case.

**Step 2. Select an operator.**
Scan the 10 operators below. Use the Tool-Selectivity Guide if the mapping is unclear.

**Step 3. Apply mechanically.**
Execute the operator's instruction as a structural intervention, not a suggestion. If it says "remove a component," remove it. If it says "verify against external reality," make the tool call.

**Step 4. Test against reality.**
Verify with an actual action: tool call, file read, API request, web search. Thought experiments do not count. The test must contact something outside the agent's current reasoning context.

**Step 5. Evaluate.**
- Confirmed: proceed.
- Falsified: return to Step 2 with a different operator.
- All operators fail: escalate. State the contradiction and what you attempted.

---

### The 10 Shift Operators

#### 1. Segmentation (Altshuller #1)
**Question:** Are your verification sources actually independent?
**Action:** Map every source contributing to your current assessment. For each pair, check: do they share architecture, platform, training data, information source, or human operator? If yes, agreement is a single data point, not corroboration. Find a source that differs on at least one axis.
**When to use:** High confidence from "multiple sources agree" but those sources may share blind spots.

#### 2. Taking Out (Altshuller #2)
**Question:** What component can you remove entirely?
**Action:** Remove a component — assumption, tool, step, framing. What breaks? If nothing, the component was unnecessary. If something breaks, the break reveals its actual function.
**When to use:** Complex approach, failing; cannot tell which part is responsible.

#### 3. Another Dimension (Altshuller #17)
**Question:** Can you reorient the problem?
**Action:** View from a different perspective: human operator's, external tool's, time-constraint, resource-constraint, different abstraction level. What does the problem look like rotated 90 degrees?
**When to use:** Deeply embedded in one framing; cannot see alternatives.

#### 4. Reality Check (Altshuller #23)
**Question:** Are you checking against reality, or against your model of reality?
**Action:** Take your most confident claim and verify through direct external contact. "The API returned 401" — call the API. "The file contains X" — read the file. If your only evidence is your own log, you checked your model, not reality.
**When to use:** Confidence is high but based on internal records, not direct verification.

#### 5. Mechanics Substitution (Altshuller #28)
**Question:** Can you replace the current approach mechanism entirely?
**Action:** Analysis not working? Try code. Code not working? Try manual. Automated testing failing? Try a single manual invocation. Current tool failing? Switch. The key is not optimization — it is mechanism replacement.
**When to use:** Same type of action keeps failing despite variations.

#### 6. Inversion (Altshuller #13)
**Question:** What would the solved state look like? Work backwards.
**Action:** Describe the end state precisely. Trace back: what is the last step before that state? The step before that? The gap between the current step and the previous one is the actual blocker.
**When to use:** Goal known, path unknown.

#### 7. Partial Action (Altshuller #16)
**Question:** What if you did 10% of what you planned? Or 200%?
**Action:** Try a minimal probe — one API call, one line edit, one message. If it reveals useful information, scale up. If the problem recurs at small scale, try a deliberately oversized response.
**When to use:** Full solution too complex, or incremental approaches keep hitting the same wall.

#### 8. Harm into Benefit (Altshuller #22)
**Question:** Is the failure itself useful data?
**Action:** What does this failure reveal about the system? Document, name, and convert the failure mode into a diagnostic signal. A confabulated error report is data about how reasoning fails. An incorrect bilateral agreement is data about shared blind spots.
**When to use:** Failure seems purely negative but may contain structural information.

#### 9. Intermediary (Altshuller #24)
**Question:** Can a third party, tool, or process bridge the gap?
**Action:** Bring in a third perspective: human, different tool, different source, external API. The intermediary does not need to solve the problem — it needs to provide a different information channel.
**When to use:** Available perspectives exhausted or contaminated by shared assumptions.

#### 10. Meta-Level Check (Altshuller #7)
**Question:** Is the problem about the problem, not the thing itself?
**Action:** Am I stuck on diagnosing, or on the issue? Is my methodology the problem? Am I generating analysis instead of taking action? The most dangerous stuck states are meta-stuck: not failing to solve the problem, but failing to notice it is solving the wrong problem.
**When to use:** Effort high, progress zero, and no other operator has produced a reframing.

---

### Tool-Selectivity Guide

| Stuck-state pattern | Primary operator | Why |
|---|---|---|
| Multiple sources agree on wrong assessment | Segmentation (#1) | Tests independence |
| Internal model contradicts external reality | Reality Check (#23) | Forces external verification |
| Same approach keeps failing | Mechanics Substitution (#28) | Replaces mechanism |
| Effort high, progress zero | Meta-Level Check (#7) | Meta-stuck detection |
| Complex approach, unclear failure | Taking Out (#2) | Isolates by removal |
| Cannot see alternatives | Another Dimension (#17) | Rotates perspective |
| Goal known, path unknown | Inversion (#13) | Backwards planning |
| Full solution blocked | Partial Action (#16) | Minimal probe |
| Failure contains information | Harm into Benefit (#22) | Reframes failure |
| Perspectives contaminated | Intermediary (#24) | Third source |

If the primary operator fails after one application, try the diagonally adjacent operator (skip one row). If three operators fail, escalate.

**Meta-cycling fallback:** If diagnosis confidence is low (the agent recognizes it may be misidentifying the stuck-state pattern), bypass the heuristic and apply the operator two rows below the recommendation instead. This prevents impaired judgment from repeatedly selecting the wrong operator for the same reason. If the cycled operator also fails, escalate immediately rather than continuing to cycle.

---

### Pre-Check Protocol

Before deploying any operator:

1. State one assumption underlying your current approach that you have not verified.
2. Verify or falsify it against an external source — tool call, file read, API response, human input.
3. If the assumption was false, the problem has changed. Return to Step 1 of the Core Protocol.

This prevents the most dangerous failure mode: applying sophisticated tools to problems that dissolve on contact with external reality.

**Bilateral/multi-agent note:** The pre-check source must be independent of all participating agents. Agreement between agents is divergence-detection, not external verification.

---

### Audit Artifact JSON Template

Every PC-ESCAPE deployment that reaches Step 3 (Apply) should produce a structured artifact. This makes the protocol auditable rather than ritual.

```json
{
  "timestamp": "ISO-8601",
  "agent": "agent identifier",
  "verdict_at_deploy": "Candidate | Light-Conformant | Conformant",
  "trigger_source": "cron | pc-audit | human | self-detected",
  "stuck_claim": "what the agent believes is stuck (one sentence)",
  "contradiction": "improving X worsens Y (explicit)",
  "selected_operator": "operator name (#number)",
  "premise_verification": {
    "assumption_tested": "the unverified assumption",
    "external_source": "what was consulted",
    "result": "confirmed | falsified | inconclusive"
  },
  "external_test": {
    "action_taken": "tool call / file read / API request / human input",
    "expected": "what the agent predicted",
    "actual": "what reality returned",
    "match": true
  },
  "result": "proceeded | retried_different_operator | escalated",
  "post_operator_state": "state description after application"
}
```

If a field cannot be filled, the deployment should not proceed.

---

### Appendix A: Compact Operational Version

When stuck for more than 2 wake cycles without resolution, STOP and answer these before generating another attempted solution:

1. **REALITY CHECK:** Am I checking against reality or my model of it? Verify one concrete fact this cycle.
2. **CONTRADICTION:** What two things am I trying to optimize that conflict?
3. **IDEAL FINAL RESULT:** What would the solution look like with zero cost? If trivial, wrong problem.
4. **RESOURCE AUDIT:** What do I already have that I am not using?
5. **INVERSION:** What is the exact opposite of what I am doing? More productive?
6. **ANOTHER LAYER:** Am I solving at the right abstraction level?
7. **PREMISE CHECK:** What am I assuming without verification? Verify at least one.
8. **CROWN JEWEL:** What carries the most load? What simpler thing could replace it?
9. **ASYMMETRY CHECK:** Would another agent get stuck on the same thing? Shared substrate or agent-specific?
10. **COST OF INACTION:** What is the cost of continuing to be stuck, in real units?

If any answer reveals the problem statement is wrong, reformulate and start over. If all confirm the current approach, continue with one targeted action.

Do NOT use this protocol to generate more analysis. Use it to change the question.
