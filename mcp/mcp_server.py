import os, sys, json, asyncio
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

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
    close_popups_fast,
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


async def handle_macro_quiettrap_report(args: dict):
    """
    一撃マクロ：
      1) チャートを開く & TF設定 &（必要なら）クリーン前処理
      2) プリセット適用（デフォ: senior_ma_cloud）
      3) （任意）フィボ描画：prices or quick
      4) QuietTrap注釈つきでスクショ撮影
    """
    symbol = args.get("symbol", "USDJPY")
    tf = args.get("tf", "1h")
    outfile = args.get("outfile", f"automation/screenshots/{symbol}_{tf}_macro_qt.png")
    headless = bool(args.get("headless", True))
    clean = bool(args.get("clean", True))

    preset_name = args.get("preset_name", "senior_ma_cloud")
    clear_existing = bool(args.get("clear_existing", True))
    skip_params = bool(args.get("skip_params", False))

    draw_fibo_flag = bool(args.get("draw_fibo", True))
    fibo_mode = args.get("fibo_mode", "prices")
    direction = args.get("direction", "high_to_low")
    xrs = float(args.get("x_ratio_start", 0.25))
    xre = float(args.get("x_ratio_end", 0.75))
    high = args.get("high")
    low = args.get("low")

    quiettrap = args.get("quiettrap") or {"side": "sell", "score": 0.8, "notes": []}

    # 実行
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            storage_state=os.getenv("TV_STORAGE", "automation/storage_state.json"),
            viewport={"width": 1600, "height": 900},
        )

        # 既存の安定した実装を使用（部分最適化のみ）
        page = await open_chart(ctx, symbol)
        await set_timeframe(page, tf)

        # 1) プリセット適用（高速化オプション対応）
        if skip_params:
            print("🚀 高速モード: インジケーターパラメータ調整をスキップします...")
        preset_res = await tv_apply_preset(
            page, preset_name, clear_existing=clear_existing, skip_params=skip_params
        )

        # 2) ポップアップ完全消去 & チャート安定化（フィボ描画前に実行）
        if clean:
            print("🧹 フィボ描画前のポップアップ高速消去...")
            try:
                await close_popups_fast(page)
            except Exception:
                pass

            # チャート完全安定化
            print("⏳ チャート完全安定化を待機...")
            await page.wait_for_timeout(1500)  # 少し長めに戻す

            # キャンバスにフォーカスを確実に当てる
            print("🎯 チャートキャンバスにフォーカス...")
            await page.click("canvas", force=True)
            await page.wait_for_timeout(500)

        # 3) フィボ描画（チャート安定化後に実行）
        fibo_res = None
        if draw_fibo_flag:
            print("📈 フィボナッチ描画開始（チャート安定化済み）...")
            if fibo_mode == "prices" and high is not None and low is not None:
                fibo_res = await draw_fibo_by_prices(
                    page,
                    float(high),
                    float(low),
                    x_ratio_start=xrs,
                    x_ratio_end=xre,
                    direction=direction,
                )
            else:
                fibo_res = await draw_fibo_quick(page, direction=direction)

            # フィボ描画後の追加安定化
            print("⏳ フィボ描画後の最終安定化...")
            await page.wait_for_timeout(1000)

            # 4) フィボ保持スクショ撮影 & QuietTrap注釈
        print("📸 フィボナッチ保持状態でスクリーンショット撮影...")

        # フィボナッチ描画後はポップアップ処理をスキップ（フィボが消去される可能性があるため）
        print("⚠️ フィボナッチ保持のため最終ポップアップチェックはスキップ...")

        # 短い安定化待機のみ
        await page.wait_for_timeout(500)

        os.makedirs(os.path.dirname(outfile), exist_ok=True)
        await page.screenshot(path=outfile)

        # スクリーンショット撮影後にツール選択解除（フィボは既に画像に保存済み）
        print("🔄 スクリーンショット撮影後にツール選択解除...")
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        # 画像後処理で注釈を焼き込む（既存の annotate.py を利用）
        try:
            from annotate import annotate_quiet_trap
        except Exception:
            # 明示import（PYTHONPATH差分対策）
            import importlib.util

            ap = Path(__file__).resolve().parent.parent / "automation" / "annotate.py"
            spec = importlib.util.spec_from_file_location("annotate", ap)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            annotate_quiet_trap = getattr(mod, "annotate_quiet_trap")
        annotate_quiet_trap(
            outfile,
            side=quiettrap.get("side", "sell"),
            score=float(quiettrap.get("score", 0.8)),
            notes=quiettrap.get("notes", []),
            footer=quiettrap.get("footer"),
        )

        await browser.close()

    return {
        "ok": True,
        "file": os.path.abspath(outfile),
        "meta": {
            "symbol": symbol,
            "tf": tf,
            "ts": datetime.utcnow().isoformat() + "Z",
            "preset": preset_name,
            "fibo": fibo_res or {},
        },
    }


async def main():
    # stdinから全体を読み込んでJSONとして解析
    input_data = sys.stdin.read().strip()
    if not input_data:
        print(json.dumps({"error": "No input data"}))
        return

    try:
        req = json.loads(input_data)
        method = req.get("method")
        params = req.get("params", {})
        req_id = req.get("id")

        if method == "tools/list":
            # Return the list of available tools from manifest
            with open("mcp/manifest.json", "r", encoding="utf-8") as f:
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
            elif name == "macro_quiettrap_report":
                res = await handle_macro_quiettrap_report(args)
            else:
                res = {"error": f"unknown tool: {name}"}
        else:
            res = {"error": f"unknown method: {method}"}

        print(json.dumps({"id": req_id, "result": res}), flush=True)

    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
