import datetime
import hashlib
import locale
import os
import wave
from tempfile import mkstemp

from bson.objectid import ObjectId
from dateutil.tz import tz

from config import config, db

allowed_types = ['wordlist', 'lexicon', 'audio', 'transcript', 'segmentation', 'archive']


def file_hash(filename):
    h = hashlib.sha1()
    with open(os.path.join(config.work_dir, filename), 'rb', buffering=0) as f:
        for b in iter(lambda: f.read(128 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def upload_file(file, type):
    if type not in allowed_types:
        return None

    fd, tmp = mkstemp(dir=config.work_dir)
    os.close(fd)
    file.save(tmp)

    hash = file_hash(tmp)

    tmpname = os.path.basename(tmp)

    file = db.clarin.resources.find_one({'hash': hash})
    if file:
        id = file['_id']
        os.remove(tmp)
    else:
        time = datetime.datetime.utcnow()
        res = db.clarin.resources.insert_one(
            {'file': tmpname, 'type': type, 'hash': hash, 'created': time, 'modified': time})
        id = res.inserted_id

    return str(id)


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
    return d.strftime('%a, %d %B %Y %H:%M:%S %Z').decode('utf-8')


def update_file(id, file):
    hash = file_hash(file)
    db.clarin.resources.update_one({'_id': ObjectId(id)},
                                   {'$set': {'hash': hash, 'modified': datetime.datetime.utcnow()}})


def invalidate_file(id):
    db.clarin.resources.update_one({'_id': ObjectId(id)},
                                   {'$set': {'error': 'manual delete'}})


def audio_file_size(file):
    try:
        f = wave.open(file)
        _, _, r, n, _, _ = f.getparams()
        return n / float(r)
    except:
        return 0
