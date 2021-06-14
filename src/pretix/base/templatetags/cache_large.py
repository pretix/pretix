from django.conf import settings
from django.template import Library, Node, TemplateSyntaxError, Variable
from django.templatetags.cache import CacheNode

register = Library()


class DummyNode(Node):
    def __init__(self, nodelist, *args):
        self.nodelist = nodelist

    def render(self, context):
        value = self.nodelist.render(context)
        return value


@register.tag('cache_large')
def do_cache(parser, token):
    nodelist = parser.parse(('endcache_large',))
    parser.delete_first_token()
    tokens = token.split_contents()
    if len(tokens) < 3:
        raise TemplateSyntaxError("'%r' tag requires at least 2 arguments." % tokens[0])

    if not settings.CACHE_LARGE_VALUES_ALLOWED:
        return DummyNode(
            nodelist,
        )

    return CacheNode(
        nodelist, parser.compile_filter(tokens[1]),
        tokens[2],  # fragment_name can't be a variable.
        [parser.compile_filter(t) for t in tokens[3:]],
        Variable(repr(settings.CACHE_LARGE_VALUES_ALIAS)),
    )
