"""Publish the prepared bundle through official ModelScope OpenAPI and Git.
Token is read locally with a masked prompt and is never stored in files or Git URLs.
"""
import base64,getpass,json,os,re,shutil,subprocess,sys,tempfile,time
from datetime import datetime
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
ENDPOINT='https://modelscope.cn'

def named_items(value):
    if isinstance(value,list):
        for item in value: yield from named_items(item)
    elif isinstance(value,dict):
        if isinstance(value.get('name'),str):yield value
        for item in value.values():
            if isinstance(item,(dict,list)):yield from named_items(item)

def choose_free_hardware(data):
    free=[x for x in named_items(data) if x['name'].startswith('platform/') and 'cpu' in x['name'].lower() and x.get('resource_type')!='paid' and x.get('available',True) is not False]
    if not free:raise RuntimeError('No confirmed free CPU resource is available. Stopped without creating a paid resource.')
    return sorted(free,key=lambda x:('cpu' not in x['name'].lower(),x['name']))[0]['name']

def safe_message(message,token):
    encoded=base64.b64encode(('oauth2:'+token).encode()).decode() if token else ''
    text=str(message)
    for secret in [token,encoded]:
        if secret:text=text.replace(secret,'[REDACTED]')
    return text

def publish(token,owner=None):
    def api(path,body=None):
        request=Request(ENDPOINT+'/openapi/v1'+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=40) as r:result=json.load(r)
        except HTTPError as error:
            raise RuntimeError('ModelScope API HTTP '+str(error.code)+' at '+path) from None
        if result.get('success') is False:raise RuntimeError('ModelScope rejected request at '+path+': '+str(result.get('message','request failed')))
        return result.get('data',result)
    user=api('/users/me')
    if not owner:
        owner=next((user.get(k) for k in ['username','user_name','Username','Name'] if isinstance(user,dict) and user.get(k)),None)
    if not owner:owner=input('Your ModelScope username (not display nickname): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',owner or ''):raise ValueError('Invalid account username.')
    hardware=choose_free_hardware(api('/studios/hardware?sdk_type=streamlit'))
    images=list(named_items(api('/studios/base-images')))
    image=next((x['name'] for x in images if re.search(r'py3(?:10|11|12)|python3[.-](?:10|11|12)',x['name'])),None)
    if not image:raise RuntimeError('No compatible Python base image found. Nothing created.')
    git=shutil.which('git')
    if not git:
        candidate=Path('D:/codex/Git/cmd/git.exe')
        if candidate.is_file():git=str(candidate)
    if not git:raise RuntimeError('Git is not installed. Nothing created.')
    bundle=ROOT/'deploy/free_cloud_bundle'
    if not (bundle/'app.py').is_file():raise RuntimeError('Prepared deployment bundle is missing.')
    repo='smartprice-ai-'+datetime.now().strftime('%Y%m%d%H%M%S')
    params=dict(owner=owner,repo_name=repo,sdk_type='streamlit',display_name='SmartPrice AI',description='主题乐园智能定价与经营收益优化演示；全部业务数据为模拟。',visibility='public',hardware=hardware,base_image=image)
    print('Account:',owner,'Free hardware:',hardware,'Python image:',image,flush=True)
    api('/studios',params)
    url=ENDPOINT+'/studios/'+owner+'/'+repo
    report={'url':url,'hardware':hardware,'sdk_type':'streamlit','stage':'created','checked_public_access':False}
    report_path=ROOT/'reports/modelscope_publish.json'
    def save():report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save();print('Created:',url,flush=True)
    # Authentication exists only in the child environment, never in command args or remote URLs.
    env=os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='http.'+ENDPOINT+'/.extraheader',GIT_CONFIG_VALUE_0='Authorization: Basic '+base64.b64encode(('oauth2:'+token).encode()).decode(),GIT_CONFIG_KEY_1='credential.helper',GIT_CONFIG_VALUE_1='',GIT_TRACE='0',GIT_CURL_VERBOSE='0',GIT_TRACE_CURL='0')
    work=Path(tempfile.mkdtemp(prefix='publish_',dir=ROOT/'deploy'))
    checkout=work/'repository'
    def gitrun(args,cwd=None):
        result=subprocess.run([git,*args],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        if result.returncode:raise RuntimeError(safe_message(result.stderr,token))
    gitrun(['clone',url+'.git',str(checkout)])
    for source in bundle.rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts or source.suffix=='.pyc':continue
        target=checkout/source.relative_to(bundle);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    gitrun(['-c','user.name=SmartPrice Deployment','-c','user.email=deployment@example.invalid','add','.'],checkout)
    gitrun(['-c','user.name=SmartPrice Deployment','-c','user.email=deployment@example.invalid','commit','-m','Deploy SmartPrice AI five-module demo'],checkout)
    gitrun(['push','origin','HEAD:master'],checkout)
    report['stage']='uploaded';save()
    # Check resource is still free before deployment; never upgrade automatically.
    details=api('/studios/'+owner+'/'+repo)
    if isinstance(details,dict) and ('paid/' in str(details.get('hardware',''))):raise RuntimeError('Paid hardware detected; deployment stopped.')
    api('/studios/'+owner+'/'+repo+'/deploy',{})
    report['stage']='deploy_requested';save()
    print('Deployment requested. Open this public space and check runtime logs:',url,flush=True)
    print('Free resources may sleep. Public availability must be verified in a logged-out browser.',flush=True)
    return report

if __name__=='__main__':
    token=''
    try:
        token=os.environ.get('MODELSCOPE_API_KEY') or getpass.getpass('Paste ModelScope access token here (hidden; not saved): ').strip()
        if not token:raise ValueError('No access token provided.')
        publish(token,os.environ.get('MODELSCOPE_USERNAME'))
    except Exception as error:
        print('Deployment stopped:',safe_message(error,token),flush=True);sys.exit(1)
