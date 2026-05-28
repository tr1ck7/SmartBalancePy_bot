import os
import psutil
import asyncio
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, callback_data
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN
from datetime import datetime, timedelta, timezone
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
    waiting_for_days = State()


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
    total_all_time = database.get_total_expenses(user_id)
    limit, limit_days, limit_start = database.get_limit_info(user_id)

    if limit > 0:
        if limit_start:
            expenses_for_limit = database.get_total_expenses(user_id, since_date = limit_start)
        else:
            expenses_for_limit = total_all_time
        remaining = limit - expenses_for_limit
        days_left = get_days_left(limit_start, limit_days)
        days_str = f'⏳ Осталось дней: {days_left}\n' if days_left is not None else ''

        if remaining >= 0:
            limit_line = f'💰 Лимит: {limit:.0f} руб.\n📉 Потрачено по лимиту: {expenses_for_limit:.0f} руб.\n✅ Остаток: {remaining:.0f} руб.\n{days_str}'
        else:
            limit_line = f'💰 Лимит: {limit:.0f} руб.\n📉 Потрачено по лимиту: {expenses_for_limit:.0f} руб.\n⛔ Перерасход: {abs(remaining):.0f} руб.\n{days_str}'
    else:
        limit_line = '💡 Лимит не установлен'

    text_pin = (
        '📊 ТЕКУЩИЙ БАЛАНС И СТАТИСТИКА\n\n'
        f'🛍 Общий расход за всё время: {total_all_time:.0f} руб.\n'
        f'{limit_line}\n'
        '\n🔄 Обновлено только что'
    )

    kb_buttons = []
    if limit > 0:
        kb_buttons.append([
            InlineKeyboardButton(text = '✏️ Изменить лимит', callback_data = 'change_limit'),
            InlineKeyboardButton(text = '🗑 Удалить лимит', callback_data = 'delete_limit')
        ])
    else:
        kb_buttons.append([
            InlineKeyboardButton(text = '💰 Установить лимит', callback_data = 'set_limit_pin')
        ])
    kb = InlineKeyboardMarkup(inline_keyboard = kb_buttons)

    pinned_msg_id = get_pinned_msg_id(user_id)

    success = False
    if pinned_msg_id:
        try:
            await bot.edit_message_text(chat_id=user_id, message_id=pinned_msg_id, text=text_pin, reply_markup=kb, parse_mode='HTML')
            await bot.pin_chat_message(chat_id=user_id, message_id=pinned_msg_id, disable_notification=True)
            success = True
        except Exception as e:
            if 'message is not modified' in str(e).lower():
                try:
                    await bot.pin_chat_message(chat_id=user_id, message_id=pinned_msg_id, disable_notification=True)
                except Exception:
                    pass
                success = True
            else:
                success = False
    if not success:
        try:
            new_msg = await bot.send_message(chat_id=user_id, text=text_pin, reply_markup=kb, parse_mode='HTML')
            await bot.pin_chat_message(chat_id=user_id, message_id=new_msg.message_id, disable_notification=True)
            update_pinned_msg_id(user_id, new_msg.message_id)
        except Exception as e:
            print(f'Ошибка закрепа: {e}')

def get_days_left(limit_start_str, limit_days):
    if not limit_start_str or not limit_days:
        return None
    start = datetime.strptime(limit_start_str, '%Y-%m-%d %H:%M:%S')
    end = start + timedelta(days = limit_days)
    now = datetime.now(timezone.utc).replace(tzinfo = None) + timedelta(hours = 3)
    delta = end - now
    return max(0, delta.days)

def get_history_pagination(expenses, page: int):
    items_per_page = 10
    total_pages = (len(expenses) + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_data = expenses[start_idx:end_idx]

    text = f'<b>⏱ История трат (Страница {page + 1} из {total_pages})</b>\n\n'

    for idx, (_, amount, category, date) in enumerate(page_data, start = start_idx + 1):
        display_date = date[:16] if date else '---'
        text += f'{idx}. <code>{display_date}</code> - <b>{amount:.0f} р.</b> ({category})\n'

    total_sum = sum(exp[1] for exp in expenses)
    text += f'\n💰 Всего расходов: <b>{total_sum:.0f} р.</b>'

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text = '⬅️ Назад', callback_data=f'hist_page_{page - 1}'))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text = 'Вперед ➡️', callback_data = f'hist_page_{page + 1}'))

    kb = InlineKeyboardMarkup(inline_keyboard = [buttons]) if buttons else None
    return text, kb

async def check_limit_expired(user_id):
    limit, limit_days, limit_start = database.get_limit_info(user_id)
    if not limit or not limit_days or not limit_start:
        return
    days_left = get_days_left(limit_start, limit_days)
    if days_left == 0:
        kb = InlineKeyboardMarkup(inline_keyboard = [[
            InlineKeyboardButton(text = f'✅ Продлить на {limit_days} дн.', callback_data = f'renew_limit_{limit_days}'),
            InlineKeyboardButton(text = '❌ Не продлевать', callback_data = 'delete_limit')
        ]])
        await bot.send_message(
            chat_id = user_id,
            text = f'⏰ <b>Лимит истёк!</b>\n\nПериод {limit_days} дн. завершён.\n💰 Лимит был: <code>{limit:.0f}</code> руб.\n\nПродлить на тот же срок?',
            reply_markup = kb, parse_mode = 'HTML'
        )


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
        [KeyboardButton(text='⏱ История'), KeyboardButton(text='📊 Статистика')],
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
    await update_pinned_message(message.from_user.id)

@dp.message(F.text == '⏱ История')
async def show_history(message: types.Message):
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer('У тебя пока нет записанных расходов! 🤷‍♂️')
        return
    text, kb = get_history_pagination(expenses, page = 0)
    await message.answer(text,reply_markup = kb, parse_mode = 'HTML')
@dp.callback_query(F.data.startswith('hist_page_'))
async def process_history_page(callback: types.CallbackQuery):
    page = int(callback.data.split('_')[2])
    expenses = database.get_all_expenses(callback.from_user.id)

    if not expenses:
        await callback.answer('Данные не найдены ❌')
        return
    text, kb = get_history_pagination(expenses, page = page)

    try:
        await callback.message.edit_text(text, reply_markup = kb, parse_mode = 'HTML')
    except Exception:
        await callback.answer()

@dp.message(F.text == '📊 Статистика')
async def stats_handler(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard = [
        [
            InlineKeyboardButton(text = '📅 За сегодня', callback_data = 'stats_today'),
            InlineKeyboardButton(text = '📅 За 7 дней', callback_data = 'stats_7days')
        ],
        [
            InlineKeyboardButton(text = '📅 За 30 дней', callback_data = 'stats_30days'),
            InlineKeyboardButton(text = '📊 За всё время', callback_data = 'stats_all')
        ]
    ])

    await message.answer('📊 <b>Выбери период для анализа трат:</b>', reply_markup = kb, parse_mode = 'HTML')
    expenses = database.get_all_expenses(message.from_user.id)
    if not expenses:
        await message.answer('У вас еще нет записей! 🤷‍♂️')
        return

@dp.callback_query(F.data.startswith('stats_'))
async def stats_period_process(callback: types.CallbackQuery):
    period = callback.data.split('_')[1]
    user_id = callback.from_user.id

    expenses = database.get_all_expenses(user_id)

    if not expenses:
        await callback.answer('У вас еще нет записей! 🤷‍♂️', show_alert = True)
        return

    now = datetime.now(timezone.utc).replace(tzinfo = None) + timedelta(hours = 3)
    start_date = None
    title = ''

    if period == 'today':
        start_date = now.replace(hour = 0, minute = 0, second = 0, microsecond = 0)
        title = 'за сегодня'
    elif period == '7days':
        start_date = now - timedelta(days=7)
        title = 'за 7 дней'
    elif period == '30days':
        start_date = now - timedelta(days=30)
        title = 'за 30 дней'
    else:
        title = 'за всё время'

    category_totals = {}
    total_sum = 0.0
    count = 0

    for exp_id, amount, category, date_str in expenses:
        exp_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')

        if start_date and exp_date < start_date:
            continue

        category_totals[category] = category_totals.get(category, 0) + amount
        total_sum += amount
        count += 1

    if count == 0:
        await callback.answer('За этот период трат не найдено 🫙', show_alert = True)
        return

    text = f'📊 <b>Статистика {title}:</b>\n'
    text += f'💰 Всего: <code>{total_sum:.0f}</code> руб.\n'
    text += f'📝 Записей: <code>{count}</code>\n'
    text += '───────────────────\n'

    sorted_cats = sorted(category_totals.items(), key = lambda x: x[1], reverse = True)

    for cat, amt in sorted_cats:
        percentage = (amt / total_sum) * 100
        bar = '🟩' * max(1, round(percentage / 20))
        text += f'▪️ {cat}: <b>{amt:.0f}</b> р. ({percentage:.1f}%)\n{bar}\n'

    kb = InlineKeyboardMarkup(inline_keyboard = [[
        InlineKeyboardButton(text = '⬅️ Назад к периодам', callback_data = 'stats_back')
    ]])

    await callback.message.edit_text(text, reply_markup = kb, parse_mode = 'HTML')

@dp.callback_query(F.data == 'stats_back')
async def stats_back(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard = [
        [
            InlineKeyboardButton(text='📅 За сегодня', callback_data='stats_today'),
            InlineKeyboardButton(text='📅 За 7 дней', callback_data='stats_7days')
        ],
        [
            InlineKeyboardButton(text='📅 За 30 дней', callback_data='stats_30days'),
            InlineKeyboardButton(text='📊 За всё время', callback_data='stats_all')
        ]
    ])
    await callback.message.edit_text('📊 <b>Выбери период для анализа трат:</b>', reply_markup = kb, parse_mode='HTML')

@dp.message(F.text == '⚙ Помощь')
async def help_handler(message: types.Message):
    await message.answer(
        'Просто пиши <b>Число Категория</b>.\nНапример: <code>1500 Оперативка</code>',
        parse_mode='HTML'
    )


# ~~~ ЛИМИТ ~~~
def limit_days_keyboard():
    return InlineKeyboardMarkup(inline_keyboard = [
        [
            InlineKeyboardButton(text = '7 дней', callback_data = 'days_7'),
            InlineKeyboardButton(text = '14 дней', callback_data = 'days_14'),
            InlineKeyboardButton(text = '30 дней', callback_data = 'days_30'),
        ],
        [InlineKeyboardButton(text = '❌ Отмена', callback_data = 'cancel_limit')]
    ])

async def ask_limit_amount(message_or_callback, state):
    await state.set_state(LimitForm.waiting_for_limit)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text = '❌ Отмена', callback_data = 'cancel_limit'),]])
    text = '💰 Введи сумму лимита в рублях:\n<i>Например: <code>15000</code></i>'
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, parse_mode = 'HTML', reply_markup = kb)
    else:
        await message_or_callback.message.edit_text(text, parse_mode = 'HTML', reply_markup = kb)

@dp.message(F.text == '💰 Установить лимит')
async def set_limit_handler(message: types.Message, state: FSMContext):
    await ask_limit_amount(message, state)

@dp.callback_query(F.data == 'set_limit_pin')
async def set_limit_from_pin(callback: types.CallbackQuery, state: FSMContext):
    await ask_limit_amount(callback, state)

@dp.callback_query(F.data == 'cancel_limit')
async def cancel_limit_process(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Установка лимита отменена 🤝')
    await callback.answer()

@dp.callback_query(F.data == 'change_limit')
async def change_limit(callback: types.CallbackQuery, state: FSMContext):
    await ask_limit_amount(callback, state)

@dp.message(LimitForm.waiting_for_limit)
async def process_limit_amount(message: types.Message, state: FSMContext):
    try:
        limit = float(message.text.replace(',', '.'))
        if limit <= 0:
            await message.answer('⚠ Лимит должен быть больше нуля. Попробуй ещё раз:')
            return
        await state.update_data(limit_amount = limit)
        await state.set_state(LimitForm.waiting_for_days)
        await message.answer(f'✅ Сумма <code>{limit:.0f}</code> руб. принята.\n\n⏳ Теперь выбери срок лимита:', parse_mode='HTML', reply_markup = limit_days_keyboard())
    except ValueError:
        await message.answer('⚠ Введи просто число, например: <code>15000</code>', parse_mode = 'HTML')

@dp.callback_query(F.data.startswith('days_'))
async def process_limit_days(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != LimitForm.waiting_for_days:
        return
    days = int(callback.data.split('_')[1])
    data = await state.get_data()
    database.set_limit_with_period(callback.from_user.id, data['limit_amount'], days)
    await state.clear()
    await callback.message.edit_text(f'✅ <b>Лимит установлен!</b>\n💰 Сумма: <code>{data["limit_amount"]:.0f}</code> руб.\n⏳ Срок: <code>{days}</code> дней', parse_mode = 'HTML')
    await update_pinned_message(callback.from_user.id)

@dp.callback_query(F.data.startswith('renew_limit_'))
async def renew_limit(callback):
    days = int(callback.data.split('_')[2])
    limit, _, _ = database.get_limit_info(callback.from_user.id)
    database.set_limit_with_period(callback.from_user.id, limit, days)
    await callback.message.edit_text(f'✅ <b>Лимит продлён!</b>\n💰 Сумма: <code>{limit:.0f}</code> руб.\n⏳ Срок: <code>{days}</code> дней', parse_mode = 'HTML')
    await update_pinned_message(callback.from_user.id)

@dp.callback_query(F.data == 'delete_limit')
async def delete_limit_handler(callback):
    database.delete_limit(callback.from_user.id)
    await callback.answer('Лимит удалён')
    await callback.message.edit_text('🗑 Лимит удалён')
    await update_pinned_message(callback.from_user.id)


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

        limit, limit_days, limit_start = database.get_limit_info(message.from_user.id)
        if limit > 0:
            if limit_start:
                total_for_limit = database.get_total_expenses(message.from_user.id, since_date = limit_start)
            else:
                total_for_limit = database.get_total_expenses(message.from_user.id)
            remaining = limit - total_for_limit
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
        await check_limit_expired(message.from_user.id)

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