"""
API 탐색기 웹 서버 (로컬 + Vercel 호환)
- 정적 파일 서빙 (index.html, JSON)
- API 엔드포인트:
  POST /api/refresh-trends  → 즉시 202 반환, 백그라운드에서 Claude AI 분석
  GET  /api/trends           → 최신 트렌드 데이터 (polling용)

사용법: python server.py
"""

import http.server
import json
import os
import sys
import threading
from datetime import datetime
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding='utf-8')

# api/ 폴더를 import 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api'))

PORT = 8080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 현재 처리 상태 (스레드 안전하게 공유)
_refresh_lock = threading.Lock()
_refresh_status = {'running': False, 'message': ''}



def run_refresh_background(api_key=None):
    """백그라운드에서 트렌드 분석 실행 (타임아웃 걱정 없이)"""
    global _refresh_status
    try:
        from importlib import import_module
        mod = import_module('refresh-trends')

        # 브라우저에서 전달된 키 우선 사용
        if api_key:
            os.environ['ANTHROPIC_API_KEY'] = api_key

        _refresh_status['message'] = '뉴스 수집 중...'
        news = mod.fetch_news()
        if not news:
            _refresh_status['message'] = '뉴스 수집 실패'
            return

        _refresh_status['message'] = f'뉴스 {len(news)}건 분석 중...'
        keyword_counts, category_counts, keyword_news = mod.extract_keywords(news)
        ai_ideas = mod.generate_ideas_with_claude(news, keyword_counts, category_counts)

        if ai_ideas is None:
            _refresh_status['message'] = 'ANTHROPIC_API_KEY 환경변수를 설정하세요.'
            return

        _refresh_status['message'] = 'API 매칭 중...'
        all_apis = mod.load_apis()
        if all_apis:
            ai_ideas = mod.match_real_apis(ai_ideas, all_apis)

        trend_ideas = [i for i in ai_ideas if i.get('type') == 'trend']
        smart_ideas = [i for i in ai_ideas if i.get('type') == 'smart']
        random_ideas = [i for i in ai_ideas if i.get('type') == 'random']

        result = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'news_count': len(news),
            'top_keywords': [{'keyword': k, 'count': c} for k, c in keyword_counts.most_common(20)],
            'top_categories': [{'category': c, 'count': n} for c, n in category_counts.most_common()],
            'ideas': {
                'trend': trend_ideas,
                'smart': smart_ideas,
                'random': random_ideas,
            },
            'total_ideas': len(ai_ideas),
        }

        trends_path = os.path.join(SCRIPT_DIR, 'trends.json')
        with open(trends_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=1)

        _refresh_status['message'] = f"완료: {len(ai_ideas)}개 아이디어 (뉴스 {len(news)}건)"
        print(f"[AI] 분석 완료: {len(ai_ideas)}개 아이디어, 뉴스 {len(news)}건")

    except Exception as e:
        _refresh_status['message'] = f'오류: {e}'
        print(f"[AI] 오류: {e}")
    finally:
        with _refresh_lock:
            _refresh_status['running'] = False



class AppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/refresh-trends':
            self.handle_refresh_trends()
        else:
            self.send_error(404)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/trends':
            self.handle_get_trends()
        elif path == '/api/refresh-status':
            self.handle_get_status()
        else:
            super().do_GET()

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, OSError):
            pass  # 브라우저가 연결을 먼저 끊은 경우 무시

    def handle_refresh_trends(self):
        """즉시 202 반환 후 백그라운드에서 처리"""
        global _refresh_status
        with _refresh_lock:
            if _refresh_status['running']:
                self.send_json({'status': 'running', 'message': _refresh_status['message']})
                return
            _refresh_status['running'] = True
            _refresh_status['message'] = '시작 중...'

        # POST body에서 API 키 읽기
        api_key = None
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                api_key = body.get('api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        except Exception:
            api_key = os.environ.get('ANTHROPIC_API_KEY', '')

        if not api_key:
            with _refresh_lock:
                _refresh_status['running'] = False
            self.send_json({'status': 'error', 'message': 'API 키를 입력해주세요.'})
            return

        t = threading.Thread(target=run_refresh_background, args=(api_key,), daemon=True)
        t.start()
        self.send_json({'status': 'started', 'message': 'AI 분석을 시작했습니다. 잠시 후 자동으로 업데이트됩니다.'})

    def handle_get_trends(self):
        trends_file = os.path.join(SCRIPT_DIR, 'trends.json')
        if os.path.exists(trends_file):
            with open(trends_file, 'r', encoding='utf-8') as f:
                self.send_json(json.load(f))
        else:
            self.send_json({'error': 'No trends data'}, 404)

    def handle_get_status(self):
        self.send_json({
            'running': _refresh_status['running'],
            'message': _refresh_status['message'],
        })


    def log_message(self, format, *args):
        try:
            msg = str(args[0]) if args else ''
            if '/api/' in msg:
                print(f"[API] {msg}")
        except Exception:
            pass


def is_port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def main():
    if is_port_in_use(PORT):
        print(f"이미 실행 중: http://localhost:{PORT}")
        return

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    print("=" * 50)
    print("API 탐색기 웹 서버")
    print(f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"주소: http://localhost:{PORT}")
    print(f"AI: {'Claude Haiku (활성)' if api_key else '❌ ANTHROPIC_API_KEY 미설정'}")
    print("=" * 50)

    import socketserver
    class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    server = ThreadingServer(('', PORT), AppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.server_close()


if __name__ == '__main__':
    main()
