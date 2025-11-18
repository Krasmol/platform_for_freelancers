from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import time
from sqlalchemy import desc

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///freelance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_client = db.Column(db.Boolean, default=False)
    is_moderator = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    profile = db.relationship('Profile', backref='user', uselist=False)
    projects = db.relationship('Project', backref='client', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver',
                                        lazy='dynamic')
    support_tickets = db.relationship('SupportTicket', backref='user', lazy='dynamic')
    ticket_messages = db.relationship('TicketMessage', backref='user', lazy='dynamic')

    favorite_projects = db.relationship('Project', secondary='favorites', backref='favorited_by')

    favorites = db.Table('favorites',
                         db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                         db.Column('project_id', db.Integer, db.ForeignKey('project.id')),
                         db.Column('created_at', db.DateTime, default=lambda: datetime.now(timezone.utc))
                         )


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(100))
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    skills = db.Column(db.String(500))
    hourly_rate = db.Column(db.Float)
    experience = db.Column(db.String(50))


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    budget = db.Column(db.Float)
    category = db.Column(db.String(100))
    skills_required = db.Column(db.String(500))
    status = db.Column(db.String(20), default='open')
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))
    is_read = db.Column(db.Boolean, default=False)
    related_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')
    priority = db.Column(db.String(20), default='medium')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    messages = db.relationship('TicketMessage', backref='ticket', lazy='dynamic')


class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_admin_response = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    rating = db.Column(db.Integer)  # 1-5 stars
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# функция для запроса уведомлений
def notifications_query(user_id):
    return Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(5).all()


# контекстный процессор
@app.context_processor
def utility_processor():
    def get_category_icon(category):
        icons = {
            'Разработка': '💻',
            'Дизайн': '🎨',
            'Маркетинг': '📈',
            'Тексты': '✍️',
            'Консультация': '💬',
            'Администрирование': '⚙️'
        }
        return icons.get(category, '🔧')

    def get_unread_notifications_count():
        if current_user.is_authenticated:
            return Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return 0

    def get_notification_icon(notification_type):
        icons = {
            'project_response': 'bi-person-plus',
            'message': 'bi-chat-dots',
            'system': 'bi-info-circle',
            'project_completed': 'bi-check-circle',
            'warning': 'bi-exclamation-triangle'
        }
        return icons.get(notification_type, 'bi-bell')

    def get_notification_color(notification_type):
        colors = {
            'project_response': 'primary',
            'message': 'info',
            'system': 'secondary',
            'project_completed': 'success',
            'warning': 'warning'
        }
        return colors.get(notification_type, 'secondary')

    def get_unread_messages_count():
        if current_user.is_authenticated:
            return Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
        return 0

    return dict(
        get_category_icon=get_category_icon,
        get_unread_notifications_count=get_unread_notifications_count,
        get_notification_icon=get_notification_icon,
        get_notification_color=get_notification_color,
        notifications_query=notifications_query,
        get_unread_messages_count=get_unread_messages_count
    )


# основные маршруты
@app.route('/')
def index():
    projects = Project.query.filter_by(status='open').order_by(Project.created_at.desc()).limit(6).all()
    return render_template('index.html', projects=projects)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']

        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            is_client=(user_type == 'client')
        )
        user.password_hash = generate_password_hash(password)

        db.session.add(user)
        db.session.commit()

        # ТОЛЬКО одно приветственное уведомление для нового пользователя
        welcome_notification = Notification(
            user_id=user.id,
            title='Добро пожаловать на FreelanceHub!',
            message='Спасибо за регистрацию. Заполните свой профиль, чтобы начать работу.',
            notification_type='system'
        )
        db.session.add(welcome_notification)
        db.session.commit()

        flash('Регистрация успешна! Войдите в систему')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Ваш аккаунт заблокирован')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Неверный email или пароль')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/profile/create', methods=['GET', 'POST'])
@login_required
def create_profile():
    if current_user.profile:
        return redirect(url_for('view_profile'))

    if request.method == 'POST':
        profile = Profile(
            user_id=current_user.id,
            full_name=request.form['full_name'],
            title=request.form['title'],
            description=request.form['description'],
            skills=request.form['skills'],
            hourly_rate=float(request.form['hourly_rate'] or 0),
            experience=request.form['experience']
        )
        db.session.add(profile)
        db.session.commit()

        # Уведомление о создании профиля (только один раз)
        profile_notification = Notification(
            user_id=current_user.id,
            title='Профиль создан!',
            message='Ваш профиль успешно создан. Теперь вы можете искать проекты или создавать свои.',
            notification_type='system'
        )
        db.session.add(profile_notification)
        db.session.commit()

        flash('Профиль создан!')
        return redirect(url_for('index'))

    return render_template('create_profile.html')


@app.route('/profile')
@login_required
def view_profile():
    if not current_user.profile:
        return redirect(url_for('create_profile'))

    user_projects = []
    if current_user.is_client:
        user_projects = Project.query.filter_by(client_id=current_user.id).order_by(Project.created_at.desc()).all()

    return render_template('view_profile.html', user_projects=user_projects)


@app.route('/projects')
def projects():
    category = request.args.get('category')
    search = request.args.get('search')

    query = Project.query.filter_by(status='open')

    if category:
        query = query.filter(Project.category.contains(category))
    if search:
        query = query.filter(Project.title.contains(search) | Project.description.contains(search))

    projects = query.order_by(Project.created_at.desc()).all()
    return render_template('projects.html', projects=projects)


@app.route('/projects/create', methods=['GET', 'POST'])
@login_required
def create_project():
    if not current_user.is_client:
        flash('Только заказчики могут создавать проекты')
        return redirect(url_for('index'))

    if request.method == 'POST':
        project = Project(
            title=request.form['title'],
            description=request.form['description'],
            budget=float(request.form['budget'] or 0),
            category=request.form['category'],
            skills_required=request.form['skills_required'],
            client_id=current_user.id
        )
        db.session.add(project)
        db.session.commit()

        # Уведомление о создании проекта
        project_notification = Notification(
            user_id=current_user.id,
            title='Проект опубликован!',
            message=f'Ваш проект "{project.title}" успешно опубликован.',
            notification_type='system',
            related_id=project.id
        )
        db.session.add(project_notification)
        db.session.commit()

        flash('Проект создан!')
        return redirect(url_for('projects'))

    return render_template('create_project.html')


@app.route('/project/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)


# отклик на проект
@app.route('/project/<int:project_id>/respond', methods=['POST'])
@login_required
def respond_to_project(project_id):
    if current_user.is_client:
        flash('Заказчики не могут откликаться на проекты')
        return redirect(url_for('project_detail', project_id=project_id))

    project = Project.query.get_or_404(project_id)

    # проверка не откликался ли уже
    existing_message = Message.query.filter_by(
        sender_id=current_user.id,
        receiver_id=project.client_id
    ).first()

    if existing_message:
        flash('Вы уже откликались на этот проект')
        return redirect(url_for('project_detail', project_id=project_id))

    # первое сообщение
    first_message = Message(
        sender_id=current_user.id,
        receiver_id=project.client_id,
        content=f'Здравствуйте! Я заинтересован в вашем проекте "{project.title}". Мой опыт: {current_user.profile.experience if current_user.profile else "не указан"}. Давайте обсудим детали!'
    )
    db.session.add(first_message)

    # уведомление для владельца
    response_notification = Notification(
        user_id=project.client_id,
        title='Новый отклик на ваш проект!',
        message=f'Пользователь {current_user.username} откликнулся на ваш проект "{project.title}". Перейдите в сообщения для обсуждения.',
        notification_type='project_response',
        related_id=project.id
    )
    db.session.add(response_notification)

    db.session.commit()

    flash('✅ Отклик отправлен! Заказчик получил уведомление. Теперь вы можете общаться в чате.')
    return redirect(url_for('chat_list', user_id=project.client_id))


# уведомления
@app.route('/notifications')
@login_required
def notifications():
    user_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    return render_template('notifications.html', notifications=user_notifications)


@app.route('/notifications/read/<int:notification_id>')
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()

    notification.is_read = True
    db.session.commit()

    flash('Уведомление отмечено как прочитанное')
    return redirect(url_for('notifications'))


@app.route('/notifications/read_all')
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()

    flash('Все уведомления отмечены как прочитанные')
    return redirect(url_for('notifications'))


# функция чатов
def get_user_chats(user_id):
    """список чатов"""
    # поиск пользователей с кем уже есть чат
    sent_messages = Message.query.filter_by(sender_id=user_id).all()
    received_messages = Message.query.filter_by(receiver_id=user_id).all()

    # id пользователей с чатов
    chat_user_ids = set()

    for msg in sent_messages:
        chat_user_ids.add(msg.receiver_id)

    for msg in received_messages:
        chat_user_ids.add(msg.sender_id)

    chats = []
    for chat_user_id in chat_user_ids:
        if chat_user_id != user_id:
            other_user = db.session.get(User, chat_user_id)
            if other_user:
                # Получаем последнее сообщение в чате
                last_message = Message.query.filter(
                    db.or_(
                        db.and_(Message.sender_id == user_id, Message.receiver_id == chat_user_id),
                        db.and_(Message.sender_id == chat_user_id, Message.receiver_id == user_id)
                    )
                ).order_by(Message.created_at.desc()).first()

                # непрочитанные сообщения
                unread_count = Message.query.filter_by(
                    sender_id=chat_user_id,
                    receiver_id=user_id,
                    is_read=False
                ).count()

                chats.append({
                    'other_user': other_user,
                    'last_message': last_message,
                    'unread_count': unread_count
                })

    # сортировка по последнему сообщению
    chats.sort(key=lambda x: x['last_message'].created_at if x['last_message'] else datetime.min, reverse=True)
    return chats


def get_chat_messages(user1_id, user2_id):
    """получение сообщений между двумя пользователями"""
    return Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == user1_id, Message.receiver_id == user2_id),
            db.and_(Message.sender_id == user2_id, Message.receiver_id == user1_id)
        )
    ).order_by(Message.created_at.asc()).all()


# система чатов
@app.route('/chats')
@login_required
def chat_list():
    chats = get_user_chats(current_user.id)
    selected_user_id = request.args.get('user_id')
    selected_user = None
    messages = []

    if selected_user_id:
        selected_user = db.session.get(User, int(selected_user_id))
        if selected_user:
            messages = get_chat_messages(current_user.id, selected_user.id)

            # Помечаем сообщения как прочитанные
            Message.query.filter_by(
                sender_id=selected_user.id,
                receiver_id=current_user.id,
                is_read=False
            ).update({'is_read': True})
            db.session.commit()

    return render_template('chat_list.html',
                           chats=chats,
                           selected_user=selected_user,
                           messages=messages,
                           User=User,
                           Message=Message,
                           time=time)


@app.route('/send_message', methods=['POST'])
@limiter.limit("5 per minute")
def send_message():
    receiver_id = request.json.get('receiver_id')
    content = request.json.get('content')

    if not receiver_id or not content:
        return jsonify({'status': 'error', 'message': 'Неверные данные'})

    receiver = db.session.get(User, receiver_id)
    if not receiver:
        return jsonify({'status': 'error', 'message': 'Пользователь не найден'})

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(message)

    # уведомление для получателя
    notification = Notification(
        user_id=receiver_id,
        title='Новое сообщение',
        message=f'{current_user.username}: {content[:50]}...',
        notification_type='message',
        related_id=current_user.id
    )
    db.session.add(notification)

    db.session.commit()

    return jsonify({
        'status': 'success',
        'message_id': message.id,
        'created_at': message.created_at.strftime('%H:%M'),
        'sender_username': current_user.username,
        'sender_avatar': current_user.username[0]
    })


@app.route('/api/check_new_messages')
@login_required
def check_new_messages():
    """новое сообщение для пользователя"""
    last_check = request.args.get('last_check', type=float)

    if last_check:
        # новые сообщения после проверки
        new_messages = Message.query.filter(
            Message.receiver_id == current_user.id,
            Message.created_at > datetime.fromtimestamp(last_check, timezone.utc)
        ).order_by(Message.created_at.desc()).all()

        # новые уведомления
        new_notifications = Notification.query.filter(
            Notification.user_id == current_user.id,
            Notification.created_at > datetime.fromtimestamp(last_check, timezone.utc)
        ).order_by(Notification.created_at.desc()).all()

        return jsonify({
            'has_new_messages': len(new_messages) > 0,
            'has_new_notifications': len(new_notifications) > 0,
            'new_messages_count': len(new_messages),
            'new_notifications_count': len(new_notifications),
            'current_time': time.time()
        })

    return jsonify({'current_time': time.time()})

# система поддержки
@app.route('/support')
@login_required
def support():
    user_tickets = SupportTicket.query.filter_by(
        user_id=current_user.id
    ).order_by(SupportTicket.created_at.desc()).all()

    return render_template('support.html', tickets=user_tickets)


@app.route('/support/create', methods=['GET', 'POST'])
@login_required
def create_support_ticket():
    if request.method == 'POST':
        subject = request.form.get('subject')
        category = request.form.get('category')
        description = request.form.get('description')
        priority = request.form.get('priority', 'medium')

        if not subject or not description:
            flash('Заполните все обязательные поля')
            return redirect(url_for('create_support_ticket'))

        ticket = SupportTicket(
            user_id=current_user.id,
            subject=subject,
            category=category,
            description=description,
            priority=priority
        )
        db.session.add(ticket)
        db.session.commit()

        # новое сообщение в тикете
        ticket_message = TicketMessage(
            ticket_id=ticket.id,
            user_id=current_user.id,
            content=description,
            is_admin_response=False
        )
        db.session.add(ticket_message)

        # уведомление для админа
        moderators = User.query.filter_by(is_moderator=True).all()
        for moderator in moderators:
            moderator_notification = Notification(
                user_id=moderator.id,
                title='Новое обращение в поддержку',
                message=f'Пользователь {current_user.username} создал обращение: {subject}',
                notification_type='warning',
                related_id=ticket.id
            )
            db.session.add(moderator_notification)

        # уведомление для пользователя
        user_notification = Notification(
            user_id=current_user.id,
            title='Обращение в поддержку создано',
            message=f'Ваше обращение "{subject}" принято в обработку.',
            notification_type='system'
        )
        db.session.add(user_notification)

        db.session.commit()

        flash('Обращение в поддержку создано!')
        return redirect(url_for('support_ticket', ticket_id=ticket.id))

    return render_template('create_support_ticket.html')


@app.route('/support/ticket/<int:ticket_id>')
@login_required
def support_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)

    # проверка доступа
    if ticket.user_id != current_user.id and not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('support'))

    messages = TicketMessage.query.filter_by(ticket_id=ticket_id).order_by(TicketMessage.created_at.asc()).all()

    return render_template('support_ticket.html', ticket=ticket, messages=messages)


@app.route('/support/ticket/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply_support_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    content = request.form.get('content')

    if not content:
        flash('Введите сообщение')
        return redirect(url_for('support_ticket', ticket_id=ticket_id))

    # проверка доступа
    if ticket.user_id != current_user.id and not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('support'))

    ticket_message = TicketMessage(
        ticket_id=ticket_id,
        user_id=current_user.id,
        content=content,
        is_admin_response=current_user.is_moderator
    )
    db.session.add(ticket_message)

    # обновляем тикет
    if current_user.is_moderator and ticket.status == 'open':
        ticket.status = 'in_progress'

    ticket.updated_at = datetime.now(timezone.utc)

    # уведомление для другой стороны
    if current_user.is_moderator:
        # уведомление для пользователя
        notification = Notification(
            user_id=ticket.user_id,
            title='Новый ответ от поддержки',
            message=f'По вашему обращению "{ticket.subject}" получен ответ.',
            notification_type='system',
            related_id=ticket.id
        )
        db.session.add(notification)
    else:
        # уведомление для модераторов
        moderators = User.query.filter_by(is_moderator=True).all()
        for moderator in moderators:
            notification = Notification(
                user_id=moderator.id,
                title='Новый ответ в обращении',
                message=f'Пользователь {current_user.username} ответил в обращении: {ticket.subject}',
                notification_type='warning',
                related_id=ticket.id
            )
            db.session.add(notification)

    db.session.commit()

    flash('Сообщение отправлено')
    return redirect(url_for('support_ticket', ticket_id=ticket_id))


@app.route('/support/ticket/<int:ticket_id>/close')
@login_required
def close_support_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)

    # проверка доступа
    if ticket.user_id != current_user.id and not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('support'))

    ticket.status = 'closed'
    ticket.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash('Обращение закрыто')
    return redirect(url_for('support_ticket', ticket_id=ticket_id))


# панель модера
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    # все обращения
    all_tickets = SupportTicket.query.order_by(desc(SupportTicket.created_at)).all()
    open_tickets = [t for t in all_tickets if t.status in ['open', 'in_progress']]
    closed_tickets = [t for t in all_tickets if t.status == 'closed']

    stats = {
        'total_users': User.query.count(),
        'total_projects': Project.query.count(),
        'open_projects': Project.query.filter_by(status='open').count(),
        'total_tickets': len(all_tickets),
        'open_tickets': len(open_tickets),
        'closed_tickets': len(closed_tickets)
    }

    return render_template('admin_dashboard.html',
                           stats=stats,
                           recent_tickets=all_tickets[:10],
                           all_tickets=all_tickets)


@app.route('/admin/tickets')
@login_required
def admin_tickets():
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    status_filter = request.args.get('status', 'all')

    if status_filter == 'all':
        tickets = SupportTicket.query.order_by(desc(SupportTicket.created_at)).all()
    elif status_filter == 'open':
        tickets = SupportTicket.query.filter(SupportTicket.status.in_(['open', 'in_progress'])).order_by(
            desc(SupportTicket.created_at)).all()
    else:
        tickets = SupportTicket.query.filter_by(status=status_filter).order_by(desc(SupportTicket.created_at)).all()

    return render_template('admin_tickets.html', tickets=tickets, status_filter=status_filter)


@app.route('/admin/ticket/<int:ticket_id>')
@login_required
def admin_ticket_detail(ticket_id):
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    ticket = SupportTicket.query.get_or_404(ticket_id)
    messages = TicketMessage.query.filter_by(ticket_id=ticket_id).order_by(TicketMessage.created_at.asc()).all()

    return render_template('support_ticket.html', ticket=ticket, messages=messages, admin_view=True)


def init_db():
    """инициализация базы данных"""
    with app.app_context():
        db.drop_all()
        db.create_all()

        # логин и пароль модера
        moderator = User(
            username='moderator',
            email='moderator@test.ru',
            is_moderator=True
        )
        moderator.password_hash = generate_password_hash('moderator123')

        db.session.add(moderator)
        db.session.commit()

        print("База данных инициализирована!")
        print("Создан только модератор:")
        print("Модератор - moderator@test.ru / moderator123")
        print("")
        print("Для тестирования:")
        print("1. Зарегистрируйте новых пользователей")
        print("2. Создайте проекты")
        print("3. Тестируйте функционал с чистого листа")


if __name__ == '__main__':
    if not os.path.exists('instance/freelance.db'):
        init_db()
    app.run(debug=True, port=5001, host='0.0.0.0')
