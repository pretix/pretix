from django.core.urlresolvers import resolve
from django.http import Http404
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event


class EventMiddleware:
    def process_request(self, request):
        url = resolve(request.path_info)
        url_namespace = url.namespace
        url_name = url.url_name
        if url_namespace != 'presale':
            return

        if 'order_secrets' not in request.session:
            request.session['order_secrets'] = []
        if 'order_secret' in request.GET and request.GET.get('order_secret') not in request.session['order_secrets']:
            # We can't use append here, because this would not trigger __setitem__
            # on the session store and would not be saved
            request.session['order_secrets'] = request.session['order_secrets'] + [request.GET.get('order_secret')]
            # Removal of the secret from the URL has been disabled so people can bookmark it
            # g = request.GET.copy()
            # del g['order_secret']
            # return redirect(request.path + '?' + g.urlencode())

        if 'event.' in url_name and 'event' in url.kwargs:
            try:
                request.event = Event.objects.current.filter(
                    slug=url.kwargs['event'],
                    organizer__slug=url.kwargs['organizer'],
                ).select_related('organizer')[0]
            except IndexError:
                raise Http404(_('The selected event was not found.'))
