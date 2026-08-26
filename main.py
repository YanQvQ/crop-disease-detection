# ============================================
# 农作物病害识别系统 - 主程序入口
# @Author : 张炎 (YanQvQ)
# @GitHub : https://github.com/YanQvQ
# @Time   : 2026-03-12
# @File   : main.py
# ============================================
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, decode_token
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from ultralytics import YOLO
import cv2
import requests
import datetime
import uuid
import time
import threading
import subprocess
import logging
import sys
import os
import re
import mimetypes
import socket
import ipaddress
import json
import shutil
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
try:
    from dotenv import load_dotenv
    load_dotenv()  # 加载项目根目录下的 .env 文件（若存在）
except Exception:
    pass  # python-dotenv 未安装时保持原行为，使用系统环境变量

# ----- 日志级别（支持 .env / 系统环境变量 LOG_LEVEL：DEBUG/INFO/WARNING/ERROR，默认 INFO）-----
_log_level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
_log_level_map = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
                  'WARNING': logging.WARNING, 'WARN': logging.WARNING,
                  'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
LOG_LEVEL = _log_level_map.get(_log_level_name, logging.INFO)

# force=True 确保即使其他模块已提前初始化 root logger，此处配置仍会生效（Python 3.8+）
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')
    ],
    force=True,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# 默认 SECRET_KEY 仅用于开发；生产部署必须通过环境变量 SECRET_KEY 覆盖，否则启动时告警。
_DEFAULT_SECRET_KEY = 'CHANGE_ME_IN_PRODUCTION_USE_openssl_rand_48bytes_OR_python_secrets_token_urlsafe_48'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', _DEFAULT_SECRET_KEY)
if app.config['SECRET_KEY'] == _DEFAULT_SECRET_KEY:
    logger.warning('=' * 66)
    logger.warning('生产安全警告：正在使用默认 SECRET_KEY！上线前必须设置环境变量 SECRET_KEY。')
    logger.warning('生成方式：python -c "import secrets; print(secrets.token_urlsafe(48))"')
    logger.warning('=' * 66)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///cropdisease.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
try:
    _jwt_days = int(os.environ.get('JWT_EXPIRE_DAYS', '7'))
except ValueError:
    _jwt_days = 7
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(days=_jwt_days)
try:
    _max_mb = int(os.environ.get('MAX_CONTENT_MB', '100'))
except ValueError:
    _max_mb = 100
app.config['MAX_CONTENT_LENGTH'] = _max_mb * 1024 * 1024

# ----- DEBUG 模式：独立 DEBUG 变量优先级最高，其次 FLASK_ENV=development，默认关闭（生产安全）-----
_debug_env = os.environ.get('DEBUG', '').strip().lower()
if _debug_env in ('1', 'true', 'yes', 'on'):
    app.config['DEBUG'] = True
elif _debug_env in ('0', 'false', 'no', 'off'):
    app.config['DEBUG'] = False
else:
    _flask_env = os.environ.get('FLASK_ENV', 'production').lower()
    app.config['DEBUG'] = _flask_env == 'development'
app.config['TEMPLATES_AUTO_RELOAD'] = True

current_dir = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(current_dir, 'files')
app.config['STATIC_FOLDER'] = os.path.join(current_dir, 'static')
app.config['TEMPLATES_FOLDER'] = os.path.join(current_dir, 'templates')

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

db = SQLAlchemy(app)
jwt = JWTManager(app)

# ----- CORS / WebSocket 来源白名单：默认仅允许本机开发来源，生产通过 CORS_ALLOWED_ORIGINS 配置 -----
_cors_origins = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5000,http://127.0.0.1:5000'
)
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
CORS(app, resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS}})
socketio = SocketIO(app, cors_allowed_origins=CORS_ALLOWED_ORIGINS)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('./runs', exist_ok=True)
os.makedirs('./weights', exist_ok=True)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), default='')
    sex = db.Column(db.String(10), default='男')
    email = db.Column(db.String(255), default='')
    tel = db.Column(db.String(20), default='')
    role = db.Column(db.String(20), default='common')
    avatar = db.Column(db.String(500), default='')
    time = db.Column(db.DateTime, default=datetime.datetime.now)


class ImgRecords(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    input_img = db.Column(db.String(500))
    out_img = db.Column(db.String(500))
    confidence = db.Column(db.String(500))
    all_time = db.Column(db.String(50))
    conf = db.Column(db.String(20))
    weight = db.Column(db.String(255))
    username = db.Column(db.String(255))
    start_time = db.Column(db.String(50))
    label = db.Column(db.String(500))
    kind = db.Column(db.String(50))


class VideoRecords(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    input_video = db.Column(db.String(500))
    out_video = db.Column(db.String(500))
    username = db.Column(db.String(255))
    start_time = db.Column(db.String(50))
    conf = db.Column(db.String(20))
    weight = db.Column(db.String(255))
    kind = db.Column(db.String(50))


class CameraRecords(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    weight = db.Column(db.String(255))
    conf = db.Column(db.String(20))
    username = db.Column(db.String(255))
    start_time = db.Column(db.String(50))
    out_video = db.Column(db.String(500))
    kind = db.Column(db.String(50))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(255))
    type = db.Column(db.String(20), default='info')
    title = db.Column(db.String(255))
    content = db.Column(db.String(500))
    time = db.Column(db.String(50))
    read = db.Column(db.Boolean, default=False)


def add_notification(username, type_, title, content):
    """写入一条用户通知（检测完成等真实事件）。"""
    try:
        n = Notification(
            username=username,
            type=type_,
            title=title,
            content=content,
            time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            read=False
        )
        db.session.add(n)
        db.session.commit()
    except Exception as e:
        logger.error(f'写入通知失败: {str(e)}')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== 模型进程级缓存 ====================
# YOLO 权重动辄数百 MB，每次请求重新加载开销极大。
# 按权重路径缓存已加载的模型实例，并为每个模型配一把推理锁，避免并发推理互相覆盖状态。
_model_cache = {}
_model_cache_lock = threading.Lock()
_model_infer_locks = {}


def get_model(weight_path):
    """返回 (model, infer_lock)：首次加载并缓存，之后复用；infer_lock 用于序列化对该模型的推理。"""
    with _model_cache_lock:
        model = _model_cache.get(weight_path)
        if model is None:
            model = YOLO(weight_path)
            _model_cache[weight_path] = model
            logger.info(f'模型加载并缓存: {weight_path}')
        lock = _model_infer_locks.get(weight_path)
        if lock is None:
            lock = threading.Lock()
            _model_infer_locks[weight_path] = lock
    return model, lock


def clear_model_cache(weight_path=None):
    """删除/替换模型时清空对应缓存，避免引用已删除的权重文件。"""
    with _model_cache_lock:
        if weight_path:
            _model_cache.pop(weight_path, None)
            _model_infer_locks.pop(weight_path, None)
        else:
            _model_cache.clear()
            _model_infer_locks.clear()
    logger.info(f'模型缓存已清理: {weight_path or "全部"}')


# ==================== 推理并发限流 ====================
# 推理是 CPU 密集操作，且同一权重由 infer_lock 串行执行。这里再加一层全局信号量，
# 限制同时进行的推理任务数，超出立即返回 429，避免大量请求排队阻塞请求线程/耗尽 CPU。
try:
    INFERENCE_MAX_CONCURRENT = max(1, int(os.environ.get('INFERENCE_MAX_CONCURRENT', '3')))
except ValueError:
    INFERENCE_MAX_CONCURRENT = 3
_infer_semaphore = threading.BoundedSemaphore(INFERENCE_MAX_CONCURRENT)


def acquire_infer_slot():
    """尝试获取一个推理名额（不阻塞），失败返回 False。"""
    return _infer_semaphore.acquire(blocking=False)


def release_infer_slot():
    """释放推理名额。"""
    _infer_semaphore.release()


def is_safe_url(url):
    """SSRF 防护：仅允许 http/https，且解析后的目标 IP 不是内网/环回/链路本地/保留地址。"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.hostname
        if not host:
            return False
        # 解析 DNS 获取所有地址，任一地址不安全即拒绝
        try:
            infos = socket.getaddrinfo(host, None)
        except (socket.gaierror, OSError):
            return False
        if not infos:
            return False
        for info in infos:
            try:
                addr = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
                return False
        return True
    except Exception:
        return False


def is_local_url(url):
    """判断 URL 是否指向本站（host 与当前请求一致）。本站已鉴权上传的文件跳过 SSRF 校验。"""
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        req_host = request.host
        if ':' in req_host:
            req_host, req_port = req_host.split(':', 1)
            req_port = int(req_port)
        else:
            req_port = 80
        if parsed.hostname.lower() != req_host.lower():
            return False
        return parsed.port in (None, req_port)
    except Exception:
        return False


def download_input(url, dest_path, timeout=30):
    """将输入文件写入本地临时文件。
    本站已鉴权上传的文件直接从磁盘复制（内部不走 HTTP，避免 /files 鉴权导致的 401）；
    外部地址仅允许通过 SSRF 校验后的 http/https，且禁止跟随重定向。"""
    if is_local_url(url):
        filename = os.path.basename(urlparse(url).path)
        src = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(src):
            raise FileNotFoundError(f'本站文件不存在: {filename}')
        shutil.copyfile(src, dest_path)
        return
    with requests.get(url, stream=True, timeout=timeout, allow_redirects=False) as response:
        if response.status_code >= 300:
            raise RuntimeError('不允许重定向')
        response.raise_for_status()
        with open(dest_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)


def get_base_url():
    return f"{request.scheme}://{request.host}"


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            name='管理员',
            sex='男',
            email='admin@example.com',
            tel='13800138000',
            role='admin',
            avatar='',
            time=datetime.datetime.now()
        )
        db.session.add(admin)
        db.session.commit()
        logger.info("默认管理员账号已创建: admin / admin123")

recording = False
camera_thread = None


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/')
def index():
    return render_template('login.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/img-predict')
def img_predict_page():
    return render_template('img_predict.html')


@app.route('/video-predict')
def video_predict_page():
    return render_template('video_predict.html')


@app.route('/camera-predict')
def camera_predict_page():
    return render_template('camera_predict.html')


@app.route('/img-records')
def img_records_page():
    return render_template('img_records.html')


@app.route('/video-records')
def video_records_page():
    return render_template('video_records.html')


@app.route('/camera-records')
def camera_records_page():
    return render_template('camera_records.html')


@app.route('/user-manage')
def user_manage_page():
    return render_template('user_manage.html')


@app.route('/personal')
def personal_page():
    return render_template('personal.html')


@app.route('/settings')
def settings_page():
    return render_template('system_settings.html')


# ==================== 登录失败限流 ====================
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15
_login_attempts = {}
_login_attempts_lock = threading.Lock()


def client_ip():
    """获取客户端 IP（考虑反向代理的 X-Forwarded-For）。"""
    ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    return ip or request.remote_addr or 'unknown'


def is_login_locked(username):
    """返回 (是否锁定, 剩余锁定分钟数)。"""
    key = (client_ip(), username)
    with _login_attempts_lock:
        rec = _login_attempts.get(key)
        if not rec:
            return False, 0
        now = time.time()
        if rec.get('lock_until') and now < rec['lock_until']:
            remaining = int((rec['lock_until'] - now) / 60) + 1
            return True, remaining
        if rec.get('lock_until') and now >= rec['lock_until']:
            _login_attempts.pop(key, None)
        return False, 0


def record_login_failure(username):
    """记录一次失败，返回剩余可尝试次数；达到阈值后锁定。"""
    key = (client_ip(), username)
    with _login_attempts_lock:
        rec = _login_attempts.get(key, {'count': 0, 'lock_until': 0})
        if rec.get('lock_until') and time.time() >= rec['lock_until']:
            rec = {'count': 0, 'lock_until': 0}
        rec['count'] += 1
        remaining = LOGIN_MAX_ATTEMPTS - rec['count']
        if rec['count'] >= LOGIN_MAX_ATTEMPTS:
            rec['lock_until'] = time.time() + LOGIN_LOCK_MINUTES * 60
            rec['count'] = 0
            remaining = 0
        _login_attempts[key] = rec
        return max(remaining, 0)


def clear_login_attempts(username):
    """登录成功后清除该 IP + 用户名 的失败记录。"""
    key = (client_ip(), username)
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


@app.route('/api/login', methods=['POST'])
def login():
    # 登录失败限流：同一 IP + 用户名连续失败 LOGIN_MAX_ATTEMPTS 次后锁定 LOGIN_LOCK_MINUTES 分钟
    username = (request.get_json(silent=True) or {}).get('username', '')
    if username:
        locked, remaining = is_login_locked(username.strip())
        if locked:
            logger.warning(f'登录被限流: 用户={username}, IP={client_ip()}')
            return jsonify({'code': 1, 'message': f'登录失败次数过多，请 {remaining} 分钟后再试'})
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 1, 'message': '请求数据格式错误'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'code': 1, 'message': '用户名和密码不能为空'})

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            clear_login_attempts(username)
            access_token = create_access_token(identity=username)
            logger.info(f'用户登录成功: {username}')
            return jsonify({
                'code': 0,
                'message': '登录成功',
                'data': {'token': access_token, 'role': user.role}
            })
        else:
            remaining = record_login_failure(username)
            logger.warning(f'用户登录失败: {username}, 剩余尝试次数: {remaining}')
            return jsonify({'code': 1, 'message': '用户名或密码错误'})
    except Exception as e:
        logger.error(f'登录异常: {str(e)}', exc_info=True)
        return jsonify({'code': 1, 'message': '服务器内部错误'}), 500


@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 1, 'message': '请求数据格式错误'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or len(username) < 3 or len(username) > 50:
            return jsonify({'code': 1, 'message': '用户名长度必须在3-50个字符之间'})
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', username):
            return jsonify({'code': 1, 'message': '用户名只能包含字母、数字、下划线和中文'})

        if not password or len(password) < 6:
            return jsonify({'code': 1, 'message': '密码长度至少6个字符'})
        if len(password) > 100:
            return jsonify({'code': 1, 'message': '密码长度不能超过100个字符'})

        if User.query.filter_by(username=username).first():
            return jsonify({'code': 1, 'message': '用户名已存在'})

        new_user = User(
            username=username,
            password=generate_password_hash(password),
            name='新用户',
            sex='男',
            email='',
            tel='',
            role='common',
            avatar='',
            time=datetime.datetime.now()
        )
        db.session.add(new_user)
        db.session.commit()
        logger.info(f'用户注册成功: {username}')
        return jsonify({'code': 0, 'message': '注册成功'})
    except Exception as e:
        logger.error(f'注册异常: {str(e)}', exc_info=True)
        return jsonify({'code': 1, 'message': '服务器内部错误'}), 500


@app.route('/api/file_names', methods=['GET'])
def file_names():
    try:
        weight_items = [
            {'value': name, 'label': name}
            for name in os.listdir('./weights')
            if os.path.isfile(os.path.join('./weights', name)) and name.endswith('.pt')
        ]
        return jsonify({'weight_items': weight_items})
    except Exception as e:
        logger.error(f'获取模型列表失败: {str(e)}')
        return jsonify({'weight_items': []})


@app.route('/api/predictImg', methods=['POST'])
@jwt_required()
def predict_img():
    data = request.get_json()
    if not data:
        return jsonify({'status': 400, 'message': '请求数据格式错误'}), 400

    current_user = get_jwt_identity()
    img_path = f"./temp_{uuid.uuid4()}.jpg"

    # SSRF 防护：校验下载地址（本站已上传文件放行，外部地址必须安全）
    if not (is_local_url(data.get('inputImg', '')) or is_safe_url(data.get('inputImg', ''))):
        return jsonify({'status': 400, 'message': '非法的图片地址'})

    try:
        # 本站文件直接读盘，外部地址禁止跟随重定向（防止绕过 SSRF 校验）
        download_input(data['inputImg'], img_path, timeout=30)
    except Exception as e:
        logger.error(f'下载图片失败: {str(e)}')
        return jsonify({'status': 400, 'message': f'下载图片失败: {str(e)}'})

    slot_acquired = False
    try:
        weight = data.get('weight', '')
        if not weight or '..' in weight or '/' in weight:
            return jsonify({'status': 400, 'message': '无效的模型文件'})

        weight_path = f'./weights/{weight}'
        if not os.path.exists(weight_path):
            return jsonify({'status': 400, 'message': '模型文件不存在'})

        # 推理并发限流：名额不足直接返回 429，避免大量请求排队阻塞
        if not acquire_infer_slot():
            return jsonify({'status': 429, 'message': '系统繁忙，请稍后再试'}), 429
        slot_acquired = True

        start_time = time.time()
        model, infer_lock = get_model(weight_path)
        conf = float(data.get('conf', 0.5))
        with infer_lock:
            results = model(img_path, conf=conf)
        end_time = time.time()

        result_path = f'./runs/result_{uuid.uuid4()}.jpg'
        results[0].save(result_path)

        filename = str(uuid.uuid4()) + '_result.jpg'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.rename(result_path, filepath)
        uploaded_url = f'{get_base_url()}/files/{filename}'

        all_time = f"{(end_time - start_time):.2f}秒"

        confidence_list = [f"{conf_val*100:.2f}%" for conf_val in results[0].boxes.conf.tolist()]
        label_list = [results[0].names.get(int(cls), '未知') for cls in results[0].boxes.cls.tolist()]

        new_record = ImgRecords(
            input_img=data["inputImg"],
            out_img=uploaded_url,
            confidence=json.dumps(confidence_list, ensure_ascii=False),
            all_time=all_time,
            conf=str(conf),
            weight=weight,
            username=current_user,
            start_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            label=json.dumps(label_list, ensure_ascii=False),
            kind=data.get("kind", "")
        )
        db.session.add(new_record)
        db.session.commit()
        add_notification(current_user, 'success', '图片检测完成', f'模型 {weight} 检测完成，耗时 {all_time}')

        logger.info(f'图片预测完成: 用户={current_user}, 模型={weight}')

        return jsonify({
            'status': 200,
            'message': '预测成功',
            'outImg': uploaded_url,
            'allTime': all_time,
            'confidence': json.dumps(confidence_list, ensure_ascii=False),
            'label': json.dumps(label_list, ensure_ascii=False)
        })
    except Exception as e:
        logger.error(f'图片预测失败: {str(e)}', exc_info=True)
        return jsonify({'status': 400, 'message': f'预测失败: {str(e)}'})
    finally:
        if slot_acquired:
            release_infer_slot()
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except:
                pass


@app.route('/api/predictVideo', methods=['POST'])
@jwt_required()
def predict_video():
    data = request.get_json()
    if not data:
        return jsonify({'status': 400, 'message': '请求数据格式错误'}), 400

    current_user = get_jwt_identity()
    video_path = f"./temp_{uuid.uuid4()}.mp4"

    # SSRF 防护：校验下载地址（本站已上传文件放行，外部地址必须安全）
    if not (is_local_url(data.get('inputVideo', '')) or is_safe_url(data.get('inputVideo', ''))):
        return jsonify({'status': 400, 'message': '非法的视频地址'})

    try:
        # 本站文件直接读盘，外部地址禁止跟随重定向（防止绕过 SSRF 校验）
        download_input(data['inputVideo'], video_path, timeout=60)
    except Exception as e:
        logger.error(f'下载视频失败: {str(e)}')
        return jsonify({'status': 400, 'message': f'下载视频失败: {str(e)}'})

    slot_acquired = False
    try:
        weight = data.get('weight', '')
        if not weight or '..' in weight or '/' in weight:
            return jsonify({'status': 400, 'message': '无效的模型文件'})

        weight_path = f'./weights/{weight}'
        if not os.path.exists(weight_path):
            return jsonify({'status': 400, 'message': '模型文件不存在'})

        # 推理并发限流：名额不足直接返回 429，避免大量请求排队阻塞
        if not acquire_infer_slot():
            return jsonify({'status': 429, 'message': '系统繁忙，请稍后再试'}), 429
        slot_acquired = True

        start_time = time.time()
        model, infer_lock = get_model(weight_path)

        output_path = f'./runs/output_{uuid.uuid4()}.mp4'
        cap = cv2.VideoCapture(video_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 1

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # 抽帧控制：目标推理帧率不超过 10fps，长视频避免全帧推理阻塞请求线程。
        # 未推理的帧复用上一帧标注结果，保证视频时长与标注连续性不变。
        step = max(1, round(fps / 10))
        conf = float(data.get('conf', 0.5))
        frame_idx = 0
        annotated_frame = None
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                with infer_lock:
                    results = model(frame, conf=conf)
                annotated_frame = results[0].plot()
            out.write(annotated_frame if annotated_frame is not None else frame)
            frame_idx += 1

        cap.release()
        out.release()
        end_time = time.time()

        h264_output_path = f'./runs/h264_{uuid.uuid4()}.mp4'
        try:
            subprocess.run([
                'ffmpeg', '-i', output_path,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-y',
                h264_output_path
            ], check=True, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                os.remove(output_path)
            output_path = h264_output_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f'ffmpeg转换失败: {str(e)}，使用原始视频')

        filename = str(uuid.uuid4()) + '_result.mp4'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.rename(output_path, filepath)
        uploaded_url = f'{get_base_url()}/files/{filename}'

        new_record = VideoRecords(
            input_video=data["inputVideo"],
            out_video=uploaded_url,
            username=current_user,
            start_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            conf=str(conf),
            weight=weight,
            kind=data.get("kind", "")
        )
        db.session.add(new_record)
        db.session.commit()
        add_notification(current_user, 'success', '视频检测完成', f'模型 {weight} 检测完成，耗时 {end_time - start_time:.2f} 秒')

        logger.info(f'视频预测完成: 用户={current_user}, 模型={weight}')

        return jsonify({
            'status': 200,
            'message': '预测成功',
            'outVideo': uploaded_url
        })
    except Exception as e:
        logger.error(f'视频预测失败: {str(e)}', exc_info=True)
        return jsonify({'status': 400, 'message': f'预测失败: {str(e)}'})
    finally:
        if slot_acquired:
            release_infer_slot()
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass


@app.route('/api/startCamera', methods=['POST'])
@jwt_required()
def start_camera():
    global recording, camera_thread
    data = request.get_json()
    if not data:
        return jsonify({'status': 400, 'message': '请求数据格式错误'}), 400

    current_user = get_jwt_identity()
    # 可选：客户端 WebSocket 连接 ID（仅向该连接推送帧，避免全局广播）
    socket_id = data.get('socket_id', '') or ''

    if recording:
        return jsonify({'status': 400, 'message': '摄像头已在运行中'})

    weight = data.get('weight', '')
    if not weight or '..' in weight or '/' in weight:
        return jsonify({'status': 400, 'message': '无效的模型文件'})

    weight_path = f'./weights/{weight}'
    if not os.path.exists(weight_path):
        return jsonify({'status': 400, 'message': '模型文件不存在'})

    recording = True
    output_path = f'./runs/camera_{uuid.uuid4()}.mp4'
    conf = float(data.get('conf', 0.5))
    kind = data.get('kind', '')

    def camera_predict():
        global recording
        nonlocal output_path

        # 仅向发起者的 WebSocket 连接推送，未提供 socket_id 时不推送（前端本地显示，无需服务器推帧）
        def notify(event, payload):
            if socket_id:
                socketio.emit(event, payload, room=socket_id)

        try:
            logger.info(f'开始加载模型: {weight}')
            model, infer_lock = get_model(weight_path)
            logger.info('模型加载完成')

            logger.info('尝试打开摄像头...')
            cap = cv2.VideoCapture(0)

            if not cap.isOpened():
                logger.error('摄像头打开失败')
                recording = False
                notify('error', {'message': '摄像头打开失败，请检查摄像头是否连接'})
                return

            logger.info('摄像头打开成功')
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = 20
            logger.info(f'摄像头分辨率: {width}x{height}, FPS: {fps}')

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            logger.info('开始摄像头预测循环...')
            frame_count = 0
            while recording:
                ret, frame = cap.read()
                if not ret:
                    logger.error('读取帧失败')
                    break
                with infer_lock:
                    results = model(frame, conf=conf)
                annotated_frame = results[0].plot()
                out.write(annotated_frame)

                ret, buffer = cv2.imencode('.jpg', annotated_frame)
                frame_base64 = buffer.tobytes()
                notify('frame', {'data': frame_base64})
                frame_count += 1

                if frame_count % 100 == 0:
                    logger.info(f'已处理 {frame_count} 帧')

            logger.info(f'摄像头预测结束，共处理 {frame_count} 帧')

            cap.release()
            out.release()

            h264_output_path = f'./runs/h264_camera_{uuid.uuid4()}.mp4'
            try:
                subprocess.run([
                    'ffmpeg', '-i', output_path,
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-y',
                    h264_output_path
                ], check=True, capture_output=True, timeout=300)

                if os.path.exists(output_path):
                    os.remove(output_path)
                output_path = h264_output_path
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.error(f'ffmpeg转换失败: {str(e)}')

            filename = str(uuid.uuid4()) + '_camera.mp4'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.rename(output_path, filepath)
            uploaded_url = f'{get_base_url()}/files/{filename}'

            with app.app_context():
                new_record = CameraRecords(
                    weight=weight,
                    conf=str(conf),
                    username=current_user,
                    start_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    out_video=uploaded_url,
                    kind=kind
                )
                db.session.add(new_record)
                db.session.commit()
                add_notification(current_user, 'success', '摄像头检测完成', f'模型 {weight} 检测完成，视频已保存至记录')
                logger.info('摄像头预测记录已保存到数据库')
        except Exception as e:
            logger.error(f'摄像头预测失败: {str(e)}', exc_info=True)
            recording = False
            notify('error', {'message': f'预测失败: {str(e)}'})

    camera_thread = threading.Thread(target=camera_predict, daemon=True)
    camera_thread.start()

    logger.info(f'摄像头预测线程已启动，用户: {current_user}')
    return jsonify({'status': 200, 'message': '摄像头预测已开始'})


@app.route('/api/stopCamera', methods=['POST'])
@jwt_required()
def stop_camera():
    global recording
    recording = False
    logger.info('摄像头预测已停止')
    return jsonify({'status': 200, 'message': '摄像头预测已停止'})


@app.route('/api/imgRecords', methods=['GET'])
@jwt_required()
def get_img_records():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if user and user.role == 'admin':
            records = ImgRecords.query.order_by(ImgRecords.id.desc()).all()
        else:
            records = ImgRecords.query.filter_by(username=current_user).order_by(ImgRecords.id.desc()).all()

        record_list = []
        for record in records:
            record_list.append({
                'id': record.id,
                'input_img': record.input_img,
                'out_img': record.out_img,
                'confidence': record.confidence,
                'all_time': record.all_time,
                'conf': record.conf,
                'weight': record.weight,
                'username': record.username,
                'start_time': record.start_time,
                'label': record.label,
                'kind': record.kind
            })
        return jsonify({'code': 0, 'data': record_list})
    except Exception as e:
        logger.error(f'获取图片记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取记录失败'}), 500


@app.route('/api/videoRecords', methods=['GET'])
@jwt_required()
def get_video_records():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if user and user.role == 'admin':
            records = VideoRecords.query.order_by(VideoRecords.id.desc()).all()
        else:
            records = VideoRecords.query.filter_by(username=current_user).order_by(VideoRecords.id.desc()).all()

        record_list = []
        for record in records:
            record_list.append({
                'id': record.id,
                'input_video': record.input_video,
                'out_video': record.out_video,
                'username': record.username,
                'start_time': record.start_time,
                'conf': record.conf,
                'weight': record.weight,
                'kind': record.kind
            })
        return jsonify({'code': 0, 'data': record_list})
    except Exception as e:
        logger.error(f'获取视频记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取记录失败'}), 500


@app.route('/api/cameraRecords', methods=['GET'])
@jwt_required()
def get_camera_records():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if user and user.role == 'admin':
            records = CameraRecords.query.order_by(CameraRecords.id.desc()).all()
        else:
            records = CameraRecords.query.filter_by(username=current_user).order_by(CameraRecords.id.desc()).all()

        record_list = []
        for record in records:
            record_list.append({
                'id': record.id,
                'weight': record.weight,
                'conf': record.conf,
                'username': record.username,
                'start_time': record.start_time,
                'out_video': record.out_video,
                'kind': record.kind
            })
        return jsonify({'code': 0, 'data': record_list})
    except Exception as e:
        logger.error(f'获取摄像头记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取记录失败'}), 500


@app.route('/api/user', methods=['GET'])
@jwt_required()
def get_users():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if not user or user.role != 'admin':
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        users = User.query.all()
        user_list = []
        for u in users:
            user_list.append({
                'id': u.id,
                'username': u.username,
                'name': u.name,
                'sex': u.sex,
                'email': u.email,
                'tel': u.tel,
                'role': u.role,
                'avatar': u.avatar,
                'create_time': u.time.strftime('%Y-%m-%d %H:%M:%S') if u.time else ''
            })
        return jsonify({'code': 0, 'data': user_list})
    except Exception as e:
        logger.error(f'获取用户列表失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取用户列表失败'}), 500


@app.route('/api/user', methods=['POST'])
@jwt_required()
def create_user_by_admin():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if not user or user.role != 'admin':
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'code': 1, 'message': '请求数据格式错误'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        role = data.get('role', 'common')
        sex = data.get('sex', '男')
        email = data.get('email', '').strip()
        tel = data.get('tel', '').strip()

        if not username or len(username) < 3 or len(username) > 50:
            return jsonify({'code': 1, 'message': '用户名长度必须在3-50个字符之间'})
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', username):
            return jsonify({'code': 1, 'message': '用户名只能包含字母、数字、下划线和中文'})
        if not password or len(password) < 6:
            return jsonify({'code': 1, 'message': '密码长度至少6个字符'})
        if len(password) > 100:
            return jsonify({'code': 1, 'message': '密码长度不能超过100个字符'})
        if role not in ['admin', 'common', 'user']:
            return jsonify({'code': 1, 'message': '角色无效'})
        if sex and sex not in ['男', '女']:
            return jsonify({'code': 1, 'message': '性别无效'})
        if email and len(email) > 255:
            return jsonify({'code': 1, 'message': '邮箱长度不能超过255个字符'})
        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({'code': 1, 'message': '邮箱格式不正确'})
        if tel and len(tel) > 20:
            return jsonify({'code': 1, 'message': '电话号码长度不能超过20个字符'})
        if tel and not re.match(r'^1[3-9]\d{9}$', tel):
            return jsonify({'code': 1, 'message': '电话号码格式不正确'})

        if User.query.filter_by(username=username).first():
            return jsonify({'code': 1, 'message': '用户名已存在'})

        real_role = 'admin' if role == 'admin' else 'common'
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            name=name if name else username,
            sex=sex,
            email=email,
            tel=tel,
            role=real_role,
            avatar='',
            time=datetime.datetime.now()
        )
        db.session.add(new_user)
        db.session.commit()
        logger.info(f'管理员创建用户: {username}, 角色: {real_role}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '用户创建成功', 'data': {'id': new_user.id}})
    except Exception as e:
        logger.error(f'创建用户失败: {str(e)}', exc_info=True)
        return jsonify({'code': 1, 'message': '创建失败'}), 500


@app.route('/api/user/<username>', methods=['GET'])
@jwt_required()
def get_user(username):
    try:
        # 权限校验：仅管理员可查看任意用户，普通用户只能查看自己
        current_user = get_jwt_identity()
        me = User.query.filter_by(username=current_user).first()
        if not me or (me.role != 'admin' and current_user != username):
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        user = User.query.filter_by(username=username).first()
        if user:
            return jsonify({'code': 0, 'data': {
                'id': user.id,
                'username': user.username,
                'name': user.name,
                'sex': user.sex,
                'email': user.email,
                'tel': user.tel,
                'role': user.role,
                'avatar': user.avatar
            }})
        else:
            return jsonify({'code': 1, 'message': '用户不存在'})
    except Exception as e:
        logger.error(f'获取用户信息失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取用户信息失败'}), 500


@app.route('/api/user/me', methods=['GET'])
@jwt_required()
def get_current_user():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()
        if user:
            profile_complete = bool(
                user.name and user.name.strip() and
                user.sex and user.sex.strip() and
                user.email and user.email.strip() and
                user.tel and user.tel.strip()
            )
            return jsonify({'code': 0, 'data': {
                'id': user.id,
                'username': user.username,
                'name': user.name,
                'sex': user.sex,
                'email': user.email,
                'tel': user.tel,
                'role': user.role,
                'avatar': user.avatar,
                'profile_complete': profile_complete
            }})
        else:
            return jsonify({'code': 1, 'message': '用户不存在'})
    except Exception as e:
        logger.error(f'获取当前用户信息失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取用户信息失败'}), 500


@app.route('/api/user/update', methods=['POST'])
@jwt_required()
def update_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 1, 'message': '请求数据格式错误'}), 400

        current_user = get_jwt_identity()
        target_username = data.get('username', '')

        if target_username != current_user:
            admin_user = User.query.filter_by(username=current_user).first()
            if not admin_user or admin_user.role != 'admin':
                return jsonify({'code': 1, 'message': '权限不足'}), 403

        user = User.query.filter_by(username=target_username).first()
        if not user:
            return jsonify({'code': 1, 'message': '用户不存在'})

        if 'name' in data:
            if len(data['name']) > 50:
                return jsonify({'code': 1, 'message': '姓名长度不能超过50个字符'})
            user.name = data['name']

        if 'sex' in data:
            if data['sex'] not in ['男', '女']:
                return jsonify({'code': 1, 'message': '性别无效'})
            user.sex = data['sex']

        if 'email' in data:
            email = data['email']
            if email:
                if len(email) > 255:
                    return jsonify({'code': 1, 'message': '邮箱长度不能超过255个字符'})
                if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                    return jsonify({'code': 1, 'message': '邮箱格式不正确'})
            user.email = email

        if 'tel' in data:
            tel = data['tel']
            if tel:
                if len(tel) > 20:
                    return jsonify({'code': 1, 'message': '电话号码长度不能超过20个字符'})
                if not re.match(r'^1[3-9]\d{9}$', tel):
                    return jsonify({'code': 1, 'message': '电话号码格式不正确'})
            user.tel = tel

        if 'role' in data:
            admin_user = User.query.filter_by(username=current_user).first()
            if admin_user and admin_user.role == 'admin':
                role = data['role']
                if role == 'user':
                    role = 'common'
                if role not in ['admin', 'common']:
                    return jsonify({'code': 1, 'message': '角色无效'})
                # 保护：禁止将任何管理员（含自己/其他管理员）降级为普通用户，防止权限被恶意回收
                if user.role == 'admin' and role != 'admin':
                    return jsonify({'code': 1, 'message': '不能将管理员账号降级为普通用户'})
                user.role = role

        if data.get('password'):
            pwd = data['password']
            if len(pwd) < 6:
                return jsonify({'code': 1, 'message': '密码长度至少6个字符'})
            if len(pwd) > 100:
                return jsonify({'code': 1, 'message': '密码长度不能超过100个字符'})
            user.password = generate_password_hash(pwd)

        db.session.commit()
        logger.info(f'用户信息更新成功: {target_username}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '更新成功'})
    except Exception as e:
        logger.error(f'更新用户信息失败: {str(e)}', exc_info=True)
        return jsonify({'code': 1, 'message': '更新失败'}), 500


@app.route('/api/user/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if not user or user.role != 'admin':
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'code': 1, 'message': '用户不存在'})

        if target_user.username == current_user:
            return jsonify({'code': 1, 'message': '不能删除自己'})

        db.session.delete(target_user)
        db.session.commit()
        logger.info(f'用户删除成功: {target_user.username}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '删除成功'})
    except Exception as e:
        logger.error(f'删除用户失败: {str(e)}')
        return jsonify({'code': 1, 'message': '删除失败'}), 500


@app.route('/api/imgRecords/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_img_record(record_id):
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        record = ImgRecords.query.get(record_id)
        if not record:
            return jsonify({'code': 1, 'message': '记录不存在'})

        if user.role != 'admin' and record.username != current_user:
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        db.session.delete(record)
        db.session.commit()
        logger.info(f'图片记录删除成功: id={record_id}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '删除成功'})
    except Exception as e:
        logger.error(f'删除图片记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '删除失败'}), 500


@app.route('/api/videoRecords/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_video_record(record_id):
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        record = VideoRecords.query.get(record_id)
        if not record:
            return jsonify({'code': 1, 'message': '记录不存在'})

        if user.role != 'admin' and record.username != current_user:
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        db.session.delete(record)
        db.session.commit()
        logger.info(f'视频记录删除成功: id={record_id}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '删除成功'})
    except Exception as e:
        logger.error(f'删除视频记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '删除失败'}), 500


@app.route('/api/cameraRecords/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_camera_record(record_id):
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        record = CameraRecords.query.get(record_id)
        if not record:
            return jsonify({'code': 1, 'message': '记录不存在'})

        if user.role != 'admin' and record.username != current_user:
            return jsonify({'code': 1, 'message': '权限不足'}), 403

        db.session.delete(record)
        db.session.commit()
        logger.info(f'摄像头记录删除成功: id={record_id}, 操作人: {current_user}')
        return jsonify({'code': 0, 'message': '删除成功'})
    except Exception as e:
        logger.error(f'删除摄像头记录失败: {str(e)}')
        return jsonify({'code': 1, 'message': '删除失败'}), 500


@app.route('/api/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()

        if user and user.role == 'admin':
            img_count = ImgRecords.query.count()
            video_count = VideoRecords.query.count()
            camera_count = CameraRecords.query.count()
            user_count = User.query.count()
        else:
            img_count = ImgRecords.query.filter_by(username=current_user).count()
            video_count = VideoRecords.query.filter_by(username=current_user).count()
            camera_count = CameraRecords.query.filter_by(username=current_user).count()
            user_count = 1

        return jsonify({
            'code': 0,
            'data': {
                'img_count': img_count,
                'video_count': video_count,
                'camera_count': camera_count,
                'user_count': user_count
            }
        })
    except Exception as e:
        logger.error(f'获取统计数据失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取统计数据失败'}), 500


@app.route('/files/upload', methods=['POST'])
@jwt_required()
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'code': 1, 'message': '没有文件'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'code': 1, 'message': '文件名不能为空'})

        if not allowed_file(file.filename):
            return jsonify({'code': 1, 'message': '不支持的文件类型'})

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        file_size = os.path.getsize(filepath)
        if file_size > app.config['MAX_CONTENT_LENGTH']:
            os.remove(filepath)
            return jsonify({'code': 1, 'message': '文件大小超出限制'})

        file_url = f'{get_base_url()}/files/{unique_filename}'
        logger.info(f'文件上传成功: {unique_filename}, 大小: {file_size} bytes')
        return jsonify({'code': 0, 'data': file_url})
    except Exception as e:
        logger.error(f'文件上传失败: {str(e)}')
        return jsonify({'code': 1, 'message': '上传失败'}), 500


@app.route('/files/<path:filename>')
def serve_file(filename):
    # 鉴权：接受 Authorization Bearer 头或 ?token= 查询参数（img/video 标签无法携带请求头）
    token = request.args.get('token')
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = token or auth_header[7:]
    if not token:
        return jsonify({'code': 1, 'message': '请先登录'}), 401
    try:
        decode_token(token)
    except Exception:
        return jsonify({'code': 1, 'message': '无效的token或已过期'}), 401

    try:
        safe_filename = os.path.basename(filename)
        if '..' in filename or filename.startswith('/'):
            return jsonify({'code': 1, 'message': '无效的文件名'}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        if not os.path.exists(filepath):
            return jsonify({'code': 1, 'message': '文件不存在'}), 404

        mimetype = mimetypes.guess_type(safe_filename)[0]
        if mimetype:
            return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename, mimetype=mimetype)
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)
    except Exception as e:
        logger.error(f'文件访问失败: {str(e)}')
        return jsonify({'code': 1, 'message': '文件访问失败'}), 500


@app.route('/api/download/<path:filename>')
@jwt_required(optional=True)
def download_file(filename):
    # 严格鉴权：接受 Authorization Bearer 头或 ?token= 查询参数（下载链接为导航式跳转，无法携带请求头）
    token = request.args.get('token')
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = token or auth_header[7:]
    if not token:
        return jsonify({'code': 1, 'message': '请先登录'}), 401
    try:
        decode_token(token)
    except Exception:
        return jsonify({'code': 1, 'message': '无效的token或已过期'}), 401

    try:
        safe_filename = os.path.basename(filename)
        if '..' in filename or filename.startswith('/'):
            return jsonify({'code': 1, 'message': '无效的文件名'}), 400

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        if not os.path.exists(filepath):
            return jsonify({'code': 1, 'message': '文件不存在'}), 404

        download_name = request.args.get('name', safe_filename)
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            safe_filename,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        logger.error(f'文件下载失败: {str(e)}')
        return jsonify({'code': 1, 'message': '下载失败'}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'code': 1, 'message': '接口不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f'服务器内部错误: {str(error)}', exc_info=True)
    return jsonify({'code': 1, 'message': '服务器内部错误'}), 500


@jwt.unauthorized_loader
def unauthorized_callback(callback):
    return jsonify({'code': 1, 'message': '请先登录'}), 401


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'code': 1, 'message': '登录已过期，请重新登录'}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'code': 1, 'message': '无效的token'}), 401


@socketio.on('connect')
def handle_connect(auth):
    # WebSocket 连接鉴权：要求携带有效 JWT（auth.token 或 ?token= 查询参数）
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get('token') or auth.get('access_token')
    if not token:
        token = request.args.get('token')
    if not token:
        logger.warning("WebSocket 连接被拒绝：缺少 token")
        return False
    try:
        decode_token(token)
    except Exception as e:
        logger.warning(f"WebSocket 连接被拒绝：无效 token: {str(e)}")
        return False
    logger.info("WebSocket connected!")
    emit('message', {'data': 'Connected to WebSocket server!'})


@socketio.on('disconnect')
def handle_disconnect():
    logger.info("WebSocket disconnected!")


# ==================== 模型管理 API ====================

ALLOWED_MODEL_EXTENSIONS = {'pt'}

DEFAULT_MODELS = {'corn_best.pt', 'rice_best.pt', 'wheat_best.pt'}


def allowed_model_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_MODEL_EXTENSIONS


def get_model_info(filename):
    filepath = os.path.join('./weights', filename)
    is_default = filename in DEFAULT_MODELS
    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    return {
        'name': filename,
        'size': size,
        'is_default': is_default,
        'is_custom': not is_default
    }


@app.route('/api/models', methods=['GET'])
@jwt_required()
def list_models():
    try:
        models = []
        weights_dir = './weights'
        if os.path.exists(weights_dir):
            for name in sorted(os.listdir(weights_dir)):
                if os.path.isfile(os.path.join(weights_dir, name)) and name.endswith('.pt'):
                    models.append(get_model_info(name))
        return jsonify({'code': 0, 'data': models})
    except Exception as e:
        logger.error(f'获取模型列表失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取模型列表失败'}), 500


@app.route('/api/models/upload', methods=['POST'])
@jwt_required()
def upload_model():
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()
        if not user or user.role != 'admin':
            return jsonify({'code': 1, 'message': '仅管理员可上传模型'}), 403

        if 'model' not in request.files:
            return jsonify({'code': 1, 'message': '未找到模型文件'}), 400

        file = request.files['model']
        if file.filename == '':
            return jsonify({'code': 1, 'message': '请选择文件'}), 400

        if not allowed_model_file(file.filename):
            return jsonify({'code': 1, 'message': '仅支持 .pt 格式的模型文件'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join('./weights', filename)

        if os.path.exists(filepath):
            return jsonify({'code': 1, 'message': '模型文件已存在'}), 400

        file.save(filepath)
        logger.info(f'模型上传成功: {filename} by {current_user}')
        return jsonify({'code': 0, 'message': '模型上传成功', 'data': get_model_info(filename)})
    except Exception as e:
        logger.error(f'模型上传失败: {str(e)}')
        return jsonify({'code': 1, 'message': '上传失败'}), 500


@app.route('/api/models/<path:filename>', methods=['DELETE'])
@jwt_required()
def delete_model(filename):
    try:
        current_user = get_jwt_identity()
        user = User.query.filter_by(username=current_user).first()
        if not user or user.role != 'admin':
            return jsonify({'code': 1, 'message': '仅管理员可删除模型'}), 403

        safe_filename = os.path.basename(filename)
        if '..' in filename or filename.startswith('/'):
            return jsonify({'code': 1, 'message': '无效的文件名'}), 400

        if safe_filename in DEFAULT_MODELS:
            return jsonify({'code': 1, 'message': '默认模型不可删除'}), 400

        filepath = os.path.join('./weights', safe_filename)
        if not os.path.exists(filepath):
            return jsonify({'code': 1, 'message': '模型不存在'}), 404

        os.remove(filepath)
        clear_model_cache(filepath)
        logger.info(f'模型删除成功: {safe_filename} by {current_user}')
        return jsonify({'code': 0, 'message': '模型已删除'})
    except Exception as e:
        logger.error(f'模型删除失败: {str(e)}')
        return jsonify({'code': 1, 'message': '删除失败'}), 500


# ==================== 系统信息 API ====================

SYSTEM_VERSION = '2.2.0'

UPDATE_LOGS = [
    {
        'version': '2.2.0',
        'date': '2026-08-25',
        'changes': [
            '新增管理员创建用户时可选填性别、邮箱、电话',
            '新增用户登录后信息完善提醒弹窗',
            '新增用户管理表格性别、邮箱、电话列展示',
            '新增个人中心性别、邮箱、电话字段编辑',
            '新增个人中心检测统计与仪表盘数据同步',
            '优化仪表盘：普通用户隐藏注册用户数统计',
            '优化表单必填/选填标记（红色*必填，灰色选填）',
            '修复用户更新接口角色映射问题',
            '修复搜索框浏览器自动填充问题',
            '修复前端角色CSS类名不匹配问题'
        ]
    },
    {
        'version': '2.1.0',
        'date': '2026-06-15',
        'changes': [
            '新增自定义模型上传与管理功能',
            '新增置信度四舍五入开关设置',
            '新增仪表盘通知面板与关于弹窗',
            '新增系统使用文档、更新日志、技术支援',
            '优化历史记录删除与下载功能',
            '修复摄像头安全上下文检测问题'
        ]
    },
    {
        'version': '2.0.0',
        'date': '2026-03-12',
        'changes': [
            '全新绿色农业主题UI设计',
            '新增摄像头实时检测功能',
            '新增视频检测与输出功能',
            '新增用户权限管理系统',
            '支持多种农作物病害识别'
        ]
    },
    {
        'version': '1.0.0',
        'date': '2026-05-01',
        'changes': [
            '首个正式版本',
            '基础图片病害检测功能',
            '用户注册登录系统',
            '历史记录管理'
        ]
    }
]

TECH_SUPPORT_INFO = {
    'developer': '农作物病害识别系统开源项目',
    'email': 'xxux5_026y9sp3d@163.com',
    'qq': '',
    'wechat': '',
    'website': 'https://github.com/YanQvQ/crop-disease-detection',
    'work_time': '通过 GitHub Issues 反馈问题，欢迎提交 PR',
    'github': 'https://github.com/YanQvQ'
}

USER_DOCS = [
    {
        'title': '快速入门指南',
        'content': '1. 注册账号并登录系统\n2. 在左侧菜单选择检测类型（图片/视频/摄像头）\n3. 选择作物类型和检测模型\n4. 上传文件或开启摄像头\n5. 点击"开始检测"查看结果\n6. 在历史记录中查看和管理检测记录'
    },
    {
        'title': '图片检测使用说明',
        'content': '支持 PNG、JPG、JPEG、BMP、WEBP 等常见图片格式。\n上传图片后系统会自动识别病害类型并标注位置。\n检测结果会自动保存到历史记录中。\n可下载标注后的图片用于报告或存档。'
    },
    {
        'title': '视频检测使用说明',
        'content': '支持 MP4、AVI、MOV、MKV 等常见视频格式。\n系统会逐帧检测视频中的病害区域。\n处理时间取决于视频长度和分辨率。\n检测完成后可下载标注视频。'
    },
    {
        'title': '摄像头检测使用说明',
        'content': '需要 HTTPS 或 localhost 环境才能使用摄像头功能。\n点击"开始检测"后请授权浏览器访问摄像头。\n实时画面中会自动标注检测到的病害。\n停止检测后视频会自动保存到记录中。'
    },
    {
        'title': '系统设置说明',
        'content': '检测参数：可调整置信度阈值、IoU阈值、最大检测数等。\n模型配置：管理可用的检测模型，支持上传自定义模型。\n通知设置：配置检测完成、新用户注册等通知偏好。\n关于系统：查看版本信息、使用文档、更新日志。'
    }
]


@app.route('/api/system/info', methods=['GET'])
def system_info():
    try:
        return jsonify({
            'code': 0,
            'data': {
                'version': SYSTEM_VERSION,
                'name': '农作物病害识别系统',
                'description': '基于深度学习YOLO模型开发的智能农作物病害识别系统',
                'tech_stack': 'Flask + YOLOv8 + SQLite'
            }
        })
    except Exception as e:
        logger.error(f'获取系统信息失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取失败'}), 500


@app.route('/api/system/updates', methods=['GET'])
def system_updates():
    try:
        return jsonify({'code': 0, 'data': UPDATE_LOGS})
    except Exception as e:
        logger.error(f'获取更新日志失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取失败'}), 500


@app.route('/api/system/support', methods=['GET'])
def system_support():
    try:
        return jsonify({'code': 0, 'data': TECH_SUPPORT_INFO})
    except Exception as e:
        logger.error(f'获取技术支援信息失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取失败'}), 500


@app.route('/api/system/docs', methods=['GET'])
def system_docs():
    try:
        return jsonify({'code': 0, 'data': USER_DOCS})
    except Exception as e:
        logger.error(f'获取使用文档失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取失败'}), 500


# ==================== 通知 API ====================

@app.route('/api/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    try:
        current_user = get_jwt_identity()
        records = Notification.query.filter_by(username=current_user).order_by(Notification.id.desc()).limit(50).all()
        notifications = [{
            'id': n.id,
            'type': n.type,
            'title': n.title,
            'content': n.content,
            'time': n.time,
            'read': n.read
        } for n in records]
        unread_count = sum(1 for n in notifications if not n['read'])
        return jsonify({'code': 0, 'data': notifications, 'unread_count': unread_count})
    except Exception as e:
        logger.error(f'获取通知失败: {str(e)}')
        return jsonify({'code': 1, 'message': '获取失败'}), 500


@app.route('/api/notifications/read', methods=['POST'])
@jwt_required()
def mark_notifications_read():
    try:
        current_user = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        ids = data.get('ids')
        if isinstance(ids, list):
            # 标记指定通知为已读
            for nid in ids:
                n = Notification.query.filter_by(id=int(nid), username=current_user).first()
                if n:
                    n.read = True
        else:
            # 未指定 ids 时标记当前用户全部通知为已读
            Notification.query.filter_by(username=current_user, read=False).update({'read': True})
        db.session.commit()
        return jsonify({'code': 0, 'message': '已标记为已读'})
    except Exception as e:
        logger.error(f'标记通知已读失败: {str(e)}')
        return jsonify({'code': 1, 'message': '操作失败'}), 500


if __name__ == '__main__':
    # 生产说明：安装 eventlet（pip install eventlet）后，socketio.run 会自动以
    # eventlet 生产级服务器运行（官方文档明确：eventlet/gevent 可用时即生产就绪），
    # 可支撑较多并发连接。生产部署完整方案见 README「生产部署」章节。
    # Linux 高并发场景亦可改用 gunicorn：gunicorn -k eventlet -w 1 main:socketio
    _host = os.environ.get('HOST', '0.0.0.0')
    try:
        _port = int(os.environ.get('PORT', '5000'))
    except ValueError:
        _port = 5000
    logger.info('服务器启动中...')
    socketio.run(app, host=_host, port=_port, debug=False)
