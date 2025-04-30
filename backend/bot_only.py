import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

BOT_TOKEN = "7838089838:AAF0xUGyDsKI3g3pG2JfEtfDR7Tq9X7G_iQ"  # <-- ваш токен
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AddReminderStates(StatesGroup):
    waiting_recipient = State()
    waiting_datetime = State()
    waiting_text = State()

@dp.message(Command("start"))
async def start_handler(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Себе", callback_data="remind_self")],
            [InlineKeyboardButton(text="Клиенту @test", callback_data="remind_test")],
        ]
    )
    await message.answer("Кому создать напоминание?", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("remind_"))
async def add_reminder_recipient(callback: types.CallbackQuery, state: FSMContext):
    recipient = callback.data.replace("remind_", "")
    await state.update_data(recipient=recipient)
    await callback.message.answer("Введи дату и время напоминания в формате ГГГГ-ММ-ДД ЧЧ:ММ (например, 2024-05-01 09:00):")
    await state.set_state(AddReminderStates.waiting_datetime)
    print("DEBUG: set_state waiting_datetime")
    await callback.answer()

@dp.message(AddReminderStates.waiting_datetime)
async def add_reminder_datetime(message: Message, state: FSMContext):
    print("DEBUG: add_reminder_datetime called")
    text = message.text.strip()
    import datetime
    try:
        remind_at = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Дата и время должны быть в формате ГГГГ-ММ-ДД ЧЧ:ММ")
        return
    await state.update_data(remind_at=remind_at)
    await message.answer("Введи текст напоминания:")
    await state.set_state(AddReminderStates.waiting_text)

@dp.message(AddReminderStates.waiting_text)
async def add_reminder_text(message: Message, state: FSMContext):
    print("DEBUG: add_reminder_text called")
    data = await state.get_data()
    text = message.text.strip()
    await message.answer(f"Напоминание для {data.get('recipient')} на {data.get('remind_at')}: {text}")
    await state.clear()

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot)) 