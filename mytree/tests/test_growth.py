"""Historical score caps, evidence dates and monotonic random edit sequences."""
from datetime import datetime,timedelta
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import growth,store,tree
from app.knowledge import KP
from app.schedule import TZ


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start()
        self.instant=datetime(2026,11,16,18,0,tzinfo=TZ);self.clock=patch('app.growth.now',side_effect=lambda:self.instant);self.clock.start();self.sequence=0
        def seed(value):
            for key in KP:
                value['knowledge_cards'][key]={'id':key,'knowledge_id':key,'status':'active'}
                value['growth_events'].append({'id':'scale_'+key,'kind':'scale','knowledge_id':key,'points':10,'at':self.instant.isoformat()})
        store.update('owner',seed)
    def tearDown(self):self.clock.stop();self.patch.stop();self.temp.cleanup()
    def get(self):return growth.get('owner',{})
    def move(self,params):
        self.sequence+=1
        return tree.move('owner',{'method':'menu','expected_revision':tree.get('owner')['revision'],**params},'edit'+str(self.sequence))['output']

    def test_components_sum_to_total_and_weekly_delta_has_explicit_timezone(self):
        result=self.get();self.assertEqual(result['total'],370);self.assertEqual(result['total'],sum(result['components'].values()))
        self.assertEqual(result['weekly_delta'],370);self.assertEqual(result['period']['timezone'],'Asia/Shanghai')
        self.assertEqual(result['period']['week_start'],'2026-11-16')
        self.instant+=timedelta(days=7);self.assertEqual(self.get()['weekly_delta'],0);self.assertEqual(self.get()['total'],370)

    def test_scale_historical_knowledge_dedup_survives_removal_and_readding(self):
        before=self.get()['total']
        def duplicate(value):
            value['growth_events'].append({**value['growth_events'][0],'id':'duplicate'})
            value['knowledge_cards']['F1']['status']='removed'
        store.update('owner',duplicate);self.assertEqual(self.get()['total'],before)
        store.update('owner',lambda value:value['knowledge_cards']['F1'].update(status='active'))
        self.assertEqual(self.get()['total'],before)

    def test_lushness_requires_three_day_spacing_and_caps_at_three_per_knowledge(self):
        for day,expected in ((2,0),(3,3),(4,3),(6,6),(9,9),(12,9)):
            self.instant=datetime(2026,11,16,18,0,tzinfo=TZ)+timedelta(days=day)
            store.update('owner',lambda value:growth.record_review(value,'F1','fact'+str(day),self.instant))
            self.assertEqual(self.get()['components']['lushness'],expected)

    def test_old_or_future_answer_cannot_farm_lushness_by_delayed_submission(self):
        old=self.instant;self.instant+=timedelta(days=4)
        store.update('owner',lambda value:growth.record_review(value,'F1','old',self.instant,old))
        store.update('owner',lambda value:growth.record_review(value,'F1','future',self.instant,self.instant+timedelta(days=1)))
        self.assertEqual(self.get()['components']['lushness'],0)

    def test_unlocked_card_is_required_for_lushness(self):
        self.instant+=timedelta(days=4)
        store.update('other',lambda value:growth.record_review(value,'F1','fact',self.instant))
        self.assertEqual(growth.get('other',{})['total'],0)

    def test_relation_cap_is_twenty_directed_pairs_and_reverse_or_unknown_awards_zero(self):
        for key,(_,_,pre) in KP.items():
            if pre:self.move({'action':'link','card_id':pre,'target_card_id':key,'relation_reason':'从前置规则理解下一步。'})
        self.assertEqual(self.get()['components']['relations'],40)
        self.move({'action':'link','card_id':'F2','target_card_id':'F1','relation_reason':'我的反向回顾。'})
        self.move({'action':'link','card_id':'F1','target_card_id':'G1','relation_reason':'我想到的另一种联系。'})
        self.assertEqual(self.get()['components']['relations'],40)

    def test_random_move_link_undo_remove_and_readd_sequence_is_monotone(self):
        rng=random.Random(2323);previous=self.get()['total'];latest=None
        for index in range(80):
            choice=rng.choice(('move','link','undo','remove'))
            if choice=='move':latest=self.move({'action':'move','card_id':'F1','parent_id':None,'position':{'x':rng.randint(0,500),'y':rng.randint(0,400)}})
            elif choice=='link':latest=self.move({'action':'link','card_id':'F1','target_card_id':'F2','relation_reason':'用公因式回顾平方差。'})
            elif choice=='undo' and latest:
                self.move({'action':'undo','undo_token':latest['undo']['token']});latest=None
            else:
                store.update('owner',lambda value:value['knowledge_cards']['E1'].update(status='removed' if index%2 else 'active'))
            result=self.get();self.assertGreaterEqual(result['total'],previous)
            self.assertEqual(result['total'],sum(result['components'].values()));previous=result['total']
        self.assertLessEqual(self.get()['components']['relations'],2)

    def test_leaderboard_never_fabricates_other_children_or_ranks(self):
        result=growth.leaderboard('owner',{'group_id':'local_only'})
        self.assertEqual(result['entries'],[]);self.assertNotIn('self_entry',result)

if __name__=='__main__':unittest.main(verbosity=2)
