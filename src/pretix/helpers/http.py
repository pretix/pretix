from django.http import StreamingHttpResponse


class ChunkBasedFileResponse(StreamingHttpResponse):
    block_size = 4096

    def __init__(self, streaming_content=(), *args, **kwargs):
        filelike = streaming_content
        streaming_content = streaming_content.chunks(self.block_size)
        super().__init__(streaming_content, *args, **kwargs)
        self['Content-Length'] = filelike.size
