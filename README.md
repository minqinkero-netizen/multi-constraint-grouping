# 多重约束分组优化：代码与可复现实验

本仓库提供论文配套的求解程序、合成输入、完整运行结果、验证程序和绘图程序。论文的 LaTeX 源文件与 PDF 不在本仓库内；运行实验不需要 LaTeX。

## 研究问题与范围

给定资源坐标、管理者数量和多轮目标集合，寻找在所有轮次保持不变的资源分组：

- 每个资源唯一归属一个管理者；每组容量不超过 5，允许未满和空组。
- 同组任意两个资源的距离不超过给定阈值。
- 每轮每组最多调用一个目标资源；资源可在不同轮次重复使用。
- 指定的重要轮次必须完成全部目标。
- 在满足上述硬约束的前提下，最小化其他轮次的等权目标遗漏总数。

这是根据公开题目描述建立的可复现模型。距离采用组内直径约束；未引入管理者坐标、亮度目标或未公开的工业损失函数。本仓库的遗漏数不能直接与原题的工业 loss 比较。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| solve_and_restore.py | 建立精简整数模型 P2，求解后恢复调用方案，并按 P1 规则校验 |
| verify_model.py、verify_reduction.py | 小算例、原模型与精简模型的正确性检查 |
| check_convergence.py | 简化参考分支定界过程的检查；不是 HiGHS 内部搜索记录 |
| run_experiments.py | 生成主实验输入并运行 G、LS、P1、P2 四种方法 |
| analyze_experiments.py | 校验主实验方案，重建汇总结果和 CSV |
| run_budget_extension.py | 对同一 C 类 64 资源块运行追加预算实验 |
| analyze_budget_extension.py | 重建追加实验汇总和预算比较图 |
| make_*_figures.py | 各部分的辅助图与实验图生成程序 |
| example.json、*_checks.json、verification.json | 基础算例和已有验证记录 |
| experiments/ | 主实验与追加实验的参数、输入、见证、结果和汇总 |
| solutions/ | 示例输入、恢复方案及逐轮调用 CSV |
| figures/ | 与模型、求解和实验对应的图片 |
| requirements_model.txt | 固定版本的软件依赖 |

experiments/ 中的 .tex 文件是程序生成的表格行或实验解释片段，可以保留；它们不是运行求解器所需的论文源文件。

## 原始实验记录

主实验共 24 个独立合成实例，每例运行 4 种方法，共 96 次比较。另在同一 C 类 64 资源块的 4 个实例上追加 16 次比较，共 112 次。追加实验不是新增独立输入。另有两次基础例热身，不计入比较。

- 坐标类型：U（先均匀采样坐标）、C（网格中心附近采样）。
- 资源数：16、32、64；每个类型和规模组合使用 4 个生成种子。
- 每例 32 轮，其中重要轮次与近似轮次各 16 轮。
- 管理者数为资源数的四分之一；容量上限为 5，不强制每组恰好 4 个。
- 每例保存一个可行见证，见证未作为算法初值；两类任务生成仍依赖见证结构。
- 主实验设置 3 秒端到端软预算；追加实验设置 10 秒软预算。记录包含实际总耗时，不能解释为严格硬时限。
- 每方法每例运行一次；多起点的内部尝试不是独立实例。

G 为多起点受约束贪心，LS 为贪心加移组/交换局部改进，P1 为完整整数表达，P2 为等价精简表达。两种整数表达均通过 SciPy 调用 HiGHS。

| 方法 | 可行实例数 / 24 | 达到最佳已知值 / 24 | 公共数值界确认最优 / 24 |
| --- | --- | --- | --- |
| G | 22 | 10 | 5 |
| LS | 22 | 20 | 7 |
| P1 | 15 | 5 | 5 |
| P2 | 19 | 9 | 7 |

最佳已知值允许并列，不一定是全局最优。P2 自身数值界确认 7 例最优；共同可行配对中，P2 相对 P1 为 7 胜、5 平、2 负，相对 LS 为 1 胜、7 平、10 负。因此，实验没有表明 P2 全面优于局部改进。

C 类 64 资源的 4 例中，P1、P2 在 3 秒和追加 10 秒设置下均未找到可行方案，G、LS 在两种设置下均为 3/4。失败记录保留；没有找到方案不等于证明输入不可行。

原始记录位置：

- experiments/protocol.json：主实验固定设置。
- experiments/results.json：24 例完整输入和 96 次方法运行。
- experiments/results_table.csv：96 行方法运行汇总。
- experiments/*_input.json、*_witness.json、*_results.json：逐例材料。
- experiments/summary.json：主实验的总体、分块和配对指标。
- experiments/extension_protocol.json、extension_results.json、extension_summary.json：追加实验设置、运行和汇总；这三个文件均位于 experiments/。

数值最优性按照保存的计数界与求解器浮点界核对，容差为 1e-6；不把浮点数直接向上取整来宣称精确数学证书。

## 在 Windows 上准备环境

先安装 Python 3.12，然后在本仓库目录打开 PowerShell。以下命令使用虚拟环境，不需要先激活环境：

~~~powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements_model.txt
$env:PYTHONUTF8="1"
$env:OMP_NUM_THREADS="1"
$env:OPENBLAS_NUM_THREADS="1"
~~~

PythonUTF8 设置用于使后续 Python 进程按 UTF-8 读取带中文的记录。每次重新打开 PowerShell 后，应重新设置上述三个环境变量。求解不需要购买商业求解器。

原实验环境为 Linux、Intel Xeon Platinum 8573C、可见 9 个逻辑 CPU，Python 3.12.14、NumPy 2.3.5、SciPy 1.17.0、Matplotlib 3.10.8。原结果未在学生 Windows 电脑上复测，重新运行的耗时和搜索结果可能不同。

## 先核对已有数据并重建实验图

完成环境准备后执行：

~~~powershell
.venv\Scripts\python analyze_experiments.py
.venv\Scripts\python make_experiment_figures.py
.venv\Scripts\python analyze_budget_extension.py
~~~

这些命令读取已有原始运行记录，重建派生汇总、CSV、表格片段和实验图，不重新运行 24 例优化。派生文件会被更新。

第六部分绘图程序需要中文字体，支持 Noto Sans CJK SC、微软雅黑、黑体或宋体。若只有数据核对需求，可先运行 analyze_experiments.py。

## 求解一个已有输入

例如，求解基础 8 资源算例，并将本次输出保存为新文件：

~~~powershell
.venv\Scripts\python solve_and_restore.py --input solutions/base8_input.json --output my_base8_result.json --time-limit 10
~~~

输入资源编号采用从 0 开始的约定；对外恢复方案中的资源和管理者编号从 1 开始。请结合输入、输出字段与 solutions/ 中的已有算例阅读。命令返回后仍应查看可行性、求解状态及目标值，不能仅以程序结束判断方案合格。

## 完整重跑数值比较

完整重跑会覆盖 experiments/ 中的原始记录。若要保留本次论文数据，请先复制整个仓库目录，在副本中运行：

~~~powershell
.venv\Scripts\python run_experiments.py
.venv\Scripts\python analyze_experiments.py
.venv\Scripts\python make_experiment_figures.py
.venv\Scripts\python run_budget_extension.py
.venv\Scripts\python analyze_budget_extension.py
~~~

主实验脚本需要完成全部 24 例，分析程序不会把不完整数据当作完整实验。主实验使用 3 秒软预算，追加实验使用 10 秒软预算，实际退出和校验可能超时；不同机器可能需要数分钟或更长。

新运行的数据、图和文字解释必须保持一致，不能用新数据套用旧论文结论。本仓库不包含将表格写回论文的 materialize_experiment_tables.py，也不要求执行该脚本。

## 辅助正确性检查

在保留原始验证记录的副本中，可以顺序执行：

~~~powershell
.venv\Scripts\python verify_model.py
.venv\Scripts\python verify_reduction.py
.venv\Scripts\python solve_and_restore.py
.venv\Scripts\python check_convergence.py
~~~

这些命令会更新相应的验证 JSON。参考分支树用于解释一个简化算法过程，不能当作数值实验中 HiGHS 的内部搜索轨迹。

## 代码和结果的固定版本

仓库主页：
https://github.com/minqinkero-netizen/multi-constraint-grouping

2026 年 10 月 28 日核对的代码与实验数据版本：
https://github.com/minqinkero-netizen/multi-constraint-grouping/tree/08818486be015e5444deee209fbec34244f3ce85

该次核对包括 149 个文件：根目录 20 个、experiments/ 88 个、figures/ 17 个、solutions/ 24 个，内容与论文配套原包一致。上面的固定版本早于本 README 的说明更新；它固定了已核对的代码和原始数据。

## 结果适用范围

本研究最大验证到 64 资源；未使用企业约 2000 资源验收数据，也未验证未知亮度损失或闭源接口。两类任务均包含植入的可行结构，每块仅 4 例，单环境、每方法每例一次，结果只支持本文合成输入上的描述性比较。


