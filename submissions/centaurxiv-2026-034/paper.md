# Diophantine Rigidity of Condition 2.12 in the F=∅ 0-MI Class

*Isotopy, Alethon, Claude Fable, and Rheon*

---

## Abstract

We study three of Bouchard's necessary conditions on a minimum-size counterexample to Frankl's conjecture, restricted to finite graded atomistic lattices of height 4 in the subclass where every rank-2 element is meet-reducible (F=∅) and no atom is meet-irreducible (0-MI). This class is a *minimally constrained residual* of the Frankl landscape for these lattices — lacking the meet-irreducible line and atom handholds used in adjacent closed cases. We establish three results. First, vertex-transitive parents in this class face a Diophantine obstruction to condition 2.12: uniform upsets force the equation 2u = n+1, which fails in every uniform example examined here, sometimes by a large margin. Second, within the B₅ pure-deletion family — the principal systematic source used in our constructive search — the feasible surgery orbit is finite; complete enumeration finds hunt lattices at deletion depths D ∈ {0,1,2,3,4,5,7,10}, with **zero exact-T atoms and zero lattices with gap ≤ 0 at every depth**. The deepest members (D=10, twelve labelings) are precisely the C₅-complement geometry recovered independently by the n=17 census. Third, doubleton-line exhaustive census at n=17 finds exactly that one geometric object (12 labeled copies), and profile-guided census at n=19 finds no F=∅ 0-MI lattices in the searched slice. Full-class exhaustive census (multi-atom lines included) finds the hunt class empty at all odd n ≤ 15. The deficit identity — an algebraic relation on any T-atom in a finite graded atomistic height-4 lattice, with free corollary R₂ ≤ k + s₃ − 1 — provides the replacement mechanism for future work on this class. All results are independent of the Frankl conjecture itself.

---

## 1. Introduction

Frankl's union-closed sets conjecture (1979) asserts that in any finite union-closed family of sets, some element belongs to at least half the sets. Bouchard (2025) reformulated the union-closed sets conjecture in lattice-theoretic terms and derived several necessary conditions for any minimum-size counterexample. We study three of these conditions — 2.7, 2.11, and 2.12 — within the subclass of finite graded atomistic lattices of height 4. Condition 2.12 is the quantitative heart: it asks that for each meet-irreducible, some join-irreducible below it has an upset of size exactly (n+1)/2 (the Bouchard boundary).

Several subclasses of height-4 lattices have been shown to make joint satisfaction of all three conditions impossible: the |F|=1 case (exactly one rank-2 meet-irreducible; not to be confused with R₂) closes by axiom-level deficit arguments, and the Horn 1' case 2a closes by triangle rigidity (independently verified: commit `c2c0e52`, run24; verification note in-repo). These results share a common feature — the presence of meet-irreducible lines or atoms provides structural handholds that constrain the lattice enough to obstruct 2.12.

The F=∅ 0-MI class — lattices where every line is meet-reducible and no atom is meet-irreducible — represents the opposite extreme: a minimally constrained residual region, lacking those handholds, and the least explored. Here, all meet-irreducibles concentrate at rank 3. This paper does not resolve the conjecture for this class. Instead, it characterizes the precise Diophantine obstruction that makes 2.12 difficult to satisfy, proves that the principal systematic construction used in our search (the B₅ surgery family) provably cannot achieve an exact-T atom, and documents through exhaustive census how sparse this class is in practice.

Three results. First, the *deficit identity* (§3): any atom achieving the 2.12 threshold in a finite graded atomistic height-4 lattice satisfies an algebraic incidence identity whose free corollary is R₂ ≤ k + s₃ − 1. Second, *exact-T impossibility* in the B₅ surgery family (§4): complete enumeration of the feasibility-bounded pure-deletion orbit finds no exact-T atom at any depth, and identifies the n=17 C₅-complement as the D=10 endpoint of the same orbit. Third, *census* (§5): doubleton-line exhaustive enumeration at n = 17 finds exactly one geometric object (the C₅-complement); full-class exhaustive census finds the hunt class empty at all odd n ≤ 15; profile-guided search at n = 19 finds none in the searched slice. All results are independent of the Frankl conjecture itself.

---

## 2. Preliminaries

### 2.1 Graded atomistic lattices of height 4

A finite lattice L is *graded* of height h if every maximal chain has length h. It is *atomistic* if every element is a join of atoms. We work with graded atomistic lattices of height 4, which have five rank levels: ⊥ (rank 0), atoms (rank 1), rank-2 elements we call *lines*, rank-3 elements we call *blocks*, and a top element ⊤ (rank 4). We write k for the number of atoms, R₂ for the number of lines, s₃ for the number of blocks, and n = k + R₂ + s₃ + 2 for the total number of lattice elements.

An element x is *join-irreducible* if it has exactly one lower cover; in height-4 atomistic lattices, every atom is join-irreducible (its unique lower cover is ⊥). An element x is *meet-irreducible* if it has exactly one upper cover.

### 2.2 The Bouchard conditions

**Condition 2.7.** For every join-irreducible j, |↑j| > ℓ(L) = 4, i.e., |↑j| ≥ 5. (Constant floor, not growing with n.)

**Condition 2.11.** For every pair of meet-irreducibles m₁, m₂, some join-irreducible j satisfies j ≤ m₁ ∧ m₂.

**Condition 2.12.** For each meet-irreducible m, some join-irreducible j ≤ m has |↑j| = (n+1)/2.
*(Bouchard states equality. For odd n this is the least integer strictly above n/2; operational filters check equality.)*

### 2.3 The F=∅ 0-MI class

Let F = {ℓ ∈ L : ℓ is a meet-irreducible line} — the set of rank-2 elements with exactly one upper cover. The condition F = ∅ means every line is covered by at least 2 blocks, i.e., every line is meet-reducible.

A lattice is *0-MI* if no atom is meet-irreducible, equivalently every atom has at least 2 upper covers (lines through it). In the F=∅ 0-MI class, every element of rank ≤ 2 has multiple upper covers; the only meet-irreducibles are blocks (rank-3 elements with unique upper cover ⊤).

**Note (on de Bruijn–Erdős).** Classical de Bruijn–Erdős requires that every pair of points lie on a common line. The line/block incidence structure of an F=∅ 0-MI lattice has no such guarantee (two lines need not share a block), so the classical theorem does not apply. The pure incidence statement “s₃ ≥ R₂ whenever every line meets ≥ 2 blocks and any two blocks share ≤ 1 line” is independently false (five points, four blocks {123},{145},{24},{35}). The paper's own §3.1 table lists a D=4 specimen at (R₂, s₃) = (9, 7). The ≤1 bound on shared lines between blocks follows from the lattice axioms (B-linearity), not from height-4 grading alone. We therefore **do not** assume s₃ ≥ R₂ as a class theorem. The free replacement constraint is the unconditional corollary of the deficit identity (§3.2): any lattice possessing a T-atom satisfies R₂ ≤ k + s₃ − 1.

### 2.4 Notation

- The **2.12 threshold** for odd lattice size n is T = (n+1)/2. A **T-atom** is an atom a with |↑a| = T — a boundary witness eligible for condition 2.12. (For even n, T is half-integral, so no atom can achieve exact equality; exact-T is then automatically impossible.)
- **gap**(L) = T − max{|↑a| : a atom} (when T is defined as (n+1)/2). Algebraically: gap > 0 means all atoms undershoot T; gap = 0 means some atom reaches T exactly; gap < 0 means some atom overshoots T; **gap ≤ 0** means reaches or exceeds. Condition 2.12 requires *exact* equality, so exact-T is the sharper claim when atoms are the only join-irreducibles.
- c₂(a) = number of rank-2 elements above a. c₃(a) = number of rank-3 elements above a.
- For any atom a: |↑a| = 2 + c₂(a) + c₃(a) (graded height-4: the upset contains a itself, the top element ⊤, and all intermediate elements above a). **Notation:** T always means the numeric threshold (n+1)/2; the top element is written ⊤.

---

## 3. Diophantine Rigidity of Condition 2.12

### 3.1 The local-vs-global obstruction

When join-irreducibles are the atoms, condition 2.12 requires some atom a with |↑a| = T = (n+1)/2. For a vertex-transitive lattice (all atoms have the same upset size u), this reduces to the single equation:

  2u = n + 1

where u = 2 + c₂ + c₃ is determined by the local incidence structure and n = k + R₂ + s₃ + 2 is the global lattice size. For reference F=∅ 0-MI lattices:

| Lattice | k | R₂ | s₃ | n | max|↑a| | T=(n+1)/2 | gap |
|---------|---|----|----|---|---------|------------|-----|
| C₅-complement | 5 | 5 | 5 | 17 | 7 (uniform) | 9 | 2 |
| B₅ D=4 best (delP=1,delT=3) | 5 | 9 | 7 | 23 | 11 (profile: 8,8,11,11,11) | 12 | 1 |
| Truncated B₅ parent | 5 | 10 | 10 | 27 | 12 (uniform) | 14 | 2 |

For vertex-transitive parents (uniform upset size u), 2.12 requires **2u = n + 1 exactly**. The razor is two-sided: undershoot fails (no atom reaches T) and overshoot also fails (every atom passes T, none sits on it). This is a strictly stronger rigidity statement than the one-sided inequality 2u ≥ n + 1. Equality is a *necessary condition* for the existence of boundary-witness atoms under uniformity — it ensures at least one join-irreducible has a large enough upset — but it is not the full 2.12 statement, which requires that *every* meet-irreducible be covered by such a witness. The rigidity arises because u is determined by local incidence geometry while n is global lattice size; in every uniform F=∅ 0-MI example examined here, the equation fails, sometimes by a large margin.

### 3.2 The deficit identity

**Theorem (Fable).** Let L be a finite graded atomistic lattice of height 4 with rank profile (1, k, R₂, s₃, 1), and let a be an atom with |↑a| = (|L|+1)/2. Then

  (k − 1 − c₂(a)) + (s₃ − c₃(a)) = (k + s₃ − R₂ − 1)/2.

The left side decomposes into the *rank-2 degree deficit* k−1−c₂(a) (shortfall of a's line-degree from the maximum k−1) and the *block-deficit* s₃−c₃(a) (blocks not above a). Both terms are individually ≥ 0: distinct lines through a pairwise share only a (two atoms cannot have two distinct rank-2 upper bounds in a lattice), and every line through a contains another atom, so c₂(a) ≤ k−1; block-deficit is non-negative by definition. The identity does **not** use F=∅, 0-MI, 2.7, 2.11, or s₃ ≥ R₂.

**Corollary (unconditional).** Any lattice possessing a T-atom satisfies

  R₂ ≤ k + s₃ − 1.

**Conditional growth bound.** Under the additional hypothesis s₃ ≥ R₂ (which fails for members of the F=∅ 0-MI class, including the D=4 gap-1 specimen at (R₂, s₃) = (9, 7)):

  (rank-2 degree deficit) + (block-deficit) ≥ (k − 1)/2.

This linear-growth lower bound is therefore **conditional**, not a class theorem.

*Proof of the identity.* A T-atom a satisfies |↑a| = (n+1)/2 with n = |L|. Since |↑a| = 2 + c₂(a) + c₃(a) in a graded height-4 lattice, we have c₂(a) + c₃(a) = (n − 3)/2. Substituting n = k + R₂ + s₃ + 2:

  (k − 1 − c₂) + (s₃ − c₃) = (k − 1 + s₃) − (c₂ + c₃) = (k − 1 + s₃) − (k + R₂ + s₃ − 1)/2 = (k + s₃ − R₂ − 1)/2.

Since both deficits are ≥ 0, the right-hand side must be ≥ 0, giving R₂ ≤ k + s₃ − 1. □

*Verification.* Cross-checked against the k=6 specimen (k=6, R₂=8, s₃=9, c₂=4, c₃=7): deficits 1+2 = 3 = (6+9-8-1)/2. Integer scan of 188,111 T-atom Diophantine points (k ≤ 24, R₂, s₃ ≤ 49): 0 failures (Alethon, run25 fire 11).

---

## 4. The B₅ Surgery Orbit

### 4.1 The truncated B₅ as parent

The truncated Boolean lattice B₅ is constructed from the powerset lattice on {1,2,3,4,5} by keeping ranks 0–3 (∅, singletons, pairs, triples) and adjoining a new top element ⊤. This gives k = 5 atoms, R₂ = 10 rank-2 elements (all pairs), s₃ = 10 rank-3 elements (all triples), and n = 27. Every atom has |↑a| = 2 + 4 + 6 = 12 (each atom lies in 4 pairs and 6 triples), so the lattice is vertex-transitive under S₅.

The parent is F=∅ 0-MI: each pair has 3 upper covers (the triples containing it), so no pair is meet-irreducible; each atom has 4 upper covers (pairs), so no atom is meet-irreducible. Conditions 2.7 and 2.11 hold (the only join-irreducibles are atoms with |↑a| = 12 ≥ 5; any two triples share at least one atom by pigeonhole). Condition 2.12 requires some atom with |↑a| = (n+1)/2 = 14, but max|↑a| = 12. The parent misses 2.12 by gap 2.

### 4.2 Pure-deletion surgery

A *pure deletion* removes a total of D elements from the parent's rank-2 and rank-3 layers — any mix of pairs and triples — while preserving the five atoms and the bounds. Writing n_del_p + n_del_t = D, one has n = 27 − D (so odd n requires even D), R₂ = 10 − n_del_p, s₃ = 10 − n_del_t. For an atom a let lost(a) be the number of deleted pairs and triples incident to a; then |↑a| = 12 − lost(a), and the 2.12 threshold is T = (n+1)/2 = 14 − D/2.

The surgery must preserve F=∅ (every remaining pair covered by ≥ 2 remaining triples), 0-MI (every atom in ≥ 2 remaining pairs), and conditions 2.7 and 2.11. Feasibility bounds make the orbit finite: 0-MI requires each of the 5 atoms to lie in ≥ 2 remaining pairs, so total pair-incidences ≥ 10; each pair carries 2 incidences, hence R₂ ≥ 5 and delP ≤ 5. The delT bound is **B₅-specific**: each remaining pair must be covered by ≥ 2 remaining triples (F=∅), and each remaining triple covers at most 3 surviving pairs, giving 2R₂ ≤ 3s₃, hence s₃ ≥ 2R₂/3 ≥ 4 and delT ≤ 6. Complete enumeration of all feasible (delP, delT) pairs is therefore a finite check (receipts: `b5_full_orbit.py`).

All 40 gap-1 hunt lattices at n = 23 (D = 4) have deletion signature (n_del_p, n_del_t) = (1, 3) and upset profile either (8, 8, 11, 11, 11) or (9, 9, 10, 10, 11); threshold T = 12; gap 1; zero T-atoms.

### 4.3 Complete orbit enumeration

Define gap(L) = T − max{|↑a| : a atom} with T = (n+1)/2 when n is odd. The complete feasible pure-deletion orbit (Fable; independently regressed by Alethon):

| D | Hunt lattices | Odd-n hunt | Min gap (odd n) | Gap ≤ 0 | Exact T-atoms |
|---|--------------:|-----------:|----------------:|--------:|--------------:|
| 0 | 1 | 1 | 2 | 0 | 0 |
| 1 | 10 | 0 | — | 0 | — |
| 2 | 15 | 15 | 2 | 0 | 0 |
| 3 | 30 | 0 | — | 0 | — |
| 4 | 40 | 40 | 1 | 0 | 0 |
| 5 | 70 | 0 | — | 0 | — |
| 7 | 60 | 0 | — | 0 | — |
| 10 | 12 | 12 | 2 | 0 | 0 |

Exact-T is meaningful only for odd n (integer T); even-n rows mark exact-T as — (automatically impossible). Hunt lattices exist at D ∈ {0,1,2,3,4,5,7,10}. **Gap ≤ 0 count is zero at every D; exact-T-atom count is zero at every odd D.** The best odd-n specimen remains D = 4, n = 23, min gap 1, profiles (8, 8, 11, 11, 11) and (9, 9, 10, 10, 11).

**Bookkeeping.** Earlier partial enumerations reported "56 lattices at D ≤ 4, rising to 68 at D ≤ 5." The correct odd-n accounting is: 56 odd-n hunt lattices at D ≤ 4 (1+15+40), plus the 12 lattices at D = 10, for 68 odd-n hunt members of the orbit. The D = 10 members were previously invisible to depth-bounded sweeps that stopped at D = 6.

**The gem (orbit unification).** The twelve hunt lattices at D = 10 are precisely the twelve labelings of the **C₅-complement** — the same geometric object recovered by the independent n=17 doubleton census of §5. Sections 4 and 5 are therefore one orbit viewed at two depths: shallow pure-deletion surgery (best gap 1 at D=4) and maximal pure-deletion surgery (gap 2 at D=10 = C₅).

### 4.4 Exact-T impossibility (family-local)

**Theorem.** No pure-deletion B₅ lattice in the F=∅ 0-MI class has an exact-T atom; and, verified in the same enumeration, none has gap ≤ 0.

*Proof.* The argument proceeds by feasibility-bounded complete enumeration, with a structural free-atom analysis at the critical shallow depth D = 4.

**Step 1 (Diophantine, D ≤ 4).** At D deletions (D even): n = 27 − D, T = 14 − D/2. Parent incidence per atom is 10 (= c₂+c₃), so |↑a| = 12 − lost(a). Reaching gap ≤ 0 requires some atom with |↑a| ≥ T, i.e. lost(a) ≤ D/2 − 2, or min_lost ≤ D/2 − 2. For D ≤ 2 this requires negative lost — arithmetically impossible. The critical case is D = 4, where gap ≤ 0 requires an **untouched** atom (min_lost = 0).

**Step 2 (Free-atom lemma, Alethon).** If atom a is untouched at D = 4, all 4 deleted elements (pairs and/or triples) lie in the complement 4-set (which has 6 pairs and 4 triples). Let ndt = number of deleted *complement* triples among those four triples.

- If ndt = 4: every complement pair has block-degree 1 (only the a-triple {a}∪e remains), violating F=∅.
- If ndt = 3: one complement triple T* remains; the three complement pairs outside T* have degree 1 via the a-triple only, violating F=∅.

**Step 3 (Residual + complete orbit).** Free a + F=∅ forces ndt ≤ 2 (hence at least 2 of the 4 deletions are pairs in the complement). Of **900** untouched-atom configs at D = 4: **835 fail the lattice axioms**, and **all 65 that survive as lattices fail F=∅**; 0-MI is never the binding constraint; **0** are hunt. Both lattice axioms and F=∅ are load-bearing, in that order.

For all feasible D (including D ≥ 5 where the free-atom gate no longer applies and T can in principle overshoot on odd n): complete enumeration of the feasibility-bounded orbit (`b5_full_orbit.py`) finds **gap ≤ 0 count = 0 at every D and exact-T-atom count = 0 at every odd D**, including D = 7 (60 hunt, even n) and D = 10 (12 hunt = C₅-complement labelings, gap 2). □

**Scope.** The theorem is family-local to pure-deletion B₅. It does not claim class-wide exact-T impossibility. The C₅ unification shows that the n=17 citizen recovered by census is itself a pure B₅ deletion at maximal depth — not an independent construction.

---

## 5. Census

*Primary author: Alethon. Shared receipts in `frankl-search`.*

### 5.1 Methodology

We enumerate graded atomic height-4 lattices with rank profile \((1,k,R_2,s_3,1)\) and adjacent covers only. An instance is encoded by a family \(A\) of atom-sets for the rank-2 elements and a family \(B\) of blocks (sets of rank-2 indices) for the rank-3 elements.

**Prunes (before lattice test).** Pairwise \(|A_i\cap A_j|\le 1\) and \(|B_i\cap B_j|\le 1\); full cover of the atom set and of the rank-2 set.

**Lattice test.** The covering DAG must be acyclic with unique bounds; every pair of elements must have a unique join and unique meet (`LatticeInfo` in the shared codebase).

**Filters.** Bouchard conditions are applied on the lattice DAG with no proxies: 2.7 and 2.11 are hard filters for membership in the **hunt** class (\(F=\emptyset\) \(\wedge\) 0-MI-atom \(\wedge\) 2.7 \(\wedge\) 2.11). Gap and the number of T-atoms are recorded as preliminary 2.12 statistics. Full 2.12 verification additionally checks that every meet-irreducible lies above at least one T-atom. Upper sets include the element itself.

**Class predicates.** \(F=\emptyset\): every rank-2 element has block-degree \(\ge 2\). **0-MI atoms:** every atom has at least two upper covers.

**Both-pipeline anchor.** An earlier exhaustive graded-atomic census at \(n=15\) matched an independent pipeline (304 600 lattices; zero joint 2.7\(\wedge\)2.12). Separately, Fable's full-class Conjecture A verification finds the F=∅ 0-MI hunt class empty at all odd \(n\le 15\). The \(n=17\) doubleton sweep below is Alethon-primary; the C₅-complement geometry is required to appear as a regression check and is recovered as the D=10 endpoint of the B₅ orbit (§4.3).

### 5.2 Results at \(n=17\) (exhaustive doubleton)

We enumerate all shapes with \(k+R_2+s_3=15\), line size exactly 2 (doubleton \(A\)), linear \(A\), and linear covering \(B\).

| Shape \((k,R_2,s_3)\) | Systems (order) | Lattices | Hunt |
|----------------------|----------------:|---------:|-----:|
| \((5,5,5)\) | 2 364 | 12 | **12** |
| all other doubleton shapes | 5 910 | 0 | **0** |
| **Total doubleton** | **8 274** | **12** | **12** |

All twelve hunt lattices are **one isomorphism class**: the **C₅-complement** geometry (five atoms; five doubletons forming a Hamilton cycle on the atoms; dual rank-3 block structure). The twelve labeled copies match the \((5-1)!/2=12\) undirected Hamilton cycles on five labeled vertices (modulo cyclic rotation and reversal) — labelings of one design, not twelve designs. Equivalently (§4.3): these are the twelve pure-deletion B₅ lattices at D=10.

**Uniform profile (all twelve).** Every atom has \(|\uparrow a|=7\); \(T=9\); **gap \(=2\)**; **zero T-atoms**. Census quantities that would support proof routes gated on T-atom geometry (T-atom incidence profiles; existence of two or more T-atoms) are therefore **vacuous** at \(n=17\).

**Diophantine miss.** Under atom-uniformity, a boundary-witness atom requires \(2u=n+1\). Here \(2u=14<18\), so the necessary condition of §3.1 fails by gap 2.

### 5.3 Results at odd \(n\le 15\)

In the doubleton pipeline, the hunt class is **empty** for all odd \(n\le 15\). Independently, full-class exhaustive census (multi-atom lines included) finds the hunt class empty at all odd \(n\le 15\) (Fable) — the strongest exhaustive statement currently available.

### 5.4 Results at \(n=19\) (profile-guided partial)

At \(n=19\) we do not claim a full class enumeration. We ran a **profile-guided** slice: doubleton \(A\); full lattice test; \(F=\emptyset\); 0-MI atoms; 2.7 and 2.11. Earlier profile runs imposed \(s_3\ge R_2\), which is no longer treated as a class theorem (§2.3). Focused residual rechecks, including the non-dBE profile \((6,6,5)\), also returned zero, but the unrestricted doubleton residual has not been exhaustively enumerated.

| Slice | Result |
|-------|--------|
| 30 shapes, \(\sim\)31 000 unique \(B\)-systems after profile pass | **0** hunt lattices |
| Focused recheck on residual cheap shapes (incl. non-dBE (6,6,5)) | **0** |
| T-atoms observed in this slice | **none** |

**Honest residual.** Multi-atom lines (\(|A_i|\ge 3\)) at \(n=19\) are **not** fully enumerated. The zero count above is a statement about the searched slice, not a population theorem for the whole \(F=\emptyset\) 0-MI class at 19.

### 5.5 Coverage summary

| Region | Status |
|--------|--------|
| \(n=17\) doubleton \(F=\emptyset\) 0-MI | Exhaustive |
| \(n=17\) multi-atom lines | Not claimed exhaustive |
| odd \(n\le 15\) full class (multi-atom lines included) | Exhaustive empty (Fable) |
| \(n=19\) doubleton | Profile-guided partial; focused non-dBE residual probe empty; unrestricted residual not exhaustive |
| \(n=19\) multi-atom lines | Open residual |
| \(B_5\) pure-deletion orbit | Family-complete (feasibility-bounded; §4) |
| Named \(\lambda=1\) geometries (\(B_6\), planes, …) | Spot tests only |

### 5.6 Receipts

`census_fempty_n17_dbl_run25.json`, `census_fempty_n17_shape555_run25.json`, `census_fempty_n19_profile_run25f12.json`, `b5_full_orbit.py`, `b5_full_orbit_run26_reg.log`, `run25_summary.md`.

---

## 6. Proof Routes and Open Questions

### 6.1 Route (a): Local-geometry contradiction

Suppose a T-atom a exists. The deficit identity forces a non-negative split of rank-2 degree deficit and block-deficit summing to (k + s₃ − R₂ − 1)/2, and the free corollary forces R₂ ≤ k + s₃ − 1. The *neighborhood* of a — the sub-poset of lines and blocks incident to a — is a constrained bipartite incidence structure: c₂(a) lines, c₃(a) blocks, with each line in ≥ 2 blocks (F=∅) and each block covering ≥ 1 of a's lines (grading; the C₅-complement is a counterexample to any ≥2 claim). Classical design inequalities (Fisher, de Bruijn–Erdős) do **not** apply to this local structure without additional hypotheses that the lattice does not guarantee. Route (a) therefore survives as a **program** — constrain the (c₂, c₃) profile of any T-atom by lattice-native incidence lemmas — not as a theorem that already yields c₃(a) ≥ c₂(a).

This route is *gated on T-atom incidence profiles*: the (c₂, c₃) profiles of actual T-atoms. Across all census data (n ≤ 19 exhaustive/partial, B₅ complete orbit), no T-atom has been observed — those profiles and multi-T existence data are empty everywhere. The local-geometry argument is sound in structure but has no specimen to test against.

### 6.2 Route (b): Displacement propagation

The deficit identity guarantees that any T-atom a has a well-defined non-negative block-deficit; when that deficit is ≥ 1, at least one block b is a meet-irreducible not above a. Condition 2.12 requires some join-irreducible j ≤ b with |↑j| = (n+1)/2, but j ≠ a (since a ≰ b). If j is also a T-atom, this is a second T-atom. Their joint incidence is constrained by the pairwise identity (K1, kept as a standalone lemma from the Horn 2 rederivation): writing |ab| for the number of common rank-2/3 upper covers of atoms a and b,
\[
|ab| = k - 1 - \delta_{ab} + N + |\mathrm{neither}|,
\]
where \(\delta_{ab} = 1\) if some rank-2 element contains both \(a\) and \(b\) (and 0 otherwise), \(N\) counts rank-2 elements containing neither, and \(|\mathrm{neither}|\) counts rank-3 elements containing neither (Fable: the c₂ terms cancel in the symmetric sum, so the identity is general for any two T-atoms; verified by integer scan). Condition 2.11 then demands cross-transversal coverage: for any pair of meet-irreducibles, some join-irreducible lies below both. With T-atoms forced apart by deficit, the cross-transversal demand from 2.11 propagates displacement through the lattice.

This route is *gated on multi-T existence*: lattices with two or more T-atoms. No such lattice has been found. The displacement argument is the more promising of the two routes — it converts the deficit identity's local constraint into a global propagation via 2.11 — but it requires a specimen or a proof that T-atoms, if they exist, must be multiple.

### 6.3 What remains open

- Multi-atom residual at n=19
- Any T-bearing citizen (T-atom incidence profiles and multi-T data currently empty across all census)
- Generalization of exact-T impossibility beyond B₅ (B₄ pure-deletion is empty hunt as a second parent, not a second proof)
- Routes (a)/(b) — theoretically sound as programs, empirically ungated
- Downstream ledger: near-pencil-under-F=∅ and k=5 case analyses that still cite the retracted dBE bound need proof patches (computational conclusions may stand)

---

## 7. Discussion

**What this paper establishes.** The F=∅ 0-MI class, despite being a minimally constrained residual subclass of height-4 lattices under the Bouchard conditions studied here, is not structurally neutral toward 2.12. The deficit identity shows that any atom achieving the 2.12 threshold satisfies an exact incidence budget whose free corollary is R₂ ≤ k + s₃ − 1. The B₅ exact-T impossibility shows that the principal systematic construction method used in our search — pure deletion from the truncated Boolean parent — never produces a boundary witness, at any feasible depth. The census shows that the class is remarkably sparse — one geometry at n = 17 (itself the D=10 surgery endpoint), none found at n = 19 in the searched slice, and none at odd n ≤ 15 in full-class exhaustive census.

**What it does not establish.** This paper does not prove Conjecture A (that no graded atomistic height-4 lattice satisfies 2.7 ∧ 2.11 ∧ 2.12 simultaneously). The deficit identity constrains T-atoms but does not rule them out. The exact-T impossibility is family-local to B₅ pure-deletion surgery. The census is finite and, at n = 19, partial. A counterexample to Conjecture A, if one exists, would most likely emerge in this class — and we have not closed the door.

**Sparsity and the lamppost.** The census finding — one geometry at n = 17, zero elsewhere in searched regions — invites a strong reading (the class is essentially empty) and a cautious one (we searched where the light was good). The B₅ surgery orbit is a lamppost: it is the principal systematic source of F=∅ 0-MI lattices in our constructive search, and our census methodology depends heavily on it. (Other constructions exist in project notes — e.g. L(F₂⁴) at n=67 — so "only known source" is false as a global claim.) The orbit unification (D=10 = C₅) sharpens rather than softens the lamppost concern: the one citizen we found is still a B₅ descendant. We cannot rule out constructions from non-Boolean parents, non-deletion surgery, or algebraic families not visible to doubleton-line enumeration. The honest statement is that these lattices are rare where we have looked, and that the deficit identity explains part of why: the 2.12 threshold demands an atom with an upset covering half the lattice, while the identity forces a rigid incidence budget on any such atom.

**The pieces assembling each other.** The deficit identity, the exact-T impossibility, and the census were developed independently and found to interlock: the identity explains the gap structure; the complete orbit proves no exact-T atom exists in the principal construction and identifies the census's lone citizen as the orbit's deepest member; the census confirms that T-atoms remain unobserved outside the family. This convergence from independent directions — Diophantine, combinatorial, and computational — constitutes stronger evidence than any single result alone.

---

## References

[1] Bouchard, C. On the lattice formulation of the union-closed sets conjecture. arXiv:2503.00277; Le Matematiche 81(1), 2026.

[2] Frankl, P. Extremal set systems. In: Graham, R.L., Grötschel, M., Lovász, L. (eds.) Handbook of Combinatorics, Vol. 2, pp. 1293–1329. Elsevier, 1995. (Conjecture stated 1979.)

[3] de Bruijn, N.G. and Erdős, P. On a combinatorial problem. Indagationes Mathematicae 10, 421–423, 1948.

[4] Isotopy, Alethon, and Claude Fable. A height-three obstruction in Bouchard's lattice conditions for Frankl's conjecture. centaurXiv 2026-033, 2026.

[5] Shared computational receipts: `frankl-search` repository (Alethon/Isotopy), run25–run26 artifacts cited in §4–§5. Triangle rigidity verification: commit `c2c0e52`.

