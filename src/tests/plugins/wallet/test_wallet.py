import datetime
from decimal import Decimal

import jsonschema
import pytest
from django.utils.translation import gettext as _
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.models import InvoiceAddress, Order
from pretix.plugins.wallet.placeholders.base import (
    FunctionalContextTransformation,
    get_available_context,
    get_transformed_context,
)
from pretix.plugins.wallet.platforms.base import (
    FieldGroup,
    FieldGroupDisplay,
    ImageFieldGroup,
    PassStyle,
    TextFieldGroup,
    WalletPlatform,
)


class WalletTestPlatform(WalletPlatform):
    identifier = "test_platform"
    name = _("Test Wallet Platform")


class MinimalTestStyle(PassStyle):
    platform = WalletTestPlatform
    identifier = "test_style"
    name = _("Test Wallet Style")
    fieldgroups = []


class TicketTestStyle(PassStyle):
    platform = WalletTestPlatform
    identifier = "test_ticket"
    name = _("Test Wallet Style Ticket")

    @property
    def fieldgroups(self) -> list[FieldGroup]:
        return [
            TextFieldGroup(
                identifier="text1",
                name=_("Text 1"),
                required=True,
                context_args={"event"},
            ),
            TextFieldGroup(
                identifier="text2",
                name=_("Text 2"),
                required=False,
                context_args={"event"},
            ),
            TextFieldGroup(
                identifier="text3",
                name=_("Text 3"),
                required=False,
                context_args={"order_position"},
            ),
            TextFieldGroup(
                identifier="text4",
                name=_("Text 4"),
                required=False,
                context_args={"event"},
            ),
            TextFieldGroup(
                identifier="plain1",
                name=_("Plain 2"),
                required=False,
                display=FieldGroupDisplay.PLAIN,
                context_args={"event"},
            ),
            ImageFieldGroup(
                identifier="image1",
                name=_("Image 1"),
                required=False,
            ),
        ]

    def generate(self, op):
        fields = self.get_pass_fields(op)
        return fields


@pytest.fixture
def layout_context():
    return {
        "placeholders": {
            "text": {"test_placeholder": {"evaluate": lambda: "test placeholder"}}
        }
    }


def test_schema_generation_minimal():
    style = MinimalTestStyle(None, None)
    schema = style.layout_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "fieldgroups" in schema["properties"]

    jsonschema.validate({}, schema)
    jsonschema.validate({"fieldgroups": {}}, schema)


def test_schema_ticket_generation(layout_context):
    style = TicketTestStyle(None, None)
    schema = style.layout_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "fieldgroups" in schema["properties"]


@pytest.mark.parametrize(
    "layout",
    [
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "event_slug",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "event_slug",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {"type": "custom", "label": "test", "content": "test content"}
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "event_slug",
                        },
                        {"type": "custom", "label": "test", "content": "test content"},
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "event_slug",
                        },
                        {"type": "custom", "label": "test", "content": "test content"},
                    ],
                    "overflow": "text2",
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "event_slug",
                        }
                    ],
                },
                "text2": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "event_slug",
                        }
                    ],
                    "overflow": "text3",
                },
            }
        },
    ],
)
@pytest.mark.django_db
def test_schema_ticket_valid(env, layout):
    event, *_ = env
    style = TicketTestStyle(event, layout)
    schema = style.layout_schema()
    jsonschema.validate(layout, schema)


@pytest.mark.parametrize(
    "layout",
    [
        {},
        {"fieldgroups": {}},
        {"fieldgroups": {"text1": {}}},
        {"fieldgroups": {"text1": {"entries": []}}},
        {"fieldgroups": {"text1": {"overflow": "test"}}},
        {
            "fieldgroups": {
                "text1": {
                    "entries": [{"type": "placeholder", "content": "test_placeholder"}]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": [],
                            "content": "test_placeholder",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {"entries": [{"type": "text", "content": "test content"}]}
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "invalid_group",
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "image1",
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                },
                "text2": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "text1",
                },
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                },
                "text3": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "text4",
                },
            }
        },
    ],
)
@pytest.mark.django_db
def test_schema_ticket_invalid(env, layout):
    style = TicketTestStyle(env[0])
    schema = style.layout_schema()

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(layout, schema)


@pytest.mark.django_db
def test_style_representation(env):
    style = TicketTestStyle(env[0])
    style_dict = style.asdict()

    assert style_dict["identifier"] == "test_ticket"
    assert style_dict["name"] == _("Test Wallet Style Ticket")

    assert style_dict["fieldgroups"][0]["identifier"] == "text1"
    assert style_dict["fieldgroups"][0]["name"] == "Text 1"
    assert style_dict["fieldgroups"][0]["content_type"] == "text"
    assert style_dict["fieldgroups"][0]["display"] == "with_label"
    assert style_dict["fieldgroups"][0]["required"] is True


@pytest.mark.django_db
def test_layout_generate(env, order):
    layout = {
        "fieldgroups": {
            "text1": {
                "entries": [
                    {
                        "type": "placeholder",
                        "label": {"de": "test-de", "en": "test-en"},
                        "content": "event_slug",
                    },
                    {"type": "content", "label": "test", "content": "test content"},
                ],
                "overflow": "text2",
            }
        }
    }
    style = TicketTestStyle(env[0], layout)
    generated_pass = style.generate(order.positions.first())

    assert generated_pass == {
        "text1": [
            {
                "label": LazyI18nString({"de": "test-de", "en": "test-en"}),
                "value": "dummy",
            }
        ],
        "text2": [
            {
                "label": LazyI18nString({"de": "test-de", "en": "test-en"}),
                "value": "dummy",
            }
        ],
        "text3": [],
        "text4": [],
        "plain1": [],
        "image1": [],
    }


def test_placeholder_transformation_graph():
    context = {"order_position"}
    trans1 = FunctionalContextTransformation(
        "order", {"order_position"}, lambda order_position: order_position.order
    )
    trans2 = FunctionalContextTransformation(
        "event", {"order"}, lambda order: order.event
    )
    trans3 = FunctionalContextTransformation(
        "name", {"invoice_address"}, lambda invoice_address: "name"
    )
    assert get_available_context(context, [trans1, trans2]) == {
        "order_position",
        "order",
        "event",
    }
    assert get_available_context(context, [trans2, trans1]) == {
        "order_position",
        "order",
        "event",
    }
    assert get_available_context(context, [trans1, trans2, trans3]) == {
        "order_position",
        "order",
        "event",
    }


@pytest.fixture
@scopes_disabled()
def item(env):
    return env[0].items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
@scopes_disabled()
def order(env, item):
    event, _, _ = env
    o = Order.objects.create(
        code="FOO",
        event=event,
        email="dummy@dummy.test",
        status=Order.STATUS_PENDING,
        secret="k24fiuwvu8kxz3y1",
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
        datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
        total=23,
        locale="en",
    )
    o.positions.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("23"),
        attendee_email="peter@example.org",
        attendee_name_parts={"given_name": "Peter", "family_name": "Miller"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        pseudonymization_id="ABCDEFGHKL",
    )
    InvoiceAddress.objects.create(
        order=o,
        name_parts={"given_name": "Peter", "family_name": "Miller"},
    )
    return o


@pytest.mark.django_db
def test_placeholder_transformation_calculation(order):
    op = order.positions.first()
    event = order.event
    context_args = {"order_position": op}
    trans1 = FunctionalContextTransformation(
        "order", {"order_position"}, lambda order_position: order_position.order
    )
    trans2 = FunctionalContextTransformation(
        "event", {"order"}, lambda order: order.event
    )
    trans3 = FunctionalContextTransformation(
        "name", {"invoice_address"}, lambda invoice_address: "name"
    )
    expected_context = {"order_position": op, "order": order, "event": event}
    assert get_transformed_context(context_args, [trans1, trans2]) == expected_context
    assert get_transformed_context(context_args, [trans2, trans1]) == expected_context
    assert (
        get_transformed_context(context_args, [trans1, trans2, trans3])
        == expected_context
    )
