"""T1: migration, atomic storage, server failures, and hint-access facts."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import profile, store
from test_all import _req, _serve


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = profile._PATH
        profile._PATH = str(Path(self.temp.name, 'profiles.json'))

    def tearDown(self):
        profile._PATH = self.old
        self.temp.cleanup()

    def seed(self, student='learner'):
        return store.update(student, lambda value: value['events'].append(
            {'id':'diag1','type':'diagnosis','status':'wrong_step','analysis':{}}))

    def test_old_profile_preserves_existing_learning_data(self):
        old={'causes':{'F-SIGN':2},'lit':['F2'],'reviews':{'F2':{'due':'2026-11-15T19:30+08:00'}},
             'exercises':{'exercise1':{'correct':True}},'history':5,'custom_old_field':{'keep':True}}
        Path(profile._PATH).write_text(json.dumps({'learner':old}))
        before=Path(profile._PATH).read_bytes()
        value=store.read('learner')
        for key, content in old.items():self.assertEqual(value[key],content)
        for key, expected in store.COLLECTIONS.items():self.assertIsInstance(value[key],expected)
        # Reading an old profile does not write or erase it as a side effect.
        self.assertEqual(Path(profile._PATH).read_bytes(),before)
        store.update('learner',lambda data:data['reminders'].update({'today':{'ack':True}}))
        saved=json.loads(Path(profile._PATH).read_text())['learner']
        for key,content in old.items():self.assertEqual(saved[key],content)
        self.assertEqual(saved['reminders']['today'],{'ack':True})

    def test_new_collections_and_profiles_do_not_share_mutable_state(self):
        store.update('a',lambda value:value['tree'].update({'revision':1}))
        self.assertEqual(store.read('b')['tree'],{})
        value=store.read('a');value['tree']['revision']=99
        self.assertEqual(store.read('a')['tree']['revision'],1)

    def test_callback_failure_does_not_commit(self):
        self.seed();before=Path(profile._PATH).read_bytes()
        def fail(value):
            value['wrong_cards']['new']='not committed'
            raise ValueError('stop')
        with self.assertRaises(ValueError):store.update('learner',fail)
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_replace_failure_keeps_whole_previous_file_and_removes_temp(self):
        self.seed();before=Path(profile._PATH).read_bytes()
        with patch('app.profile.os.replace',side_effect=OSError('injected disk failure')):
            with self.assertRaises(store.StorageFailed) as error:
                store.update('learner',lambda value:value['wrong_cards'].update({'new':{'id':'new'}}))
        self.assertEqual(error.exception.code,'STORAGE_FAILED')
        self.assertEqual(Path(profile._PATH).read_bytes(),before)
        self.assertNotIn('new',store.read('learner')['wrong_cards'])
        self.assertFalse(list(Path(self.temp.name).glob('.mytree-*.tmp')))

    def test_failed_flush_cannot_replace_previous_profile(self):
        self.seed();before=Path(profile._PATH).read_bytes()
        with patch('app.profile.os.fsync',side_effect=OSError('injected fsync failure')):
            with self.assertRaises(store.StorageFailed):
                store.update('learner',lambda value:value.update(history=99))
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_corrupt_or_wrong_type_store_is_not_silently_overwritten(self):
        for content in ['{unfinished','[]',json.dumps({'learner':{'wrong_cards':[]}})]:
            Path(profile._PATH).write_text(content)
            with self.assertRaises(store.StorageFailed):store.read('learner')
            self.assertEqual(Path(profile._PATH).read_text(),content)

    def test_concurrent_transactions_do_not_lose_updates(self):
        def increment(_):
            store.update('learner',lambda value:value.update(history=value['history']+1))
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(increment,range(64)))
        self.assertEqual(store.read('learner')['history'],64)
        self.assertEqual(stat.S_IMODE(Path(profile._PATH).stat().st_mode),0o600)

    def test_hint_levels_are_saved_deduplicated_and_never_decrease(self):
        self.seed()
        self.assertEqual(store.max_hint_level('learner','diag1'),0)
        first=store.record_hint_view('learner','diag1',1)
        self.assertEqual(store.record_hint_view('learner','diag1',1),first)
        self.assertEqual(store.record_hint_view('learner','diag1',2)['max_hint_level'],2)
        self.assertEqual(store.record_hint_view('learner','diag1',1)['max_hint_level'],2)
        saved=store.read('learner')['hint_views']
        self.assertEqual(len(saved),2)
        self.assertTrue(all(item['at'].endswith('+08:00') for item in saved))
        self.assertEqual(store.max_hint_level('learner','diag1'),2)

    def test_invalid_hint_or_foreign_diagnosis_does_not_write(self):
        self.seed();before=Path(profile._PATH).read_bytes()
        for level in [True,0,4,'2']:
            with self.assertRaises(ValueError):store.record_hint_view('learner','diag1',level)
        with self.assertRaises(ValueError):store.record_hint_view('other','diag1',3)
        with self.assertRaises(ValueError):store.record_hint_view('learner','missing',3)
        self.assertEqual(Path(profile._PATH).read_bytes(),before)

    def test_http_write_failure_has_storage_code_and_no_saved_progress(self):
        httpd,base=_serve()
        try:
            self.seed();before=Path(profile._PATH).read_bytes()
            with patch('app.profile.os.replace',side_effect=OSError('do not expose this text')):
                status,raw=_req(base,'POST','/api/availability',{'student':'learner','availability':{'days':[2],'time':'18:15'}})
            self.assertEqual(status,503)
            result=json.loads(raw);self.assertEqual(result['code'],'STORAGE_FAILED')
            self.assertNotIn('do not expose',str(result))
            self.assertEqual(Path(profile._PATH).read_bytes(),before)
        finally:
            httpd.shutdown();httpd.server_close()


if __name__=='__main__':
    unittest.main(verbosity=2)
