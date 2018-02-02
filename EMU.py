import datetime
import hashlib
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import bcrypt as bcrypt
from bson import ObjectId
from dateutil.parser import parse
from flask import Blueprint, render_template, abort, request, redirect, session

import tools
from config import db, config
from tools.utils import utc_to_localtime, audio_file_size

emu_page = Blueprint('emu_page', __name__, template_folder='templates')


@emu_page.route('/')
def index():
    return render_template('emu.html')


@emu_page.route('new')
def new():
    return render_template('emu_new.html')


@emu_page.route('create', methods=['POST'])
def create():
    proj = {'owner': request.form['owner'], 'description': request.form['desc'], 'created': datetime.datetime.utcnow(),
            'bundles': {}}
    if request.form['pass']:
        proj['password'] = bcrypt.hashpw(request.form['pass'].encode('utf-8'), bcrypt.gensalt())

    res = db.clarin.emu.insert_one(proj)
    id = res.inserted_id

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


def check_project(id):
    proj = db.clarin.emu.find_one({'_id': ObjectId(id)})
    if not proj:
        return None, abort(404)

    if 'deleted' in proj:
        return None, render_template('emu_deleted.html')

    if 'password' in proj:
        if 'pass_proj_id' not in session or session['pass_proj_id'] != id:
            return None, redirect('/emu/project/password/' + urllib.parse.quote(str(id)))
    else:
        if 'pass_proj_id' in session:
            session.pop('pass_proj_id')
    return proj, None


@emu_page.route('project/<id>')
def project(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    if 'password' in proj:
        pass_check = proj['password']
        pass_check = hashlib.sha1(pass_check.encode('utf-8')).hexdigest()
    else:
        pass_check = ''

    disable = {'asr': False, 'align': False, 'emu': False}
    refresh_req = False

    bundles = []
    bundle_names = []
    for name, b in proj['bundles'].items():
        bundle = {}
        if 'audio' in b:
            res = tools.utils.get_file(b['audio'])
            if res:
                bundle['audio'] = res
                if 'error' not in bundle['audio'] and not bundle['audio']['file']:
                    refresh_req = True
        if 'trans' in b:
            res = tools.utils.get_file(b['trans'])
            if res:
                bundle['trans'] = res
                if 'error' not in bundle['trans'] and not bundle['trans']['file']:
                    refresh_req = True
        if 'seg' in b:
            res = tools.utils.get_file(b['seg'])
            if res:
                bundle['seg'] = res
                if 'error' not in bundle['seg'] and not bundle['seg']['file']:
                    refresh_req = True

        if 'audio' not in bundle or not bundle['audio']['file']:
            disable['asr'] = True
            disable['align'] = True
            disable['emu'] = True
        if 'trans' not in bundle or not bundle['trans']['file']:
            disable['align'] = True
        if 'seg' not in bundle or not bundle['seg']['file']:
            disable['emu'] = True

        bundle['session'] = b['session']
        bundles.append((name, bundle))
        bundle_names.append(name)

    bundles = sorted(bundles, key=lambda x: x[0])
    if not bundles:
        disable = {'asr': True, 'align': True, 'emu': True}

    return render_template('emu_project.html', proj=proj, bundles=bundles, bundle_names=bundle_names,
                           create_date=utc_to_localtime(proj['created'], session),
                           pass_check=pass_check, disable=disable, refresh_req=refresh_req)


@emu_page.route('project/modify/<id>', methods=['POST'])
def project_modify(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    upd = {'owner': request.form['owner'], 'description': request.form['desc']}
    if request.form['pass'] != request.form['pass_check']:
        if request.form['pass']:
            upd['password'] = bcrypt.hashpw(request.form['pass'].encode('utf-8'), bcrypt.gensalt())
        else:
            db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {'password': 1}})
    db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': upd})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/remove/<id>')
def project_remove(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {'deleted': True}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


def check_password(id, password):
    proj = db.clarin.emu.find_one({'_id': ObjectId(id)})
    if not proj:
        return False
    if 'password' not in proj:
        return not password
    if password == config.emu.master_password:
        return True
    return bcrypt.hashpw(password.encode('utf-8'), proj['password'].encode('utf-8')) == proj['password'].encode(
        'utf-8')


@emu_page.route('project/password/<id>', methods=['GET', 'POST'])
def project_password(id):
    if request.method == 'GET':
        return render_template('emu_password.html', id=id, error=('error' in request.args))
    else:
        if check_password(id, request.form['pass']):
            session['pass_proj_id'] = id
            return redirect('/emu/project/' + urllib.parse.quote(str(id)))
        else:
            return redirect('/emu/project/password/' + urllib.parse.quote(str(id)) + '?error')


@emu_page.route('search', defaults={'page': 0}, methods=['GET', 'POST'])
@emu_page.route('search/<int:page>', methods=['GET', 'POST'])
def search(page):
    if 'reset' in request.args:
        session.pop('emu_search_filter', None)
    elif request.method == 'POST':
        filt = {}
        if request.form['owner']:
            filt['owner'] = request.form['owner']
        if request.form['description']:
            filt['description'] = request.form['description']
        if request.form['beforedate']:
            filt['beforedate'] = parse(request.form['beforedate'])
            filt['beforedatestr'] = request.form['beforedate']
        if request.form['afterdate']:
            filt['afterdate'] = parse(request.form['afterdate'])
            filt['afterdatestr'] = request.form['afterdate']
        session['emu_search_filter'] = filt

    filter = {}
    if 'emu_search_filter' in session:
        filter = session['emu_search_filter']

    query = {'deleted': {'$exists': False}}

    if 'owner' in filter:
        query['owner'] = {'$regex': filter['owner']}
    if 'description' in filter:
        query['description'] = {'$regex': filter['description']}
    if 'beforedate' in filter:
        query['created'] = {'$lte': filter['beforedate']}
    if 'afterdate' in filter:
        query['created'] = {'$gte': filter['afterdate']}

    res = db.clarin.emu.find(query, sort=[('created', -1)])
    proj_num = res.count()

    page_num = int(math.ceil(proj_num / float(config.emu.projects_per_page)))
    if page > page_num:
        page = page_num

    skip = page * config.emu.projects_per_page
    projects = res.skip(skip).limit(config.emu.projects_per_page)

    ret = []
    for proj in projects:
        proj['datestr'] = utc_to_localtime(proj['created'], session)
        ret.append(proj)

    pagination_start = page - 10
    if pagination_start < 0:
        pagination_start = 0
    pagination_end = pagination_start + 22
    if pagination_end > page_num:
        pagination_end = page_num
        pagination_start = pagination_end - 22
        if pagination_start < 0:
            pagination_start = 0

    return render_template('emu_search.html', projects=ret, page=page, page_num=page_num, filter=filter,
                           pagination_start=pagination_start, pagination_end=pagination_end)


def find_unique_name(proj, suggestion):
    if suggestion not in proj['bundles']:
        return suggestion
    for i in range(1, 100):
        name = f'{suggestion}({i})'
        if name not in proj['bundles']:
            return name
    return None


@emu_page.route('project/add_audio/<id>', methods=['POST'])
def add_audio(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    file = request.files['file']

    orig_id = tools.utils.upload_file(file, 'audio')

    audio_id = tools.tasks.start_audio_normalize(orig_id)

    time.sleep(0.1)

    if 'name' in request.form:
        name = request.form['name']
        if name not in proj['bundles']:
            return abort(404)
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{name}.audio': audio_id}})
    else:
        suggested = Path(file.filename).stem
        suggested = suggested.replace('.', '_')
        suggested = suggested.replace('$', '_')
        name = find_unique_name(proj, suggested)

        if not name:
            return abort(500)

        bundle = {'audio': audio_id, 'session': 'default'}

        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{name}': bundle}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/rename/<id>/<name>', methods=['POST'])
def rename_bundle(id, name):
    proj, resp = check_project(id)
    if not proj:
        return resp

    new_session = request.form['session']
    new_name = request.form['name']

    if name not in proj['bundles']:
        return abort(404)

    bundle = proj['bundles'][name]

    if name != new_name:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{new_name}': bundle}})
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{name}': 1}})

    if new_session != bundle['session']:
        db.clarin.emu.update_one({'_id': ObjectId(id)},
                                 {'$set': {f'bundles.{new_name}.session': new_session}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/add_trans/<id>', methods=['POST'])
def add_trans(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    name = request.form['name']
    file = request.files['file']

    if name not in proj['bundles']:
        return abort(404)

    orig_id = tools.utils.upload_file(file, 'transcript')

    trans_id = tools.tasks.start_text_normalize(orig_id)

    time.sleep(0.1)

    db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{name}.trans': trans_id}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/remove_bndl/<id>/<name>')
def remove_bndl(id, name):
    proj, resp = check_project(id)
    if not proj:
        return resp

    if name not in proj['bundles']:
        return abort(404)

    if 'audio' in request.args:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{name}.audio': 1}})
    elif 'trans' in request.args:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{name}.trans': 1}})
    elif 'seg' in request.args:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{name}.seg': 1}})
    else:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{name}': 1}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/reco/<id>/<name>')
def reco(id, name):
    proj, resp = check_project(id)
    if not proj:
        return resp

    if name not in proj['bundles']:
        return abort(404)

    bundle = proj['bundles'][name]

    if 'audio' not in bundle:
        return abort(404)

    audio_id = bundle['audio']
    res = tools.utils.get_file(audio_id)

    if 'file' not in res:
        return abort(404)

    trans_id = tools.tasks.start_speech_recognize(audio_id)

    time.sleep(0.1)

    db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{name}.trans': trans_id}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/align/<id>/<name>')
def align(id, name):
    proj, resp = check_project(id)
    if not proj:
        return resp

    if name not in proj['bundles']:
        return abort(404)

    bundle = proj['bundles'][name]

    if 'audio' not in bundle:
        return abort(404)

    audio_id = bundle['audio']
    res = tools.utils.get_file(audio_id)

    audio_file = config.work_dir / res['file']
    len = audio_file_size(audio_file)
    forced = True
    if len > 60:
        forced = False

    if 'file' not in res:
        return abort(404)

    if 'trans' not in bundle:
        return abort(404)

    trans_id = bundle['trans']
    res = tools.utils.get_file(trans_id)

    if 'file' not in res:
        return abort(404)

    if forced:
        seg_id = tools.tasks.start_speech_forcealign(audio_id, trans_id)
    else:
        seg_id = tools.tasks.start_speech_segmentalign(audio_id, trans_id)

    time.sleep(0.1)

    db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{name}.seg': seg_id}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/reco/<id>')
def reco_all(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    for name, bundle in proj['bundles'].items():

        if 'trans' in bundle:
            continue

        if 'audio' not in bundle:
            continue

        reco(id, name)

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/align/<id>')
def align_all(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    for name, bundle in proj['bundles'].items():

        if 'seg' in bundle:
            continue

        if name not in proj['bundles']:
            continue

        if 'audio' not in bundle:
            continue

        if 'trans' not in bundle:
            continue

        align(id, name)

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


pat = re.compile('^[a-zA-Z]*://([^:/]*)[:/]')


@emu_page.route('project/webapp/<id>')
def webapp(id):
    server = pat.match(request.url_root).group(1)
    url = f'ws://{server}:{config.emu.webapp_port}/{id}'
    return redirect('http://ips-lmu.github.io/EMU-webApp/?autoConnect=true&serverUrl=' + urllib.parse.quote_plus(url))


@emu_page.route('project/download/<id>')
def download(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    res_id = tools.tasks.start_emu_package(proj, id)

    return redirect('/tools/ui/view/' + urllib.parse.quote(str(res_id)))
