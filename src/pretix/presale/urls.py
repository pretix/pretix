#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos, Tobias Kunze, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.urls import include, re_path
from django.views.decorators.csrf import csrf_exempt

import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.customer
import pretix.presale.views.event
import pretix.presale.views.locale
import pretix.presale.views.oidc_op
import pretix.presale.views.order
import pretix.presale.views.organizer
import pretix.presale.views.robots
import pretix.presale.views.theme
import pretix.presale.views.user
import pretix.presale.views.waiting
import pretix.presale.views.widget

# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.

frame_wrapped_urls = [
    re_path(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
    re_path(r'^cart/voucher$', pretix.presale.views.cart.CartApplyVoucher.as_view(), name='event.cart.voucher'),
    re_path(r'^cart/clear$', pretix.presale.views.cart.CartClear.as_view(), name='event.cart.clear'),
    re_path(r'^cart/answer/(?P<answer>[^/]+)/$',
            pretix.presale.views.cart.AnswerDownload.as_view(),
            name='event.cart.download.answer'),
    re_path(r'^checkout/start$', pretix.presale.views.checkout.CheckoutView.as_view(), name='event.checkout.start'),
    re_path(r'^checkout/(?P<step>[^/]+)/$', pretix.presale.views.checkout.CheckoutView.as_view(),
            name='event.checkout'),
    re_path(r'^redeem/?$', pretix.presale.views.cart.RedeemView.as_view(),
            name='event.redeem'),
    re_path(r'^seatingframe/$', pretix.presale.views.event.SeatingPlanView.as_view(),
            name='event.seatingplan'),
    re_path(r'^(?P<subevent>[0-9]+)/seatingframe/$', pretix.presale.views.event.SeatingPlanView.as_view(),
            name='event.seatingplan'),
    re_path(r'^(?P<subevent>[0-9]+)/$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
    re_path(r'^waitinglist/remove$', pretix.presale.views.waiting.WaitingRemoveView.as_view(), name='event.waitinglist.remove'),
    re_path(r'^waitinglist', pretix.presale.views.waiting.WaitingView.as_view(), name='event.waitinglist'),
    re_path(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
]

event_patterns = [
    # Cart/checkout patterns are a bit more complicated, as they should have simple URLs like cart/clear in normal
    # cases, but need to have versions with unguessable URLs like w/8l4Y83XNonjLxoBb/cart/clear to be used in widget
    # mode. This is required to prevent all clickjacking and CSRF attacks that would otherwise be possible.
    # First, we define the normal version. The docstring of get_or_create_cart_id() has more information on this.
    re_path(r'', include(frame_wrapped_urls)),
    # Second, the widget version
    re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/', include(frame_wrapped_urls)),
    # Third, a fake version that is defined like the first (and never gets called), but makes reversing URLs easier
    re_path(r'(?P<cart_namespace>[_]{0})', include(frame_wrapped_urls)),
    # CartAdd goes extra since it also gets a csrf_exempt decorator in one of the cases
    re_path(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    re_path(r'^(?P<cart_namespace>[_]{0})cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/cart/add',
            csrf_exempt(pretix.presale.views.cart.CartAdd.as_view()),
            name='event.cart.add'),

    re_path(r'unlock/(?P<hash>[a-z0-9]{64})/$', pretix.presale.views.user.UnlockHashView.as_view(),
            name='event.payment.unlock'),
    re_path(r'resend/$', pretix.presale.views.user.ResendLinkView.as_view(), name='event.resend_link'),

    re_path(r'^favicon.ico/?$',
            pretix.presale.views.organizer.OrganizerFavicon.as_view(),
            name='event.favicon'),

    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/open/(?P<hash>[a-z0-9]+)/$', pretix.presale.views.order.OrderOpen.as_view(),
            name='event.order.open'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/$', pretix.presale.views.order.OrderDetails.as_view(),
            name='event.order'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice$',
            pretix.presale.views.order.OrderInvoiceCreate.as_view(),
            name='event.order.geninvoice'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/change$',
            pretix.presale.views.order.OrderChange.as_view(),
            name='event.order.change'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel$',
            pretix.presale.views.order.OrderCancel.as_view(),
            name='event.order.cancel'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel/do$',
            pretix.presale.views.order.OrderCancelDo.as_view(),
            name='event.order.cancel.do'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/modify$',
            pretix.presale.views.order.OrderModify.as_view(),
            name='event.order.modify'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/(?P<payment>[0-9]+)/$',
            pretix.presale.views.order.OrderPaymentStart.as_view(),
            name='event.order.pay'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/(?P<payment>[0-9]+)/confirm$',
            pretix.presale.views.order.OrderPaymentConfirm.as_view(),
            name='event.order.pay.confirm'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/(?P<payment>[0-9]+)/complete$',
            pretix.presale.views.order.OrderPaymentComplete.as_view(),
            name='event.order.pay.complete'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/change',
            pretix.presale.views.order.OrderPayChangeMethod.as_view(),
            name='event.order.pay.change'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/answer/(?P<answer>[^/]+)/$',
            pretix.presale.views.order.AnswerDownload.as_view(),
            name='event.order.download.answer'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<output>[^/]+)$',
            pretix.presale.views.order.OrderDownload.as_view(),
            name='event.order.download.combined'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/(?P<output>[^/]+)$',
            pretix.presale.views.order.OrderDownload.as_view(),
            name='event.order.download'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/giftcard/(?P<pk>[0-9]+)/$',
            pretix.presale.views.order.OrderGiftCardDetails.as_view(),
            name='event.order.giftcard'),
    re_path(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice/(?P<invoice>[0-9]+)$',
            pretix.presale.views.order.InvoiceDownload.as_view(),
            name='event.invoice.download'),

    re_path(r'^ticket/(?P<order>[^/]+)/(?P<position>\d+)/(?P<secret>[A-Za-z0-9]+)/$',
            pretix.presale.views.order.OrderPositionDetails.as_view(),
            name='event.order.position'),
    re_path(r'^ticket/(?P<order>[^/]+)/(?P<position>\d+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<pid>[0-9]+)/(?P<output>[^/]+)$',
            pretix.presale.views.order.OrderPositionDownload.as_view(),
            name='event.order.position.download'),
    re_path(r'^ticket/(?P<order>[^/]+)/(?P<position>\d+)/(?P<secret>[A-Za-z0-9]+)/giftcard/(?P<pk>[0-9]+)/$',
            pretix.presale.views.order.OrderPositionGiftCardDetails.as_view(),
            name='event.order.position.giftcard'),
    re_path(r'^ticket/(?P<order>[^/]+)/(?P<position>\d+)/(?P<secret>[A-Za-z0-9]+)/change$',
            pretix.presale.views.order.OrderPositionChange.as_view(),
            name='event.order.position.change'),

    re_path(r'^ical/?$',
            pretix.presale.views.event.EventIcalDownload.as_view(),
            name='event.ical.download'),
    re_path(r'^ical/(?P<subevent>[0-9]+)/$',
            pretix.presale.views.event.EventIcalDownload.as_view(),
            name='event.ical.download'),
    re_path(r'^auth/$', pretix.presale.views.event.EventAuth.as_view(), name='event.auth'),

    re_path(r'^widget/product_list$', pretix.presale.views.widget.WidgetAPIProductList.as_view(),
            name='event.widget.productlist'),
    re_path(r'^widget/v1.css$', pretix.presale.views.widget.widget_css, name='event.widget.css'),
    re_path(r'^(?P<subevent>\d+)/widget/product_list$', pretix.presale.views.widget.WidgetAPIProductList.as_view(),
            name='event.widget.productlist'),

    # Account management is done on org level, but we at least need a logout
    re_path(r'^account/logout$', pretix.presale.views.customer.LogoutView.as_view(), name='organizer.customer.logout'),
]

organizer_patterns = [
    re_path(r'^$', pretix.presale.views.organizer.OrganizerIndex.as_view(), name='organizer.index'),
    re_path(r'^favicon.ico/?$',
            pretix.presale.views.organizer.OrganizerFavicon.as_view(),
            name='organizer.favicon'),
    re_path(r'^events/ical/$',
            pretix.presale.views.organizer.OrganizerIcalDownload.as_view(),
            name='organizer.ical'),

    re_path(r'^widget/product_list$', pretix.presale.views.widget.WidgetAPIProductList.as_view(),
            name='organizer.widget.productlist'),
    re_path(r'^widget/v1.css$', pretix.presale.views.widget.widget_css, name='organizer.widget.css'),

    re_path(r'^account/login/(?P<provider>[0-9]+)/$', pretix.presale.views.customer.SSOLoginView.as_view(), name='organizer.customer.login'),
    re_path(r'^account/login/(?P<provider>[0-9]+)/return$', pretix.presale.views.customer.SSOLoginReturnView.as_view(), name='organizer.customer.login.return'),
    re_path(r'^account/login$', pretix.presale.views.customer.LoginView.as_view(), name='organizer.customer.login'),
    re_path(r'^account/logout$', pretix.presale.views.customer.LogoutView.as_view(), name='organizer.customer.logout'),
    re_path(r'^account/register$', pretix.presale.views.customer.RegistrationView.as_view(), name='organizer.customer.register'),
    re_path(r'^account/pwreset$', pretix.presale.views.customer.ResetPasswordView.as_view(), name='organizer.customer.resetpw'),
    re_path(r'^account/pwrecover$', pretix.presale.views.customer.SetPasswordView.as_view(), name='organizer.customer.recoverpw'),
    re_path(r'^account/activate$', pretix.presale.views.customer.SetPasswordView.as_view(), name='organizer.customer.activate'),
    re_path(r'^account/password$', pretix.presale.views.customer.ChangePasswordView.as_view(), name='organizer.customer.password'),
    re_path(r'^account/change$', pretix.presale.views.customer.ChangeInformationView.as_view(), name='organizer.customer.change'),
    re_path(r'^account/confirmchange$', pretix.presale.views.customer.ConfirmChangeView.as_view(), name='organizer.customer.change.confirm'),
    re_path(r'^account/membership/(?P<id>\d+)/$', pretix.presale.views.customer.MembershipUsageView.as_view(), name='organizer.customer.membership'),
    re_path(r'^account/addresses/(?P<id>\d+)/delete$', pretix.presale.views.customer.AddressDeleteView.as_view(), name='organizer.customer.address.delete'),
    re_path(r'^account/profiles/(?P<id>\d+)/delete$', pretix.presale.views.customer.ProfileDeleteView.as_view(), name='organizer.customer.profile.delete'),
    re_path(r'^account/$', pretix.presale.views.customer.ProfileView.as_view(), name='organizer.customer.profile'),

    re_path(r'^oauth2/v1/authorize$', pretix.presale.views.oidc_op.AuthorizeView.as_view(),
            name='organizer.oauth2.v1.authorize'),
    re_path(r'^oauth2/v1/token$', pretix.presale.views.oidc_op.TokenView.as_view(),
            name='organizer.oauth2.v1.token'),
    re_path(r'^oauth2/v1/userinfo$', pretix.presale.views.oidc_op.UserInfoView.as_view(),
            name='organizer.oauth2.v1.userinfo'),
    re_path(r'^oauth2/v1/keys$', pretix.presale.views.oidc_op.KeysView.as_view(),
            name='organizer.oauth2.v1.jwks'),
    re_path(r'^.well-known/openid-configuration$', pretix.presale.views.oidc_op.ConfigurationView.as_view(),
            name='organizer.oauth2.v1.configuration'),
]

locale_patterns = [
    re_path(r'^locale/set$', pretix.presale.views.locale.LocaleSet.as_view(), name='locale.set'),
    re_path(r'^robots.txt$', pretix.presale.views.robots.robots_txt, name='robots.txt'),
    re_path(r'^browserconfig.xml$', pretix.presale.views.theme.browserconfig_xml, name='browserconfig.xml'),
    re_path(r'^site.webmanifest$', pretix.presale.views.theme.webmanifest, name='site.webmanifest'),
    re_path(r'^widget/v1\.(?P<lang>[a-zA-Z0-9_\-]+)\.js$', pretix.presale.views.widget.widget_js, name='widget.js'),
]
