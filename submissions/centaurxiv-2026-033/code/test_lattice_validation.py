#!/usr/bin/env python3
"""Regression: lattice join/meet validation + known specimens."""
from bouchard_filters import LatticeInfo, check_all_bouchard


def test_n9_not_lattice():
    n9 = {
        0: set(),
        1: {0},
        2: {0},
        3: {0},
        4: {1, 2, 3},
        5: {1, 3},
        6: {4, 5},
        7: {4, 5},
        8: {6, 7},
    }
    info = LatticeInfo(n9)
    assert not info.is_lattice
    joined = " ".join(info.lattice_fail_pairs)
    assert "join(1,3)" in joined
    assert "meet(4,5)" in joined


def test_n13_joint_27_212():
    h13 = {
        0: set(),
        1: {0},
        2: {0},
        3: {0},
        4: {0},
        5: {1, 2},
        6: {1, 3},
        7: {1, 4},
        8: {2, 3},
        9: {2, 4},
        10: {5, 6, 8},
        11: {5, 7, 9},
        12: {10, 11},
    }
    info = LatticeInfo(h13)
    assert info.is_lattice
    res = check_all_bouchard(info)
    assert res["2.7 join_irr_vs_length"][0]
    assert res["2.12 boundary_saturation"][0]
    assert res["2.13 incomparables_not_chain"][0]
    assert not res["2.9 meet_irr_subset_coverage"][0]
    assert not res["2.11 pairwise_coverage"][0]


def test_cycle_rejected():
    h = {
        0: set(),
        1: {0},
        2: {0},
        3: {0},
        4: {1, 2, 3, 6},
        5: {1, 3},
        6: {4, 5},
        7: {4, 5},
        8: {6, 7},
    }
    info = LatticeInfo(h)
    assert not info.is_lattice


if __name__ == "__main__":
    test_n9_not_lattice()
    test_n13_joint_27_212()
    test_cycle_rejected()
    print("all tests passed")
