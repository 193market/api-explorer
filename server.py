"""
API 탐색기 웹 서버 (로컬 + Vercel 호환)
- 정적 파일 서빙 (index.html, JSON)
- API 엔드포인트:
  POST /api/refresh-trends  → Claude AI로 뉴스 분석 + 아이디어 생성
  GET  /api/trends           → 최신 트렌드 데이터

사용법: python server.py
"""

import http.server
import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding='utf-8')

# api/ 폴더를 import 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api'))

PORT = 8080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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
        else:
            super().do_GET()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def handle_refresh_trends(self):
        """Claude AI로 트렌드 분석"""
        try:
            # api/refresh-trends.py의 함수 재사용
            from importlib import import_module
            mod = import_module('refresh-trends')

            news = mod.fetch_news()
            if not news:
                self.send_json({'success': False, 'message': '뉴스 수집 실패'}, 500)
                return

            keyword_counts, category_counts, keyword_news = mod.extract_keywords(news)
            ai_ideas = mod.generate_ideas_with_claude(news, keyword_counts, category_counts)

            if ai_ideas is None:
                self.send_json({'success': False, 'message': 'ANTHROPIC_API_KEY 환경변수를 설정하세요.'}, 500)
                return

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

            # trends.json 저장
            trends_path = os.path.join(SCRIPT_DIR, 'trends.json')
            with open(trends_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=1)

            self.send_json({
                'success': True,
                'message': f"AI 분석 완료: {len(ai_ideas)}개 아이디어 (뉴스 {len(news)}건)",
                'trends': result,
            })
        except Exception as e:
            self.send_json({'success': False, 'message': str(e)}, 500)

    def handle_get_trends(self):
        trends_file = os.path.join(SCRIPT_DIR, 'trends.json')
        if os.path.exists(trends_file):
            with open(trends_file, 'r', encoding='utf-8') as f:
                self.send_json(json.load(f))
        else:
            self.send_json({'error': 'No trends data'}, 404)

    def log_message(self, format, *args):
        if '/api/' in (args[0] if args else ''):
            print(f"[API] {args[0]}")


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

    server = http.server.HTTPServer(('', PORT), AppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.server_close()


if __name__ == '__main__':
    main()
