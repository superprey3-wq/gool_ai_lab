'''OddsPortal/OddsHarvester adapter boundary.

The collector is intentionally isolated: DOM/API changes must not affect the market engine.
The first deployment will verify MonkeyBytes Chromium and source accessibility before selectors are pinned.
'''
import logging
log=logging.getLogger(__name__)

def collect(browser):
    # Runtime-safe placeholder until live source shape is verified on the target host.
    return []
