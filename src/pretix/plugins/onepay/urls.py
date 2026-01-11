from django.urls import re_path
from .views import ReturnView

event_patterns = [
    re_path(r'^onepay/return/', ReturnView.as_view(), name='return'),
]
