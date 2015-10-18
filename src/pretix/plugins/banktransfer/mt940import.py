import io
from decimal import Decimal

import mt940


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
            'amount': str(t.data['amount'].amount.quantize(Decimal('.01'))),
            'date': t.data['date'].isoformat()
        })
    return result
