import os
import psutil
import asyncio
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN
import database
from database import get_total_expenses, get_pinned_msg_id, update_pinned_msg_id

# Инициализация бота
load_dotenv()
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
proxy_url = 'http://proxy.server:3128'
session = AiohttpSession(proxy=proxy_url)
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
database.init_db()


# ~~~ FSM СОСТОЯНИЯ ~~~

class LimitForm(StatesGroup):
    waiting_for_limit = State()


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
    cpu_usage = psutil.cpu_percent(interval=None)
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

    await message.answer(status_text, parse_mode='Markdown')


# ~~~ ЗАКРЕП ~~~

async def update_pinned_message(user_id):
    total_expenses = get_total_expenses(user_id)
    limit = database.get_monthly_limit(user_id)

    if limit > 0:
        remaining = limit - total_expenses
        if remaining >= 0:
            limit_line = f'💰 Лимит: {limit:.0f} руб.\n📉 Потрачено: {total_expenses:.0f} руб.\n✅ Остаток: {remaining:.0f} руб.'
        else:
            limit_line = f'💰 Лимит: {limit:.0f} руб.\n📉 Потрачено: {total_expenses:.0f} руб.\n⛔ Перерасход: {abs(remaining):.0f} руб.'
    else:
        limit_line = f'📉 Потрачено всего: {total_expenses:.0f} руб.\n💡 Лимит не установлен'

    text_pin = (
        '📊 ТЕКУЩИЙ БАЛАНС И СТАТИСТИКА\n\n'
        f'{limit_line}\n'
        '\n🔄 Обновлено только что'
    )

    pinned_msg_id = get_pinned_msg_id(user_id)

    if pinned_msg_id:
        try:
            await bot.edit_message_text(chat_id=user_id, message_id=pinned_msg_id, text=text_pin, parse_mode='HTML')
            return
        except Exception:
            pass
    try:
        new_msg = await bot.send_message(chat_id=user_id, text=text_pin, parse_mode='HTML')
        await bot.pin_chat_message(chat_id=user_id, message_id=new_msg.message_id, disable_notification=True)
        update_pinned_msg_id(user_id, new_msg.message_id)
    except Exception as e:
        print(f'Ошибка закрепа: {e}')


# ~~~ ГЛАВНОЕ МЕНЮ ~~~

text_start = (
    '<b>🏠 Главное меню</b>\n\n'
    'Я готов записывать твои расходы! 💰\n\n'
    '📍 <b>Как добавить трату?</b>\n'
    'Просто напиши мне в чат сообщение в формате:\n<i>Сумма Категория</i>\n\n'
    '<i>Пример:<code> 300 Чипсы</code></i>'
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🏠 Главное меню')],
        [KeyboardButton(text='💰 Установить лимит')],
        [KeyboardButton(text='⏱ История')],
        [KeyboardButton(text='📊 Статистика')],
        [KeyboardButton(text='❌ Удалить ошибочную запись')],
        [KeyboardButton(text='⚙ Помощь')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Введите сумму и описание...'
)


# ~~~ ОБРАБОТКА КОМАНД ~~~

@dp.message(F.text == '🏠 Главное меню')
@dp.message(Command('start'))
async def start_handler(message: types.Message):
    await message.answer_sticker(sticker='CAACAgIAAxkBAAERHn5p7ctbAAFvtBXPLGvdUnJuMmbP_FIAAvU9AAKW4YlKEbbqPv0lxiw7BA')
    await message.answer(text_start, reply_markup=main_menu, parse_mode='HTML')


@dp.message(F.text == '📊 Статистика')
async def stats_handler(message: types.Message):
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer('У вас еще нет записей! 🤷‍♂️')
        return

    total = sum(exp[1] for exp in expenses)
    await message.answer(
        f'<b>📊 Твоя статистика</b>\n├Общая сумма: <code>{total}</code> руб.\n└Записей: <code>{len(expenses)}</code>',
        parse_mode='HTML'
    )


@dp.message(F.text == '⚙ Помощь')
async def help_handler(message: types.Message):
    await message.answer(
        'Просто пиши <b>Число Категория</b>.\nНапример: <code>1500 Оперативка</code>',
        parse_mode='HTML'
    )


# ~~~ ЛИМИТ ~~~

@dp.message(F.text == '💰 Установить лимит')
async def set_limit_handler(message: types.Message, state: FSMContext):
    await state.set_state(LimitForm.waiting_for_limit)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_limit')]
    ])
    await message.answer(
        '💰 Введи сумму лимита в рублях:\n<i>Например: <code>15000</code></i>',
        parse_mode='HTML',
        reply_markup=kb
    )


@dp.callback_query(F.data == 'cancel_limit')
async def cancel_limit(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Установка лимита отменена 🤝')


@dp.message(LimitForm.waiting_for_limit)
async def process_limit(message: types.Message, state: FSMContext):
    try:
        limit = float(message.text.replace(',', '.'))
        if limit <= 0:
            await message.answer('⚠ Лимит должен быть больше нуля. Попробуй ещё раз:')
            return
        database.update_monthly_limit(message.from_user.id, limit)
        await state.clear()
        await message.answer(
            f'✅ Лимит установлен: <code>{limit:.0f}</code> руб.\n'
            f'Теперь я буду показывать остаток после каждой траты.',
            parse_mode='HTML'
        )
    except ValueError:
        await message.answer('⚠ Введи просто число, например: <code>15000</code>', parse_mode='HTML')


# ~~~ УДАЛЕНИЕ ~~~

@dp.message(F.text == '❌ Удалить ошибочную запись')
async def show_expenses_for_delete(message: types.Message):
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer('У тебя пока что нет записей для удаления 💔')
        return

    keyboard = []
    for exp_id, amount, category, date in expenses[:10]:
        btn_text = f'{amount} р. - {category}'
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f'confirm_del_{exp_id}')])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(
        '‼ <b>Помни, что удалённую запись невозможно вернуть</b>‼\n\n🗑Выбери запись, которую нужно удалить🗑',
        reply_markup=markup,
        parse_mode='HTML'
    )


@dp.callback_query(F.data.startswith('confirm_del_'))
async def ask_confirm_delete(callback: types.CallbackQuery):
    exp_id = callback.data.split('_')[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Да, удалить', callback_data=f'final_del_{exp_id}'),
            InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_del')
        ]
    ])
    await callback.message.edit_text('❗ Вы уверены, что хотите удалить эту запись?', reply_markup=kb)


@dp.callback_query(F.data.startswith('final_del_'))
async def final_delete(callback: types.CallbackQuery):
    exp_id = callback.data.split('_')[2]
    database.delete_expense(exp_id)
    await callback.answer('Запись удалена')
    await callback.message.edit_text('✅ Запись успешно удалена')
    await update_pinned_message(callback.from_user.id)


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

        # Проверка лимита
        limit = database.get_monthly_limit(message.from_user.id)
        if limit > 0:
            total = database.get_total_expenses(message.from_user.id)
            remaining = limit - total
            if remaining < 0:
                limit_text = f'\n\n⛔ <b>Лимит превышен!</b> Перерасход: <code>{abs(remaining):.0f}</code> руб.'
            else:
                limit_text = f'\n\n💰 Остаток по лимиту: <code>{remaining:.0f}</code> руб.'
        else:
            limit_text = ''

        await message.reply(
            f'✅ <b>Записал!</b>\nСумма: <code>{amount}</code> руб.\nКатегория: <code>{category}</code>{limit_text}',
            parse_mode='HTML'
        )

        await update_pinned_message(message.from_user.id)

    except (ValueError, IndexError):
        await message.answer(
            '⚠ Ошибка! Введи сначала число, а потом описание.\nПример: <code>100 сок</code>',
            parse_mode='HTML'
        )


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')