from flask import Flask, render_template, session, abort, redirect, request
from flask_babel import Babel

from EMU import emu_page
from Tools import tools_page

app = Flask(__name__)
app.register_blueprint(tools_page, url_prefix='/tools/')
app.register_blueprint(emu_page, url_prefix='/emu/')
babel = Babel(app)

app.secret_key = '\x92c\xb0\x00x \x19y\xdanY\xba\x8d|\xac\x1a\xc4\x16Q\xc6\xa6\xb1\x87\x89'


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


@babel.localeselector
def get_locale():
    if 'lang' in session:
        return session['lang']
    return 'pl'


if __name__ == '__main__':
    app.run()
