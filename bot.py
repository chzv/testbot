import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# === НАСТРОЙКИ ===
TOKEN = #"токен от BotFather"
CHANNEL_ID = #цифровой ID канала -100123456
ADMIN_IDS = #[ID админа 123456678]

# === FSM ===
class AddRecipe(StatesGroup):
    teaser_media = State()
    full_text = State()
    confirm = State()

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# === ПРОВЕРКА ПОДПИСКИ ===
async def is_subscriber(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        status_str = member.status.value
        print(f"[Проверка подписки] user_id={user_id}, status={status_str}")
        return status_str in {"member", "administrator", "creator", "owner"}
    except Exception as e:
        print(f"[Ошибка проверки подписки] {e}")
        return False

# === /admin ===
@router.message(Command("admin"))
async def admin_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("Нет доступа.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить рецепт", callback_data="add_recipe")]
    ])
    await message.answer("👩‍🍳 Админ-панель:", reply_markup=kb)

# === КНОПКА "Добавить рецепт" ===
@router.callback_query(F.data == "add_recipe")
async def start_add(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Пришли тизер (до 200 символов) с прикреплённым фото или видео:")
    await state.clear()
    await state.set_state(AddRecipe.teaser_media)

# === ТИЗЕР + МЕДИА ===
@router.message(AddRecipe.teaser_media)
async def set_teaser_media(message: Message, state: FSMContext):
    text = message.caption or message.text or ""
    if len(text) > 200:
        return await message.answer(f"❌ Тизер слишком длинный: {len(text)}/200 символов.")

    await state.update_data(teaser=text)

    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
        await state.update_data(media=(media_type, file_id))
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
        await state.update_data(media=(media_type, file_id))

    await message.answer("🧾 Введи полный рецепт (до 200 символов):")
    await state.set_state(AddRecipe.full_text)

# === ПОЛНЫЙ РЕЦЕПТ ===
@router.message(AddRecipe.full_text)
async def set_full_text(message: Message, state: FSMContext):
    if not message.text:
        return await message.answer("❌ Пожалуйста, пришли текст рецепта.")
    text = message.text.strip()
    if len(text) > 200:
        return await message.answer(f"❌ Полный рецепт слишком длинный: {len(text)}/200 символов. Сократи, пожалуйста.")
    await state.update_data(full_text=text)
    await send_preview(message.chat.id, state)
    await state.set_state(AddRecipe.confirm)

# === ПРЕДПРОСМОТР ===
async def send_preview(chat_id: int, state: FSMContext):
    data = await state.get_data()
    teaser = data['teaser']
    media = data.get('media')

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish")],
        [
            InlineKeyboardButton(text="✏️ Редактировать тизер", callback_data="edit_teaser"),
            InlineKeyboardButton(text="✏️ Редактировать рецепт", callback_data="edit_full")
        ],
        [InlineKeyboardButton(text="❌ Сбросить", callback_data="cancel")]
    ])

    if media:
        media_type, file_id = media
        if media_type == "photo":
            await bot.send_photo(chat_id, file_id, caption=teaser, reply_markup=kb)
        else:
            await bot.send_video(chat_id, file_id, caption=teaser, reply_markup=kb)
    else:
        await bot.send_message(chat_id, teaser, reply_markup=kb)

# === ОБРАБОТКА КНОПОК РЕДАКТИРОВАНИЯ ===
@router.callback_query(F.data == "edit_teaser")
async def edit_teaser(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Пришли заново тизер с медиа (фото/видео):")
    await state.set_state(AddRecipe.teaser_media)

@router.callback_query(F.data == "edit_full")
async def edit_full(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🧾 Введи заново полный текст рецепта:")
    await state.set_state(AddRecipe.full_text)

# === СБРОС ===
@router.callback_query(F.data == "cancel")
async def cancel_recipe(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Загрузка рецепта отменена. Возврат в админку.")
    fake_message = Message(
        message_id=callback.message.message_id,
        chat=callback.message.chat,
        from_user=callback.from_user,
        date=callback.message.date,
        text="/admin"
    )
    await admin_menu(fake_message)

# === ОПУБЛИКОВАТЬ ===
@router.callback_query(F.data == "publish")
async def publish_recipe(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    teaser = data.get("teaser")
    full_text = data.get("full_text")
    media = data.get("media")

    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Показать рецепт", callback_data=f"show_recipe:{full_text}")]
        ])

        if media:
            media_type, file_id = media
            if media_type == "photo":
                await bot.send_photo(CHANNEL_ID, file_id, caption=teaser, reply_markup=kb)
            else:
                await bot.send_video(CHANNEL_ID, file_id, caption=teaser, reply_markup=kb)
        else:
            await bot.send_message(CHANNEL_ID, text=teaser, reply_markup=kb)

        await callback.message.answer("✅ Рецепт опубликован в канал!")
        await state.clear()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при публикации: {e}")

# === КНОПКА "ПОКАЗАТЬ РЕЦЕПТ" ===
@router.callback_query(F.data.startswith("show_recipe:"))
async def handle_show_recipe(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_sub = await is_subscriber(user_id)
    print(f"[Проверка подписки] user_id={user_id}, подписан={is_sub}")

    full_text = callback.data.split(":", 1)[1]

    if is_sub:
        await callback.answer(full_text[:200], show_alert=True)
    else:
        await callback.answer("❌ Сначала подпишись на канал!", show_alert=True)

# === ЗАПУСК ===
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
