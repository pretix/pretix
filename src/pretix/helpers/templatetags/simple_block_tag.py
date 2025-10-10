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

#
# backport from Django 5.2 (django/django/template/library.py)
#
# TODO: remove once we upgrade to Django 5.2

from functools import wraps
from inspect import getfullargspec, unwrap

from django.template.exceptions import TemplateSyntaxError
from django.template.library import SimpleNode, parse_bits


class SimpleBlockNode(SimpleNode):
    def __init__(self, nodelist, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nodelist = nodelist

    def get_resolved_arguments(self, context):
        resolved_args, resolved_kwargs = super().get_resolved_arguments(context)

        # Restore the "content" argument.
        # It will move depending on whether takes_context was passed.
        resolved_args.insert(
            1 if self.takes_context else 0, self.nodelist.render(context)
        )

        return resolved_args, resolved_kwargs


def register_simple_block_tag(library, func=None, takes_context=None, name=None, end_name=None):
    """
    Register a callable as a compiled block template tag. Example:

    @register_simple_block_tag(register)
    def hello(content):
        return 'world'
    """
    def dec(func):
        nonlocal end_name

        (
            params,
            varargs,
            varkw,
            defaults,
            kwonly,
            kwonly_defaults,
            _,
        ) = getfullargspec(unwrap(func))
        function_name = name or func.__name__

        if end_name is None:
            end_name = f"end{function_name}"

        @wraps(func)
        def compile_func(parser, token):
            tag_params = params.copy()

            if takes_context:
                if len(tag_params) >= 2 and tag_params[1] == "content":
                    del tag_params[1]
                else:
                    raise TemplateSyntaxError(
                        f"{function_name!r} is decorated with takes_context=True so"
                        " it must have a first argument of 'context' and a second "
                        "argument of 'content'"
                    )
            elif tag_params and tag_params[0] == "content":
                del tag_params[0]
            else:
                raise TemplateSyntaxError(
                    f"'{function_name}' must have a first argument of 'content'"
                )

            bits = token.split_contents()[1:]
            target_var = None
            if len(bits) >= 2 and bits[-2] == "as":
                target_var = bits[-1]
                bits = bits[:-2]

            nodelist = parser.parse((end_name,))
            parser.delete_first_token()

            args, kwargs = parse_bits(
                parser,
                bits,
                tag_params,
                varargs,
                varkw,
                defaults,
                kwonly,
                kwonly_defaults,
                takes_context,
                function_name,
            )

            return SimpleBlockNode(
                nodelist, func, takes_context, args, kwargs, target_var
            )

        library.tag(function_name, compile_func)
        return func

    if func is None:
        # @register.simple_block_tag(...)
        return dec
    elif callable(func):
        # @register.simple_block_tag
        return dec(func)
    else:
        raise ValueError("Invalid arguments provided to simple_block_tag")
