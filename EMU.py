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
from flask_babel import lazy_gettext as _
from flask_breadcrumbs import register_breadcrumb
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, RadioField
from wtforms.fields.html5 import DateField
from wtforms.validators import DataRequired, EqualTo
from wtforms.widgets import TextArea

import tools
from Tools import ui_view, ui_view_multi
from config import db, config
from tools.utils import utc_to_localtime, audio_file_size

emu_page = Blueprint('emu_page', __name__, template_folder='templates')


@emu_page.route('/')
@register_breadcrumb(emu_page, '.', _(u'EMU'))
def index():
    return render_template('emu.html')


class EmuProject(FlaskForm):
    owner = StringField(_(u'właściciel'), validators=[DataRequired()], default='Anonymous')
    description = StringField(_(u'opis'), widget=TextArea())
    password = PasswordField(_(u'hasło'), validators=[
        EqualTo('confirm', message=_(u'hasła_się_różnią'))
    ])
    confirm = PasswordField(_(u'powtórz_hasło'))
    visibility = RadioField(_(u'widoczność'),
                            choices=[('public', _(u'publiczny')), ('viewonly', _(u'tylko_do_odczytu')),
                                     ('private', _(u'prywatny'))],
                            validators=[DataRequired()], default='public')

    def password_required(self):
        self.password.validators.append(DataRequired())


@emu_page.route('new', methods=['GET', 'POST'])
@register_breadcrumb(emu_page, '.new', _(u'nowy_projekt'))
def new():
    form = EmuProject(request.form)
    form.password_required()
    if form.validate_on_submit():
        proj = {'owner': request.form['owner'], 'description': request.form['description'],
                'password': bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt()),
                'visibility': request.form['visibility'],
                'created': datetime.datetime.utcnow(),
                'bundles': {}}

        res = db.clarin.emu.insert_one(proj)
        id = res.inserted_id

        return redirect('/emu/project/' + urllib.parse.quote(str(id)))

    return render_template('emu_new.html', form=form)


@register_breadcrumb(emu_page, '.delete', _(u'projekt_usunięty'))
def check_project(id, modify=False, admin=False):
    proj = db.clarin.emu.find_one({'_id': ObjectId(id)})
    if not proj:
        return None, abort(404)

    if 'deleted' in proj:
        return None, render_template('emu_deleted.html')

    check_pw = False
    if proj['visibility'] == 'private':
        check_pw = True
    elif proj['visibility'] == 'viewonly' and (modify or admin):
        check_pw = True
    elif admin:  # public
        check_pw = True

    if 'pass_proj_id' in session and session['pass_proj_id'] != id:
        session.pop('pass_proj_id')

    if check_pw and 'pass_proj_id' not in session:
        return None, redirect('/emu/project/password/' + urllib.parse.quote(str(id)))

    return proj, None


@emu_page.route('project/<id>')
@register_breadcrumb(emu_page, '.project', _(u'emu_projekt_tytuł'))
def project(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    if 'password' in proj:
        pass_check = proj['password']
        pass_check = hashlib.sha1(pass_check).hexdigest()
    else:
        pass_check = ''

    disable = {'asr': False, 'align': False, 'emu': False}
    refresh_req = False

    bundles = []
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
        bundle['name'] = b['name']
        bundles.append((name, bundle))

    bundles = sorted(bundles, key=lambda x: (x[0]))
    if not bundles:
        disable = {'asr': True, 'align': True, 'emu': True}

    logged_in = False
    if 'pass_proj_id' in session and session['pass_proj_id'] == id:
        logged_in = True

    can_admin = True
    can_modify = True
    if not logged_in:
        can_admin = False
        if proj['visibility'] == 'viewonly':
            can_modify = False

    return render_template('emu_project.html', proj=proj, bundles=bundles,
                           create_date=utc_to_localtime(proj['created'], session),
                           pass_check=pass_check, disable=disable, refresh_req=refresh_req,
                           logged_in=logged_in, can_modify=can_modify, can_admin=can_admin)


@emu_page.route('project/modify/<id>', methods=['GET', 'POST'])
@register_breadcrumb(emu_page, '.project.modify', _(u'zmień_projekt'))
def project_modify(id):
    proj, resp = check_project(id, admin=True)
    if not proj:
        return resp

    form = EmuProject(request.form)
    if form.validate_on_submit():
        upd = {'owner': request.form['owner'], 'description': request.form['description'],
               'visibility': request.form['visibility']}

        if request.form['password']:
            upd['password'] = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())

        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': upd})

        return redirect('/emu/project/' + urllib.parse.quote(str(id)))

    form.owner.data = proj['owner']
    form.description.data = proj['description']
    form.visibility.data = proj['visibility']

    vis = {'public': '', 'viewonly': '', 'private': ''}
    vis[proj['visibility']] = 'checked'
    vis2 = {'public': '', 'viewonly': '', 'private': ''}
    vis2[proj['visibility']] = 'active'

    return render_template('emu_modify.html', form=form, proj=proj, vis=vis, vis2=vis2)


@emu_page.route('project/remove/<id>')
def project_remove(id):
    proj, resp = check_project(id, admin=True)
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
    return bcrypt.hashpw(password.encode('utf-8'), proj['password']) == proj['password']


@emu_page.route('project/password/<id>', methods=['GET', 'POST'])
@register_breadcrumb(emu_page, '.password', _(u'hasło_tytuł'))
def project_password(id):
    if request.method == 'GET':
        return render_template('emu_password.html', id=id, error=('error' in request.args))
    else:
        if check_password(id, request.form['pass']):
            session['pass_proj_id'] = id
            return redirect('/emu/project/' + urllib.parse.quote(str(id)))
        else:
            return redirect('/emu/project/password/' + urllib.parse.quote(str(id)) + '?error')


@emu_page.route('project/logout/<id>', methods=['GET'])
def logout(id):
    session.pop('pass_proj_id')
    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


class EmuSearchFilter(FlaskForm):
    owner = StringField(_(u'właściciel'))
    description = StringField(_(u'opis'))
    afterdate = DateField(_(u'po_dacie'))
    beforedate = DateField(_(u'przed_datą'))


@emu_page.route('search', defaults={'page': 0}, methods=['GET', 'POST'])
@emu_page.route('search/<int:page>', methods=['GET', 'POST'])
@register_breadcrumb(emu_page, '.search', _(u'szukaj_projekt'))
def search(page):
    form = EmuSearchFilter()
    if 'reset' in request.args:
        session.pop('emu_search_filter', None)
        return redirect('/emu/search')
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

    filter_expanded = ''
    if len(filter) > 0:
        filter_expanded = 'show'

    return render_template('emu_search.html', projects=ret, page=page, page_num=page_num, form=form,
                           filter_expanded=filter_expanded, filter=filter, pagination_start=pagination_start,
                           pagination_end=pagination_end)


def find_unique_name(proj, session, suggestion):
    if f'{session}_{suggestion}' not in proj['bundles']:
        return suggestion
    for i in range(1, 100):
        name = f'{suggestion}({i})'
        if f'{session}_{name}' not in proj['bundles']:
            return name
    return None


@emu_page.route('project/add_audio/<id>', methods=['POST'])
def add_audio(id):
    proj, resp = check_project(id, modify=True)
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
        name = Path(file.filename).stem
        name = ''.join(c for c in name if c.isalnum()).rstrip()
        name = find_unique_name(proj, 'default', name)

        if not name:
            return abort(500)

        bundle = {'audio': audio_id, 'session': 'default', 'name': name}

        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.default_{name}': bundle}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


# TODO: check for repeating names
@emu_page.route('project/rename/<id>/<bundle_id>', methods=['POST'])
def rename_bundle(id, bundle_id):
    proj, resp = check_project(id, modify=True)
    if not proj:
        return resp

    if bundle_id not in proj['bundles']:
        return abort(404)

    new_session = None
    new_name = None

    if 'session' in request.form:
        new_session = request.form['session']
        new_session = ''.join(c for c in new_session if c.isalnum()).rstrip()
    if 'name' in request.form:
        new_name = request.form['name']
        new_name = ''.join(c for c in new_name if c.isalnum()).rstrip()

    bundle = proj['bundles'][bundle_id]

    if new_session and new_session != bundle['session']:
        bundle['session'] = new_session

    if new_name and new_name != bundle['name']:
        new_name = find_unique_name(proj, bundle['session'], new_name)
        bundle['name'] = new_name

    new_bundle_id = f'{bundle["session"]}_{bundle["name"]}'

    if new_bundle_id != bundle_id:
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$set': {f'bundles.{new_bundle_id}': bundle}})
        db.clarin.emu.update_one({'_id': ObjectId(id)}, {'$unset': {f'bundles.{bundle_id}': 1}})

    return redirect('/emu/project/' + urllib.parse.quote(str(id)))


@emu_page.route('project/add_trans/<id>', methods=['POST'])
def add_trans(id):
    proj, resp = check_project(id, modify=True)
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
    proj, resp = check_project(id, modify=True)
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


@emu_page.route('project/remove_bndl/<id>')
def remove_bndl_all(id):
    proj, resp = check_project(id, modify=True)
    if not proj:
        return resp

    for name in proj['bundles']:
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
    proj, resp = check_project(id, modify=True)
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
    proj, resp = check_project(id, modify=True)
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
    proj, resp = check_project(id, modify=True)
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
    proj, resp = check_project(id, modify=True)
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
    url = f'wss://{server}:{config.emu.webapp_port}/{id}'
    return redirect('http://ips-lmu.github.io/EMU-webApp/?autoConnect=true&serverUrl=' + urllib.parse.quote_plus(url))


@emu_page.route('project/download/<id>')
def download(id):
    proj, resp = check_project(id)
    if not proj:
        return resp

    res_id = tools.tasks.start_emu_package(proj, id)

    return redirect(f'/emu/project/{id}/view/{res_id}')


@emu_page.route('project/<id>/view/<res_id>')
@register_breadcrumb(emu_page, '.project.view', _(u'view_any_tytuł'))
def project_view(id, res_id):
    return ui_view(res_id)


@emu_page.route('project/<id>/multiview/<res_a>/<res_b>')
@register_breadcrumb(emu_page, '.project.multiview', _(u'view_any_tytuł'))
def project_multiview(id, res_a, res_b):
    return ui_view_multi(res_a, res_b)
