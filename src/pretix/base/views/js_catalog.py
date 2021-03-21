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
from django.utils import timezone
from django.utils.translation.trans_real import DjangoTranslation
from django.views.decorators.cache import cache_page
from django.views.decorators.http import etag
from django.views.i18n import JavaScriptCatalog

# Yes, we want to regenerate this every time the module has been imported to
# refresh the cache at least at every code deployment
import_date = timezone.now().strftime("%Y%m%d%H%M")


# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.
js_info_dict = {
    'packages': ('pretix',),
}


@etag(lambda *s, **k: import_date)
@cache_page(3600, key_prefix='js18n-%s' % import_date)
def js_catalog(request, lang):
    c = JavaScriptCatalog()
    c.translation = DjangoTranslation(lang, domain='djangojs')
    context = c.get_context_data()
    return c.render_to_response(context)
