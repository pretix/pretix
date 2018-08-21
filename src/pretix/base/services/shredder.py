import json
from datetime import timedelta
from tempfile import NamedTemporaryFile
from typing import List
from zipfile import ZipFile

from dateutil.parser import parse
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import CachedFile, Event, cachedfile_name
from pretix.base.services.tasks import ProfiledTask
from pretix.base.shredder import ShredError
from pretix.celery_app import app


@app.task(base=ProfiledTask)
def export(event: str, shredders: List[str]) -> None:
    event = Event.objects.get(id=event)
    known_shredders = event.get_data_shredders()

    with NamedTemporaryFile() as rawfile:
        with ZipFile(rawfile, 'w') as zipfile:
            ccode = get_random_string(6)
            zipfile.writestr(
                'CONFIRM_CODE.txt',
                ccode,
            )
            zipfile.writestr(
                'index.json',
                json.dumps({
                    'instance': settings.SITE_URL,
                    'organizer': event.organizer.slug,
                    'event': event.slug,
                    'time': now().isoformat(),
                    'shredders': shredders,
                    'confirm_code': ccode
                }, indent=4)
            )
            for s in shredders:
                shredder = known_shredders.get(s)
                if not shredder:
                    continue

                it = shredder.generate_files()
                if not it:
                    continue
                for fname, ftype, content in it:
                    zipfile.writestr(fname, content)

        rawfile.seek(0)

        cf = CachedFile()
        cf.date = now()
        cf.filename = event.slug + '.zip'
        cf.type = 'application/pdf'
        cf.expires = now() + timedelta(hours=1)
        cf.save()
        cf.file.save(cachedfile_name(cf, cf.filename), rawfile)

    return cf.pk


@app.task(base=ProfiledTask, throws=(ShredError,))
def shred(event: str, fileid: str, confirm_code: str) -> None:
    event = Event.objects.get(id=event)
    known_shredders = event.get_data_shredders()
    try:
        cf = CachedFile.objects.get(pk=fileid)
    except CachedFile.DoesNotExist:
        raise ShredError(_("The download file could no longer be found on the server, please try to start again."))
    with ZipFile(cf.file.file, 'r') as zipfile:
        indexdata = json.loads(zipfile.read('index.json').decode())
    if indexdata['organizer'] != event.organizer.slug or indexdata['event'] != event.slug:
        raise ShredError(_("This file is from a different event."))
    if indexdata['confirm_code'] != confirm_code:
        raise ShredError(_("The confirm code you entered was incorrect."))
    if event.logentry_set.filter(datetime__gte=parse(indexdata['time'])):
        raise ShredError(_("Something happened in your event after the export, please try again."))

    for s in indexdata['shredders']:
        shredder = known_shredders.get(s)
        if not shredder:
            continue

        shredder.shred_data()

    cf.file.delete(save=False)
    cf.delete()
