import json
import logging
import requests
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

    # 1. Login to get Token
    token = None
    try:
        # Placeholder endpoint for login
        # MISA API usually requires mapping generic data
        # response = requests.post(f"{url}/api/v1/auth/login", json={...})
        # token = response.json().get('Token')
        pass
    except Exception:
        logger.error("MISA Login failed")
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

    invoice_data = {
        "RefId": order.code,
        "InvSeries": s.misa_series,
        "InvTemplate": s.misa_template_code,
        "BuyerLegalName": order.invoice_address.name if getattr(order, 'invoice_address', None) else "Khách lẻ",
        "BuyerTaxCode": order.invoice_address.vat_id if getattr(order, 'invoice_address', None) else "",
        "BuyerEmail": order.email,
        "Items": items
    }

    # 3. Send Invoice
    # try:
    #     headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    #     resp = requests.post(f"{url}/api/v1/invoice", json=invoice_data, headers=headers)
    #     if resp.status_code == 200:
    #         order.log_action('pretix.plugins.misa.success', data=resp.json())
    #     else:
    #         order.log_action('pretix.plugins.misa.failed', data=resp.text)
    # except Exception as e:
    #     self.retry(exc=e)

    logger.info(f"MISA Invoice Data prepared for {order.code}: {json.dumps(invoice_data)}")
    # Log action for now since we can't really call API
    order.log_action('pretix.plugins.misa.created', data={'mock': True})
