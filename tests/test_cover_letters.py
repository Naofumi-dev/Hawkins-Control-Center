"""Cover-letter assistance: mocked provider, no real messages or paid calls."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from client_finder.agents import TaskModel, TaskRunner
from client_finder.providers import ProviderError

CONTEXT = {
    "task": {"task_type": "cover_letter"},
    "job": {"questions": ["What relevant work have you built?"]},
    "profile_facts": ["Built an intake demo."],
    "verified_proofs": [{"proof_url": "https://proof.example/intake"}],
}
OUTPUT = {
    "summary": "Connects the intake need to a reviewed demo.",
    "evidence": ["Built an intake demo."], "missing": [], "suggested_category": "",
    "draft_body": "I can help your team track each intake and its next step. I built an intake demo and can walk you through it: https://proof.example/intake",
    "screening_answers": [{"question": "What relevant work have you built?", "answer": "Built an intake demo."}],
}


class CoverLetterModelTests(unittest.TestCase):
    def generate(self, output, database=None):
        response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
                "client_finder.agents.request_json", return_value=response) as request:
            result = TaskModel(database or Mock()).generate("Steve", CONTEXT)
        return result, request.call_args.kwargs['payload']

    def test_output_focused_letter_and_answers_are_separate_bounded_fields(self):
        result, payload = self.generate(copy.deepcopy(OUTPUT))
        self.assertEqual(result, OUTPUT)
        self.assertNotIn('screening_answers', result['draft_body'])
        self.assertIn("employer's stated need", payload['messages'][0]['content'])
        self.assertIn('70-110 words', payload['messages'][0]['content'])
        self.assertIn('screening_answers', payload['response_format']['json_schema']['schema']['required'])
        self.assertEqual(payload['max_tokens'], 1200)

    def test_long_cover_letter_is_held_for_review(self):
        output = {**OUTPUT, 'draft_body': 'word '*131}
        with self.assertRaises(ProviderError): self.generate(output)

    def test_invented_screening_question_is_rejected(self):
        output = {**OUTPUT, 'screening_answers': [{'question': 'Invented question', 'answer': 'Yes'}]}
        with self.assertRaises(ProviderError): self.generate(output)

    def test_unverified_link_cannot_be_hidden_in_screening_answer(self):
        output = copy.deepcopy(OUTPUT)
        output['screening_answers'][0]['answer'] = 'See https://invented.example'
        with self.assertRaises(ProviderError): self.generate(output)

    def test_missing_required_answer_must_be_explicit(self):
        output = copy.deepcopy(OUTPUT)
        output['screening_answers'][0]['answer'] = ''
        with self.assertRaises(ProviderError): self.generate(output)
        output['missing'] = ['Confirm the relevant experience.']
        self.assertEqual(self.generate(output)[0]['missing'], output['missing'])

    def test_no_provider_request_when_shared_budget_is_exhausted(self):
        db = Mock()
        db.reserve_cost.side_effect = ProviderError('budget exhausted')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}), patch('client_finder.agents.request_json') as request:
            with self.assertRaises(ProviderError): TaskModel(db).generate('Steve', CONTEXT)
        request.assert_not_called()


class CoverLetterWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.task = {'id':'draft-task','agent':'Steve','task_type':'cover_letter','title':'Prepare letter',
                     'opportunity_id':'opportunity','dependency_id':'brief-task','context_version':2,'lease_id':'lease'}
        self.resource = {'id':'profile','kind':'profile','version':'v1','content':'Built an intake demo.','url':None}
        self.brief = {'id':'brief-task','task_type':'qualify_job','opportunity_id':'opportunity',
                      'context_version':2,'status':'review','result':{'summary':'The employer needs a clear intake queue.','evidence':[],'missing':[]}}
        self.job = {'source_verified_at':'2026-10-05','context_version':2,'blockers':[],'questions':[]}
        self.db, self.model = Mock(), Mock()
        self.db.rpc.side_effect = lambda name, args: self.task if name == 'client_finder_task_claim' else None
        self.model.generate.return_value = copy.deepcopy(OUTPUT)

    def run_task(self):
        self.db.rows.side_effect = [[{'id':'opportunity'}], [], [self.resource], [self.job], [self.brief]]
        return TaskRunner(self.db, self.model).run_one()

    def test_current_brief_and_reviewed_resource_versions_reach_the_draft(self):
        self.assertEqual(self.run_task()['status'], 'review')
        context = self.model.generate.call_args.args[1]
        self.assertEqual(context['qualification_brief']['summary'], self.brief['result']['summary'])
        saved = self.db.rpc.call_args.args[1]['result']
        self.assertEqual(saved['source_resources'], [{'id':'profile','version':'v1'}])
        self.assertEqual([call.args[0] for call in self.db.rpc.call_args_list],
                         ['client_finder_task_claim','client_finder_task_context','client_finder_task_finish'])

    def test_stale_qualification_cannot_trigger_a_paid_draft(self):
        self.brief['context_version'] = 1
        self.assertEqual(self.run_task()['status'], 'blocked')
        self.model.generate.assert_not_called()
        self.assertIn('Eleven', self.db.rpc.call_args.args[1]['blocker'])

    def test_changed_job_is_blocked_before_a_paid_draft(self):
        self.job['context_version'] = 3
        self.assertEqual(self.run_task()['status'], 'blocked')
        self.model.generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
