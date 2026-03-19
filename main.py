import json
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- НАСТРОЙКИ ---
# Вставь сюда свою ссылку на таблицу!
SHEET_URL = "https://docs.google.com/spreadsheets/d/16Pfa9dJhOPlPU7zfNp7x5IRBKwuMpPb4XX5OpDmcGv8/edit?pli=1&gid=0#gid=0"

# --- СПИСОК ПРОРАБОВ ---
FOREMEN = ["Цонев", "Петров", "Сидоров", "Кузнецов", "Смирнов"]

# --- ПОДКЛЮЧЕНИЕ К ОБЛАКУ ИЛИ ЛОКАЛЬНОМУ ФАЙЛУ ---
@st.cache_resource
def get_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. Если мы в Облаке (Streamlit Cloud)
    if "google_key" in st.secrets:
        # Читаем ключ из секретов (превращаем текст в словарь)
        key_dict = json.loads(st.secrets["google_key"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    
    # 2. Если мы на компьютере (Локально)
    else:
        # Ищем файл credentials.json рядом с скриптом
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
    return gspread.authorize(creds)

# --- ЗАГРУЗКА ДАННЫХ ---
@st.cache_data(ttl=600)
def load_data():
    try:
        client = get_client()
        sheet = client.open_by_url(SHEET_URL)
        
        # Пытаемся открыть лист "Справочник"
        try:
            ws = sheet.worksheet("Справочник")
        except:
            ws = sheet.get_worksheet(0)

        all_values = ws.get_all_values()
        
        if not all_values:
            return pd.DataFrame()

        headers = all_values[0]
        data = all_values[1:]
        df = pd.DataFrame(data, columns=headers)
        
        # Чистим заголовки от пробелов
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Ошибка чтения данных: {e}")
        return pd.DataFrame()

# --- ОТПРАВКА ЗАЯВКИ ---
def send_order(order_items):
    try:
        client = get_client()
        sheet = client.open_by_url(SHEET_URL)
        
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

    # Проверка загрузки
    df = load_data()
    if df.empty:
        st.error("Не удалось загрузить справочник. Проверьте таблицу.")
        st.stop()

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'order_id' not in st.session_state: 
        st.session_state.order_id = str(uuid.uuid4())[:6].upper()
        st.session_state.order_date = datetime.now().strftime("%d.%m.%Y")

    with st.sidebar:
        st.header(f"Заявка № {st.session_state.order_id}")
        sel_foreman = st.selectbox("Прораб:", FOREMEN)
        if st.button("🔄 Обновить справочник"):
            load_data.clear()
            st.rerun()

    # --- ПОИСК МАТЕРИАЛОВ ---
    objects = sorted([x for x in df["Название объекта"].unique() if str(x).strip() != ""])
    sel_obj = st.selectbox("1. Объект", objects)
    df_step1 = df[df["Название объекта"] == sel_obj]

    rds = sorted([x for x in df_step1["Раздел РД"].unique() if str(x).strip() != ""])
    sel_rd = st.selectbox("2. Раздел РД", rds)
    df_step2 = df_step1[df_step1["Раздел РД"] == sel_rd]

    # Ищем колонку с именем материала
    mat_col_name = next((col for col in df.columns if "Наименование" in col and "работ" in col), df.columns[3])
    materials = sorted([x for x in df_step2[mat_col_name].unique() if str(x).strip() != ""])
    sel_material = st.selectbox("3. Материал", materials)

    row = df_step2[df_step2[mat_col_name] == sel_material].iloc[0]

    st.markdown("---")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        unit = row.get("Единица измерения") or row.get("Ед. изм.") or "шт"
        st.info(f"**{sel_material}** ({unit})")
        
        norm = row.get("норма расход") or row.get("Норма") or "-"
        constr = row.get("Наименование конструктивных решений (элементов), комплексов (видов) работ") or "-"
        justif = row.get("Обоснование") or "-"
        
        st.caption(f"Обоснование: {justif}")

    with col2:
        qty = st.number_input("Количество", min_value=0.0, step=0.1)
        
        if st.button("⬇️ ДОБАВИТЬ", type="primary"):
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
                st.success("ОК")

    st.markdown("---")
    
    if st.session_state.cart:
        cart_df = pd.DataFrame(st.session_state.cart)
        st.dataframe(cart_df[["material", "qty", "unit"]], use_container_width=True)

        if st.button("🚀 ОТПРАВИТЬ ЗАЯВКУ"):
            if send_order(st.session_state.cart):
                st.balloons()
                st.success("Отправлено!")
                st.session_state.cart = []
                del st.session_state.order_id
                st.rerun()

if __name__ == "__main__":
    main()
