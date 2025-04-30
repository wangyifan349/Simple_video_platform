# 导入必要的库和模块
import os
import random
import string
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from forms import RegisterForm, LoginForm, UploadForm, SearchForm
from captcha.image import ImageCaptcha
# ----------------------------------------------------------------------------
# Flask应用程序设置
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # 用于会话的密钥
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_share.db'  # 数据库配置
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # 上传视频的目录
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 设置最大上传大小为100MB
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'avi', 'mov', 'mkv'}  # 允许的视频格式

# 初始化数据库和登录管理器
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 登录必需视图
# ----------------------------------------------------------------------------
# 定义用户模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    username = db.Column(db.String(150), unique=True, nullable=False)  # 用户名
    password_hash = db.Column(db.String(256), nullable=False)  # 密码哈希值
    # 建立与视频模型的关系
    videos = db.relationship('Video', backref='owner', lazy=True)

    # 设置密码并进行哈希加密
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # 验证输入的密码是否正确
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 定义视频模型
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    filename = db.Column(db.String(200), nullable=False)  # 视频文件名
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 用户模型的外键
# ----------------------------------------------------------------------------
# 用户加载函数，给flask-login用的
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 检查上传文件的扩展名是否合规
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# 生成随机验证码文字
def random_captcha_text(length=5):
    choices = string.ascii_uppercase + string.digits
    return ''.join(random.choices(choices, k=length))
# ----------------------------------------------------------------------------
# 生成并返回验证码图片的路由
@app.route('/captcha')
def get_captcha():
    text = random_captcha_text()
    session['captcha_text'] = text
    image = ImageCaptcha(width=160, height=60)
    data = image.generate(text)
    return send_file(data, mimetype='image/png')
# ----------------------------------------------------------------------------
# 计算最长公共子序列的长度
def lcs_length(s1, s2):
    m, n = len(s1), len(s2)
    # 初始化二维DP表
    dp = []
    for i in range(m + 1):
        dp.append([0] * (n + 1))
    
    # 填充DP表
    for i in range(m):
        for j in range(n):
            if s1[i].lower() == s2[j].lower():
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
    
    return dp[m][n]
# ----------------------------------------------------------------------------
# 网站首页
@app.route('/')
def index():
    return render_template('index.html')
# 用户注册
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.captcha.data.upper() != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=form.username.data).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=form.username.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)
# 用户登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.captcha.data.upper() != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
    return render_template('login.html', form=form)
# 用户登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出', 'info')
    return redirect(url_for('index'))
# -------------------------------------------------------------------------
# 视频上传功能
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        file = form.video.data
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 确保上传目录存在
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            # 保存视频时加上用户名以防重复
            save_filename = f"{current_user.username}_{filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], save_filename)
            file.save(save_path)
            video = Video(filename=save_path, owner=current_user)
            db.session.add(video)
            db.session.commit()
            flash('视频上传成功！', 'success')
            return redirect(url_for('user_profile', username=current_user.username))
        else:
            flash('不支持的视频格式', 'danger')
    return render_template('upload.html', form=form)
# 用户主页
@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    videos = user.videos
    return render_template('user.html', user=user, videos=videos)
# 视频播放
@app.route('/video/<int:video_id>')
def play_video(video_id):
    video = Video.query.get_or_404(video_id)
    return render_template('play_video.html', video=video)
# 视频删除功能
@app.route('/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    # 查询要删除的视频
    video = Video.query.get_or_404(video_id
    # 确保当前用户拥有该视频
    if video.user_id != current_user.id:
        flash('您无权删除此视频', 'error')
        return jsonify({'message': 'Unauthorized'}), 403
    try:
        # 从数据库中删除视频
        db.session.delete(video)
        db.session.commit()
        return jsonify({'message': '视频删除成功'}), 200
    except Exception as e:
        # 捕获删除过程中的错误
        db.session.rollback()
        return jsonify({'message': '删除视频时出现错误', 'error': str(e)}), 500
# ----------------------------------------------------------------------------
# 用户搜索功能
@app.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    users = []  # 存储搜索结果的用户列表
    if form.validate_on_submit():
        keyword = form.keyword.data.strip()
        all_users = User.query.all()  # 查询所有用户
        scored_users = []  # 用于记录匹配得分的用户
        for user in all_users:
            score = lcs_length(keyword, user.username)  # 计算用户名与关键词的匹配程度
            if score > 0:
                scored_users.append((score, user))  # 将匹配得分和用户对象存入列表
        # 按照得分从高到低排序
        scored_users.sort(key=lambda x: x[0], reverse=True)
        # 提取前20个高分用户
        for scored_user in scored_users[:20]:
            users.append(scored_user[1])
    return render_template('search.html', form=form, users=users)
# --------------------------------------------------------------------------
# 应用程序的主入口
if __name__ == '__main__':
    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # 创建数据库表
    with app.app_context():
        db.create_all()
    # 启动Flask应用
    app.run(debug=False)
