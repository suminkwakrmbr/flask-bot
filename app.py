from flask import Flask, request
import requests
import os

app = Flask(__name__)

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
SLACK_API_URL = 'https://slack.com/api/chat.postMessage'

def get_summary_from_gptonline(text):
    return f"📝 요약 결과: '{text}' 에 대한 핵심 내용 정리 완료!"

@app.route('/')
def home():
    return "Slack Bot Server is running! 🤖"

@app.route('/slack/events', methods=['GET', 'POST'])
def slack_events():
    if request.method == 'GET':
        return "Slack Events endpoint is working!"
    
    try:
        data = request.get_json(force=True)
        print(f"데이터: {data}")
        
        # Challenge 처리
        if data and 'challenge' in data:
            return str(data['challenge'])
        
        # 이벤트 처리
        if data and 'event' in data:
            event = data['event']
            event_type = event.get('type')
            print(f"이벤트 타입: {event_type}")
            
            # message 타입과 app_mention 타입 모두 처리
            if event_type in ['message', 'app_mention']:
                user_message = event.get('text', '')
                channel_id = event.get('channel')
                user_id = event.get('user')
                
                print(f"메시지: {user_message}")
                print(f"채널: {channel_id}")
                print(f"사용자: {user_id}")
                
                # 봇 자신의 메시지는 무시 (무한 루프 방지)
                if event.get('bot_id'):
                    print("봇 메시지 무시")
                    return 'ok'
                
                # 봇이 멘션된 경우만 처리
                if '<@U092S5G2P7V>' in user_message:  # 실제 봇 ID
                    print("봇 멘션 감지!")
                    
                    if '요약해줘' in user_message:
                        print("요약 요청 처리 중...")
                        summary = get_summary_from_gptonline(user_message)
                        result = send_message_to_slack(channel_id, summary)
                        print(f"메시지 전송 결과: {result}")
                    else:
                        send_message_to_slack(channel_id, "안녕하세요! '요약해줘'라고 말씀해주세요 😊")
        
        return 'ok'
        
    except Exception as e:
        print(f"에러 발생: {e}")
        return 'error'

def send_message_to_slack(channel, text):
    if not SLACK_TOKEN:
        print("❌ SLACK_TOKEN이 설정되지 않았습니다!")
        return False
        
    print(f"메시지 전송 시도: 채널={channel}, 텍스트={text}")
    
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
        print(f"API 응답 상태: {response.status_code}")
        print(f"API 응답 내용: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print("✅ 메시지 전송 성공!")
                return True
            else:
                print(f"❌ 메시지 전송 실패: {result.get('error')}")
        else:
            print(f"❌ HTTP 에러: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 요청 에러: {e}")
    
    return False

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)