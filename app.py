from flask import Flask, request, jsonify
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

@app.route('/health')
def health():
    return {"status": "healthy", "message": "Server is running"}

@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    
    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})
    
    if 'event' in data:
        event = data['event']
        event_type = event.get('type')
        
        if event_type == 'app_mention':
            user_message = event.get('text', '')
            channel_id = event.get('channel')
            
            if '요약해줘' in user_message:
                summary = get_summary_from_gptonline(user_message)
                send_message_to_slack(channel_id, summary)
    
    return '', 200

def send_message_to_slack(channel, text):
    if not SLACK_TOKEN:
        print("❌ SLACK_TOKEN이 설정되지 않았습니다!")
        return
        
    headers = {
        'Authorization': f'Bearer {SLACK_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'channel': channel,
        'text': text
    }
    
    response = requests.post(SLACK_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ 슬랙 전송 실패: {response.text}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # ✅ Render PORT 사용
    app.run(host='0.0.0.0', port=port, debug=False)
