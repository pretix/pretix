from django.utils.crypto import get_random_string


def add_cart_session(client, event, data):
    new_id = get_random_string(length=32)
    session = client.session
    session['current_cart_event_{}'.format(event.pk)] = new_id
    if 'carts' not in session:
        session['carts'] = {}
    session['carts'][new_id] = data
    session.save()
    return new_id


def get_cart_session_key(client, event):
    cart_id = client.session.get('current_cart_event_{}'.format(event.pk))
    if cart_id:
        return cart_id
    else:
        return add_cart_session(client, event, {})
