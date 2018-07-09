import sys
from logging import Formatter, DEBUG
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, session, abort, redirect, request, logging
from flask_babel import Babel, lazy_gettext
from flask_breadcrumbs import Breadcrumbs, register_breadcrumb

from EMU import emu_page
from Tools import tools_page
from config import config

app = Flask(__name__)
app.register_blueprint(tools_page, url_prefix='/tools/')
app.register_blueprint(emu_page, url_prefix='/emu/')
babel = Babel(app)
Breadcrumbs(app=app)

filename = config.proj_root / 'secret_key'
try:
    app.config['SECRET_KEY'] = open(filename, 'rb').read()
except IOError:
    print('Error: No secret key. Create it with:')
    if not filename.is_dir():
        print(f'mkdir -p {filename.parent}')
    print(f'head -c 24 /dev/urandom > {filename}')
    sys.exit(-1)

formatter = Formatter('[%(asctime)s] %(levelname)s - %(message)s')
handler = RotatingFileHandler(config.proj_root / 'debug.log', maxBytes=10 * 1024 * 1024, backupCount=5)
handler.setLevel(DEBUG)
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(DEBUG)


# @app.before_request
# def log_request_info():
#     app.logger.debug(f'Request {request.url}')
#     for name, file in request.files.items():
#         file.seek(0, os.SEEK_END)
#         file_length = file.tell()
#         file.seek(0)
#         app.logger.debug(f'-includes file >>{name}<< of size {file_length} bytes')


@app.route('/')
@register_breadcrumb(app, '.', lazy_gettext(u'strona_główna'))
def index():
    return render_template('index.html')


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('img/favicon.ico')


@app.route('/lang/<code>')
def lang(code):
    if code not in ('en', 'pl'):
        return abort(404)
    session['lang'] = code
    return redirect(request.referrer)


@app.route('/korpusy')
@register_breadcrumb(app, '.corpora', lazy_gettext(u'korpusy'))
def korpusy():
    return render_template('korpusy.html')


@app.route('/kontakt')
@register_breadcrumb(app, '.contact', lazy_gettext(u'kontakt'))
def kontakt():
    return render_template('kontakt.html')


@app.route('/transcriber/')
def g2p_redirect():
    return redirect('/tools/ui/phonetize/word')

@babel.localeselector
def get_locale():
    if 'lang' in session:
        return session['lang']
    return 'pl'


if __name__ == '__main__':
    app.run(debug=False)
