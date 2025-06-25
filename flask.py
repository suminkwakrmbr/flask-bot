# 파일명: app.py
from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Slack Bot Token (OAuth 설치 후 발급받은 xoxb-... 토큰)
SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
SLACK_API_URL = 'https://slack.com/api/chat.postMessage'

# GPTOnline API 연동 부분 (임시 요약 함수 사용 중)
def get_summary_from_gptonline(text):
    # 실제 GPTOnline API 연동 대신 임시 요약 처리
    return f"📝 요약 결과: '{text}' 에 대한 핵심 내용 정리 완료!"

# Slack Event 수신 엔드포인트
@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json

    # URL 인증용 challenge
    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})

    # 메시지 수신 처리
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

# 슬랙 채널에 메시지 보내기
def send_message_to_slack(channel, text):
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'channel': channel,
        'text': text
    }
    response = requests.post(SLACK_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ 슬랙 전송 실패: {response.text}")

# 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)