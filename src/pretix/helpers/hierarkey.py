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


def clean_filename(fname):
    """
    hierarkey.forms.SettingsForm appends a random value to every filename. However, it keeps the
    extension around "twice". This leads to:

    "Terms.pdf" → "Terms.pdf.OybgvyAH.pdf"

    In pretix Hosted, our storage layer also adds a hash of the file to the filename, so we have

    "Terms.pdf" → "Terms.pdf.OybgvyAH.22c0583727d5bc.pdf"

    This function reverses this operation:

    "Terms.pdf.OybgvyAH.22c0583727d5bc.pdf" → "Terms.pdf"
    """
    ext = '.' + fname.split('.')[-1]
    return fname.rsplit(ext + ".", 1)[0] + ext
