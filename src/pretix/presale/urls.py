from django.conf.urls import include, url
from django.views.decorators.csrf import csrf_exempt

import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.event
import pretix.presale.views.locale
import pretix.presale.views.order
import pretix.presale.views.organizer
import pretix.presale.views.robots
import pretix.presale.views.user
import pretix.presale.views.waiting
import pretix.presale.views.widget

# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.

frame_wrapped_urls = [
    url(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
    url(r'^cart/clear$', pretix.presale.views.cart.CartClear.as_view(), name='event.cart.clear'),
    url(r'^cart/answer/(?P<answer>[^/]+)/$',
        pretix.presale.views.cart.AnswerDownload.as_view(),
        name='event.cart.download.answer'),
    url(r'^checkout/start$', pretix.presale.views.checkout.CheckoutView.as_view(), name='event.checkout.start'),
    url(r'^checkout/(?P<step>[^/]+)/$', pretix.presale.views.checkout.CheckoutView.as_view(),
        name='event.checkout'),
    url(r'^redeem/?$', pretix.presale.views.cart.RedeemView.as_view(),
        name='event.redeem'),
    url(r'^(?P<subevent>[0-9]+)/$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
    url(r'^waitinglist', pretix.presale.views.waiting.WaitingView.as_view(), name='event.waitinglist'),
    url(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
]
event_patterns = [
    # Cart/checkout patterns are a bit more complicated, as they should have simple URLs like cart/clear in normal
    # cases, but need to have versions with unguessable URLs like w/8l4Y83XNonjLxoBb/cart/clear to be used in widget
    # mode. This is required to prevent all clickjacking and CSRF attacks that would otherwise be possible.
    # First, we define the normal version. The docstring of get_or_create_cart_id() has more information on this.
    url(r'', include(frame_wrapped_urls)),
    # Second, the widget version
    url(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/', include(frame_wrapped_urls)),
    # Third, a fake version that is defined like the first (and never gets called), but makes reversing URLs easier
    url(r'(?P<cart_namespace>[_]{0})', include(frame_wrapped_urls)),
    # CartAdd goes extra since it also gets a csrf_exempt decorator in one of the cases
    url(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    url(r'^(?P<cart_namespace>[_]{0})cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    url(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/cart/add',
        csrf_exempt(pretix.presale.views.cart.CartAdd.as_view()),
        name='event.cart.add'),

    url(r'resend/$', pretix.presale.views.user.ResendLinkView.as_view(), name='event.resend_link'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/$', pretix.presale.views.order.OrderDetails.as_view(),
        name='event.order'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice$',
        pretix.presale.views.order.OrderInvoiceCreate.as_view(),
        name='event.order.geninvoice'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel$',
        pretix.presale.views.order.OrderCancel.as_view(),
        name='event.order.cancel'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel/do$',
        pretix.presale.views.order.OrderCancelDo.as_view(),
        name='event.order.cancel.do'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/modify$',
        pretix.presale.views.order.OrderModify.as_view(),
        name='event.order.modify'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay$', pretix.presale.views.order.OrderPaymentStart.as_view(),
        name='event.order.pay'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/confirm$',
        pretix.presale.views.order.OrderPaymentConfirm.as_view(),
        name='event.order.pay.confirm'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/complete$',
        pretix.presale.views.order.OrderPaymentComplete.as_view(),
        name='event.order.pay.complete'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/change',
        pretix.presale.views.order.OrderPayChangeMethod.as_view(),
        name='event.order.pay.change'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/answer/(?P<answer>[^/]+)/$',
        pretix.presale.views.order.AnswerDownload.as_view(),
        name='event.order.download.answer'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<output>[^/]+)$',
        pretix.presale.views.order.OrderDownload.as_view(),
        name='event.order.download.combined'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/(?P<output>[^/]+)$',
        pretix.presale.views.order.OrderDownload.as_view(),
        name='event.order.download'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice/(?P<invoice>[0-9]+)$',
        pretix.presale.views.order.InvoiceDownload.as_view(),
        name='event.invoice.download'),
    url(r'^ical/?$',
        pretix.presale.views.event.EventIcalDownload.as_view(),
        name='event.ical.download'),
    url(r'^ical/(?P<subevent>[0-9]+)/$',
        pretix.presale.views.event.EventIcalDownload.as_view(),
        name='event.ical.download'),
    url(r'^auth/$', pretix.presale.views.event.EventAuth.as_view(), name='event.auth'),

    url(r'^widget/product_list$', pretix.presale.views.widget.WidgetAPIProductList.as_view(),
        name='event.widget.productlist'),
    url(r'^widget/v1.css$', pretix.presale.views.widget.widget_css, name='event.widget.css'),
    url(r'^(?P<subevent>\d+)/widget/product_list$', pretix.presale.views.widget.WidgetAPIProductList.as_view(),
        name='event.widget.productlist'),
]

organizer_patterns = [
    url(r'^$', pretix.presale.views.organizer.OrganizerIndex.as_view(), name='organizer.index'),
    url(r'^events/ical/$',
        pretix.presale.views.organizer.OrganizerIcalDownload.as_view(),
        name='organizer.ical'),
]

locale_patterns = [
    url(r'^locale/set$', pretix.presale.views.locale.LocaleSet.as_view(), name='locale.set'),
    url(r'^robots.txt$', pretix.presale.views.robots.robots_txt, name='robots.txt'),
    url(r'^widget/v1\.(?P<lang>[a-zA-Z0-9_\-]+)\.js$', pretix.presale.views.widget.widget_js, name='widget.js'),
]
