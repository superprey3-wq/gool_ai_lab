from collections import defaultdict


def implied(odds):
    return 1.0 / odds if odds and odds > 1 else 0.0


def no_vig_two_way(a, b):
    pa,pb=implied(a),implied(b); s=pa+pb
    return (pa/s,pb/s) if s else (0.0,0.0)


def score_flow(rows, now, window=600):
    by=defaultdict(list)
    for book,odds,ts in rows:
        if odds and ts >= now-window: by[book].append((ts,float(odds)))
    moves=[]
    persistent=0
    reversals=0
    for book, seq in by.items():
        seq.sort(); first=seq[0][1]; last=seq[-1][1]
        if first <= 1 or last <= 1: continue
        move=(first-last)/first*100.0
        moves.append(move)
        if abs(move)>=2.0 and len(seq)>=2: persistent += 1
        if len(seq)>=3:
            low=min(x[1] for x in seq)
            if move>0 and last > low*1.025: reversals += 1
    if not moves: return None
    directional=[m for m in moves if m>=2.0]
    breadth=len(directional)
    avg=sum(directional)/breadth if breadth else 0.0
    velocity=avg/max(window/60.0,1.0)
    move_score=min(30.0,avg*3.0)
    breadth_score=min(30.0,breadth*7.5)
    persistence_score=min(25.0,persistent*6.25)
    velocity_score=min(15.0,velocity*8.0)
    reversal_penalty=min(30.0,reversals*10.0)
    total=max(0.0,min(100.0,move_score+breadth_score+persistence_score+velocity_score-reversal_penalty))
    return {'score':round(total,1),'move_pct':round(avg,2),'breadth':breadth,'books':len(by),'persistent':persistent,'reversals':reversals,'velocity':round(velocity,2)}
