from flask import Flask, request
import requests
import os

app = Flask(__name__)

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
SLACK_API_URL = 'https://slack.com/api/chat.postMessage'

def get_gemini_summary(text):
    try:
        # 여기서 import (런타임에 확인)
        import google.generativeai as genai
        
        # API 키 설정
        genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
        
        # 모델 선택
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 텍스트 정리
        clean_text = text.replace('<@U092S5G2P7V>', '').replace('요약해줘', '').strip()
        
        if len(clean_text) < 10:
            return "📝 요약할 내용을 함께 알려주세요!"
        
        # 프롬프트
        prompt = f"""다음 내용을 한국어로 간단히 요약해주세요:

{clean_text}

요약 형식:
- 3-5줄로 핵심 내용 정리
- 주요 키워드 포함
- 이해하기 쉽게 작성"""
        
        # API 요청
        response = model.generate_content(prompt)
        
        if response.text:
            return f"📝 **AI 요약 결과**\n\n{response.text}"
        else:
            return "📝 요약 생성에 실패했습니다."
            
    except ImportError:
        return "📝 Gemini 패키지가 설치되지 않았습니다."
    except Exception as e:
        print(f"Gemini API 오류: {e}")
        return f"📝 요약 중 오류가 발생했습니다: {str(e)}"

@app.route('/')
def home():
    return "Slack Bot Server is running! 🤖"

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
            
            if event_type in ['message', 'app_mention']:
                user_message = event.get('text', '')
                channel_id = event.get('channel')
                
                # 봇 자신의 메시지 무시
                if event.get('bot_id'):
                    return 'ok'
                
                # 봇 멘션 확인
                if '<@U092S5G2P7V>' in user_message:
                    if '요약해줘' in user_message:
                        summary = get_gemini_summary(user_message)
                        send_message_to_slack(channel_id, summary)
                    else:
                        send_message_to_slack(channel_id, "안녕하세요! '요약해줘 [내용]'이라고 말씀해주세요 😊")
        
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
            return result.get('ok', False)
    except Exception as e:
        print(f"❌ 메시지 전송 에러: {e}")
    
    return False

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)