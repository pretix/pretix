from django.conf.urls import url, include

import pretix.presale.views.event
import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.order
import pretix.presale.views.locale


urlpatterns = [
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include([
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
        url(r'^order/(?P<order>[^/]+)/modify$', pretix.presale.views.order.OrderModify.as_view(),
            name='event.order.modify'),
        url(r'^order/(?P<order>[^/]+)/pay$', pretix.presale.views.order.OrderPay.as_view(),
            name='event.order.pay'),
        url(r'^order/(?P<order>[^/]+)/pay/confirm$', pretix.presale.views.order.OrderPayDo.as_view(),
            name='event.order.pay.confirm'),
        url(r'^order/(?P<order>[^/]+)/download/(?P<output>[^/]+)$', pretix.presale.views.order.OrderDownload.as_view(),
            name='event.order.download'),
        url(r'^login$', pretix.presale.views.event.EventLogin.as_view(), name='event.checkout.login'),
        url(r'^forgot$', pretix.presale.views.event.EventForgot.as_view(), name='event.forgot'),
        url(r'^forgot/recover$', pretix.presale.views.event.EventRecover.as_view(), name='event.forgot.recover'),
        url(r'^logout$', pretix.presale.views.event.EventLogout.as_view(), name='event.logout'),
        url(r'^orders$', pretix.presale.views.event.EventOrders.as_view(), name='event.orders'),
        url(r'^account$', pretix.presale.views.event.EventAccount.as_view(), name='event.account'),
        url(r'^account/settings$', pretix.presale.views.event.EventAccountSettings.as_view(), name='event.account.settings'),
    ])),
    url(r'^locale/set$', pretix.presale.views.locale.LocaleSet.as_view(), name='locale.set'),
]
