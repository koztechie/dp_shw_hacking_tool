from src.db import get_connection
import time as _time
from fastapi import APIRouter, Request, BackgroundTasks, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from src.api.core import (
    templates,
    limiter,
    verify_local_access,
    get_workflow_context,
    PROJECT_ROOT,
)
from src.ui.i18n.system import t
from src.logger import logger
from config.settings import DB_PATH
import json
import contextlib

router = APIRouter()


@router.get("/ideas/{prediction_id}", response_class=HTMLResponse)
async def ideas_page(request: Request, prediction_id: str):
    try:
        import duckdb

        con = get_connection(read_only=True)
        row = con.execute(
            "SELECT hackathon_url, idea_1_description, idea_2_description, idea_3_description FROM predictions WHERE id = ?",
            [prediction_id],
        ).fetchone()
    except Exception as e:
        logger.error(f"Помилка зчитування передбачень: {e}")
        return HTMLResponse(f"Помилка бази даних: {e}", status_code=500)
    finally:
        if "con" in locals():
            con.close()

    if not row:
        return HTMLResponse("Передбачення не знайдено (404)", status_code=404)

    def safe_parse(json_str):
        try:
            return json.loads(json_str) if json_str else {}
        except Exception:
            return {}

    ideas = [safe_parse(row[1]), safe_parse(row[2]), safe_parse(row[3])]
    valid_ideas = [i for i in ideas if i and "title" in i]
    workflow = get_workflow_context("/ideas", prediction_id)
    return templates.TemplateResponse(
        request=request,
        name="ideas.html",
        context={
            "prediction_id": prediction_id,
            "ideas": valid_ideas,
            "hackathon_url": row[0],
            "workflow": workflow,
            "t": t,
        },
    )


@router.post("/techspec/{prediction_id}/{idea_index}")
@limiter.limit("5/minute")
async def get_techspec(request: Request, prediction_id: str, idea_index: int):
    try:
        import duckdb

        con = get_connection(read_only=True)
        row = con.execute(
            "SELECT hackathon_url FROM predictions WHERE id = ?", [prediction_id]
        ).fetchone()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if "con" in locals():
            con.close()

    from src.analyzer.techspec_pipeline import generate_and_save_techspec

    techspec = generate_and_save_techspec(
        prediction_id, idea_index, row[0] if row else ""
    )
    if "error" in techspec:
        return JSONResponse({"error": techspec["error"]}, status_code=500)
    return JSONResponse(techspec)


@router.get("/techspec/{prediction_id}", response_class=HTMLResponse)
async def techspec_page(request: Request, prediction_id: str):
    try:
        import duckdb

        con = get_connection(read_only=True)
        row = con.execute(
            "SELECT techspec, selected_idea FROM predictions WHERE id = ?",
            [prediction_id],
        ).fetchone()
    except Exception as e:
        return HTMLResponse(f"Помилка БД: {e}", status_code=500)
    finally:
        if "con" in locals():
            con.close()

    techspec = json.loads(row[0]) if row and row[0] else {}
    workflow = get_workflow_context("/techspec", prediction_id)
    return templates.TemplateResponse(
        request=request,
        name="techspec.html",
        context={
            "techspec": techspec,
            "selected_idea": row[1] if row else None,
            "workflow": workflow,
            "t": t,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, page: int = 1, limit: int = 50):
    page = max(1, min(page, 100))
    limit = max(10, min(limit, 100))
    offset = (page - 1) * limit
    predictions = []
    try:
        import duckdb
        import pandas as pd

        con = get_connection(read_only=True)
        df = con.execute(
            "SELECT p.id, p.hackathon_url, strftime('%Y-%m-%d %H:%M', p.generated_at) as gen_date, p.idea_1_title, p.idea_1_score, p.selected_idea, f.won as feedback_won FROM predictions p LEFT JOIN feedback f ON p.id = f.prediction_id ORDER BY p.generated_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchdf()
        records = df.to_dict("records")
        for r in records:
            r["feedback_won"] = (
                None if pd.isna(r.get("feedback_won")) else bool(r.get("feedback_won"))
            )
        predictions = records
    except Exception as e:
        logger.error(f"Помилка завантаження історії: {e}")
    finally:
        if "con" in locals():
            con.close()
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"predictions": predictions, "page": page, "limit": limit, "t": t},
    )


@router.delete("/history/all")
@limiter.limit("5/minute")
async def delete_all_history(request: Request):
    try:
        import duckdb

        con = get_connection(read_only=False)
        con.execute("DELETE FROM feedback")
        con.execute("DELETE FROM predictions")
        con.close()
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/history/{prediction_id}")
@limiter.limit("20/minute")
async def delete_history_item(request: Request, prediction_id: str):
    try:
        import duckdb

        con = get_connection(read_only=False)
        con.execute("DELETE FROM feedback WHERE prediction_id = ?", [prediction_id])
        con.execute("DELETE FROM predictions WHERE id = ?", [prediction_id])
        con.close()
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/selector", response_class=HTMLResponse)
async def hackathon_selector_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="hackathon_selector.html", context={"t": t}
    )


@router.get("/api/hackathon/recommend")
@limiter.limit("10/minute")
async def recommend_hackathon(request: Request):
    try:
        from src.analyzer.hackathon_selector import get_best_hackathon_async

        result = await get_best_hackathon_async()
        if not result:
            return JSONResponse(
                {"error": "Не знайдено жодного відповідного хакатону."}, status_code=404
            )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/ml/retrain-check")
async def retrain_check():
    suggest_retrain = False
    current_count = 0
    try:
        import duckdb

        con = get_connection(read_only=True)
        current_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
    except Exception:
        pass
    finally:
        if "con" in locals():
            con.close()

    count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
    last_count = 0
    if count_file.exists():
        with contextlib.suppress(BaseException):
            last_count = int(count_file.read_text(encoding="utf-8").strip())

    has_model = (PROJECT_ROOT / "data" / "models" / "best_model.pkl").exists()
    # import time as _time
    cooldown_file = PROJECT_ROOT / "data" / "models" / "last_train_time.txt"
    if cooldown_file.exists():
        with contextlib.suppress(BaseException):
            if (
                _time.time() - float(cooldown_file.read_text(encoding="utf-8").strip())
                < 600
            ):
                return JSONResponse(
                    {
                        "hackathons": current_count,
                        "last_train_count": last_count,
                        "suggest_retrain": False,
                    }
                )

    if not has_model:
        suggest_retrain = True
    elif current_count > last_count:
        delta = current_count - last_count
        if delta >= 20:
            suggest_retrain = True
        else:
            from src.ml.drift_detector import detect_drift

            if delta >= 5 and detect_drift():
                suggest_retrain = True

    return JSONResponse(
        {
            "hackathons": current_count,
            "last_train_count": last_count,
            "suggest_retrain": suggest_retrain,
        }
    )


def run_ml_pipeline():
    try:
        from src.analyzer.batch_features import run_batch_feature_extraction
        from src.ml.train_ensemble import train_ensemble
        import duckdb

        run_batch_feature_extraction()
        train_ensemble()
        con = get_connection(read_only=True)
        current_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        con.close()
        count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
        count_file.parent.mkdir(parents=True, exist_ok=True)
        count_file.write_text(str(current_count), encoding="utf-8")
        # import time as _time
        (PROJECT_ROOT / "data" / "models" / "last_train_time.txt").write_text(
            str(_time.time()), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"Помилка MLOps пайплайну: {e}")


@router.post("/ml/retrain", dependencies=[Depends(verify_local_access)])
@limiter.limit("2/minute")
async def retrain_model(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ml_pipeline)
    return JSONResponse({"status": "retraining started"})


@router.get("/ml/evolution")
async def ml_evolution():
    from src.analyzer.evolution_engine import analyze_system_performance

    return JSONResponse(analyze_system_performance())


@router.post("/feedback/{prediction_id}", dependencies=[Depends(verify_local_access)])
async def submit_feedback(
    prediction_id: str,
    background_tasks: BackgroundTasks,
    won: bool = Form(...),
    actual_place: int = Form(0),
):
    try:
        import duckdb

        con = get_connection(read_only=False)
        if not con.execute(
            "SELECT id FROM predictions WHERE id = ?", [prediction_id]
        ).fetchone():
            return JSONResponse(
                {"status": "error", "error": "Prediction not found"}, status_code=404
            )
        con.execute(
            "INSERT INTO feedback VALUES (?, ?, ?, current_timestamp)",
            [prediction_id, won, actual_place],
        )
        con.commit()
        from src.analyzer.evolution_engine import trigger_auto_evolution_check

        background_tasks.add_task(trigger_auto_evolution_check)
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
    finally:
        if "con" in locals():
            con.close()
    return JSONResponse({"status": "success"})


@router.post("/generate_assets/{prediction_id}")
async def generate_assets(prediction_id: str):
    try:
        import duckdb

        con = get_connection(read_only=True)
        row = con.execute(
            "SELECT techspec FROM predictions WHERE id = ?", [prediction_id]
        ).fetchone()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if "con" in locals():
            con.close()
    if not row or not row[0]:
        return JSONResponse({"error": "TechSpec not found."}, status_code=404)
    try:
        from src.analyzer.assets_generator import generate_project_assets

        return JSONResponse(generate_project_assets(json.loads(row[0])))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
