from flask import Flask, request
import requests
import os
import json
from datetime import datetime, timedelta
import time

app = Flask(__name__)

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
SLACK_API_URL = 'https://slack.com/api/chat.postMessage'

# 사용량 추적을 위한 전역 변수
usage_data = {
    'count': 0,
    'reset_date': None,
    'daily_count': 0,
    'last_request_date': None
}

# 중복 요청 방지를 위한 캐시
processed_events = {}
CACHE_EXPIRE_TIME = 300  # 5분

# 사용량 데이터 파일 경로
USAGE_FILE = 'gemini_usage.json'

def clean_expired_cache():
    """만료된 캐시 정리"""
    current_time = time.time()
    expired_keys = [key for key, timestamp in processed_events.items() 
                   if current_time - timestamp > CACHE_EXPIRE_TIME]
    for key in expired_keys:
        del processed_events[key]

def is_duplicate_event(event):
    """중복 이벤트 확인"""
    clean_expired_cache()
    
    # 이벤트 고유 키 생성 (사용자 + 채널 + 메시지 내용 + 시간)
    event_key = f"{event.get('user', '')}_{event.get('channel', '')}_{event.get('text', '')}_{event.get('ts', '')}"
    
    current_time = time.time()
    
    if event_key in processed_events:
        print(f"중복 이벤트 감지: {event_key}")
        return True
    
    # 새 이벤트로 캐시에 저장
    processed_events[event_key] = current_time
    return False

# 사용량 데이터 로드
def load_usage_data():
    global usage_data
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                usage_data.update(loaded_data)
                print(f"사용량 데이터 로드: {usage_data}")
    except Exception as e:
        print(f"사용량 데이터 로드 실패: {e}")

def save_usage_data():
    try:
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(usage_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"사용량 데이터 저장 실패: {e}")

def check_monthly_reset():
    global usage_data
    now = datetime.now()
    
    if not usage_data['reset_date']:
        usage_data['reset_date'] = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        usage_data['count'] = 0
        save_usage_data()
        return
    
    reset_date = datetime.fromisoformat(usage_data['reset_date'])
    
    if now.month != reset_date.month or now.year != reset_date.year:
        print(f"월 리셋! 이전 사용량: {usage_data['count']}")
        usage_data['count'] = 0
        usage_data['reset_date'] = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        save_usage_data()

def check_daily_reset():
    global usage_data
    today = datetime.now().date().isoformat()
    
    if usage_data['last_request_date'] != today:
        usage_data['daily_count'] = 0
        usage_data['last_request_date'] = today
        save_usage_data()

def increment_usage():
    global usage_data
    check_monthly_reset()
    check_daily_reset()
    
    usage_data['count'] += 1
    usage_data['daily_count'] += 1
    save_usage_data()
    
    print(f"현재 사용량 - 월: {usage_data['count']}/1500, 일: {usage_data['daily_count']}/50")

def can_use_gemini():
    check_monthly_reset()
    check_daily_reset()
    
    monthly_limit = usage_data['count'] < 1500
    daily_limit = usage_data['daily_count'] < 50
    
    return monthly_limit and daily_limit

def get_usage_info():
    check_monthly_reset()
    check_daily_reset()
    
    return {
        'monthly_used': usage_data['count'],
        'monthly_limit': 1500,
        'monthly_remaining': 1500 - usage_data['count'],
        'daily_used': usage_data['daily_count'],
        'daily_limit': 50,
        'daily_remaining': 50 - usage_data['daily_count'],
        'reset_date': usage_data['reset_date']
    }

def get_gemini_summary_direct(text):
    try:
        if not can_use_gemini():
            usage_info = get_usage_info()
            return f"""📝 **API 사용량 초과**

🚫 **월간 한도**: {usage_info['monthly_used']}/{usage_info['monthly_limit']}
🚫 **일간 한도**: {usage_info['daily_used']}/{usage_info['daily_limit']}

⏰ **다음 리셋**: 매월 1일 자정"""

        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            return "📝 Google API 키가 설정되지 않았습니다."
        
        clean_text = text.replace('<@U092S5G2P7V>', '').replace('요약해줘', '').strip()
        
        if len(clean_text) < 10:
            return "📝 요약할 내용을 함께 알려주세요!"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"다음 내용을 한국어로 3-5줄로 간단히 요약해주세요:\n\n{clean_text}"
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.8,
                "maxOutputTokens": 200,
            }
        }
        
        print(f"Gemini API 호출 시작...")
        
        increment_usage()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                summary = result['candidates'][0]['content']['parts'][0]['text']
                usage_info = get_usage_info()
                return f"""📝 **AI 요약 결과**

{summary.strip()}

📊 **사용량**: 월 {usage_info['monthly_used']}/1500, 오늘 {usage_info['daily_used']}/50"""
            else:
                return "📝 AI 응답을 생성할 수 없습니다."
        else:
            print(f"API 오류: {response.status_code} - {response.text}")
            return f"📝 API 오류 (상태: {response.status_code})"
            
    except Exception as e:
        print(f"Gemini API 오류: {e}")
        return f"📝 요약 중 오류: {str(e)}"

@app.route('/')
def home():
    usage_info = get_usage_info()
    return f"""
    <h1>🤖 Slack Bot Server</h1>
    <h2>📊 API 사용량</h2>
    <ul>
        <li>월간 사용량: {usage_info['monthly_used']}/{usage_info['monthly_limit']}</li>
        <li>일간 사용량: {usage_info['daily_used']}/{usage_info['daily_limit']}</li>
        <li>월간 남은 횟수: {usage_info['monthly_remaining']}</li>
        <li>일간 남은 횟수: {usage_info['daily_remaining']}</li>
    </ul>
    """

@app.route('/usage')
def usage_status():
    return get_usage_info()

@app.route('/slack/events', methods=['GET', 'POST'])
def slack_events():
    if request.method == 'GET':
        return "Slack Events endpoint is working!"
    
    try:
        data = request.get_json(force=True)
        
        # Challenge 처리
        if data and 'challenge' in data:
            return str(data['challenge'])
        
        # 이벤트 처리
        if data and 'event' in data:
            event = data['event']
            event_type = event.get('type')
            
            print(f"이벤트 타입: {event_type}")
            print(f"이벤트 상세: {event}")
            
            # 중복 이벤트 확인
            if is_duplicate_event(event):
                print("중복 이벤트로 인한 무시")
                return 'ok'
            
            # message 타입만 처리 (app_mention 무시하여 중복 방지)
            if event_type == 'message':
                user_message = event.get('text', '')
                channel_id = event.get('channel')
                user_id = event.get('user')
                
                # 봇 자신의 메시지 무시
                if event.get('bot_id') or event.get('subtype') == 'bot_message':
                    print("봇 메시지 무시")
                    return 'ok'
                
                # 멘션된 메시지만 처리
                if '<@U092S5G2P7V>' in user_message:
                    print(f"봇 멘션 감지: {user_message}")
                    
                    if '요약해줘' in user_message:
                        print("요약 요청 처리 시작")
                        summary = get_gemini_summary_direct(user_message)
                        send_message_to_slack(channel_id, summary)
                    elif '사용량' in user_message or '한도' in user_message:
                        usage_info = get_usage_info()
                        usage_msg = f"""📊 **API 사용량 현황**

🗓️ **월간**: {usage_info['monthly_used']}/{usage_info['monthly_limit']} (남은 횟수: {usage_info['monthly_remaining']})
📅 **오늘**: {usage_info['daily_used']}/{usage_info['daily_limit']} (남은 횟수: {usage_info['daily_remaining']})

🔄 **리셋**: 매월 1일 자정"""
                        send_message_to_slack(channel_id, usage_msg)
                    else:
                        help_msg = """안녕하세요! 🤖

**사용 가능한 명령어:**
• `@봇이름 요약해줘 [내용]` - AI 텍스트 요약
• `@봇이름 사용량` - API 사용량 확인

💡 **제한**: 월 1,500회, 일 50회"""
                        send_message_to_slack(channel_id, help_msg)
                else:
                    print("봇 멘션 없음 - 무시")
            else:
                print(f"처리하지 않는 이벤트 타입: {event_type}")
        
        return 'ok'
        
    except Exception as e:
        print(f"에러 발생: {e}")
        return 'error'

def send_message_to_slack(channel, text):
    if not SLACK_TOKEN:
        print("❌ SLACK_TOKEN이 설정되지 않았습니다!")
        return False
        
    headers = {
        'Authorization': f'Bearer {SLACK_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'channel': channel,
        'text': text
    }
    
    try:
        response = requests.post(SLACK_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            result = response.json()
            success = result.get('ok', False)
            if success:
                print("✅ 메시지 전송 성공")
            else:
                print(f"❌ 메시지 전송 실패: {result.get('error')}")
            return success
        else:
            print(f"❌ HTTP 에러: {response.status_code}")
    except Exception as e:
        print(f"❌ 메시지 전송 에러: {e}")
    
    return False

if __name__ == '__main__':
    load_usage_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)