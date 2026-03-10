"""
Vercel Serverless Function: 뉴스 트렌드 → Claude AI → 앱 아이디어 생성
"""

import json
import os
import re
import random
from datetime import datetime
from urllib.request import urlopen, Request
from xml.etree import ElementTree as ET
from collections import Counter
from http.server import BaseHTTPRequestHandler

# ===== RSS 소스 =====
RSS_FEEDS = [
    ('Google 뉴스 한국', 'https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko'),
    ('Google 뉴스 경제', 'https://news.google.com/rss/topics/CAAqIQgKIhtDQkFTRGdvSUwyMHZNRGx6TVdZU0FtdHZLQUFQAQ?hl=ko&gl=KR&ceid=KR:ko'),
    ('Google 뉴스 기술', 'https://news.google.com/rss/topics/CAAqIQgKIhtDQkFTRGdvSUwyMHZNRGRqTVhZU0FtdHZLQUFQAQ?hl=ko&gl=KR&ceid=KR:ko'),
]

SENSITIVE_KEYWORDS = {'살인', '자살', '성범죄', '성폭력', '마약', '도박', '테러', '전쟁', '학대', '혐오', '차별'}

KEYWORD_TO_CATEGORY = {
    '대출': '재정금융', '금리': '재정금융', '은행': '재정금융', '환율': '재정금융',
    '주식': '재정금융', '코인': '재정금융', '투자': '재정금융', '보험': '재정금융',
    '금융': '재정금융', '경제': '재정금융', '물가': '재정금융', '전세': '재정금융',
    '신용': '재정금융', '카드': '재정금융',
    '병원': '보건의료', '의료': '보건의료', '건강': '보건의료', '약국': '보건의료',
    '감염': '보건의료', '진료': '보건의료', '응급': '보건의료', '질병': '보건의료',
    '식품': '식품건강', '음식': '식품건강', '영양': '식품건강', '식당': '식품건강',
    '맛집': '식품건강', '레시피': '식품건강', '배달': '식품건강',
    '교통': '교통물류', '버스': '교통물류', '지하철': '교통물류', '도로': '교통물류',
    '주차': '교통물류', '택시': '교통물류', '항공': '교통물류', '운전': '교통물류',
    '교육': '교육', '학교': '교육', '대학': '교육', '입시': '교육',
    '취업': '교육', '자격증': '교육',
    '관광': '문화관광', '여행': '문화관광', '축제': '문화관광', '공연': '문화관광',
    '영화': '문화관광', '문화': '문화관광', '캠핑': '문화관광',
    '날씨': '환경기상', '미세먼지': '환경기상', '폭염': '환경기상', '태풍': '환경기상',
    '환경': '환경기상', '기후': '환경기상',
    '부동산': '국토관리', '아파트': '국토관리', '토지': '국토관리',
    '주택': '국토관리', '분양': '국토관리',
    '재난': '재난안전', '안전': '재난안전', '화재': '재난안전', '사고': '재난안전',
    '일자리': '산업고용', '채용': '산업고용', '고용': '산업고용', '창업': '산업고용',
    '기업': '산업고용', '스타트업': '산업고용',
    '복지': '사회복지', '지원금': '사회복지', '연금': '사회복지',
    '육아': '사회복지', '출산': '사회복지', '돌봄': '사회복지',
    '농산물': '농축수산', '축산': '농축수산', '수산': '농축수산',
    '정부': '공공행정', '민원': '공공행정', '선거': '공공행정', '정책': '공공행정',
    '법률': '법률', '법원': '법률', '세금': '법률', '규제': '법률',
}

API_CATEGORIES = {
    '재정금융': {'apis': 610, 'examples': '환율정보, 사업자등록확인, 기업경영분석, 금감원 공시'},
    '보건의료': {'apis': 542, 'examples': '병원정보, 약국정보, 건강정보포털, 예방접종현황'},
    '식품건강': {'apis': 708, 'examples': '레시피DB, 바코드제품정보, 건강기능식품, 식품영양정보'},
    '교통물류': {'apis': 1272, 'examples': '지하철실시간, 버스노선정보, CCTV, 자동차정보'},
    '교육': {'apis': 406, 'examples': '학교기본정보, 대학학과정보, 도서관인기대출'},
    '문화관광': {'apis': 1301, 'examples': '관광정보, 영화정보DB, 등산로, 골프장현황'},
    '환경기상': {'apis': 816, 'examples': '대기오염정보, 미세먼지경보, 측정소정보'},
    '국토관리': {'apis': 540, 'examples': '연속지적도, 지오코더, 토지이용계획도'},
    '재난안전': {'apis': 611, 'examples': '교통CCTV, 침수흔적도, 범죄주의구간, 편의점'},
    '산업고용': {'apis': 941, 'examples': '채용정보, 상가정보, 안심식당, 가맹정보'},
    '사회복지': {'apis': 859, 'examples': '어린이집정보, 국민연금, 노인복지시설'},
    '농축수산': {'apis': 1257, 'examples': '농산물가격, 동물등록현황, 축산물등급'},
    '공공행정': {'apis': 1668, 'examples': '행정구역, 공공기관정보, 법령정보'},
    '과학기술': {'apis': 288, 'examples': '특허정보, 위성정보, 기상관측'},
}


def fetch_news():
    """RSS 피드에서 뉴스 제목 수집"""
    all_news = []
    for name, url in RSS_FEEDS:
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=8) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.iter('item'):
                title = item.findtext('title', '')
                if title and not any(sw in title for sw in SENSITIVE_KEYWORDS):
                    all_news.append(title)
        except:
            pass
    return all_news


def extract_keywords(news_items):
    """키워드 추출 + 카테고리 매핑"""
    keyword_counts = Counter()
    category_counts = Counter()
    keyword_news = {}

    for title in news_items:
        for keyword, category in KEYWORD_TO_CATEGORY.items():
            if keyword in title:
                keyword_counts[keyword] += 1
                category_counts[category] += 1
                if keyword not in keyword_news:
                    keyword_news[keyword] = []
                if len(keyword_news[keyword]) < 3:
                    keyword_news[keyword].append(title[:80])

    return keyword_counts, category_counts, keyword_news


def generate_ideas_with_claude(news_titles, keyword_counts, category_counts):
    """Claude AI로 뉴스 기반 앱 아이디어 생성"""
    try:
        import anthropic
    except ImportError:
        return None

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None

    top_news = news_titles[:60]
    top_keywords = [f"{k}({c}건)" for k, c in keyword_counts.most_common(15)]
    top_cats = [f"{c}({n}건)" for c, n in category_counts.most_common(8)]

    cat_info = "\n".join([
        f"- {cat}: API {info['apis']}개 (예: {info['examples']})"
        for cat, info in API_CATEGORIES.items()
    ])

    prompt = f"""뉴스 헤드라인에서 "요즘 트렌드"를 읽고, 공공데이터 API를 활용한 모바일 앱 아이디어를 생성해주세요.

## 중요 배경
- 공공데이터 API는 활용신청 후 승인까지 1~3일 소요됨
- 따라서 "오늘 당장 필요한 속보성 앱"이 아니라, **몇 주~몇 달간 유효한 트렌드 기반 앱**이어야 함
- 예: "환율 급등" 뉴스 → ❌ "오늘 환율 속보" / ✅ "환율 변동기 해외송금 절약 가이드"
- 예: "AI 열풍" 뉴스 → ❌ "AI 뉴스 모음" / ✅ "AI 자격증 취업 매칭"

## 최근 뉴스 헤드라인 (트렌드 파악용)
{chr(10).join(f'- {t}' for t in top_news)}

## 트렌드 키워드 (빈도순)
{', '.join(top_keywords)}

## 트렌드 카테고리 (빈도순)
{', '.join(top_cats)}

## 사용 가능한 공공데이터 API 카테고리
{cat_info}

## 요청사항
위 뉴스에서 읽히는 **중장기 트렌드**를 반영한 앱 아이디어를 JSON 배열로 20개 생성해주세요.

규칙:
1. 속보/단기 이슈가 아니라 **몇 주~몇 달간 유효한 트렌드** 기반이어야 함
2. 공공데이터 API 2~3개를 조합해서 만들 수 있는 앱이어야 함
3. 토스 미니앱(간단한 유틸리티/정보 앱)에 적합해야 함
4. 이모지 1개 + 짧은 앱 이름 (10자 이내)
5. related_news에는 이 트렌드를 보여주는 뉴스 제목 1~2개를 원문 그대로 포함
6. description에 어떤 공공데이터 API를 어떻게 조합하는지 구체적으로 설명

JSON 형식 (반드시 이 형식만):
```json
[
  {{
    "name": "🏠 전세안심 체크",
    "description": "등기부등본 API + 실거래가 API + 전세가율로 전세사기 위험도 자동 분석",
    "categories": ["재정금융", "국토관리"],
    "feasibility": "high",
    "sustainability": "high",
    "related_news": ["실제 뉴스 제목1", "실제 뉴스 제목2"],
    "trend_score": 8
  }}
]
```

feasibility: high(바로 개발 가능) / medium(보통) / low(난이도 높음)
sustainability: high(지속형=계속 쓸 앱) / medium(시즌형=몇 달) / low(단기=몇 주)
trend_score: 1~10 (트렌드 반영도, 높을수록 뉴스와 연관 강함)

JSON 배열만 출력하세요. 다른 텍스트 없이."""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=4000,
        messages=[{'role': 'user', 'content': prompt}]
    )

    text = response.content[0].text.strip()
    # JSON 블록 추출
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0].strip()
    elif '```' in text:
        text = text.split('```')[1].split('```')[0].strip()

    # JSON 파싱 (실패 시 repair 시도)
    try:
        ideas = json.loads(text)
    except json.JSONDecodeError:
        # 흔한 문제: 뉴스 제목에 이스케이프 안 된 따옴표
        # 마지막 유효한 ] 위치까지만 파싱
        last_bracket = text.rfind(']')
        if last_bracket > 0:
            try:
                ideas = json.loads(text[:last_bracket + 1])
            except json.JSONDecodeError:
                # 각 객체를 개별 파싱
                ideas = []
                for match in re.finditer(r'\{[^{}]+\}', text):
                    try:
                        obj = json.loads(match.group())
                        if 'name' in obj:
                            ideas.append(obj)
                    except:
                        pass
        else:
            ideas = []

    # 타입 분류: trend_score 6+ = trend, 3-5 = smart, 1-2 = random
    for idea in ideas:
        score = idea.get('trend_score', 5)
        if score >= 6:
            idea['type'] = 'trend'
        elif score >= 3:
            idea['type'] = 'smart'
        else:
            idea['type'] = 'random'
        idea['competitors'] = 0
        if not idea.get('apis'):
            idea['apis'] = []

    return ideas


def load_apis():
    """apis.json 로드"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    apis_path = os.path.join(script_dir, '..', 'apis.json')
    if not os.path.exists(apis_path):
        apis_path = os.path.join(script_dir, 'apis.json')
    if os.path.exists(apis_path):
        with open(apis_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def match_real_apis(ideas, all_apis):
    """아이디어별로 실제 공공데이터 API를 매칭 (카테고리 엄격 적용)"""
    # 불용어 (너무 흔해서 매칭에 쓸모없는 단어)
    STOP_WORDS = {
        'API', '조합', '조회', '정보', '서비스', '데이터', '활용', '기반', '통합',
        '실시간', '맞춤', '추천', '확인', '분석', '비교', '계산', '현황', '목록',
        '시스템', '관리', '제공', '이용', '결합', '자동', '최적', '타이밍', '방법',
        '가이드', '알림', '추적', '변동', '위험', '안전', '지수', '트렌드', '상품',
    }

    for idea in ideas:
        categories = idea.get('categories', [])
        idea_text = f"{idea.get('name','')} {idea.get('description','')}"

        # 핵심 키워드만 추출 (3글자 이상 우선)
        idea_keywords = set()
        for word in re.split(r'[\s+/·,→()\[\]]+', idea_text):
            word = re.sub(r'[^\w가-힣]', '', word)
            if len(word) >= 2 and word not in STOP_WORDS:
                idea_keywords.add(word)

        matched = []
        seen_ids = set()

        # 카테고리별로 순차 매칭
        for cat in categories:
            cat_apis = [a for a in all_apis if a.get('category_main') == cat]

            scored = []
            for api in cat_apis:
                api_text = f"{api['name']} {api.get('keywords', '')}"
                # 키워드 매칭 (API 이름+키워드에서만, description 제외로 정확도 향상)
                kw_hits = [kw for kw in idea_keywords if kw in api_text]
                kw_score = len(kw_hits)
                if kw_score > 0:
                    # 3글자 이상 키워드 매칭에 보너스
                    long_kw_bonus = sum(1 for kw in kw_hits if len(kw) >= 3) * 2
                    rest_bonus = 5 if api.get('api_type') == 'REST' else 0
                    dl_bonus = min(api.get('downloads', 0) / 10000, 3)
                    total = kw_score * 10 + long_kw_bonus + rest_bonus + dl_bonus
                    scored.append((api, total, kw_score))

            scored.sort(key=lambda x: (-x[1],))

            for api, total, kw in scored[:2]:
                if api['id'] not in seen_ids:
                    matched.append({
                        'id': api['id'],
                        'name': api['name'],
                        'type': api.get('api_type', '?'),
                        'downloads': api.get('downloads', 0),
                        'provider': api.get('provider', ''),
                    })
                    seen_ids.add(api['id'])

        # 카테고리 인기 API로 보충 (최소 2개 보장)
        if len(matched) < 2:
            for cat in categories:
                popular = sorted(
                    [a for a in all_apis if a.get('category_main') == cat and a['id'] not in seen_ids],
                    key=lambda a: -a.get('downloads', 0)
                )
                for api in popular[:2]:
                    matched.append({
                        'id': api['id'],
                        'name': api['name'],
                        'type': api.get('api_type', '?'),
                        'downloads': api.get('downloads', 0),
                        'provider': api.get('provider', ''),
                    })
                    seen_ids.add(api['id'])
                    if len(matched) >= 3:
                        break
                if len(matched) >= 3:
                    break

        idea['apis'] = matched[:4]

    return ideas


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # 1. 뉴스 수집
            news = fetch_news()
            if not news:
                self._send_json({'success': False, 'message': '뉴스 수집 실패'}, 500)
                return

            # 2. 키워드 분석
            keyword_counts, category_counts, keyword_news = extract_keywords(news)

            # 3. Claude AI로 아이디어 생성
            ai_ideas = generate_ideas_with_claude(news, keyword_counts, category_counts)

            if ai_ideas is None:
                self._send_json({'success': False, 'message': 'Claude API 키가 설정되지 않았습니다.'}, 500)
                return

            # 4. 실제 공공데이터 API 매칭
            all_apis = load_apis()
            if all_apis:
                ai_ideas = match_real_apis(ai_ideas, all_apis)

            # 5. 결과 분류
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

            # trends.json 저장 (로컬 환경용)
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                trends_path = os.path.join(script_dir, '..', 'trends.json')
                with open(trends_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=1)
            except:
                pass

            self._send_json({
                'success': True,
                'message': f"AI 분석 완료: {len(ai_ideas)}개 아이디어 (뉴스 {len(news)}건)",
                'trends': result,
            })

        except Exception as e:
            self._send_json({'success': False, 'message': f'오류: {str(e)}'}, 500)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
