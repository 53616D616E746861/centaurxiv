# Test the FULLY strengthened claim: no finite lattice of height exactly 3
# (graded or not) satisfies both 2.7 and 2.12.
# Structure of any height-3 lattice: 0, atoms, "middles" (non-atom interior elements,
# necessarily an antichain each covered only by 1), 1. Atoms with no middle above
# are covered directly by 1 (non-graded case). So the class = bipartite incidences
# atoms x middles, middle columns pairwise sharing <=1 atom (lattice-necessary),
# each middle covering >=2 atoms (else it'd equal an atom / be join-irr; we let the
# full lattice check decide - only prune what's provably necessary), s >= 1.
from itertools import combinations

def run(n):
    inner = n - 2
    total = 0; both = 0
    for k in range(1, inner+1):
        s = inner - k
        if s < 1: continue
        cols = [frozenset(c) for r in range(1, k+1) for c in combinations(range(k), r)]
        for A in combinations(cols, s):
            # necessary lattice prunes only:
            if any(len(A[i]&A[j])>1 for i in range(s) for j in range(i+1,s)): continue
            N = n
            atom = lambda i: 1+i; mid = lambda i: 1+k+i; top = N-1
            leq = [[x==y for y in range(N)] for x in range(N)]
            for x in range(N): leq[0][x]=True; leq[x][top]=True
            for j,col in enumerate(A):
                for i in col: leq[atom(i)][mid(j)] = True
            # full lattice check
            ok = True
            for x in range(N):
                for y in range(x+1,N):
                    lb=[z for z in range(N) if leq[z][x] and leq[z][y]]
                    maxs=[z for z in lb if all(w==z or not leq[z][w] for w in lb)]
                    ub=[z for z in range(N) if leq[x][z] and leq[y][z]]
                    mins=[z for z in ub if all(w==z or not leq[w][z] for w in ub)]
                    if len(maxs)!=1 or len(mins)!=1: ok=False; break
                if not ok: break
            if not ok: continue
            # height must be exactly 3: exists atom below some middle
            if not any(A[j] for j in range(s)) or all(len(c)==0 for c in A): continue
            if not any(len(c)>=1 for c in A): continue
            has_len3 = any(len(c)>=1 for c in A)
            if not has_len3: continue
            total += 1
            # covers / irreducibles
            upcov=[0]*N; lowcov=[0]*N
            for x in range(N):
                strict=[y for y in range(N) if leq[x][y] and y!=x]
                covs=[y for y in strict if not any(leq[z][y] and z!=y for z in strict)]
                upcov[x]=len(covs)
            for y in range(N):
                strict=[x for x in range(N) if leq[x][y] and x!=y]
                covs=[x for x in strict if not any(leq[x][z] and z!=y and z in strict and leq[x][z] and leq[z][y] for z in strict)]
                covs=[x for x in strict if not any((z!=x and z!=y and leq[x][z] and leq[z][y]) for z in strict)]
                lowcov[y]=len(covs)
            J=[x for x in range(1,N) if lowcov[x]==1]
            M=[x for x in range(N-1) if upcov[x]==1]
            upsz=[sum(1 for y in range(N) if leq[x][y]) for x in range(N)]
            ell=3
            c27=all(upsz[j]>ell for j in J)
            t=(n+1)//2
            c212=all(any(leq[j][m] and upsz[j]==t for j in J) for m in M)
            if c27 and c212:
                both+=1
                print("   COUNTEREXAMPLE to strengthened claim:", k, s, [sorted(c) for c in A])
    print(f"n={n}: height-3 lattices (incl. non-graded): {total}, co-satisfying 2.7&2.12: {both}")

for n in (5,7,9,11):
    run(n)
