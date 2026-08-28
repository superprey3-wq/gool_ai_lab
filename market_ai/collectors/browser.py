import logging
from playwright.sync_api import sync_playwright

log=logging.getLogger(__name__)

class BrowserCollector:
    '''Browser transport. Source-specific parsers are added independently.''' 
    def __init__(self): self.pw=None; self.browser=None
    def start(self):
        if self.browser: return
        self.pw=sync_playwright().start()
        self.browser=self.pw.chromium.launch(headless=True,args=['--disable-dev-shm-usage','--no-sandbox'])
        log.info('BROWSER started chromium')
    def page(self):
        self.start()
        ctx=self.browser.new_context(viewport={'width':1280,'height':720})
        page=ctx.new_page()
        page.route('**/*',lambda route: route.abort() if route.request.resource_type in {'image','media','font'} else route.continue_())
        return page,ctx
    def close(self):
        try:
            if self.browser: self.browser.close()
        finally:
            self.browser=None
            if self.pw:
                try:self.pw.stop()
                except Exception:pass
            self.pw=None
