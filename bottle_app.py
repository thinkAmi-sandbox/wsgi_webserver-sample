import os
import bottle
from bottle import route, template, static_file, TEMPLATE_PATH

# Change working directory so relative paths (and template lookup) work again
os.chdir(os.path.dirname(__file__))


TEMPLATE_PATH.append("./views")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')


# Bottle app
@route('/')
def index():
    # Bottleで設定するレスポンスヘッダを確認
    print("----Bottle's response_header----")
    print(bottle.response.headerlist)
    return template('index.html')

@route('/hello')
def hello():
    return 'はろー　Bottle!'

# static files
@route('/static/css/<filename>')
def static_css(filename):
    return static_file(filename, root=STATIC_DIR + '/css/')

@route('/static/images/<filename>')
def static_css(filename):
    return static_file(filename, root=STATIC_DIR + '/images/')

app = bottle.default_app()