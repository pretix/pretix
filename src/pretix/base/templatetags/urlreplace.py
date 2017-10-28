from django import template

register = template.Library()


@register.simple_tag
def url_replace(request, *pairs):
    dict_ = request.GET.copy()
    key = None
    for p in pairs:
        if key is None:
            key = p
        else:
            if p == "":
                if key in dict_:
                    del dict_[key]
            else:
                dict_[key] = p
            key = None
    return dict_.urlencode(safe='[]')
