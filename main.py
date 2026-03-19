import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import json
# --- НАСТРОЙКИ ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/16Pfa9dJhOPlPU7zfNp7x5IRBKwuMpPb4XX5OpDmcGv8/edit?pli=1&gid=0#gid=0"
CREDENTIALS_FILE = "credentials.json"

# --- СПИСОК ПРОРАБОВ ---
FOREMEN = ["Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов"]

# --- ПОДКЛЮЧЕНИЕ ---
@st.cache_resource
# --- ПОДКЛЮЧЕНИЕ (УНИВЕРСАЛЬНОЕ) ---
@st.cache_resource
# --- ПОДКЛЮЧЕНИЕ (УНИВЕРСАЛЬНОЕ) ---
@st.cache_resource
def get_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # ВАРИАНТ 1: Мы в Облаке (Streamlit Cloud)
    # Ищем переменную "my_key" в секретах
    if "my_key" in st.secrets:
        # Превращаем текст обратно в словарь
        key_dict = json.loads(st.secrets["my_key"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    
    # ВАРИАНТ 2: Мы на компьютере (Локально)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
    return gspread.authorize(creds)
# --- ЗАГРУЗКА ДАННЫХ (УМНАЯ) ---
@st.cache_data(ttl=600) # Обновляем каждые 10 мин
def load_data():
    try:
        client = get_client()
        sheet = client.open_by_url(SHEET_URL)
        
        # Пытаемся открыть лист "Справочник", если нет - берем первый
        try:
            ws = sheet.worksheet("Справочник")
        except:
            ws = sheet.get_worksheet(0)

        # Читаем ВСЕ данные как простой список строк (самый надежный способ)
        all_values = ws.get_all_values()
        
        if not all_values:
            return pd.DataFrame()

        # Первая строка - это заголовки
        headers = all_values[0]
        data = all_values[1:]

        # Создаем таблицу
        df = pd.DataFrame(data, columns=headers)

        # !!! ЧИСТКА ЗАГОЛОВКОВ !!!
        # Убираем пробелы в начале и конце названий колонок ("Название объекта " -> "Название объекта")
        df.columns = [c.strip() for c in df.columns]
        
        return df
    except Exception as e:
        st.error(f"Ошибка чтения данных: {e}")
        return pd.DataFrame()

# --- ОТПРАВКА ЗАЯВКИ ---
def send_order(order_items):
    try:
        client = get_client()
        sheet = client.open_by_url(SHEET_URL)
        
        # Ищем или создаем лист "Заявки"
        try:
            ws = sheet.worksheet("Заявки")
        except:
            ws = sheet.add_worksheet(title="Заявки", rows="1000", cols="20")
            ws.append_row(["ID Заявки", "Дата", "Прораб", "Объект", "Раздел РД", 
                           "Материал", "Ед.изм", "Количество", "Обоснование", "Конструктив"])

        rows_to_add = []
        for item in order_items:
            rows_to_add.append([
                item['id'], item['date'], item['foreman'], 
                item['object'], item['rd'], item['material'], 
                item['unit'], item['qty'], item['justification'], item['constructive']
            ])
        
        ws.append_rows(rows_to_add)
        return True
    except Exception as e:
        st.error(f"Ошибка записи: {e}")
        return False

# --- ИНТЕРФЕЙС ---
def main():
    st.set_page_config(page_title="Снабжение", layout="wide")
    st.title("🏗️ Заказ материалов")

    # 1. Загрузка справочника
    df = load_data()
    if df.empty:
        st.error("Справочник пуст или не загрузился. Проверьте Гугл Таблицу.")
        st.stop()

    # Инициализация сессии
    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'order_id' not in st.session_state: 
        st.session_state.order_id = str(uuid.uuid4())[:6].upper()
        st.session_state.order_date = datetime.now().strftime("%d.%m.%Y")

    # --- БОКОВАЯ ПАНЕЛЬ ---
    with st.sidebar:
        st.header(f"Заявка № {st.session_state.order_id}")
        st.info(f"Дата: {st.session_state.order_date}")
        sel_foreman = st.selectbox("Прораб:", FOREMEN)
        
        if st.button("🔄 Обновить справочник"):
            load_data.clear()
            st.rerun()

    st.subheader("1. Поиск материала")

    # --- КАСКАДНЫЕ ФИЛЬТРЫ (МАТРЕШКА) ---
    
    # ШАГ 1: ОБЪЕКТ
    # Берем уникальные объекты, сортируем
    objects = sorted(df["Название объекта"].unique())
    # Если в списке есть пустые строки - выкидываем их
    objects = [x for x in objects if x.strip() != ""]
    
    sel_obj = st.selectbox("1. Выберите Объект", objects)

    # Фильтруем таблицу: оставляем только строки этого объекта
    df_step1 = df[df["Название объекта"] == sel_obj]

    # ШАГ 2: РАЗДЕЛ РД (Только из того, что осталось после Шага 1)
    rds = sorted(df_step1["Раздел РД"].unique())
    rds = [x for x in rds if x.strip() != ""]
    
    sel_rd = st.selectbox("2. Выберите Раздел РД", rds)

    # Фильтруем дальше
    df_step2 = df_step1[df_step1["Раздел РД"] == sel_rd]

    # ШАГ 3: ВИД РАБОТ (Опционально, но помогает сузить поиск)
    works = sorted(df_step2["Вид работ"].unique())
    works = [x for x in works if x.strip() != ""]
    
    if works:
        sel_work = st.selectbox("3. Вид работ", works)
        df_step3 = df_step2[df_step2["Вид работ"] == sel_work]
    else:
        df_step3 = df_step2 # Если вид работ не указан, пропускаем шаг

    # ШАГ 4: МАТЕРИАЛ (Финал)
    # Ищем колонку с именем материала (она длинная, может отличаться)
    # Ищем колонку, в названии которой есть "Наименование"
    mat_col_name = next((col for col in df.columns if "Наименование" in col and "работ" in col), None)
    
    if not mat_col_name:
        st.error("Не найдена колонка с названием материала! Проверьте заголовки в Excel.")
        st.stop()

    materials = sorted(df_step3[mat_col_name].unique())
    sel_material = st.selectbox("4. Материал / Оборудование", materials)

    # ПОЛУЧАЕМ ДАННЫЕ О МАТЕРИАЛЕ
    # Берем первую строку, которая совпадает со всеми фильтрами
    row = df_step3[df_step3[mat_col_name] == sel_material].iloc[0]

    # --- БЛОК ДОБАВЛЕНИЯ ---
    st.markdown("---")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.success(f"**Выбрано:** {sel_material}")
        # Пытаемся найти колонки (с защитой от опечаток в заголовках)
        unit = row.get("Единица измерения") or row.get("Ед. изм.") or "шт"
        norm = row.get("норма расход") or row.get("Норма") or "-"
        constr = row.get("Наименование конструктивных решений (элементов), комплексов (видов) работ") or "-"
        justif = row.get("Обоснование") or "-"

        st.caption(f"Конструктив: {constr}")
        st.caption(f"Обоснование: {justif}")
        st.text(f"Норма расхода: {norm}")

    with col2:
        qty = st.number_input(f"Количество ({unit})", min_value=0.0, step=0.1)
        
        if st.button("⬇️ ДОБАВИТЬ В ЗАЯВКУ", type="primary"):
            if qty > 0:
                item = {
                    "id": st.session_state.order_id,
                    "date": st.session_state.order_date,
                    "foreman": sel_foreman,
                    "object": sel_obj,
                    "rd": sel_rd,
                    "material": sel_material,
                    "unit": unit,
                    "qty": qty,
                    "justification": justif,
                    "constructive": constr
                }
                st.session_state.cart.append(item)
                st.success("Добавлено!")
            else:
                st.warning("Введите количество > 0")

    # --- КОРЗИНА ---
    st.markdown("---")
    st.subheader("📋 Ваш список к заказу")
    
    if st.session_state.cart:
        cart_df = pd.DataFrame(st.session_state.cart)
        # Показываем красивую таблицу
        st.dataframe(
            cart_df[["object", "rd", "material", "qty", "unit"]], 
            use_container_width=True,
            column_config={
                "object": "Объект",
                "rd": "Раздел",
                "material": "Наименование",
                "qty": "Кол-во",
                "unit": "Ед."
            }
        )

        col_l, col_r = st.columns([1, 4])
        with col_l:
            if st.button("❌ Очистить"):
                st.session_state.cart = []
                st.rerun()
        with col_r:
            if st.button("🚀 ОТПРАВИТЬ ЗАЯВКУ В ОФИС", type="primary", use_container_width=True):
                with st.spinner("Отправка в Google Таблицу..."):
                    if send_order(st.session_state.cart):
                        st.balloons()
                        st.success("Заявка успешно сохранена!")
                        st.session_state.cart = []
                        del st.session_state.order_id
                        st.rerun()

if __name__ == "__main__":
    main()
