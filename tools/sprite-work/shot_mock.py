from playwright.sync_api import sync_playwright
import sys
src = "/private/tmp/claude-501/-Users-samwilkie/a9cb41ea-f87b-47c5-b2d6-1e2b647554c6/scratchpad/clawd-redesign.html"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width":1100,"height":900}, device_scale_factor=1)
    pg.goto("file://"+src); pg.wait_for_timeout(1500)
    pg.evaluate("document.getElementById('play').click()")  # pause
    pg.screenshot(path=str(__import__('pathlib').Path.home()/"Projects/margarita-tank-worktrees/previews/_mockup.png"), full_page=False, clip={"x":0,"y":330,"width":1100,"height":620})
    b.close()
