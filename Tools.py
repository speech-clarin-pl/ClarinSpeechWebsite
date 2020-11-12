import codecs
import json
import pprint
import time

from flask import Blueprint, render_template, make_response, request, abort, send_file, Response, stream_with_context, \
    redirect
from flask_babel import lazy_gettext
from flask_breadcrumbs import register_breadcrumb

import tools.phonetize
import tools.segmentation
import tools.tasks
import tools.utils
from config import config

tools_page = Blueprint('tools_page', __name__, template_folder='templates')


@tools_page.route('/')
@register_breadcrumb(tools_page, '.', lazy_gettext(u'tool_tytuł'))
def index():
    return render_template('tools.html')


@tools_page.route('annotationpro')
@register_breadcrumb(tools_page, '.tool_annotationpro', lazy_gettext(u'annotation_tytuł'))
def annotationpro():
    return render_template('annotationpro.html')


@tools_page.route('upload/<type>', methods=['POST'])
def upload(type):
    if 'file' not in request.files:
        return abort(404)
    file = request.files['file']
    return tools.utils.upload_file(file, type)


# TODO - security?!
# TODO - warning that filenames can pose a problems if they aren't ASCII or alphanumeric
@tools_page.route('download/<id>')
def download(id):
    file = tools.utils.get_file(id)
    if not file:
        return abort(404)
    else:
        if 'error' in file:
            return abort(500)
        if not file['file']:
            resp = make_response('503 Service Unavailable', 503)
            resp.headers.extend({'Retry-After': 1})
            return resp
        else:
            filepath = config.work_dir / file['file']
            resp = make_response(send_file(str(filepath)))
            resp.headers['Access-Control-Allow-Origin'] = 'http://ips-lmu.github.io'
            resp.headers['Content-disposition'] = f'attachment; filename={filepath.name}'
            return resp


@tools_page.route('delete/<id>')
def delete(id):
    if config.allow_res_delete:
        tools.utils.invalidate_file(id)
    return redirect(f'/tools/ui/view/{id}')


@tools_page.route('status/<id>')
def status(id):
    file = tools.utils.get_file(id)
    if not file:
        return abort(404)
    else:
        if 'error' in file:
            return 'error: ' + file['error']
        elif file['file']:
            return 'ok'
        else:
            return 'wait'


pp = pprint.PrettyPrinter(indent=4)


@tools_page.route('status/debug/<id>')
def status_debug(id):
    file = tools.utils.get_file(id)
    return pp.pformat(file)


@tools_page.route('ui/view/<id>')
@register_breadcrumb(tools_page, '.view', lazy_gettext(u'view_any_tytuł'))
def ui_view(id):
    file = tools.utils.get_file(id)
    if not file:
        return abort(404)
    else:
        if file['type'] == 'transcript':
            from_id = None
            from_audio = False
            if 'from' in file:
                from_id = file['from']['input']
                from_file = tools.utils.get_file(from_id)
                if from_file != None and from_file['type'] == 'audio':
                    from_audio = True
            return render_template('view_transcription.html', res_id=id, from_id=from_id, from_audio=from_audio,
                                   allow_delete=config.allow_res_delete)
        if file['type'] == 'audio':
            from_id = None
            if 'from' in file:
                from_id = file['from']['input']
            return render_template('view_audio.html', res_id=id, from_id=from_id, allow_delete=config.allow_res_delete)
        if file['type'] == 'segmentation':
            from_audio = None
            from_trans = None
            from_seg = None
            if 'from' in file:
                if 'audio' in file['from']:
                    from_audio = file['from']['audio']
                if 'transcript' in file['from']:
                    from_trans = file['from']['transcript']
                if 'seg' in file['from']:
                    from_seg = file['from']['seg']
            return render_template('view_segmentation.html', res_id=id, from_audio=from_audio, from_trans=from_trans,
                                   from_seg=from_seg, server_url=request.url_root, allow_delete=config.allow_res_delete)
        else:
            return render_template('view_any.html', res_id=id, allow_delete=config.allow_res_delete)


@tools_page.route('ui/multiview/<ida>/<idb>')
@register_breadcrumb(tools_page, '.multiview', lazy_gettext(u'view_any_tytuł'))
def ui_view_multi(ida, idb):
    file_a = tools.utils.get_file(ida)
    file_b = tools.utils.get_file(idb)
    if not file_a or not file_b:
        return abort(404)
    if file_a['type'] == 'audio' and file_b['type'] == 'transcript':
        return render_template('multiview_audio_trans.html', audio_id=ida, trans_id=idb)
    elif file_a['type'] == 'transcript' and file_b['type'] == 'audio':
        return render_template('multiview_audio_trans.html', audio_id=idb, trans_id=ida)
    else:
        return render_template('multiview_any.html', res_a=ida, res_b=idb)


@tools_page.route('ui/phonetize/word')
@register_breadcrumb(tools_page, '.tool_g2p_word', lazy_gettext(u'g2p_tytuł'))
def ui_phonetize_word():
    return render_template('tool_g2p_word.html', server_url=request.url_root)


@tools_page.route('ui/phonetize/list')
@register_breadcrumb(tools_page, '.tool_g2p_list', lazy_gettext(u'g2p_wordlist_tytuł'))
def ui_phonetize_wordlist():
    return render_template('tool_g2p_list.html', server_url=request.url_root)


@tools_page.route('ui/text/normalize')
@register_breadcrumb(tools_page, '.tool_text_to_text', lazy_gettext(u'textnorm_tytuł'))
def ui_normalize():
    return render_template('tool_text_to_text.html', server_url=request.url_root)


@tools_page.route('ui/audio/normalize')
@register_breadcrumb(tools_page, '.tool_audio_to_audio', lazy_gettext(u'audionorm_tytuł'))
def ui_audio_normalize():
    return render_template('tool_audio_to_audio.html', server_url=request.url_root)


@tools_page.route('ui/align/forced')
@register_breadcrumb(tools_page, '.tool_align_forced', lazy_gettext(u'forcealign_tytuł'))
def ui_align_forced():
    return render_template('tool_align.html', server_url=request.url_root, forced=True)


@tools_page.route('ui/align/segment')
@register_breadcrumb(tools_page, '.tool_align_segment', lazy_gettext(u'segalign_tytuł'))
def ui_align_segment():
    return render_template('tool_align.html', server_url=request.url_root, forced=False)


@tools_page.route('ui/speech/recognize')
@register_breadcrumb(tools_page, '.tool_reco', lazy_gettext(u'reco_tytuł'))
def ui_speech_recognize():
    return render_template('tool_reco.html', server_url=request.url_root)

@tools_page.route('ui/speech/adapt/am')
@register_breadcrumb(tools_page, '.tool_adapt_am', lazy_gettext(u'adapt_am_tytuł'))
def ui_speech_adapt_am():
    return render_template('tool_adapt_am.html', server_url=request.url_root)

@tools_page.route('ui/speech/diarize')
@register_breadcrumb(tools_page, '.tool_diar', lazy_gettext(u'diar_tytuł'))
def ui_speech_diarize():
    return render_template('tool_diar.html', server_url=request.url_root)


@tools_page.route('ui/speech/vad')
@register_breadcrumb(tools_page, '.tool_vad', lazy_gettext(u'vad_tytuł'))
def ui_speech_vad():
    return render_template('tool_vad.html', server_url=request.url_root)


@tools_page.route('ui/speech/kws')
@register_breadcrumb(tools_page, '.tool_kws', lazy_gettext(u'kws_tytuł'))
def ui_speech_kws():
    return render_template('tool_kws.html', server_url=request.url_root)


@tools_page.route('phonetize/word/<word>')
def phonetize_word(word):
    script = 'sampa'
    if 'ipa' in request.args:
        script = 'ipa'
    if 'sampa' in request.args:
        script = 'sampa'

    ret = tools.phonetize.phonetize_word(word, script)
    if not ret:
        resp = make_response('503 Service Unavailable', 503)
        resp.headers.extend({'Retry-After': 1})
        return resp
    else:
        return json.dumps(ret)


@tools_page.route('phonetize/list', methods=['POST'])
def phonetize_wordlist_file():
    script = None
    if 'ipa' in request.args:
        script = 'ipa'
    if 'sampa' in request.args:
        script = 'sampa'

    if 'file' not in request.files:
        return abort(404)

    def generate():
        file = request.files['file']
        for line in file:
            word = line.strip().decode('utf-8')
            ret = tools.phonetize.phonetize_word(word, script)
            for trans in ret:
                yield f'{word} {trans}\n'

    return Response(stream_with_context(generate()), mimetype='text/plain')


@tools_page.route('text/normalize', methods=['POST'])
def normalize_file():
    if 'file' not in request.files:
        return abort(404)
    file = request.files['file']

    input_id = tools.utils.upload_file(file, 'transcript')

    output_id = tools.tasks.start_text_normalize(input_id)

    time.sleep(0.1)

    return json.dumps({'input': input_id, 'output': output_id})


@tools_page.route('text/normalize/<id>')
def normalize_id(id):
    output_id = tools.tasks.start_text_normalize(id)

    time.sleep(0.1)

    return output_id


@tools_page.route('text/modify/<id>', methods=['POST'])
def text_modify(id):
    redirect_url = request.form['redirect_url']
    text = request.form['text']

    res = tools.utils.get_file(id)
    if not res or not res['file']:
        return abort(404)

    file = res['file']

    with codecs.open(config.work_dir / file, mode='w', encoding='utf-8') as f:
        f.write(text)

    tools.utils.update_file(id, file)

    return redirect(redirect_url)


@tools_page.route('audio/normalize', methods=['POST'])
def audio_normalize_file():
    if 'file' not in request.files:
        return abort(404)
    file = request.files['file']
    input_id = tools.utils.upload_file(file, 'audio')

    output_id = tools.tasks.start_audio_normalize(input_id)

    time.sleep(0.1)

    return json.dumps({'input': input_id, 'output': output_id})


@tools_page.route('audio/normalize/<id>')
def audio_normalize_id(id):
    output_id = tools.tasks.start_audio_normalize(id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/forcealign', methods=['POST'])
def speech_forcealign_file():
    if 'audio' not in request.files or 'transcript' not in request.files:
        return abort(404)
    audio = request.files['audio']
    transcript = request.files['transcript']
    audio_id = tools.utils.upload_file(audio, 'audio')
    transcript_id = tools.utils.upload_file(transcript, 'transcript')

    output_id = tools.tasks.start_speech_forcealign(audio_id, transcript_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'transcript': transcript_id, 'output': output_id})


@tools_page.route('speech/forcealign/<audio_id>/<transcript_id>')
def speech_forcealign_id(audio_id, transcript_id):
    output_id = tools.tasks.start_speech_forcealign(audio_id, transcript_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/segmentalign', methods=['POST'])
def speech_segmentalign_file():
    if 'audio' not in request.files or 'transcript' not in request.files:
        return abort(404)
    audio = request.files['audio']
    transcript = request.files['transcript']
    audio_id = tools.utils.upload_file(audio, 'audio')
    transcript_id = tools.utils.upload_file(transcript, 'transcript')

    output_id = tools.tasks.start_speech_segmentalign(audio_id, transcript_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'transcript': transcript_id, 'output': output_id})


@tools_page.route('speech/segmentalign/<audio_id>/<transcript_id>')
def speech_segmentalign_id(audio_id, transcript_id):
    output_id = tools.tasks.start_speech_segmentalign(audio_id, transcript_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('textgrid/<id>', methods=['GET'])
def transcript_to_textgrid(id):
    file = tools.utils.get_file(id)
    if not file:
        return abort(404)

    if file['type'] != 'segmentation':
        return abort(404)

    script = None
    if 'script' in request.args:
        script = request.args['script']

    if not file['file']:
        resp = make_response('503 Service Unavailable', 503)
        resp.headers.extend({'Retry-After': 1})
        return resp

    ret = tools.segmentation.segmentation_to_textgrid(config.work_dir / file['file'], script=script)

    headers = {'Access-Control-Allow-Origin': 'http://ips-lmu.github.io',
               'Content-disposition': 'attachment; filename=output.TextGrid'}
    return Response(ret, mimetype='text/plain', headers=headers)


@tools_page.route('annot/<id>', methods=['GET'])
def transcript_to_emu_annot(id):
    file = tools.utils.get_file(id)
    if not file:
        return abort(404)

    if file['type'] != 'segmentation':
        return abort(404)

    script = None
    if 'script' in request.args:
        script = request.args['script']

    if not file['file']:
        resp = make_response('503 Service Unavailable', 503)
        resp.headers.extend({'Retry-After': 1})
        return resp

    ret = tools.segmentation.segmentation_to_emu_annot(config.work_dir / file['file'], 'output', script=script)

    headers = {'Access-Control-Allow-Origin': 'http://ips-lmu.github.io',
               'Content-disposition': 'attachment; filename=output_annot.josn'}

    return Response(ret, mimetype='application/json', headers=headers)


@tools_page.route('speech/reco', methods=['POST'])
def speech_recognize_file():
    if 'file' not in request.files:
        return abort(404)
    audio = request.files['file']
    audio_id = tools.utils.upload_file(audio, 'audio')

    output_id = tools.tasks.start_speech_recognize(audio_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'output': output_id})


@tools_page.route('speech/reco/<audio_id>')
def speech_recognize_id(audio_id):
    output_id = tools.tasks.start_speech_recognize(audio_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/adapt/am', methods=['POST'])
def speech_adapt_am_file():
    if 'file' not in request.files:
        return abort(404)
    archive = request.files['file']
    archive_id = tools.utils.upload_file(archive, 'archive')

    output_id = tools.tasks.start_speech_adapt_am(archive_id)

    time.sleep(0.1)

    return json.dumps({'archive': archive_id, 'output': output_id})


@tools_page.route('speech/adapt/am/<archive_id>')
def speech_adapt_am_id(archive_id):
    output_id = tools.tasks.start_speech_adapt_am(archive_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/vad', methods=['POST'])
def speech_vad_file():
    if 'file' not in request.files:
        return abort(404)
    audio = request.files['file']
    audio_id = tools.utils.upload_file(audio, 'audio')

    output_id = tools.tasks.start_speech_vad(audio_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'output': output_id})


@tools_page.route('speech/vad/<audio_id>')
def speech_vad_id(audio_id):
    output_id = tools.tasks.start_speech_vad(audio_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/diarize', methods=['POST'])
def speech_diarize_file():
    if 'file' not in request.files:
        return abort(404)
    audio = request.files['file']
    audio_id = tools.utils.upload_file(audio, 'audio')

    output_id = tools.tasks.start_speech_diarize(audio_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'output': output_id})


@tools_page.route('speech/diarize/<audio_id>')
def speech_diarize_id(audio_id):
    output_id = tools.tasks.start_speech_diarize(audio_id)

    time.sleep(0.1)

    return output_id


@tools_page.route('speech/kws', methods=['POST'])
def speech_kws_file():
    if 'audio' not in request.files or 'keywords' not in request.files:
        return abort(404)
    audio = request.files['audio']
    keywords = request.files['keywords']
    audio_id = tools.utils.upload_file(audio, 'audio')
    keywords_id = tools.utils.upload_file(keywords, 'wordlist')

    output_id = tools.tasks.start_speech_kws(audio_id, keywords_id)

    time.sleep(0.1)

    return json.dumps({'audio': audio_id, 'keywords': keywords_id, 'output': output_id})


@tools_page.route('speech/kws/<audio_id>/<keywords_id>')
def speech_kws_id(audio_id, keywords_id):
    output_id = tools.tasks.start_speech_kws(audio_id, keywords_id)

    time.sleep(0.1)

    return output_id
