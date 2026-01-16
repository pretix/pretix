#!/usr/bin/env python3
#
# Helper script to dump data as fixtures using Django's dumpdata command.
# This script handles django-scopes by disabling scopes during the dump operation,
# which is necessary for dumpdata to access all data across different organizers/events.
#
# Usage:
#   python dump_fixtures.py [dumpdata arguments...]
#
# Examples:
#   # Dump all data
#   python dump_fixtures.py > fixtures/all_data.json
#
#   # Dump specific models
#   python dump_fixtures.py pretixbase.Organizer pretixbase.Event > fixtures/organizers_events.json
#
#   # Dump with natural keys for better fixtures
#   python dump_fixtures.py --natural-foreign --natural-primary pretixbase.Event > fixtures/events.json
#
#   # Dump with pretty formatting
#   python dump_fixtures.py --indent 2 pretixbase.Event > fixtures/events.json
#
import os
import sys
import django

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
    
    # Initialize Django
    django.setup()
    
    from django.core.management import call_command
    from django_scopes import scopes_disabled
    
    # Get all arguments except script name
    dumpdata_args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    # Call dumpdata with scopes disabled to access all data
    # This is necessary because dumpdata needs to access data across different organizers/events
    with scopes_disabled():
        call_command('dumpdata', *dumpdata_args)

