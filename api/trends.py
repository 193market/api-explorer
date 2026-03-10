"""
Vercel Serverless Function: 최신 트렌드 데이터 반환
정적 trends.json을 서빙 (refresh-trends에서 갱신)
"""

import json
import os
from http.server import BaseHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Vercel에서는 빌드 시 포함된 trends.json 로드
        trends_path = os.path.join(SCRIPT_DIR, '..', 'trends.json')
        if os.path.exists(trends_path):
            with open(trends_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
        else:
            body = json.dumps({'error': 'No trends data'}, ensure_ascii=False).encode('utf-8')
            self.send_response(404)

        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
