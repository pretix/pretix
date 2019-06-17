from django_scopes import scope


def classscope(attr='o'):
    def wrap(fn):
        def wrapped(self, *args, **kwargs):
            with scope(organizer=getattr(self, attr)):
                return fn(self, *args, **kwargs)
        return wrapped
    return wrap
