import datetime
import hashlib
import json

import pika
from bson import ObjectId

from config import config, db
from tools.utils import allowed_types


def queue(body):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    channel.basic_publish(exchange='', routing_key='workers', body=body,
                          properties=pika.BasicProperties(delivery_mode=2, ))
    connection.close()


def get_res_hash(id):
    return db.clarin.resources.find_one({'_id': ObjectId(id)}, {'hash': 1})['hash']


# TODO: this assumes we always generate one destination resource!
def run_task(task, input_res, output_type, options=None, hash=None):
    if output_type not in allowed_types:
        raise RuntimeError(u'Type {} not allowed!'.format(output_type))

    if not hash:
        from_hash = {}
        from_hash['task'] = task
        if options:
            from_hash['options'] = options
        for key, val in input_res.iteritems():
            from_hash[key] = get_res_hash(val)

        hash = hashlib.sha1(json.dumps(from_hash)).hexdigest()

    file = db.clarin.resources.find_one({'from_hash': hash, 'error': {'$exists': False}})
    if file:
        return str(file['_id'])
    else:

        args = {}
        args['task'] = task;
        if options:
            args['options'] = options
        for key, val in input_res.iteritems():
            args[key] = val

        time = datetime.datetime.utcnow()
        res = db.clarin.resources.insert_one({'file': None, 'type': output_type, 'hash': None,
                                              'created': time, 'modified': time, 'from': args, 'from_hash': hash})
        id = res.inserted_id

        args['output'] = str(id)
        args['work_dir'] = config.work_dir

        queue(json.dumps(args))

        return str(id)


def start_text_normalize(in_id):
    return run_task('text_normalize', {'input': str(in_id)}, 'transcript')


def start_audio_normalize(in_id):
    return run_task('ffmpeg', {'input': str(in_id)}, 'audio')


def start_speech_forcealign(audio_id, transcript_id):
    return run_task('forcealign', {'audio': str(audio_id), 'transcript': str(transcript_id)}, 'segmentation')


def start_speech_segmentalign(audio_id, transcript_id):
    return run_task('segmentalign', {'audio': str(audio_id), 'transcript': str(transcript_id)}, 'segmentation')


def start_speech_recognize(audio_id):
    return run_task('recognize', {'input': str(audio_id)}, 'transcript')


def start_emu_package(proj, proj_id):
    hash_list = []
    for name, bundle in proj['bundles'].iteritems():
        hash_item = {}
        hash_item['name'] = name
        hash_item['session'] = bundle['session']
        if 'audio' in bundle:
            hash_item['audio'] = get_res_hash(bundle['audio'])
        if 'trans' in bundle:
            hash_item['trans'] = get_res_hash(bundle['trans'])
        if 'seg' in bundle:
            hash_item['seg'] = get_res_hash(bundle['seg'])
        hash_list.append(hash_item)
    hash = hashlib.sha1(json.dumps(hash_list)).hexdigest()
    return run_task('emupackage', {'project': str(proj_id)}, 'archive', hash=hash)
