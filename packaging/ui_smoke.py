"""Automated UI acceptance test for a disposable native-server test instance.

Runs in CI's own headless Chromium; never uses an operator's browser profile.
"""
from pathlib import Path


def verify_ui(admin_origin, web_origin, documents, output):
    from playwright.sync_api import sync_playwright, expect
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
            errors = []
            admin = context.new_page()
            admin.on("pageerror", lambda error: errors.append(str(error)))
            admin.goto(admin_origin)
            expect(admin.get_by_role("heading", name="管理员登录")).to_be_visible()
            admin.get_by_label("密码", exact=True).fill("Native-Smoke-Only-2026!")
            admin.get_by_role("button", name="登录管理端").click()
            expect(admin.get_by_role("heading", name="开放哪些资料？")).to_be_visible()
            admin.get_by_label("服务器文件夹路径").fill(str(documents))
            admin.get_by_role("button", name="扫描目录", exact=True).click()
            expect(admin.locator("#notice")).to_contain_text("目录扫描完成", timeout=120000)
            admin.get_by_label("资料室.md", exact=True).check()
            admin.get_by_role("button", name="保存访问范围").click()
            expect(admin.locator("#notice")).to_contain_text("访问范围已保存")
            admin.screenshot(path=str(output / "admin-desktop.png"), full_page=True)

            query = context.new_page()
            query.on("pageerror", lambda error: errors.append(str(error)))
            query.goto(web_origin)
            assert str(documents) not in query.locator("body").inner_text()
            assert query.locator('input[type="file"], input[type="password"], #source, #libraries').count() == 0
            query.locator("#question").fill("资料室开放时间是什么？")
            query.get_by_role("button", name="查找原文").click()
            expect(query.locator("blockquote").first).to_contain_text("09:30", timeout=180000)
            assert "SECRET-NOT-PUBLISHED-429" not in query.locator("body").inner_text()
            query.screenshot(path=str(output / "query-desktop.png"), full_page=True)
            query.set_viewport_size({"width": 390, "height": 844})
            assert query.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            query.screenshot(path=str(output / "query-mobile.png"), full_page=True)

            admin.get_by_role("button", name="关闭全部资料访问").click()
            expect(admin.locator("#notice")).to_contain_text("已关闭全部资料访问")
            query.get_by_role("button", name="查找原文").click()
            expect(query.locator("#message")).to_contain_text("管理员尚未开放")
            admin.get_by_role("button", name="修改密码", exact=True).click()
            admin.get_by_label("当前密码", exact=True).fill("Native-Smoke-Only-2026!")
            admin.get_by_label("新密码", exact=True).fill("UI-Smoke-Changed-2026!")
            admin.get_by_label("再次输入新密码", exact=True).fill("UI-Smoke-Changed-2026!")
            admin.get_by_role("button", name="保存新密码").click()
            expect(admin.locator("#notice")).to_contain_text("管理员密码已更新")
            admin.get_by_role("button", name="退出登录").click()
            expect(admin.get_by_role("heading", name="管理员登录")).to_be_visible()
            admin.get_by_label("密码", exact=True).fill("UI-Smoke-Changed-2026!")
            admin.get_by_role("button", name="登录管理端").click()
            expect(admin.get_by_role("heading", name="开放哪些资料？")).to_be_visible()
            admin.set_viewport_size({"width": 390, "height": 844})
            assert admin.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            admin.screenshot(path=str(output / "admin-mobile.png"), full_page=True)
            assert not errors, errors
            context.close()
        finally:
            browser.close()
