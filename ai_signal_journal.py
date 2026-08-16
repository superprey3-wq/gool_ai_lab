from __future__ import annotations
import json,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
STORE=Path('ai_scout_signals.json')
MSK=timezone(timedelta(hours=3))
def _load():
    try:
        x=json.loads(STORE.read_text('utf-8'));return x if isinstance(x,list) else []
    except:return []
def _save(rows):
    STORE.write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
def add(entry):
    rows=_load();entry=dict(entry);entry.setdefault('id',f"{entry.get('event_id')}:{int(time.time())}");entry.setdefault('created_ts',int(time.time()));entry.setdefault('result','pending');rows.append(entry);_save(rows);return entry['id']
def pending():return [r for r in _load() if r.get('result')=='pending']
def close(signal_id,result,final_score=None,goal_minute=None):
    rows=_load();changed=False
    for r in rows:
        if r.get('id')==signal_id and r.get('result')=='pending':
            r['result']=result;r['closed_ts']=int(time.time());r['final_score']=final_score or r.get('final_score');r['goal_minute']=goal_minute;changed=True
    if changed:_save(rows)
    return changed
def build_report():
    rows=_load();today=datetime.now(MSK).date();day=[]
    for r in rows:
        try:d=datetime.fromtimestamp(int(r.get('created_ts',0)),MSK).date()
        except:continue
        if d==today:day.append(r)
    wins=sum(r.get('result')=='win' for r in day);loss=sum(r.get('result')=='loss' for r in day);pend=sum(r.get('result')=='pending' for r in day);closed=wins+loss;rate=round(wins*100/closed) if closed else 0
    def bucket(lo,hi=None):
        arr=[r for r in day if lo<=int(r.get('probability',0)) and (hi is None or int(r.get('probability',0))<=hi) and r.get('result') in {'win','loss'}]
        w=sum(r.get('result')=='win' for r in arr);return f"{w}/{len(arr)} · {round(w*100/len(arr)) if arr else 0}%"
    lines=[f"📊 <b>GEMINI SCOUT — ОТЧЁТ</b>",f"🗓 {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')} МСК","",f"Сигналов: <b>{len(day)}</b>",f"✅ Зашло: <b>{wins}</b>",f"❌ Не зашло: <b>{loss}</b>",f"⏳ В игре: <b>{pend}</b>",f"🎯 Проходимость закрытых: <b>{rate}%</b>","","🤖 <b>По оценке Gemini</b>",f"• 70–79%: {bucket(70,79)}",f"• 80–89%: {bucket(80,89)}",f"• 90%+: {bucket(90)}","","Последние сигналы:"]
    for r in day[-8:][::-1]:
        icon={'win':'✅','loss':'❌','pending':'⏳'}.get(r.get('result'),'•');lines.append(f"{icon} {r.get('home')} — {r.get('away')} | {r.get('minute')}' {r.get('score_at_signal')} · {r.get('probability')}%")
    return '\n'.join(lines)
