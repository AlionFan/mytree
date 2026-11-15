"""Tree persistence, accessible methods, conflict isolation and latest undo."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import agent,contract,profile,store,tree


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start();self.sequence=0
        def seed(value):
            for key in ('F1','F2','E1'):value['knowledge_cards'][key]={'id':key,'knowledge_id':key,'status':'active'}
        store.update('owner',seed)
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def call(self,params,identity=None,status=200,student='owner'):
        self.sequence+=1
        envelope={'schema_version':'1.0','request_id':identity or 'request'+str(self.sequence),'operation':'tree.move',
                  'client':{'type':'web','name':'test','version':'1'},'subject':{'profile_id':student},'input':params}
        result,code=agent.handle(envelope);self.assertEqual(code,status,result);contract.response(result);return result
    def move(self,key='F1',method='menu',x=100,parent=None,revision=None):
        return self.call({'action':'move','method':method,'expected_revision':tree.get('owner')['revision'] if revision is None else revision,
                          'card_id':key,'parent_id':parent,'position':{'x':x,'y':80}})['output']
    def link(self,source='F1',target='F2'):
        return self.call({'action':'link','method':'menu','expected_revision':tree.get('owner')['revision'],
                          'card_id':source,'target_card_id':target,'relation_reason':'我想把前置规则连起来。'})['output']
    def undo(self,result):
        return self.call({'action':'undo','method':'keyboard','expected_revision':result['revision'],'undo_token':result['undo']['token']})['output']

    def test_get_is_read_only_and_reference_skeleton_has_no_forced_positions(self):
        before=Path(profile._PATH).read_bytes();result=tree.get('owner')
        self.assertEqual(len(result['skeleton']),37);self.assertEqual(result['placements'],[])
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_drag_keyboard_and_menu_persist_the_same_position(self):
        for method in ('drag','keyboard','menu'):
            result=self.move(method=method,x=120)
            saved=tree.get('owner')['placements'][0]
            self.assertEqual(saved['position'],{'x':120,'y':80});self.assertEqual(saved,result['placement'])
        self.assertEqual(tree.get('owner')['revision'],3)

    def test_group_creation_reuses_group_and_parent_positions_remain_child_controlled(self):
        for key in ('F1','F2'):
            self.call({'action':'group','method':'keyboard','expected_revision':tree.get('owner')['revision'],'card_id':key,'group_title':'我的公式'})
        result=tree.get('owner');self.assertEqual(len(result['groups']),1)
        self.assertEqual({item['parent_id'] for item in result['placements']},{result['groups'][0]['id']})
        self.move(parent=result['groups'][0]['id'],x=312)
        self.assertEqual(tree.get('owner')['placements'][0]['position']['x'],312)

    def test_reference_match_reverse_and_unknown_relations_keep_learner_reason(self):
        result=self.link();self.assertEqual(result['relation_assessment']['awarded_points'],2)
        result=self.link('F2','F1');self.assertEqual(result['relation_assessment']['status'],'contradiction')
        result=self.link('F1','E1');self.assertEqual(result['relation_assessment']['status'],'learner_link')
        self.assertEqual(result['relation_assessment']['awarded_points'],0)
        self.assertEqual(len(tree.get('owner')['links']),3)
        self.assertTrue(all(link['relation_reason'] for link in tree.get('owner')['links']))

    def test_stale_revision_returns_current_without_overwriting(self):
        self.move();before=Path(profile._PATH).read_bytes()
        result=self.call({'action':'move','method':'drag','expected_revision':0,'card_id':'F1','parent_id':None,'position':{'x':999,'y':999}},status=409)
        self.assertEqual(result['error']['current_revision'],1);self.assertEqual(before,Path(profile._PATH).read_bytes())

    def test_simultaneous_tabs_have_only_one_winner(self):
        def run(x):
            params={'action':'move','method':'menu','expected_revision':0,'card_id':'F1','parent_id':None,'position':{'x':x,'y':10}}
            envelope={'schema_version':'1.0','request_id':'tab'+str(x),'operation':'tree.move','client':{'type':'web','name':'test','version':'1'},'subject':{'profile_id':'owner'},'input':params}
            return agent.handle(envelope)[1]
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(run,(10,20)))
        self.assertEqual(sorted(codes),[200,409]);self.assertEqual(tree.get('owner')['revision'],1)

    def test_latest_undo_restores_before_state_and_cannot_be_reused(self):
        first=self.move(x=10);second=self.move(x=20)
        self.call({'action':'undo','method':'menu','expected_revision':2,'undo_token':first['undo']['token']},status=409)
        result=self.undo(second);self.assertEqual(result['revision'],3)
        self.assertEqual(tree.get('owner')['placements'][0]['position']['x'],10)
        self.call({'action':'undo','method':'menu','expected_revision':3,'undo_token':second['undo']['token']},status=409)

    def test_undo_removes_link_but_historical_relation_growth_stays(self):
        result=self.link();before=store.read('owner')['growth_events']
        self.undo(result);self.assertEqual(tree.get('owner')['links'],[])
        self.assertEqual(store.read('owner')['growth_events'],before)
        result=self.link();self.assertEqual(result['relation_assessment']['awarded_points'],0)

    def test_unknown_removed_foreign_or_wrong_cards_cannot_be_placed(self):
        for key in ('missing','wrong'):
            self.call({'action':'move','method':'menu','expected_revision':0,'card_id':key,'parent_id':None,'position':{'x':0,'y':0}},status=404)
        self.call({'action':'move','method':'menu','expected_revision':0,'card_id':'F1','parent_id':None,'position':{'x':0,'y':0}},student='other',status=404)
        store.update('owner',lambda value:value['knowledge_cards']['F1'].update(status='removed'))
        self.call({'action':'move','method':'menu','expected_revision':0,'card_id':'F1','parent_id':None,'position':{'x':0,'y':0}},status=404)

    def test_cycles_unknown_parent_and_nonfinite_positions_are_rejected(self):
        self.move('F1',parent='F2')
        for parent in ('F1','missing'):
            self.call({'action':'move','method':'menu','expected_revision':1,'card_id':'F2','parent_id':parent,'position':{'x':1,'y':1}},status=404 if parent=='missing' else 400)
        self.call({'action':'move','method':'menu','expected_revision':1,'card_id':'F2','parent_id':None,'position':{'x':float('inf'),'y':1}},status=400)
        self.assertEqual(tree.get('owner')['revision'],1)

    def test_write_failure_rolls_back_tree_and_growth(self):
        before=Path(profile._PATH).read_bytes()
        with patch('app.profile.os.replace',side_effect=OSError('private')):
            self.call({'action':'link','method':'menu','expected_revision':0,'card_id':'F1','target_card_id':'F2','relation_reason':'先有公因式再看公式。'},status=503)
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

if __name__=='__main__':unittest.main(verbosity=2)
