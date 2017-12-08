import os
import sys
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, session, abort, redirect, request, logging
from flask_babel import Babel

from EMU import emu_page
from Tools import tools_page
from config import config

app = Flask(__name__)
app.register_blueprint(tools_page, url_prefix='/tools/')
app.register_blueprint(emu_page, url_prefix='/emu/')
babel = Babel(app)

filename = os.path.join(config.proj_root, 'secret_key')
try:
    app.config['SECRET_KEY'] = open(filename, 'rb').read()
except IOError:
    print 'Error: No secret key. Create it with:'
    if not os.path.isdir(os.path.dirname(filename)):
        print 'mkdir -p', os.path.dirname(filename)
    print 'head -c 24 /dev/urandom >', filename
    sys.exit(-1)

formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
handler = RotatingFileHandler(os.path.join(config.proj_root, 'debug.log'), maxBytes=10000, backupCount=1)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)


@app.before_request
def log_request_info():
    app.logger.debug('Request {}'.format(request.url))
    for name, file in request.files.iteritems():
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        file.seek(0)
        app.logger.debug('-includes file >>{}<< of size {} bytes'.format(name, file_length))


@app.route('/')
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
def korpusy():
    return render_template('korpusy.html')


@app.route('/kontakt')
def kontakt():
    return render_template('kontakt.html')


@babel.localeselector
def get_locale():
    if 'lang' in session:
        return session['lang']
    return 'pl'


if __name__ == '__main__':
    app.run(debug=True)
