from django.conf.urls import patterns, url, include

import pretix.presale.views.event
import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.order


urlpatterns = patterns(
    '',
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(
        patterns(
            'pretix.presale.views.event',
            url(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
            url(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
            url(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
            url(r'^checkout$', pretix.presale.views.checkout.CheckoutStart.as_view(), name='event.checkout.start'),
            url(r'^checkout/payment$', pretix.presale.views.checkout.PaymentDetails.as_view(),
                name='event.checkout.payment'),
            url(r'^checkout/confirm$', pretix.presale.views.checkout.OrderConfirm.as_view(),
                name='event.checkout.confirm'),
            url(r'^order/(?P<order>[^/]+)/$', pretix.presale.views.order.OrderDetails.as_view(),
                name='event.order'),
            url(r'^order/(?P<order>[^/]+)/cancel$', pretix.presale.views.order.OrderCancel.as_view(),
                name='event.order.cancel'),
            url(r'^login$', pretix.presale.views.event.EventLogin.as_view(), name='event.checkout.login'),
        )
    )),
)
