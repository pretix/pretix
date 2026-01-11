import json
import logging
import requests
from pretix.base.models import Order
from pretix.celery_app import app

logger = logging.getLogger('pretix.plugins.zalozns')

@app.task(bind=True, max_retries=3)
def send_zns(self, order_id):
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    settings = order.event.settings
    access_token = settings.zalozns_access_token
    template_id = settings.zalozns_template_id

    if not access_token or not template_id:
        return

    phone = str(order.phone).replace('+', '') if order.phone else None

    if not phone:
        logger.warning(f"Zalo ZNS: Order {order.code} has no phone number.")
        return

    # Normalize phone to 84 format
    if phone.startswith('0'):
        phone = '84' + phone[1:]
    elif not phone.startswith('84'):
        # Assume it's a local number without 0 prefix? Or international?
        # Zalo usually requires 84xxxxxxxxx
        pass

    template_data = {}
    try:
        mapping = json.loads(settings.zalozns_template_data_mapping or '{}')
        for key, val_path in mapping.items():
            if val_path == 'code':
                template_data[key] = order.code
            elif val_path == 'total':
                template_data[key] = str(int(order.total)) if order.total else "0" # ZNS often wants string
            elif val_path == 'name':
                try:
                    template_data[key] = order.invoice_address.name
                except:
                    template_data[key] = "Customer"
            elif val_path == 'email':
                template_data[key] = order.email
    except json.JSONDecodeError:
        logger.error("Zalo ZNS: Invalid mapping JSON")
        return

    url = "https://business.openapi.zalo.me/message/template"
    headers = {
        "access_token": access_token,
        "Content-Type": "application/json"
    }
    payload = {
        "phone": phone,
        "template_id": template_id,
        "template_data": template_data,
        "tracking_id": order.code
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        if response_data.get('error') != 0:
            logger.error(f"Zalo ZNS Error for order {order.code}: {response_data}")
            order.log_action('pretix.plugins.zalozns.failed', data=response_data)
        else:
            order.log_action('pretix.plugins.zalozns.sent', data=response_data)
    except Exception as e:
        logger.exception("Zalo ZNS Exception")
        self.retry(exc=e)
