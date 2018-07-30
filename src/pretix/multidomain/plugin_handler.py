from pretix.presale.utils import _event_view


def plugin_event_urls(urllist, plugin):
    for entry in urllist:
        if hasattr(entry, 'url_patterns'):
            plugin_event_urls(entry.url_patterns, plugin)
        elif hasattr(entry, 'callback'):
            entry.callback = _event_view(entry.callback, require_plugin=plugin,
                                         require_live=getattr(entry.pattern, '_require_live', True))
    return urllist
