import asyncio
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import pandas as pd

# Вставьте сюда токен вашего бота от @BotFather
TOKEN = "8816812279:AAFImASlU6K7RsSPHP7ONRSEWjAMo4MpB0w"
EXCEL_FILE = "current_schedule.xlsx"  # Имя файла, куда бот сохраняет расписание из чата

bot = Bot(token=TOKEN)
dp = Dispatcher()


def load_schedule_for_group_5301():
  """Парсит актуальный Excel-файл для группы 5301."""
  if not os.path.exists(EXCEL_FILE):
    return {}

  df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ")

  group_col_idx = None
  header_row = df.iloc[4].values
  for idx, val in enumerate(header_row):
    if pd.notna(val) and "5301" in str(val):
      group_col_idx = idx
      break

  if group_col_idx is None:
    return {}

  schedule_data = {}
  current_date = None
  current_day = None

  for _, row in df.iloc[5:].iterrows():
    date_val = row.iloc[2]
    day_val = row.iloc[3]
    pair_num = row.iloc[4]
    time_val = row.iloc[5]

    if pd.notna(date_val):
      current_date = str(date_val).strip()
    if pd.notna(day_val):
      current_day = str(day_val).strip()

    subject = row.iloc[group_col_idx]
    aud = row.iloc[group_col_idx + 1] if group_col_idx + 1 < len(row) else ""

    if pd.notna(pair_num) and pd.notna(subject):
      day_key = current_day.lower() if current_day else "other"
      if day_key not in schedule_data:
        schedule_data[day_key] = {
            "title": current_day,
            "date": current_date,
            "lessons": [],
        }

      time_str = str(time_val).strip() if pd.notna(time_val) else ""
      subj_str = str(subject).strip().replace("\n", " ")
      aud_str = str(aud).strip() if pd.notna(aud) else "—"

      schedule_data[day_key]["lessons"].append(
          (f"{pair_num} пара ({time_str})", subj_str, aud_str)
      )

  return schedule_data


DAYS_ORDER = [
    ("понедельник", "Пн", "19 октября"),
    ("вторник", "Вт", "20 октября"),
    ("среда", "Ср", "21 октября"),
    ("четверг", "Чт", "22 октября"),
    ("пятница", "Пт", "23 октября"),
    ("суббота", "Сб", "24 октября"),
]


def build_keyboard(active_day="понедельник", show_teachers=False):
  builder = InlineKeyboardBuilder()
  SCHEDULE = load_schedule_for_group_5301()

  for code, label, _ in DAYS_ORDER:
    if code in SCHEDULE:
      if code == active_day:
        builder.button(text=f"📌 {label}", callback_data=f"day_{code}")
      else:
        builder.button(text=label, callback_data=f"day_{code}")
  builder.adjust(5)

  if active_day in SCHEDULE:
    if show_teachers:
      builder.button(
          text="👩‍🏫 Скрыть преподавателей",
          callback_data=f"hide_tch_{active_day}",
      )
    else:
      builder.button(
          text="👩‍🏫 Преподаватели", callback_data=f"show_tch_{active_day}"
      )
    builder.adjust(1)

  return builder.as_markup()


def format_message(active_day="понедельник", show_teachers=False):
  SCHEDULE = load_schedule_for_group_5301()
  text = "📚 **Неделя 19 октября – 25 октября**\n_обновлено автоматически_\n\n"

  for code, label, date_str in DAYS_ORDER:
    if code not in SCHEDULE:
      continue

    day_info = SCHEDULE[code]
    lessons_count = len(day_info["lessons"])

    if code == active_day:
      text += f"▲ **👉 {label}, {date_str} · {lessons_count} пары**\n\n"
      text += "```\n"
      text += "┌──────────────────────┬──────────────────────────────┬──────┐\n"
      text += "│      Пара/Время      │           Предмет            │ Ауд. │\n"
      text += "├──────────────────────┼──────────────────────────────┼──────┤\n"
      for time_slot, subject, room in day_info["lessons"]:
        subj_trunc = (
            (subject[:27] + "…") if len(subject) > 28 else subject
        )
        text += (
            f"│ {time_slot:<20} │ {subj_trunc:<28} │ {room:<4} │\n"
        )
      text += "└──────────────────────┴──────────────────────────────┴──────┘\n"
      text += "```\n"

      if show_teachers:
        text += "▲ 👩‍🏫 **Преподаватели:**\n"
        for _, subject, _ in day_info["lessons"]:
          text += f"• {subject}\n"
        text += "\n"
      else:
        text += "▼ 👩‍🏫 Преподаватели\n\n"
    else:
      text += f"▼ {label}, {date_str} · {lessons_count} пары\n\n"

  return text


# Автоматический перехват файлов из чата группы или ЛС
@dp.message(F.document)
async def handle_docs(message: types.Message):
  document = message.document
  if document.file_name.endswith(".xlsx"):
    file_info = await bot.get_file(document.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)

    with open(EXCEL_FILE, "wb") as new_file:
      new_file.write(downloaded_file.read())

    await message.reply(
        "✅ **Новый файл расписания принят и сохранен!**\nБот мгновенно"
        " переключился на свежие данные."
    )
  else:
    await message.reply(
        "Пожалуйста, отправьте файл в формате `.xlsx` (Excel таблицу)."
    )


@dp.message(Command("start", "schedule"))
async def cmd_start(message: types.Message):
  text = format_message(active_day="понедельник", show_teachers=False)
  await message.answer(
      text,
      reply_markup=build_keyboard(
          active_day="понедельник", show_teachers=False
      ),
      parse_mode="Markdown",
  )


@dp.callback_query(F.data.startswith("day_"))
async def switch_day(callback: types.CallbackQuery):
  day_code = callback.data.split("_")[1]
  text = format_message(active_day=day_code, show_teachers=False)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=False),
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("show_tch_"))
async def show_teachers(callback: types.CallbackQuery):
  day_code = callback.data.split("_")[2]
  text = format_message(active_day=day_code, show_teachers=True)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=True),
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("hide_tch_"))
async def hide_teachers(callback: types.CallbackQuery):
  day_code = callback.data.split("_")[2]
  text = format_message(active_day=day_code, show_teachers=False)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=False),
      parse_mode="Markdown",
  )
  await callback.answer()


async def main():
  print("Автономный облачный бот запущен!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())