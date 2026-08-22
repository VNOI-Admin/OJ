from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from judge.utils.views import add_file_response


class RemoteStorageResponseTest(SimpleTestCase):
    def test_add_file_response_reads_storage_without_path(self):
        storage = InMemoryStorage()
        storage.save('submission_file/aplusb/1/source.zip', ContentFile(b'archive-content'))
        request = RequestFactory().get('/download')
        response = HttpResponse()

        add_file_response(
            request,
            response,
            None,
            'submission_file/aplusb/1/source.zip',
            storage,
        )

        self.assertEqual(response.content, b'archive-content')
