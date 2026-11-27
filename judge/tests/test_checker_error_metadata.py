import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from judge.bridge.judge_handler import JudgeHandler
from judge.models import Submission


class CheckerErrorMetadataTest(SimpleTestCase):
    def test_bridge_keeps_ie_and_only_stores_checker_metadata(self):
        handler = object.__new__(JudgeHandler)
        handler.name = 'judge'
        handler.judge_address = None
        handler._free_self = Mock()
        handler._post_update_submission = Mock()
        message = 'checker traceback\nwith a second line'
        for tag in (None, 'checker', 'unknown', ['checker']):
            with self.subTest(tag=tag), patch('judge.bridge.judge_handler.Submission') as model, \
                    patch('judge.bridge.judge_handler.event.post'), \
                    patch('judge.bridge.judge_handler.logger.exception'):
                model.objects.filter.return_value.update.return_value = 1
                packet = {'submission-id': 42, 'message': message}
                if tag is not None:
                    packet['error-type'] = tag
                handler.on_internal_error(packet)

                update = model.objects.filter.return_value.update.call_args.kwargs
                self.assertEqual((update['status'], update['result']), ('IE', 'IE'))
                classified, decoded = Submission(status='IE', error=update['error']).internal_error_info
                self.assertEqual(classified, tag == 'checker')
                self.assertEqual(decoded, message)
                if tag == 'checker':
                    self.assertEqual(json.loads(update['error'])['error-type'], 'checker')
                else:
                    self.assertEqual(update['error'], message)
                handler._post_update_submission.assert_called_with(42, 'internal-error', done=True)

    def test_legacy_malformed_and_unknown_errors_keep_original_text(self):
        for error in (None, 'legacy traceback', '{bad json', '{"version":"2","error-type":"checker","message":"text"}',
                      '{"version":"1","error-type":"checker","message":[]}', '{"version":"1","message":"text"}'):
            with self.subTest(error=error):
                self.assertEqual(Submission(status='IE', error=error).internal_error_info, (False, error))

    def test_compile_message_is_not_interpreted_as_checker_metadata(self):
        message = '{"version":"1","error-type":"checker","message":"text"}'
        self.assertEqual(Submission(status='CE', error=message).internal_error_info, (False, message))
