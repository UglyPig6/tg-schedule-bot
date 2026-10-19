import asyncio
import http.server
import os
import threading
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import pandas as pd

# Бот берет токен из защищенных настроек Render (BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN")


def find_excel_file():
  """Автоматически находит файл расписания .xlsx в папке."""
  for f in os.listdir("."):
    if f.endswith(".xlsx") and not f.startswith("~$"):
      return f
  return "current_schedule.xlsx"


EXCEL_FILE = find_excel_file()

bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- МИНИ-СЕРВЕР ДЛЯ RENDER (чтобы не было ошибки портов) ---
class HealthCheckHandler(http.server.BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"Bot is alive!")


def run_web_server():
  port = int(os.getenv("PORT", 10000))
  server = http.server.HTTPServer(("0.0.0.0", port), HealthCheckHandler)
  server.serve_forever()


# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------------------


def load_schedule_for_group_5301():
  """Парсит актуальный Excel-файл для группы 5301 с поддержкой общих аудиторий."""
  current_file = find_excel_file()
  if not os.path.exists(current_file):
    return {}

  df = pd.read_excel(current_file, sheet_name="2 курс ")

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
    
    # Умный поиск аудитории: если в колонке аудитории группы пусто,
    # ищем ближайшую заполненную ячейку справа (для общих лекций и конф-залов)
    aud = None
    for col_idx in range(group_col_idx + 1, min(group_col_idx + 4, len(row))):
      val = row.iloc[col_idx]
      if pd.notna(val) and str(val).strip() != "":
        aud = str(val).strip()
        break
    
    if not aud:
      aud = "—"

    if pd.notna(pair_num) and pd.notna(subject):
      day_key = current_day.lower() if current_day else "other"
      if day_key not in schedule_data:
        schedule_data[day_key] = {
            "title": current_day,
            "date": current_date,
            "lessons": [],
        }

      time_str = (
          str(time_val)
          .strip()
          .replace(".", ":")
          .replace("–", "-")
          if pd.notna(time_val)
          else ""
      )
      subj_str = str(subject).strip().replace("\n", " ")
      aud_str = aud

      schedule_data[day_key]["lessons"].append({
          "num": pair_num,
          "time": time_str,
          "subject": subj_str,
          "aud": aud_str,
      })

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
        builder.button(text=f"📌 {label} (Выбран)", callback_data=f"day_{code}")
      else:
        builder.button(text=label, callback_data=f"day_{code}")
  builder.adjust(3, 3)

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


def format_single_day_message(active_day="понедельник", show_teachers=False):
  SCHEDULE = load_schedule_for_group_5301()

  if active_day not in SCHEDULE:
    return "📚 **Расписание группы 5301**\nВыберите день недели ниже:"

  day_info = SCHEDULE[active_day]
  text = (
      f"📚 **Неделя 19 октября – 25 октября**\n\n📅 **{day_info['title']}**"
      f" ({day_info['date']})\n"
      f"────────────────────────\n"
  )

  for item in day_info["lessons"]:
    text += (
        f"🔹 **{item['num']} пара** (`{item['time']}`)\n"
        f"📖 {item['subject']}\n"
        f"📍 Ауд: `{item['aud']}`\n\n"
    )

  if show_teachers:
    text += "────────────────────────\n👩‍🏫 **Список преподавателей:**\n"
    for item in day_info["lessons"]:
      text += f"• {item['subject']}\n"

  return text


@dp.message(F.document)
async def handle_docs(message: types.Message):
  document = message.document
  if document.file_name.endswith(".xlsx"):
    file_info = await bot.get_file(document.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)

    global EXCEL_FILE
    EXCEL_FILE = document.file_name

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
  text = format_single_day_message(
      active_day="понедельник", show_teachers=False
  )
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
  text = format_single_day_message(active_day=day_code, show_teachers=False)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=False),
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("show_tch_"))
async def show_teachers(callback: types.CallbackQuery):
  day_code = callback.data.split("_")[2]
  text = format_single_day_message(active_day=day_code, show_teachers=True)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=True),
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("hide_tch_"))
async def hide_teachers(callback: types.CallbackQuery):
  day_code = callback.data.split("_")[2]
  text = format_single_day_message(active_day=day_code, show_teachers=False)
  await callback.message.edit_text(
      text,
      reply_markup=build_keyboard(active_day=day_code, show_teachers=False),
      parse_mode="Markdown",
  )
  await callback.answer()


async def main():
  print("Бот с умным определением аудиторий запущен!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())