from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.forms import ModelForm
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from judge.models import UserFile

__all__ = ['UserFileUploadForm', 'UserFileEditForm']


class UserFileUploadForm(ModelForm):
    """Form for uploading new user files."""
    
    file = forms.FileField(
        required=True,
        help_text=_('Maximum file size is %s.') % filesizeformat(getattr(settings, 'USER_FILE_MAX_SIZE', 10 * 1024 * 1024)),
        label=_('File'),
    )
    
    class Meta:
        model = UserFile
        fields = ['file', 'file_type', 'description', 'is_public']
        labels = {
            'file_type': _('File Type'),
            'description': _('Description (optional)'),
            'is_public': _('Make Public'),
        }
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Add an optional description for this file'),
            }),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_file(self):
        """Validate uploaded file."""
        file = self.cleaned_data.get('file')
        
        if file:
            # Check file size
            max_size = getattr(settings, 'USER_FILE_MAX_SIZE', 10 * 1024 * 1024)  # Default 10MB
            if file.size > max_size:
                raise ValidationError(
                    _('File size exceeds the maximum allowed size of %s.')
                    % filesizeformat(max_size)
                )
            
            # Check file extension - allow most common types
            allowed_extensions = getattr(settings, 'USER_FILE_ALLOWED_EXTENSIONS', [
                'cpp', 'c', 'java', 'py', 'js', 'h', 'hpp', 'pas', 'rb',
                'txt', 'pdf', 'doc', 'docx', 'zip', 'tar', 'gz', 'rar',
                'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg',
            ])
            
            file_ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
            if file_ext not in allowed_extensions:
                raise ValidationError(
                    _('File type ".%(ext)s" is not allowed. Allowed types: %(types)s')
                    % {
                        'ext': file_ext,
                        'types': ', '.join(allowed_extensions),
                    }
                )
        
        return file


class UserFileEditForm(ModelForm):
    """Form for editing user file metadata."""
    
    class Meta:
        model = UserFile
        fields = ['description', 'is_public']
        labels = {
            'description': _('Description'),
            'is_public': _('Make Public'),
        }
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
            }),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
