import subprocess
import tempfile
import time
from decimal import Decimal

from pretix.base.decimal import round_decimal


def hbci_transactions(event, conf):
    try:
        from defusedxml import ElementTree
    except:
        from xml.etree import ElementTree

    log = []
    data = []
    accname = 'pretix_%d_%d' % (event.id, int(time.time() * 1000))
    try:
        try:
            subprocess.call([
                'aqhbci-tool4', 'deluser', '-a', '--all',
                '-b', conf['hbci_blz'],
                '-u', conf['hbci_userid']
            ])
        except subprocess.CalledProcessError:
            pass
        aqhbci_params = [
            'aqhbci-tool4', 'adduser',
            '-N', accname,
            '-b', conf['hbci_blz'],
            '-s', conf['hbci_server'],
            '-t', conf['hbci_tokentype'],
            '-u', conf['hbci_userid']
        ]
        if conf['hbci_customerid']:
            aqhbci_params += ['-c', conf['hbci_customerid']]
        if conf['hbci_tokenname']:
            aqhbci_params += ['-n', conf['hbci_tokenname']]
        if conf['hbci_version']:
            aqhbci_params += ['--hbciversion=' + str(conf['hbci_version'])]
        aqhbci_add = subprocess.check_output(aqhbci_params)
        log.append("$ " + " ".join(aqhbci_params))
        log.append(aqhbci_add.decode("utf-8"))
        with tempfile.NamedTemporaryFile() as f, tempfile.NamedTemporaryFile() as g:
            f.write(('PIN_%s_%s = "%s"\n' % (
                conf['hbci_blz'],
                conf['hbci_userid'],
                conf['pin'],
            )).encode("utf-8"))
            f.flush()
            aqhbci_params = [
                'aqhbci-tool4',
                '-P', f.name,
                '-n', '-A',
                'getsysid',
                '-u', conf['hbci_userid'],
                '-b', conf['hbci_blz'],
            ]
            if conf['hbci_customerid']:
                aqhbci_params += ['-c', conf['hbci_customerid']]
            aqhbci_test = subprocess.check_output(aqhbci_params)
            log.append("$ " + " ".join(aqhbci_params))
            log.append(aqhbci_test.decode("utf-8"))
            aqbanking_params = [
                'aqbanking-cli',
                '-P', f.name, '-A', '-n',
                'request',
                '--transactions',
                '-c', g.name,
                '-n', accname
            ]
            aqbanking_trans = subprocess.check_output(aqbanking_params)
            log.append("$ " + " ".join(aqbanking_params))
            log.append(aqbanking_trans.decode("utf-8"))
            aqbanking_params = [
                'aqbanking-cli',
                'listtrans',
                '-c', g.name,
                '--exporter=xmldb',
            ]
            aqbanking_conv = subprocess.check_output(aqbanking_params)
            log.append("$ " + " ".join(aqbanking_params))

            root = ElementTree.fromstring(aqbanking_conv)
            trans_list = root.find('accountInfoList').find('accountInfo').find('transactionList')
            for trans in trans_list.findall('transaction'):
                payer = []
                for child in trans:
                    if child.tag.startswith('remote'):
                        payer.append(child.find('value').text)
                date = '%s-%02d-%02d' % (
                    trans.find('date').find('date').find('year').find('value').text,
                    int(trans.find('date').find('date').find('month').find('value').text),
                    int(trans.find('date').find('date').find('day').find('value').text)
                )
                value = trans.find('value').find('value').find('value').text
                if "/" in value:
                    parts = value.split("/")
                    num = int(parts[0])
                    denom = int(parts[1])
                    value = Decimal(num) / Decimal(denom)
                    value = str(round_decimal(value))
                data.append({
                    'payer': "\n".join(payer),
                    'reference': trans.find('purpose').find('value').text,
                    'amount': value,
                    'date': date
                })
    except subprocess.CalledProcessError as e:
        log.append("Command '%s' failed with %d and output:" % (" ".join(e.cmd), e.returncode))
        log.append(e.output.decode("utf-8"))
    except Exception as e:
        log.append(str(e))
    finally:
        subprocess.call([
            'aqhbci-tool4', 'deluser', '-a', '-N', accname
        ])
    log = "\n".join(log)
    return data, log
