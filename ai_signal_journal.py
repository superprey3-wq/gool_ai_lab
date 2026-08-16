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
def has_pending_event(event_id):
    eid=str(event_id)
    return any(str(r.get('event_id'))==eid and r.get('result')=='pending' for r in _load())
def has_pending_snapshot(event_id,score):
    eid=str(event_id);score=str(score)
    return any(str(r.get('event_id'))==eid and str(r.get('score_at_signal'))==score and r.get('result')=='pending' for r in _load())
def close(signal_id,result,final_score=None,goal_minute=None):
    rows=_load();changed=False
    for r in rows:
        if r.get('id')==signal_id and r.get('result')=='pending':
            r['result']=result;r['closed_ts']=int(time.time());r['final_score']=final_score or r.get('final_score');r['goal_minute']=goal_minute;changed=True
    if changed:_save(rows)
    return changed
def _day_rows():
    rows=_load();today=datetime.now(MSK).date();day=[]
    for r in rows:
        try:d=datetime.fromtimestamp(int(r.get('created_ts',0)),MSK).date()
        except:continue
        if d==today:day.append(r)
    return day
def _bucket(day,lo,hi=None):
    arr=[r for r in day if lo<=int(r.get('probability',0)) and (hi is None or int(r.get('probability',0))<=hi) and r.get('result') in {'win','loss'}]
    w=sum(r.get('result')=='win' for r in arr);pct=round(w*100/len(arr)) if arr else 0
    return w,len(arr),pct
def build_report():
    day=_day_rows();wins=sum(r.get('result')=='win' for r in day);loss=sum(r.get('result')=='loss' for r in day);pend=sum(r.get('result')=='pending' for r in day);voids=sum(r.get('result')=='void' for r in day);closed=wins+loss;rate=round(wins*100/closed) if closed else 0
    b1=_bucket(day,70,79);b2=_bucket(day,80,89);b3=_bucket(day,90)
    now=datetime.now(MSK).strftime('%d.%m.%Y %H:%M')
    lines=['📊 <b>GEMINI LIVE SCOUT — ОТЧЁТ</b>',f'🗓 {now} МСК','',
        '<pre>╭──────────────────────╮',f'│ Сигналов      {len(day):>5} │',f'│ ✅ Зашло       {wins:>5} │',f'│ ❌ Не зашло    {loss:>5} │',f'│ ⏳ В игре       {pend:>5} │',f'│ ⚪ Аннулир.     {voids:>5} │',f'│ 🎯 Проходимость {rate:>4}% │','╰──────────────────────╯</pre>',
        '<b>🤖 По оценке Gemini</b>','<pre>┌────────┬────────┬──────┐','│ AI %   │ Win/All│ Win% │','├────────┼────────┼──────┤',f'│ 70–79  │ {b1[0]:>2}/{b1[1]:<3} │ {b1[2]:>3}% │',f'│ 80–89  │ {b2[0]:>2}/{b2[1]:<3} │ {b2[2]:>3}% │',f'│ 90+    │ {b3[0]:>2}/{b3[1]:<3} │ {b3[2]:>3}% │','└────────┴────────┴──────┘</pre>','<b>Последние сигналы</b>']
    for r in day[-8:][::-1]:
        icon={'win':'✅','loss':'❌','pending':'⏳','void':'⚪'}.get(r.get('result'),'•');home=str(r.get('home') or '');away=str(r.get('away') or '');name=f'{home} — {away}'
        if len(name)>29:name=name[:28]+'…'
        lines.append(f"{icon} <b>{name}</b>\n↳ {r.get('minute')}' · {r.get('score_at_signal')} · AI {r.get('probability')}%")
    if not day:lines.append('Пока сигналов за сегодня нет.')
    return '\n'.join(lines)
