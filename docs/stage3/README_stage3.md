# SmartPrice AI — Stage 3 经营分析与定价模型

## 环境

- Python 3.10+
- 已完成 Stage 2 并存在 `data/database/smartprice_ai.db`

安装依赖：

```powershell
pip install -r requirements.txt
```

运行第三阶段：

```powershell
python run_stage3.py
```

## 本阶段功能

1. SQLite + SQL + Pandas 数据读取。
2. 日度、月度、产品、二次消费类别和销售渠道经营指标。
3. 综合经营收入、游客人均收入、贡献利润及贡献利润率。
4. 产品级 log-log 价格弹性回归，使用 HC3 稳健标准误。
5. Random Forest 客流预测，按时间先后划分训练集和测试集。
6. 使用 SLSQP 进行多产品联合定价优化，并考虑价格边界、单次价格调整幅度和容量约束。

## 输出

`reports/stage3/`：

- `daily_metrics.csv`
- `monthly_metrics.csv`
- `product_metrics.csv`
- `secondary_metrics.csv`
- `channel_metrics.csv`
- `business_kpi_summary.json`
- `price_elasticity_results.csv`
- `price_elasticity_diagnostics.csv`
- `elasticity_model_*.txt`
- `visitor_forecast_backtest.csv`
- `visitor_forecast_metrics.json`
- `pricing_recommendation_demo.csv`
- `pricing_optimization_summary.json`
- `stage3_execution_report.json`
- `stage3_summary.md`

`models/visitor_forecast_model.joblib` 保存客流预测模型。

## 关键方法说明

### 收入与贡献利润

综合经营收入 = 门票及套餐净销售额 + 套餐外增量餐饮净销售额 + 周边商品净销售额。

套餐收入只计入一次。套餐内餐饮收入分配字段仅用于结构分析，不重复加总。

贡献利润（本原型口径）= 综合经营收入 - 门票/套餐单位变动成本 - 增量餐饮及周边商品COGS。

此处不是完整会计利润，不含固定成本、折旧、税费、融资费用等。

### 价格弹性

对每个产品估计：

`ln(net_orders) = α + β ln(list_price) + controls + ε`

β 为估计价格弹性。模型控制星期、节假日、寒暑假、天气、温度、降雨、营销和特殊活动，并采用 HC3 稳健标准误。

由于输入是模拟数据，系数仅用于展示建模流程，不应当作真实市场因果弹性。

### 客流预测

按时间顺序以 2025-11-01 为测试集起点。测试期间采用滚动单步预测，lag 特征使用此前已观察到的游客数。它不是一次性预测整个未来期间。

### 动态定价

基于产品级价格弹性模型预测各产品需求，并用 SLSQP 优化各产品价格。目标为模拟总收入最大化，价格受产品价格区间及相对基准价格 ±10% 约束，预测游客人数受目标容量利用率约束。

目标场景日为 2025-10-04。结果是历史模拟场景下的模型反事实，不是实际已发生的收入提升。

## 运行边界

如果优化器无法找到满足容量约束的可行解，输出会标记 WARNING；不要把未通过约束的价格建议用于业务决策。
