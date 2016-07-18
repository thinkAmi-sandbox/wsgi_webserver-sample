import sys
import socket
import io

# コールバック関数で受け取るレスポンスヘッダ用グローバル変数
headers_set = []


def main(ip_address, port, application):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((ip_address, port))
    server.listen(1)
    print("クライアントからの接続を待ちます")
    connection, client_address = server.accept()
    byte_request = connection.recv(1024)

    # WSGIで使うenvで必要なため、サーバ名を取得する
    server_name = socket.getfqdn(ip_address)

    # -----------------------------------------------------------
    # WSGIサーバとして必要な、2つの処理
    # 1.WSGIで使う環境変数を取得
    env = get_environ(byte_request, server_name, port)

    # 2.WSGI環境変数と、コールバック関数を指定して、WSGIアプリを実行
    byte_response_body = application(env, start_response)
    # -----------------------------------------------------------

    # WSGIアプリからのレスポンスを元に、
    # 接続しているクライアントへレスポンスを返す
    finish_response(connection, byte_response_body)


def get_environ(byte_request, server_name, port):
    # クライアントからのリクエストには
    # バイト列で、リクエストライン + リクエストヘッダ + リクエストボディが、改行コード付きで設定
    print("----request header----")
    print(byte_request)

    # WSGIの環境変数としてリクエストラインを使うため、
    # 改行コードで分割して、一行目のリクエストラインだけを取り出す
    byte_request_line = byte_request.splitlines()[0]
    str_request_line = byte_request_line.decode('utf-8')
    str_request_line_without_crlf = str_request_line.rstrip('\r\n')
    request_method, path, request_version = str_request_line_without_crlf.split()

    # 以下に説明あり
    # https://knzm.readthedocs.io/en/latest/pep-3333-ja.html#environ-variables
    env = {}
    env['wsgi.version']      = (1, 0)   # WSGIのバージョン：決め打ち
    env['wsgi.url_scheme']   = 'http'   # urlのスキーム(http/https)
    env['wsgi.input']        = io.BytesIO(byte_request)    # HTTP リクエスト本体のバイト列を読み出すことができる入力ストリーム 
    env['wsgi.errors']       = sys.stderr # エラー出力を書き込むことができる出力ストリーム
    env['wsgi.multithread']  = False # アプリケーションオブジェクトが同じプロセスの中で 同時に別のスレッドによって呼び出されることがあるなら、この値は true
    env['wsgi.multiprocess'] = False # 等価なアプリケーションオブジェクトが、同時に別の プロセスによって呼び出されることがあるなら、この値は true 
    env['wsgi.run_once']     = False # サーバまたはゲートウェイが、プロセスの寿命の間にアプリケーションが呼び出されるのはこの 1回だけであると期待する時にtrue
    env['REQUEST_METHOD']    = request_method    # GET
    env['PATH_INFO']         = path              # /
    env['SERVER_NAME']       = server_name       # FQDN
    env['SERVER_PORT']       = str(port)         # 8888

    return env


def start_response(status, response_headers, exc_info=None):
    '''
    WSGIサーバとして必要な、WSGIアプリから呼ばれるコールバック関数
    この関数内でしかWSGIアプリからレスポンスヘッダを受け取れないので、
    グローバル変数にレスポンスヘッダを保持しておく
    '''

    # 任意の内容の、WSGIサーバで追加するレスポンスヘッダ
    server_headers = [
        ('Date', 'Sat, 16 Jul 2016 00:00:00 JST'),
        ('Server', 'HenaWSGIServer 0.1'),
    ]

    # コールバック関数の戻り値として`headers_set`を戻したいが、
    # サーバ側で受け取ることができないため、グローバル変数に渡しておく
    # グローバル変数`headers_set`にアクセスするため、globalで宣言しておく
    global headers_set
    headers_set = [status, response_headers + server_headers]


def finish_response(connection, byte_response_body):
    try:
        # グローバル変数に格納されたレスポンスヘッダと
        # コールバックで受け取ったレスポンスボディの内容を確認
        print("----response_headers_set----")
        print(headers_set)
        print("----response_body----")
        print(byte_response_body)

        # コールバック関数で設定された`headers_set`の値は、
        # ['200 OK', [('Content-Length', '391'), ('Content-Type', 'text/html; charset=UTF-8'), ('Date', 'Sat, 16 Jul 2016 00:00:00 JST'), ('Server', 'HenaWSGIServer 0.1')]]
        # のような値であるため、アンパック代入を使って、ステータスコードとレスポンスヘッダを分離する
        status, response_headers = headers_set

        # WSGIを使っていないアプリとは異なり、
        # 下記の関数のように、レスポンスを一行ごとに送信した場合、
        # 正しいレスポンスとならないので注意
        # send_each_line(connection, status, response_headers, byte_response_body)

        # ステータスラインからレスポンスボディまで、一括で送信する
        # ステータスライン
        str_response = 'HTTP/1.1 {status}\r\n'.format(status=status)

        # レスポンスヘッダ
        for header in response_headers:
            str_response += '{0}: {1}\r\n'.format(*header)

        # レスポンスヘッダとレスポンスボディを分ける、改行コード
        str_response += '\r\n'

        # レスポンスボディ
        for byte_body in byte_response_body:
            # WSGIアプリからもらったレスポンスボディはバイト列
            # レスポンスヘッダなどと結合するため、一度文字列へとデコードする
            str_response += byte_body.decode('utf-8')

        # クライアントへ送信
        # バイト列で送信する必要があるため、エンコードしてから送信
        connection.sendall(str_response.encode('utf-8'))

    finally:
        connection.close()


def send_each_line(connection, status, response_headers, byte_response_body):
    '''実際には使わない関数'''
    # ステータスライン
    write_line(connection, 'HTTP/1.1 {status}\r\n'.format(status=status))

    # レスポンスヘッダ
    for header in response_headers:
        # レスポンスヘッダは、"('Content-Length', '391')"のようなタプルオブジェクトであるため
        # format時にアンパックして渡す
        write_line(connection, '{0}: {1}\r\n'.format(*header))

    # レスポンスヘッダとレスポンスボディを分ける改行コード
    write_line(connection, "")

    # レスポンスボディ
    # バイト列 + 改行コードのリストが返ってきてるので、
    # リストの要素ごとに送信する
    for body in byte_response_body:
        connection.sendall(body)

def write_line(connection, str_data):
    '''実際には使わない関数'''
    str_data_with_crlf = str_data + "\r\n"
    byte_data = str_data_with_crlf.encode("utf-8")
    connection.sendall(byte_data)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('"module:callable"の形でWSGIアプリケーションを指定してください')

    # 引数で指定したWSGIアプリのインスタンスを生成する
    app_path = sys.argv[1]
    module, application = app_path.split(':')
    module = __import__(module)
    wsgi_app = getattr(module, application)

    # WSGIサーバの起動
    main('', 8888, wsgi_app)