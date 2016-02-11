import io

import mt940

from pretix.base.decimal import round_decimal


def parse(file):
    data = file.read()
    try:
        import chardet

        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or 'utf-8')
    mt = mt940.parse(io.StringIO(data.strip()))
    result = []
    for t in mt:
        result.append({
            'reference': "\n".join([
                t.data.get(f) for f in ('transaction_details', 'customer_reference', 'bank_reference',
                                        'extra_details') if t.data.get(f, '')]),
            'amount': str(round_decimal(t.data['amount'].amount)),
            'date': t.data['date'].isoformat()
        })
    return result
