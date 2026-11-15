"""Child-controlled knowledge-card placements, groups, links and latest undo."""
import copy
import math
import uuid

from . import contract,growth,store
from .errors import DomainError
from .knowledge import KP


def _tree(value):
    saved=value['tree']
    saved.setdefault('revision',0);saved.setdefault('placements',[]);saved.setdefault('groups',[]);saved.setdefault('links',[])
    return saved


def get(student):
    value=store.read(student);saved=_tree(value)
    active={card['id'] for card in value['knowledge_cards'].values() if card['status']=='active'}
    return contract.definition('TreeGetOutput',{'revision':saved['revision'],
        'skeleton':[{'id':key,'name':item[0],'pre':item[2]} for key,item in KP.items()],
        'placements':[item for item in saved['placements'] if item['card_id'] in active],
        'groups':saved['groups'],'links':[item for item in saved['links'] if item['from'] in active and item['to'] in active]})


def _card(value,identity):
    card=value['knowledge_cards'].get(identity)
    if card is None or card['status']!='active':raise DomainError('NOT_FOUND','请先选一张已解锁、仍在使用的知识卡。',404)
    return card


def _placement(saved,card_id):
    return next((item for item in saved['placements'] if item['card_id']==card_id),None)


def _relation(saved,source,target,reason,value):
    src=source['knowledge_id'];dst=target['knowledge_id']
    if KP[dst][2]==src:
        event_id=growth.record_relation(value,src,dst)
        return {'status':'reference_match','awarded_points':2 if event_id else 0,
                'reason':'这与参考目录的前置关系一致。'+('关联成长已记录。' if event_id else '这对关系已有历史记录或已达到参考计分上限。')},event_id
    if KP[src][2]==dst:
        key=src+':'+dst;warned=saved.setdefault('_warned_pairs',[]);first=key not in warned
        if first:warned.append(key)
        return {'status':'contradiction','awarded_points':0,'reason':
                '参考目录的前置方向相反，可以再想想条件；你的连线会保留，不扣分。' if first else '你的这条想法已保留，参考计分没有变化。'},None
    return {'status':'learner_link','awarded_points':0,'reason':'参考目录没有这一对前置关系，保留你的解释，不据此判错或计分。'},None


def move(student,params,request_id):
    contract.definition('TreeMoveInput',params)
    def commit(value,_):
        saved=_tree(value);revision=saved['revision']
        if params['expected_revision']!=revision:
            raise DomainError('CONFLICT','知识树在另一个页面里更新了，请重新读取再移动。',409,current_revision=revision)
        action=params['action'];extra={};effects=[]
        if action=='undo':
            undo=saved.get('_undo')
            if not undo or undo['token']!=params['undo_token'] or undo['revision']!=revision:
                raise DomainError('CONFLICT','只能撤销最近的一次整理，请重新读取知识树。',409,current_revision=revision)
            for field in ('placements','groups','links'):saved[field]=copy.deepcopy(undo['before'][field])
            saved.pop('_undo',None);token='used_'+uuid.uuid4().hex
        else:
            card=_card(value,params['card_id'])
            before={field:copy.deepcopy(saved[field]) for field in ('placements','groups','links')}
            placed=_placement(saved,card['id'])
            if action=='move':
                position=params['position'];parent=params['parent_id']
                if any(not math.isfinite(n) or abs(n)>10000 for n in position.values()):raise DomainError('INVALID_INPUT','位置超出可整理的范围。')
                valid={item['id'] for item in saved['groups']}|set(KP)|{item['id'] for item in value['knowledge_cards'].values() if item['status']=='active'}
                if parent is not None and parent not in valid:raise DomainError('NOT_FOUND','放入的位置已经改变，请重新选择。',404)
                ancestor=parent;seen={card['id']}
                while ancestor is not None:
                    if ancestor in seen:raise DomainError('INVALID_INPUT','不能把卡片放到自己的下层。')
                    seen.add(ancestor);node=_placement(saved,ancestor);ancestor=node['parent_id'] if node else None
                next_place={'card_id':card['id'],'parent_id':parent,'position':copy.deepcopy(position)}
                if placed:placed.update(next_place)
                else:saved['placements'].append(next_place)
                extra['placement']=next_place
            elif action=='group':
                title=params['group_title'].strip()
                if not title:raise DomainError('INVALID_INPUT','给这一组起个名字吧。')
                group=next((item for item in saved['groups'] if item['title']==title),None)
                if group is None:
                    if len(saved['groups'])>=1000:raise DomainError('INVALID_INPUT','分组数量已达本机上限。')
                    group={'id':uuid.uuid4().hex,'title':title};saved['groups'].append(group)
                if placed:placed['parent_id']=group['id']
                else:
                    placed={'card_id':card['id'],'parent_id':group['id'],'position':{'x':0,'y':0}}
                    saved['placements'].append(placed)
                extra['placement']=placed
            else:
                target=_card(value,params['target_card_id'])
                if target['id']==card['id']:raise DomainError('INVALID_INPUT','请选择另一张知识卡来建立关系。')
                existing=next((link for link in saved['links'] if link['from']==card['id'] and link['to']==target['id']),None)
                link={'from':card['id'],'to':target['id'],'relation_reason':params['relation_reason']}
                if existing:existing.update(link)
                else:saved['links'].append(link)
                assessment,event_id=_relation(saved,card,target,params['relation_reason'],value)
                extra['relation_assessment']=assessment
                if event_id:effects.append({'kind':'update_growth','id':event_id,'idempotent_replay':False})
            token=uuid.uuid4().hex;saved['_undo']={'token':token,'revision':revision+1,'before':before}
        saved['revision']=revision+1
        output={'revision':saved['revision'],'undo':{'token':token,'previous_revision':revision},**extra}
        effects.insert(0,{'kind':'move_card','id':params.get('card_id') or token,'idempotent_replay':False})
        return {'status':'ok','verification':{'level':'unavailable','label':'位置由你整理；关系仅对照本机参考目录'},'output':output,'effects':effects}
    return store.command(student,'tree.move',request_id,params,lambda:None,commit,
                         validate=lambda result:contract.definition('TreeMoveOutput',result['output']))
