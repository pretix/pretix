import json
import logging
import requests
from django.core.cache import cache
from pretix.base.models import Order
from pretix.celery_app import app

logger = logging.getLogger('pretix.plugins.misa')

@app.task(bind=True, max_retries=3)
def create_misa_invoice(self, order_id):
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    s = order.event.settings
    if not s.misa_enabled:
        return

    url = s.misa_url
    app_id = s.misa_app_id
    tax_code = s.misa_tax_code
    username = s.misa_username
    password = s.misa_password

    if not (url and app_id and tax_code and username and password):
        return

    # 1. Login to get Token (with Caching)
    cache_key = f'misa_token_{order.event.pk}_{username}'
    token = cache.get(cache_key)

    if not token:
        try:
            login_url = f"{url.rstrip('/')}/api/v1/auth/login"
            payload = {
                "app_id": app_id,
                "username": username,
                "password": password
            }

            resp = requests.post(login_url, json=payload, timeout=15)
            resp.raise_for_status()

            data = resp.json()
            token = data.get('Token') or data.get('access_token')

            if not token:
                logger.error(f"MISA Login failed: No token returned. Response: {data}")
                order.log_action('pretix.plugins.misa.failed', data={'step': 'login', 'response': data})
                return

            # Cache for 23 hours (usually tokens last 24h)
            cache.set(cache_key, token, timeout=3600 * 23)

        except Exception as e:
            logger.exception("MISA Login failed")
            order.log_action('pretix.plugins.misa.failed', data={'step': 'login', 'error': str(e)})
            return

    # 2. Build Invoice Data
    items = []
    for p in order.positions.all():
        items.append({
            "ItemName": str(p.item.name),
            "Unit": "Vé",
            "Quantity": 1,
            "UnitPrice": float(p.price),
            "Amount": float(p.price),
            "TaxRate": float(p.tax_rate) if p.tax_rate else 0
        })

    ia = getattr(order, 'invoice_address', None)
    invoice_data = {
        "RefId": order.code,
        "InvSeries": s.misa_series,
        "InvTemplate": s.misa_template_code,
        "BuyerLegalName": ia.name if ia else "Khách lẻ",
        "BuyerTaxCode": ia.vat_id if ia else "",
        "BuyerEmail": order.email or "",
        "Items": items
    }

    # 3. Send Invoice
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        invoice_url = f"{url.rstrip('/')}/api/v1/invoice"

        resp = requests.post(invoice_url, json=invoice_data, headers=headers, timeout=30)

        if resp.status_code in (200, 201):
            order.log_action('pretix.plugins.misa.success', data=resp.json())
        elif resp.status_code == 401:
            # Token might be expired, clear cache and retry once
            cache.delete(cache_key)
            # We could retry recursively, but let's just raise to let Celery retry
            raise Exception("Token expired or invalid (401)")
        else:
            logger.error(f"MISA Send Invoice failed: {resp.status_code} - {resp.text}")
            order.log_action('pretix.plugins.misa.failed', data={'step': 'invoice', 'status': resp.status_code, 'response': resp.text})

            if 500 <= resp.status_code < 600:
                raise Exception(f"Server error {resp.status_code}")

    except Exception as e:
        logger.exception("MISA Send Invoice Exception")
        self.retry(exc=e)
