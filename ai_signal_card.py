"""PNG cards for Gemini LIVE Scout entry and goal confirmation."""
from __future__ import annotations
from io import BytesIO
import textwrap
from PIL import Image,ImageDraw,ImageFont
W,H=1080,1080
BG=(7,12,20);PANEL=(15,24,38);PANEL2=(21,31,47);TEXT=(246,248,252);MUTED=(158,172,193);PURPLE=(173,112,255);GREEN=(85,215,126);GOLD=(255,188,62);LINE=(47,63,87);RED=(255,112,112)
def _font(size,bold=False):
 paths=["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
 for p in paths:
  try:return ImageFont.truetype(p,size)
  except OSError:pass
 return ImageFont.load_default()
def _fit(d,text,width,start=40,bold=True):
 text=str(text or '')
 for s in range(start,17,-2):
  f=_font(s,bold)
  if d.textbbox((0,0),text,font=f)[2]<=width:return f
 return _font(18,bold)
def _center(d,text,y,font,fill):
 b=d.textbbox((0,0),str(text),font=font);d.text(((W-(b[2]-b[0]))/2,y),str(text),font=font,fill=fill)
def _pill(d,box,text,accent):
 d.rounded_rectangle(box,20,fill=PANEL2,outline=accent,width=2);f=_font(24,True);b=d.textbbox((0,0),text,font=f);d.text(((box[0]+box[2]-(b[2]-b[0]))/2,(box[1]+box[3]-(b[3]-b[1]))/2-3),text,font=f,fill=accent)
def _out(img):
 out=BytesIO();img.save(out,'PNG',optimize=True);return out.getvalue()
def render(match,verdict,model,now_msk):
 img=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(img);d.rounded_rectangle((30,25,1050,115),26,fill=PANEL,outline=PURPLE,width=3);d.text((62,50),'GEMINI LIVE SCOUT',font=_font(31,True),fill=TEXT);_pill(d,(790,43,1020,98),'AI ВХОД',PURPLE)
 league=str(getattr(match,'league','') or 'Турнир не определён');_center(d,league,145,_fit(d,league,880,25,False),MUTED);teams=f"{getattr(match,'home','')} — {getattr(match,'away','')}";_center(d,teams,195,_fit(d,teams,930,42,True),TEXT)
 d.rounded_rectangle((85,270,995,455),30,fill=PANEL2,outline=LINE,width=2);_center(d,'● LIVE',290,_font(24,True),GREEN);score=f"{int(getattr(match,'home_score',0) or 0)} : {int(getattr(match,'away_score',0) or 0)}";_center(d,score,330,_font(78,True),TEXT);_center(d,f"{int(getattr(match,'minute',0) or 0)}'",413,_font(29,True),GOLD)
 d.rounded_rectangle((85,485,995,620),30,fill=(12,31,27),outline=GREEN,width=3);_center(d,'🔥 ВИЖУ ЕЩЁ ГОЛ',508,_font(42,True),GREEN);prob=int(verdict.get('goal_probability') or 0);h=int(verdict.get('horizon_minutes') or 0);d.text((125,570),f'AI: {prob}%',font=_font(28,True),fill=TEXT);d.text((420,570),f'Горизонт: ~{h} мин',font=_font(28,True),fill=TEXT);conf={'HIGH':'ВЫСОКАЯ','MEDIUM':'СРЕДНЯЯ','LOW':'НИЗКАЯ'}.get(str(verdict.get('confidence') or '').upper(),'—');d.text((760,570),conf,font=_font(24,True),fill=GOLD)
 d.rounded_rectangle((85,650,995,915),30,fill=PANEL,outline=LINE,width=2);d.text((125,682),'ПОЧЕМУ GEMINI ВИДИТ ГОЛ',font=_font(25,True),fill=PURPLE);yy=730
 for line in textwrap.wrap(str(verdict.get('reason') or '—'),width=61)[:4]:d.text((125,yy),line,font=_font(23),fill=TEXT);yy+=35
 d.text((125,855),'⚠ РИСК',font=_font(22,True),fill=RED);risk=textwrap.wrap(str(verdict.get('risk') or '—'),width=68);d.text((255,855),risk[0] if risk else '—',font=_font(21),fill=MUTED)
 d.text((70,960),f'{now_msk} МСК',font=_font(21),fill=MUTED);mf=_fit(d,model,420,20,False);mb=d.textbbox((0,0),model,font=mf);d.text((1010-(mb[2]-mb[0]),960),model,font=mf,fill=MUTED);_center(d,'НЕЗАВИСИМЫЙ АНАЛИЗ LIVE-ДАННЫХ FLASHSCORE',1015,_font(19,True),MUTED);return _out(img)
def render_goal(entry,new_score,goal_minute,now_msk):
 img=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(img);d.rounded_rectangle((30,25,1050,125),28,fill=(10,35,27),outline=GREEN,width=4);d.text((60,53),'GEMINI LIVE SCOUT',font=_font(30,True),fill=TEXT);_pill(d,(765,45,1020,105),'✓ ЗАХОД',GREEN)
 league=str(entry.get('league') or 'Турнир не определён');_center(d,league,160,_fit(d,league,900,25,False),MUTED);teams=f"{entry.get('home','')} — {entry.get('away','')}";_center(d,teams,215,_fit(d,teams,930,44,True),TEXT)
 d.rounded_rectangle((80,290,1000,505),32,fill=(11,38,29),outline=GREEN,width=4);_center(d,'✅ ГОЛ ПОДТВЕРЖДЁН',315,_font(42,True),GREEN);_center(d,str(new_score).replace(':',' : '),385,_font(82,True),TEXT);_center(d,f"Гол: ~{goal_minute}'" if goal_minute else 'Гол подтверждён LIVE',470,_font(27,True),GOLD)
 d.rounded_rectangle((80,545,1000,790),30,fill=PANEL,outline=LINE,width=2);d.text((125,585),'СИГНАЛ GEMINI',font=_font(25,True),fill=PURPLE);d.text((125,645),f"Вход: {entry.get('minute')}'   |   {entry.get('score_at_signal')}",font=_font(31,True),fill=TEXT);d.text((125,705),f"Оценка AI: {entry.get('probability')}%",font=_font(31,True),fill=GREEN);d.text((600,705),f"Горизонт: ~{entry.get('horizon')} мин",font=_font(27,True),fill=TEXT)
 _center(d,'ПРОГНОЗ НА ЕЩЁ ОДИН ГОЛ СРАБОТАЛ',835,_font(30,True),GREEN);d.text((70,960),f'{now_msk} МСК',font=_font(21),fill=MUTED);model=str(entry.get('model') or 'Gemini');mf=_fit(d,model,420,20,False);mb=d.textbbox((0,0),model,font=mf);d.text((1010-(mb[2]-mb[0]),960),model,font=mf,fill=MUTED);_center(d,'LIVE-ПОДТВЕРЖДЕНИЕ FLASHSCORE',1015,_font(19,True),MUTED);return _out(img)
