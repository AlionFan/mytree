"""DESIGN-001 mechanism cases. No model calls or photographs are used."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.readings import disambiguate


def candidates(quote=None, kind='integer_list', reference=2):
    return [dict(id='read-'+str(value), group='line-1', line=1,
                 text=r'$-2<x\le '+str(value)+'$',
                 evidence=[] if quote is None else [dict(line=reference, quote=quote, kind=kind)],
                 # Upstream flags are not authoritative.
                 selected=value == 2, consistency='match') for value in (2, 7)]


class ReadingConsistencyTests(unittest.TestCase):
    def test_d1_unique_integer_context_chooses_two(self):
        quote='整数解为 -1,0,1,2'
        result=disambiguate('题干', [r'$-2<x\le ?$',quote], [1], candidates(quote))
        self.assertEqual(result['steps'][0], r'$-2<x\le 2$')
        self.assertTrue(result['inferred'])
        self.assertIn('整数解',result['reading_evidence'])
        self.assertEqual([a['id'] for a in result['alternatives'] if a['selected']], ['read-2'])

    def test_d2_wrong_student_value_seven_is_preserved(self):
        quote='整数解为 -1,0,1,2,3,4,5,6,7'
        result=disambiguate('解题条件算出的正确上界为2，但不得用来消歧',
                            [r'$-2<x\le ?$',quote], [1], candidates(quote))
        self.assertTrue(result['inferred'])
        self.assertEqual(result['steps'][0],r'$-2<x\le 7$')
        self.assertEqual([a['id'] for a in result['alternatives'] if a['selected']], ['read-7'])

    def test_d3_no_student_context_keeps_alternatives(self):
        result=disambiguate('题干', [r'$-2<x\le ?$'], [1], candidates())
        self.assertFalse(result['inferred'])
        self.assertEqual(len(result['alternatives']),2)
        self.assertTrue(all(a['consistency']=='unverified' and not a['selected'] for a in result['alternatives']))
        self.assertIn('没有其他线索', result['reading_evidence'])

    def test_d4_clear_seven_does_not_get_corrected_by_later_list(self):
        quote='整数解为 -1,0,1,2'
        result=disambiguate('题干', [r'$-2<x\le 7$',quote], [], candidates(quote))
        self.assertFalse(result['inferred'])
        self.assertEqual(result['steps'][0], r'$-2<x\le 7$')
        self.assertIn('矛盾', result['reading_evidence'])
        self.assertEqual(len(result['alternatives']),2)

    def test_d5_crossed_out_ink_is_excluded(self):
        result=disambiguate('题干', ['[划掉:7]2'])
        self.assertEqual(result['steps'],['2'])
        self.assertFalse(result['inferred'])
        self.assertIn('划掉',result['reading_evidence'])

    def test_compact_integer_range_is_bounded(self):
        quote='整数解: -1..7'
        result=disambiguate('题干', ['?',quote],[1],candidates(quote))
        self.assertEqual(result['steps'][0],r'$-2<x\le 7$')
        quote='整数解: -1..9999'
        result=disambiguate('题干',['?',quote],[1],candidates(quote))
        self.assertFalse(result['inferred'])

    def test_printed_question_cannot_impersonate_student_evidence(self):
        quote='整数解为 -1,0,1,2'
        result=disambiguate(quote,['?'],[1],candidates(quote,reference=0))
        self.assertFalse(result['inferred'])
        self.assertTrue(all(a['consistency']=='unverified' for a in result['alternatives']))

    def test_invented_quote_does_not_choose_a_value(self):
        result=disambiguate('题干',['?','没有写整数解'],[1],candidates('整数解为 -1,0,1,2'))
        self.assertFalse(result['inferred'])

    def test_multiple_matching_candidates_do_not_force_a_choice(self):
        quote='整数解为 -1,0,1,2'
        alternatives=candidates(quote)
        alternatives[1]['text']=r'$-2<x<3$'
        result=disambiguate('题干',['?',quote],[1],alternatives)
        self.assertFalse(result['inferred'])
        self.assertEqual(result['steps'][0],'?')

    def test_contradictory_student_evidence_does_not_force_a_choice(self):
        q1='整数解为 -1,0,1,2'
        q2='整数解为 -1,0,1,2,3,4,5,6,7'
        alternatives=candidates(q1)
        for item in alternatives:
            item['evidence'].append(dict(line=3,quote=q2,kind='integer_list'))
        result=disambiguate('题干',['?',q1,q2],[1],alternatives)
        self.assertFalse(result['inferred'])
        self.assertTrue(all(a['consistency']=='conflict' for a in result['alternatives']))

    def test_repeat_copies_existing_wrong_writing_without_solving(self):
        alternatives=[dict(id='v'+str(n),group='one',line=1,text='$x='+str(n)+'$',
                           evidence=[dict(line=2,quote='$x=7$',kind='repeat')]) for n in (2,7)]
        result=disambiguate('2x=4',['$x=?$','$x=7$'],[1],alternatives)
        self.assertTrue(result['inferred'])
        self.assertEqual(result['steps'][0],'$x=7$')

    def test_previous_terminal_value_is_copied_not_recalculated(self):
        alternatives=[dict(id='v'+str(n),group='one',line=2,text=str(n),
                           evidence=[dict(line=1,quote='$2+2=7$',kind='previous')]) for n in (4,7)]
        result=disambiguate('计算2+2',['$2+2=7$','?'],[2],alternatives)
        self.assertEqual(result['steps'][1],'7')
        # Without a written terminal value, no arithmetic is used to choose 4.
        for item in alternatives:item['evidence'][0]['quote']='$2+2$'
        result=disambiguate('计算2+2',['$2+2$','?'],[2],alternatives)
        self.assertFalse(result['inferred'])

    def test_crossed_only_line_is_removed_and_references_are_remapped(self):
        quote='整数解为 -1,0,1,2'
        alternatives=candidates(quote, reference=3)
        result=disambiguate('题干',['?','[划掉:7]',quote],[1],alternatives)
        self.assertEqual(len(result['steps']),2)
        self.assertEqual(result['alternatives'][0]['evidence'][0]['line'],2)

    def test_invalid_or_oversized_candidate_groups_are_rejected(self):
        for alternatives in ([candidates()[0]], candidates()*2,
                             [dict(id='a',group='a',line=999,text='2',evidence=[]),candidates()[1]]):
            with self.assertRaises(ValueError):disambiguate('题干',['?'],[1],alternatives)

    def test_input_is_not_mutated_and_unmatched_strikes_are_kept(self):
        alternatives=candidates()
        original=copy.deepcopy(alternatives)
        result=disambiguate('题干',['[划掉:7?'],[1],alternatives)
        self.assertEqual(alternatives,original)
        self.assertEqual(result['steps'],['[划掉:7?'])


if __name__=='__main__':
    unittest.main(verbosity=2)
