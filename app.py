from flask import Flask, request
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Slack Bot Server is running! 🤖"

# 모든 HTTP 메서드 허용
@app.route('/slack/events', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def slack_events():
    try:
        print(f"=== 요청 정보 ===")
        print(f"메서드: {request.method}")
        print(f"URL: {request.url}")
        print(f"헤더: {dict(request.headers)}")
        
        if request.method == 'GET':
            return "GET 요청 성공!"
        
        # POST 데이터 처리
        data = None
        try:
            data = request.get_json(force=True)
        except:
            try:
                raw = request.get_data(as_text=True)
                import json
                data = json.loads(raw)
            except:
                data = {}
        
        print(f"데이터: {data}")
        
        # Challenge 응답
        if isinstance(data, dict) and 'challenge' in data:
            return str(data['challenge'])
        
        return 'ok'
        
    except Exception as e:
        print(f"에러: {e}")
        return 'error'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)