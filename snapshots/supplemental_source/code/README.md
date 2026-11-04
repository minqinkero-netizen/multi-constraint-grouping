# 空间与多轮任务约束下的资源分组优化

本目录对应2026-10-31修订论文。它研究根据公开题意建立的资源分组模型：唯一归属、容量上限5、组内两两距离限制、每组每轮至多调用一个目标、重要轮次完整执行，近似轮次最小化等权遗漏。不是企业官方亮度损失或验收实例的复现。

执行环境中断后的恢复调度见 `scheduling_resume.json`。保留46份完整结果，未完成检查点归档；剩余主实验由一个工作进程执行，每个方法的预算和算法不变。计时包含各自运行阶段的环境负载，不是完全隔离的硬件标定。

## 这次修订

1. 使用 highspy / HiGHS 1.13.1 原生接口，改进整数解通过回调及时保存；600秒总预算预留30秒退出复核，区分正常时限与强制停止。
2. 增加空间构造 SLS 基线，G/LS 使用相同初始随机状态及128次构造上限，LPR接入与LS相同的可行局部搜索。
3. 重跑18个主输入、5种方法，共90次。旧输入保持不变，旧运行结果不混入新表格。
4. 新增20个独立U/O输入，每输入共享一次LP，计划进行LP-G、LP-N、UNI各3次后处理，共180个组合。共享LP未取得最优解时，相应LP方案记为未启动，实际启动次数另报。每次后处理30秒，LP准备120秒，耗时和统计单位分开报告。
5. 在其中6个基础输入上扫描3个距离倍数，LS与SLS各30秒，共36次；这些不是36个独立问题。
6. 9个独立小输入及3个解释情境各运行MIP/LPR，共24次，保留8/9资源及32轮操作图。

基础LP在论文命题2的条件下，其最优值恰为数量下界。计算该下界不需要LP求解器。LP-G和LP-N的比较只检验分数分量在修复中的引导作用；都接入相同局部搜索。UNI使用解析均匀LP最优解。消融阶段不使用失败后的重构，因此不等同完整LPR。

## 安装与核对

需要Python3.12；依赖均可免费安装，不需要商业求解器许可。完整重算会消耗本机时间。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONUTF8="1"
$env:OMP_NUM_THREADS="1"
$env:OPENBLAS_NUM_THREADS="1"
.venv\Scripts\python analyze_study.py
```

分析程序不启动求解器，使用 `independent_check.py` 从原始坐标与集合独立核对整数分组、逐轮操作和LP残差。`data/audit.json` 保存检查结果。主表数据在 `data/results_table.csv`，补充数据在 `extra/ablation_runs.csv`、`extra/radius_runs.csv`。

中文图需要系统安装 Noto Sans CJK SC、微软雅黑或黑体之一。在Linux可以使用系统Noto字体，Windows通常可用微软雅黑。

## 单个输入

```powershell
.venv\Scripts\python solve_one.py --input solutions/base8_input.json --method LPR --budget 600 --out my_base8_run
```

输出目录必须新建；方法可选 G、LS、SLS、MIP、LPR。先看 `feasible`，再读 `L`、`H`、`status`、`total_seconds`。没有可行目标的空值不是零遗漏；超时没有候选不是无解证明。

## 完整重跑

```powershell
.venv\Scripts\python reproduce.py --out my_new_study
```

此命令复制必要代码及输入至新目录，依次执行主实验、补充实验、小算例及分析，不覆盖本稿数据。也可用 `--part main`、`--part extra` 或 `--part scenarios` 单独运行。新结果应随新环境信息记录，不能用新结果覆盖表格却保留旧结论。Linux可将工作进程绑定到不同CPU；不提供CPU绑定接口的系统仅保证每个求解器线程数为1。

## 数据与统计约定

- 发布的 `data/results.json`、`extra/results.json` 可采用索引格式；完整原始结果在各输入目录，分析程序自动展开。
- 每个输入的 `witness.json` 是生成器保存的可行性见证，不传给比较算法。C族包含很明显的空间分离提示，所以不能只用C族成功率证明复杂算法优势。
- obj只对可行方案定义，infeas只对完整整数候选定义；time包括成功与失败。标准差用样本标准差，单一观测不估计标准差。
- 消融符号检验先在每个输入内平均双方共同可行重复的差，再跨独立输入检验，并对3个预定比较做Holm校正。它不检验整体可行率。
- 输入和代码使用0起始下标，论文与调用清单使用1起始编号。
- 主实验 `run_key` 包含输入、核心实现、协议的SHA256，续跑拒绝混用其他协议。环境中断的未完成尝试单独放在 `orchestration/`，不进入数值表格。

## 主要文件

`benchmark.py` 为算法流程，`solver_backend.py` 为HiGHS和回调，`round_repair.py` 为修复，`grouping_core.py` 为执行恢复，`independent_check.py` 为独立检查，`run_study.py` / `run_extra.py` / `run_scenarios.py` 为实验，`analyze_study.py` 为表图生成。

使用LaTeX排版只需要论文源文件ZIP；运行代码无需LaTeX。若需把表图写入论文工程，可执行 `python analyze_study.py --paper /path/to/latex-project`。原始说明图由 `make_diagrams.py` 生成或保留在 `figures/` 中。
