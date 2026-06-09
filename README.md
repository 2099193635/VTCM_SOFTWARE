# VTCM_PYTHON：LNN-PINO 正逆一体化框架规划

## 1. 项目目标
本项目在现有车辆-轨道耦合动力学仿真基础上，构建 **LNN + PINO** 的神经动力学框架，支持：

- **正向问题（Forward）**：由不平顺/缺陷激励预测系统状态响应。
- **逆向问题（Inverse）**：由测得响应反演轨道不平顺与缺陷参数。

核心原则：**同一套可微前向模型服务正向预测与逆向反演**，避免“两个模型、两套物理假设”。

---

## 2. 总体架构

### 2.1 Forward Core（可微前向核心）
- **LNN Backbone**：学习保守动力学主干（能量结构、状态演化基础）。
- **PINO Residual Head**：学习外激励/非保守项导致的残差（广义力或加速度修正）。
- 组合形式：
  - `dz = dz_lnn + dz_pino_residual`

### 2.2 Inverse Loop（逆向反演环）
- **Inverse Encoder（快速初值）**：`(y, c) -> u0`
- **Differentiable Refiner（物理精修）**：
  - 以 `u0` 为初值，最小化观测误差 + 正则项 + 物理约束项，迭代得到 `u*`
- 最终流程：
  - `y -> u0 -> Forward Core重建 -> 反向梯度修正 -> u*`

---

## 3. 数学形式（简化）

### 3.1 正向
- 状态方程：
  - `z_{t+1} = F_theta(z_t, u_t, c)`
- 其中：
  - `F_theta = F_lnn + F_pino_res`

### 3.2 逆向
- 初值网络：
  - `u0 = G_phi(y, c)`
- 精修优化：
  - `u* = argmin_u ||H(F_theta(u)) - y||^2 + R(u) + P(u)`

说明：
- `H`：观测算子（如从状态映射到加速度/位移传感器输出）。
- `R(u)`：先验正则（平滑、频带、幅值边界等）。
- `P(u)`：物理可行性约束（接触、能量、边界条件）。

---

## 4. 训练策略（分阶段）

1. **Stage A：训练 LNN Backbone**
   - 目标：先学稳定的基础动力学。
2. **Stage B：冻结/半冻结 LNN，训练 PINO Residual**
   - 目标：学习激励与非线性残差映射。
3. **Stage C：训练 Inverse Encoder**
   - 目标：给反演提供快速、可用的初值。
4. **Stage D：端到端联合微调**
   - 目标：提升正逆一致性与泛化能力。

---

## 5. 推荐损失函数

总损失：
- `L = λ1*L_state + λ2*L_dynamics + λ3*L_spectrum + λ4*L_inverse + λ5*L_reg`

建议项：
- `L_state`：状态/加速度时域误差
- `L_dynamics`：动力学残差误差
- `L_spectrum`：PSD 或频域一致性误差
- `L_inverse`：反演量与标注真值误差（若有标注）
- `L_reg`：反演参数平滑、幅值约束、稀疏先验

---

## 6. 目录与模块规划

当前建议在本仓库新增或完善以下模块：

- `pino_model/lnn_backbone.py`：LNN主干
- `pino_model/pino_architecture.py`：PINO残差分支（当前为空，需实现）
- `pino_model/hybrid_forward.py`：LNN+PINO融合前向器
- `pino_model/inverse_encoder.py`：逆向初值网络
- `pino_model/inverse_refiner.py`：可微优化精修器
- `pino_model/losses.py`：统一损失函数
- `pipeline/dataset_generator.py`：正向/逆向数据样本构造（当前为空，需实现）
- `pipeline/signal_processing.py`：频域特征与滤波处理（当前为空，需实现）

---

## 7. 与现有仿真模块的关系

- `generate_main.py` 与动力学求解器继续作为高可信数据源。
- 通过批量工况仿真生成训练数据：
  - 输入：不平顺、速度、线路参数、缺陷配置
  - 输出：状态 `X/V/A`、接触力、可观测通道
- 训练数据建议统一保存为按窗口切分的 `.npz/.pt` 格式，便于正逆任务复用。

---

## 8. 里程碑建议

- **M1**：完成 LNN+PINO 正向预测基线（可复现实验）
- **M2**：完成逆向初值网络（可快速估计不平顺）
- **M3**：完成“初值+精修”闭环反演
- **M4**：在多工况下验证鲁棒性与不确定性

---

## 9. 当前状态说明

- 已有：动力学仿真主流程、结果分析与对齐比较脚本。
- 待实现：`pino_model` 与 `pipeline` 中核心学习模块（当前部分文件为空）。

---

## 10. 下一步建议

优先顺序：
1. 完成 `pino_model/pino_architecture.py`（PINO残差主类）
2. 完成 `pipeline/dataset_generator.py`（统一数据接口）
3. 搭建最小可训练脚本（仅Forward）
4. 增加 `Inverse Encoder + Refiner`

可在上述基础上逐步接入你现有的不平顺对齐与频域评估流程，形成完整正逆一体化研究链路。
