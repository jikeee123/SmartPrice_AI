from pathlib import Path
import subprocess,sys,json,time,os
root=Path(__file__).resolve().parents[1]
os.chdir(root)
os.environ['PYTHONPATH']=str(root)
os.environ['PYTHONIOENCODING']='utf-8'
commands=[['validate_data.py'],['run_stage3.py'],['tests/validate_stage3.py'],['tests/validate_stage4.py'],['tests/validate_stage5.py'],['-m','unittest','discover','-s','tests','-p','test_*.py'],['tests/check_ui.py'],['tests/check_workflow_ui.py']]
results=[]
for args in commands:
    start=time.perf_counter()
    p=subprocess.run([sys.executable,*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
    name=args[0] if args[0]!='-m' else 'unittest'
    logfile=root/'reports'/('final_'+Path(name).stem+'.log')
    logfile.write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
    results.append(dict(command=' '.join(args),status='PASS' if p.returncode==0 else 'FAIL',seconds=round(time.perf_counter()-start,2),log=logfile.name))
    print(results[-1],flush=True)
(root/'reports'/'final_acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(x['status']=='PASS' for x in results),results
