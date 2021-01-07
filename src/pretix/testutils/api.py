from rest_framework.renderers import BaseRenderer


class UploadRenderer(BaseRenderer):
    media_type = None
    format = 'upload'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        self.media_type = data['media_type']
        return data['file']
