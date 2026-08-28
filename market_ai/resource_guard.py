def rss_mb():
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'): return float(line.split()[1])/1024.0
    except Exception: pass
    return 0.0
