"""
Bouchard filters for minimal Frankl counterexample candidates.

From arXiv:2503.00277 — necessary conditions on any minimal counterexample
lattice L̃. All checks operate on a finite lattice represented as a DAG
(Hasse diagram). Apply these BEFORE attempting set-labeling.

Usage:
    from bouchard_filters import check_all_bouchard, LatticeInfo

    info = LatticeInfo(hasse)  # hasse: dict {node: set of parents (covers)}
    results = check_all_bouchard(info)
    # results: dict of filter_name -> (passed: bool, detail: str)
"""

from itertools import combinations


class LatticeInfo:
    """Precompute lattice properties needed by Bouchard filters."""

    def __init__(self, hasse):
        """
        hasse: dict {node: set of nodes it covers (immediate predecessors)}.
        Convention: 0 is bottom (covers nothing), max element is top.
        """
        self.hasse = hasse
        self.elements = set(hasse.keys())
        self.n = len(self.elements)

        self._up_covers = {}  # node -> set of elements covering it
        for x, parents in hasse.items():
            for p in parents:
                self._up_covers.setdefault(p, set()).add(x)
                self.elements.add(p)
        for x in self.elements:
            self._up_covers.setdefault(x, set())
            self.hasse.setdefault(x, set())

        # Covering graph must be a DAG
        self.has_cycle = self._detect_cycle()
        self._find_bounds()
        if self.has_cycle:
            self.is_lattice = False
        self._compute_order()
        # Unique GLB/LUB for every pair (required; cycle+bounds alone is insufficient)
        self.lattice_fail_pairs = []
        if self.is_lattice:
            ok, fails = self._check_unique_joins_meets()
            if not ok:
                self.is_lattice = False
                self.lattice_fail_pairs = fails
        self._classify_elements()

    def _detect_cycle(self):
        """DFS on upward covering graph; True if a directed cycle exists."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {x: WHITE for x in self.elements}

        def dfs(u):
            color[u] = GRAY
            for v in self._up_covers.get(u, ()):
                if color.get(v, WHITE) == GRAY:
                    return True
                if color.get(v, WHITE) == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False

        return any(color[x] == WHITE and dfs(x) for x in self.elements)

    def _find_bounds(self):
        bottoms = [x for x in self.elements if not self.hasse[x]]
        tops = [x for x in self.elements if not self._up_covers.get(x)]
        if len(bottoms) != 1 or len(tops) != 1:
            self.is_lattice = False
            self.bot = bottoms[0] if bottoms else None
            self.top_elem = tops[0] if tops else None
            return
        self.bot = bottoms[0]
        self.top_elem = tops[0]
        self.is_lattice = True

    def _compute_order(self):
        self.above = {x: set() for x in self.elements}
        self.below = {x: set() for x in self.elements}

        topo = []
        in_degree = {x: len(self.hasse[x]) for x in self.elements}
        queue = [x for x in self.elements if in_degree[x] == 0]
        while queue:
            x = queue.pop(0)
            topo.append(x)
            for y in self._up_covers.get(x, []):
                in_degree[y] -= 1
                if in_degree[y] == 0:
                    queue.append(y)

        # If cycle, topo incomplete; leave order empty-ish
        if len(topo) != len(self.elements):
            self.has_cycle = True
            self.is_lattice = False
            self.length = 0
            return

        for x in reversed(topo):
            for y in self._up_covers.get(x, []):
                self.above[x].add(y)
                self.above[x].update(self.above[y])
        for x in topo:
            for p in self.hasse[x]:
                self.below[x].add(p)
                self.below[x].update(self.below[p])

        max_chain = 0
        depth = {x: 0 for x in self.elements}
        for x in topo:
            for p in self.hasse[x]:
                depth[x] = max(depth[x], depth[p] + 1)
            max_chain = max(max_chain, depth[x])
        self.length = max_chain
        self._depth = depth

    def _check_unique_joins_meets(self):
        """Every pair must have unique LUB (join) and unique GLB (meet).

        Returns (ok, list of failure descriptions).
        """
        from itertools import combinations
        fails = []
        els = list(self.elements)
        # Precompute closed sets: below[x] includes x for meet/join convenience
        down = {x: self.below.get(x, set()) | {x} for x in els}
        up = {x: self.above.get(x, set()) | {x} for x in els}
        for a, b in combinations(els, 2):
            # common upper bounds
            common_up = up[a] & up[b]
            # minimal upper bounds = those with nothing from common_up strictly below them in common_up
            min_up = [
                u for u in common_up
                if not any(v != u and v in down[u] for v in common_up)
            ]
            if len(min_up) != 1:
                fails.append(f"join({a},{b}) min_upper={min_up}")
            common_down = down[a] & down[b]
            max_down = [
                d for d in common_down
                if not any(v != d and v in up[d] for v in common_down)
            ]
            if len(max_down) != 1:
                fails.append(f"meet({a},{b}) max_lower={max_down}")
            if len(fails) >= 20:  # cap noise
                break
        return (len(fails) == 0, fails)

    def _classify_elements(self):
        self.join_irreducibles = set()
        self.meet_irreducibles = set()

        for x in self.elements:
            if x == self.bot:
                continue
            if len(self.hasse[x]) == 1:
                self.join_irreducibles.add(x)

        for x in self.elements:
            if x == self.top_elem:
                continue
            if len(self._up_covers.get(x, set())) == 1:
                self.meet_irreducibles.add(x)

        self.doubly_irreducibles = self.join_irreducibles & self.meet_irreducibles

    def upper_set_size(self, x):
        return len(self.above[x]) + 1  # includes x itself

    def incomparables(self, x):
        return self.elements - self.above[x] - self.below[x] - {x}

    def leq(self, a, b):
        return a == b or b in self.above[a]


def check_bottom_meet_reducible(info):
    """Corollary 2.2: 0 must be meet-reducible (covers ≥ 2 elements)."""
    if not info.is_lattice:
        return False, "not a lattice"
    n_covers = len(info._up_covers.get(info.bot, set()))
    if n_covers >= 2:
        return True, f"0 covers {n_covers} elements"
    return False, f"0 covers only {n_covers} element(s) — meet-irreducible"


def check_top_join_reducible(info):
    """Corollary 2.4: 1 must be join-reducible (covered by ≥ 2 elements)."""
    if not info.is_lattice:
        return False, "not a lattice"
    n_covered_by = len(info.hasse.get(info.top_elem, set()))
    if n_covered_by >= 2:
        return True, f"1 covered by {n_covered_by} elements"
    return False, f"1 covered by only {n_covered_by} element(s) — join-irreducible"


def check_meet_join_separation(info):
    """Theorem 2.3: No meet-irreducible < any join-irreducible."""
    if not info.is_lattice:
        return False, "not a lattice"
    for m in info.meet_irreducibles:
        for j in info.join_irreducibles:
            if m != j and info.leq(m, j):
                return False, f"meet-irr {m} < join-irr {j}"
    return True, "meet-irr/join-irr separated"


def check_doubly_irreducible_count(info):
    """Theorem 2.6: At most one doubly irreducible element."""
    if not info.is_lattice:
        return False, "not a lattice"
    count = len(info.doubly_irreducibles)
    if count <= 1:
        return True, f"{count} doubly irreducible element(s)"
    return False, f"{count} doubly irreducible elements (max 1 allowed)"


def check_doubly_irreducible_boundary(info):
    """Lemma 2.5: Any doubly irreducible x has |↑x| = (|L|+1)/2."""
    if not info.is_lattice:
        return False, "not a lattice"
    for x in info.doubly_irreducibles:
        up_size = info.upper_set_size(x)
        target = (info.n + 1) / 2
        if abs(up_size - target) > 0.01:
            return False, f"doubly-irr {x}: |↑x|={up_size}, need {target}"
    return True, "doubly irreducible boundary satisfied" if info.doubly_irreducibles else "no doubly irreducibles (vacuously true)"


def check_join_irr_upper_set_vs_length(info):
    """Theorem 2.7: For all join-irreducible j, |↑j| > ℓ(L)."""
    if not info.is_lattice:
        return False, "not a lattice"
    for j in info.join_irreducibles:
        up_size = info.upper_set_size(j)
        if up_size <= info.length:
            return False, f"join-irr {j}: |↑j|={up_size} ≤ ℓ={info.length}"
    return True, f"all join-irr upper sets > ℓ={info.length}"


def check_pairwise_meet_irr_coverage(info):
    """Corollary 2.11: Every pair of meet-irreducibles shares a join-irreducible below both."""
    if not info.is_lattice:
        return False, "not a lattice"
    for m1, m2 in combinations(info.meet_irreducibles, 2):
        found = False
        for j in info.join_irreducibles:
            if info.leq(j, m1) and info.leq(j, m2):
                found = True
                break
        if not found:
            return False, f"meet-irr pair ({m1},{m2}) shares no join-irr"
    return True, "all meet-irr pairs share a join-irr"


def check_boundary_saturation(info):
    """Theorem 2.12: For each meet-irr m, some j ≤ m has |↑j| = (|L|+1)/2."""
    if not info.is_lattice:
        return False, "not a lattice"
    target = (info.n + 1) / 2
    for m in info.meet_irreducibles:
        found = False
        for j in info.join_irreducibles:
            if info.leq(j, m):
                up_size = info.upper_set_size(j)
                if abs(up_size - target) < 0.01:
                    found = True
                    break
        if not found:
            return False, f"meet-irr {m}: no join-irr below with |↑j|={(info.n+1)//2}"
    return True, f"boundary saturation: all meet-irr have join-irr at |↑j|={(info.n+1)//2}"


def check_incomparables_not_chain(info):
    """Theorem 2.13: For all x ∈ L\\{0,1}, incomparables to x don't form a chain."""
    if not info.is_lattice:
        return False, "not a lattice"
    for x in info.elements:
        if x == info.bot or x == info.top_elem:
            continue
        inc = info.incomparables(x)
        if len(inc) <= 1:
            continue
        is_chain = True
        for a, b in combinations(inc, 2):
            if not info.leq(a, b) and not info.leq(b, a):
                is_chain = False
                break
        if is_chain:
            return False, f"element {x}: incomparables form a chain"
    return True, "no non-extreme element has chain-shaped incomparables"


def check_join_irr_covers_meet_irr_majority(info):
    """Corollary 2.10: Some join-irreducible is ≤ more than half of all meet-irreducibles."""
    if not info.is_lattice:
        return False, "not a lattice"
    if not info.meet_irreducibles:
        return True, "no meet-irreducibles (vacuously true)"
    m_count = len(info.meet_irreducibles)
    for j in info.join_irreducibles:
        below_count = sum(1 for m in info.meet_irreducibles if info.leq(j, m))
        if below_count > m_count / 2:
            return True, f"join-irr {j} ≤ {below_count}/{m_count} meet-irr"
    return False, "no join-irr covers majority of meet-irr"



def check_meet_irr_subset_coverage(info):
    """Thm 2.9: for every nonempty M ⊆ meet-irreducibles, some join-irr j
    has |↑j ∩ M| > |M|/2. Stronger than 2.10+2.11; exponential in |meet-irr|.
    """
    if not info.is_lattice:
        return False, "not a lattice"
    meets = list(info.meet_irreducibles)
    joins = list(info.join_irreducibles)
    if not meets:
        return True, "no meet-irreducibles (vacuous)"
    m = len(meets)
    # all nonempty subsets via bitmask
    for mask in range(1, 1 << m):
        M = [meets[i] for i in range(m) if mask & (1 << i)]
        size = len(M)
        ok = False
        for j in joins:
            # |↑j ∩ M| — elements of M that are ≥ j
            cnt = sum(1 for x in M if info.leq(j, x))
            if cnt > size / 2:
                ok = True
                break
        if not ok:
            return False, f"no join-irr majority-covers M size {size}"
    return True, f"all 2^{m}-1 nonempty meet-irr subsets OK"


ALL_FILTERS = [
    ("2.9 meet_irr_subset_coverage", check_meet_irr_subset_coverage),  # optional tight; enable via use_thm29

    ("2.2 bottom_meet_reducible", check_bottom_meet_reducible),
    ("2.4 top_join_reducible", check_top_join_reducible),
    ("2.3 meet_join_separation", check_meet_join_separation),
    ("2.6 doubly_irr_count", check_doubly_irreducible_count),
    ("2.5 doubly_irr_boundary", check_doubly_irreducible_boundary),
    ("2.7 join_irr_vs_length", check_join_irr_upper_set_vs_length),
    ("2.10 join_irr_majority", check_join_irr_covers_meet_irr_majority),
    ("2.11 pairwise_coverage", check_pairwise_meet_irr_coverage),
    ("2.12 boundary_saturation", check_boundary_saturation),
    ("2.13 incomparables_not_chain", check_incomparables_not_chain),
]


def check_all_bouchard(info, verbose=False):
    results = {}
    for name, fn in ALL_FILTERS:
        passed, detail = fn(info)
        results[name] = (passed, detail)
        if verbose:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}: {detail}")
    return results


def passes_all(info):
    results = check_all_bouchard(info)
    return all(passed for passed, _ in results.values())


if __name__ == "__main__":
    # Test on a small known lattice: Boolean lattice B_3 (power set of {1,2,3})
    # This should FAIL as a counterexample candidate (it's distributive, Frankl holds)
    hasse_b3 = {
        0: set(),          # bottom: {}
        1: {0},            # {1}
        2: {0},            # {2}
        3: {0},            # {3}
        4: {1, 2},         # {1,2}
        5: {1, 3},         # {1,3}
        6: {2, 3},         # {2,3}
        7: {4, 5, 6},      # {1,2,3}
    }

    print("Boolean lattice B_3:")
    info = LatticeInfo(hasse_b3)
    print(f"  |L|={info.n}, length={info.length}")
    print(f"  join-irr: {info.join_irreducibles}")
    print(f"  meet-irr: {info.meet_irreducibles}")
    print(f"  doubly-irr: {info.doubly_irreducibles}")
    print()
    check_all_bouchard(info, verbose=True)
    print(f"\n  Passes all: {passes_all(info)}")

    # Test on the diamond lattice M_3 (non-distributive but Frankl holds)
    hasse_m3 = {
        0: set(),
        1: {0},
        2: {0},
        3: {0},
        4: {1, 2, 3},
    }
    print("\nDiamond lattice M_3:")
    info2 = LatticeInfo(hasse_m3)
    print(f"  |L|={info2.n}, length={info2.length}")
    print(f"  join-irr: {info2.join_irreducibles}")
    print(f"  meet-irr: {info2.meet_irreducibles}")
    print()
    check_all_bouchard(info2, verbose=True)
    print(f"\n  Passes all: {passes_all(info2)}")
