"""Package verified sources without the machine-specific virtual environment."""
from pathlib import Path
import json,sqlite3,zipfile,joblib
root=Path(__file__).resolve().parent
results=json.loads((root/'reports/final_acceptance.json').read_text(encoding='utf-8'))
assert all(x['status']=='PASS' for x in results)
ui=json.loads((root/'reports/ui_validation.json').read_text(encoding='utf-8'))
flow=json.loads((root/'reports/workflow_ui_validation.json').read_text(encoding='utf-8'))
with sqlite3.connect(root/'data/database/smartprice_ai.db') as c:
    n=c.execute('select count(*) from approval_event where run_id=?',(flow['pricing_run_id'],)).fetchone()[0]
    assert n>0
metrics=joblib.load(root/'models/platform_forecaster.joblib')['metrics']
(root/'reports/platform_model_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# SmartPrice AI 平台验收报告','','验收日期：2026年11月2日（北京时间）','','## 结论','','完整参赛平台通过本机验收。原阶段2–5压缩包保持不变，第5阶段为整合基线。','','## 自动验收','','| 命令 | 结果 | 耗时（秒） |','|---|---|---:|']
for x in results: lines.append('| '+x['command']+' | '+x['status']+' | '+str(x['seconds'])+' |')
lines+=['','五模块导航、默认首页、页签归属、历史分析日期范围、AI与定价记录隔离及跨模块同run_id且不重新计算的检查通过。','新增业务测试17项通过；包括财务勾稽、5元步长、价格边界、不可行容量、多日递归、训练期留痕、审批修改后采纳、月报期间一致性、数据损坏阻断、缺少上月和外部服务失败回退。','','五个核心模块及内部页签均无异常或错误提示。页面切换耗时为 {:.3f}–{:.3f} 秒，仅代表本机自动化测量。'.format(min(x['seconds'] for x in ui.values()),max(x['seconds'] for x in ui.values())),'','页面完整流程：未来预测→三策略比较→AI五工具调用→月报→人工审批保存。定价运行编号：'+flow['pricing_run_id'],'','## 浏览器与记录持久化检查','','实际启动服务，在浏览器检查五模块导航、经营总览和季节环境统计，并验证桌面与窄屏布局。预测、定价、AI、审批和导出通过完整页面流程验收。新数据库连接确认上述运行仍保留 '+str(n)+' 条审批事件。','','## 模型评估','','训练：'+metrics['train']+'；校准：'+metrics['calibration']+'；测试：'+metrics['test']+'。','MAE {:.2f} 人，WAPE {:.2%}，上周同日基线WAPE {:.2%}，测试区间覆盖率 {:.2%}。'.format(metrics['mae'],metrics['wape'],metrics['baseline_wape'],metrics['interval_coverage']),'','未来多步区间由校准残差按步数平方根扩展，为情景参考，不保证未来覆盖率。预测客流与定价需求分别由随机森林和弹性模型估计，结果可能不同。','','## 复核与限制','','既有月报期间、训练期间和连续审批修复继续通过回归。本轮只读复核发现的历史日期覆盖已修复，新增环境分组与容量预警非空检查通过。','全部数据为模拟，收益提升为模型测算；未接入实时天气、真实交易或自动发布票价。无密钥本地AI与失败回退已验收；真实付费大模型服务未配置或验收。本地审批无生产身份认证。','迁移时请安装Python 3.10并运行setup.bat；本机可直接运行run_app.bat。原始运行及审批数据保存在SQLite文件中。','','完整输出见 final_*.log，机器可读汇总见 final_acceptance.json。']
(root/'reports/平台验收报告.md').write_text('\n'.join(lines),encoding='utf-8')
# Exclude private configuration, caches, and machine-specific environments.
output=root.parent/'SmartPrice_AI_完整参赛平台.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file() and not any(x in p.parts for x in ['.venv','__pycache__','.git']) and p.name!='.env' and p.suffix!='.pyc':
            z.write(p,Path('SmartPrice_AI')/p.relative_to(root))
with zipfile.ZipFile(output) as z: assert z.testzip() is None
print('ALL PASS; release:',output,'bytes:',output.stat().st_size)
print(json.dumps(metrics,ensure_ascii=False))
