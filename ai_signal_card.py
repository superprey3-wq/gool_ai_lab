"""Polished PNG cards for Gemini LIVE Scout entry and goal confirmation."""
from __future__ import annotations
from io import BytesIO
import textwrap
from PIL import Image,ImageDraw,ImageFont
W=1080
BG=(6,10,18);PANEL=(14,22,35);PANEL2=(20,30,46);TEXT=(246,248,252);MUTED=(151,166,188)
PURPLE=(176,112,255);GREEN=(84,218,128);GOLD=(255,190,64);LINE=(45,62,85);RED=(255,112,112);CYAN=(83,188,255)
def _font(size,bold=False):
 paths=["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
 for p in paths:
  try:return ImageFont.truetype(p,size)
  except OSError:pass
 return ImageFont.load_default()
def _fit(d,text,width,start=42,bold=True):
 text=str(text or '')
 for s in range(start,17,-2):
  f=_font(s,bold)
  if d.textbbox((0,0),text,font=f)[2]<=width:return f
 return _font(18,bold)
def _center(d,text,y,font,fill):
 b=d.textbbox((0,0),str(text),font=font);d.text(((W-(b[2]-b[0]))/2,y),str(text),font=font,fill=fill)
def _out(img):
 out=BytesIO();img.save(out,'PNG',optimize=True);return out.getvalue()
def _badge(d,box,text,accent):
 d.rounded_rectangle(box,22,fill=(18,25,39),outline=accent,width=3);f=_font(25,True);b=d.textbbox((0,0),text,font=f);d.text(((box[0]+box[2]-(b[2]-b[0]))/2,(box[1]+box[3]-(b[3]-b[1]))/2-2),text,font=f,fill=accent)
def _header(d,title,badge,accent):
 d.rounded_rectangle((28,24,1052,122),28,fill=PANEL,outline=accent,width=3);d.text((62,52),title,font=_font(31,True),fill=TEXT);_badge(d,(790,45,1020,102),badge,accent)
def _wrap(d,text,x,y,width_chars,max_lines,font_size,fill,line_gap=36):
 lines=textwrap.wrap(str(text or '—'),width=width_chars)[:max_lines]
 for line in lines:d.text((x,y),line,font=_font(font_size),fill=fill);y+=line_gap
 return y
def render(match,verdict,model,now_msk):
 H=1180;img=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(img);_header(d,'GEMINI LIVE SCOUT','AI ВХОД',PURPLE)
 league=str(getattr(match,'league','') or 'Турнир не определён');_center(d,league,153,_fit(d,league,880,25,False),MUTED)
 teams=f"{getattr(match,'home','')} — {getattr(match,'away','')}";_center(d,teams,205,_fit(d,teams,930,44,True),TEXT)
 d.rounded_rectangle((70,282,1010,485),34,fill=PANEL2,outline=LINE,width=2);_center(d,'LIVE',303,_font(24,True),GREEN);d.ellipse((435,309,451,325),fill=GREEN)
 score=f"{int(getattr(match,'home_score',0) or 0)} : {int(getattr(match,'away_score',0) or 0)}";_center(d,score,342,_font(82,True),TEXT);_center(d,f"{int(getattr(match,'minute',0) or 0)}'",438,_font(30,True),GOLD)
 prob=int(verdict.get('goal_probability') or 0);h=int(verdict.get('horizon_minutes') or 0);conf={'HIGH':'ВЫСОКАЯ','MEDIUM':'СРЕДНЯЯ','LOW':'НИЗКАЯ'}.get(str(verdict.get('confidence') or '').upper(),'—')
 d.rounded_rectangle((70,520,1010,695),34,fill=(10,32,27),outline=GREEN,width=3);_center(d,'ВИЖУ ЕЩЁ ОДИН ГОЛ',548,_font(40,True),GREEN)
 d.line((385,620,385,670),fill=(53,92,76),width=2);d.line((710,620,710,670),fill=(53,92,76),width=2)
 d.text((120,620),'AI ОЦЕНКА',font=_font(19,True),fill=MUTED);d.text((120,650),f'{prob}%',font=_font(31,True),fill=TEXT)
 d.text((430,620),'ГОРИЗОНТ',font=_font(19,True),fill=MUTED);d.text((430,650),f'~{h} мин',font=_font(31,True),fill=TEXT)
 d.text((755,620),'УВЕРЕННОСТЬ',font=_font(19,True),fill=MUTED);d.text((755,650),conf,font=_fit(d,conf,210,25,True),fill=GOLD)
 d.rounded_rectangle((70,735,1010,1040),34,fill=PANEL,outline=LINE,width=2);d.text((115,772),'ПОЧЕМУ GEMINI ЖДЁТ ГОЛ',font=_font(24,True),fill=PURPLE)
 y=_wrap(d,verdict.get('reason'),115,822,64,4,22,TEXT,34)
 d.line((115,960,965,960),fill=LINE,width=2);d.text((115,982),'РИСК',font=_font(21,True),fill=RED);_wrap(d,verdict.get('risk'),230,978,63,2,20,MUTED,31)
 d.text((70,1090),f'{now_msk} МСК',font=_font(20),fill=MUTED);mf=_fit(d,model,390,19,False);mb=d.textbbox((0,0),model,font=mf);d.text((1010-(mb[2]-mb[0]),1090),model,font=mf,fill=MUTED);_center(d,'НЕЗАВИСИМЫЙ LIVE-АНАЛИЗ FLASHSCORE',1135,_font(18,True),MUTED);return _out(img)
def render_goal(entry,new_score,goal_minute,now_msk):
 H=1080;img=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(img);_header(d,'GEMINI LIVE SCOUT','ЗАХОД',GREEN)
 league=str(entry.get('league') or 'Турнир не определён');_center(d,league,158,_fit(d,league,900,25,False),MUTED);teams=f"{entry.get('home','')} — {entry.get('away','')}";_center(d,teams,212,_fit(d,teams,930,44,True),TEXT)
 d.rounded_rectangle((70,290,1010,535),36,fill=(9,36,28),outline=GREEN,width=4);_center(d,'ГОЛ ПОДТВЕРЖДЁН',320,_font(40,True),GREEN);_center(d,str(new_score).replace(':',' : '),382,_font(86,True),TEXT);_center(d,f"Гол ~{goal_minute}'" if goal_minute else 'Гол подтверждён LIVE',482,_font(27,True),GOLD)
 d.rounded_rectangle((70,575,1010,840),34,fill=PANEL,outline=LINE,width=2);d.text((115,612),'КАК БЫЛ ДАН СИГНАЛ',font=_font(24,True),fill=PURPLE)
 d.text((115,670),'ВХОД',font=_font(19,True),fill=MUTED);d.text((115,704),f"{entry.get('minute')}'  |  {entry.get('score_at_signal')}",font=_font(32,True),fill=TEXT)
 d.text((460,670),'ОЦЕНКА AI',font=_font(19,True),fill=MUTED);d.text((460,704),f"{entry.get('probability')}%",font=_font(32,True),fill=GREEN)
 d.text((735,670),'ГОРИЗОНТ',font=_font(19,True),fill=MUTED);d.text((735,704),f"~{entry.get('horizon')} мин",font=_font(30,True),fill=TEXT)
 d.rounded_rectangle((115,765,965,815),22,fill=(12,31,27),outline=(40,92,70),width=2);_center(d,'ПРОГНОЗ НА ЕЩЁ ОДИН ГОЛ СРАБОТАЛ',775,_font(23,True),GREEN)
 d.text((70,925),f'{now_msk} МСК',font=_font(20),fill=MUTED);model=str(entry.get('model') or 'Gemini');mf=_fit(d,model,390,19,False);mb=d.textbbox((0,0),model,font=mf);d.text((1010-(mb[2]-mb[0]),925),model,font=mf,fill=MUTED);_center(d,'LIVE-ПОДТВЕРЖДЕНИЕ FLASHSCORE',985,_font(18,True),MUTED);return _out(img)
