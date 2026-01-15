import os
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import docker
import aiofiles
from dotenv import dotenv_values

app = FastAPI(title="SubDir Archiver WebUI")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Docker client
try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"Warning: Docker client unavailable: {e}")
    docker_client = None

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "reddit_archiver"),
        user=os.getenv("POSTGRES_USER", "archiver"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        cursor_factory=RealDictCursor
    )

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI"""
    html_file = Path(__file__).parent / "static" / "index.html"
    if html_file.exists():
        async with aiofiles.open(html_file, 'r') as f:
            return await f.read()
    return "<h1>SubDir Archiver WebUI</h1><p>Frontend not found</p>"

@app.get("/api/stats")
async def get_stats():
    """Get overall database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Overall stats
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') as active_subreddits,
                COUNT(*) FILTER (WHERE status = 'pending') as pending_subreddits,
                COUNT(*) FILTER (WHERE status = 'processing') as processing_subreddits,
                COUNT(*) FILTER (WHERE status = 'error') as error_subreddits,
                COUNT(*) as total_subreddits,
                SUM(total_posts) as total_posts,
                SUM(total_comments) as total_comments,
                SUM(total_media_urls) as total_media_urls
            FROM subreddits
        """)
        stats = cursor.fetchone()

        # Recent activity
        cursor.execute("""
            SELECT name, status, total_posts, total_comments, last_metadata_update
            FROM subreddits
            WHERE last_metadata_update IS NOT NULL
            ORDER BY last_metadata_update DESC
            LIMIT 10
        """)
        recent = cursor.fetchall()

        # Currently processing
        cursor.execute("""
            SELECT name, current_phase, phase_progress
            FROM subreddits s
            JOIN processing_state ps ON s.name = ps.subreddit
            WHERE s.status = 'processing'
        """)
        processing = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "stats": stats,
            "recent_activity": recent,
            "currently_processing": processing,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/subreddits")
async def get_subreddits(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None
):
    """Get list of subreddits with filtering"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM subreddits WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)

        if search:
            query += " AND name ILIKE %s"
            params.append(f"%{search}%")

        query += " ORDER BY last_metadata_update DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        subreddits = cursor.fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) as count FROM subreddits WHERE 1=1"
        count_params = []
        if status:
            count_query += " AND status = %s"
            count_params.append(status)
        if search:
            count_query += " AND name ILIKE %s"
            count_params.append(f"%{search}%")

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()["count"]

        cursor.close()
        conn.close()

        return {
            "subreddits": subreddits,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/subreddit/{name}")
async def get_subreddit_detail(name: str):
    """Get detailed info about a specific subreddit"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Subreddit info
        cursor.execute("SELECT * FROM subreddits WHERE name = %s", (name,))
        subreddit = cursor.fetchone()

        if not subreddit:
            raise HTTPException(status_code=404, detail="Subreddit not found")

        # Processing state
        cursor.execute("SELECT * FROM processing_state WHERE subreddit = %s", (name,))
        processing_state = cursor.fetchone()

        # Recent posts
        cursor.execute("""
            SELECT id, title, score, num_comments, created_utc, post_type
            FROM posts
            WHERE subreddit = %s
            ORDER BY score DESC
            LIMIT 20
        """, (name,))
        top_posts = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "subreddit": subreddit,
            "processing_state": processing_state,
            "top_posts": top_posts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config")
async def get_config():
    """Get current configuration from .env file"""
    try:
        env_path = Path("/app/.env")
        if env_path.exists():
            config = dotenv_values(env_path)
            # Hide sensitive values
            sensitive_keys = ["REDDIT_CLIENT_SECRET", "REDDIT_PASSWORD", "POSTGRES_PASSWORD"]
            for key in sensitive_keys:
                if key in config:
                    config[key] = "***HIDDEN***"
            return {"config": config}
        else:
            raise HTTPException(status_code=404, detail=".env file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
async def update_config(config_updates: Dict[str, str]):
    """Update configuration (writes to .env file)"""
    try:
        env_path = Path("/app/.env")
        if not env_path.exists():
            raise HTTPException(status_code=404, detail=".env file not found")

        # Read current config
        current_config = dotenv_values(env_path)

        # Update values (skip hidden values)
        for key, value in config_updates.items():
            if value != "***HIDDEN***":
                current_config[key] = value

        # Write back
        async with aiofiles.open(env_path, 'w') as f:
            for key, value in current_config.items():
                await f.write(f"{key}={value}\n")

        return {"status": "success", "message": "Configuration updated. Restart containers for changes to take effect."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scanner/status")
async def get_scanner_status():
    """Get scanner container status"""
    if not docker_client:
        return {"status": "unknown", "message": "Docker client unavailable"}

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")
        return {
            "status": container.status,
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else "unknown",
            "created": container.attrs["Created"],
            "started": container.attrs["State"].get("StartedAt"),
        }
    except docker.errors.NotFound:
        return {"status": "not_found", "message": "Scanner container not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/start")
async def start_scanner():
    """Start the scanner container"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker client unavailable")

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")
        if container.status != "running":
            container.start()
            return {"status": "success", "message": "Scanner started"}
        return {"status": "already_running", "message": "Scanner is already running"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Scanner container not found. Run 'docker-compose up -d scanner' first.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/stop")
async def stop_scanner():
    """Stop the scanner container"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker client unavailable")

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")
        if container.status == "running":
            container.stop()
            return {"status": "success", "message": "Scanner stopped"}
        return {"status": "already_stopped", "message": "Scanner is not running"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Scanner container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/restart")
async def restart_scanner():
    """Restart the scanner container"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker client unavailable")

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")
        container.restart()
        return {"status": "success", "message": "Scanner restarted"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Scanner container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """Get recent scanner logs"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker client unavailable")

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")
        logs = container.logs(tail=lines, timestamps=True).decode('utf-8')
        return {"logs": logs.split('\n')}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Scanner container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """Stream logs in real-time via WebSocket"""
    await websocket.accept()

    if not docker_client:
        await websocket.send_json({"error": "Docker client unavailable"})
        await websocket.close()
        return

    try:
        container = docker_client.containers.get("subdir-archiver-scanner")

        # Stream logs
        for line in container.logs(stream=True, follow=True, timestamps=True):
            try:
                await websocket.send_text(line.decode('utf-8'))
                await asyncio.sleep(0.01)  # Small delay to prevent overwhelming
            except WebSocketDisconnect:
                break
    except docker.errors.NotFound:
        await websocket.send_json({"error": "Scanner container not found"})
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        try:
            await websocket.close()
        except:
            pass

@app.post("/api/subreddit/add")
async def add_subreddit(name: str, priority: int = 1):
    """Add a new subreddit to the queue"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if already exists
        cursor.execute("SELECT name FROM subreddits WHERE name = %s", (name,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Subreddit already exists")

        # Add new subreddit
        cursor.execute("""
            INSERT INTO subreddits (name, priority, status, first_seen_at)
            VALUES (%s, %s, 'pending', extract(epoch from now())::bigint)
        """, (name, priority))

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "message": f"Added {name} to queue"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8480)
