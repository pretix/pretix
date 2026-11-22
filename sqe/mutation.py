"""Run two Orders-specific mutation operators against the original rule tests."""

import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from xml.etree import ElementTree

OPERATORS = {
    'remove-active-position-requirement': (
        'test_br02_cancel_allowed_mcc', 'and self.count_positions', 'and True',
    ),
    'reject-fee-at-order-total': (
        'test_br04_cancellation_persists_expected_state',
        'cancellation_fee > order.total', 'cancellation_fee >= order.total',
    ),
}


def pytest_sessionstart(session):
    """Apply exactly one mutation in the subprocess running pytest."""
    from pretix.base.models import Order
    from pretix.base.services.orders import _cancel_order

    operator = os.environ['SQE_MUTATION_OPERATOR']
    target = Order.cancel_allowed if operator == 'remove-active-position-requirement' else _cancel_order
    _, original, mutated = OPERATORS[operator]
    source, first_line = inspect.getsourcelines(target)
    source = textwrap.dedent(''.join(source))
    if source.count(original) != 1:
        raise RuntimeError(f'Expected one match for mutation {operator}.')
    source = '\n' * (first_line - 1) + source.replace(original, mutated)
    namespace = {}
    exec(compile(source, inspect.getsourcefile(target), 'exec'), target.__globals__, namespace)
    target.__code__ = namespace[target.__name__].__code__


def run():
    evidence = Path(__file__).resolve().parents[1] / 'local' / 'sqe' / 'evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    suite = 'tests/team/unit/test_orders_rules.py'
    command = [sys.executable, '-m', 'pytest', '-q', suite]
    targets = ' or '.join(test for test, _, _ in OPERATORS.values())
    subprocess.run([*command, '-k', targets], check=True)
    killed = 0
    for operator, (test, _, _) in OPERATORS.items():
        report = evidence / f'mutation-{operator}.xml'
        result = subprocess.run(
            [*command, '-k', test, '-p', 'sqe.mutation', f'--junitxml={report}'],
            env={**os.environ, 'SQE_MUTATION_OPERATOR': operator},
        )
        if result.returncode not in (0, 1) or not report.is_file():
            raise RuntimeError(f'Test runner failed for {operator} with exit code {result.returncode}.')
        results = ElementTree.parse(report).getroot()
        if results.findall('.//error'):
            raise RuntimeError(f'Test setup produced errors for {operator}.')
        failed = result.returncode == 1 and bool(results.findall('.//failure'))
        killed += failed
        print(f'{operator}: {"killed" if failed else "survived"}', flush=True)
    print(f'Targeted mutation score: {killed}/{len(OPERATORS)}.')
    return int(killed != len(OPERATORS))


if __name__ == '__main__':
    sys.exit(run())
