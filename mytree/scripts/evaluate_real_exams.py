"""真实试卷冒烟评测，结果不直接发布新提示或更改评分规则。私有照片不进入前端资源。"""
import base64,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,junior
from app.formulas import parse_math
import sympy as sp
ROOT=Path(__file__).resolve().parents[1]
CASES={'calculation':{'source':'p2 第17(1)题','expected':'4'},
       'probability':{'source':'p3 第19题','expected':r'\frac{7}{16}'},
       'function':{'source':'p5 第24题','expected':r'[7,8.5]\cup[16,19]','human_review':True}}
results=[]
for name in sys.argv[1:] or CASES:
 started=time.monotonic();record={'case':name,**CASES[name]}
 try:
  data='data:image/jpeg;base64,'+base64.b64encode((ROOT/'data/evaluation'/f'{name}.jpg').read_bytes()).decode()
  ocr=ai.recognize(data);record['ocr']=ocr
  if ocr['supported'] and not ocr['multiple_questions']:
   lesson=junior.study({'problem':ocr['problem'],'problem_latex':ocr['problem_latex'],'steps':ocr['steps'],'recognition':ocr})
   record['lesson']=lesson
   answer=lesson['analysis']['target_latex']
   if not record.get('human_review'):
    try:record['final_answer_matches']=bool(sp.simplify(parse_math(answer)-parse_math(record['expected']))==0)
    except ValueError:record['final_answer_matches']=None
  else:record['requires_recrop']=True
 except (ai.ModelError,ValueError) as e:record['error']=str(e)
 record['seconds']=round(time.monotonic()-started,2);results.append(record)
 out=ROOT/'data/evaluation/live-results.json';out.write_text(json.dumps(results,ensure_ascii=False,indent=2));out.chmod(0o600)
 print(json.dumps({k:v for k,v in record.items() if k not in ('ocr','lesson')},ensure_ascii=False),flush=True)
