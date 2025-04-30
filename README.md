```markdown
# Simple_video_platform

## 视频分享平台

![License](https://img.shields.io/badge/license-BSD--2--Clause-blue.svg)
![Python](https://img.shields.io/badge/python-3.6%2B-blue)

一个简单高效的基于 Flask 开发的视频分享平台！用户可以轻松注册、登录、上传和观看视频。

## 🎯 功能特性

- ✔️ 用户注册和登录
- ✔️ 视频上传与播放
- ✔️ 用户主页展示视频列表
- ✔️ 用户间的模糊搜索功能
- ✔️ 视频删除功能

## 🚀 快速开始

### 系统要求

- Python 3.6+
- SQLite 数据库（默认集成）

### 安装步骤

1. **克隆仓库**

   ```bash
   git clone https://github.com/wangyifan349/Simple_video_platform.git
   cd Simple_video_platform
   ```

2. **安装依赖**

   使用以下命令安装项目依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. **初始化数据库**

   在首次运行应用时，需要初始化数据库：

   ```bash
   python app.py
   ```

4. **运行应用**

   启动 Flask 应用：

   ```bash
   flask run
   ```

   然后在浏览器中访问 `http://127.0.0.1:5000` 查看应用效果。

## 📂 项目结构

```plaintext
Simple_video_platform/
├── app.py                # Flask 应用主文件
├── forms.py              # Flask WTForms 表单定义
├── requirements.txt      # Python 依赖列表
├── instance/
│   └── video_share.db    # SQLite 数据库文件
├── static/               # 静态文件（CSS, 图像, JS 等）
└── templates/            # HTML Jinja2 模板
    ├── base.html         # 主模板，包含基础布局
    ├── index.html        # 首页
    ├── login.html        # 登录页
    ├── play_video.html   # 视频播放页
    ├── register.html     # 注册页
    ├── search.html       # 用户搜索页
    ├── upload.html       # 视频上传页
    └── user.html         # 用户主页
```

## 🤝 参与贡献

欢迎贡献！请 fork 本仓库并提交您的 Pull Request 以增加您的代码。

## 📜 许可证

此项目基于 BSD 2-Clause License - [查看详细内容](LICENSE)。

## 🙋‍♂️ 作者

- [Wang Yifan](https://github.com/wangyifan349)

- 邮箱: wangyifangebk@163.com 或 wangyifan1999@protonmail.com

如果您在使用过程中有任何问题或建议，请与我联系。感谢您参与并使用视频分享平台项目！
```
