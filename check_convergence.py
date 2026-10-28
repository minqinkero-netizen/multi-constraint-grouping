"""Transparent LP-based B&B trace for proof checks, NOT HiGHS MIP history.

The production solver remains solve_and_restore.py. This small reference
implementation uses the same P2 and starts with a previously checked feasible
solution. It illustrates bound closing, not search performance or a new method.
"""
from pathlib import Path
from itertools import product
import heapq
import json
import math
import platform
import numpy as np
import scipy
from scipy.optimize import linprog
from scipy.sparse import vstack
from solve_and_restore import build_p2, restore
from verify_reduction import direct

ROOT = Path(__file__).resolve().parent
TOL = 1e-7


def trace_case(d, initial_x=None):
    c, _, bounds, constraint, info = build_p2(d)
    A = constraint.A
    lo, hi = np.asarray(constraint.lb), np.asarray(constraint.ub)
    eq = np.isfinite(lo) & np.isfinite(hi) & (lo == hi)
    up = np.isfinite(hi) & ~eq
    down = np.isfinite(lo) & ~eq
    Aub = vstack([A[up, :], -A[down, :]], format='csc')
    bub = np.r_[hi[up], -lo[down]]
    Aeq, beq = A[eq, :], hi[eq]
    nx = info['nx']
    U = math.inf
    if initial_x is not None:
        _, _, _, audit = restore(d, initial_x)
        U = audit['L']
    initial_U = U if math.isfinite(U) else None
    incumbent = initial_x
    count_bound = sum(max(len(d['targets'][t]) - d['m'], 0)
                      for t in info['approximate_rounds'])
    nodes, history, queue = [], [], []
    split_count = 0

    def evaluate(fixed, parent=None):
        lower, upper = np.array(bounds.lb, copy=True), np.array(bounds.ub, copy=True)
        for j, value in fixed.items():
            lower[j] = upper[j] = value
        lp = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq,
                     bounds=list(zip(lower, upper)), method='highs',
                     options={'primal_feasibility_tolerance': 1e-9,
                              'dual_feasibility_tolerance': 1e-9, 'time_limit': 10.})
        nid = len(nodes)
        rec = {'id': nid, 'parent': parent, 'fixed': {str(k): v for k, v in fixed.items()},
               'depth': len(fixed), 'lp_status': int(lp.status),
               'lp_objective': float(lp.fun) if lp.fun is not None else None}
        nodes.append(rec)
        if lp.status == 2:
            rec['action'] = 'infeasible'
            return
        if lp.status != 0:
            raise RuntimeError('LP oracle did not complete: ' + lp.message)
        x = np.array(lp.x[:nx])
        rec['lp_x'] = x.reshape(d['n'], d['m']).tolist()
        heapq.heappush(queue, (float(lp.fun), nid, fixed, x))

    def snapshot(event):
        # A completed expansion leaves a full covering frontier. This history
        # records the ideal formula evaluated with floating-point LP results.
        B = max(count_bound, min([U] + [item[0] for item in queue]))
        history.append({'event': event, 'completed_splits': split_count,
                        'lp_calls': len(nodes), 'frontier_nodes': len(queue),
                        'lower_bound': float(B) if math.isfinite(B) else None,
                        'upper_bound': float(U) if math.isfinite(U) else None,
                        'gap': max(0., float(U-B)) if math.isfinite(U) else None})

    evaluate({})
    snapshot('root_lp')
    while queue:
        b, nid, fixed, x = heapq.heappop(queue)
        rec = nodes[nid]
        rec['incumbent_at_action'] = U if math.isfinite(U) else None
        if b >= U - TOL:
            rec['action'] = 'bound_prune_with_numerical_tolerance'
        else:
            fractional = np.flatnonzero(np.abs(x - np.rint(x)) > TOL)
            if len(fractional) == 0:
                _, _, _, audit = restore(d, x.reshape(d['n'], d['m']))
                q = audit['L']
                assert abs(q-b) <= 1e-6
                if q < U:
                    U = q
                    incumbent = np.rint(x).reshape(d['n'], d['m']).astype(int).tolist()
                rec['action'] = 'integer_lp_solution'
            else:
                j = int(fractional[0])
                assert j not in fixed
                rec.update(action='branch', branch_variable=j)
                split_count += 1
                evaluate({**fixed, j: 0}, nid)
                evaluate({**fixed, j: 1}, nid)
        snapshot(rec['action'])
        if len(nodes) > 5000:
            raise RuntimeError('reference check exceeded its safety node limit')
    if not math.isfinite(U):
        outcome = 'infeasible'
    else:
        outcome = 'verified_reference_optimum'
        assert incumbent is not None
    # Exhaustive, independent semantic evaluation for THESE SMALL inputs only.
    feasible = []
    for labels in product(range(d['m']), repeat=d['n']):
        value = direct(d, labels)
        if value is not None:
            feasible.append((np.eye(d['m'], dtype=int)[list(labels)].reshape(-1), value))
    actual_best = min((v for _, v in feasible), default=None)
    assert (actual_best is None) == (outcome == 'infeasible')
    if actual_best is not None:
        assert U == actual_best
        for h in history:
            assert h['lower_bound'] <= actual_best + 1e-6
            assert h['upper_bound'] >= actual_best
        for a, b in zip(history, history[1:]):
            assert b['lower_bound'] >= a['lower_bound'] - 1e-6
            assert b['upper_bound'] <= a['upper_bound']
    for node in nodes:
        compatible = [v for x, v in feasible
                      if all(int(x[int(j)]) == value for j, value in node['fixed'].items())]
        if node['lp_status'] == 2:
            assert not compatible
        elif compatible:
            assert node['lp_objective'] <= min(compatible) + 1e-6
            if node.get('action') == 'bound_prune_with_numerical_tolerance':
                assert min(compatible) >= node['incumbent_at_action']
    return {'outcome': outcome, 'initial_upper_bound': initial_U,
            'elementary_count_lower_bound': count_bound,
            'best_objective': actual_best, 'feasible_labeled_assignments': len(feasible),
            'lp_calls': len(nodes), 'split_count': split_count,
            'max_explicit_binary_depth': max(n['depth'] for n in nodes),
            'nodes': nodes, 'history': history, 'incumbent_x': incumbent,
            'all_node_bounds_checked_against_exhaustive_integer_completions': True}


def main():
    old = json.loads((ROOT/'recovery_checks.json').read_text())
    specs = [old['cases'][0], old['cases'][-1]]
    cases = []
    for case in specs:
        result = trace_case(case['instance'], case['result']['x'])
        cases.append({'name': case['name'], 'instance': case['instance'], 'result': result})
    tight = old['tight_distance_case']['instance']
    cases.append({'name': 'tight_distance', 'instance': tight, 'result': trace_case(tight)})
    # Check integer gap conditions exactly over representative integer bounds.
    # These checks never certify a raw floating-point solver bound by ceiling it.
    from fractions import Fraction
    gap_checks = []
    for U, B in [(6, Fraction(5)), (6, Fraction(11, 2)), (6, Fraction(6)), (0, Fraction(0))]:
        allowed = list(range(math.ceil(B), U+1))
        certified = (U-B < 1)
        assert certified == (allowed == [U])
        gap_checks.append({'U': U, 'exact_B': str(B), 'allowed_integer_values': allowed,
                           'strict_gap_under_one_certifies_optimal': certified})
    output = {'purpose': 'independent simplified B&B proof-check trace, NOT production HiGHS MIP iteration history',
              'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__},
              'numerical_prune_tolerance': TOL, 'cases': cases, 'exact_gap_checks': gap_checks}
    (ROOT/'convergence_checks.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps([{'name':c['name'], **{k:c['result'][k] for k in
                      ['outcome','lp_calls','split_count','max_explicit_binary_depth','best_objective','feasible_labeled_assignments']}}
                      for c in cases],ensure_ascii=False))


if __name__ == '__main__':
    main()
