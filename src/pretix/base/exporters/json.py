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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch
from django.dispatch import receiver
from django.utils.functional import lazy
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy

from ..exporter import BaseExporter
from ..models import ItemMetaValue, ItemVariation, ItemVariationMetaValue
from ..signals import register_data_exporters


class JSONExporter(BaseExporter):
    identifier = 'json'
    verbose_name = lazy(lambda *args: gettext('Order data') + ' (JSON)', str)()
    category = pgettext_lazy('export_category', 'Order data')
    description = gettext_lazy('Download a structured JSON representation of all orders. This might be useful for the '
                               'import in third-party systems.')

    def render(self, form_data):
        jo = {
            'event': {
                'name': str(self.event.name),
                'slug': self.event.slug,
                'organizer': {
                    'name': str(self.event.organizer.name),
                    'slug': self.event.organizer.slug
                },
                'meta_data': self.event.meta_data,
                'categories': [
                    {
                        'id': category.id,
                        'name': str(category.name),
                        'description': str(category.description),
                        'position': category.position,
                        'internal_name': category.internal_name
                    } for category in self.event.categories.all()
                ],
                'items': [
                    {
                        'id': item.id,
                        'position': item.position,
                        'name': str(item.name),
                        'internal_name': str(item.internal_name),
                        'category': item.category_id,
                        'price': item.default_price,
                        'tax_rate': item.tax_rule.rate if item.tax_rule else Decimal('0.00'),
                        'tax_name': str(item.tax_rule.name) if item.tax_rule else None,
                        'admission': item.admission,
                        'personalized': item.personalized,
                        'active': item.active,
                        'sales_channels': item.sales_channels,
                        'description': str(item.description),
                        'available_from': item.available_from,
                        'available_until': item.available_until,
                        'require_voucher': item.require_voucher,
                        'hide_without_voucher': item.hide_without_voucher,
                        'allow_cancel': item.allow_cancel,
                        'require_bundling': item.require_bundling,
                        'min_per_order': item.min_per_order,
                        'max_per_order': item.max_per_order,
                        'checkin_attention': item.checkin_attention,
                        'original_price': item.original_price,
                        'issue_giftcard': item.issue_giftcard,
                        'meta_data': item.meta_data,
                        'require_membership': item.require_membership,
                        'variations': [
                            {
                                'id': variation.id,
                                'active': variation.active,
                                'price': variation.default_price if variation.default_price is not None else
                                item.default_price,
                                'name': str(variation),
                                'description': str(variation.description),
                                'position': variation.position,
                                'checkin_attention': variation.checkin_attention,
                                'require_approval': variation.require_approval,
                                'require_membership': variation.require_membership,
                                'sales_channels': variation.sales_channels,
                                'available_from': variation.available_from,
                                'available_until': variation.available_until,
                                'hide_without_voucher': variation.hide_without_voucher,
                                'meta_data': variation.meta_data,
                            } for variation in item.variations.all()
                        ]
                    } for item in self.event.items.select_related('tax_rule').prefetch_related(
                        Prefetch(
                            'meta_values',
                            ItemMetaValue.objects.select_related('property'),
                            to_attr='meta_values_cached'
                        ),
                        Prefetch(
                            'variations',
                            queryset=ItemVariation.objects.prefetch_related(
                                Prefetch(
                                    'meta_values',
                                    ItemVariationMetaValue.objects.select_related('property'),
                                    to_attr='meta_values_cached'
                                ),
                            ),
                        ),
                    )
                ],
                'questions': [
                    {
                        'id': question.id,
                        'identifier': question.identifier,
                        'required': question.required,
                        'question': str(question.question),
                        'position': question.position,
                        'hidden': question.hidden,
                        'ask_during_checkin': question.ask_during_checkin,
                        'help_text': str(question.help_text),
                        'type': question.type
                    } for question in self.event.questions.all()
                ],
                'orders': [
                    {
                        'code': order.code,
                        'status': order.status,
                        'customer': order.customer.identifier if order.customer else None,
                        'testmode': order.testmode,
                        'user': order.email,
                        'email': order.email,
                        'phone': str(order.phone),
                        'locale': order.locale,
                        'comment': order.comment,
                        'custom_followup_at': order.custom_followup_at,
                        'require_approval': order.require_approval,
                        'checkin_attention': order.checkin_attention,
                        'sales_channel': order.sales_channel,
                        'expires': order.expires,
                        'datetime': order.datetime,
                        'fees': [
                            {
                                'type': fee.fee_type,
                                'description': fee.description,
                                'value': fee.value,
                            } for fee in order.fees.all()
                        ],
                        'total': order.total,
                        'positions': [
                            {
                                'id': position.id,
                                'positionid': position.positionid,
                                'item': position.item_id,
                                'variation': position.variation_id,
                                'subevent': position.subevent_id,
                                'seat': position.seat.seat_guid if position.seat else None,
                                'price': position.price,
                                'tax_rate': position.tax_rate,
                                'tax_value': position.tax_value,
                                'attendee_name': position.attendee_name,
                                'attendee_email': position.attendee_email,
                                'company': position.company,
                                'street': position.street,
                                'zipcode': position.zipcode,
                                'country': str(position.country) if position.country else None,
                                'state': position.state,
                                'secret': position.secret,
                                'addon_to': position.addon_to_id,
                                'valid_from': position.valid_from,
                                'valid_until': position.valid_until,
                                'blocked': position.blocked,
                                'answers': [
                                    {
                                        'question': answer.question_id,
                                        'answer': answer.answer
                                    } for answer in position.answers.all()
                                ]
                            } for position in order.positions.all()
                        ]
                    } for order in
                    self.event.orders.all().prefetch_related('positions', 'positions__answers', 'positions__seat', 'customer', 'fees')
                ],
                'quotas': [
                    {
                        'id': quota.id,
                        'size': quota.size,
                        'subevent': quota.subevent_id,
                        'items': [item.id for item in quota.items.all()],
                        'variations': [variation.id for variation in quota.variations.all()],
                    } for quota in self.event.quotas.all().prefetch_related('items', 'variations')
                ],
                'subevents': [
                    {
                        'id': se.id,
                        'name': str(se.name),
                        'location': str(se.location),
                        'date_from': se.date_from,
                        'date_to': se.date_to,
                        'date_admission': se.date_admission,
                        'geo_lat': se.geo_lat,
                        'geo_lon': se.geo_lon,
                        'is_public': se.is_public,
                        'meta_data': se.meta_data,
                    } for se in self.event.subevents.all()
                ]
            }
        }

        return '{}_pretixdata.json'.format(self.event.slug), 'application/json', json.dumps(jo, cls=DjangoJSONEncoder)


@receiver(register_data_exporters, dispatch_uid="exporter_json")
def register_json_export(sender, **kwargs):
    return JSONExporter
