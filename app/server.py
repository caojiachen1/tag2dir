import os
import re
import json
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from .utils_metadata import extract_people_and_tags, has_exiftool
from .utils_thumbs import get_thumbnail_path, build_thumbnail
from .utils_scan import scan_images, is_allowed_image


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["CACHE_DIR"] = os.path.abspath(os.path.join(app.root_path, "cache"))
    os.makedirs(app.config["CACHE_DIR"], exist_ok=True)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        return jsonify({"ok": True, "hasExiftool": bool(has_exiftool())})

    @app.post("/api/scan")
    def api_scan():
        data = request.get_json(force=True) or {}
        src_dir = data.get("srcDir")
        if not src_dir or not os.path.isdir(src_dir):
            return jsonify({"ok": False, "error": "源目录不存在"}), 400
        if not has_exiftool():
            return jsonify({"ok": False, "error": "未检测到 exiftool，可安装 https://exiftool.org/ 并将其加入系统 PATH"}), 400
        
        results = []
        for path in scan_images(src_dir):
            people, tags = extract_people_and_tags(path)
            # Compatible with old interface: only return when there are people names
            if people:
                results.append({
                    "path": path,
                    "people": people,
                    "tags": tags,
                })
        return jsonify({"ok": True, "items": results})

    @app.get("/api/scan_stream")
    def api_scan_stream():
        """Push scan results one by one per image (SSE).
        Parameters:
          - srcDir: source directory
        Event data:
          {"type":"start"}
          {"type":"item", "idx", "path", "people", "tags"}
          {"type":"end", "count"}
        """
        src_dir = request.args.get("srcDir")
        if not src_dir or not os.path.isdir(src_dir):
            return jsonify({"ok": False, "error": "源目录不存在"}), 400
        if not has_exiftool():
            return jsonify({"ok": False, "error": "未检测到 exiftool，可安装 https://exiftool.org/ 并将其加入系统 PATH"}), 400

        def sse_event(payload: dict, event: str | None = None) -> str:
            data = json.dumps(payload, ensure_ascii=False)
            lines = []
            if event:
                lines.append(f"event: {event}")
            # Split by lines, send line by line for better compatibility
            for line in data.splitlines() or [""]:
                lines.append(f"data: {line}")
            lines.append("")  # Empty line to end the event
            return "\n".join(lines) + "\n"

        def generate():
            # Start event
            yield sse_event({"type": "start"}, event="start")
            idx = 0
            for path in scan_images(src_dir):
                idx += 1
                try:
                    people, tags = extract_people_and_tags(path)
                except Exception as e:
                    people, tags = [], []
                item = {"type": "item", "idx": idx, "path": path, "people": people, "tags": tags}
                yield sse_event(item, event="item")
            # End event
            yield sse_event({"type": "end", "count": idx}, event="end")

        resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
        # Try to avoid intermediate proxy buffering to improve real-time performance
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        resp.headers["Connection"] = "keep-alive"
        return resp

    @app.get("/thumbnail")
    def thumbnail():
        path = request.args.get("path")
        size = int(request.args.get("size", 256))
        if not path or not os.path.isfile(path) or not is_allowed_image(path):
            return jsonify({"ok": False, "error": "无效图片路径"}), 400
        thumb_path = get_thumbnail_path(app.config["CACHE_DIR"], path, size)
        if not os.path.exists(thumb_path):
            try:
                build_thumbnail(path, thumb_path, size)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        return send_file(thumb_path, mimetype="image/jpeg")

    @app.get("/api/browse")
    def api_browse():
        """Open native system selection dialog, return selected path.
        Parameters:
          - type: 'dir' | 'file', default 'dir'
          - initial: initial directory
          - title: dialog title
        Returns: { ok, path, canceled? }
        """
        typ = request.args.get("type", "dir").lower()
        initial = request.args.get("initial") or os.getcwd()
        title = request.args.get("title") or ("选择文件" if typ == "file" else "选择目录")
        try:
            # Delayed import to avoid early failure in non-GUI environments
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            # Set to topmost to avoid being hidden behind the browser
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass

            selected = None
            if typ == "file":
                selected = filedialog.askopenfilename(initialdir=initial, title=title)
            else:
                # Select directory; allow creating non-existent directories (on Windows, it will return the new path entered by the user)
                selected = filedialog.askdirectory(initialdir=initial, title=title, mustexist=False)
            try:
                root.destroy()
            except Exception:
                pass

            if not selected:
                return jsonify({"ok": True, "canceled": True, "path": ""})
            return jsonify({"ok": True, "path": selected})
        except Exception as e:
            return jsonify({"ok": False, "error": f"无法打开系统选择窗口: {e}"}), 500

    @app.post("/api/move")
    def api_move():
        data = request.get_json(force=True) or {}
        plan = data.get("plan", [])
        dest_root = data.get("destRoot")
        dry_run = bool(data.get("dryRun", False))
        
        if not dest_root:
            return jsonify({"ok": False, "error": "缺少目标根目录"}), 400
        if not os.path.exists(dest_root):
            try:
                os.makedirs(dest_root, exist_ok=True)
            except Exception as e:
                return jsonify({"ok": False, "error": f"无法创建目标目录: {e}"}), 400
        
        moved = []
        errors = []
        import shutil

        def unique_target(path: str) -> str:
            if not os.path.exists(path):
                return path
            base, ext = os.path.splitext(path)
            i = 1
            while True:
                cand = f"{base} ({i}){ext}"
                if not os.path.exists(cand):
                    return cand
                i += 1
        for item in plan:
            src = item.get("path")
            person = item.get("person")
            if not src or not person:
                continue
            if not os.path.isfile(src):
                errors.append({"path": src, "error": "源文件不存在"})
                continue
            # Target directory name: remove illegal characters, while trying to preserve Chinese
            def sanitize_name(name: str) -> str:
                # Allow Chinese, English, numbers, spaces, underscores, hyphens and dots
                allowed = re.compile(r"[^\w\-\u4e00-\u9fa5\. ]+", re.UNICODE)
                out = allowed.sub("", name).strip()
                # Avoid leaving only empty string
                return out or person or "Unknown"

            safe_person = sanitize_name(person)
            target_dir = os.path.join(dest_root, safe_person)
            target_path = os.path.join(target_dir, os.path.basename(src))
            target_path = unique_target(target_path)
            try:
                if not dry_run:
                    os.makedirs(target_dir, exist_ok=True)
                    if os.path.abspath(src) != os.path.abspath(target_path):
                        # Avoid failure caused by cross-disk cutting, use copy+delete, try to preserve metadata
                        shutil.copy2(src, target_path)
                        try:
                            os.remove(src)
                        except Exception:
                            # If deletion fails, rollback the target file
                            try:
                                os.remove(target_path)
                            except Exception:
                                pass
                            raise
                moved.append({"from": src, "to": target_path})
            except Exception as e:
                errors.append({"path": src, "error": str(e)})
        return jsonify({"ok": True, "moved": moved, "errors": errors})

    return app


if __name__ == "__main__":
    import threading, time, webbrowser
    app = create_app()

    def open_browser_when_ready():
        # Small delay to let the server start
        time.sleep(0.7)
        try:
            webbrowser.open_new_tab("http://127.0.0.1:5000/")
        except Exception:
            pass

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
