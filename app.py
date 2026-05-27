import streamlit as st
import google.generativeai as genai
import json
import random
import string
import pandas as pd
from datetime import datetime, timedelta
from PIL import Image
import io
import base64
import requests
import uuid

# ==========================================
# 0. 輕量版 Supabase 資料庫直連引擎 (免認證、極速相容版)
# ==========================================
class LightPostgrestQuery:
    def __init__(self, base_url, anon_key, table_name):
        self.base_url = base_url
        self.anon_key = anon_key
        self.table_name = table_name
        self.params = {}
        self.method = "GET"
        self.payload = None
        self.headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def select(self, select_str="*"):
        self.method = "GET"
        self.params["select"] = select_str
        return self

    def eq(self, column, value):
        self.params[column] = f"eq.{value}"
        return self

    def in_(self, column, values):
        formatted_vals = []
        for v in values:
            if isinstance(v, str):
                v_clean = v.replace('"', '\\"')
                formatted_vals.append(f'"{v_clean}"')
            else:
                formatted_vals.append(str(v))
        self.params[column] = f"in.({','.join(formatted_vals)})"
        return self

    def order(self, column, desc=False):
        self.params["order"] = f"{column}.desc" if desc else f"{column}.asc"
        return self

    def insert(self, payload):
        self.method = "POST"
        self.payload = payload
        return self

    def update(self, payload):
        self.method = "PATCH"
        self.payload = payload
        return self

    def execute(self):
        url = f"{self.base_url}/rest/v1/{self.table_name}"
        
        if self.method == "GET":
            res = requests.get(url, headers=self.headers, params=self.params)
        elif self.method == "POST":
            res = requests.post(url, headers=self.headers, json=self.payload)
        elif self.method == "PATCH":
            res = requests.patch(url, headers=self.headers, params=self.params, json=self.payload)
            
        if res.status_code not in (200, 201, 204):
            try:
                err_msg = res.json().get("message") or res.text
            except:
                err_msg = res.text
            raise Exception(f"資料庫操作失敗: {err_msg}")
        
        class DBResponse:
            def __init__(self, response_data):
                self.data = response_data
        
        data = []
        if res.text:
            try:
                data = res.json()
            except:
                pass
        return DBResponse(data)

class SimpleSupabaseClient:
    def __init__(self, supabase_url, supabase_key):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key

    def table(self, table_name):
        return LightPostgrestQuery(self.supabase_url, self.supabase_key, table_name)

def create_client(supabase_url, supabase_key):
    return SimpleSupabaseClient(supabase_url, supabase_key)


# ==========================================
# 1. 系統初始化與金鑰設定
# ==========================================
SUPABASE_URL = "https://tppzpbidjeqlktfnvbjq.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_vAqC_F3CuXGZSV1TYRqyVA_M46QFfid"
GEMINI_API_KEY = "AIzaSyAqL1A_OaQVtGP8PRUxl9nOgGrf7eiAgrE"

@st.cache_resource
def init_connections():
    supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    return supabase_client

try:
    supabase = init_connections()
except Exception as e:
    st.error(f"雲端連線失敗：{e}")

# ==========================================
# 2. 頁面外觀與風格設計 (客製化 CSS)
# ==========================================
st.set_page_config(
    page_title="小小家庭健康久久",
    page_icon="❤️",
    layout="centered"
)

st.markdown("""
<style>
    .main { font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif; }
    .health-card {
        background-color: #f8f9fa;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border-left: 5px solid #ff4b4b;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .exercise-card { border-left: 5px solid #1f77b4; }
    div.stButton > button { border-radius: 20px; padding: 6px 20px; }
    .metric-val { font-size: 24px; font-weight: bold; color: #ff4b4b; }
    
    /* 儀表板卡片設計 */
    .dashboard-box {
        background-color: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 核心輔助功能
# ==========================================
def compress_image_to_base64(uploaded_file):
    try:
        img = Image.open(uploaded_file)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((250, 250))
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=75)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        st.warning(f"照片處理失敗：{e}")
        return None

# 初始化狀態常駐變數
if "current_user" not in st.session_state:
    st.session_state.current_user = None  # 儲存目前選取的登入角色

# ==========================================
# 4. 角色選擇與管理介面 (免註冊核心)
# ==========================================
if st.session_state.current_user is None:
    st.title("❤️ 小小家庭健康久久")
    st.caption("免註冊群組！直接選擇您的角色或新增成員，即可開始記錄家庭健康！")
    st.markdown("---")
    
    # 讀取雲端所有的 Profiles 角色列表
    try:
        profiles_res = supabase.table("profiles").select("*").execute()
        user_list = profiles_res.data if profiles_res.data else []
    except Exception as e:
        st.error(f"讀取角色列表失敗，請確認 Supabase 的 SQL 初始化是否成功執行。錯誤：{e}")
        user_list = []

    st.subheader("👪 誰要開始記錄？請選擇角色")
    if not user_list:
        st.info("💡 目前系統中還沒有任何成員，請在下方新增第一個角色！")
    else:
        # 將成員排成兩欄漂亮的按鈕
        cols = st.columns(2)
        for idx, u in enumerate(user_list):
            col_target = cols[idx % 2]
            # 當點擊某個角色的按鈕，直接將其寫入登入狀態
            if col_target.button(f"👤 {u['display_name']}", key=f"user_select_{u['id']}", use_container_width=True):
                st.session_state.current_user = u
                st.success(f"歡迎回來，{u['display_name']}！")
                st.rerun()

    st.markdown("---")
    st.subheader("➕ 新增家庭新成員")
    with st.form("add_new_user_form", clear_on_submit=True):
        new_name = st.text_input("成員稱呼 (例如：爸爸、媽媽、Leon、Lily)")
        submitted = st.form_submit_button("確認新增並登入", use_container_width=True)
        if submitted:
            if not new_name.strip():
                st.warning("請輸入成員稱呼！")
            else:
                try:
                    # 使用標準 UUID 寫入以符合 Postgres 資料庫格式 (解決 violates row-level security / UUID 格式錯誤)
                    random_id = str(uuid.uuid4())
                    insert_res = supabase.table("profiles").insert({
                        "id": random_id,
                        "display_name": new_name.strip(),
                        "hide_weight": False,
                        "family_id": "00000000-0000-0000-0000-000000000000", # 預設家庭 UUID
                        "target_calories": 2000 # 預設目標卡路里
                    }).execute()
                    
                    if insert_res.data:
                        st.success(f"成功新增角色：{new_name}！")
                        st.session_state.current_user = insert_res.data[0]
                        st.rerun()
                except Exception as e:
                    st.error(f"新增角色失敗，請確認是否已成功執行 SQL 初始化腳本。錯誤原因：{e}")

# ==========================================
# 5. 主應用程式功能 (已選取角色)
# ==========================================
else:
    cur_user = st.session_state.current_user
    
    # 側邊欄導覽與切換角色
    st.sidebar.title("❤️ 家庭健康管理")
    st.sidebar.markdown(f"當前身分：<span style='font-size:20px; font-weight:bold; color:#ff4b4b;'>{cur_user['display_name']}</span>", unsafe_allow_html=True)
    
    if st.sidebar.button("🔄 切換/登出角色", use_container_width=True):
        st.session_state.current_user = None
        st.rerun()
        
    st.sidebar.markdown("---")
    menu = st.sidebar.radio(
        "功能目錄",
        ["📸 AI 智慧紀錄", "📊 熱量收支表", "💬 家庭動態牆", "📈 體重管理", "👤 角色設定"]
    )
        
    # ------------------------------------------
    # 分頁 A：AI 智慧紀錄
    # ------------------------------------------
    if menu == "📸 AI 智慧紀錄":
        st.title("📸 AI 智慧健康紀錄")
        st.write("您可以**上傳食物或運動照片**，或直接**用文字描述**，Gemini AI 會自動計算數據！")
        
        log_type = st.radio("您要記錄的是？", ["🍎 飲食紀錄", "🏃 運動紀錄"], horizontal=True)
        user_desc = st.text_area("寫點什麼吧 (例如:『中午吃了排骨便當配一杯半糖紅茶』或『今天慢跑了40分鐘』)", height=100)
        uploaded_img = st.file_uploader("上傳照片 (可選)", type=["jpg", "jpeg", "png"])
        
        if "ai_parsed_result" not in st.session_state:
            st.session_state.ai_parsed_result = None
            st.session_state.active_type = None
            st.session_state.image_base64 = None

        if st.button("✨ 送出 AI 智慧分析", use_container_width=True):
            if not user_desc and not uploaded_img:
                st.warning("請至少輸入一些文字或上傳一張照片喔！")
            else:
                with st.spinner("AI 正在全力分析中，請稍候..."):
                    try:
                        img_to_send = None
                        if uploaded_img:
                            img_to_send = Image.open(uploaded_img)
                            st.session_state.image_base64 = compress_image_to_base64(uploaded_img)
                        else:
                            st.session_state.image_base64 = None
                            
                        # 使用最新且支援多模態的 Gemini 2.5 Flash
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        
                        if log_type == "🍎 飲食紀錄":
                            prompt = """
                            請分析以下關於食物的描述或照片。
                            你必須回答一個符合以下格式的 JSON 字串，不要包含 any 額外的說明文字、Markdown 語法標記（例如 ```json ）。
                            JSON 欄位格式：
                            {
                                "food_items": ["食物名稱1", "食物名稱2"],
                                "calories": 總估算熱量數字 (整數，單位 kcal),
                                "protein": 估算蛋白質克數 (整數，單位 g),
                                "carbs": 估算碳水化合物克數 (整數，單位 g),
                                "fat": 估算脂肪克數 (整數，單位 g),
                                "health_tip": "一句話的健康提醒或溫馨建議"
                            }
                            """
                        else:
                            prompt = """
                            請分析以下關於運動的描述或照片。
                            你必須回答一個符合以下格式的 JSON 字串，不要包含 any 額外的說明文字、Markdown 語法標記（例如 ```json ）。
                            JSON 欄位格式：
                            {
                                "exercise_type": "運動類型名稱(例如：跑步、游泳)",
                                "duration_minutes": 運動估算時長(整數，單位分鐘),
                                "calories_burned": 估算消耗熱量(整數，單位 kcal),
                                "tip": "一句話的鼓勵或運動安全提醒"
                            }
                            """
                        
                        inputs = []
                        if img_to_send:
                            inputs.append(img_to_send)
                        inputs.append(f"【用戶提供描述】：{user_desc}\n\n{prompt}")
                        
                        response = model.generate_content(inputs)
                        
                        # 極其健壯的 JSON 清理與 Markdown 標記過濾
                        raw_text = response.text.strip()
                        if raw_text.startswith("```"):
                            first_newline = raw_text.find('\n')
                            if first_newline != -1:
                                raw_text = raw_text[first_newline:]
                            else:
                                raw_text = raw_text[3:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        raw_text = raw_text.strip()
                        
                        st.session_state.ai_parsed_result = json.loads(raw_text)
                        st.session_state.active_type = "diet" if log_type == "🍎 飲食紀錄" else "exercise"
                        st.session_state.user_raw_desc = user_desc
                        
                    except Exception as e:
                        st.error(f"AI 解析失敗，請再試一次或用更明確的文字描述。錯誤：{e}")
                        
        if st.session_state.ai_parsed_result:
            st.markdown("---")
            st.subheader("💡 AI 智慧估算結果 (您可以微調數據)")
            
            with st.form("confirm_log_form"):
                if st.session_state.active_type == "diet":
                    st.write(f"🥗 **偵測到食物**：{', '.join(st.session_state.ai_parsed_result.get('food_items', []))}")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1: final_cal = st.number_input("熱量 (kcal)", value=int(st.session_state.ai_parsed_result.get("calories", 0)))
                    with col2: final_pro = st.number_input("蛋白質 (g)", value=int(st.session_state.ai_parsed_result.get("protein", 0)))
                    with col3: final_carbs = st.number_input("碳水化合物 (g)", value=int(st.session_state.ai_parsed_result.get("carbs", 0)))
                    with col4: final_fat = st.number_input("脂肪 (g)", value=int(st.session_state.ai_parsed_result.get("fat", 0)))
                    final_tip = st.text_input("AI 健康小提示", value=st.session_state.ai_parsed_result.get("health_tip", ""))
                else:
                    st.write(f"🏃 **偵測到運動**：{st.session_state.ai_parsed_result.get('exercise_type', '未知運動')}")
                    col1, col2 = st.columns(2)
                    with col1: final_duration = st.number_input("運動時長 (分鐘)", value=int(st.session_state.ai_parsed_result.get("duration_minutes", 0)))
                    with col2: final_cal_burned = st.number_input("消耗熱量 (kcal)", value=int(st.session_state.ai_parsed_result.get("calories_burned", 0)))
                    final_tip = st.text_input("AI 運動小勉勵", value=st.session_state.ai_parsed_result.get("tip", ""))
                
                submitted = st.form_submit_button("💾 確認，存入雲端日誌", use_container_width=True)
                if submitted:
                    try:
                        if st.session_state.active_type == "diet":
                            db_parsed_data = {
                                "food_items": st.session_state.ai_parsed_result.get('food_items', []),
                                "calories": final_cal, "protein": final_pro, "carbs": final_carbs, "fat": final_fat, "health_tip": final_tip
                            }
                        else:
                            db_parsed_data = {
                                "exercise_type": st.session_state.ai_parsed_result.get('exercise_type'),
                                "duration_minutes": final_duration, "calories_burned": final_cal_burned, "tip": final_tip
                            }
                        
                        insert_payload = {
                            "user_id": cur_user["id"],
                            "type": st.session_state.active_type,
                            "raw_input": st.session_state.image_base64 if st.session_state.image_base64 else st.session_state.user_raw_desc,
                            "parsed_data": db_parsed_data,
                            "cheers": {}
                        }
                        
                        supabase.table("health_logs").insert(insert_payload).execute()
                        st.success("🎉 日誌已成功儲存至雲端動態牆！")
                        st.session_state.ai_parsed_result = None
                        st.session_state.active_type = None
                        st.session_state.image_base64 = None
                    except Exception as e:
                        st.error(f"儲入資料庫失敗：{e}")

    # ------------------------------------------
    # 分頁 B：熱量收支表 (盈餘與赤字統計)
    # ------------------------------------------
    elif menu == "📊 熱量收支表":
        st.title("📊 每日熱量收支與盈餘")
        st.caption("體重控制核心公式：淨熱量餘額 = 飲食總攝取 - 運動總消耗。維持合理的熱量缺口是控制體重的關鍵！")
        
        # 讀取當前使用者在 Profiles 中設定的每日目標卡路里 (超強防呆預設 2000)
        target_cal_raw = cur_user.get("target_calories")
        target_cal = int(target_cal_raw) if target_cal_raw is not None else 2000
        
        try:
            # 讀取該用戶的所有健康日誌
            logs_res = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).execute()
            all_logs = logs_res.data if logs_res.data else []
            
            # 使用 Python 處理今日日期
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            diet_today = 0
            exercise_today = 0
            
            for log in all_logs:
                # 轉換 ISO 時間字串為日期格式
                log_date = datetime.fromisoformat(log["logged_at"].replace("Z", "+00:00")).strftime("%Y-%m-%d")
                if log_date == today_str:
                    data = log["parsed_data"]
                    if log["type"] == "diet":
                        diet_today += int(data.get("calories", 0))
                    elif log["type"] == "exercise":
                        exercise_today += int(data.get("calories_burned", 0))
            
            # 計算淨熱量餘額 (攝取減消耗)
            net_balance = diet_today - exercise_today
            
            # 熱量儀表板排版 (分三欄)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="dashboard-box" style="border-top: 5px solid #ff4b4b;">
                    <div style="color: gray; font-size: 14px;">🍎 今日飲食攝取</div>
                    <div style="font-size: 28px; font-weight: bold; color: #ff4b4b; margin: 10px 0;">{diet_today}</div>
                    <div style="color: gray; font-size: 12px;">kcal</div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="dashboard-box" style="border-top: 5px solid #1f77b4;">
                    <div style="color: gray; font-size: 14px;">🏃 今日運動消耗</div>
                    <div style="font-size: 28px; font-weight: bold; color: #1f77b4; margin: 10px 0;">{exercise_today}</div>
                    <div style="color: gray; font-size: 12px;">kcal</div>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                # 判斷是否處於熱量盈餘狀態 (淨熱量餘額小於或等於目標為綠色控制良好，大於為紅色盈餘)
                is_surplus = net_balance > target_cal
                balance_color = "#28a745" if not is_surplus else "#dc3545"
                
                st.markdown(f"""
                <div class="dashboard-box" style="border-top: 5px solid {balance_color};">
                    <div style="color: gray; font-size: 14px;">⚖️ 淨熱量餘額</div>
                    <div style="font-size: 28px; font-weight: bold; color: {balance_color}; margin: 10px 0;">{net_balance}</div>
                    <div style="color: gray; font-size: 12px;">目標上限: {target_cal} kcal</div>
                </div>
                """, unsafe_allow_html=True)

            st.write("")
            if is_surplus:
                st.warning(f"⚠️ 今日淨卡路里已超出您的每日設定上限 {target_cal} kcal！多做一些運動可以有效扣減多餘熱量唷！")
            else:
                st.success(f"🎉 乾淨漂亮！您目前的淨熱量控制在安全範圍內，目前成功創造了 {target_cal - net_balance} kcal 的健康熱量缺口！")
                
            # ------------------------------------------
            # 統計近一週趨勢圖
            # ------------------------------------------
            st.markdown("---")
            st.subheader("📈 近一週熱量控制趨勢圖")
            
            # 產生裝載最近 7 天日期序列
            date_list = [(datetime.now() - timedelta(days=i)).strftime("%m/%d") for i in range(6, -1, -1)]
            
            # 初始化每日數據字典
            daily_diet = {d: 0 for d in date_list}
            daily_exercise = {d: 0 for d in date_list}
            
            for log in all_logs:
                log_dt = datetime.fromisoformat(log["logged_at"].replace("Z", "+00:00"))
                log_md = log_dt.strftime("%m/%d")
                if log_md in daily_diet:
                    data = log["parsed_data"]
                    if log["type"] == "diet":
                        daily_diet[log_md] += int(data.get("calories", 0))
                    elif log["type"] == "exercise":
                        daily_exercise[log_md] += int(data.get("calories_burned", 0))
            
            chart_list = []
            for d in date_list:
                chart_list.append({
                    "日期": d,
                    "飲食攝取 (kcal)": daily_diet[d],
                    "運動消耗 (kcal)": daily_exercise[d],
                    "淨餘額 (kcal)": daily_diet[d] - daily_exercise[d],
                    "目標上限控制線": target_cal
                })
            
            df_chart = pd.DataFrame(chart_list).set_index("日期")
            st.line_chart(df_chart)
            
        except Exception as e:
            st.error(f"讀取熱量統計表失敗：{e}")

    # ------------------------------------------
    # 分頁 C：家庭動態牆
    # ------------------------------------------
    elif menu == "💬 家庭動態牆":
        st.title("💬 家庭健康動態牆")
        st.caption("在這裡可以看到所有家人的即時動態，點擊下方按鈕為彼此加油打氣！")
        
        try:
            members_res = supabase.table("profiles").select("id, display_name").execute()
            member_dict = {m["id"]: m["display_name"] for m in members_res.data}
            
            logs_res = supabase.table("health_logs").select("*").order("logged_at", desc=True).execute()
            
            if not logs_res.data:
                st.info("目前家庭內還沒有任何健康日誌，快去『AI 智慧紀錄』寫下第一筆吧！")
            else:
                for log in logs_res.data:
                    author = member_dict.get(log["user_id"], "未知成員")
                    log_time = datetime.fromisoformat(log["logged_at"].replace("Z", "+00:00")).strftime("%m/%d %H:%M")
                    
                    is_diet = log["type"] == "diet"
                    card_class = "health-card" if is_diet else "health-card exercise-card"
                    emoji = "🍎 飲食紀錄" if is_diet else "🏃 運動紀錄"
                    
                    with st.container():
                        st.markdown(f"""
                        <div class="{card_class}">
                            <div style="display: flex; justify-content: space-between;">
                                <strong>👤 {author} ({emoji})</strong>
                                <span style="color: gray; font-size: 12px;">{log_time}</span>
                            </div>
                            <hr style="margin: 8px 0;">
                        """, unsafe_allow_html=True)
                        
                        raw_val = log.get("raw_input", "")
                        if raw_val and raw_val.startswith("data:image"):
                            st.image(raw_val, width=150)
                        elif raw_val:
                            st.write(f"📝 *備註: {raw_val}*")
                            
                        data = log["parsed_data"]
                        if is_diet:
                            st.markdown(f"""
                            <span class="metric-val">{data.get('calories', 0)}</span> kcal | 
                            🥩 蛋白質 {data.get('protein', 0)}g | 
                            🍞 碳水 {data.get('carbs', 0)}g | 
                            🥑 脂肪 {data.get('fat', 0)}g
                            """, unsafe_allow_html=True)
                            st.write(f"💡 *AI 建議：{data.get('health_tip', '無')}*")
                        else:
                            st.markdown(f"""
                            🏃 運動: **{data.get('exercise_type', '運動')}** | 
                            ⏱️ 時長: **{data.get('duration_minutes', 0)}** 分 | 
                            🔥 消耗: <span class="metric-val">{data.get('calories_burned', 0)}</span> kcal
                            """, unsafe_allow_html=True)
                            st.write(f"✨ *AI 鼓勵：{data.get('tip', '無')}*")
                            
                        cheers = log.get("cheers", {})
                        if cheers:
                            cheer_text = " ".join([f"{name}: {em}" for name, em in cheers.items()])
                            st.markdown(f"<div style='background-color:#fff3cd; padding:4px 8px; border-radius:4px; font-size:13px;'>💝 家人加油團：{cheer_text}</div>", unsafe_allow_html=True)
                            
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        with st.expander("👉 給家人一個加油鼓勵！", expanded=False):
                            col1, col2, col3, col4, col5 = st.columns(5)
                            cur_name = cur_user["display_name"]
                            
                            def send_cheer(emoji_selected, log_id=log["id"], current_cheers=cheers):
                                current_cheers[cur_name] = emoji_selected
                                supabase.table("health_logs").update({"cheers": current_cheers}).eq("id", log_id).execute()
                                st.success(f"已送出 {emoji_selected} 鼓勵！")
                                st.rerun()
                                
                            if col1.button("👍", key=f"cheer1_{log['id']}"): send_cheer("👍")
                            if col2.button("🔥", key=f"cheer2_{log['id']}"): send_cheer("🔥")
                            if col3.button("💪", key=f"cheer3_{log['id']}"): send_cheer("💪")
                            if col4.button("❤️", key=f"cheer4_{log['id']}"): send_cheer("❤️")
                            if col5.button("🌟", key=f"cheer5_{log['id']}"): send_cheer("🌟")
                        st.write("") 
        except Exception as e:
            st.error(f"載入動態牆失敗：{e}")

    # ------------------------------------------
    # 分頁 D：體重管理
    # ------------------------------------------
    elif menu == "📈 體重管理":
        st.title("📈 體重管理中心")
        st.write("記錄下您今天的體重，追蹤長期的體重變化曲線。")
        
        with st.form("weight_log_form"):
            new_weight = st.number_input("今日體重 (kg)", min_value=1.0, max_value=300.0, value=60.0, step=0.1)
            submitted = st.form_submit_button("💾 記錄今日體重", use_container_width=True)
            if submitted:
                try:
                    supabase.table("weight_logs").insert({
                        "user_id": cur_user["id"], "weight": new_weight
                    }).execute()
                    st.success("體重已成功記錄！")
                except Exception as e:
                    st.error(f"記錄體重出錯：{e}")
                    
        st.subheader("📊 您的體重趨勢圖")
        try:
            w_res = supabase.table("weight_logs").select("*").eq("user_id", cur_user["id"]).order("logged_at", desc=False).execute()
            if w_res.data:
                chart_data = []
                for w in w_res.data:
                    local_time = datetime.fromisoformat(w["logged_at"].replace("Z", "+00:00")).strftime("%m/%d")
                    chart_data.append({"日期": local_time, "體重 (kg)": float(w["weight"])})
                st.line_chart(pd.DataFrame(chart_data).set_index("日期"))
            else:
                st.info("尚無體重記錄，請登錄第一筆體重！")
        except Exception as e:
            st.error(f"讀取趨勢失敗：{e}")

    # ------------------------------------------
    # 分頁 E：角色設定
    # ------------------------------------------
    elif menu == "👤 角色設定":
        st.title("👤 角色與卡路里目標設定")
        
        # 讀取當前的目標熱量 (超強防呆預設 2000)
        current_target_cal_raw = cur_user.get("target_calories")
        current_target_cal = int(current_target_cal_raw) if current_target_cal_raw is not None else 2000
        
        with st.form("profile_update_form"):
            current_display_name = st.text_input("更換您的稱呼", value=cur_user["display_name"])
            target_calories_val = st.number_input("每日目標熱量上限 (kcal) (TDEE/目標攝取)", min_value=500, max_value=10000, value=int(current_target_cal), step=50)
            submitted = st.form_submit_button("💾 儲存修改", use_container_width=True)
            if submitted:
                try:
                    # 更新雲端個人資料 (包含新名字與新熱量上限)
                    update_res = supabase.table("profiles").update({
                        "display_name": current_display_name,
                        "target_calories": target_calories_val
                    }).eq("id", cur_user["id"]).execute()
                    
                    if update_res.data:
                        st.success("設定修改儲存成功！")
                        st.session_state.current_user = update_res.data[0]
                        st.rerun()
                except Exception as e:
                    st.error(f"修改個人設定失敗：{e}")