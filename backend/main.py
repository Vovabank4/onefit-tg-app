from fastapi import FastAPI
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.storage.memory import MemoryStorage
from db import init_db, SessionLocal, User, UserRole, PendingInvite, Reminder
from sqlalchemy.future import select
from aiogram.filters import Command
import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError
from aiogram import Router
import logging

# Указываем токен бота напрямую
BOT_TOKEN = "7838089838:AAF0xUGyDsKI3g3pG2JfEtfDR7Tq9X7G_iQ"

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "OneFit backend работает!"}

# --- Telegram bot setup ---

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# @dp.message()
# async def echo_handler(message: Message):
#     await message.answer("Привет! Я OneFit-бот. Скоро здесь будет фитнес-магия 💪")

# --- Кнопки выбора роли ---
def get_role_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тренер 💪", callback_data="role_trainer")],
            [InlineKeyboardButton(text="Подопечный 🏃", callback_data="role_client")],
        ]
    )

# --- Кнопки подтверждения удаления профиля ---
def get_delete_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить ❌", callback_data="delete_yes")],
            [InlineKeyboardButton(text="Нет, отменить", callback_data="delete_no")],
        ]
    )

# --- Универсальная клавиатура ---
def get_main_keyboard(role: str = None):
    if role == "trainer":
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Мои тренировки")],
            [KeyboardButton(text="👥 Мои клиенты"), KeyboardButton(text="➕ Добавить клиента")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ]
    elif role == "client":
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Мои тренировки")],
            [KeyboardButton(text="👨‍🏫 Мои тренеры"), KeyboardButton(text="ℹ️ Помощь")],
        ]
    else:
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Мои тренировки")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- START/CHANGEROLE с кнопками ---
@dp.message(Command("start"))
async def start_handler(message: Message):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user:
            if user.username != message.from_user.username:
                user.username = message.from_user.username
                await session.commit()
            await message.answer(
                f"👋 <b>Привет, {user.full_name or user.username}!</b>\nВаша роль: <b>{user.role.value if user.role else 'не выбрана'}</b>",
                parse_mode="HTML",
                reply_markup=get_main_keyboard(user.role.value if user.role else None)
            )
        else:
            new_user = User(
                telegram_id=str(message.from_user.id),
                username=message.from_user.username,
                full_name=message.from_user.full_name,
                role=None
            )
            session.add(new_user)
            await session.commit()
            username = (message.from_user.username or "").lower()
            if not username:
                await message.answer("У вас не установлен username в Telegram. Пожалуйста, установите его в настройках Telegram и повторите попытку.")
            else:
                result = await session.execute(select(PendingInvite))
                invites = result.scalars().all()
                invite = next((i for i in invites if i.username and i.username.lower() == username), None)
                if invite:
                    result = await session.execute(select(User).where(User.id == invite.trainer_id))
                    trainer = result.scalar_one_or_none()
                    if trainer:
                        await message.answer(f"Вас пригласил тренер @{trainer.username or trainer.full_name} в OneFit! Теперь вы можете вести дневник и получать задания.")
                        from db import TrainerClient
                        trainer_client = TrainerClient(trainer_id=trainer.id, client_id=new_user.id)
                        session.add(trainer_client)
                        new_user.role = UserRole.client
                        await session.commit()
                        await message.answer("Ваша роль автоматически установлена как 'подопечный'. Если хотите сменить роль — используйте /changerole после регистрации.")
                    await session.delete(invite)
                    await session.commit()
                    return
            await message.answer(
                "<b>Добро пожаловать в OneFit!</b>\n\nПожалуйста, выберите свою роль:",
                reply_markup=get_role_keyboard(),
                parse_mode="HTML"
            )

# --- Callback для выбора роли ---
from aiogram import F
@dp.callback_query(F.data.in_(["role_trainer", "role_client"]))
async def role_callback_handler(callback: types.CallbackQuery):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        if user.role:
            await callback.answer("Роль уже выбрана. Используйте /changerole для смены.", show_alert=True)
            return
        if callback.data == "role_trainer":
            user.role = UserRole.trainer
            await session.commit()
            await callback.message.edit_text("Вы выбрали роль: <b>Тренер 💪</b>", parse_mode="HTML")
        elif callback.data == "role_client":
            user.role = UserRole.client
            await session.commit()
            await callback.message.edit_text("Вы выбрали роль: <b>Подопечный 🏃</b>", parse_mode="HTML")
        await callback.answer()

# --- CHANGEROLE с кнопками ---
@dp.message(Command("changerole"))
async def changerole_handler(message: Message):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        user.role = None
        await session.commit()
        await message.answer(
            "Выберите новую роль:",
            reply_markup=get_role_keyboard()
        )

# --- Удаление профиля с кнопками ---
@dp.message(Command("deleteprofile"))
async def deleteprofile_start(message: Message, state: FSMContext):
    await message.answer(
        "<b>Вы уверены, что хотите удалить свой профиль и все данные?</b> Это действие необратимо.",
        reply_markup=get_delete_confirm_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(DeleteProfileStates.waiting_confirm)

@dp.callback_query(F.data.in_(["delete_yes", "delete_no"]))
async def deleteprofile_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "delete_yes":
        async with SessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
            user = result.scalar_one_or_none()
            if user:
                from db import TrainerClient, Workout, Reminder, PendingInvite
                await session.execute(TrainerClient.__table__.delete().where((TrainerClient.trainer_id == user.id) | (TrainerClient.client_id == user.id)))
                await session.execute(Workout.__table__.delete().where((Workout.trainer_id == user.id) | (Workout.client_id == user.id)))
                await session.execute(Reminder.__table__.delete().where(Reminder.user_id == user.id))
                await session.execute(PendingInvite.__table__.delete().where(PendingInvite.trainer_id == user.id))
                await session.delete(user)
                await session.commit()
                await callback.message.edit_text("Ваш профиль и все данные <b>удалены</b>. Спасибо, что пользовались OneFit!", parse_mode="HTML")
            else:
                await callback.message.edit_text("Профиль не найден.")
        await state.clear()
    else:
        await callback.message.edit_text("Удаление отменено.")
        await state.clear()
    await callback.answer()

# --- Улучшение сообщений (пример для /about) ---
@dp.message(Command("about"))
async def about_handler(message: Message):
    about_text = (
        "<b>OneFit</b> — фитнес-бот для тренеров и подопечных 🏋️‍♂️\n\n"
        "OneFit помогает тренерам вести клиентов, назначать тренировки и напоминания, а подопечным — отслеживать свой прогресс и получать задания.\n"
        "Бот прост в использовании, не требует установки приложений и работает прямо в Telegram.\n\n"
        "<b>Автор:</b> <a href='https://t.me/ChursinVldmr'>@ChursinVldmr</a>\n"
        "По вопросам и предложениям — пишите автору!"
    )
    await message.answer(about_text, parse_mode="HTML")

# --- Аналогично можно улучшить другие сообщения (пример для /help, /privacy и т.д.) ---

@dp.message(Command("addclient"))
async def add_client_handler(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Используй команду так: /addclient username_клиента")
        return
    username = args[1].lstrip("@").lower()
    async with SessionLocal() as session:
        # Проверяем, что отправитель — тренер
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять клиентов.")
            return
        # Ищем клиента по username (без учёта регистра)
        result = await session.execute(select(User))
        users = result.scalars().all()
        client = next((u for u in users if u.username and u.username.lower() == username), None)
        if not client:
            # Если клиента нет — создаём приглашение
            invite = PendingInvite(username=username, trainer_id=trainer.id)
            session.add(invite)
            await session.commit()
            await message.answer("Клиенту отправлено приглашение! Как только он напишет боту, он получит уведомление.")
            return
        # Проверяем, есть ли уже связь
        from db import TrainerClient
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if link:
            await message.answer("Этот клиент уже добавлен.")
            return
        # Создаём связь
        new_link = TrainerClient(trainer_id=trainer.id, client_id=client.id)
        session.add(new_link)
        await session.commit()
        await message.answer(f"Клиент @{client.username} успешно добавлен!")
        # Отправляем уведомление клиенту
        try:
            await bot.send_message(client.telegram_id, f"Вас добавил тренер @{trainer.username or trainer.full_name} в OneFit! Теперь вы можете вести дневник и получать задания.")
        except Exception:
            pass

@dp.message(Command("myclients"))
async def my_clients_handler(message: Message):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может просматривать список клиентов.")
            return
        from db import TrainerClient, Workout
        result = await session.execute(
            select(TrainerClient, User)
            .join(User, TrainerClient.client_id == User.id)
            .where(TrainerClient.trainer_id == trainer.id)
        )
        clients = result.all()
        if not clients:
            await message.answer("У тебя пока нет клиентов.")
            return
        for client_link, client in clients:
            # Считаем тренировки и находим последнюю
            result = await session.execute(
                select(Workout).where(Workout.client_id == client.id, Workout.trainer_id == trainer.id).order_by(Workout.date.desc())
            )
            workouts = result.scalars().all()
            count = len(workouts)
            last_date = workouts[0].date.date() if workouts else None
            days_ago = (datetime.date.today() - last_date).days if last_date else None
            text = f"<b>Клиент:</b> {client.full_name or '-'} (@{client.username or '-'})\n"
            text += f"Тренировок: {count}\n"
            if last_date:
                text += f"Последняя тренировка: {last_date} ({days_ago} дн. назад)\n"
                if days_ago > 7:
                    text += "Статус: не тренировался больше недели!\n"
                else:
                    text += "Статус: активен\n"
            else:
                text += "Тренировок пока не было.\n"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Профиль клиента", callback_data=f"clientinfo_{client.username.lower()}")]]
            )
            await message.answer(text, parse_mode="HTML", reply_markup=kb)

def get_client_profile_text(client, trainer, workouts):
    count = len(workouts)
    last_date = workouts[0].date.date() if workouts else None
    days_ago = (datetime.date.today() - last_date).days if last_date else None
    msg = f"<b>Профиль @{client.username or ''}</b>\n"
    msg += f"ФИО: {client.full_name or '-'}\n"
    msg += f"Пол: {client.gender or '-'}\n"
    msg += f"Возраст: {client.age or '-'}\n"
    msg += f"Вес: {client.weight or '-'} кг\n"
    msg += f"Рост: {client.height or '-'} см\n"
    msg += f"Цель: {client.goal or '-'}\n"
    msg += f"Всего тренировок: {count}\n"
    if last_date:
        msg += f"Последняя тренировка: {last_date} ({days_ago} дн. назад)\n"
        if days_ago > 7:
            msg += "Статус: не тренировался больше недели!\n"
        else:
            msg += "Статус: активен\n"
    else:
        msg += "Тренировок пока не было.\n"
    return msg

@dp.callback_query(F.data.startswith("clientinfo_"))
async def clientinfo_callback(callback: types.CallbackQuery, state: FSMContext):
    username = callback.data.replace("clientinfo_", "").lower()
    async with SessionLocal() as session:
        # trainer = текущий пользователь
        result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
        trainer = result.scalar_one_or_none()
        # client = по username
        result = await session.execute(select(User))
        users = result.scalars().all()
        client = next((u for u in users if u.username and u.username.lower() == username), None)
        if not client:
            await callback.message.answer("Клиент с таким username не найден.")
            await callback.answer()
            return
        # Проверяем связь тренер-клиент
        from db import TrainerClient, Workout
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            await callback.message.answer("Этот клиент не привязан к тебе.")
            await callback.answer()
            return
        # Считаем тренировки
        result = await session.execute(
            select(Workout).where(Workout.client_id == client.id, Workout.trainer_id == trainer.id).order_by(Workout.date.desc())
        )
        workouts = result.scalars().all()
        msg = get_client_profile_text(client, trainer, workouts)
        await callback.message.answer(msg, parse_mode="HTML")
    await callback.answer()

@dp.message(Command("mytrainers"))
async def my_trainers_handler(message: Message):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        client = result.scalar_one_or_none()
        if not client or client.role != UserRole.client:
            await message.answer("Только подопечный может просматривать список тренеров.")
            return
        from db import TrainerClient
        result = await session.execute(
            select(TrainerClient, User)
            .join(User, TrainerClient.trainer_id == User.id)
            .where(TrainerClient.client_id == client.id)
        )
        trainers = result.all()
        if not trainers:
            await message.answer("У тебя пока нет тренеров.")
            return
        msg = "Твои тренеры:\n" + "\n".join([
            f"@{trainer.User.username or trainer.User.full_name}" for trainer in trainers
        ])
        await message.answer(msg)

@dp.message(Command("addworkout"))
async def add_workout_handler(message: Message):
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer("Используй команду так: /addworkout username_клиента дата упражнения | заметки\nПример: /addworkout ankalini 2024-04-29 Присед 3x10, Жим 3x8 | Хорошая тренировка!")
        return
    username = args[1].lstrip("@")
    date_str = args[2]
    rest = args[3].split("|", 1)
    exercises = rest[0].strip()
    notes = rest[1].strip() if len(rest) > 1 else ""
    from db import Workout
    import datetime
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Дата должна быть в формате ГГГГ-ММ-ДД (например, 2024-04-29)")
        return
    async with SessionLocal() as session:
        # Проверяем, что отправитель — тренер
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять тренировки.")
            return
        # Ищем клиента по username
        result = await session.execute(select(User).where(User.username == username))
        client = result.scalar_one_or_none()
        if not client:
            await message.answer("Клиент с таким username не найден. Попроси клиента сначала написать боту!")
            return
        # Проверяем, есть ли связь тренер-клиент
        from db import TrainerClient
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            await message.answer("Этот клиент не привязан к тебе. Сначала добавь его через /addclient.")
            return
        # Добавляем тренировку
        workout = Workout(
            client_id=client.id,
            trainer_id=trainer.id,
            date=date,
            exercises=exercises,
            notes=notes
        )
        session.add(workout)
        await session.commit()
        await message.answer(f"Тренировка для @{username} успешно добавлена!")

@dp.message(Command("workouts"))
async def workouts_handler(message: Message):
    from db import Workout
    args = message.text.split()
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        # Для тренера: /workouts username_клиента
        if user.role == UserRole.trainer:
            if len(args) != 2:
                await message.answer("Используй: /workouts username_клиента")
                return
            username = args[1].lstrip("@").lower()
            result = await session.execute(select(User))
            users = result.scalars().all()
            client = next((u for u in users if u.username and u.username.lower() == username), None)
            if not client:
                await message.answer("Клиент с таким username не найден.")
                return
            result = await session.execute(
                select(Workout).where(Workout.client_id == client.id, Workout.trainer_id == user.id).order_by(Workout.date.desc())
            )
            workouts = result.scalars().all()
            if not workouts:
                await message.answer("У этого клиента нет тренировок.")
                return
            msg = f"Тренировки @{client.username}:\n"
            for w in workouts:
                msg += f"ID:{w.id} {w.date.date()} — {w.exercises} | {w.notes}\n"
            await message.answer(msg)
        # Для клиента: /workouts
        elif user.role == UserRole.client:
            result = await session.execute(
                select(Workout).where(Workout.client_id == user.id).order_by(Workout.date.desc())
            )
            workouts = result.scalars().all()
            if not workouts:
                await message.answer("У тебя пока нет тренировок.")
                return
            msg = "Твои тренировки:\n"
            for w in workouts:
                msg += f"ID:{w.id} {w.date.date()} — {w.exercises} | {w.notes}\n"
            await message.answer(msg)
        else:
            await message.answer("Неизвестная роль пользователя.")

@dp.message(Command("delworkout"))
async def del_workout_handler(message: Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("Используй: /delworkout id_тренировки")
        return
    workout_id = int(args[1])
    from db import Workout
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        result = await session.execute(select(Workout).where(Workout.id == workout_id))
        workout = result.scalar_one_or_none()
        if not workout:
            await message.answer("Тренировка не найдена.")
            return
        # Только владелец может удалить тренировку
        if user.role == UserRole.trainer and workout.trainer_id != user.id:
            await message.answer("Вы не можете удалить эту тренировку.")
            return
        if user.role == UserRole.client and workout.client_id != user.id:
            await message.answer("Вы не можете удалить эту тренировку.")
            return
        await session.delete(workout)
        await session.commit()
        await message.answer("Тренировка удалена.")

@dp.message(Command("editworkout"))
async def edit_workout_handler(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3 or not args[1].isdigit():
        await message.answer("Используй: /editworkout id_тренировки дата упражнения | заметки\nПример: /editworkout 5 2024-05-01 Присед 3x12, Жим 3x10 | Отличная тренировка!")
        return
    workout_id = int(args[1])
    rest = args[2].split("|", 1)
    exercises_and_date = rest[0].strip().split(maxsplit=1)
    if len(exercises_and_date) < 2:
        await message.answer("Укажите дату и упражнения через пробел.")
        return
    date_str = exercises_and_date[0]
    exercises = exercises_and_date[1]
    notes = rest[1].strip() if len(rest) > 1 else ""
    from db import Workout
    import datetime
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("Дата должна быть в формате ГГГГ-ММ-ДД (например, 2024-05-01)")
        return
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        result = await session.execute(select(Workout).where(Workout.id == workout_id))
        workout = result.scalar_one_or_none()
        if not workout:
            await message.answer("Тренировка не найдена.")
            return
        # Только владелец может редактировать тренировку
        if user.role == UserRole.trainer and workout.trainer_id != user.id:
            await message.answer("Вы не можете редактировать эту тренировку.")
            return
        if user.role == UserRole.client and workout.client_id != user.id:
            await message.answer("Вы не можете редактировать эту тренировку.")
            return
        workout.date = date
        workout.exercises = exercises
        workout.notes = notes
        await session.commit()
        await message.answer("Тренировка обновлена.")

@dp.message(Command("remind"))
async def remind_handler(message: Message):
    args = message.text.split(maxsplit=4)
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        # Если тренер и указал username клиента
        if user.role == UserRole.trainer and len(args) >= 4:
            username = args[1].lstrip("@").lower()
            date_str = args[2]
            time_str = args[3]
            text = args[4] if len(args) >= 5 else "Напоминание о тренировке!"
            result = await session.execute(select(User))
            users = result.scalars().all()
            client = next((u for u in users if u.username and u.username.lower() == username), None)
            if not client:
                await message.answer("Клиент с таким username не найден.")
                return
            remind_at = None
            try:
                remind_at = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                await message.answer("Дата и время должны быть в формате YYYY-MM-DD HH:MM")
                return
            reminder = Reminder(user_id=client.id, remind_at=remind_at, text=text)
            session.add(reminder)
            await session.commit()
            await message.answer(f"Напоминание для @{client.username} установлено на {remind_at.strftime('%Y-%m-%d %H:%M')}")
        # Для себя (клиент или тренер без username)
        elif len(args) >= 3:
            date_str = args[1]
            time_str = args[2]
            text = args[3] if len(args) >= 4 else "Напоминание о тренировке!"
            remind_at = None
            try:
                remind_at = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                await message.answer("Дата и время должны быть в формате YYYY-MM-DD HH:MM")
                return
            reminder = Reminder(user_id=user.id, remind_at=remind_at, text=text)
            session.add(reminder)
            await session.commit()
            await message.answer(f"Напоминание установлено на {remind_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            await message.answer("Используй: /remind [username_] YYYY-MM-DD HH:MM [текст_напоминания]\nПримеры:\n/remind 2024-05-01 09:00\n/remind passway_pro 2024-05-02 10:00 Не забудь о тренировке!")

@dp.message(Command("clientinfo"))
async def client_info_handler(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Используй: /clientinfo username_клиента")
        return
    username = args[1].lstrip("@").lower()
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может просматривать профили клиентов.")
            return
        result = await session.execute(select(User))
        users = result.scalars().all()
        client = next((u for u in users if u.username and u.username.lower() == username), None)
        if not client:
            await message.answer("Клиент с таким username не найден.")
            return
        # Проверяем, есть ли связь тренер-клиент
        from db import TrainerClient, Workout
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            await message.answer("Этот клиент не привязан к тебе.")
            return
        # Считаем тренировки и находим последнюю
        result = await session.execute(
            select(Workout).where(Workout.client_id == client.id, Workout.trainer_id == trainer.id).order_by(Workout.date.desc())
        )
        workouts = result.scalars().all()
        count = len(workouts)
        last_date = workouts[0].date.date() if workouts else None
        days_ago = (datetime.date.today() - last_date).days if last_date else None
        msg = f"Профиль @{client.username or ''}\n"
        msg += f"ФИО: {client.full_name or '-'}\n"
        msg += f"Возраст: {client.age or '-'}\n"
        msg += f"Вес: {client.weight or '-'} кг\n"
        msg += f"Рост: {client.height or '-'} см\n"
        msg += f"Цель: {client.goal or '-'}\n"
        msg += f"Всего тренировок: {count}\n"
        if last_date:
            msg += f"Последняя тренировка: {last_date} ({days_ago} дн. назад)\n"
            if days_ago > 7:
                msg += "Статус: не тренировался больше недели!\n"
            else:
                msg += "Статус: активен\n"
        else:
            msg += "Тренировок пока не было.\n"
        await message.answer(msg)

async def reminder_worker():
    while True:
        now = datetime.datetime.now()
        async with SessionLocal() as session:
            result = await session.execute(
                select(Reminder, User)
                .join(User, Reminder.user_id == User.id)
                .where(Reminder.sent == 0)
                .where(Reminder.remind_at <= now)
            )
            reminders = result.all()
            for reminder, user in reminders:
                try:
                    await bot.send_message(user.telegram_id, f"Напоминание: {reminder.text}")
                except Exception:
                    pass
                reminder.sent = 1
            await session.commit()
        await asyncio.sleep(60)

# Фоновая задача для запуска бота
@app.on_event("startup")
async def on_startup():
    await init_db()
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(reminder_worker())

class ProfileStates(StatesGroup):
    waiting_full_name = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_weight = State()  # только для клиента
    waiting_height = State()  # только для клиента
    waiting_goal = State()    # только для клиента
    waiting_experience = State()  # только для тренера
    waiting_specialization = State()  # только для тренера
    waiting_contacts = State()  # только для тренера
    waiting_about = State()  # только для тренера
    waiting_photo = State()  # только для тренера

# --- Универсальный /profile ---
async def profile_start_from_id(user_id, message, state: FSMContext):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        await state.update_data(role=user.role.value)
    await message.answer("Введите ваше ФИО:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ProfileStates.waiting_full_name)

@dp.message(Command("profile"))
async def profile_start(message: Message, state: FSMContext):
    await profile_start_from_id(message.from_user.id, message, state)

@dp.message(ProfileStates.waiting_full_name)
async def profile_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    # Кнопки для выбора пола
    gender_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Мужской")],[KeyboardButton(text="Женский")]],
        resize_keyboard=True
    )
    await message.answer("Выберите ваш пол:", reply_markup=gender_kb)
    await state.set_state(ProfileStates.waiting_gender)

@dp.message(ProfileStates.waiting_gender)
async def profile_gender(message: Message, state: FSMContext):
    gender = message.text.strip().lower()
    if gender not in ["мужской", "женский"]:
        await message.answer("Пожалуйста, выберите пол кнопкой.")
        return
    await state.update_data(gender="М" if gender == "мужской" else "Ж")
    data = await state.get_data()
    if data.get("role") == "trainer":
        await message.answer("Введите ваш возраст (лет):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.waiting_age)
    else:
        await message.answer("Введите ваш возраст (лет):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.waiting_age)

@dp.message(ProfileStates.waiting_age)
async def profile_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите возраст числом.")
        return
    await state.update_data(age=int(message.text))
    data = await state.get_data()
    if data.get("role") == "trainer":
        await message.answer("Введите ваш опыт работы (лет):")
        await state.set_state(ProfileStates.waiting_experience)
    else:
        await message.answer("Введите ваш вес (кг):")
        await state.set_state(ProfileStates.waiting_weight)

@dp.message(ProfileStates.waiting_weight)
async def profile_weight(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите вес числом.")
        return
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (см):")
    await state.set_state(ProfileStates.waiting_height)

@dp.message(ProfileStates.waiting_height)
async def profile_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите рост числом.")
        return
    await state.update_data(height=int(message.text))
    await message.answer("Введите вашу цель (например, похудеть, набрать массу и т.д.):")
    await state.set_state(ProfileStates.waiting_goal)

@dp.message(ProfileStates.waiting_goal)
async def profile_goal(message: Message, state: FSMContext):
    await state.update_data(goal=message.text)
    data = await state.get_data()
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = data["full_name"]
            user.gender = data["gender"]
            user.age = data["age"]
            user.weight = data["weight"]
            user.height = data["height"]
            user.goal = data["goal"]
            await session.commit()
    await message.answer("Профиль успешно обновлён!", reply_markup=get_main_keyboard("client"))
    await state.clear()

# --- Для тренера ---
@dp.message(ProfileStates.waiting_experience)
async def profile_experience(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите опыт работы числом (лет).")
        return
    await state.update_data(experience=int(message.text))
    await message.answer("Введите вашу специализацию (например, жиросжигание, набор массы, растяжка и т.д.):")
    await state.set_state(ProfileStates.waiting_specialization)

@dp.message(ProfileStates.waiting_specialization)
async def profile_specialization(message: Message, state: FSMContext):
    await state.update_data(specialization=message.text)
    await message.answer("Введите ваши контакты (по желанию, можно пропустить):")
    await state.set_state(ProfileStates.waiting_contacts)

@dp.message(ProfileStates.waiting_contacts)
async def profile_contacts(message: Message, state: FSMContext):
    await state.update_data(contacts=message.text)
    await message.answer("Расскажите о себе (коротко):")
    await state.set_state(ProfileStates.waiting_about)

@dp.message(ProfileStates.waiting_about)
async def profile_about(message: Message, state: FSMContext):
    await state.update_data(about=message.text)
    await message.answer("Вы можете отправить свою фотографию или нажмите 'Пропустить'.")
    await state.set_state(ProfileStates.waiting_photo)

@dp.message(ProfileStates.waiting_photo)
async def profile_photo(message: Message, state: FSMContext):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
        await state.update_data(photo_file_id=file_id)
    elif message.text and message.text.lower().startswith("пропустить"):
        await state.update_data(photo_file_id=None)
    else:
        await message.answer("Пожалуйста, отправьте фото или напишите 'Пропустить'.")
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = data["full_name"]
            user.gender = data["gender"]
            user.age = data["age"]
            user.experience = data["experience"]
            user.specialization = data["specialization"]
            user.contacts = data["contacts"]
            user.about = data["about"]
            user.photo_file_id = data.get("photo_file_id")
            await session.commit()
    await message.answer("Профиль тренера успешно обновлён!", reply_markup=get_main_keyboard("trainer"))
    await state.clear()

@dp.message(Command("editclient"))
async def edit_client_handler(message: Message):
    args = message.text.split(maxsplit=3)
    if len(args) != 4:
        await message.answer(
            "❗️ Неправильный формат команды.\n"
            "Используй: /editclient username поле значение\n"
            "Поля: full_name, age, weight, height, goal\n"
            "Пример: /editclient passway_pro weight 80"
        )
        return
    username = args[1].lstrip("@").lower()
    field = args[2]
    value = args[3]
    allowed_fields = ["full_name", "age", "weight", "height", "goal"]
    if field not in allowed_fields:
        await message.answer(f"Можно редактировать только поля: {', '.join(allowed_fields)}")
        return
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может редактировать профиль клиента этой командой.")
            return
        result = await session.execute(select(User))
        users = result.scalars().all()
        client = next((u for u in users if u.username and u.username.lower() == username), None)
        if not client:
            await message.answer("Клиент с таким username не найден.")
            return
        # Проверяем, есть ли связь тренер-клиент
        from db import TrainerClient
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            await message.answer("Этот клиент не привязан к тебе.")
            return
        # Обновляем поле
        if field in ["age", "weight", "height"]:
            if not value.isdigit():
                await message.answer(f"Поле {field} должно быть числом.")
                return
            setattr(client, field, int(value))
        else:
            setattr(client, field, value)
        await session.commit()
        await message.answer(f"Профиль клиента @{client.username} обновлён: {field} = {value}")

@dp.message(Command("privacy"))
async def privacy_handler(message: Message):
    privacy_text = (
        "Политика конфиденциальности OneFit\n\n"
        "Ваши персональные данные (имя, username, Telegram ID, информация о тренировках и профиле) используются только для работы приложения OneFit и не передаются третьим лицам.\n"
        "Данные хранятся на защищённом сервере и используются исключительно для предоставления сервисов внутри бота (ведение дневника, напоминания, связь с тренером и т.д.).\n\n"
        "Вы можете удалить свой профиль по запросу, написав администратору или воспользовавшись соответствующей функцией (если она появится в будущем).\n\n"
        "Используя бота, вы соглашаетесь с данной политикой."
    )
    await message.answer(privacy_text)

@dp.message(Command("help"))
async def help_handler(message: Message):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        role = user.role.value if user and user.role else None
    help_text = (
        "<b>Доступные команды:</b>\n"
        "/start — начать работу с ботом\n"
        "/about — о боте и авторе\n"
        "/addclient username — добавить клиента (тренер)\n"
        "/myclients — список ваших клиентов (тренер)\n"
        "/mytrainers — список ваших тренеров (клиент)\n"
        "/addworkout username дата упражнения | заметки — добавить тренировку клиенту (тренер)\n"
        "/workouts username — посмотреть тренировки клиента (тренер)\n"
        "/workouts — посмотреть свои тренировки (клиент)\n"
        "/delworkout id — удалить тренировку\n"
        "/editworkout id дата упражнения | заметки — редактировать тренировку\n"
        "/remind [username] дата время [текст] — создать напоминание себе или клиенту\n"
        "/clientinfo username — мини-CRM: профиль и активность клиента (тренер)\n"
        "/profile — заполнить или изменить свой профиль (клиент)\n"
        "/editclient username поле значение — редактировать профиль клиента (тренер)\n"
        "/changerole — сменить свою роль (тренер/подопечный)\n"
        "/privacy — политика конфиденциальности\n"
        "/deleteprofile — удалить свой профиль и все данные\n"
        "/help — список всех команд и подсказки\n"
        "\nПримеры:\n"
        "/addclient passway_pro\n"
        "/addworkout passway_pro 2024-05-01 Присед 3x10 | Отлично!\n"
        "/remind 2024-05-02 10:00 Не забудь о тренировке!\n"
        "/remind passway_pro 2024-05-02 10:00 Не забудь о тренировке!\n"
        "/editclient passway_pro weight 80\n"
    )
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_main_keyboard(role))

# --- Показ профиля ---
def get_profile_text(user):
    if user.role == UserRole.trainer:
        text = f"<b>Профиль тренера</b>\n"
        text += f"ФИО: {user.full_name or '-'}\n"
        text += f"Пол: {user.gender or '-'}\n"
        text += f"Возраст: {user.age or '-'}\n"
        text += f"Опыт работы: {user.experience or '-'} лет\n"
        text += f"Специализация: {user.specialization or '-'}\n"
        text += f"Контакты: {user.contacts or '-'}\n"
        text += f"О себе: {user.about or '-'}\n"
    else:
        text = f"<b>Профиль подопечного</b>\n"
        text += f"ФИО: {user.full_name or '-'}\n"
        text += f"Пол: {user.gender or '-'}\n"
        text += f"Возраст: {user.age or '-'}\n"
        text += f"Вес: {user.weight or '-'} кг\n"
        text += f"Рост: {user.height or '-'} см\n"
        text += f"Цель: {user.goal or '-'}\n"
    return text

profile_edit_kb = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")]]
)

@dp.message(lambda m: m.text == "🏠 Мой профиль")
async def quick_profile(message: Message, state: FSMContext):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        # Показываем фото, если есть
        if user.photo_file_id:
            await message.answer_photo(user.photo_file_id, caption=get_profile_text(user), parse_mode="HTML", reply_markup=profile_edit_kb)
        else:
            await message.answer(get_profile_text(user), parse_mode="HTML", reply_markup=profile_edit_kb)

# --- Callback для редактирования профиля ---
from aiogram import F
@dp.callback_query(F.data == "edit_profile")
async def edit_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await profile_start_from_id(callback.from_user.id, callback.message, state)

@dp.message(lambda m: m.text == "👥 Мои клиенты")
async def quick_myclients(message: Message, state: FSMContext):
    await my_clients_handler(message)

@dp.message(lambda m: m.text == "👨‍🏫 Мои тренеры")
async def quick_mytrainers(message: Message, state: FSMContext):
    await my_trainers_handler(message)

@dp.message(lambda m: m.text == "ℹ️ Помощь")
async def quick_help(message: Message, state: FSMContext):
    await help_handler(message)

@dp.message(lambda m: m.text == "🏋️‍♂️ Мои тренировки")
async def quick_workouts(message: Message, state: FSMContext):
    await workouts_handler(message)

@dp.message(lambda m: m.text == "➕ Добавить клиента")
async def quick_addclient(message: Message, state: FSMContext):
    await message.answer(
        "Чтобы добавить клиента, отправьте его username (например: passway_pro) или используйте команду /addclient username"
    )
    await state.set_state(AddClientStates.waiting_username)

class AddClientStates(StatesGroup):
    waiting_username = State()

@dp.message(AddClientStates.waiting_username)
async def addclient_username_handler(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@").lower()
    if not username.isalnum() and "_" not in username:
        await message.answer("Пожалуйста, введите корректный username (только латиница, цифры и _)")
        return
    async with SessionLocal() as session:
        # Проверяем, что отправитель — тренер
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять клиентов.")
            await state.clear()
            return
        # Ищем клиента по username (без учёта регистра)
        result = await session.execute(select(User))
        users = result.scalars().all()
        client = next((u for u in users if u.username and u.username.lower() == username), None)
        if not client:
            # Если клиента нет — создаём приглашение
            invite = PendingInvite(username=username, trainer_id=trainer.id)
            session.add(invite)
            await session.commit()
            await message.answer("Клиенту отправлено приглашение! Как только он напишет боту, он получит уведомление.")
            await state.clear()
            return
        # Проверяем, есть ли уже связь
        from db import TrainerClient
        result = await session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client.id
            )
        )
        link = result.scalar_one_or_none()
        if link:
            await message.answer("Этот клиент уже добавлен.")
            await state.clear()
            return
        # Создаём связь
        new_link = TrainerClient(trainer_id=trainer.id, client_id=client.id)
        session.add(new_link)
        await session.commit()
        await message.answer(f"Клиент @{client.username} успешно добавлен!")
        # Отправляем уведомление клиенту
        try:
            await bot.send_message(client.telegram_id, f"Вас добавил тренер @{trainer.username or trainer.full_name} в OneFit! Теперь вы можете вести дневник и получать задания.")
        except Exception:
            pass
    await state.clear()

# Универсальный fallback-обработчик должен быть в самом низу файла!
@dp.message()
async def fallback_handler(message: Message):
    known_commands = [
        "/start", "/addclient", "/myclients", "/mytrainers", "/addworkout", "/workouts", "/delworkout", "/editworkout", "/remind", "/clientinfo", "/profile", "/editclient", "/changerole", "/help"
    ]
    if any(message.text.startswith(cmd) for cmd in known_commands):
        await message.answer("Похоже, команда введена не полностью или с ошибкой.\nПопробуй /help для списка всех команд и примеров.")
    # иначе не мешаем другим обработчикам
