import datetime
import os

from config import db, config

time = datetime.datetime.utcnow() - datetime.timedelta(days=1)

print 'Getting all resources older than {:%Y-%m-%d %H:%M}...'.format(time)

rsrcs = db.clarin.resources.find({'modified': {'$lt': time}})
ids = set()
for res in rsrcs:
    ids.add(res['_id'])

print 'Discarding anything that can be used in EMU projects...'

projs = db.clarin.emu.find({})
for proj in projs:
    for bndl in proj['bundles']:
        if 'audio' in bndl:
            ids.discard(bndl['audio'])
        if 'trans' in bndl:
            ids.discard(bndl['trans'])
        if 'seg' in bndl:
            ids.discard(bndl['seg'])

print 'Deleting {} resources...'.format(len(ids))

db.clarin.resources.remove({'_id': {'$in': list(ids)}})

print 'Making a list of files in databse...'

rsrcs = db.clarin.resources.find({})

db_files = set()
for res in rsrcs:
    db_files.add(res['file'])

print 'Removing files not in database...'

for root, dirs, files in os.walk(config.work_dir):
    for file in files:
        if os.path.relpath(os.path.join(root, file), config.work_dir) not in db_files:
            try:
                # print 'Removing {}/{}'.format(root, file)
                os.remove(os.path.join(root, file))
            except OSError:
                continue
    for dir in dirs:
        dir_path = os.path.join(root, dir)
        if os.path.islink(dir_path):
            try:
                # print 'Removing symlink {}/{}'.format(root, dir)
                os.remove(dir_path)
            except OSError:
                continue

for root, dirs, files in os.walk(config.work_dir, topdown=False):
    for dir in dirs:
        try:
            # print 'Removing dir {}/{}'.format(root, dir)
            os.rmdir(os.path.join(root, dir))
        except OSError:
            continue

print 'Done!'
