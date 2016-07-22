import socket
import io
import sys
import threading

class MyWSGIHandler(object):
    def __init__(self, client_connection, client_address, application, server_name, server_port):
        self.connection = client_connection
        self.address = client_address
        self.application = application
        self.server_name = server_name
        self.server_port = server_port

        # コールバック関数で取得できるステータスコード・レスポンスヘッダの保存先
        self.headers_set = []


    def handle_one_request(self):
        request_data = self.connection.recv(1024)
        env = self.get_environ(request_data)
        byte_response_body = self.application(env, self.start_response)
        self.finish_response(byte_response_body)


    def get_environ(self, byte_request):
        byte_request_line = byte_request.splitlines()[0]
        str_request_line = byte_request_line.decode('utf-8')
        str_request_line_without_crlf = str_request_line.rstrip('\r\n')
        request_method, path, request_version = str_request_line_without_crlf.split()

        env = {}
        env['wsgi.version']      = (1, 0)
        env['wsgi.url_scheme']   = 'http'
        env['wsgi.input']        = io.BytesIO(byte_request) 
        env['wsgi.errors']       = sys.stderr
        env['wsgi.multithread']  = True  # マルチスレッドだからTrueでいいのかな 
        env['wsgi.multiprocess'] = False # マルチプロセスではないのでFalse 
        env['wsgi.run_once']     = True  # 複数回呼ばれそうなので、True
        env['REQUEST_METHOD']    = request_method        # GET
        env['PATH_INFO']         = path                  # /
        env['SERVER_NAME']       = self.server_name      # FQDN
        env['SERVER_PORT']       = str(self.server_port) # 8888

        return env


    def start_response(self, status, response_headers, exc_info=None):
        server_headers = [
            ('Date', 'Sat, 16 Jul 2016 00:00:00 JST'),
            ('Server', 'MyWSGIServer 0.2'),
        ]
        self.headers_set = [status, response_headers + server_headers]


    def finish_response(self, byte_response_body):
        try:
            status, response_headers = self.headers_set

            # ステータスライン
            str_response = 'HTTP/1.1 {status}\r\n'.format(status=status)

            # レスポンスヘッダ
            for header in response_headers:
                str_response += '{0}: {1}\r\n'.format(*header)

            # レスポンスヘッダとレスポンスボディを分ける、改行コード
            str_response += '\r\n'

            # レスポンスボディ
            print(byte_response_body)
            # 画像データのレスポンスがあった場合のオブジェクト
            # => <bottle.WSGIFileWrapper object at 0x03305B30>
            # これをそのままdecodeするとエラーになる
            # => UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89 in position 0: invalid start byte

            if 'image' in str_response:
                # 画像データの場合
                # レスポンスヘッダを送信した後、sendfile()で画像データを送信する
                # https://github.com/j4cbo/chiral/blob/master/chiral/web/httpd.py#L135
                # http://docs.python.jp/3/library/socket.html#socket.socket.sendfile
                self.connection.sendall(str_response.encode('utf-8'))
                self.connection.sendfile(byte_response_body)

            else:
                # 画像データ以外の場合
                for byte_body in byte_response_body:
                    # WSGIアプリからもらったレスポンスボディはバイト列
                    # レスポンスヘッダなどと結合するため、一度文字列へとデコードする
                    str_response += byte_body.decode('utf-8')

                # クライアントへ送信
                # バイト列で送信する必要があるため、エンコードしてから送信
                self.connection.sendall(str_response.encode('utf-8'))

        finally:
            self.connection.close()


class MyWSGIServer(object):
    def __init__(self, ip_address, port, wsgi_app):
        self.listen_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )
        self.listen_socket.bind((ip_address, port))
        self.listen_socket.listen(1)
        self.application = wsgi_app
        self.server_name = socket.gethostname()
        self.server_port = port
    
    def serve_forever(self):
        while True:
            client_connection, client_address = self.listen_socket.accept()
            handler = MyWSGIHandler(client_connection, client_address, 
                self.application, self.server_name, self.server_port)

            # 念のため、オブジェクト識別値を確認
            print("handler object id: {}".format(id(handler)))

            # スレッドで画像ファイルとかも受け取れるようにする
            thread = threading.Thread(target=handler.handle_one_request)
            thread.start()


def make_server(ip_address, port, wsgi_app):
    server = MyWSGIServer(ip_address, port, wsgi_app)
    return server


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('"module:callable"の形でWSGIアプリケーションを指定してください')

    app_path = sys.argv[1]
    module, application = app_path.split(':')
    module = __import__(module)
    wsgi_app = getattr(module, application)

    # WSGIサーバの起動
    httpd = make_server('', 8888, wsgi_app)
    print('MyWSGIServer: ホスト{address}、ポート{port}にて起動しました\n'.format(
        address=httpd.server_name, port=httpd.server_port))
    httpd.serve_forever()