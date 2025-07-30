from flask import Flask, request, jsonify, send_file, abort, render_template
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 后端存储根目录
BASE_DIR = os.path.abspath("storage")
os.makedirs(BASE_DIR, exist_ok=True)

def safe_path(rel_path=""):
    """
    拼接并规范化路径，防止路径穿越
    """
    target = os.path.normpath(os.path.join(BASE_DIR, rel_path))
    if not target.startswith(BASE_DIR):
        abort(400, description="非法路径访问")
    return target

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/list", methods=["GET"])
def list_files():
    rel = request.args.get("path", "")
    dirp = safe_path(rel)
    if not os.path.isdir(dirp):
        abort(404, description="目录不存在")
    items = []
    for name in sorted(os.listdir(dirp)):
        full = os.path.join(dirp, name)
        items.append({
            "name": name,
            "is_dir": os.path.isdir(full)
        })
    return jsonify({"current": rel, "items": items})

@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or f.filename == "":
        abort(400, description="未选择文件")
    rel = request.form.get("path", "")
    dirp = safe_path(rel)
    if not os.path.isdir(dirp):
        abort(404, description="目录不存在")
    filename = secure_filename(f.filename)
    f.save(os.path.join(dirp, filename))
    return jsonify({"msg": "上传成功"})

@app.route("/api/download", methods=["GET"])
def download():
    rel = request.args.get("path")
    if not rel:
        abort(400, description="请指定path")
    fp = safe_path(rel)
    if not os.path.isfile(fp):
        abort(404, description="文件不存在")
    return send_file(fp, as_attachment=True)

@app.route("/api/delete", methods=["POST"])
def delete():
    rel = request.form.get("path")
    if not rel:
        abort(400, description="请指定path")
    target = safe_path(rel)
    if os.path.isfile(target):
        os.remove(target)
        return jsonify({"msg": "文件已删除"})
    if os.path.isdir(target):
        try:
            os.rmdir(target)
            return jsonify({"msg": "目录已删除"})
        except OSError:
            abort(400, description="目录非空或无法删除")
    abort(404, description="目标不存在")

@app.route("/api/mkdir", methods=["POST"])
def mkdir():
    rel = request.form.get("path", "")
    name = request.form.get("name", "")
    if not name:
        abort(400, description="请指定目录名")
    parent = safe_path(rel)
    if not os.path.isdir(parent):
        abort(404, description="父目录不存在")
    newp = os.path.join(parent, secure_filename(name))
    try:
        os.mkdir(newp)
    except FileExistsError:
        abort(400, description="目录已存在")
    return jsonify({"msg": "目录创建成功"})

@app.route("/api/move", methods=["POST"])
def move():
    data = request.get_json() or request.form
    src = data.get("src")
    dst = data.get("dst")
    if not src or not dst:
        abort(400, description="请指定src和dst")
    psrc = safe_path(src)
    pdst = safe_path(dst)
    if not os.path.exists(psrc):
        abort(404, description="源不存在")
    if os.path.exists(pdst):
        abort(400, description="目标已存在")
    os.renames(psrc, pdst)
    return jsonify({"msg": "移动成功"})

if __name__ == "__main__":
    app.run(debug=True)






<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>文件管理器</title>
  <style>
    body { font-family: sans-serif; }
    ul { padding-left: 20px; }
    li { margin: 4px 0; cursor: pointer; }
    li.folder::before { content: "📁 "; }
    li.file::before   { content: "📄 "; }
    #ctxMenu {
      position: absolute; display: none; background: #fff;
      border: 1px solid #ccc; list-style: none; padding: 0;
      z-index: 1000;
    }
    #ctxMenu li { padding: 5px 10px; }
    #ctxMenu li:hover { background: #eef; }
  </style>
</head>
<body>
  <h2>文件管理器</h2>
  <div>
    当前路径：<span id="currentPath">/</span>
    <button onclick="goUp()">上级</button>
    <input type="file" id="fileInput">
    <button onclick="upload()">上传</button>
    <button onclick="makeDir()">新建文件夹</button>
  </div>
  <ul id="tree"></ul>

  <ul id="ctxMenu">
    <li onclick="onMoveHere()">移动到此处</li>
    <li onclick="onDelete()">删除</li>
    <li onclick="onDownload()">下载</li>
  </ul>

  <script>
    let current = "";
    let ctxTarget = null;

    // 加载目录
    function load(path="") {
      fetch(`/api/list?path=${encodeURIComponent(path)}`)
        .then(r => r.json())
        .then(data => {
          current = data.current;
          document.getElementById("currentPath").innerText = "/" + current;
          renderTree(data.items);
        });
    }

    // 渲染列表
    function renderTree(items) {
      const ul = document.getElementById("tree");
      ul.innerHTML = "";
      items.forEach(it => {
        const li = document.createElement("li");
        li.textContent = it.name;
        li.className = it.is_dir ? "folder" : "file";
        li.draggable = true;
        li.dataset.name = it.name;
        li.oncontextmenu = e => { openCtx(e, it); };
        li.ondblclick = e => { if (it.is_dir) load(join(current, it.name)); };
        li.ondragstart = e => {
          e.dataTransfer.setData("text/plain", join(current, it.name));
        };
        li.ondragover = e => { e.preventDefault(); };
        li.ondrop = e => {
          e.preventDefault();
          const src = e.dataTransfer.getData("text/plain");
          const dst = join(current, it.name, it.is_dir ? "" : "");
          doMove(src, join(current, it.name));
        };
        ul.appendChild(li);
      });
    }

    // 上传
    function upload() {
      const f = document.getElementById("fileInput").files[0];
      if (!f) return alert("请先选文件");
      const fd = new FormData();
      fd.append("file", f);
      fd.append("path", current);
      fetch("/api/upload", { method:"POST", body: fd })
        .then(r => r.json()).then(load.bind(null, current));
    }

    // 新建文件夹
    function makeDir() {
      const name = prompt("新文件夹名称");
      if (!name) return;
      const fd = new FormData();
      fd.append("path", current);
      fd.append("name", name);
      fetch("/api/mkdir", { method:"POST", body: fd })
        .then(r => r.json()).then(load.bind(null, current));
    }

    // 删除
    function onDelete() {
      if (!ctxTarget) return;
      const path = ctxTarget;
      const fd = new FormData();
      fd.append("path", path);
      fetch("/api/delete", { method:"POST", body: fd })
        .then(r => r.json()).then(() => hideCtx(), load.bind(null, current));
    }

    // 下载
    function onDownload() {
      if (!ctxTarget) return;
      location.href = `/api/download?path=${encodeURIComponent(ctxTarget)}`;
      hideCtx();
    }

    // 打开右键菜单
    function openCtx(e, it) {
      e.preventDefault();
      ctxTarget = join(current, it.name);
      const menu = document.getElementById("ctxMenu");
      menu.style.left = e.pageX + "px";
      menu.style.top  = e.pageY + "px";
      menu.style.display = "block";
    }
    window.onclick = hideCtx;
    function hideCtx() {
      document.getElementById("ctxMenu").style.display = "none";
    }

    // 上级
    function goUp() {
      if (!current) return;
      const parts = current.split("/");
      parts.pop();
      load(parts.join("/"));
    }

    // 拼路径
    function join() {
      const parts = Array.from(arguments).filter(s=>s!=="");
      return parts.join("/").replace(/^\/+|\/+$/g,"");
    }

    // 移动
    function doMove(src, dstDir) {
      const name = src.split("/").pop();
      const dst = dstDir ? dstDir + "/" + name : name;
      fetch("/api/move", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({src, dst})
      }).then(r=>r.json()).then(()=>load(current));
    }
    function onMoveHere() {
      // “移动到此处”功能已通过拖拽实现，这里简单隐藏即可
      hideCtx();
    }

    // 初始加载
    load();
  </script>
</body>
</html>





