from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import os
import time
from sqlalchemy import desc, text

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///freelance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'

# модели
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
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    support_tickets = db.relationship('SupportTicket', backref='user', lazy='dynamic')
    ticket_messages = db.relationship('TicketMessage', backref='user', lazy='dynamic')


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
    technologies = db.Column(db.String(500))
    status = db.Column(db.String(20), default='open')
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    freelancer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='open')

    client = db.relationship('User', foreign_keys=[client_id], backref='created_projects')
    freelancer = db.relationship('User', foreign_keys=[freelancer_id], backref='assigned_projects')

    # связь с фрилансером
    freelancer = db.relationship('User', foreign_keys=[freelancer_id], backref='assigned_projects')

class ProjectResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    freelancer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text)
    proposed_budget = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship('Project', backref='responses')
    freelancer = db.relationship('User', foreign_keys=[freelancer_id], backref='project_responses')

    def reject(self):
        """отклонить отклик"""
        self.status = 'rejected'

        # уведомление фрилансеру
        notification = Notification(
            user_id=self.freelancer_id,
            title='Отклик отклонен',
            message=f'Ваш отклик на проект "{self.project.title}" был отклонен.',
            notification_type='project_response',
            related_id=self.project.id
        )
        db.session.add(notification)

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
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Кто оставляет отзыв
    freelancer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Кого оценивают
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship('Project', backref='reviews')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='given_reviews')
    freelancer = db.relationship('User', foreign_keys=[freelancer_id], backref='received_reviews')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# функция для запроса уведомлений
def notifications_query(user_id):
    return Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(5).all()


def get_freelancer_rating(freelancer_id):
    reviews = Review.query.filter_by(freelancer_id=freelancer_id).all()
    if not reviews:
        return 0
    return sum(review.rating for review in reviews) / len(reviews)


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

    def get_freelancer_rating(freelancer_id):
        reviews = Review.query.filter_by(freelancer_id=freelancer_id).all()
        if not reviews:
            return 0
        return sum(review.rating for review in reviews) / len(reviews)

    return dict(
        get_category_icon=get_category_icon,
        get_unread_notifications_count=get_unread_notifications_count,
        get_notification_icon=get_notification_icon,
        get_notification_color=get_notification_color,
        get_unread_messages_count=get_unread_messages_count,  # ← ДОБАВЬТЕ ЗАПЯТУЮ ЗДЕСЬ
        get_freelancer_rating=get_freelancer_rating,
        notifications_query=notifications_query
    )


# основные маршруты
@app.route('/')
def index():
    projects = Project.query.filter_by(status='open').order_by(Project.created_at.desc()).limit(6).all()
    return render_template('index.html', projects=projects)


@app.route('/profile/<int:user_id>')
@login_required
def user_profile(user_id):
    """Просмотр профиля другого пользователя"""
    user = User.query.get_or_404(user_id)

    # Не позволяем смотреть свой же профиль через этот маршрут
    if user.id == current_user.id:
        return redirect(url_for('view_profile'))

    if user.is_client:
        # Для заказчика
        user_projects_active = Project.query.filter(
            Project.client_id == user.id,
            Project.status.in_(['open', 'in_progress'])
        ).order_by(Project.created_at.desc()).limit(10).all()

        user_projects_completed = Project.query.filter(
            Project.client_id == user.id,
            Project.status == 'completed'
        ).order_by(Project.completed_at.desc()).limit(10).all()

        total_budget = sum(project.budget for project in user_projects_completed)

        client_reviews = Review.query.join(Project).filter(
            Project.client_id == user.id
        ).all()
        client_rating = sum(review.rating for review in client_reviews) / len(client_reviews) if client_reviews else 0

        return render_template('user_profile.html',
                               user=user,
                               user_projects_active=user_projects_active,
                               user_projects_completed=user_projects_completed,
                               total_budget=total_budget,
                               client_rating=client_rating)
    else:
        # для фрилансера
        freelancer_projects_active = Project.query.filter(
            Project.freelancer_id == user.id,
            Project.status == 'in_progress'
        ).order_by(Project.created_at.desc()).limit(10).all()

        freelancer_projects_completed = Project.query.filter(
            Project.freelancer_id == user.id,
            Project.status == 'completed'
        ).order_by(Project.completed_at.desc()).limit(10).all()

        freelancer_reviews = Review.query.filter_by(
            freelancer_id=user.id
        ).order_by(Review.created_at.desc()).all()

        return render_template('user_profile.html',
                               user=user,
                               freelancer_projects_active=freelancer_projects_active,
                               freelancer_projects_completed=freelancer_projects_completed,
                               freelancer_reviews=freelancer_reviews,
                               get_freelancer_rating=get_freelancer_rating)

@app.route('/project/<int:project_id>/review', methods=['GET', 'POST'])
@login_required
def create_review(project_id):
    project = Project.query.get_or_404(project_id)

    # проверяем что это заказчик и проект завершен
    if current_user.id != project.client_id:
        flash('Только заказчик может оставить отзыв')
        return redirect(url_for('project_detail', project_id=project_id))

    if project.status != 'completed':
        flash('Можно оставить отзыв только для завершенных проектов')
        return redirect(url_for('project_detail', project_id=project_id))

    # проверка, что отзыв еще не оставлен
    existing_review = Review.query.filter_by(project_id=project_id, reviewer_id=current_user.id).first()
    if existing_review:
        flash('Вы уже оставили отзыв по этому проекту')
        return redirect(url_for('project_detail', project_id=project_id))

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment')

        review = Review(
            project_id=project_id,
            reviewer_id=current_user.id,
            freelancer_id=project.freelancer_id,
            rating=int(rating),
            comment=comment
        )
        db.session.add(review)

        # уведомляем фрилансера
        notification = Notification(
            user_id=project.freelancer_id,
            title='Новый отзыв!',
            message=f'Заказчик оставил отзыв по проекту "{project.title}"',
            notification_type='review',
            related_id=project.id
        )
        db.session.add(notification)

        db.session.commit()

        flash('✅ Отзыв успешно оставлен!')
        return redirect(url_for('project_detail', project_id=project_id))

    return render_template('create_review.html', project=project)


# расчет рейтинга фрилансера
def get_freelancer_rating(freelancer_id):
    reviews = Review.query.filter_by(freelancer_id=freelancer_id).all()
    if not reviews:
        return 0
    return sum(review.rating for review in reviews) / len(reviews)

@app.route('/project/<int:project_id>/reject_response/<int:response_id>')
@login_required
def reject_project_response(project_id, response_id):
    project = Project.query.get_or_404(project_id)
    response = ProjectResponse.query.get_or_404(response_id)

    # проверяем что текущий пользователь - владелец проекта
    if project.client_id != current_user.id:
        flash('Доступ запрещен')
        return redirect(url_for('project_detail', project_id=project_id))

    # отклоняем отклик
    response.status = 'rejected'

    # уведомление фрилансеру
    notification = Notification(
        user_id=response.freelancer_id,
        title='Отклик отклонен',
        message=f'Ваш отклик на проект "{project.title}" был отклонен.',
        notification_type='project_response',
        related_id=project.id
    )
    db.session.add(notification)

    db.session.commit()

    flash('❌ Отклик отклонен')
    return redirect(url_for('project_detail', project_id=project_id))

@app.route('/about')
def about():
    """Страница "О проекте" """
    return render_template('about.html')


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

        # Для фрилансеров - редирект на создание профиля
        if user_type == 'freelancer':
            flash('Регистрация успешна! Заполните ваш профиль фрилансера.')
            login_user(user)
            return redirect(url_for('create_profile'))
        else:
            # Для заказчиков - сразу на главную
            flash('Регистрация успешна! Теперь вы можете создавать проекты.')
            login_user(user)
            return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/debug/user')
@login_required
def debug_user():
    """Страница для отладки информации о пользователе"""
    user_info = {
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'is_client': current_user.is_client,
        'is_moderator': current_user.is_moderator,
        'is_active': current_user.is_active,
        'created_at': current_user.created_at
    }
    return jsonify(user_info)


def create_moderator_if_needed():
    """Создает модератора если его нет"""
    with app.app_context():
        moderator = User.query.filter_by(email='moderator@test.ru').first()
        if not moderator:
            moderator = User(
                username='moderator',
                email='moderator@test.ru',
                is_moderator=True
            )
            moderator.password_hash = generate_password_hash('moderator123')
            db.session.add(moderator)
            db.session.commit()
            print("✅ Создан новый модератор: moderator@test.ru / moderator123")
        else:
            # Обновляем права существующего модератора
            moderator.is_moderator = True
            db.session.commit()
            print("✅ Права модератора обновлены")


# Маршруты управления пользователями для модератора
@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/user/<int:user_id>/toggle_ban')
@login_required
def admin_toggle_ban_user(user_id):
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)

    # Не позволяем банить других модераторов
    if user.is_moderator:
        flash('Нельзя заблокировать другого модератора')
        return redirect(url_for('admin_users'))

    user.is_active = not user.is_active
    status = "заблокирован" if not user.is_active else "разблокирован"

    # Создаем уведомление для пользователя
    if not user.is_active:  # Если пользователь заблокирован
        notification = Notification(
            user_id=user.id,
            title='Аккаунт заблокирован',
            message='Ваш аккаунт был заблокирован модератором. Для выяснения причин обратитесь в поддержку.',
            notification_type='warning'
        )
        db.session.add(notification)

    db.session.commit()

    flash(f'Пользователь {user.username} {status}')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:user_id>/delete')
@login_required
def admin_delete_user(user_id):
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)

    # Не позволяем удалять других модераторов
    if user.is_moderator:
        flash('Нельзя удалить другого модератора')
        return redirect(url_for('admin_users'))

    # Собираем информацию для лога
    username = user.username
    projects_count = Project.query.filter_by(client_id=user.id).count()
    responses_count = ProjectResponse.query.filter_by(freelancer_id=user.id).count()

    # Удаляем связанные данные пользователя
    # 1. Уведомления
    Notification.query.filter_by(user_id=user.id).delete()

    # 2. Сообщения
    Message.query.filter_by(sender_id=user.id).delete()
    Message.query.filter_by(receiver_id=user.id).delete()

    # 3. Отклики на проекты
    ProjectResponse.query.filter_by(freelancer_id=user.id).delete()

    # 4. Профиль
    if user.profile:
        db.session.delete(user.profile)

    # 5. Отзывы
    Review.query.filter_by(reviewer_id=user.id).delete()
    Review.query.filter_by(freelancer_id=user.id).delete()

    # 6. Обращения в поддержку
    SupportTicket.query.filter_by(user_id=user.id).delete()
    TicketMessage.query.filter_by(user_id=user.id).delete()

    # 7. Проекты пользователя (если он заказчик)
    user_projects = Project.query.filter_by(client_id=user.id).all()
    for project in user_projects:
        # Удаляем отклики на эти проекты
        ProjectResponse.query.filter_by(project_id=project.id).delete()
        # Удаляем отзывы на эти проекты
        Review.query.filter_by(project_id=project.id).delete()
        # Удаляем проект
        db.session.delete(project)

    # 8. Удаляем самого пользователя
    db.session.delete(user)
    db.session.commit()

    flash(f'Пользователь {username} удален (проектов: {projects_count}, откликов: {responses_count})')
    return redirect(url_for('admin_users'))


# Маршруты управления проектами для модератора
@app.route('/admin/projects')
@login_required
def admin_projects():
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')

    query = Project.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    if search:
        query = query.filter(Project.title.contains(search) | Project.description.contains(search))

    projects = query.order_by(Project.created_at.desc()).all()
    return render_template('admin_projects.html', projects=projects, status_filter=status_filter, search=search)


@app.route('/admin/project/<int:project_id>/delete')
@login_required
def admin_delete_project(project_id):
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    project = Project.query.get_or_404(project_id)

    # Собираем информацию для уведомления
    project_title = project.title
    client_username = project.client.username

    # Удаляем связанные данные проекта
    # 1. Отклики на проект
    ProjectResponse.query.filter_by(project_id=project_id).delete()

    # 2. Отзывы на проект
    Review.query.filter_by(project_id=project_id).delete()

    # 3. Уведомления, связанные с проектом
    Notification.query.filter_by(related_id=project_id).delete()

    # 4. Удаляем сам проект
    db.session.delete(project)
    db.session.commit()

    # Создаем уведомление для владельца проекта
    notification = Notification(
        user_id=project.client_id,
        title='Проект удален модератором',
        message=f'Ваш проект "{project_title}" был удален модератором за нарушение правил платформы.',
        notification_type='warning'
    )
    db.session.add(notification)
    db.session.commit()

    flash(f'Проект "{project_title}" (автор: {client_username}) удален')
    return redirect(url_for('admin_projects'))


@app.route('/admin/project/<int:project_id>/toggle_status')
@login_required
def admin_toggle_project_status(project_id):
    if not current_user.is_moderator:
        flash('Доступ запрещен')
        return redirect(url_for('index'))

    project = Project.query.get_or_404(project_id)

    # Переключаем статус проекта
    if project.status == 'open':
        project.status = 'hidden'
        status_msg = "скрыт"
    elif project.status == 'hidden':
        project.status = 'open'
        status_msg = "восстановлен"
    else:
        flash('Нельзя изменить статус проекта в работе или завершенного')
        return redirect(url_for('admin_projects'))

    db.session.commit()

    # Уведомление владельцу проекта
    notification = Notification(
        user_id=project.client_id,
        title=f'Проект {status_msg}',
        message=f'Ваш проект "{project.title}" был {status_msg} модератором.',
        notification_type='warning' if status_msg == 'скрыт' else 'system'
    )
    db.session.add(notification)
    db.session.commit()

    flash(f'Проект "{project.title}" {status_msg}')
    return redirect(url_for('admin_projects'))


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

        # уведомление о создании профиля
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
    # для фрилансеров без профиля - редирект на создание
    if not current_user.is_client and not current_user.profile:
        return redirect(url_for('create_profile'))

    if current_user.is_client:
        # для заказчика
        user_projects_active = Project.query.filter(
            Project.client_id == current_user.id,
            Project.status.in_(['open', 'in_progress'])
        ).order_by(Project.created_at.desc()).all()

        user_projects_completed = Project.query.filter(
            Project.client_id == current_user.id,
            Project.status == 'completed'
        ).order_by(Project.completed_at.desc()).all()

        # статистика заказчика
        total_budget = sum(project.budget for project in user_projects_completed)

        # рейтинг заказчика
        client_reviews = Review.query.join(Project).filter(
            Project.client_id == current_user.id
        ).all()
        client_rating = sum(review.rating for review in client_reviews) / len(client_reviews) if client_reviews else 0

        return render_template('view_profile.html',
                               user_projects_active=user_projects_active,
                               user_projects_completed=user_projects_completed,
                               total_budget=total_budget,
                               client_rating=client_rating)
    else:
        # для фрилансера
        freelancer_projects_active = Project.query.filter(
            Project.freelancer_id == current_user.id,
            Project.status == 'in_progress'
        ).order_by(Project.created_at.desc()).all()

        freelancer_projects_completed = Project.query.filter(
            Project.freelancer_id == current_user.id,
            Project.status == 'completed'
        ).order_by(Project.completed_at.desc()).all()

        freelancer_reviews = Review.query.filter_by(
            freelancer_id=current_user.id
        ).order_by(Review.created_at.desc()).all()

        return render_template('view_profile.html',
                               freelancer_projects_active=freelancer_projects_active,
                               freelancer_projects_completed=freelancer_projects_completed,
                               freelancer_reviews=freelancer_reviews,
                               get_freelancer_rating=get_freelancer_rating)


@app.route('/projects')
def projects():
    category = request.args.get('category')
    search = request.args.get('search')
    status_filter = request.args.get('status', 'open')

    query = Project.query

    # для обычных пользователей скрываем проекты со статусом 'скрытые'
    if not current_user.is_authenticated or not current_user.is_moderator:
        query = query.filter(Project.status != 'hidden')

    # фильтр по статусу
    if status_filter == 'open':
        query = query.filter_by(status='open')
    elif status_filter == 'in_progress':
        query = query.filter_by(status='in_progress')
    elif status_filter == 'completed':
        query = query.filter_by(status='completed')

    if category:
        query = query.filter(Project.category.contains(category))
    if search:
        query = query.filter(Project.title.contains(search) | Project.description.contains(search))

    projects = query.order_by(Project.created_at.desc()).all()
    return render_template('projects.html', projects=projects, status_filter=status_filter)


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

        # уведомление о создании проекта
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


# принять отклик
@app.route('/project/<int:project_id>/accept_response/<int:response_id>')
@login_required
def accept_project_response(project_id, response_id):
    project = Project.query.get_or_404(project_id)
    response = ProjectResponse.query.get_or_404(response_id)

    # проверяем что текущий пользователь - владелец проекта
    if project.client_id != current_user.id:
        flash('Доступ запрещен')
        return redirect(url_for('project_detail', project_id=project_id))

    # назначаем фрилансера и меняем статус проекта
    project.freelancer_id = response.freelancer_id
    project.status = 'in_progress'
    response.status = 'accepted'

    # отклоняем остальные отклики
    other_responses = ProjectResponse.query.filter_by(project_id=project_id).filter(
        ProjectResponse.id != response_id
    ).all()

    for other_response in other_responses:
        other_response.status = 'rejected'
        # уведомление другим фрилансерам
        notification = Notification(
            user_id=other_response.freelancer_id,
            title='Отклик отклонен',
            message=f'Ваш отклик на проект "{project.title}" был отклонен. Заказчик выбрал другого исполнителя.',
            notification_type='project_response',
            related_id=project.id
        )
        db.session.add(notification)

    # уведомление выбранному фрилансеру
    accepted_notification = Notification(
        user_id=response.freelancer_id,
        title='Ваш отклик принят!',
        message=f'Заказчик принял ваш отклик на проект "{project.title}". Начинайте работу!',
        notification_type='project_accepted',
        related_id=project.id
    )
    db.session.add(accepted_notification)

    # автоматически создаем первое сообщение в чате
    welcome_message = Message(
        sender_id=current_user.id,
        receiver_id=response.freelancer_id,
        content=f'Здравствуйте! Я принял ваш отклик на проект "{project.title}". Давайте обсудим детали сотрудничества.'
    )
    db.session.add(welcome_message)

    db.session.commit()

    flash('✅ Фрилансер назначен! Проект переведен в статус "В работе". Чат создан автоматически.')
    return redirect(url_for('project_detail', project_id=project_id))

# завершить проект
@app.route('/project/<int:project_id>/complete')
@login_required
def complete_project(project_id):
    project = Project.query.get_or_404(project_id)

    # проверяем, что пользователь - владелец проекта или назначенный фрилансер
    if project.client_id != current_user.id and project.freelancer_id != current_user.id:
        flash('Доступ запрещен')
        return redirect(url_for('project_detail', project_id=project_id))

    project.status = 'completed'
    project.completed_at = datetime.now(timezone.utc)

    # уведомление второй стороне
    other_user_id = project.freelancer_id if current_user.id == project.client_id else project.client_id
    notification = Notification(
        user_id=other_user_id,
        title='Проект завершен!',
        message=f'Проект "{project.title}" был завершен.',
        notification_type='project_completed',
        related_id=project.id
    )
    db.session.add(notification)

    db.session.commit()

    flash('✅ Проект завершен! Теперь можно оставить отзыв об исполнителе.')
    return redirect(url_for('project_detail', project_id=project_id))

# отменить проект
@app.route('/project/<int:project_id>/cancel')
@login_required
def cancel_project(project_id):
    project = Project.query.get_or_404(project_id)

    # только владелец может отменить проект
    if project.client_id != current_user.id:
        flash('Доступ запрещен')
        return redirect(url_for('project_detail', project_id=project_id))

    project.status = 'cancelled'

    # уведомление фрилансеру, если он был назначен
    if project.freelancer_id:
        notification = Notification(
            user_id=project.freelancer_id,
            title='Проект отменен',
            message=f'Проект "{project.title}" был отменен заказчиком.',
            notification_type='project_cancelled',
            related_id=project.id
        )
        db.session.add(notification)

    db.session.commit()

    flash('⚠️ Проект отменен')
    return redirect(url_for('project_detail', project_id=project_id))




# отклик на проект
@app.route('/project/<int:project_id>/respond', methods=['POST'])
@login_required
def respond_to_project(project_id):
    if current_user.is_client:
        flash('Заказчики не могут откликаться на проекты')
        return redirect(url_for('project_detail', project_id=project_id))

    project = Project.query.get_or_404(project_id)

    # проверка не откликался ли пользователь
    existing_response = ProjectResponse.query.filter_by(
        project_id=project_id,
        freelancer_id=current_user.id
    ).first()

    if existing_response:
        flash('Вы уже откликались на этот проект')
        return redirect(url_for('project_detail', project_id=project_id))

    # создание отклика
    response = ProjectResponse(
        project_id=project_id,
        freelancer_id=current_user.id,
        message=request.form.get('message', ''),
        proposed_budget=float(request.form.get('proposed_budget', project.budget))
    )
    db.session.add(response)

    # Создаем уведомление для владельца проекта
    notification = Notification(
        user_id=project.client_id,
        title='Новый отклик на ваш проект!',
        message=f'Пользователь {current_user.username} откликнулся на ваш проект "{project.title}".',
        notification_type='project_response',
        related_id=project.id
    )
    db.session.add(notification)

    db.session.commit()

    flash('✅ Отклик отправлен! Заказчик получил уведомление.')
    return redirect(url_for('project_detail', project_id=project_id))


# уведомления
@app.route('/notifications')
@login_required
def notifications():
    user_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    return render_template('notifications.html', notifications=user_notifications)


# удаление уведомления
@app.route('/notifications/delete/<int:notification_id>')
@login_required
def delete_notification(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()

    db.session.delete(notification)
    db.session.commit()

    flash('Уведомление удалено')
    return redirect(url_for('notifications'))


# удаление всех прочитанных уведомлений
@app.route('/notifications/delete_read')
@login_required
def delete_read_notifications():
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).delete()

    db.session.commit()

    flash('Все прочитанные уведомления удалены')
    return redirect(url_for('notifications'))


# удаление всех уведомлений
@app.route('/notifications/delete_all')
@login_required
def delete_all_notifications():
    Notification.query.filter_by(
        user_id=current_user.id
    ).delete()

    db.session.commit()

    flash('Все уведомления удалены')
    return redirect(url_for('notifications'))


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


@app.route('/api/send_message', methods=['POST'])
@login_required
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
    print(
        f"🔍 Проверка прав пользователя {current_user.username}: is_moderator = {current_user.is_moderator}")  # Для отладки

    if not current_user.is_moderator:
        flash('Доступ запрещен. Только модераторы могут просматривать эту страницу.')
        return redirect(url_for('index'))

    # Получаем ВСЕ обращения (не только открытые)
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
    """Инициализация базы данных - ПЕРЕСОЗДАЕТ ВСЕ ТАБЛИЦЫ"""
    with app.app_context():
        db.drop_all()  # Удаляем все таблицы
        db.create_all()  # Создаем заново с новыми полями

        # Создаем ТОЛЬКО модератора
        moderator = User(
            username='moderator',
            email='moderator@test.ru',
            is_moderator=True
        )
        moderator.password_hash = generate_password_hash('moderator123')
        db.session.add(moderator)
        db.session.commit()


# Добавьте эту функцию ПЕРЕД if __name__ == '__main__':

def check_and_migrate_database():
    """Проверяет и обновляет структуру базы данных при необходимости"""
    with app.app_context():
        try:
            print("🔍 Проверяем структуру базы данных...")

            # Проверяем существование таблицы project
            result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='project'"))
            if not result.fetchone():
                print("❌ Таблица project не найдена. Запустите init_db() сначала.")
                return False

            # Проверяем существование полей в таблице project
            result = db.session.execute(text("PRAGMA table_info(project)"))
            columns = [row[1] for row in result]
            migrations_applied = 0

            # Список полей для добавления
            fields_to_add = [
                ('technologies', 'VARCHAR(500)'),
                ('freelancer_id', 'INTEGER REFERENCES user(id)'),
                ('completed_at', 'DATETIME')
            ]

            for field_name, field_type in fields_to_add:
                if field_name not in columns:
                    print(f"📝 Добавляем поле {field_name} в таблицу project...")
                    db.session.execute(text(f"ALTER TABLE project ADD COLUMN {field_name} {field_type}"))
                    migrations_applied += 1
                    print(f"✅ Поле {field_name} добавлено!")
                else:
                    print(f"✅ Поле {field_name} уже существует")

            # Проверяем существование таблицы project_response
            result = db.session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='project_response'"))
            if not result.fetchone():
                print("📝 Создаем таблицу project_response...")
                db.session.execute(text("""
                    CREATE TABLE project_response (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        freelancer_id INTEGER NOT NULL,
                        message TEXT,
                        proposed_budget FLOAT,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (project_id) REFERENCES project (id),
                        FOREIGN KEY (freelancer_id) REFERENCES user (id)
                    )
                """))
                migrations_applied += 1
                print("✅ Таблица project_response создана!")
            else:
                print("✅ Таблица project_response уже существует")

            if migrations_applied > 0:
                db.session.commit()
                print(f"🎉 Применено {migrations_applied} миграций! База данных обновлена.")
            else:
                print("✅ База данных уже актуальна. Миграции не требуются.")

            return True

        except Exception as e:
            print(f"❌ Ошибка при проверке базы данных: {e}")
            db.session.rollback()
            return False


# ОБНОВИТЕ функцию init_db() чтобы она создавала все нужные таблицы:

def init_db():
    """Инициализация базы данных - ТОЛЬКО модератор и базовые таблицы"""
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Создаем ТОЛЬКО модератора
        moderator = User(
            username='moderator',
            email='moderator@test.ru',
            is_moderator=True
        )
        moderator.password_hash = generate_password_hash('moderator123')

        db.session.add(moderator)
        db.session.commit()

        print("✅ База данных инициализирована!")
        print("🔑 Модератор - moderator@test.ru / moderator123")
        print("")
        print("Для тестирования:")
        print("1. Зарегистрируйте новых пользователей")
        print("2. Создайте проекты")
        print("3. Тестируйте функционал с чистого листа")


def migrate_database():
    """Миграция базы данных для добавления недостающих таблиц и полей"""
    with app.app_context():
        try:
            print("🔄 Проверяем необходимость миграций...")

            # Проверяем существование таблицы review
            result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='review'"))
            if not result.fetchone():
                print("📝 Создаем таблицу review...")
                db.session.execute(text("""
                    CREATE TABLE review (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        reviewer_id INTEGER NOT NULL,
                        freelancer_id INTEGER NOT NULL,
                        rating INTEGER NOT NULL,
                        comment TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (project_id) REFERENCES project (id),
                        FOREIGN KEY (reviewer_id) REFERENCES user (id),
                        FOREIGN KEY (freelancer_id) REFERENCES user (id)
                    )
                """))
                print("✅ Таблица review создана!")
            else:
                # Проверяем существование поля freelancer_id в таблице review
                result = db.session.execute(text("PRAGMA table_info(review)"))
                columns = [row[1] for row in result]

                if 'freelancer_id' not in columns:
                    print("📝 Добавляем поле freelancer_id в таблицу review...")
                    db.session.execute(text("ALTER TABLE review ADD COLUMN freelancer_id INTEGER NOT NULL DEFAULT 1"))
                    db.session.execute(text("ALTER TABLE review ADD FOREIGN KEY (freelancer_id) REFERENCES user(id)"))
                    print("✅ Поле freelancer_id добавлено!")

            db.session.commit()
            print("🎉 Миграция базы данных завершена!")
            return True

        except Exception as e:
            print(f"❌ Ошибка при миграции базы данных: {e}")
            db.session.rollback()
            return False


if __name__ == '__main__':
    # Проверяем и обновляем базу данных при каждом запуске
    if not os.path.exists('instance/freelance.db'):
        print("🆕 База данных не найдена. Создаем новую...")
        init_db()
    else:
        print("🔍 База данных найдена. Проверяем структуру...")
        check_and_migrate_database()
        migrate_database()  # Добавляем вызов функции миграции

    print("🚀 Запуск приложения...")
    app.run(debug=True, port=5001, host='0.0.0.0')
