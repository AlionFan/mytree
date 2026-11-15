"""Current-page multi-question OCR; immutable, account-bound auto acceptance."""
from dataclasses import replace
import base64
import io
from PIL import Image
import copy
import hashlib
import json
import math
import re

from . import ai, cards, contract, store
from .errors import DomainError
from .reading_registry import registry, new_id, ConfirmationError

MAX_ITEMS=12
POLICY='page-auto-v2'
PAGE_PROMPT=ai.OCR_PROMPT.split('返回JSON：',1)[0]+'\n核心id对应：F1提公因式、F2平方差、F3完全平方、F4分解彻底、F5符号；N1实数运算、N2二次根式、N3整式与幂、N4科学计数法；U1坐标系、U2一次函数、U3反比例、U4二次函数、U5应用；G7图形变换与视图。知识点id使用N1~N4/F1~F5/R1~R3/E1~E4/I1~I2/U1~U5/G1~G9/S1~S3/P1~P2；选择实际最相关知识点，不由答案对错猜测。\n'+r'''
本次是整页识别：先清点可见印刷题号（包括选择题、填空题），逐一对应输出，最后复查遗漏与重复；不能只挑有学生作答的题。识别当前整图所有独立大题，不要求用户先框选。不解题、不要更正错误。
选择题的全部A、B、C、D选项是题干必需内容：必须完整写进problem，并逐字出现在role=problem的片段。选项标签统一写为“A. … B. … C. … D. …”，保留全部原选项表达。图形选项也要逐个标明A/B/C/D及可见图形条件；diagram_description只能补充空间关系，绝不能代替题干中的选项。任何选项读不全时problem_complete=false，不能把仅有问句的选择题标完整。
题干填空、括号或下划线内学生填写的选项字母/序号（如①②、③）必须单独记录student_work片段并进入steps，不混入problem、不遗漏；疑似数字或字形看不清时标uncertain_lines，不按解题结果倒改笔迹。
按双栏/页面阅读顺序给出大题列表。子问与共享题干、图表必须放在同一大题的problem中，不丢共享条件。
严格区分印刷/手写笔迹与语义角色，它们并不等价：手抄题干仍可为problem；教师手写是teacher_annotation。
学生答案即使写进题干空白、覆盖文字、题目上方、旁边或页边，也只能记student_work，不能变成题干条件。
被覆盖无法读出的印刷条件不能用解题常识补全。跨题归属不明的笔迹只放unassigned_fragments，不给两道题复制步骤。
teacher_annotation/crossed_out不得放进steps。学生明显算错的内容照抄，划掉重写只以重写为当前作答。
association_evidence只用一条简短依据，不重复题干或作答；不输出空泛分析文字。
同一内容只采用一种统一转录：problem必须与role=problem的fragments.text逐字相同（可只差题号），公式表示也必须完全一致；steps必须按顺序逐字对应所有student_work片段，不添加“手写选择”等原图没有的说明词。每个student_work片段都须在steps出现，不漏旁边明确属于本题的草稿。无法确定归属的跨题草图放unassigned_fragments，不能按最近空间位置猜归属。每题必须返回printed_number与完整所需字段。
每题必须报告problem_complete、diagram_complete、answer_presence(present/absent/uncertain)、association_status(clear/uncertain)、association_evidence。
只有确实清楚才填clear；不确定有没有作答必须uncertain，不能假装absent。缺少图形条件不能假装完整。
fragments为可追溯片段，role=problem/student_work/teacher_annotation/crossed_out/unknown，script_kind=printed/handwritten/unknown；text原样，region使用具名对象{"x":左,"y":上,"width":宽,"height":高}，均为0~1，width/height是宽高而非右/下坐标；x+width、y+height不得超过1。例如底部区域y=0.8,height=0.15，其下边界为0.95；不得把下边界0.95当height。区域可重叠。
每题region覆盖题干和相应作答，不要求几何框互不重叠；题干区域与作答区域可重叠。
返回JSON {"items":[{"printed_number":"1或空串","problem":"完整题干，公式用$LaTeX$","problem_latex":"只有完整纯式题才填写","steps":["学生原样作答"],"question_type":"factor/simplify/calculate/equation/inequality/function/geometry/statistics/probability/word_problem/other","topic_id":"大纲id","diagram_description":"明确图表条件或空串","uncertain_lines":[],"warnings":[],"alternatives":[],"supported":true,"region":{"x":0,"y":0,"width":1,"height":1},"fragments":[{"role":"problem","script_kind":"printed","text":"原印刷题干","region":{"x":0,"y":0,"width":1,"height":0.2}}],"problem_complete":true,"diagram_complete":true,"answer_presence":"present","association_status":"clear","association_evidence":"依据题号、笔迹延续与内容指向说明归属，不按答案对错推断"}],"unassigned_fragments":[{"role":"unknown","script_kind":"handwritten","text":"无法归属的片段","region":{"x":0,"y":0,"width":1,"height":1},"affected_orders":[1,2]}],"overflow":false,"warnings":[]}。
JSON字符串中的LaTeX反斜杠必须按JSON规范写成双反斜杠，例如"\\triangle ABC"、"a\\bot b"；不要让\\t或\\b成为制表符或退格符。所有region（题目、fragments、unassigned_fragments）一律使用上述具名对象，不输出坐标数组。
最多12道大题；超过12道或输出无法容纳时overflow=true，不宣称已识别整页。不要输出图片base64、标准答案或额外解题。
'''


def _box(value):
    # Model input is explicit xywh. Legacy arrays retain their original contract;
    # never infer xyxy from geometry or silently reinterpret cached readings.
    if isinstance(value,dict):
        if set(value)!={'x','y','width','height'}:raise ValueError('区域格式不正确')
        value=[value[key] for key in ('x','y','width','height')]
    if not isinstance(value,list) or len(value)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value):raise ValueError('区域格式不正确')
    x,y,w,h=value
    if min(x,y)<0 or min(w,h)<=0 or x+w>1.000001 or y+h>1.000001:raise ValueError('区域超出当前页')
    return value


def _text_key(value):
    for marker in (r'\(',r'\)',r'\[',r'\]','$',r'\left',r'\right'):value=value.replace(marker,'')
    value=re.sub(r'\\(?:qquad|quad)(?![A-Za-z])|\\[,;!]','',value)
    return re.sub(r'\s+','',value)


def _transcript_key(value,number='',problem=False):
    # Formatting only: no solving, simplification or algebraic equivalence.
    value=re.sub(r'\[划掉[:：][^\[\]]{0,500}\]','',value)
    if problem and number:
        label=number.strip().strip('.．、:：)（()）')
        if label:
            value=re.sub(r'^\s*(?:[（(]'+re.escape(label)+r'[）)]\s*|'+re.escape(label)+r'[.．、:：)](?:\s+|(?=[^\d\s])))','',value)
    value=value.translate(str.maketrans({'，':',','；':';','：':':','（':'(', '）':')','．':'.'}))
    value=re.sub(r'(?<!\d)。|。(?!\d)','.',value)
    value=value.replace(r'\dfrac',r'\frac').replace(r'\tfrac',r'\frac')
    for command,glyph in [('angle','∠'),('alpha','α'),('beta','β'),('gamma','γ'),('triangle','△'),('perp','⊥'),('bot','⊥'),('approx','≈')]:
        value=re.sub(r'\\'+command+r'(?![A-Za-z])',lambda _:glyph,value)
    for command in ('sin','cos','tan'):
        value=re.sub(r'\\'+command+r'(?![A-Za-z])',command,value)
    value=_text_key(value)
    value=re.sub(r'_\{([0-9A-Za-z])\}',r'_\1',value)
    if problem:value=re.sub(r'^\(本题满分\d+(?:\.\d+)?分\)','',value)
    for old,new in (('−','-'),('＝','='),('²','^2'),('³','^3'),('≤','<='),('≥','>='),(r'\leq','<='),(r'\geq','>='),(r'\le','<='),(r'\ge','>='),(r'\cdot','*'),(r'\times','*')):value=value.replace(old,new)
    value=re.sub(r'\^\{(-?\d+)\}',r'^\1',value)
    value=re.sub(r'(?<=\d)\*(?=[a-zA-Z(])','',value)
    value=value.replace(')*(',')(')
    if problem:
        if number:
            value=re.sub(r'^'+re.escape(number.strip().strip('.．、:：)（()）'))+r'[.．、:：)](?!\d)','',value)
        value=re.sub(r'^(?:分解因式|因式分解|化简|计算|解方程|解不等式|Factor|Simplify|Calculate)[:：]?','',value,flags=re.I)
        value=value.strip('。；;：:.')
    else:
        value=re.sub(r'^(?:解|原式|所以|因此|得)[:：=]*','',value)
    return value


def _fragments(values,unassigned=False):
    if not isinstance(values,list) or len(values)>64:raise ValueError('片段数量不正确')
    result=[]
    for item in values:
        if not isinstance(item,dict) or item.get('role') not in ('problem','student_work','teacher_annotation','crossed_out','unknown') or item.get('script_kind') not in ('printed','handwritten','unknown'):raise ValueError('片段角色不正确')
        text=item.get('text')
        if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ValueError('片段内容不正确')
        row={'role':item['role'],'script_kind':item['script_kind'],'text':text,'region':_box(item.get('region'))}
        if unassigned:
            affected=item.get('affected_orders',[])
            if not isinstance(affected,list) or len(affected)>12 or any(type(v) is not int or not 1<=v<=12 for v in affected):raise ValueError('未归属片段关联不正确')
            row['affected_orders']=affected
        result.append(row)
    return result


def source_topic(item):
    """Bounded content taxonomy, independent of correctness/student answers."""
    from . import source_patterns
    p=item['problem']
    if re.search('美术字|轴对称|俯视图|左视图|三视图',p):return 'G7'
    if re.search('科学记数法|科学计数法',p):return 'N4'
    if '下列计算正确' in p and re.search(r'\\div|÷',p) and not re.search(r'\\sqrt|√',p):return 'N3'
    family=source_patterns.classify(p)
    if family:return {'expression-domain':'N2','perfect-square-polynomial':'F3','similar-area-perimeter':'G5','scientific-notation':'N4','event-certainty':'P1'}[family['family']]
    if item['question_type']=='function' and re.search(r'\\frac\{[^}]+\}\{x\}|/x',p):return 'U3'
    return item['topic_id']



def _unclear_symbols(text):
    """Permit only ordinary Chinese question punctuation, never math blanks."""
    if '�' in text or re.search(r'[?？]{2,}',text):return True
    # Track explicit math delimiters; an unmatched delimiter is not evidence
    # that a question mark represents ordinary punctuation.
    spans=[];opened=None;begin=0
    for match in re.finditer(r'\$\$|\$|\\[()\[\]]',text):
        token=match.group()
        if opened is None:
            if token in ('$', '$$', r'\(', r'\['):opened=token;begin=match.start()
            else:return True
        elif token=={'$':'$','$$':'$$',r'\(':r'\)',r'\[':r'\]'}[opened]:
            spans.append((begin,match.end()));opened=None
    if opened is not None and ('?' in text or '？' in text):return True
    for match in re.finditer(r'[?？]',text):
        pos=match.start()
        if any(a<=pos<b for a,b in spans):return True
        prefix=re.split(r'[。！？?；;\n]',text[:pos])[-1]
        if not re.search(r'是否|能否|多少|为什么|为何|吗|几何|多大|几种|怎样|如何',prefix):return True
        if not re.search(r'[\u3400-\u9fff][”」]?$',prefix):return True
        if pos+1<len(text) and not re.match(r'[\s。；;，,）)】」”]',text[pos+1]):return True
    return False



def _missing_choice_options(source):
    """A-D evidence must live in the authoritative problem, not diagram notes."""
    def choices(text):
        text=text.translate(str.maketrans('ＡＢＣＤ','ABCD'))
        labels=list(re.finditer(r'(?<![A-Za-z])([ABCD])\s*[.．。:：、]',text))
        if [v[1] for v in labels]!=list('ABCD'):return False
        return all(text[v.end():labels[i+1].start() if i<3 else len(text)].strip() for i,v in enumerate(labels))
    problem=source.get('problem','')
    evidence=source.get('diagram_description','')+'\n'+'\n'.join(f.get('text','') for f in source.get('fragments',[]) if isinstance(f,dict) and f.get('role')=='problem')
    # Check the query before any partial option list as well as a bare query.
    stem=re.sub(r'\s+','',re.split(r'(?<![A-Za-z])[ABCDＡＢＣＤ]\s*[.．。:：、]',problem,maxsplit=1)[0])
    bare_choice=bool(re.search(r'(?:下列|以下|下面)[^。！？?]{0,100}(?:正确|错误|成立|符合|确定事件|随机事件)[^。！？?]{0,20}(?:的是|为)[.。?？:：]?$',stem))
    value_choice=bool(re.search(r'值可能(?:是|为)[（(][）)]',stem))
    explicit=bool(bare_choice or value_choice or re.search(r'选择题|单选题|单项选择',problem) or
                  re.search(r'下列|以下',problem) and re.search(r'是[（(]\s*[）)]|[（(]\s*[）)]',problem) or
                  choices(evidence) or re.search(r'选项\s*[A-DＡ-Ｄ]',evidence))
    return explicit and not choices(problem)


def lesson_eligible(item):
    if not item['supported'] or not item['problem_complete'] or not item['diagram_complete'] or not item['problem'].strip() or _unclear_symbols(item['problem']) or 0 in item['uncertain_lines']:return False
    allowed={'还不能确定这些笔迹属于哪道题。','还不能确定这道题是否有作答。','作答内容没有读完整。','读到了作答片段，不能当成未作答。','作答状态与读到的笔迹不一致。','题目中还有角色不明的笔迹。','附近有无法归属的笔迹，先跳过这题。','缺少可追溯的作答片段。','作答步骤与原样笔迹片段不一致，先跳过这题。','批注或划掉内容与当前作答混在一起。','同一笔迹被分配给多道题。','关键文字或符号还没看清。'}
    return bool(item['attention_reasons']) and all(reason in allowed for reason in item['attention_reasons'])


def normalize_page(raw,page_index,generation):
    from . import question_search
    if not isinstance(raw,dict) or not isinstance(raw.get('items'),list) or not raw['items'] or len(raw['items'])>40:raise ai.ModelError('这次没有读到完整的题目列表，请重新拍清楚一些。','MODEL_OUTPUT_INVALID')
    if type(raw.get('overflow')) is not bool:raise ai.ModelError('这次页面完整性信息缺失，请重试。','MODEL_OUTPUT_INVALID')
    try:unassigned=_fragments(raw.get('unassigned_fragments',[]),True)
    except ValueError:raise ai.ModelError('这次未归属笔迹信息不完整，请重试。','MODEL_OUTPUT_INVALID') from None
    output={'batch_id':new_id(),'source_revision':1,'client_generation':generation,'page_index':page_index,'items':[],
            'unassigned_fragments':unassigned,'overflow':raw['overflow'] or len(raw['items'])>MAX_ITEMS,
            'warnings':[],'original_search':{'status':question_search.capabilities()}}
    seen_work={}
    for order,source in enumerate(raw['items'][:MAX_ITEMS],1):
        item_id=new_id()
        base={'item_id':item_id,'reading_id':new_id(),'order':order,'printed_number':'','parent_item_id':None,'region':[0,0,1,1],
              'problem':'','problem_latex':'','steps':[],'question_type':'other','topic_id':'F1','diagram_description':'',
              'uncertain_lines':[],'warnings':[],'inferred':False,'reading_evidence':'','alternatives':[],
              'supported':False,'multiple_questions':False,'needs_confirmation':False,
              'auto_ready':False,'readiness':'needs_attention','attention_reasons':[],'fragments':[],
              'association_status':'uncertain','answer_presence':'uncertain','problem_complete':False,'diagram_complete':False,
              'association_evidence':'','provenance':{'source_kind':'photo','page_index':page_index,'transcription_version':1}}
        try:
            required={'problem','steps','question_type','supported','region','fragments','problem_complete','diagram_complete','answer_presence','association_status','association_evidence','uncertain_lines'}
            if not isinstance(source,dict) or not required.issubset(source):raise ValueError('题目结构不完整')
            base.update(ai.normalize_recognition({**source,'multiple_questions':False},validate_algebra=False))
            base.pop('ok',None);base.pop('meta',None);base['needs_confirmation']=False
            base['region']=_box(source.get('region'))
            number=source.get('printed_number','')
            if not isinstance(number,str) or len(number)>64:raise ValueError('题号不正确')
            base['printed_number']=number
            base['fragments']=_fragments(source.get('fragments'))
            base['problem_complete']=source.get('problem_complete') is True and not _missing_choice_options(source)
            base['diagram_complete']=source.get('diagram_complete') is True
            base['association_status']=source.get('association_status') if source.get('association_status') in ('clear','uncertain') else 'uncertain'
            base['answer_presence']=source.get('answer_presence') if source.get('answer_presence') in ('present','absent','uncertain') else 'uncertain'
            evidence=source.get('association_evidence','')
            if not isinstance(evidence,str) or len(evidence)>1000:raise ValueError('归属依据不完整')
            base['association_evidence']=evidence
            reasons=[]
            if not base['problem_complete'] or not base['problem'].strip():reasons.append('题干有遮挡、裁断或缺少条件。')
            if re.search('如图|下图|图中|表中|如表',base['problem']) and not base['diagram_description'].strip():reasons.append('题目依赖的图表条件没有展开。')
            if not base['diagram_complete']:reasons.append('需要的图形或表格条件没读完整。')
            if base['association_status']!='clear' or not evidence.strip():reasons.append('还不能确定这些笔迹属于哪道题。')
            if base['answer_presence']=='uncertain':reasons.append('还不能确定这道题是否有作答。')
            if base['answer_presence']=='present' and not base['steps']:reasons.append('作答内容没有读完整。')
            if base['answer_presence']=='absent' and any(f['role']=='student_work' for f in base['fragments']):reasons.append('读到了作答片段，不能当成未作答。')
            if base['answer_presence']=='absent' and base['steps']:reasons.append('作答状态与读到的笔迹不一致。')
            if any(re.search('题干|条件|图形|作答|符号',note) and re.search('模糊|看不清|遮挡|不完整|不确定|无法辨',note) for note in base['warnings']):reasons.append('关键内容仍有识别疑点。')
            if base['uncertain_lines'] or _unclear_symbols(base['problem']) or any(_unclear_symbols(s) for s in base['steps']):reasons.append('关键文字或符号还没看清。')
            if any(f['role']=='unknown' for f in base['fragments']):reasons.append('题目中还有角色不明的笔迹。')
            for fragment in unassigned:
                if fragment['role']=='unknown' and (not fragment['affected_orders'] or order in fragment['affected_orders']):reasons.append('附近有无法归属的笔迹，先跳过这题。')
            if not any(f['role']=='problem' for f in base['fragments']):reasons.append('缺少可追溯的原题片段。')
            if base['answer_presence']=='present' and not any(f['role']=='student_work' for f in base['fragments']):reasons.append('缺少可追溯的作答片段。')
            printed=''.join(_transcript_key(f['text'],number,True) for f in base['fragments'] if f['role']=='problem')
            authoritative=_transcript_key(source['problem'],number,True)
            if printed!=authoritative:reasons.append('题干与原题片段不一致，先跳过这题。')
            if base['problem_latex'] and _transcript_key(base['problem'],number,True)!=_transcript_key(base['problem_latex'],number,True):reasons.append('纯式与完整题干不一致，先跳过这题。')
            work=''.join(_transcript_key(f['text']) for f in base['fragments'] if f['role']=='student_work')
            steps=''.join(_transcript_key(line) for line in source['steps'])
            if work!=steps:reasons.append('作答步骤与原样笔迹片段不一致，先跳过这题。')
            ignored={_transcript_key(f['text'].split('：')[-1].split(':')[-1]) for f in base['fragments'] if f['role'] in ('teacher_annotation','crossed_out')}
            if any(_transcript_key(line) and any(_transcript_key(line) in note for note in ignored) for line in base['steps']):reasons.append('批注或划掉内容与当前作答混在一起。')
            for f in base['fragments']:
                if f['role']=='student_work':
                    key=(f['text'],tuple(f['region']))
                    if key in seen_work:
                        other=output['items'][seen_work[key]];other['attention_reasons'].append('同一笔迹被分配给多道题。');other['auto_ready']=False;other['readiness']='needs_attention';other['association_status']='uncertain'
                        reasons.append('同一笔迹被分配给多道题。');base['association_status']='uncertain'
                    else:seen_work[key]=order-1
            base['attention_reasons']=list(dict.fromkeys(reasons))
            base['readiness']='unsupported' if not base['supported'] else 'needs_attention' if reasons else 'ready'
            base['auto_ready']=base['readiness']=='ready'
        except (ValueError,TypeError,ai.ModelError) as error:
            # Preserve legible source text when one metadata field is malformed.
            # It remains ineligible for automatic study; never silently blank a question.
            if isinstance(source,dict):
                for key,limit in [('problem',6000),('printed_number',64),('diagram_description',3000)]:
                    text=source.get(key)
                    if isinstance(text,str) and len(text)<=limit:base[key]=text
                lines=source.get('steps')
                if isinstance(lines,list) and len(lines)<=30 and all(isinstance(t,str) and len(t)<=2000 for t in lines):base['steps']=lines
            base['attention_reasons']=['这道题的识别结构不完整，请重拍这题。'];base['auto_ready']=False;base['readiness']='needs_attention'
        output['items'].append(base)
    if output['overflow']:output['warnings'].append('本次最多整理12道大题，还有内容未处理。可以保留原图，稍后局部重拍。')
    for item in output['items']:
        item['topic_id']=source_topic(item)
        item['visual_required']=bool(item.get('diagram_description') or re.search('美术字|如图|下图|图中|图示|立体|几何体|俯视图|统计图|折线图|条形图',item['problem']))
        item['lesson_ready']=lesson_eligible(item)
        if item['lesson_ready']:item['readiness']='lesson_only'
    contract.definition('PageRecognitionOutput',output)
    return output


def vision_views(image):
    """One request with a full-page anchor and overlapping detail views.

    All reported regions remain in the original page coordinate system. The
    overlap is explicitly one source, never two copies of the same question.
    """
    views=[{'type':'text','text':'图1是完整原页。输出区域坐标一律基于图1，按原页阅读顺序列题。'},
           {'type':'image_url','image_url':{'url':image,'detail':'high'}}]
    with Image.open(io.BytesIO(base64.b64decode(image.split(',',1)[1]))) as page:
        w,h=page.size
        if h<1400 or h/w<1.15:return views
        for index,(top,bottom) in enumerate(((0,.58),(.42,1)),2):
            crop=page.crop((0,int(h*top),w,int(h*bottom)));out=io.BytesIO();crop.save(out,format='JPEG',quality=92)
            views.extend([{'type':'text','text':f'图{index}是图1的局部放大：原页x=0..1，y={top}..{bottom}。局部坐标(u,v)还原为(u,{top}+v*{bottom-top})。和其他图重叠的是同一题，只输出一次。跨切口的大题必须结合完整图与另一局部补齐共享题干、图形和作答，不能把局部截断当成原页缺失。'},
                          {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode(),'detail':'high'}}])
    return views


def recognize(student,body):
    contract.definition('PageRecognitionInput',body)
    digest=hashlib.sha256(body['image_data'].encode()).hexdigest()
    key=(student,'page',body['request_id'])
    with store.request_lock(key):
        cached=registry.page_request(student,body['request_id'],digest,body['client_generation'],body.get('page_index',1))
        if cached is not None:return cached
        image=ai.prepare_image(body['image_data'],max_edge=2400)
        result,_=ai.complete('vision',[{'role':'system','content':PAGE_PROMPT},{'role':'user','content':vision_views(image)}],cfg=replace(ai.settings(),timeout=90),limit=16000)
        output=normalize_page(result,body.get('page_index',1),body['client_generation'])
        from .source_images import images
        images.put(student,output['batch_id'],output['source_revision'],image)
        registry.remember_page(student,body['request_id'],digest,output)
        return output


def _saved(student,reading_id,batch_id,revision):
    value=store.read(student)
    for card in value['wrong_cards'].values():
        source=card.get('_source',{})
        if source.get('reading_id')==reading_id and source.get('batch_id')==batch_id:
            if source.get('source_revision')!=revision:raise ConfirmationError('来源版本已变化，请重新识别。','CONFLICT',409)
            return {'ok':True,'analysis':cards.public_analysis(card['_analysis']),'diagnosis_id':card['diagnosis_id'],'duplicate':True,'wrong_card':cards.public_card(card)}
    return None


def study(student,body):
    contract.definition('ReadingStudyInput',body)
    with store.request_lock((student,'page-study',body['reading_id'])):
        if body['batch_id'] in registry._pages:registry.page_reading(student,body['batch_id'],body['reading_id'],body['source_revision'])
        saved=_saved(student,body['reading_id'],body['batch_id'],body['source_revision'])
        if saved is not None:return saved
        token,reading=registry.accept_auto(student,body['batch_id'],body['reading_id'],body['source_revision'])
        request=hashlib.sha256(('page:'+body['batch_id']+':'+body['reading_id']+':'+str(body['source_revision'])).encode()).hexdigest()
        result=cards.study(student,{'problem':reading['problem'],'problem_latex':reading.get('problem_latex',''),'steps':reading['steps']},request,acceptance_token=token)
        return {'ok':True,**result['output']}


def resume(student,body):
    contract.definition('PageResumeInput',body)
    if body.get('image_data'):
        with registry._lock:source=registry._page(student,body['batch_id'],body['source_revision'],allow_cancelled=True);digest=source['digest']
        if hashlib.sha256(body['image_data'].encode()).hexdigest()!=digest:raise ConfirmationError('原图已变化，请重新识别当前页。','CONFLICT',409)
        from .source_images import images
        images.put(student,body['batch_id'],body['source_revision'],ai.prepare_image(body['image_data'],max_edge=2400))
    return registry.resume_page(student,body['batch_id'],body['source_revision'])
