#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from pretix.helpers.templatetags.simple_block_tag import (
    register_simple_block_tag,
)

from django.utils.translation import gettext_lazy as _  # NOQA


register = template.Library()


@register_simple_block_tag(register)
def dialog(content, html_id, title, description, *args, **kwargs):
    format_kwargs = {
        "id": html_id,
        "title": title,
        "description": description,
        "icon": format_html('<div class="modal-card-icon"><span class="fa fa-{}" aria-hidden="true"></span></div>', kwargs["icon"]) if "icon" in kwargs else "",
        "alert": mark_safe('role="alertdialog"') if kwargs.get("alert", "False") != "False" else "",
        "content": content,
    }
    result = """
    <dialog {alert}
        id="{id}" class="modal-card"
        aria-labelledby="{id}-title"
        aria-describedby="{id}-description">
        <form method="dialog" class="modal-card-inner form-horizontal">
            {icon}
            <div class="modal-card-content">
                <h2 id="{id}-title" class="modal-card-title h3">{title}</h2>
                <p id="{id}-description" class="modal-card-description">{description}</p>
                {content}
            </div>
        </form>
    </dialog>
    """
    return format_html(result, **format_kwargs)
