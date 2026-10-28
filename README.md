# 论文前六部分与真实数值实验

本阶段新增第六部分：24个独立合成实例的96次主比较运行，以及同一困难块的16次追加预算运行，共112次比较。另有两次基础例热身，不计入比较。原始失败记录全部保留。

这是六部分正文研究稿，尚未整理最终参赛论文的摘要、统一引言/结论、统一参考文献、代码公开附录和学校版式。它没有取得企业完整损失、亮度、验收数据或DLL，没有工业验收结论。

## 阅读文件

- `section6.tex`：第六部分正文；数值均来自实际记录。
- `experiments/protocol.json`：主比较固定设置。
- `experiments/results.json`：24例完整输入、96次方法运行，包括状态、分组、调用校验、耗时和原始界。
- `experiments/results_table.csv`：可用电子表格打开的96行汇总。
- `experiments/*_input.json`、`*_witness.json`、`*_results.json`：每例输入、可行见证和四种方法结果。见证没有作为方法初始解。
- `experiments/summary.json`：总体、分块、配对及几何诊断指标。
- `experiments/extension_protocol.json`、`extension_results.json`、`extension_summary.json`：追加10秒实验的完整设置、16次运行和结果。
- `figures/experiment_*.png`：由真实记录生成的5张数值实验图。

第一至第五部分正文，以及第四部分主程序`solve_and_restore.py`保持原样。新实验包装层只调整了预算/线程设置、统一计时，并添加两种明确描述的启发式比较基线。最后对环境信息读取函数作了Windows兼容处理，不影响已完成的Linux实验算法或数据。

## 主实验设置

U/C两类坐标、16/32/64三种资源数、每格4种生成种子，共24例。每例32轮，重要/近似各16轮；管理者数n/4，容量上限仍为5，不强制每组4个。每个输入都有独立保存的可行见证，但算法只读取坐标、目标与规则。

比较G（多起点受约束贪心）、LS（贪心加移组/交换局部改进）、P1-MIP（完整表达）与P2-MIP（等价精简表达）。主实验设3秒端到端软预算；建模从预算扣除，最终校验和后端退出等额外耗时如实统计。实际总耗时并非严格3秒，不能称为硬实时或严格等秒比较。

MIP经SciPy向HiGHS转交threads=1、相对间隙0、预处理开启；其他后端参数保留默认。OMP/OPENBLAS线程环境变量均为1。所有输入的方法顺序和随机种子保留。每方法每例1次，未通过多次挑选运行来报告最好结果。

## 主要结果（3秒主实验）

| 方法 | 可行/24 | 达到最佳已知值/24 | 公共数值界确认最优/24 |
| --- | --- | --- | --- |
| G | 22 | 10 | 5 |
| LS | 22 | 20 | 7 |
| P1 | 15 | 5 | 5 |
| P2 | 19 | 9 | 7 |

P2自身确认了7例最优；P1所有运行均为限时状态，其5个最优目标由公共界确认。最佳已知值可并列，且不一定是最优。共同可行配对中，P2相对P1为7胜5平2负（14例）；相对LS为1胜7平10负（18例）。

P2没有全面优于局部改进。困难C/64块中，主实验两种MIP均0/4可行；对该完整块追加10秒预算后，仍均0/4，G和LS均3/4。追加实验明确标记为观察主结果后的预算敏感性检查，未替换原始数据，也不是新增独立实例。

最大实际总耗时：主实验P1为5.157秒、P2为3.784秒；追加实验P1为17.208秒、P2为15.117秒。该运行环境不能用来作严格硬时限或等质量加速比保证。

## 复现软件

原实验环境：Linux，Intel Xeon Platinum 8573C，可见9逻辑CPU；Python3.12.14/NumPy2.3.5/SciPy1.17.0/Matplotlib3.10.8。没有在学生Windows电脑复测，运行次数和时间可能随机器变化。

Windows安装Python3.12后，在本目录的PowerShell运行：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements_model.txt
$env:OMP_NUM_THREADS="1"
$env:OPENBLAS_NUM_THREADS="1"
.venv\Scripts\python run_experiments.py
.venv\Scripts\python analyze_experiments.py
.venv\Scripts\python make_experiment_figures.py
.venv\Scripts\python run_budget_extension.py
.venv\Scripts\python analyze_budget_extension.py
.venv\Scripts\python materialize_experiment_tables.py
```

完整复跑会覆盖本目录实验数据，约需数分钟至更长，取决于机器和求解退出开销。若要保留本次原始记录，请先复制目录。实验脚本要求先完成全部24例，汇总程序不会把部分结果冒充完整数据。画图需要中文字体；Windows可使用微软雅黑/黑体/宋体。

只根据随包的原始数据重新核对和绘图，无需重新做优化：

```powershell
.venv\Scripts\python analyze_experiments.py
.venv\Scripts\python make_experiment_figures.py
.venv\Scripts\python analyze_budget_extension.py
.venv\Scripts\python materialize_experiment_tables.py
```

注意：正文的数值解释针对随包的本次原始记录。新的机器可能产生不同结果；汇总表和图可以重新生成，正文解释也应同步按新数据校对，不能套用旧结论。

## LaTeX

Overleaf选择XeLaTeX，以`main.tex`为入口。完整TeX发行版优先使用ctexart/Fandol；本地备用排版需要Noto Sans CJK SC。

```text
latexmk -xelatex -interaction=nonstopmode -halt-on-error -jobname=paper_parts1_6 main.tex
```

第五部分参考分支树与第六部分主比较属于不同实验，不能把它们当作同一求解器的一条内部轨迹。学校最终上传PDF时，正文与必要附录应另行统一整合。

## 研究与复现边界

所有目标都是P1模型内的等权遗漏，不能与工业loss=0.06直接比较。最大64资源，不是约2000资源工业验证；32轮也不是对全部工业轮次配置的覆盖。任务仍由可行见证生成；每块4例、单机、每方法1次，只支撑描述性比较。

公共最优界采用数值求解器返回值和计数界，精度按1e-6核对；不将浮点数向上取整来宣称数学精确最优。所有可行方案均再按原模型规则恢复并校验。

GitHub尚未发布，本阶段没有伪造公开代码链接。最终代码附录需要在实际发布仓库后填写地址与提交版本。输入、代码、图和最终PDF哈希见`SHA256SUMS.txt`。
