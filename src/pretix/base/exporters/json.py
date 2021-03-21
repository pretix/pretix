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
from django.dispatch import receiver

from ..exporter import BaseExporter
from ..signals import register_data_exporters


class JSONExporter(BaseExporter):
    identifier = 'json'
    verbose_name = 'Order data (JSON)'

    def render(self, form_data):
        jo = {
            'event': {
                'name': str(self.event.name),
                'slug': self.event.slug,
                'organizer': {
                    'name': str(self.event.organizer.name),
                    'slug': self.event.organizer.slug
                },
                'categories': [
                    {
                        'id': category.id,
                        'name': str(category.name),
                        'internal_name': category.internal_name
                    } for category in self.event.categories.all()
                ],
                'items': [
                    {
                        'id': item.id,
                        'name': str(item.name),
                        'internal_name': str(item.internal_name),
                        'category': item.category_id,
                        'price': item.default_price,
                        'tax_rate': item.tax_rule.rate if item.tax_rule else Decimal('0.00'),
                        'tax_name': str(item.tax_rule.name) if item.tax_rule else None,
                        'admission': item.admission,
                        'active': item.active,
                        'variations': [
                            {
                                'id': variation.id,
                                'active': variation.active,
                                'price': variation.default_price if variation.default_price is not None else
                                item.default_price,
                                'name': str(variation)
                            } for variation in item.variations.all()
                        ]
                    } for item in self.event.items.select_related('tax_rule').prefetch_related('variations')
                ],
                'questions': [
                    {
                        'id': question.id,
                        'question': str(question.question),
                        'type': question.type
                    } for question in self.event.questions.all()
                ],
                'orders': [
                    {
                        'code': order.code,
                        'status': order.status,
                        'user': order.email,
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
                                'item': position.item_id,
                                'variation': position.variation_id,
                                'price': position.price,
                                'attendee_name': position.attendee_name,
                                'attendee_email': position.attendee_email,
                                'secret': position.secret,
                                'addon_to': position.addon_to_id,
                                'answers': [
                                    {
                                        'question': answer.question_id,
                                        'answer': answer.answer
                                    } for answer in position.answers.all()
                                ]
                            } for position in order.positions.all()
                        ]
                    } for order in
                    self.event.orders.all().prefetch_related('positions', 'positions__answers', 'fees')
                ],
                'quotas': [
                    {
                        'id': quota.id,
                        'size': quota.size,
                        'items': [item.id for item in quota.items.all()],
                        'variations': [variation.id for variation in quota.variations.all()],
                    } for quota in self.event.quotas.all().prefetch_related('items', 'variations')
                ]
            }
        }

        return '{}_pretixdata.json'.format(self.event.slug), 'application/json', json.dumps(jo, cls=DjangoJSONEncoder)


@receiver(register_data_exporters, dispatch_uid="exporter_json")
def register_json_export(sender, **kwargs):
    return JSONExporter
