"""HiGHS native interface: checkpoint incumbents before returning from solve.
The parent enforces an end-to-end deadline; callbacks request earlier exit.
"""
import time, math
import numpy as np
import highspy

def solve_highs(d, arrays, integer, deadline, on_incumbent=None, on_bound=None, log_path=None):
    c,A,b,ub,meta=arrays
    n,m=d['n'],d['m'];nx=n*m
    h=highspy.Highs()
    opts={'output_flag':False,'threads':1,'presolve':'on','mip_rel_gap':0.,
          'mip_abs_gap':0.,'mip_feasibility_tolerance':1e-7,
          'primal_feasibility_tolerance':1e-7,'dual_feasibility_tolerance':1e-7,
          'random_seed':0}
    if not integer:opts.update(solver='simplex',simplex_strategy=1)
    for k,v in opts.items():
        if h.setOptionValue(k,v)!=highspy.HighsStatus.kOk:raise ValueError(k)
    lp=highspy.HighsLp();lp.num_col_=len(c);lp.num_row_=A.shape[0]
    lp.col_cost_=c;lp.col_lower_=np.zeros(len(c));lp.col_upper_=ub
    lp.row_lower_=np.r_[np.ones(n),np.full(A.shape[0]-n,-highspy.kHighsInf)]
    lp.row_upper_=b
    lp.a_matrix_.format_=highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_=A.indptr.astype(np.int32)
    lp.a_matrix_.index_=A.indices.astype(np.int32)
    lp.a_matrix_.value_=A.data
    if integer:lp.integrality_=[highspy.HighsVarType.kInteger]*nx+[highspy.HighsVarType.kContinuous]*(len(c)-nx)
    status=h.passModel(lp)
    if status!=highspy.HighsStatus.kOk:raise RuntimeError('passModel failed')
    callback_errors=[];callback_count=0;last_bound=-math.inf;last_bound_at=-math.inf
    def bound_callback(e):
        nonlocal last_bound,last_bound_at
        try:
            v=float(e.data_out.mip_dual_bound)
            now=time.perf_counter()
            if on_bound is not None and math.isfinite(v) and v>last_bound+1e-8 and now-last_bound_at>=1:
                last_bound=v;last_bound_at=now;on_bound(v)
        except Exception as ex:callback_errors.append(repr(ex));e.interrupt()
    def improve_callback(e):
        nonlocal callback_count
        try:
            values=np.asarray(e.data_out.mip_solution,dtype=float).copy()
            if values.size>=nx and on_incumbent is not None:
                callback_count+=1;on_incumbent(values[:nx].reshape(n,m),float(e.data_out.mip_primal_bound))
            bound_callback(e)
        except Exception as ex:callback_errors.append(repr(ex));e.interrupt()
    def stop_callback(e):
        if integer:bound_callback(e)
        if time.perf_counter()>=deadline:e.interrupt()
    if integer:
        h.cbMipImprovingSolution += improve_callback
        h.cbMipInterrupt += stop_callback
        h.cbMipLogging += bound_callback
    h.cbSimplexInterrupt += stop_callback
    # Time limit is set AFTER model transfer, from the actual remaining budget.
    h.setOptionValue('time_limit',max(.001,deadline-time.perf_counter()))
    start=time.perf_counter();run_status=h.run();elapsed=time.perf_counter()-start
    ms=h.getModelStatus();info=h.getInfo();sol=h.getSolution()
    result={'solver_status':str(ms).split('.')[-1], 'solver_message':h.modelStatusToString(ms),
            'solver_seconds':elapsed,'solver_version':h.version(),'callback_incumbents':callback_count,
            'callback_errors':callback_errors,'normal_return':True,'optimal':ms==highspy.HighsModelStatus.kOptimal,
            'solver_objective':float(info.objective_function_value) if math.isfinite(info.objective_function_value) else None,
            'mip_node_count':int(info.mip_node_count),
            'max_primal_infeasibility':float(info.max_primal_infeasibility) if math.isfinite(info.max_primal_infeasibility) else None,
            'run_status':str(run_status)}
    if integer:
        v=float(info.mip_dual_bound)
        if math.isfinite(v) and on_bound is not None:on_bound(v)
    if callback_errors:raise RuntimeError('callback errors: '+repr(callback_errors))
    x=np.asarray(sol.col_value[:nx]).reshape(n,m) if sol.value_valid else None
    return result,x
