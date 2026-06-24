import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from io import BytesIO
from pretix.base.forms.questions import CroppedImageField
from pretix.base.models import Question, Event, Organizer

@pytest.fixture
def image_file():
   def _create(width, height):
       f = BytesIO()
       image = Image.new('RGB', (width, height), 'white')
       image.save(f, 'JPEG')
       f.seek(0)
       return SimpleUploadedFile('test.jpg', f.read(), content_type='image/jpeg')
   return _create

from django import forms

@pytest.mark.django_db
def test_cropped_image_field_ratio_3_4(image_file):
    field = CroppedImageField(ratio='3:4', widget=forms.FileInput())
    assert field.clean(image_file(300, 400))
    with pytest.raises(ValidationError) as excinfo:
        field.clean(image_file(400, 300))
    assert excinfo.value.code == 'aspect_ratio_wrong'

@pytest.mark.django_db
def test_cropped_image_field_ratio_1_1(image_file):
    field = CroppedImageField(ratio='1:1', widget=forms.FileInput())
    assert field.clean(image_file(300, 300))
    with pytest.raises(ValidationError) as excinfo:
        field.clean(image_file(300, 400))
    assert excinfo.value.code == 'aspect_ratio_wrong'

@pytest.mark.django_db
def test_cropped_image_field_free_crop(image_file):
    field = CroppedImageField(ratio=None, widget=forms.FileInput())
    assert field.clean(image_file(300, 400))
    assert field.clean(image_file(400, 300))
    assert field.clean(image_file(300, 300))

from django.utils.timezone import now
from django_scopes import scope

@pytest.mark.django_db
def test_question_model_backward_compatibility():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        e = Event.objects.create(organizer=o, name='Dummy', slug='dummy', date_from=now())
        q = Question.objects.create(event=e, question='Test', type='F', valid_file_ratio='3:4')
        
        assert q.valid_file_portrait is True
        
        q.valid_file_portrait = False
        q.save()
        assert q.valid_file_ratio is None
        
        q.valid_file_portrait = True
        q.save()
        assert q.valid_file_ratio == '3:4'

from pretix.control.forms.item import QuestionForm
from django.http import QueryDict

@pytest.mark.django_db
def test_question_form_ratio_logic():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        e = Event.objects.create(organizer=o, name='Dummy', slug='dummy', date_from=now())
        item = e.items.create(name='Item', default_price=10)
        
        data = {
            'question_0': 'Q',
            'type': 'F',
            'items': [item.pk],
            'required': False,
            'ask_during_checkin': False,
            'show_during_checkin': False,
            'hidden': False,
            'valid_file_ratio': '',
            'identifier': 'TEST1'
        }
        qd = QueryDict('', mutable=True)
        qd.update(data)
        qd.setlist('items', [item.pk])
        form = QuestionForm(data=qd, instance=Question(event=e))
        assert form.is_valid(), form.errors
        assert form.cleaned_data['valid_file_ratio'] is None
        
        data['valid_file_ratio'] = '1:1'
        data['identifier'] = 'TEST2'
        qd = QueryDict('', mutable=True)
        qd.update(data)
        qd.setlist('items', [item.pk])
        form = QuestionForm(data=qd, instance=Question(event=e))
        assert form.is_valid(), form.errors
        assert form.cleaned_data['valid_file_ratio'] == '1:1'

        data['valid_file_ratio'] = 'free'
        data['identifier'] = 'TEST3'
        qd = QueryDict('', mutable=True)
        qd.update(data)
        qd.setlist('items', [item.pk])
        form = QuestionForm(data=qd, instance=Question(event=e))
        assert form.is_valid(), form.errors
        assert form.cleaned_data['valid_file_ratio'] == 'free'
