from django.urls import path
from resumable_upload.views import TusdHookView, UploadIntentView

app_name = 'resumable_upload'

urlpatterns = [
    path('intent/', UploadIntentView.as_view(), name='upload_intent'),
    path('hooks/', TusdHookView.as_view(), name='tusd_hooks'),
]
