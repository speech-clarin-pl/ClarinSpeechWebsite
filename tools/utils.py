import datetime
import hashlib
import locale
import wave
from os import close
from pathlib import Path
from tempfile import mkstemp

import wavio
from bson.objectid import ObjectId
from dateutil.tz import tz

from config import config, db

allowed_types = ['wordlist', 'lexicon', 'audio', 'transcript', 'segmentation', 'archive', 'keywords']


def file_hash(file_path):
    h = hashlib.sha1()
    with open(file_path, 'rb', buffering=0) as f:
        for b in iter(lambda: f.read(128 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def insert_file(file, type):
    hash = file_hash(file)

    file_res = db.clarin.resources.find_one({'hash': hash})
    if file_res:
        id = file_res['_id']
        file.unlink()
    else:
        time = datetime.datetime.utcnow()
        res = db.clarin.resources.insert_one(
            {'file': file.name, 'type': type, 'hash': hash, 'created': time, 'modified': time})
        id = res.inserted_id

    return str(id)


def upload_file(file, type):
    if type not in allowed_types:
        return None

    fd, tmp = mkstemp(dir=config.work_dir)
    close(fd)

    tmp = Path(config.work_dir) / tmp
    file.save(str(tmp))

    return insert_file(tmp, type)


def get_file(id):
    if not id:
        return None
    return db.clarin.resources.find_one({'_id': ObjectId(id)})


loc_map = {'pl': 'pl_PL.UTF-8', 'en': 'en_US.UTF-8'}


def utc_to_localtime(dt, session=None):
    lang = 'pl'
    if session and 'lang' in session:
        lang = session['lang']

    locale.setlocale(locale.LC_TIME, loc_map[lang])

    d = dt.replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())
    return d.strftime('%a, %d %B %Y %H:%M:%S %Z')


def update_file(id, file):
    hash = file_hash(config.work_dir / file)
    db.clarin.resources.update_one({'_id': ObjectId(id)},
                                   {'$set': {'hash': hash, 'modified': datetime.datetime.utcnow()}})


def invalidate_file(fid):
    file = get_file(fid)
    if file:
        db.clarin.resources.update_many({'hash': file['hash']}, {'$set': {'error': 'manual delete', 'hash': ''}})


def audio_file_size(file):
    try:
        f = wave.open(str(file))
        _, _, r, n, _, _ = f.getparams()
        return n / float(r)
    except IOError:
        return 0


def wav_extract(input, output, start, end):
    y = wavio.read(str(input.absolute()))
    samp_start = int(start * y.rate)
    samp_end = int(end * y.rate)
    wavio.write(str(output.absolute()), y.data[samp_start:samp_end], y.rate, scale="none", sampwidth=y.sampwidth)
