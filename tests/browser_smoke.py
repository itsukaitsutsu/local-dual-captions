"""Optional developer smoke test. Requires Playwright + its Chromium download.

Uses the real MV3 extension, but a mocked media webpage. It does NOT claim to
validate Windows GPU acceleration or Chrome tab-audio capture on Windows.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    with TemporaryDirectory() as profile, sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True,
            args=[f"--disable-extensions-except={ROOT / 'extension'}",
                  f"--load-extension={ROOT / 'extension'}", "--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        worker = browser.service_workers[0] if browser.service_workers else browser.wait_for_event("serviceworker")
        extension_id = worker.url.split("/")[2]
        popup = browser.new_page()
        popup.on("pageerror", lambda error: errors.append(str(error)))
        popup.goto(f"chrome-extension://{extension_id}/popup.html")
        popup.get_by_role("button", name="Check connection").click()
        popup.get_by_role("alert").wait_for(state="visible")
        assert "pairing key" in popup.get_by_role("alert").inner_text()
        assert popup.locator("#start").is_visible()
        assert popup.locator("body").bounding_box()["height"] == 600
        popup.locator("#position").select_option("top")
        popup.wait_for_function("document.getElementById('position').value === 'top'")
        saved = worker.evaluate("async () => (await chrome.storage.local.get('settings')).settings")
        assert saved["position"] == "top"
        screenshots = ROOT / ".cache" / "screenshots"
        screenshots.mkdir(parents=True, exist_ok=True)
        popup.set_viewport_size({"width": 392, "height": 600})
        popup.screenshot(path=str(screenshots / "popup.png"))

        tab = browser.new_page()
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.route("http://127.0.0.1:9999/**", lambda route: route.fulfill(
            content_type="text/html", body="<html><body style='background:#18232c;color:white;font-family:system-ui'><h1 style='margin:80px'>Local media test page</h1></body></html>"))
        tab.goto("http://127.0.0.1:9999/test")
        tab_id = worker.evaluate("async () => (await chrome.tabs.query({url:'http://127.0.0.1:9999/*'}))[0].id")
        worker.evaluate("async id => chrome.scripting.executeScript({target:{tabId:id},files:['content.js']})", tab_id)
        worker.evaluate("async id => chrome.tabs.sendMessage(id,{type:'LDC_START',settings:{fontSize:28,opacity:90,showJapanese:true,position:'bottom',keepSeconds:12}})", tab_id)
        worker.evaluate("async id => chrome.tabs.sendMessage(id,{type:'LDC_CAPTION',caption:{ja:'今日は、いい天気ですね。',en:'It is a beautiful day today.',translating:false,rtf:.4}})", tab_id)
        tab.locator("#local-dual-captions-overlay").wait_for()
        cdp = browser.new_cdp_session(tab)
        document = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        serialized = json.dumps(document, ensure_ascii=False)
        assert "今日は、いい天気ですね。" in serialized
        assert "It is a beautiful day today." in serialized
        tab.screenshot(path=str(screenshots / "overlay.png"))
        worker.evaluate("async id => chrome.tabs.sendMessage(id,{type:'LDC_STOP'})", tab_id)
        assert tab.locator("#local-dual-captions-overlay").count() == 0
        assert not errors, errors
        browser.close()
    print("PASS: MV3 extension loads; popup settings, pairing error, bilingual shadow-DOM overlay, and stop cleanup.")


if __name__ == "__main__":
    main()
