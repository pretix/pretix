import io
from collections import defaultdict

from . import mt940


class MT940(mt940.MT940):
    def __init__(self, f):
        # Default implementation only takes a filename, but our file object
        # is not necessarily a file on the disk.
        self.statements = []
        values = defaultdict(str)
        transactions = []
        for line in self._readline(f):
            for name, sections in mt940.SECTIONS.items():
                if name == 'begin':
                    continue
                for section in sections:
                    if line.startswith(section):
                        if name in values and name == 'statement':
                            self._set_statement(values, transactions)
                        if name.endswith('_balance'):
                            values[name] = self._get_balance(
                                line[len(section):])
                        elif name == 'transaction':
                            transactions.append(
                                self._get_transaction(line[len(section):]))
                        elif name == 'description':
                            transactions[-1] = (transactions[-1][:-1]
                                                + (line[len(section):],))
                        else:
                            values[name] += line[len(section):]
        if values:
            self._set_statement(values, transactions)


def parse(file):
    data = file.read()
    try:
        import chardet
        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or 'utf-8')
    mt = MT940(io.StringIO(data))
    result = []
    for statement in mt.statements:
        for t in statement.transactions:
            result.append({
                'reference': t.reference + '\n' + t.description,
                'amount': str(t.amount),
                'date': t.booking.isoformat(),
            })
    return result
