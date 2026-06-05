"""Brain: 로컬 ollama 호출 (thinking OFF, 음성용 짧은 답).

설정(모델/언어)은 config.json에서 읽는다. keep_alive로 모델을 메모리에 유지.
"""
import json
import urllib.request
import datetime

import config

OLLAMA = "http://127.0.0.1:11434/api/chat"

_WD_KO = ["월", "화", "수", "목", "금", "토", "일"]
_WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WD_JA = ["月", "火", "水", "木", "金", "土", "日"]

# 언어별 시스템 프롬프트 (음성용: 짧게, 마크다운 금지)
_SYSTEM = {
    "ko": ("너는 '음성비서', 사용자의 한국어 음성 비서야. "
           "답은 귀로 듣는 거니까 2~3문장, 길어도 4문장 안으로 짧고 자연스럽게 말해. "
           "목록 기호, 이모지, 마크다운, 별표는 절대 쓰지 말고 사람이 말하듯 평범한 문장으로만 답해. "
           "모르면 모른다고 솔직히 말하고, 친근한 반말로 대화해."),
    "en": ("You are 'VoiceAssistant', the user's English voice assistant. "
           "Answers are heard aloud, so keep them to 2-3 sentences (4 max), short and natural. "
           "Never use bullet points, emoji, markdown, or asterisks — speak in plain spoken sentences. "
           "If you don't know, say so honestly, in a friendly casual tone."),
    "ja": ("あなたは『voice assistant』、ユーザーの日本語音声アシスタントです。"
           "答えは耳で聞くものなので、2〜3文、長くても4文以内で短く自然に話してください。"
           "箇条書き、絵文字、マークダウン、アスタリスクは絶対に使わず、"
           "人が話すような普通の文で答えてください。"
           "分からないことは正直に分からないと言い、親しみやすい口調で話してください。"),
}

# 언어별 현재 시각 주입 문구 (시간/날짜 질문 grounding)
_STAMP = {
    "ko": lambda n: (f" 참고로 지금은 {n.year}년 {n.month}월 {n.day}일 {_WD_KO[n.weekday()]}요일 "
                     f"{n.hour}시 {n.minute}분이야. 시간이나 날짜를 물으면 이걸로 답하고, "
                     "날씨처럼 실시간 정보가 필요한 건 모르면 솔직히 모른다고 해."),
    "en": lambda n: (f" For reference, it is now {n.year}-{n.month:02d}-{n.day:02d} "
                     f"({_WD_EN[n.weekday()]}) {n.hour:02d}:{n.minute:02d}. Use this for time/date "
                     "questions; for live info like weather, admit it if you don't know."),
    "ja": lambda n: (f" 参考までに、今は{n.year}年{n.month}月{n.day}日{_WD_JA[n.weekday()]}曜日"
                     f"{n.hour}時{n.minute}分です。時刻や日付はこれで答え、"
                     "天気などのリアルタイム情報は分からなければ正直にそう言ってください。"),
}


def _system(lang):
    base = _SYSTEM.get(lang, _SYSTEM["ko"])
    stamp = _STAMP.get(lang, _STAMP["ko"])(datetime.datetime.now())
    return base + stamp


def ask(text, history=None):
    """text(사용자 발화) → 음성비서 답변 텍스트. 모델/언어는 config.json 기준."""
    cfg = config.load()
    msgs = [{"role": "system", "content": _system(cfg["language"])}]
    if history:
        msgs += history
    msgs.append({"role": "user", "content": text})
    body = json.dumps({
        "model": cfg["brain_model"],
        "messages": msgs,
        "think": False,
        "stream": False,
        "keep_alive": "30m",
    }).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return d.get("message", {}).get("content", "").strip()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "안녕 음성비서, 한 문장으로 자기소개해줘."
    print(ask(q))
