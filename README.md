# 最终实验版本：90 次主实验与补充实验

固定分支：`final-experiments-20261103`。保留 main 及全部历史提交。此次仅恢复、校验和同步既有记录，没有重新运行优化器。

## 统计口径

18 个输入 × G、LS、SLS、MIP、LPR 共 90 次主实验，预算 600 秒。可行数依次为 14、14、12、17、12（分母均为 18）。目标统计仅使用可行结果；失败和强制停止仍保留在可行率分母中，不能解释为实例不可行。

补充实验单独保存：20 次共享 LP、180 次后处理、36 次距离扫描、24 次小规模/说明情境运行。共享 LP 是每输入一次，LP-G/LP-N 共享该解，UNI 不调用共享 LP。LP-G、LP-N、UNI 可行数为 55/60、56/60、56/60。小规模/情境运行预算为 600 秒。

## 目录与原检查点

- `snapshots/supplemental_source/`：原始检查点的全部 758 个文件，加最终哈希源本身；逐字节保留。环境依赖中的 Linux 二进制只用于历史环境追溯，Windows 应安装依赖。
- `snapshots/supplemental_source/SUPPLEMENTAL_FINAL_SHA256.json`：原始 758 项大小和 SHA-256，文件自身哈希为 `a428bcb8ae92ea486943ec8f49a1f91c7edee522174ab67cba07ec4a82326479`。
- `code/`：与原检查点相同的可运行目录，包括输入、逐次结果、配置、说明情境、独立检查器与分析脚本。
- `data/results.json`、`data/summary.json`、`data/results_table.csv`：主实验原始汇总、统计、逐例 CSV；均与 `code/data/` 对应文件一致。
- `data/extra/`：20 个共享 LP、180 次后处理和 36 次距离扫描；`data/scenario_data/`：24 次小规模/说明情境运行。
- `experiments/latest_complete_experiment_package_20261102.zip`：经完整 CRC 校验的原始完整实验快照。
- `reports/revalidation_main_20261104.json`、`reports/revalidation_all_20261104.json`：此次独立复核；`reports/recomputed_summary_20261104.json`：重新核算的统计。

## 只核验已保存结果

Python 依赖见 `code/requirements.txt`。原运行环境及 CPU 调度历史见原协议、scheduling_resume.json 和快照报告。安装依赖后，在仓库根目录运行：

```text
python -m pip install -r code/requirements.txt
python verify_saved.py
```

该命令先核对 758 项原哈希，再在临时副本中独立检查已保存的整数解、LP、输入见证、聚合与逐次记录，重新计算统计；不会运行任何优化器，也不覆盖原记录。绘图和重新求解是不同操作。若要生成新运行，应使用 `code/reproduce.py --out 新目录`，不覆盖本批数据。

论文附录 B/D 和验证清单应固定引用实际已推送 commit，不使用 main 或旧版 72 次/4 方法作为本次实验版本。
