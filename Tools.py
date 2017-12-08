import codecs
import json
import os
import pprint
import time

from flask import Blueprint, render_template, make_response, request, abort, send_file, Response, stream_with_context, \
    redirect

import tools.phonetize
import tools.segmentation
import tools.tasks
import tools.utils
from config import config

tools_page = Blueprint('tools_page', __name__, template_folder='templates')


@tools_page.route('/')
def index():
    return render_template('tools.html')


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
            filepath = os.path.join(config.work_dir, file['file'])
            resp = make_response(send_file(filepath))
            resp.headers['Access-Control-Allow-Origin'] = 'http://ips-lmu.github.io'
            resp.headers['Content-disposition'] = 'attachment; filename={}'.format(os.path.basename(filepath))
            return resp


@tools_page.route('delete/<id>')
def delete(id):
    tools.utils.invalidate_file(id)
    return u'Invalidated {}'.format(id)


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
                if from_file['type'] == 'audio':
                    from_audio = True
            return render_template('view_transcription.html', res_id=id, from_id=from_id, from_audio=from_audio)
        if file['type'] == 'audio':
            from_id = None
            if 'from' in file:
                from_id = file['from']['input']
            return render_template('view_audio.html', res_id=id, from_id=from_id)
        if file['type'] == 'segmentation':
            from_audio = None
            from_trans = None
            if 'from' in file:
                from_audio = file['from']['audio']
                from_trans = file['from']['transcript']
            return render_template('view_segmentation.html', res_id=id, from_audio=from_audio, from_trans=from_trans,
                                   server_url=request.url_root)
        else:
            return render_template('view_any.html', res_id=id)


@tools_page.route('ui/multiview/<ida>/<idb>')
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
def ui_phonetize_word():
    return render_template('tool_g2p_word.html', server_url=request.url_root)


@tools_page.route('ui/phonetize/list')
def ui_phonetize_wordlist():
    return render_template('tool_g2p_list.html', server_url=request.url_root)


@tools_page.route('ui/text/normalize')
def ui_normalize():
    return render_template('tool_text_to_text.html', server_url=request.url_root)


@tools_page.route('ui/audio/normalize')
def ui_audio_normalize():
    return render_template('tool_audio_to_audio.html', server_url=request.url_root)


@tools_page.route('ui/align/forced')
def ui_align_forced():
    return render_template('tool_align.html', server_url=request.url_root, forced=True)


@tools_page.route('ui/align/segment')
def ui_align_segment():
    return render_template('tool_align.html', server_url=request.url_root, forced=False)


@tools_page.route('ui/speech/recognize')
def ui_speech_recognize():
    return render_template('tool_reco.html', server_url=request.url_root)


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
                yield u'{} {}\n'.format(word, trans)

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

    with codecs.open(os.path.join(config.work_dir, file), mode='w', encoding='utf-8') as f:
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

    ret = tools.segmentation.segmentation_to_textgrid(os.path.join(config.work_dir, file['file']), script=script)

    headers = {}
    headers['Access-Control-Allow-Origin'] = 'http://ips-lmu.github.io'
    headers['Content-disposition'] = 'attachment; filename=output.TextGrid'
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

    ret = tools.segmentation.segmentation_to_emu_annot(os.path.join(config.work_dir, file['file']), 'output',
                                                       script=script)

    headers = {}
    headers['Access-Control-Allow-Origin'] = 'http://ips-lmu.github.io'
    headers['Content-disposition'] = 'attachment; filename=output_annot.josn'

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
