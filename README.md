# Cognition V4 — 认知操作系统

Cognition V4 是一个基于信念推理的认知操作系统。它从多源数据提取观测 → 结构化证据 → 动态信念 → 预测 → 结果验证 → 学习闭环，支持因果图谱推理和实体精度追踪。

## 架构

```
观测 → 证据 → 信念 → 预测 → 结果 → 学习
                        ↓
                   因果图谱 ← 实体精度
```

### 核心引擎（15 个）

| 引擎 | 职责 |
|------|------|
| ObservationEngine | 多源数据采集（财经 / 政策） |
| EvidenceEngine | 原始观测 → 结构化证据 |
| BeliefEngine | 信念推理（含置信度衰减） |
| PredictionEngine | 多场景预测（4 场景） |
| DecisionEngine | 决策建议（Kelly 准则） |
| OutcomeEngine | 实际结果对比 & 误差分类 |
| LearningEngine | 三路学习（特征 / 因果 / 权重） |
| CausalEngine | 因果图谱构建 |
| ScenarioEngine | 场景生成（含黑天鹅） |
| GapEngine | 认知差距分析 |
| ConfidenceEngine | 置信度衰减调度 |
| PredictabilityEngine | 可预测性评分 |
| CounterfactualEngine | 反事实分析 |
| FeatureLearningEngine | 特征重要性学习 |
| WeightLearningEngine | 权重自适应 |

### 数据存储（SQLite，10 张表）

- observations / evidence / beliefs / predictions
- outcomes / learning / entity_accuracy
- causal_nodes / causal_edges / prediction_bindings

## 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest

# 运行完整管道
python cron_cognitive_v4.py
```

## 项目结构

```
cognition-v4/
├── core/           # 数据实体定义
├── engines/        # 15 个处理引擎
├── memory/         # SQLite 持久化层
├── workflow/       # 管道编排
├── config/         # 配置（domain / horizon / engine）
├── models/         # LLM 封装
├── scripts/        # CLI 工具
├── tests/          # 84 个测试
└── _scripts/       # 辅助脚本
```

## 状态

- ✅ 84/84 测试通过
- ✅ 15 引擎注册 & 集成
- ✅ 10 张 DB 表全部活跃
- ✅ cron 每日自动运行
- ✅ 真实数据源（腾讯财经 + akshare）