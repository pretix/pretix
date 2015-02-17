from django.conf.urls import patterns, url, include

import pretix.presale.views.event
import pretix.presale.views.cart
import pretix.presale.views.checkout


urlpatterns = patterns(
    '',
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(
        patterns(
            'pretix.presale.views.event',
            url(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
            url(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
            url(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
            url(r'^checkout$', pretix.presale.views.checkout.CheckoutStart.as_view(), name='event.checkout.start'),
        )
    )),
)
