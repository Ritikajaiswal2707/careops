"""
Record a scripted CareOps walkthrough (1280x720, captions, visible cursor).

    pip install playwright && python -m playwright install chromium
    python scripts/record_demo.py https://careops-live-demo-18xj.onrender.com/ demo_video

Writes a .webm into the output folder. Convert to MP4 with:
    ffmpeg -i demo_video/<file>.webm -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p careops-demo.mp4

Open the site in a browser first if it has been idle: free hosting can take
up to a minute to wake up, and the recording should not start on a loading page.
"""
import asyncio
import sys

from playwright.async_api import async_playwright

URL = sys.argv[1]
OUT = sys.argv[2]
SHORT = len(sys.argv) > 3 and sys.argv[3] == "short"

OVERLAY = """
(() => {
  const css = document.createElement('style');
  css.textContent = `
    body{padding-bottom:420px !important;}
    #demo-cap{position:fixed; left:50%; bottom:28px; transform:translateX(-50%); max-width:880px; width:calc(100% - 64px);
      background:rgba(20,48,46,.94); color:#fff; font:600 19px/1.4 Figtree, system-ui, sans-serif; padding:14px 22px;
      border-radius:12px; z-index:99999; opacity:0; transition:opacity .35s; text-align:center;}
    #demo-cap.on{opacity:1;}
    #demo-cur{position:fixed; left:0; top:0; width:22px; height:22px; border-radius:50%; background:rgba(30,107,99,.35);
      border:2px solid #1e6b63; z-index:100000; pointer-events:none; transition:transform .6s cubic-bezier(.4,0,.2,1);
      transform:translate(640px,360px);}
    #demo-cur.press{background:rgba(30,107,99,.75);}
    #demo-end{position:fixed; inset:0; background:#f1f5f4; z-index:100001; display:flex; flex-direction:column; align-items:center;
      justify-content:center; gap:14px; font-family:'Bricolage Grotesque', Figtree, sans-serif; color:#14302e; opacity:0; transition:opacity .5s;}
    #demo-end.on{opacity:1;}
    #demo-end h2{font-size:52px; margin:0; letter-spacing:-.02em;}
    #demo-end p{font:500 22px Figtree, sans-serif; margin:0; color:#56706b;}`;
  document.head.appendChild(css);
  const cap = document.createElement('div'); cap.id = 'demo-cap'; document.body.appendChild(cap);
  const cur = document.createElement('div'); cur.id = 'demo-cur'; document.body.appendChild(cur);
})();
"""


async def caption(pg, text, hold=0):
    await pg.evaluate("""t => { const c = document.getElementById('demo-cap'); c.classList.remove('on');
      setTimeout(() => { c.textContent = t; c.classList.add('on'); }, 250); }""", text)
    await pg.wait_for_timeout(400 + hold)


async def move_to(pg, locator):
    await locator.scroll_into_view_if_needed()
    box = await locator.bounding_box()
    x, y = box["x"] + box["width"] / 2 - 11, box["y"] + box["height"] / 2 - 11
    await pg.evaluate("([x, y]) => document.getElementById('demo-cur').style.transform = `translate(${x}px,${y}px)`", [x, y])
    await pg.wait_for_timeout(700)


async def click(pg, locator, after=600):
    await move_to(pg, locator)
    await pg.evaluate("document.getElementById('demo-cur').classList.add('press')")
    await locator.click()
    await pg.wait_for_timeout(150)
    await pg.evaluate("document.getElementById('demo-cur').classList.remove('press')")
    await pg.wait_for_timeout(after)


async def scroll_to(pg, locator, offset=120):
    await pg.evaluate("""([el, off]) => window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - off,
      behavior: 'smooth'})""", [await locator.element_handle(), offset])
    await pg.wait_for_timeout(900)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1,
                                        record_video_dir=OUT, record_video_size={"width": 1280, "height": 720})
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(URL)
        await pg.add_script_tag(content=OVERLAY)
        await pg.wait_for_timeout(1600)

        await caption(pg, "A home-care coordinator's day: 95 visits. CareOps shows the 16 that need her.", 3000)
        card = pg.locator("#list .card.start")
        await scroll_to(pg, card, 70)
        await caption(pg, "A family writes in Hinglish: “Doctor visit hai usi din, reschedule possible?”", 2600)
        await caption(pg, "CareOps finds a day with the usual nurse and drafts the reply, ready to send.", 300)
        await scroll_to(pg, card.locator("details.draft"), 200)
        await pg.wait_for_timeout(2600)
        await caption(pg, "Approving holds the slot. The nurse is told only after the family says yes.", 300)
        await click(pg, card.locator("button.approve"), 3000)
        await click(pg, card.locator("button", has_text="Family said yes"), 2400)

        if not SHORT:
            nb = pg.locator("#list .card", has_text="none is free today").first
            await scroll_to(pg, nb, 120)
            await caption(pg, "No backup nurse free? It is escalated and stays unassigned, never “handled”.", 300)
            await click(pg, nb.locator("button.approve"), 2600)

            await caption(pg, "A nurse is running late, and the next family has not been told. The message is ready.", 300)
            await click(pg, pg.locator('#view-tabs .tab[data-v="cascade"]'), 300)
            await pg.evaluate("window.scrollTo({top: 380, behavior: 'smooth'})")
            await pg.wait_for_timeout(3400)

            await caption(pg, "A nurse calls in sick: CareOps suggests cover for all her visits, without overloading anyone.", 300)
            await click(pg, pg.locator('#view-tabs .tab[data-v="live"]'), 600)
            await click(pg, pg.locator("#mode-nurse"), 300)
            await click(pg, pg.locator("#nurse-button"), 6500)
            await scroll_to(pg, pg.locator("#nurse-result"), 90)
            await pg.wait_for_timeout(3600)

        await caption(pg, "After each visit, the caregiver's voice note becomes a report for the family.", 300)
        await click(pg, pg.locator('#view-tabs .tab[data-v="vr"]'), 600)
        if not SHORT:
            await scroll_to(pg, pg.locator("#vr-list .card", has_text="VR14"), 60)
            await caption(pg, "The AI misheard “sattanve” (97) as 100. Checks after the AI held it for a human.", 4000)
        await scroll_to(pg, pg.locator("#vr-list .card", has_text="VR20"), 60)
        await caption(pg, "Sugar was 62, then 88. The AI kept only 88; a second check caught the 62.", 4000)
        await caption(pg, "So the family gets a holding message, and the full update waits for the coordinator.", 2600)

        await pg.evaluate("""() => { const e = document.createElement('div'); e.id = 'demo-end';
          e.innerHTML = '<h2>CareOps</h2><p>An AI operations copilot for home healthcare</p><p>careops-live-demo-18xj.onrender.com</p>';
          document.body.appendChild(e); requestAnimationFrame(() => e.classList.add('on'));
          document.getElementById('demo-cap').classList.remove('on'); }""")
        await pg.wait_for_timeout(3500)
        print("page errors:", errors)
        await ctx.close()
        await browser.close()


asyncio.run(main())
