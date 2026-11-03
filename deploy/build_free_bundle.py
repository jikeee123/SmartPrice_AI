from pathlib import Path
import sqlite3,zipfile,shutil
root=Path(__file__).resolve().parents[1]
out=root/'deploy'/'free_cloud_bundle';out.mkdir(exist_ok=True)
for source in (root/'smartprice_src').glob('*.py'):
    dest=out/'smartprice_src'/source.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(source,dest)
for source,target in [(root/'app.py',out/'platform_app.py'),(root/'legacy_app.py',out/'legacy_app.py')]:shutil.copyfile(source,target)
for source in (root/'deploy'/'modelscope').iterdir():
    if source.is_file():shutil.copyfile(source,out/source.name)
(out/'.streamlit').mkdir(exist_ok=True);shutil.copyfile(root/'.streamlit/config.toml',out/'.streamlit/config.toml')
(out/'models').mkdir(exist_ok=True)
seed=out/'data/database/smartprice_ai.db';seed.parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(root/'data/database/smartprice_ai.db') as original:
    with sqlite3.connect(seed) as copy:
        original.backup(copy)
        for table in ['approval_event','forecast_result','pricing_recommendation','scenario_result','platform_run','model_run']:
            copy.execute('DELETE FROM '+table)
        copy.commit()
archive=root.parent/'SmartPrice_AI_免费托管部署包.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for source in out.rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts and source.suffix!='.pyc':z.write(source,source.relative_to(out))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(archive,archive.stat().st_size)
