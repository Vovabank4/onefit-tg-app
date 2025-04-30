import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from db import SessionLocal, User, UserRole, PendingInvite, Reminder, TrainerClient, Workout
from sqlalchemy.future import select
import datetime
from aiogram.utils.markdown import hbold
import os
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "7838089838:AAF0xUGyDsKI3g3pG2JfEtfDR7Tq9X7G_iQ"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

PRIVACY_PATH = os.path.join(os.path.dirname(__file__), "privacy.txt")

def pluralize_years(n):
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return f"{n} лет"
    elif n % 10 == 1:
        return f"{n} год"
    elif 2 <= n % 10 <= 4:
        return f"{n} года"
    else:
        return f"{n} лет"

# --- Кнопки ---
def get_role_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тренер 💪", callback_data="role_trainer")],
            [InlineKeyboardButton(text="Подопечный 🏃", callback_data="role_client")],
        ]
    )

def get_delete_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить ❌", callback_data="delete_yes")],
            [InlineKeyboardButton(text="Нет, отменить", callback_data="delete_no")],
        ]
    )

def get_main_keyboard(role: str = None):
    if role == "trainer":
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Журнал тренировок"), KeyboardButton(text="👥 Мои клиенты"), KeyboardButton(text="➕ Добавить клиента")],
            [KeyboardButton(text="🔔 Напоминания"), KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🔄 Сменить роль"), KeyboardButton(text="ℹ️ Помощь")],
        ]
    elif role == "client":
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Мои тренировки"), KeyboardButton(text="👨‍🏫 Мои тренеры"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔔 Напоминания"), KeyboardButton(text="📅 Календарь"), KeyboardButton(text="🔄 Сменить роль"), KeyboardButton(text="ℹ️ Помощь")],
        ]
    else:
        buttons = [
            [KeyboardButton(text="🏠 Мой профиль"), KeyboardButton(text="🏋️‍♂️ Мои тренировки")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- FSM состояния профиля ---
class ProfileStates(StatesGroup):
    waiting_full_name = State()
    waiting_age = State()
    waiting_weight = State()
    waiting_height = State()
    waiting_experience = State()  # для тренера
    waiting_specialization = State()  # для тренера
    waiting_contacts = State()  # для тренера
    waiting_about = State()  # для тренера
    waiting_photo = State()  # для тренера
    waiting_goal = State()  # для клиента

# --- FSM для добавления тренировки ---
class WorkoutStates(StatesGroup):
    waiting_client_username = State()
    waiting_date = State()
    waiting_exercises = State()
    waiting_notes = State()

# --- Универсальная FSM для напоминаний ---
class ReminderFSM(StatesGroup):
    waiting_recipient = State()
    waiting_client = State()
    waiting_datetime = State()
    waiting_text = State()

# --- FSM для добавления клиента ---
class AddClientStates(StatesGroup):
    waiting_username = State()

# --- START/CHANGEROLE ---
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
            if not message.from_user.username:
                await message.answer("Пожалуйста, установите username в Telegram для работы с ботом.")
                return
            new_user = User(
                telegram_id=str(message.from_user.id),
                username=message.from_user.username,
                full_name=message.from_user.full_name,
                role=None
            )
            session.add(new_user)
            await session.commit()
            await message.answer(
                "<b>Добро пожаловать в OneFit!</b>\n\nПожалуйста, выберите свою роль:",
                reply_markup=get_role_keyboard(),
                parse_mode="HTML"
            )

@dp.message(Command("changerole"))
async def changerole_handler(message: Message):
    await message.answer("Выберите новую роль:", reply_markup=get_role_keyboard())

@dp.callback_query(F.data.in_(["role_trainer", "role_client"]))
async def role_callback_handler(callback: types.CallbackQuery):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        new_role = UserRole.trainer if callback.data == "role_trainer" else UserRole.client
        user.role = new_role
        await session.commit()
        await callback.message.edit_text(f"Вы выбрали роль: <b>{'Тренер 💪' if new_role==UserRole.trainer else 'Подопечный 🏃'}</b>", parse_mode="HTML")
        await bot.send_message(user.telegram_id, "Роль успешно изменена!", reply_markup=get_main_keyboard(new_role.value))
        await callback.answer()

# --- Профиль (FSM) ---
@dp.message(Command("profile"))
async def profile_start(message: Message, state: FSMContext):
    await message.answer("Введите ФИО:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ProfileStates.waiting_full_name)

@dp.message(ProfileStates.waiting_full_name)
async def profile_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer("Возраст:")
    await state.set_state(ProfileStates.waiting_age)

@dp.message(ProfileStates.waiting_age)
async def profile_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer("Возраст должен быть числом!")
        return
    await state.update_data(age=age)
    await message.answer("Вес (кг):")
    await state.set_state(ProfileStates.waiting_weight)

@dp.message(ProfileStates.waiting_weight)
async def profile_weight(message: Message, state: FSMContext):
    try:
        weight = int(message.text.strip())
    except ValueError:
        await message.answer("Вес должен быть числом!")
        return
    await state.update_data(weight=weight)
    await message.answer("Рост (см):")
    await state.set_state(ProfileStates.waiting_height)

@dp.message(ProfileStates.waiting_height)
async def profile_height(message: Message, state: FSMContext):
    try:
        height = int(message.text.strip())
    except ValueError:
        await message.answer("Рост должен быть числом!")
        return
    await state.update_data(height=height)
    # Определяем роль пользователя
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user and user.role == UserRole.trainer:
            await message.answer("Опыт работы (лет):")
            await state.set_state(ProfileStates.waiting_experience)
        else:
            await message.answer("Ваша цель (например, похудеть, набрать массу):")
            await state.set_state(ProfileStates.waiting_goal)

@dp.message(ProfileStates.waiting_experience)
async def profile_experience(message: Message, state: FSMContext):
    try:
        experience = int(message.text.strip())
    except ValueError:
        await message.answer("Опыт должен быть числом (лет)!")
        return
    await state.update_data(experience=experience)
    await message.answer("Ваша специализация (например, набор мышечной массы, жиросжигание, реабилитация):")
    await state.set_state(ProfileStates.waiting_specialization)

@dp.message(ProfileStates.waiting_specialization)
async def profile_specialization(message: Message, state: FSMContext):
    await state.update_data(specialization=message.text.strip())
    await message.answer("Ваши контакты (например, телефон, email, соцсети):")
    await state.set_state(ProfileStates.waiting_contacts)

@dp.message(ProfileStates.waiting_contacts)
async def profile_contacts(message: Message, state: FSMContext):
    await state.update_data(contacts=message.text.strip())
    await message.answer("Расскажите о себе (коротко):")
    await state.set_state(ProfileStates.waiting_about)

@dp.message(ProfileStates.waiting_about)
async def profile_about(message: Message, state: FSMContext):
    await state.update_data(about=message.text.strip())
    await message.answer("Отправьте фото для аватара или напишите 'Пропустить':")
    await state.set_state(ProfileStates.waiting_photo)

@dp.message(ProfileStates.waiting_photo)
async def profile_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text and message.text.lower().strip() == 'пропустить':
        photo_file_id = None
    else:
        await message.answer("Пожалуйста, отправьте фото или напишите 'Пропустить'.")
        return
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = data.get("full_name")
            user.age = data.get("age")
            user.weight = data.get("weight")
            user.height = data.get("height")
            user.experience = data.get("experience")
            user.specialization = data.get("specialization")
            user.contacts = data.get("contacts")
            user.about = data.get("about")
            user.goal = data.get("goal")
            if photo_file_id:
                user.photo_file_id = photo_file_id
            await session.commit()
    await message.answer("Профиль обновлён!", reply_markup=get_main_keyboard(user.role.value if user and user.role else None))
    await state.clear()

@dp.message(ProfileStates.waiting_goal)
async def profile_goal(message: Message, state: FSMContext):
    await state.update_data(goal=message.text.strip())
    await message.answer("Отправьте фото для аватара или напишите 'Пропустить':")
    await state.set_state(ProfileStates.waiting_photo)

# --- Добавление клиента ---
@dp.message(Command("addclient"))
async def addclient_handler(message: Message):
    args = message.get_args()
    if not args:
        await message.answer("Используйте: /addclient username")
        return
    username = args.strip().lstrip("@")
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять клиентов!")
            return
        client_result = await session.execute(select(User).where(User.username.ilike(username)))
        client = client_result.scalar_one_or_none()
        if client:
            # Проверка на существующую связь
            link = await session.execute(select(TrainerClient).where(TrainerClient.trainer_id==trainer.id, TrainerClient.client_id==client.id))
            if link.scalar_one_or_none():
                await message.answer("Клиент уже добавлен!")
                return
            session.add(TrainerClient(trainer_id=trainer.id, client_id=client.id))
            await session.commit()
            await message.answer(f"Клиент @{client.username} добавлен!")
        else:
            # Создаём приглашение
            session.add(PendingInvite(username=username, trainer_id=trainer.id))
            await session.commit()
            await message.answer(f"Пользователь @{username} не найден. Приглашение создано!")

# --- Список клиентов ---
@dp.message(Command("myclients"))
async def myclients_handler(message: Message):
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может просматривать клиентов!")
            return
        links = await session.execute(select(TrainerClient, User).join(User, TrainerClient.client_id==User.id).where(TrainerClient.trainer_id==trainer.id))
        clients = links.all()
        if not clients:
            await message.answer("У вас нет клиентов.")
            return
        text = "Ваши клиенты:\n" + "\n".join([f"@{c.User.username} ({c.User.full_name or '-'})" for c in clients])
        await message.answer(text)

# --- Список тренеров ---
@dp.message(Command("mytrainers"))
async def mytrainers_handler(message: Message):
    async with SessionLocal() as session:
        client_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        client = client_result.scalar_one_or_none()
        if not client or client.role != UserRole.client:
            await message.answer("Только подопечный может просматривать тренеров!")
            return
        links = await session.execute(select(TrainerClient, User).join(User, TrainerClient.trainer_id==User.id).where(TrainerClient.client_id==client.id))
        trainers = links.all()
        if not trainers:
            await message.answer("У вас нет тренеров.")
            return
        text = "Ваши тренеры:\n" + "\n".join([f"@{c.User.username} ({c.User.full_name or '-'})" for c in trainers])
        await message.answer(text)

# --- Добавление тренировки (FSM) ---
@dp.message(Command("addworkout"))
async def addworkout_start(message: Message, state: FSMContext):
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user or user.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять тренировки!")
            return
    await message.answer("Для какого клиента? Введите username:")
    await state.set_state(WorkoutStates.waiting_client_username)

@dp.message(WorkoutStates.waiting_client_username)
async def addworkout_client(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.update_data(client_username=username)
    await message.answer("Дата тренировки (ГГГГ-ММ-ДД, по умолчанию сегодня):")
    await state.set_state(WorkoutStates.waiting_date)

@dp.message(WorkoutStates.waiting_date)
async def addworkout_date(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        date = datetime.datetime.now()
    else:
        try:
            date = datetime.datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await message.answer("Формат даты: ГГГГ-ММ-ДД")
            return
    await state.update_data(date=date)
    await message.answer("Опишите упражнения:")
    await state.set_state(WorkoutStates.waiting_exercises)

@dp.message(WorkoutStates.waiting_exercises)
async def addworkout_exercises(message: Message, state: FSMContext):
    await state.update_data(exercises=message.text.strip())
    await message.answer("Заметки (опционально):")
    await state.set_state(WorkoutStates.waiting_notes)

@dp.message(WorkoutStates.waiting_notes)
async def addworkout_notes(message: Message, state: FSMContext):
    data = await state.get_data()
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        client_result = await session.execute(select(User).where(User.username.ilike(data.get("client_username"))))
        client = client_result.scalar_one_or_none()
        if not client:
            await message.answer("Клиент не найден!")
            await state.clear()
            return
        workout = Workout(
            client_id=client.id,
            trainer_id=trainer.id,
            date=data.get("date"),
            exercises=data.get("exercises"),
            notes=message.text.strip()
        )
        session.add(workout)
        await session.commit()
    await message.answer("Тренировка добавлена!", reply_markup=get_main_keyboard(trainer.role.value if trainer and trainer.role else None))
    await state.clear()

# --- Просмотр тренировок ---
@dp.message(Command("workouts"))
async def workouts_handler(message: Message):
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден!")
            return
        if user.role == UserRole.trainer:
            # Тренер видит тренировки своих клиентов
            links = await session.execute(select(TrainerClient).where(TrainerClient.trainer_id==user.id))
            client_ids = [l.client_id for l in links.scalars().all()]
            if not client_ids:
                await message.answer("У вас нет клиентов.")
                return
            workouts = await session.execute(select(Workout, User).join(User, Workout.client_id==User.id).where(Workout.client_id.in_(client_ids)))
            items = workouts.all()
            if not items:
                await message.answer("Нет тренировок у ваших клиентов.")
                return
            text = "Тренировки ваших клиентов:\n" + "\n\n".join([
                f"@{c.User.username} {c.Workout.date.strftime('%Y-%m-%d')}: {c.Workout.exercises} ({c.Workout.notes or '-'})" for c in items
            ])
            await message.answer(text)
        else:
            # Клиент видит свои тренировки
            workouts = await session.execute(select(Workout).where(Workout.client_id==user.id))
            items = workouts.scalars().all()
            if not items:
                await message.answer("У вас нет тренировок.")
                return
            text = "Ваши тренировки:\n" + "\n\n".join([
                f"{w.date.strftime('%Y-%m-%d')}: {w.exercises} ({w.notes or '-'})" for w in items
            ])
            await message.answer(text)

# --- Удаление тренировки ---
@dp.message(Command("delworkout"))
async def delworkout_handler(message: Message):
    args = message.get_args()
    if not args:
        await message.answer("Используйте: /delworkout id")
        return
    try:
        workout_id = int(args.strip())
    except ValueError:
        await message.answer("ID должен быть числом!")
        return
    async with SessionLocal() as session:
        workout_result = await session.execute(select(Workout).where(Workout.id==workout_id))
        workout = workout_result.scalar_one_or_none()
        if not workout:
            await message.answer("Тренировка не найдена!")
            return
        await session.delete(workout)
        await session.commit()
        await message.answer("Тренировка удалена!")

# --- Редактирование тренировки ---
@dp.message(Command("editworkout"))
async def editworkout_handler(message: Message):
    await message.answer("Редактирование тренировки пока не реализовано (MVP)")

# --- Напоминания (FSM) ---
@dp.message(Command("remind"))
async def remind_start(message: Message, state: FSMContext):
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if user and user.role == UserRole.client:
            # Только себе
            await state.update_data(recipient="self")
            await message.answer("Введи дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-05-01 09:00):")
            await state.set_state(ReminderFSM.waiting_datetime)
        else:
            # Старое меню для тренера
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Себе", callback_data="remind_self")],
                    [InlineKeyboardButton(text="Клиенту", callback_data="remind_client")],
                ]
            )
            await message.answer("Кому создать напоминание?", reply_markup=kb)
            await state.set_state(ReminderFSM.waiting_recipient)

@dp.callback_query(lambda c: c.data == "remind_self")
async def remind_self(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(recipient="self")
    await callback.message.answer("Введи дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-05-01 09:00):")
    await state.set_state(ReminderFSM.waiting_datetime)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "remind_client")
async def remind_client(callback: types.CallbackQuery, state: FSMContext):
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await callback.message.answer("Только тренер может создавать напоминания клиенту!")
            await state.clear()
            await callback.answer()
            return
        links = await session.execute(select(TrainerClient, User).join(User, TrainerClient.client_id==User.id).where(TrainerClient.trainer_id==trainer.id))
        clients = links.all()
        kb = InlineKeyboardBuilder()
        for c in clients[:20]:
            kb.button(text=f"@{c.User.username}", callback_data=f"remind_client_select_{c.User.username}")
        kb.button(text="Ввести username вручную", callback_data="remind_client_manual")
        kb.adjust(2)
        await callback.message.answer("Выберите клиента или введите username вручную:", reply_markup=kb.as_markup())
        await state.set_state(ReminderFSM.waiting_client)
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("remind_client_select_"))
async def remind_client_select(callback: types.CallbackQuery, state: FSMContext):
    username = callback.data.replace("remind_client_select_", "")
    async with SessionLocal() as session:
        client_result = await session.execute(select(User).where(User.username.ilike(username)))
        client = client_result.scalar_one_or_none()
        if not client:
            await callback.message.answer("Клиент не найден! Попробуйте ещё раз.")
            await callback.answer()
            return
        await state.update_data(recipient="client", client_id=client.id)
    await callback.message.answer(
        f"Клиент @{username} выбран!\nТеперь введите дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-06-10 09:00):"
    )
    await state.set_state(ReminderFSM.waiting_datetime)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "remind_client_manual")
async def remind_client_manual(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите username клиента:")
    await state.set_state(ReminderFSM.waiting_client)
    await callback.answer()

@dp.message(ReminderFSM.waiting_client)
async def remind_client_username(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может создавать напоминания клиенту!")
            await state.clear()
            return
        client_result = await session.execute(select(User).where(User.username.ilike(username)))
        client = client_result.scalar_one_or_none()
        if not client:
            await message.answer("Клиент не найден! Введите корректный username:")
            return
        link = await session.execute(select(TrainerClient).where(TrainerClient.trainer_id==trainer.id, TrainerClient.client_id==client.id))
        if not link.scalar_one_or_none():
            await message.answer("Этот клиент не привязан к вам. Добавьте его через /addclient.")
            await state.clear()
            return
        await state.update_data(recipient="client", client_id=client.id)
    await message.answer(
        f"Клиент @{username} выбран!\nТеперь введите дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-06-10 09:00):"
    )
    await state.set_state(ReminderFSM.waiting_datetime)

@dp.message(ReminderFSM.waiting_datetime)
async def remind_datetime(message: Message, state: FSMContext):
    # Универсальная обработка глобальных кнопок
    if message.text in GLOBAL_MENU_BUTTONS:
        await state.clear()
        await GLOBAL_MENU_BUTTONS[message.text](message, state)
        return
    print(f"[DEBUG] waiting_datetime: {message.text}")
    text = message.text.strip()
    try:
        remind_at = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Дата и время должны быть в формате ГГГГ-ММ-ДД ЧЧ:ММ")
        return
    await state.update_data(remind_at=remind_at)
    await message.answer("Введи текст напоминания:")
    await state.set_state(ReminderFSM.waiting_text)

@dp.message(ReminderFSM.waiting_text)
async def remind_text(message: Message, state: FSMContext):
    if message.text in GLOBAL_MENU_BUTTONS:
        await state.clear()
        await GLOBAL_MENU_BUTTONS[message.text](message, state)
        return
    print(f"[DEBUG] waiting_text: {message.text}")
    data = await state.get_data()
    async with SessionLocal() as session:
        if data.get("recipient") == "self":
            user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
            user = user_result.scalar_one_or_none()
            if not user:
                await message.answer("Пользователь не найден!")
                await state.clear()
                return
            reminder = Reminder(user_id=user.id, remind_at=data.get("remind_at"), text=message.text.strip())
            session.add(reminder)
            await session.commit()
            await message.answer(f"Напоминание создано!")
        elif data.get("recipient") == "client":
            reminder = Reminder(user_id=data["client_id"], remind_at=data["remind_at"], text=message.text.strip())
            session.add(reminder)
            await session.commit()
            await message.answer("Напоминание для клиента создано!")
    await state.clear()

# --- Информация о клиенте ---
@dp.message(Command("clientinfo"))
async def clientinfo_handler(message: Message):
    args = message.get_args()
    if not args:
        await message.answer("Используйте: /clientinfo username")
        return
    username = args.strip().lstrip("@")
    async with SessionLocal() as session:
        client_result = await session.execute(select(User).where(User.username.ilike(username)))
        client = client_result.scalar_one_or_none()
        if not client:
            await message.answer("Клиент не найден!")
            return
        text = f"Профиль клиента @{client.username}:\n" \
               f"ФИО: {client.full_name or '-'}\n" \
               f"Возраст: {client.age or '-'}\n" \
               f"Вес: {client.weight or '-'}\n" \
               f"Рост: {client.height or '-'}\n" \
               f"Цель: {client.goal or '-'}"
        await message.answer(text)

# --- Политика с пагинацией ---
PRIVACY_PAGE_SIZE = 8  # Количество пунктов на первой странице

async def get_privacy_pages():
    with open(PRIVACY_PATH, encoding="utf-8") as f:
        text = f.read()
    # Разделяем по номерам пунктов
    parts = text.split("\n\n")
    page1 = "\n\n".join(parts[:PRIVACY_PAGE_SIZE])
    page2 = "\n\n".join(parts[PRIVACY_PAGE_SIZE:])
    return [page1, page2]

@dp.message(Command("privacy"))
async def privacy_handler(message: Message):
    pages = await get_privacy_pages()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Далее", callback_data="privacy_next")]]
    ) if len(pages) > 1 else None
    await message.answer(pages[0], reply_markup=kb)

@dp.callback_query(F.data == "privacy_next")
async def privacy_next_handler(callback: types.CallbackQuery):
    pages = await get_privacy_pages()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="privacy_prev")]]
    )
    await callback.message.edit_text(pages[1], reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "privacy_prev")
async def privacy_prev_handler(callback: types.CallbackQuery):
    pages = await get_privacy_pages()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Далее", callback_data="privacy_next")]]
    )
    await callback.message.edit_text(pages[0], reply_markup=kb)
    await callback.answer()

# --- Удаление профиля ---
@dp.message(Command("deleteprofile"))
async def deleteprofile_handler(message: Message):
    await message.answer("Вы уверены, что хотите удалить профиль?", reply_markup=get_delete_confirm_keyboard())

@dp.callback_query(lambda c: c.data in ["delete_yes", "delete_no"])
async def deleteprofile_confirm(callback: types.CallbackQuery):
    if callback.data == "delete_no":
        await callback.message.answer("Удаление отменено.")
        await callback.answer()
        return
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user:
            await session.delete(user)
            await session.commit()
            await callback.message.answer("Профиль удалён.", reply_markup=ReplyKeyboardRemove())
        else:
            await callback.message.answer("Пользователь не найден.")
    await callback.answer()

# --- Помощь ---
@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Это бот OneFit! Доступные команды:\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/profile — профиль\n"
        "/addclient — добавить клиента\n"
        "/myclients — мои клиенты\n"
        "/mytrainers — мои тренеры\n"
        "/addworkout — добавить тренировку\n"
        "/workouts — мои тренировки\n"
        "/delworkout — удалить тренировку\n"
        "/editworkout — редактировать тренировку\n"
        "/remind — напоминание\n"
        "/clientinfo — инфо о клиенте\n"
        "/changerole — сменить роль\n"
        "/privacy — политика\n"
        "/deleteprofile — удалить профиль"
    )

# --- Быстрые кнопки меню ---
@dp.message(F.text.in_(["🏠 Мой профиль"]))
async def menu_profile(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        # Формируем текст профиля
        if user.role == UserRole.trainer:
            text = (
                f"👤 <b>Профиль тренера</b>\n"
                f"ФИО: {user.full_name or '-'}\n"
                f"Username: @{user.username}\n"
                f"Возраст: {pluralize_years(user.age) if user.age else '-'}\n"
                f"Вес: {str(user.weight) + ' кг' if user.weight else '-'}\n"
                f"Рост: {str(user.height) + ' см' if user.height else '-'}\n"
                f"Опыт: {pluralize_years(user.experience) if user.experience else '-'}\n"
                f"Специализация: {user.specialization or '-'}\n"
                f"Контакты: {user.contacts or '-'}\n"
                f"О себе: {user.about or '-'}\n"
            )
        else:
            text = (
                f"👤 <b>Профиль подопечного</b>\n"
                f"ФИО: {user.full_name or '-'}\n"
                f"Username: @{user.username}\n"
                f"Возраст: {pluralize_years(user.age) if user.age else '-'}\n"
                f"Вес: {str(user.weight) + ' кг' if user.weight else '-'}\n"
                f"Рост: {str(user.height) + ' см' if user.height else '-'}\n"
                f"Цель: {user.goal or '-'}\n"
            )
        # Кнопка редактирования
        edit_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")]]
        )
        # Сначала отправляем фото, если есть
        if user.photo_file_id:
            await message.answer_photo(user.photo_file_id, caption=text, parse_mode="HTML", reply_markup=edit_kb)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=edit_kb)
        # Если профиль не заполнен — предложить заполнить
        if not user.full_name or not user.age or not user.weight or not user.height or (user.role == UserRole.trainer and (not user.experience or not user.specialization)):
            await message.answer("Похоже, ваш профиль не заполнен. Хотите заполнить? Отправьте /profile")

@dp.callback_query(F.data == "edit_profile")
async def edit_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    await profile_start(callback.message, state)
    await callback.answer()

@dp.message(F.text.in_(["👥 Мои клиенты"]))
async def menu_clients(message: Message, state: FSMContext):
    await state.clear()
    await myclients_handler(message)

@dp.message(F.text.in_(["👨‍🏫 Мои тренеры"]))
async def menu_trainers(message: Message, state: FSMContext):
    await state.clear()
    await mytrainers_handler(message)

@dp.message(F.text.in_(["🏋️‍♂️ Журнал тренировок"]))
async def menu_workouts_trainer(message: Message, state: FSMContext):
    await state.clear()
    await workouts_handler(message)

@dp.message(F.text.in_(["➕ Добавить клиента"]))
async def menu_addclient(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите username клиента:")
    await state.set_state(AddClientStates.waiting_username)

@dp.message(AddClientStates.waiting_username)
async def addclient_fsm_username(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    async with SessionLocal() as session:
        trainer_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        trainer = trainer_result.scalar_one_or_none()
        if not trainer or trainer.role != UserRole.trainer:
            await message.answer("Только тренер может добавлять клиентов!")
            await state.clear()
            return
        client_result = await session.execute(select(User).where(User.username.ilike(username)))
        client = client_result.scalar_one_or_none()
        if client:
            link = await session.execute(select(TrainerClient).where(TrainerClient.trainer_id==trainer.id, TrainerClient.client_id==client.id))
            if link.scalar_one_or_none():
                await message.answer("Клиент уже добавлен!")
                await state.clear()
                return
            session.add(TrainerClient(trainer_id=trainer.id, client_id=client.id))
            await session.commit()
            await message.answer(f"Клиент @{client.username} добавлен!")
        else:
            session.add(PendingInvite(username=username, trainer_id=trainer.id))
            await session.commit()
            await message.answer(f"Пользователь @{username} не найден. Приглашение создано!")
    await state.clear()

@dp.message(F.text.in_(["🔔 Напоминания"]))
async def menu_remind(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if user and user.role == UserRole.client:
            # Только себе
            await state.update_data(recipient="self")
            await message.answer("Введи дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-05-01 09:00):")
            await state.set_state(ReminderFSM.waiting_datetime)
        else:
            # Старое меню для тренера
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Себе", callback_data="remind_self")],
                    [InlineKeyboardButton(text="Клиенту", callback_data="remind_client")],
                ]
            )
            await message.answer("Кому создать напоминание?", reply_markup=kb)
            await state.set_state(ReminderFSM.waiting_recipient)

@dp.message(F.text.in_(["🔔 Клиенту напоминание"]))
async def menu_remind_client(message: Message, state: FSMContext):
    await message.answer("Создание напоминаний клиенту будет реализовано в следующей версии.")

@dp.message(F.text.in_(["ℹ️ Помощь"]))
async def menu_help(message: Message, state: FSMContext):
    await state.clear()
    await help_handler(message)

@dp.message(F.text.in_(["🔄 Сменить роль"]))
async def menu_changerole(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите новую роль:", reply_markup=get_role_keyboard())

@dp.message(F.text.in_(["📊 Статистика"]))
async def menu_stats(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден!")
            return
        if user.role == UserRole.trainer:
            # ... старая логика для тренера ...
            links = await session.execute(select(TrainerClient, User).join(User, TrainerClient.client_id==User.id).where(TrainerClient.trainer_id==user.id))
            clients = links.all()
            num_clients = len(clients)
            from datetime import datetime, timedelta
            month_ago = datetime.now() - timedelta(days=30)
            new_clients = [c for c in clients if c.User.created_at and c.User.created_at >= month_ago]
            workouts = await session.execute(select(Workout).where(Workout.trainer_id==user.id))
            workouts_list = workouts.scalars().all()
            num_workouts = len(workouts_list)
            workouts_month = [w for w in workouts_list if w.date and w.date >= month_ago]
            reminders = await session.execute(select(Reminder).where(Reminder.user_id.in_([c.User.id for c in clients]+[user.id])))
            reminders_list = reminders.scalars().all()
            num_reminders = len(reminders_list)
            from collections import Counter
            client_ids = [w.client_id for w in workouts_list]
            if client_ids:
                most_active_id = Counter(client_ids).most_common(1)[0][0]
                most_active = next((c.User for c in clients if c.User.id == most_active_id), None)
                most_active_count = Counter(client_ids).most_common(1)[0][1]
                active_str = f"@{most_active.username} ({most_active_count} тренировок)" if most_active else "-"
            else:
                active_str = "-"
            text = (
                f"📊 Ваша статистика:\n\n"
                f"👥 Клиентов: {num_clients}\n"
                f"➕ Новых за месяц: {len(new_clients)}\n\n"
                f"🏋️‍♂️ Проведено тренировок: {num_workouts}\n"
                f"📅 За последний месяц: {len(workouts_month)}\n\n"
                f"🔔 Создано напоминаний: {num_reminders}\n\n"
                f"🥇 Самый активный клиент: {active_str}"
            )
            await message.answer(text)
        else:
            # Логика для клиента
            from datetime import datetime, timedelta
            month_ago = datetime.now() - timedelta(days=30)
            workouts = await session.execute(select(Workout).where(Workout.client_id==user.id))
            workouts_list = workouts.scalars().all()
            num_workouts = len(workouts_list)
            workouts_month = [w for w in workouts_list if w.date and w.date >= month_ago]
            reminders = await session.execute(select(Reminder).where(Reminder.user_id==user.id))
            reminders_list = reminders.scalars().all()
            num_reminders = len(reminders_list)
            text = (
                f"📊 Ваша статистика:\n\n"
                f"🏋️‍♂️ Ваших тренировок: {num_workouts}\n"
                f"📅 За последний месяц: {len(workouts_month)}\n\n"
                f"🔔 Ваших напоминаний: {num_reminders}"
            )
            await message.answer(text)

@dp.message(F.text.in_(["🏋️‍♂️ Мои тренировки"]))
async def menu_workouts_client(message: Message, state: FSMContext):
    await state.clear()
    await workouts_handler(message)

@dp.message(F.text.in_(["📅 Календарь"]))
async def menu_calendar(message: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user or user.role != UserRole.client:
            await message.answer("Только клиент может просматривать календарь своих тренировок!")
            return
        workouts = await session.execute(select(Workout).where(Workout.client_id==user.id))
        workouts_list = workouts.scalars().all()
        if not workouts_list:
            await message.answer("У вас нет тренировок.")
            return
        from collections import defaultdict
        calendar = defaultdict(list)
        for w in workouts_list:
            date_str = w.date.strftime('%Y-%m-%d')
            calendar[date_str].append(w)
        text = "\n".join([f"{date}: {len(items)} тренировок" for date, items in sorted(calendar.items())])
        await message.answer(f"📅 Ваш календарь тренировок:\n\n{text}")

# --- Фоновая задача для напоминаний ---
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

# --- Список глобальных кнопок ---
GLOBAL_MENU_BUTTONS = {
    "🏠 Мой профиль": menu_profile,
    "👥 Мои клиенты": menu_clients,
    "👨‍🏫 Мои тренеры": menu_trainers,
    "🏋️‍♂️ Журнал тренировок": menu_workouts_trainer,
    "🏋️‍♂️ Мои тренировки": menu_workouts_client,
    "➕ Добавить клиента": menu_addclient,
    "🔔 Напоминания": menu_remind,
    "📊 Статистика": menu_stats,
    "🔄 Сменить роль": menu_changerole,
    "ℹ️ Помощь": menu_help,
    "📅 Календарь": menu_calendar,
}

# --- Запуск бота ---
if __name__ == "__main__":
    import sys
    if sys.version_info >= (3, 10):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    loop.create_task(reminder_worker())
    loop.run_until_complete(dp.start_polling(bot))