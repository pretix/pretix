from django.core.management.base import BaseCommand
from django.core.paginator import Paginator

from pretix.base.models import Order, OrderSearchIndex


class Command(BaseCommand):
    help = "Rebuild search index"

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean', action='store_true', dest='clean',
            help="Clear search index before run.",
        )

    def iter_pages(self, qs):
        paginator = Paginator(qs, 500)
        for index in range(paginator.num_pages):
            yield paginator.get_page(index + 1)

    def handle(self, *args, **options):
        if options.get('clean'):
            OrderSearchIndex.objects.all().delete()
        qs = Order.objects.select_related('event', 'event__organizer', 'invoice_address').prefetch_related('all_positions', 'payments')
        for page in self.iter_pages(qs):
            if options.get('clean'):
                OrderSearchIndex.objects.bulk_create([o.index() for o in page])
            else:
                for o in page:
                    o.index()
