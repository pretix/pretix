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

"""
This file contains settings that we need at wheel require time. All settings that we only need at runtime are set
in settings.py.
"""
from ._base_settings import *  # NOQA

ENTROPY = {
    'order_code': 5,
    'customer_identifier': 7,
    'ticket_secret': 32,
    'voucher_code': 16,
    'giftcard_secret': 12,
}

MAIL_FROM_ORGANIZERS = 'invalid@invalid'
FILE_UPLOAD_MAX_SIZE_EMAIL_AUTO_ATTACHMENT = 10
FILE_UPLOAD_MAX_SIZE_EMAIL_ATTACHMENT = 10
FILE_UPLOAD_MAX_SIZE_IMAGE = 10
DEFAULT_CURRENCY = 'EUR'
SECRET_KEY = "build-time-secret-key"
HAS_REDIS = False
STATIC_URL = '/static/'
HAS_MEMCACHED = False
HAS_CELERY = False
HAS_GEOIP = False
SENTRY_ENABLED = False
