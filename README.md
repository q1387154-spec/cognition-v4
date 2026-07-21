# Cognition V4 — 认知操作系统

> 信念驱动的认知闭环系统。从多源数据自动提取观测 → 结构化证据 → 动态信念 → 多场景预测 → 结果验证 → 学习进化，同时构建因果图谱和追踪实体精度。

## 解决的问题

传统投资决策依赖个人经验，缺少系统化的信息处理、信念追踪和复盘机制。

Cognition V4 解决三个核心问题：

1. **信息过载** — 自动从腾讯财经、akshare 等多源数据提取结构化的观测和证据
2. **信念偏差** — 动态信念推理带置信度衰减和版本链，追踪判断的演变过程
3. **复盘缺失** — 自动对比预测 vs 实际结果，4 级误差分类，三路学习更新

## 架构

```
┌─────────────────────────────────────────────────────┐
│                      数据流                           │
│                                                      │
│  观测 → 证据 → 信念 → 预测 → 结果 → 学习              │
│   (src)  (struct) (dynamic) (scenes) (verify) (evolve)│
│                        ↓                              │
│                   因果图谱 ← 实体精度追踪                │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 核心实体

| 实体 | 说明 | 存储 |
|------|------|------|
| Observation | 原始观测（新闻/财报/行情） | `observations` 表 |
| Evidence | 结构化证据（定性/定量/分类） | `evidence` 表 |
| Belief | 动态信念（含置信度衰减、版本链） | `beliefs` 表 |
| Prediction | 多场景预测（4 场景 + 期望值） | `predictions` 表 |
| Outcome | 实际结果（4 级误差分类） | `outcomes` 表 |
| Learning | 学习记录（特征/因果/权重三路） | `learning` 表 |

### 15 个引擎

| 引擎 | 职责 | 文件 |
|------|------|------|
| **ObservationEngine** | 多源数据采集（腾讯财经行情 + akshare 财报） | `engines/observation_engine.py` |
| **EvidenceEngine** | 原始观测 → 结构化证据（含负面词触发分类证据） | `engines/evidence_engine.py` |
| **BeliefEngine** | 贝叶斯信念推理，logit 域平滑，prior cap 防过拟合 | `engines/belief_engine.py` |
| **PredictionEngine** | 4 场景预测（baseline/optimistic/pessimistic/black_swan） | `engines/prediction_engine.py` |
| **DecisionEngine** | Kelly 准则决策建议，最大亏损 10% 风控 | `engines/decision_engine.py` |
| **OutcomeEngine** | 预测 vs 实际对比，4 级误差分类（no_error/missing_signal/overconfidence/regime_mismatch） | `engines/outcome_engine.py` |
| **LearningEngine** | 三路学习（特征/因果/权重） | `engines/learning_engine.py` |
| **CausalEngine** | 关键词+因果连接词构建因果图谱 | `engines/causal_engine.py` |
| **ScenarioEngine** | 4 场景生成（含黑天鹅），概率动态归一化 | `engines/scenario_engine.py` |
| **GapEngine** | 认知差距分析 | `engines/gap_engine.py` |
| **ConfidenceEngine** | 置信度衰减调度 | `engines/confidence_engine.py` |
| **PredictabilityEngine** | 5 维度可预测性评分（信号质量/因果清晰度/历史可重复性/噪声水平/时间跨度可行性） | `engines/predictability_engine.py` |
| **CounterfactualEngine** | 反事实分析 | `engines/counterfactual_engine.py` |
| **FeatureLearningEngine** | 特征重要性学习 | `engines/feature_learning_engine.py` |
| **WeightLearningEngine** | 权重自适应 | `engines/weight_learning_engine.py` |

### 10 张数据表

```
observations          — 原始观测（1,498 条）
evidence              — 结构化证据（1,008 条）
beliefs               — 动态信念（1,020 条）
predictions           — 多场景预测（311 条）
outcomes              — 实际结果对比（23 条）
learning              — 学习记录（18 条）
causal_nodes          — 因果图谱节点（42 个）
causal_edges          — 因果图谱边（30 条）
entity_accuracy       — 实体精度追踪（7 个主体）
prediction_bindings   — 证据↔预测绑定（269 条）
```

## 快速开始

### 环境要求

- Python 3.11+
- SQLite 3（系统自带）

### 安装

```bash
git clone https://github.com/q1387154-spec/cognition-v4.git
cd cognition-v4

# 可选：创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 运行测试

```bash
pytest
```

预期输出：84/84 测试通过。

### 运行完整管道

```bash
python cron_cognitive_v4.py
```

每轮处理 12 个主体，生成 12 条预测 × 4 场景 = 48 个场景，自动绑定证据、更新因果图谱。

### 定时运行

```bash
# 查看已注册的 cron 任务
hermes cron list

# 手动触发一次
hermes cron run <job_id>
```

默认每天 03:00 自动运行。

## 数据流详解

### 一次完整运行

```
Step A: 数据采集
  ObservationEngine.fetch(subject_list)
  → 12 个主体 × 腾讯财经行情 + akshare 财报
  → 写入 observations 表

Step B: 证据提取
  EvidenceEngine.process(observations)
  → 定性证据（正面/负面关键词）+ 分类证据（数字变动）
  → 写入 evidence 表

Step C: 信念更新
  BeliefEngine.update(support_evidence, contradict_evidence)
  → 贝叶斯更新，logit 域平滑，置信度衰减
  → 写入 beliefs 表（含版本链）

Step D: 预测生成
  PredictabilityEngine.score(subject) → 可预测性评分
  ScenarioEngine.generate(belief, horizon) → 4 场景
  PredictionEngine.predict(belief, scenarios) → 最终预测
  → 写入 predictions 表

Step E: 因果图谱
  CausalEngine.build(evidence) → 关键词提取 + 因果连接
  → 写入因果图谱节点/边

Step F: 绑定
  PredictionBindingStore.bind(evidence, prediction)
  → 定量证据→直接绑定，定性→推理绑定，分类→矛盾绑定
```

### 结果验证（独立运行）

```
OutcomeEngine.compare(prediction, actual_value)
→ 4 级误差分类（no_error < 5% / reasonable < 15% / overconfidence < 30% / missing_signal ≥ 30%）
→ 写入 outcomes 表

LearningEngine.learn(outcome)
→ 更新特征重要性、因果权重、实体精度
→ 写入 learning 表 + entity_accuracy 表
```

## 项目结构

```
cognition-v4/
├── cron_cognitive_v4.py      # 主编排器（串行 12 个 subject）
├── data_fetcher.py           # 数据源适配（腾讯财经 + akshare）
├── core/                     # 数据实体定义
│   ├── belief.py / evidence.py / observation.py
│   ├── prediction.py / outcome.py / learning.py
│   └── entity.py
├── engines/                  # 15 个处理引擎（详见上方表格）
├── memory/                   # SQLite 持久化层（单例模式）
│   ├── base_store.py
│   ├── belief_store.py / evidence_store.py / ...
│   ├── causal_graph.py       # 因果图谱节点/边表
│   ├── entity_accuracy_store.py
│   └── prediction_binding_store.py
├── workflow/                 # 管道编排
│   ├── prediction_pipeline.py
│   ├── learning_pipeline.py
│   └── enhanced_learning_pipeline.py
├── config/                   # 配置
│   ├── domains.py / horizons.py / engines.py
├── models/llm.py             # LLM 封装
├── scripts/                  # CLI 工具
│   ├── cron_v4.py / query.py / verify.py
│   ├── auto_learn.py / seed_test_predictions.py
│   └── sync_to_wiki.py
├── _scripts/                 # 辅助脚本
│   ├── daily_briefing.py     # 每日简报生成
│   └── gen_causal_wiki.py    # 因果图谱 Wiki 快照
└── tests/                    # pytest 84 个测试
    ├── unit/
    └── integration/
```

## 配置

### 主体列表

在 `data_fetcher.py` 中配置预测主体：

```python
SUBJECTS = {
    "赛力斯毛利率": {"sources": ["tencent", "akshare"], "stock_code": "601127"},
    "招行净息差": {"sources": ["akshare"], "stock_code": "600036"},
    "腾讯毛利率": {"sources": ["tencent", "akshare"], "stock_code": "0700"},
    "英伟达股价": {"sources": ["tencent"], "stock_code": "NVDA"},
    "工行不良贷款率": {"sources": ["akshare"], "stock_code": "601398"},
    "ZTO单票成本": {"sources": ["tencent", "akshare"], "stock_code": "ZTO"},
    "赛力斯股价": {"sources": ["tencent"], "stock_code": "601127"},
    # ...
}
```

### 时间跨度

在 `config/horizons.py` 中配置：

```python
HORIZONS = {
    "5d":  {"days": 5,  "label": "短期"},
    "90d": {"days": 90, "label": "中期"},
}
```

## 测试

```bash
# 全部测试
pytest

# 仅单元测试
pytest tests/unit/

# 仅集成测试
pytest tests/integration/

# 带覆盖率
pytest --cov=. --cov-report=term
```

## 开发状态

| 模块 | 状态 |
|------|------|
| 数据采集 | ✅ 腾讯财经行情 + akshare 财报 |
| 证据提取 | ✅ 含负面词触发分类证据 |
| 信念推理 | ✅ logit 域平滑，prior cap 0.95 |
| 多场景预测 | ✅ 4 场景（baseline/optimistic/pessimistic/black_swan）|
| 决策建议 | ✅ Kelly 准则 + 10% 风控 |
| 结果验证 | ✅ 4 级误差分类 |
| 学习进化 | ✅ 三路学习（特征/因果/权重）|
| 因果图谱 | ✅ 关键词+连接词，42 节点/30 边 |
| 实体精度追踪 | ✅ 7 个主体，精度趋势（improving/declining/stable）|
| 证据↔预测绑定 | ✅ 多对多，3 种绑定类型 |
| 可预测性评分 | ✅ 5 维度评分 |
| 置信度衰减 | ✅ 每日调度 |
| Cron 自动运行 | ✅ 每天 03:00 |
| 每日简报 | ✅ 每天 03:30 推送微信 |
| 测试覆盖率 | ✅ 84/84 通过 |

## 路线图

- [ ] 数据源升级：替换 akshare 摘要为东方财富/新浪财经，解决银行专有指标缺失
- [ ] 预测幂等化：添加去重，避免每日重复预测
- [ ] 低精度自动过滤：可预测性 < 0.3 的主体跳过预测
- [ ] 策略信号：将七星评价系统与 V4 认知输出交叉验证
- [ ] 政策传导链：接入政策文件，分析政策→行业→持仓的传导路径

## 相关项目

- [Hermes Agent](https://hermes-agent.nousresearch.com) — 运行该系统的 AI Agent 框架
- [七星投资评价系统](https://github.com/q1387154-spec) — 主观投资评价体系，与 V4 客观认知互补

## License

MIT