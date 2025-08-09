import os, sys, json, asyncio
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# 直接Playwright関数を呼ぶ
automation_path = os.path.abspath("automation")
sys.path.insert(0, automation_path)
from tv_controller import (
    capture as tv_capture,
    apply_preset as tv_apply_preset,
    apply_indicator_params as tv_tune,
    open_chart,
    set_timeframe,
    draw_fibo_by_prices,
    draw_fibo_quick,
)
from playwright.async_api import async_playwright


async def handle_capture_chart(args: dict):
    symbol = args["symbol"]
    tf = args.get("tf", "1h")
    indicators = args.get("indicators", [])
    outfile = args.get("outfile", f"automation/screenshots/{symbol}_{tf}.png")
    annotate = args.get("annotate")  # ← 追加（任意）

    path = await tv_capture(symbol, tf, indicators, outfile, annotate=annotate)
    return {
        "ok": True,
        "file": os.path.abspath(path),
        "meta": {"symbol": symbol, "tf": tf, "ts": datetime.utcnow().isoformat() + "Z"},
        "annotated": bool(annotate),
    }


async def handle_tv_action(args: dict):
    action = args.get("action")
    if action == "apply_preset":
        # args: { name, symbol?, tf?, clear_existing?, headless? }
        name = args["name"]
        symbol = args.get("symbol", "USDJPY")
        tf = args.get("tf", "1h")
        clear = bool(args.get("clear_existing", False))
        headless = bool(args.get("headless", True))
        storage = os.getenv("TV_STORAGE", "automation/storage_state.json")

        async with async_playwright() as p:
            b = await p.chromium.launch(headless=headless)
            ctx = await b.new_context(
                storage_state=storage if os.path.exists(storage) else None,
                viewport={"width": 1600, "height": 900},
            )
            # チャートを開いて時間足セット
            from tv_controller import CHART_URL

            page = await ctx.new_page()
            await page.goto(CHART_URL)
            # 簡易に時間足だけ設定（必要なら既存のset_timeframeをimport）
            try:
                from tv_controller import set_timeframe

                await set_timeframe(page, tf)
            except Exception:
                pass
            # シンボル切替（既存open_chartを使うなら置換可）
            try:
                await page.keyboard.press("/")
                from tv_controller import SEARCH_INPUT

                await page.wait_for_selector(SEARCH_INPUT, timeout=3000)
                await page.fill(SEARCH_INPUT, symbol)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(1200)
            except Exception:
                pass

            res = await tv_apply_preset(page, name, clear_existing=clear)
            # スクショも返すと便利
            outfile = f"automation/screenshots/{symbol}_{tf}_{name}.png"
            await page.screenshot(path=outfile)
            await b.close()
            res.update({"screenshot": os.path.abspath(outfile)})
            return {"ok": True, **res}

    # 既存の他アクション
    return {
        "ok": True,
        "msg": f"action '{action}' received",
        "args": args.get("args", {}),
    }


async def handle_draw_fibo(args: dict):
    """Fib描画ハンドラ"""
    mode = args.get("mode", "prices")
    symbol = args.get("symbol", "USDJPY")
    tf = args.get("tf", "1h")
    headless = bool(args.get("headless", True))
    outfile = args.get("outfile", "automation/screenshots/fibo.png")

    async with async_playwright() as p:
        b = await p.chromium.launch(headless=headless)
        ctx = await b.new_context(
            storage_state=(
                os.getenv("TV_STORAGE", "automation/storage_state.json")
                if os.path.exists(
                    os.getenv("TV_STORAGE", "automation/storage_state.json")
                )
                else None
            ),
            viewport={"width": 1600, "height": 900},
        )
        page = await open_chart(ctx, symbol)
        await set_timeframe(page, tf)

        if mode == "prices":
            high = float(args["high"])
            low = float(args["low"])
            res = await draw_fibo_by_prices(
                page,
                high,
                low,
                x_ratio_start=float(args.get("x_ratio_start", 0.25)),
                x_ratio_end=float(args.get("x_ratio_end", 0.75)),
                direction=args.get("direction", "high_to_low"),
            )
        else:
            res = await draw_fibo_quick(
                page, direction=args.get("direction", "high_to_low")
            )

        await page.screenshot(path=outfile)
        await b.close()
        res.update(
            {
                "screenshot": os.path.abspath(outfile),
                "symbol": symbol,
                "tf": tf,
                "mode": mode,
            }
        )
        return {"ok": True, **res}


async def handle_tune_indicator(args: dict):
    name = args["name"]
    params = args["params"]
    headless = bool(args.get("headless", True))
    storage = os.getenv("TV_STORAGE", "automation/storage_state.json")

    async with async_playwright() as p:
        b = await p.chromium.launch(headless=headless)
        ctx = await b.new_context(
            storage_state=storage if os.path.exists(storage) else None,
            viewport={"width": 1600, "height": 900},
        )
        page = await ctx.new_page()
        from tv_controller import CHART_URL

        await page.goto(CHART_URL)
        res = await tv_tune(page, name, params)
        shot = "automation/screenshots/tune_indicator.png"
        await page.screenshot(path=shot)
        await b.close()
        return {"ok": True, "result": res, "screenshot": os.path.abspath(shot)}


async def main():
    # stdinの各行をリクエスト(JSON)とみなし、結果をstdout(JSON)へ返す超簡易ループ
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            params = req.get("params", {})
            req_id = req.get("id")

            if method == "tools/list":
                # Return the list of available tools from manifest
                with open("mcp/manifest.json", "r") as f:
                    manifest = json.load(f)
                res = {"tools": manifest["tools"]}
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments", {}) or {}

                if name == "capture_chart":
                    res = await handle_capture_chart(args)
                elif name == "tv_action":
                    res = await handle_tv_action(args)
                elif name == "tune_indicator":
                    res = await handle_tune_indicator(args)
                elif name == "draw_fibo":
                    res = await handle_draw_fibo(args)
                else:
                    res = {"error": f"unknown tool: {name}"}
            else:
                res = {"error": f"unknown method: {method}"}

            print(json.dumps({"id": req_id, "result": res}), flush=True)

        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
