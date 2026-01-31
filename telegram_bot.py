"""
Telegram бот для управления задачами с AI помощником
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

from sqlalchemy.orm import Session
from database import init_db, SessionLocal, User, Task, Goal
from ai_agent import AIAgent, create_agent

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
SETUP_AGENT_NAME, SETUP_AGENT_PROMPT = range(2)
CREATE_TASK, CREATE_GOAL = range(2, 4)


class TaskManagerBot:
    """Класс для управления ботом"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        
        self.ai_agent = create_agent()
        init_db()
    
    def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None) -> User:
        """Получить или создать пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        finally:
            db.close()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        telegram_user = update.effective_user
        user = self.get_or_create_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name
        )
        
        welcome_text = f"""
👋 Привет, {user.first_name}!

Я твой персональный AI помощник для управления задачами и целями.

🤖 Мой текущий агент: **{user.agent_name}**

**Что я умею:**
• 📝 Создавать задачи из твоих сообщений
• 🎯 Управлять целями
• 📅 Планировать по календарю
• 🔔 Напоминать о важном
• 💡 Давать советы по продуктивности

**Команды:**
/tasks - Мои задачи
/goals - Мои цели
/today - План на сегодня
/agent - Настроить AI агента
/help - Помощь

Просто напиши мне что нужно сделать, и я помогу это организовать! 🚀
"""
        
        # Клавиатура с быстрыми действиями
        keyboard = [
            [KeyboardButton("📝 Новая задача"), KeyboardButton("🎯 Новая цель")],
            [KeyboardButton("📋 Мои задачи"), KeyboardButton("📊 Мои цели")],
            [KeyboardButton("📅 Сегодня"), KeyboardButton("⚙️ Настройки")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
📚 **Руководство пользователя**

**Создание задач:**
Просто напиши что нужно сделать:
• "Купить молоко завтра в 10:00"
• "Закончить отчёт к пятнице"
• "Позвонить Маше, это важно"

AI автоматически определит:
- Название задачи
- Дату и время
- Приоритет

**Работа с целями:**
/goals - Список целей
Создай цель и AI предложит подзадачи!

**Календарь:**
/today - Задачи на сегодня
/week - План на неделю

**Настройка AI:**
/agent - Настроить своего помощника
Можешь дать ему имя и особые инструкции!

**Быстрые кнопки:**
Используй кнопки внизу для быстрого доступа к функциям.
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def tasks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tasks - показать все задачи"""
        telegram_user = update.effective_user
        user = self.get_or_create_user(telegram_user.id)
        
        db = SessionLocal()
        try:
            # Получаем незавершённые задачи
            tasks = db.query(Task).filter(
                Task.user_id == user.id,
                Task.completed == False
            ).order_by(Task.scheduled_date.asc()).all()
            
            if not tasks:
                await update.message.reply_text("📝 У вас пока нет активных задач.\n\nПросто напишите мне что нужно сделать!")
                return
            
            # Формируем список задач
            text = f"📋 **Ваши задачи ({len(tasks)}):**\n\n"
            
            for i, task in enumerate(tasks[:10], 1):  # Показываем максимум 10
                priority_emoji = {"low": "🔵", "medium": "🟡", "high": "🔴"}.get(task.priority, "⚪")
                date_str = task.scheduled_date.strftime("%d.%m %H:%M") if task.scheduled_date else "без даты"
                
                text += f"{priority_emoji} **{i}. {task.title}**\n"
                text += f"   📅 {date_str}\n"
                if task.description:
                    text += f"   💭 {task.description[:50]}...\n"
                text += "\n"
            
            # Кнопки для управления
            keyboard = [
                [InlineKeyboardButton("✅ Отметить выполненной", callback_data="complete_task")],
                [InlineKeyboardButton("🗑 Удалить задачу", callback_data="delete_task")],
                [InlineKeyboardButton("📝 Создать новую", callback_data="new_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        finally:
            db.close()
    
    async def goals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /goals - показать цели"""
        telegram_user = update.effective_user
        user = self.get_or_create_user(telegram_user.id)
        
        db = SessionLocal()
        try:
            goals = db.query(Goal).filter(
                Goal.user_id == user.id,
                Goal.completed == False
            ).all()
            
            if not goals:
                text = "🎯 У вас пока нет активных целей.\n\nСоздайте цель, и я помогу разбить её на задачи!"
                keyboard = [[InlineKeyboardButton("➕ Создать цель", callback_data="new_goal")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(text, reply_markup=reply_markup)
                return
            
            text = f"🎯 **Ваши цели ({len(goals)}):**\n\n"
            
            for i, goal in enumerate(goals, 1):
                # Считаем прогресс
                total_tasks = len(goal.tasks)
                completed_tasks = sum(1 for t in goal.tasks if t.completed)
                progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                
                text += f"**{i}. {goal.title}**\n"
                if total_tasks > 0:
                    text += f"   📊 Прогресс: {completed_tasks}/{total_tasks} ({progress:.0f}%)\n"
                if goal.deadline:
                    text += f"   ⏰ Срок: {goal.deadline.strftime('%d.%m.%Y')}\n"
                text += "\n"
            
            keyboard = [
                [InlineKeyboardButton("➕ Новая цель", callback_data="new_goal")],
                [InlineKeyboardButton("📋 Подробнее", callback_data="goal_details")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        finally:
            db.close()
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /today - задачи на сегодня"""
        telegram_user = update.effective_user
        user = self.get_or_create_user(telegram_user.id)
        
        db = SessionLocal()
        try:
            # Задачи на сегодня
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            today_end = today_start + timedelta(days=1)
            
            tasks_today = db.query(Task).filter(
                Task.user_id == user.id,
                Task.completed == False,
                Task.scheduled_date >= today_start,
                Task.scheduled_date < today_end
            ).all()
            
            # Получаем AI сводку
            tasks_data = [{"title": t.title} for t in tasks_today]
            goals_data = [{"title": g.title} for g in user.goals if not g.completed]
            
            summary = await self.ai_agent.daily_summary(tasks_data[:5], goals_data[:3])
            
            text = f"📅 **План на сегодня**\n\n{summary}\n\n"
            
            if tasks_today:
                text += f"**Задачи ({len(tasks_today)}):**\n"
                for i, task in enumerate(tasks_today, 1):
                    time_str = task.scheduled_date.strftime("%H:%M") if task.scheduled_date else ""
                    text += f"{i}. {task.title} {time_str}\n"
            else:
                text += "✨ На сегодня задач нет! Отличный день для отдыха или новых начинаний.\n"
            
            await update.message.reply_text(text, parse_mode='Markdown')
        
        finally:
            db.close()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка обычных сообщений - создание задач через AI"""
        text = update.message.text
        telegram_user = update.effective_user
        user = self.get_or_create_user(telegram_user.id)
        
        # Обработка кнопок
        if text == "📝 Новая задача" or text == "📋 Мои задачи":
            return await self.tasks_command(update, context)
        elif text == "🎯 Новая цель" or text == "📊 Мои цели":
            return await self.goals_command(update, context)
        elif text == "📅 Сегодня":
            return await self.today_command(update, context)
        elif text == "⚙️ Настройки":
            return await self.agent_command(update, context)
        
        # Парсим задачу через AI
        await update.message.reply_text("🤖 Обрабатываю вашу задачу...")
        
        try:
            task_data = await self.ai_agent.parse_task_from_text(text)
            
            db = SessionLocal()
            try:
                # Создаём задачу
                new_task = Task(
                    user_id=user.id,
                    title=task_data.get("title", text[:50]),
                    description=task_data.get("description"),
                    priority=task_data.get("priority", "medium"),
                    scheduled_date=self._parse_datetime(task_data.get("scheduled_date"))
                )
                db.add(new_task)
                db.commit()
                
                # Подтверждение
                priority_emoji = {"low": "🔵", "medium": "🟡", "high": "🔴"}.get(new_task.priority, "⚪")
                confirm_text = f"✅ Задача создана!\n\n"
                confirm_text += f"{priority_emoji} **{new_task.title}**\n"
                if new_task.scheduled_date:
                    confirm_text += f"📅 {new_task.scheduled_date.strftime('%d.%m.%Y %H:%M')}\n"
                
                await update.message.reply_text(confirm_text, parse_mode='Markdown')
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Ошибка создания задачи: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте ещё раз или используйте /help")
    
    async def agent_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /agent - настройка AI агента"""
        telegram_user = update.effective_user
        user = self.get_or_create_user(telegram_user.id)
        
        text = f"""
🤖 **Настройки AI Агента**

Текущее имя: **{user.agent_name}**
Промпт: {user.agent_prompt[:100]}...

Вы можете настроить своего AI помощника:
• Дать ему имя
• Задать особую роль или инструкции
• Изменить стиль общения

Что хотите изменить?
"""
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data="change_agent_name")],
            [InlineKeyboardButton("📝 Изменить промпт", callback_data="change_agent_prompt")],
            [InlineKeyboardButton("🔄 Сброс по умолчанию", callback_data="reset_agent")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Парсинг даты из строки"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except:
            return None
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.token).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("tasks", self.tasks_command))
        application.add_handler(CommandHandler("goals", self.goals_command))
        application.add_handler(CommandHandler("today", self.today_command))
        application.add_handler(CommandHandler("agent", self.agent_command))
        
        # Обработчик обычных сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Запуск
        logger.info("🚀 Бот запущен!")
        print("✅ Бот работает. Нажмите Ctrl+C для остановки.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = TaskManagerBot()
    bot.run()
