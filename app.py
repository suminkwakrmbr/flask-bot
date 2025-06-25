from flask import Flask, request
import requests
import os
import time
from datetime import datetime, timedelta
import re

app = Flask(__name__)

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
SLACK_API_URL = 'https://slack.com/api/chat.postMessage'
SLACK_CONVERSATIONS_HISTORY_URL = 'https://slack.com/api/conversations.history'
SLACK_CONVERSATIONS_REPLIES_URL = 'https://slack.com/api/conversations.replies'
SLACK_USERS_INFO_URL = 'https://slack.com/api/users.info'

# 중복 요청 방지 캐시
processed_messages = {}
user_cache = {}  # 사용자 정보 캐시
    

def is_duplicate_message(user_id, channel_id, message_text, timestamp):
    """중복 메시지 확인"""
    message_key = f"{user_id}_{channel_id}_{hash(message_text)}_{timestamp}"
    current_time = time.time()
    
    # 5분 이상 된 캐시 정리
    expired_keys = [key for key, cached_time in processed_messages.items() 
                   if current_time - cached_time > 300]
    for key in expired_keys:
        del processed_messages[key]
    
    if message_key in processed_messages:
        print(f"중복 메시지 감지: {message_key}")
        return True
    
    processed_messages[message_key] = current_time
    return False

def get_user_name(user_id):
    """사용자 ID로 이름 가져오기 (캐시 사용)"""
    if user_id in user_cache:
        return user_cache[user_id]
    
    try:
        headers = {
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        params = {'user': user_id}
        response = requests.get(SLACK_USERS_INFO_URL, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                user = data.get('user', {})
                name = user.get('real_name') or user.get('display_name') or user.get('name', 'Unknown')
                user_cache[user_id] = name
                return name
        
        user_cache[user_id] = 'Unknown'
        return 'Unknown'
        
    except Exception as e:
        print(f"사용자 정보 가져오기 오류: {e}")
        user_cache[user_id] = 'Unknown'
        return 'Unknown'

def get_channel_messages_with_pagination(channel_id, days_back=30):
    """페이지네이션을 사용해서 더 많은 메시지 가져오기"""
    try:
        since_time = datetime.now() - timedelta(days=days_back)
        oldest_timestamp = since_time.timestamp()
        
        headers = {
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        all_messages = []
        cursor = None
        page_count = 0
        max_pages = 50  # 최대 50페이지 (약 10,000개 메시지)
        
        print(f"📊 {days_back}일간 메시지 수집 시작...")
        
        while page_count < max_pages:
            params = {
                'channel': channel_id,
                'oldest': oldest_timestamp,
                'limit': 200  # 페이지당 200개
            }
            
            if cursor:
                params['cursor'] = cursor
            
            response = requests.get(SLACK_CONVERSATIONS_HISTORY_URL, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    messages = data.get('messages', [])
                    if not messages:
                        break
                    
                    all_messages.extend(messages)
                    page_count += 1
                    
                    print(f"📄 페이지 {page_count}: {len(messages)}개 메시지 수집 (총 {len(all_messages)}개)")
                    
                    # 다음 페이지 확인
                    if data.get('has_more') and data.get('response_metadata', {}).get('next_cursor'):
                        cursor = data['response_metadata']['next_cursor']
                        time.sleep(0.5)  # API 호출 간격 조절
                    else:
                        break
                else:
                    print(f"API 오류: {data.get('error')}")
                    break
            else:
                print(f"HTTP 오류: {response.status_code}")
                break
        
        print(f"✅ 총 {len(all_messages)}개 메시지 수집 완료")
        return all_messages
        
    except Exception as e:
        print(f"메시지 수집 오류: {e}")
        return []

def get_channel_messages(channel_id, hours_back=24):
    """단기간 메시지 가져오기 (기존 함수)"""
    try:
        since_time = datetime.now() - timedelta(hours=hours_back)
        oldest_timestamp = since_time.timestamp()
        
        headers = {
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        params = {
            'channel': channel_id,
            'oldest': oldest_timestamp,
            'limit': 200
        }
        
        response = requests.get(SLACK_CONVERSATIONS_HISTORY_URL, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                return data.get('messages', [])
            else:
                print(f"채널 메시지 API 오류: {data.get('error')}")
                return []
        else:
            print(f"채널 메시지 HTTP 오류: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"채널 메시지 가져오기 오류: {e}")
        return []

def get_thread_messages(channel_id, thread_ts):
    """스레드의 모든 메시지들을 가져오기"""
    try:
        headers = {
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        params = {
            'channel': channel_id,
            'ts': thread_ts,
            'limit': 100
        }
        
        response = requests.get(SLACK_CONVERSATIONS_REPLIES_URL, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                return data.get('messages', [])
            else:
                print(f"스레드 API 오류: {data.get('error')}")
                return []
        else:
            print(f"스레드 HTTP 오류: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"스레드 메시지 가져오기 오류: {e}")
        return []

def analyze_messages_by_period(messages, days_back):
    """메시지를 기간별로 분석"""
    now = datetime.now()
    
    # 시간대별 분류
    periods = {
        'recent': [],    # 최근 7일
        'weekly': [],    # 1주-2주 전
        'monthly': []    # 2주-30일 전
    }
    
    user_activity = {}
    daily_counts = {}
    
    for message in messages:
        if message.get('bot_id') or message.get('subtype') in ['channel_join', 'channel_leave']:
            continue
            
        try:
            msg_time = datetime.fromtimestamp(float(message.get('ts', 0)))
            days_ago = (now - msg_time).days
            user_id = message.get('user')
            
            # 기간별 분류
            if days_ago <= 7:
                periods['recent'].append(message)
            elif days_ago <= 14:
                periods['weekly'].append(message)
            else:
                periods['monthly'].append(message)
            
            # 사용자 활동 추적
            if user_id:
                user_name = get_user_name(user_id)
                if user_name not in user_activity:
                    user_activity[user_name] = 0
                user_activity[user_name] += 1
            
            # 일별 카운트
            date_key = msg_time.strftime('%Y-%m-%d')
            if date_key not in daily_counts:
                daily_counts[date_key] = 0
            daily_counts[date_key] += 1
            
        except:
            continue
    
    return periods, user_activity, daily_counts

def format_messages_for_summary(messages, include_time=True):
    """메시지들을 요약하기 좋은 형태로 포맷팅"""
    formatted_messages = []
    
    for message in reversed(messages):  # 시간순으로 정렬
        # 봇 메시지나 시스템 메시지 제외
        if message.get('bot_id') or message.get('subtype') in ['channel_join', 'channel_leave']:
            continue
            
        user_id = message.get('user')
        text = message.get('text', '')
        timestamp = message.get('ts', '')
        
        if user_id and text:
            user_name = get_user_name(user_id)
            
            # 시간 포맷팅
            time_str = ''
            if include_time and timestamp:
                try:
                    msg_time = datetime.fromtimestamp(float(timestamp))
                    time_str = f"[{msg_time.strftime('%m/%d %H:%M')}] "
                except:
                    time_str = ''
            
            # 멘션 정리 및 텍스트 길이 제한
            clean_text = re.sub(r'<@[A-Z0-9]+>', '@사용자', text)
            if len(clean_text) > 100:
                clean_text = clean_text[:100] + "..."
            
            formatted_msg = f"{time_str}{user_name}: {clean_text}"
            formatted_messages.append(formatted_msg)
    
    return '\n'.join(formatted_messages)

def get_long_term_channel_summary(channel_id, days_back=30):
    """장기간 채널 대화를 요약 (30일 등)"""
    try:
        print(f"🔍 {days_back}일간 채널 분석 시작...")
        
        # 메시지 수집 (페이지네이션 사용)
        all_messages = get_channel_messages_with_pagination(channel_id, days_back)
        
        if not all_messages:
            return f"📊 **{days_back}일간 채널 분석**\n\n해당 기간 동안 메시지가 없습니다."
        
        # 실제 대화 메시지만 필터링
        real_messages = [msg for msg in all_messages if not msg.get('bot_id') and not msg.get('subtype')]
        
        if len(real_messages) < 5:
            return f"📊 **{days_back}일간 채널 분석**\n\n해당 기간의 대화가 너무 적어서 분석하기 어렵습니다."
        
        # 메시지 분석
        periods, user_activity, daily_counts = analyze_messages_by_period(real_messages, days_back)
        
        # 상위 활성 사용자
        top_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 최근 중요 메시지들만 샘플링 (너무 길면 API 한계)
        sample_messages = real_messages[:50] + real_messages[-50:] if len(real_messages) > 100 else real_messages
        formatted_text = format_messages_for_summary(sample_messages[:100])  # 최대 100개만
        
        # Gemini로 요약
        import google.generativeai as genai
        
        genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""다음은 Slack 채널에서 최근 {days_back}일 동안의 대화 샘플입니다. 장기적 관점에서 주요 내용을 한국어로 요약해주세요:

{formatted_text}

분석 정보:
- 총 메시지 수: {len(real_messages)}개
- 활성 사용자: {len(user_activity)}명
- 분석 기간: {days_back}일

요약 형식:
- 🗓️ 기간별 주요 활동 및 트렌드
- 🏆 주요 참여자들의 기여도
- 📋 핵심 논의 주제나 결정사항
- 🔍 반복적으로 언급된 이슈들
- 📈 활동 패턴이나 변화 추세
- 💡 향후 주목할 점이나 액션 아이템
- 8-12줄로 포괄적으로 정리"""
        
        response = model.generate_content(prompt)
        
        if response.text:
            # 통계 정보 추가
            stats_info = f"""📊 **상세 통계:**
👥 **활성 사용자 TOP 5:**
{chr(10).join([f"• {name}: {count}개 메시지" for name, count in top_users])}

📅 **기간별 메시지 분포:**
• 최근 7일: {len(periods['recent'])}개
• 1-2주 전: {len(periods['weekly'])}개  
• 2주-{days_back}일 전: {len(periods['monthly'])}개"""
            
            return f"""📊 **{days_back}일간 채널 종합 분석**

{response.text.strip()}

───────────────────
{stats_info}

🔍 **총 분석 데이터**: {len(real_messages)}개 메시지, {len(user_activity)}명 참여"""
        else:
            return f"📊 {days_back}일간 채널 분석 생성에 실패했습니다."
            
    except Exception as e:
        print(f"장기 채널 분석 오류: {e}")
        return f"📊 {days_back}일간 채널 분석 중 오류가 발생했습니다: {str(e)}"

def get_channel_summary(channel_id, hours_back=24):
    """단기간 채널 대화를 요약 (기존 함수)"""
    try:
        print(f"채널 {channel_id}의 최근 {hours_back}시간 메시지 수집 중...")
        
        messages = get_channel_messages(channel_id, hours_back)
        
        if not messages:
            return f"📅 **채널 대화 요약**\n\n최근 {hours_back}시간 동안 이 채널에 메시지가 없습니다."
        
        # 봇 메시지 제외하고 실제 대화만 필터링
        real_messages = [msg for msg in messages if not msg.get('bot_id') and not msg.get('subtype')]
        
        if len(real_messages) < 2:
            return f"📅 **채널 대화 요약**\n\n최근 {hours_back}시간 동안의 대화가 너무 적어서 요약하기 어렵습니다."
        
        formatted_text = format_messages_for_summary(real_messages)
        
        # Gemini로 요약
        import google.generativeai as genai
        
        genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""다음은 Slack 채널에서 최근 {hours_back}시간 동안의 대화 내용입니다. 주요 내용을 한국어로 요약해주세요:

{formatted_text}

요약 형식:
- 📋 주요 참여자와 핵심 대화 내용
- 🔍 중요한 결정사항이나 논의점  
- ✅ 액션 아이템이나 할 일
- ⏰ 시간대별 주요 흐름
- 💡 기타 특이사항
- 5-10줄로 구조화해서 정리

총 메시지 수: {len(real_messages)}개"""
        
        response = model.generate_content(prompt)
        
        if response.text:
            return f"""📅 **채널 대화 요약** (최근 {hours_back}시간)

{response.text.strip()}

───────────────────
📊 **수집 정보**: {len(real_messages)}개 메시지 분석 완료"""
        else:
            return "📅 채널 요약 생성에 실패했습니다."
            
    except Exception as e:
        print(f"채널 요약 오류: {e}")
        return f"📅 채널 요약 중 오류가 발생했습니다: {str(e)}"

def get_thread_summary(channel_id, thread_ts):
    """스레드 대화를 요약"""
    try:
        print(f"스레드 {thread_ts} 메시지 수집 중...")
        
        messages = get_thread_messages(channel_id, thread_ts)
        
        if not messages:
            return "🧵 **스레드 요약**\n\n스레드 메시지를 가져올 수 없습니다."
        
        if len(messages) < 2:
            return "🧵 **스레드 요약**\n\n스레드에 메시지가 너무 적어서 요약하기 어렵습니다."
        
        formatted_text = format_messages_for_summary(messages, include_time=False)
        
        # Gemini로 요약
        import google.generativeai as genai
        
        genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""다음은 Slack 스레드의 대화 내용입니다. 주요 내용을 한국어로 요약해주세요:

{formatted_text}

요약 형식:
- 🧵 스레드의 핵심 주제와 논의 내용
- 👥 주요 참여자별 의견이나 기여
- 🎯 결론이나 합의된 사항
- ❓ 미해결 질문이나 이슈
- 3-7줄로 간결하게 정리

총 메시지 수: {len(messages)}개"""
        
        response = model.generate_content(prompt)
        
        if response.text:
            return f"""🧵 **스레드 요약**

{response.text.strip()}

───────────────────
📊 **스레드 정보**: {len(messages)}개 메시지 분석 완료"""
        else:
            return "🧵 스레드 요약 생성에 실패했습니다."
            
    except Exception as e:
        print(f"스레드 요약 오류: {e}")
        return f"🧵 스레드 요약 중 오류가 발생했습니다: {str(e)}"

def get_gemini_summary(text):
    """기존 텍스트 요약 기능"""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        clean_text = text.replace('<@U092S5G2P7V>', '').strip()
        
        if '요약해줘' in clean_text:
            clean_text = clean_text.replace('요약해줘', '').strip()
        
        if len(clean_text) < 10:
            return """📝 **사용법 안내**

**기본 요약:**
• `@GPT Online [메시지 내용] 요약해줘`

**단기 채널 대화 요약:**
• `@GPT Online 오늘 채널 대화 요약해줘`
• `@GPT Online 최근 12시간 채널 메시지 요약해줘`

**장기 채널 분석:**
• `@GPT Online 최근 7일간 채널 분석해줘`
• `@GPT Online 최근 30일간 채널 분석해줘`
• `@GPT Online 한달간 채널 분석해줘`

**스레드 요약:**
• 스레드에서 `@GPT Online 이 스레드 요약해줘`"""
        
        # 메시지 형태 감지
        is_conversation = '[' in clean_text and ']' in clean_text
        is_long_message = len(clean_text) > 500
        has_multiple_lines = '\n' in clean_text or len(clean_text.split('.')) > 5
        
        if is_conversation:
            prompt = f"""다음은 대화 내용입니다. 주요 내용을 한국어로 요약해주세요:

{clean_text}

요약 형식:
- 💬 참여자별 주요 발언 정리
- 🔍 핵심 결정사항이나 논의점
- ✅ 액션 아이템이 있다면 포함
- 3-7줄로 간결하게 정리"""
        
        elif is_long_message or has_multiple_lines:
            prompt = f"""다음 내용의 핵심을 한국어로 요약해주세요:

{clean_text}

요약 형식:
- 📋 주요 포인트를 불릿포인트로 정리
- 🎯 중요한 날짜, 숫자, 결정사항 포함
- 📊 순서나 우선순위가 있다면 반영
- 5-8줄로 구조화해서 정리"""
        
        else:
            prompt = f"""다음 내용을 한국어로 간단히 요약해주세요:

{clean_text}

요약 형식:
- 📝 3-5줄로 핵심 내용 정리
- 🔑 주요 키워드와 핵심 메시지 포함
- 💡 명확하고 이해하기 쉽게 작성"""
        
        response = model.generate_content(prompt)
        
        if response.text:
            if is_conversation:
                summary_type = "💬 대화 요약"
            elif is_long_message:
                summary_type = "📄 긴 메시지 요약"
            elif has_multiple_lines:
                summary_type = "📋 구조화된 요약"
            else:
                summary_type = "📝 AI 요약"
            
            return f"""{summary_type} **결과**

{response.text.strip()}

───────────────────
📊 **원본 길이**: {len(clean_text)}자 → 요약 완료"""
        else:
            return "📝 요약 생성에 실패했습니다."
            
    except ImportError:
        return "📝 Gemini 패키지가 설치되지 않았습니다."
    except Exception as e:
        print(f"Gemini API 오류: {e}")
        return f"📝 요약 중 오류가 발생했습니다: {str(e)}"

@app.route('/')
def home():
    return """
    <h1>🤖 Slack Bot Server - 요약-bot</h1>
    
    <h2>📝 기본 텍스트 요약</h2>
    <p><strong>@GPT Online [내용] 요약해줘</strong></p>
    
    <h2>📅 단기 채널 대화 요약</h2>
    <ul>
        <li>@GPT Online 오늘 채널 대화 요약해줘</li>
        <li>@GPT Online 최근 12시간 채널 메시지 요약해줘</li>
        <li>@GPT Online 어제부터 채널 대화 요약해줘</li>
    </ul>
    
    <h2>📊 장기 채널 분석 (NEW!)</h2>
    <ul>
        <li>@GPT Online 최근 7일간 채널 분석해줘</li>
        <li>@GPT Online 최근 30일간 채널 분석해줘</li>
        <li>@GPT Online 한달간 채널 분석해줘</li>
        <li>@GPT Online 2주간 채널 분석해줘</li>
    </ul>
    
    <h2>🧵 스레드 요약</h2>
    <p>스레드에서: <strong>@GPT Online 이 스레드 요약해줘</strong></p>
    
    <h2>✨ 지원하는 요약 타입</h2>
    <ul>
        <li>💬 대화 요약: [이름] 형태의 대화 내용</li>
        <li>📄 긴 메시지 요약: 500자 이상의 긴 텍스트</li>
        <li>📋 구조화된 요약: 여러 줄의 구조화된 내용</li>
        <li>📅 단기 채널 요약: 시간별 채널 메시지 수집</li>
        <li>📊 장기 채널 분석: 일/주/월 단위 트렌드 분석</li>
        <li>🧵 스레드 요약: 스레드 전체 대화 분석</li>

    <h1> 유용하게 사용하세요 :) Made By. 숨 </h1>
    </ul>
    """

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
            
            print(f"받은 이벤트 타입: {event_type}")
            
            # message 타입만 처리
            if event_type == 'message':
                user_message = event.get('text', '')
                channel_id = event.get('channel')
                user_id = event.get('user')
                timestamp = event.get('ts', '')
                thread_ts = event.get('thread_ts')  # 스레드 정보
                
                print(f"메시지 처리: {user_message[:100]}..." if len(user_message) > 100 else f"메시지 처리: {user_message}")
                
                # 봇 자신의 메시지 무시
                if event.get('bot_id') or event.get('subtype') == 'bot_message':
                    print("봇 메시지 무시")
                    return 'ok'
                
                # 중복 메시지 확인
                if is_duplicate_message(user_id, channel_id, user_message, timestamp):
                    print("중복 메시지로 인한 무시")
                    return 'ok'
                
                # 봇 멘션 확인
                if '<@U092S5G2P7V>' in user_message:
                    print("봇 멘션 감지")
                    
                    if '요약해줘' in user_message or '분석해줘' in user_message:
                        # 스레드 요약 확인
                        if ('스레드' in user_message or '쓰레드' in user_message) and thread_ts:
                            print("스레드 요약 요청")
                            summary = get_thread_summary(channel_id, thread_ts)
                            send_message_to_slack(channel_id, summary)
                        
                        # 장기 채널 분석 확인 (30일, 7일 등)
                        elif '분석' in user_message or ('일간' in user_message) or ('한달' in user_message) or ('30일' in user_message):
                            days_back = 30  # 기본값
                            
                            if '7일' in user_message or '일주일' in user_message:
                                days_back = 7
                            elif '14일' in user_message or '2주' in user_message:
                                days_back = 14
                            elif '21일' in user_message or '3주' in user_message:
                                days_back = 21
                            elif '30일' in user_message or '한달' in user_message:
                                days_back = 30
                            elif '60일' in user_message or '두달' in user_message:
                                days_back = 60
                            
                            print(f"장기 채널 분석 요청: 최근 {days_back}일")
                            summary = get_long_term_channel_summary(channel_id, days_back)
                            send_message_to_slack(channel_id, summary)
                        
                        # 단기 채널 대화 요약 확인 (시간 단위)
                        elif '채널' in user_message and ('대화' in user_message or '메시지' in user_message):
                            # 시간 파싱
                            hours_back = 24  # 기본값
                            if '1시간' in user_message:
                                hours_back = 1
                            elif '3시간' in user_message:
                                hours_back = 3
                            elif '6시간' in user_message:
                                hours_back = 6
                            elif '12시간' in user_message:
                                hours_back = 12
                            elif '오늘' in user_message:
                                hours_back = 24
                            elif '어제' in user_message or '48시간' in user_message:
                                hours_back = 48
                            elif '3일' in user_message:
                                hours_back = 72
                            
                            print(f"단기 채널 대화 요약 요청: 최근 {hours_back}시간")
                            summary = get_channel_summary(channel_id, hours_back)
                            send_message_to_slack(channel_id, summary)
                        
                        # 기존 텍스트 요약
                        else:
                            print("일반 텍스트 요약 요청")
                            summary = get_gemini_summary(user_message)
                            send_message_to_slack(channel_id, summary)
                    
                    # 도움말
                    elif '도움말' in user_message or '사용법' in user_message:
                        help_message = """📚 **GPT Online 고급 요약 봇 사용법**

**📝 기본 텍스트 요약:**
`@GPT Online [요약할 내용] 요약해줘`

**📅 단기 채널 대화 요약:**
• `@GPT Online 오늘 채널 대화 요약해줘`
• `@GPT Online 최근 12시간 채널 메시지 요약해줘`
• `@GPT Online 어제부터 채널 대화 요약해줘`

**📊 장기 채널 분석 (NEW!):**
• `@GPT Online 최근 7일간 채널 분석해줘`
• `@GPT Online 최근 30일간 채널 분석해줘`
• `@GPT Online 한달간 채널 분석해줘`
• `@GPT Online 2주간 채널 분석해줘`

**🧵 스레드 요약:**
• 스레드에서: `@GPT Online 이 스레드 요약해줘`

**✨ 특별 기능:**
• 📊 사용자 활동 통계 포함
• 📈 기간별 트렌드 분석
• 🏆 활성 사용자 TOP 5
• 📅 일별/주별 메시지 분포
• 🔍 핵심 키워드 및 이슈 추출"""
                        send_message_to_slack(channel_id, help_message)
                    
                    else:
                        help_message = """안녕하세요! 🤖 **고급 요약 봇**입니다!

**📝 주요 기능:**
• 텍스트 요약: `@GPT Online [내용] 요약해줘`
• 단기 채널 요약: `@GPT Online 오늘 채널 대화 요약해줘`
• **장기 채널 분석**: `@GPT Online 최근 30일간 채널 분석해줘` 🆕
• 스레드 요약: `@GPT Online 이 스레드 요약해줘`

**💬 더 자세한 사용법:**
`@GPT Online 도움말`"""
                        send_message_to_slack(channel_id, help_message)
                else:
                    print("봇 멘션 없음")
            
            elif event_type == 'app_mention':
                print("app_mention 이벤트 무시 (중복 방지)")
            
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)