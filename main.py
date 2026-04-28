import os
import psutil
import asyncio
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from config import TOKEN
import database



# Инициализация бота
load_dotenv()
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
proxy_url = 'http://proxy.server:3128'
session = AiohttpSession(proxy=proxy_url)
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()
database.init_db()

# ~~~ АДМИН КОМАНДЫ ~~~
def get_disk_info():
    quota_mb = 512.0
    total_size = 0
    root_directory = '/home/tr1ck7/'

    for dirpath, dirnames, filenames in os.walk(root_directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    continue

    used_mb = (total_size / (1024 * 1024)) + 48.5
    percent = (used_mb / quota_mb) * 100
    free_mb = quota_mb - used_mb

    return f'{percent:.1f}% занято (Свободно: {free_mb:.1f} MB)'


@dp.message(Command('status'))
async def cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return


    disk_stat = get_disk_info()

    cpu_usage = psutil.cpu_percent(interval = None)
    ram_usage = psutil.virtual_memory().percent

    status_text = (
        '🛠 **Панель управления сервером**\n\n'
        f'💾 **Диск:** {disk_stat}\n'
        f'🖥 Процессор: {cpu_usage}%\n'
        f'⚡ **RAM:** {ram_usage}%\n'
        f'👤 **Твой ID:** `{message.from_user.id}`\n\n'
        '✅ Бот работает через прокси\n'
        '🚀 Статус: Online'
    )

    await message.answer(status_text, parse_mode = 'Markdown')


# Текст для главного меню
text_start = (''
        '<b>🏠 Главное меню</b>\n\n'
        'Я готов записывать твои расходы! 💰\n\n'
        '📍 <b>Как добавить трату?</b>\n'
        'Просто напиши мне в чат сообщение в формате:\n<i>Сумма Категория</i>\n\n'
        '<i>Пример:<code> 300 Чипсы</code></i>')

# Клавиатура
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text = '🏠 Главное меню')],
        [KeyboardButton(text = '📊 Статистика')],
        [KeyboardButton(text = '❌ Удалить ошибочную запись')],
        [KeyboardButton(text = '⚙ Помощь')]
    ],
    resize_keyboard=True,
    input_field_placeholder = 'Введите сумму и описание...'
)

# ~~~ ОБРАБОТКА КОМАНД ~~~

# Кнопка Главное меню и команда /start
@dp.message(F.text == '🏠 Главное меню')
@dp.message(Command('start'))
async def start_handler(message: types.Message):
    await message.answer_sticker(sticker = 'CAACAgIAAxkBAAERHn5p7ctbAAFvtBXPLGvdUnJuMmbP_FIAAvU9AAKW4YlKEbbqPv0lxiw7BA')
    await message.answer(text_start, reply_markup = main_menu, parse_mode = 'HTML')

# Кнопка Статистики
@dp.message(F.text == '📊 Статистика')
async def stats_handler(message: types.Message):
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer("У вас еще нет записей! 🤷‍♂️")
        return

    total = sum(exp[1] for exp in expenses)
    await message.answer(f'<b>📊 Твоя статистика</b>\n├Общая сумма: <code>{total}</code> руб.\n└Записей: <code>{len(expenses)}</code>', parse_mode = 'HTML')

# Кнопка Помощь
@dp.message(F.text == '⚙ Помощь')
async def help_handler(message: types.Message):
    await message.answer('Просто пиши <b>Число Категория</b>.\nНапример: <code>1500 Оперативка</code>', parse_mode="HTML")


# ~~~ЛОГИКА УДАЛЕНИЯ~~~

# Кнопка Удалить ошибочную запись
@dp.message(F.text == '❌ Удалить ошибочную запись')
async def show_expenses_for_delete(message: types.Message):
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer('У тебя пока что нет записей для удаления 💔')
        return

    keyboard = []
    for exp_id, amount, category, date in expenses[:10]:
        btn_text = f'{amount} р. - {category}'
        keyboard.append([InlineKeyboardButton(text = btn_text, callback_data = f'confirm_del_{exp_id}')])

    markup = InlineKeyboardMarkup(inline_keyboard = keyboard)
    await message.answer('‼ <b>Помни, что удалённую запись невозможно вернуть</b>‼\n\n🗑Выбери запись, которую нужно удалить🗑', reply_markup = markup, parse_mode = 'HTML')

# Подтверждение удаления
@dp.callback_query(F.data.startswith('confirm_del_'))
async def ask_confirm_delete(callback: types.CallbackQuery):
    exp_id = callback.data.split('_')[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text = '✅ Да, удалить', callback_data = f'final_del_{exp_id}'),
            InlineKeyboardButton(text = '❌ Отмена', callback_data = 'cancel_del')
        ]
    ])
    await callback.message.edit_text('❗ Вы уверены, что хотите удалить эту запись?', reply_markup = kb)

# Удаление записи
@dp.callback_query(F.data.startswith('final_del_'))
async def final_delete(callback: types.CallbackQuery):
    exp_id = callback.data.split('_')[2]
    database.delete_expense(exp_id)
    await callback.answer('Запись удалена')
    await callback.message.edit_text('✅ Запись успешно удалена')

# Отмена удаления записи
@dp.callback_query(F.data == 'cancel_del')
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.edit_text('Удаление отменено 🤝')

# ~~~ ОБРАБОТЧИК ТЕКСТА ~~~
@dp.message()
async def message_handler(message: types.Message):
    try:
        parts = message.text.split(maxsplit=1)
        amount = float(parts[0].replace(',', '.'))
        category = parts[1] if len(parts) > 1 else 'Прочее'

        database.add_expense(message.from_user.id, amount, category)
        await message.reply(f'✅ <b>Записал!</b>\nСумма: <code>{amount}</code> руб.\nКатегория: <code>{category}</code>', parse_mode = 'HTML')
    except (ValueError, IndexError):
        await message.answer('⚠ Ошибка! Введи сначала число, а потом описание.\nПример: <code>100 сок</code>', parse_mode = 'HTML')

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')