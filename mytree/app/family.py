"""Read-only facts for the current account's own profile in verified parent mode."""
from . import auth, parent_access, profile


def overview(account,header=''):
    parent_access.require(account,header)
    p=profile.get(account['profile_id'])
    return {'mode':'same-account','email':account['email'],'profile':{
        'practice_correct':p['practice_correct'],
        'knowledge_count':sum(bool(k['lit']) for k in p['tree']),
        'review_count':len(p['reviews']),
        'recent':[{'type':e.get('type',''),'at':e.get('at',e.get('time',''))} for e in p['recent'][:5]]},
        'message':'当前账号的学习记录；家长密码仅用于模式隔离。'}


def handle(account,action,body):
    # Historical links/invites are retained in storage, never read or converted.
    raise auth.AuthError('邀请配对已停用，请使用同一账号的家长端。','PARENT_LEGACY_DISABLED',410)
