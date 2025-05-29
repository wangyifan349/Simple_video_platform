import os
import re
import random
import string
from datetime import datetime
from io import BytesIO

from flask import (
    Flask, render_template_string, request, redirect, url_for, flash, session,
    send_file, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from captcha.image import ImageCaptcha
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = '请替换为你的随机密钥'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    filename = filename.strip().replace('/', '').replace('\\', '').replace('\0','')
    filename = re.sub(r'[<>:"|?*]', '', filename)
    filename = filename.replace('\n', '').replace('\r', '')
    return filename

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    videos = db.relationship('Video', backref='owner', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='video', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

image_captcha = ImageCaptcha(width=160, height=60)
def generate_captcha_img(text):
    data = image_captcha.generate(text)
    return data

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def lcs_length(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    dp = [[0]*(lb+1) for _ in range(la+1)]
    a = a.lower()
    b = b.lower()
    for i in range(1, la+1):
        for j in range(1, lb+1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] +1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[la][lb]

def build_comment_tree(comments):
    comment_map = {c.id: c for c in comments}
    roots = []
    for c in comments:
        if c.parent_id:
            parent = comment_map.get(c.parent_id)
            if parent:
                if not hasattr(parent, 'children'):
                    parent.children = []
                parent.children.append(c)
        else:
            roots.append(c)

    def sort_children(cmt):
        if hasattr(cmt, 'children'):
            cmt.children.sort(key=lambda x: x.timestamp)
            for child in cmt.children:
                sort_children(child)
        else:
            cmt.children = []
    for root in roots:
        sort_children(root)
    return roots

@app.route('/captcha')
def captcha():
    text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    session['captcha_text'] = text
    img_data = generate_captcha_img(text)
    return send_file(img_data, mimetype='image/png')

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    users = []
    if query:
        all_users = User.query.all()
        scored = []
        for u in all_users:
            score = lcs_length(query, u.username)
            if score > 0:
                scored.append((score, u))
        scored.sort(key=lambda x: x[0], reverse=True)
        users = [u for score,u in scored[:10]]
    return render_template_string(index_html, users=users, query=query)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').upper()

        if captcha_input != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))

        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template_string(register_html)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').upper()

        if captcha_input != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))

    return render_template_string(login_html)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    title = request.form.get('title', '').strip()
    file = request.files.get('file')

    if not title:
        return jsonify({'success': False, 'msg': '请输入视频标题'})
    if not file or file.filename == '':
        return jsonify({'success': False, 'msg': '请选择视频文件'})
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'msg': '只允许上传 mp4, avi, mov, mkv 视频格式'})

    filename = sanitize_filename(file.filename)
    filename = f"{current_user.id}_{random.randint(1000, 9999)}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    video = Video(filename=filename, title=title, owner=current_user)
    db.session.add(video)
    db.session.commit()

    return jsonify({'success': True, 'msg': '上传成功'})

@app.route('/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    video = Video.query.get_or_404(video_id)
    if video.owner != current_user:
        return jsonify({'success': False, 'msg': '没有权限删除该视频'})

    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], video.filename))
    except Exception as e:
        print("删除文件异常:", e)

    db.session.delete(video)
    db.session.commit()
    return jsonify({'success': True, 'msg': '删除成功'})

@app.route('/user/<int:user_id>')
def user_videos(user_id):
    user = User.query.get_or_404(user_id)
    videos = user.videos
    return render_template_string(user_videos_html, user=user, videos=videos)

@app.route('/video/<int:video_id>')
def video_player(video_id):
    video = Video.query.get_or_404(video_id)
    search_query = request.args.get('q', '').strip()

    user_videos_sorted = sorted(video.owner.videos, key=lambda v: v.id)
    current_index = next((i for i,v in enumerate(user_videos_sorted) if v.id == video_id), None)

    next_video_url = None
    if current_index is not None and current_index + 1 < len(user_videos_sorted):
        next_vid = user_videos_sorted[current_index+1]
        next_video_url = url_for('video_player', video_id=next_vid.id, q=search_query)

    comments = Comment.query.filter_by(video_id=video_id).order_by(Comment.timestamp.asc()).all()
    comment_tree = build_comment_tree(comments)

    return render_template_string(video_player_html,
                                  video=video,
                                  next_video_url=next_video_url,
                                  search_query=search_query,
                                  comment_tree=comment_tree)

@app.route('/video/<int:video_id>/comment', methods=['POST'])
@login_required
def add_comment(video_id):
    video = Video.query.get_or_404(video_id)
    content = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id')

    if not content:
        return jsonify({'success': False, 'msg': '评论内容不能为空'})

    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.video_id != video_id:
            return jsonify({'success': False, 'msg': '无效的回复评论'})

    comment = Comment(content=content,
                      user_id=current_user.id,
                      video_id=video_id,
                      parent_id=parent_id if parent_id else None)
    db.session.add(comment)
    db.session.commit()
    return jsonify({'success': True, 'msg': '评论成功'})

base_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <title>{% block title %}视频网站{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
    <style>
        body { background: #f8f9fa; }
        .navbar-brand { font-weight: bold; font-size: 1.5rem; letter-spacing: 1px; }
        .container { margin-top: 2rem; margin-bottom: 3rem; }
        video { border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
        footer { margin-top: 4rem; padding: 1rem 0; text-align: center; color: #999; font-size: 0.9rem; border-top: 1px solid #ddd; }
    </style>
    {% block css %}{% endblock %}
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-light bg-white shadow-sm sticky-top">
    <div class="container">
        <a class="navbar-brand" href="{{ url_for('index') }}">视频站</a>
        <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#navMenu"
            aria-controls="navMenu" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navMenu">
            <ul class="navbar-nav mr-auto mt-2 mt-lg-0">
                <li class="nav-item {% if request.endpoint=='index' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('index') }}">首页</a>
                </li>
                {% if current_user.is_authenticated %}
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for('user_videos', user_id=current_user.id) }}">我的视频</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link text-danger" href="{{ url_for('logout') }}">退出</a>
                </li>
                {% else %}
                <li class="nav-item {% if request.endpoint=='login' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('login') }}">登录</a>
                </li>
                <li class="nav-item {% if request.endpoint=='register' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('register') }}">注册</a>
                </li>
                {% endif %}
            </ul>
            <form class="form-inline my-2 my-lg-0" method="get" action="{{ url_for('index') }}">
                <input class="form-control mr-sm-2" type="search" name="q" placeholder="搜索用户名"
                    aria-label="搜索用户名" value="{{ query|default('') }}">
                <button class="btn btn-outline-success my-2 my-sm-0" type="submit">搜索</button>
            </form>
        </div>
    </div>
</nav>
<div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="close" data-dismiss="alert" aria-label="关闭">
                        <span aria-hidden="true">&times;</span>
                    </button>
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</div>
<footer>
    &copy; 2024 视频网站 - 仅供测试学习使用
</footer>
<script src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/popper.js@1.16.1/dist/umd/popper.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
'''

video_player_html = '''
{% extends base_html %}
{% block title %}播放：{{ video.title }} - 视频网站{% endblock %}
{% block content %}
<div class="video-container">
  <video id="player" controls autoplay playsinline style="width:100%; max-height:80vh;">
    <source src="{{ url_for('static', filename='uploads/' + video.filename) }}" type="video/mp4" />
    你的浏览器不支持 video 标签。
  </video>
  <div class="controls my-3 d-flex justify-content-between">
    <button class="btn btn-outline-secondary" onclick="goBack()">&larr; 返回搜索结果</button>
    {% if next_video_url %}
    <button class="btn btn-primary" onclick="goNext()">下一个视频 &rarr;</button>
    {% else %}
    <button class="btn btn-primary" disabled>没有下一个视频了</button>
    {% endif %}
  </div>
</div>
<div class="container mt-4" style="max-width: 700px;">
  <h4>评论区</h4>
  {% if current_user.is_authenticated %}
  <form id="commentForm" class="mb-3">
    <input type="hidden" name="parent_id" id="parent_id" value="">
    <textarea name="content" id="commentContent" class="form-control" rows="3" placeholder="写下你的评论..." required></textarea>
    <button type="submit" class="btn btn-primary mt-2">发表评论</button>
    <button type="button" id="cancelReply" class="btn btn-secondary mt-2" style="display:none;">取消回复</button>
  </form>
  {% else %}
  <p><a href="{{ url_for('login') }}">登录</a>后才能发表评论。</p>
  {% endif %}
  <div id="commentList">
    {% macro render_comment(cmt) %}
      <div class="media mb-3" style="margin-left: {{ loop.depth0 * 20 }}px;">
        <div class="media-body">
          <h6 class="mt-0">{{ cmt.author.username }} <small class="text-muted">{{ cmt.timestamp.strftime("%Y-%m-%d %H:%M") }}</small></h6>
          <p>{{ cmt.content|e }}</p>
          {% if current_user.is_authenticated %}
          <a href="javascript:;" class="reply-link" data-comment-id="{{ cmt.id }}">回复</a>
          {% endif %}
          {% if cmt.children %}
            <div class="mt-2">
              {% for child in cmt.children recursive %}
                {{ render_comment(child) }}
              {% endfor %}
            </div>
          {% endif %}
        </div>
      </div>
    {% endmacro %}
    {% if comment_tree %}
      {% for comment in comment_tree recursive %}
        {{ render_comment(comment) }}
      {% endfor %}
    {% else %}
      <p class="text-muted">暂无评论，快来抢沙发！</p>
    {% endif %}
  </div>
</div>
{% endblock %}
{% block scripts %}
{{ super() }}
<script>
function goBack() {
    if (document.referrer && document.referrer.includes(window.location.host)) {
      window.history.back();
    } else {
      let q="{{ search_query }}";
      if(q){
        window.location.href = "{{ url_for('index') }}" + "?q=" + encodeURIComponent(q);
      } else {
        window.location.href = "{{ url_for('index') }}";
      }
    }
}
function goNext() {
    {% if next_video_url %}
    window.location.href = "{{ next_video_url }}";
    {% endif %}
}
document.addEventListener('DOMContentLoaded', () => {
    const commentForm = document.getElementById('commentForm');
    const commentContent = document.getElementById('commentContent');
    const parentInput = document.getElementById('parent_id');
    const cancelReplyBtn = document.getElementById('cancelReply');
    if(commentForm){
        commentForm.addEventListener('submit', e => {
            e.preventDefault();
            let content = commentContent.value.trim();
            if(!content){
                alert('评论不能为空');
                return;
            }
            let parent_id = parentInput.value || '';
            let formData = new FormData();
            formData.append('content', content);
            formData.append('parent_id', parent_id);
            fetch('{{ url_for("add_comment", video_id=video.id) }}', {
                method: 'POST',
                body: formData,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            }).then(r => r.json())
              .then(data => {
                if(data.success){
                    alert(data.msg);
                    window.location.reload();
                } else {
                    alert(data.msg);
                }
              }).catch(() => alert('提交失败，请稍后再试'));
        });
    }
    document.getElementById('commentList').addEventListener('click', e => {
        if(e.target.classList.contains('reply-link')){
            let replyId = e.target.getAttribute('data-comment-id');
            parentInput.value = replyId;
            commentContent.focus();
            cancelReplyBtn.style.display = 'inline-block';
        }
    });
    cancelReplyBtn && cancelReplyBtn.addEventListener('click', () => {
        parentInput.value = '';
        commentContent.value = '';
        cancelReplyBtn.style.display = 'none';
    });
});
</script>
{% endblock %}
'''

@app.context_processor
def inject_base_html():
    return dict(base_html=base_html)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
