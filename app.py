import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json
import base64
from PIL import Image
import io

# ------------------------------------------
# Page Configuration & Style Settings
# ------------------------------------------
st.set_page_config(
    page_title="小小家庭健康久久",
    page_icon="❤️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 套用精美的自訂 CSS 樣式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700;900&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans TC', sans-serif;
    }
    
    /* 卡片設計 */
    .health-card {
        background-color: #ffffff;
        border-radius: 20px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border-left: 6px solid #f43f5e;
        margin-bottom: 20px;
    }
    .exercise-card {
        border-left: 6px solid #3b82f6;
    }
    
    /* 數值高亮 */
    .metric-val {
        font-size: 24px;
        font-weight: 900;
        color: #f43f5e;
    }
    
    /* 能量電池樣式 */
    .battery-container {
        border: 4px solid #475569;
        border-radius: 20px;
        padding: 4px;
        background-color: #f8fafc;
        width: 100%;
        max-width: 240px;
        height: 100px;
        position: relative;
        display: flex;
        align-items: center;
        margin: 0 auto;
    }
    .battery-fluid {
        height: 100%;
        border-radius: 12px;
        transition: width 0.5s ease;
    }
    .battery-text {
        position: absolute;
        width: 100%;
        text-align: center;
        font-weight: 900;
        font-size: 20px;
        color: #1e293b;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# 雲端環境檢查與連線初始化 (Supabase & Gemini)
# ------------------------------------------
# 檢查 Streamlit Secrets 是否設定
if (
    "SUPABASE_URL" not in st.secrets or 
    "SUPABASE_KEY" not in st.secrets or 
    "GEMINI_API_KEY" not in st.secrets
):
    st.title("🛠️ 雲端服務尚未完成連線設定")
    st.info("""
    歡迎來到「小小家庭健康久久」！在我們開始之前，請在您的 Streamlit Cloud 後台設定您的秘密金鑰（Secrets）：
    
    請將以下內容複製並貼入 Streamlit Dashboard -> App Settings -> Secrets 中：
    ```toml
    SUPABASE_URL = "您的 Supabase URL"
    SUPABASE_KEY = "您的 Supabase Anon Key"
    GEMINI_API_KEY = "您的 Google Gemini API Key"
    ```
    """)
    st.stop()

# 延遲載入 Supabase 套件以加快載入
from supabase import create_client

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def init_gemini():
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return genai.GenerativeModel("gemini-1.5-flash")

supabase = get_supabase()
model = init_gemini()

# ------------------------------------------
# Session State Initialization
# ------------------------------------------
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "ai_parsed_result" not in st.session_state:
    st.session_state.ai_parsed_result = None
if "user_raw_desc" not in st.session_state:
    st.session_state.user_raw_desc = ""
if "image_base64" not in st.session_state:
    st.session_state.image_base64 = None

# ------------------------------------------
# Helper Functions
# ------------------------------------------
def image_to_base64(image_file):
    img = Image.open(image_file)
    # 智慧型圖片壓縮，將寬高限制在最大 800px 以節省資料庫空間
    img.thumbnail((800, 800))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=80)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

# ------------------------------------------
# 登入與角色切換頁面
# ------------------------------------------
if st.session_state.current_user is None:
    st.title("❤️ 小小家庭健康久久")
    st.caption("免註冊家庭健康管理！直接點擊您的名字即可進入。")
    st.markdown("---")
    
    st.subheader("👥 誰要開始記錄？請選擇角色")
    
    try:
        # 從 profiles 資料表中讀取所有成員
        res = supabase.table("profiles").select("*").execute()
        members = res.data if res.data else []
    except Exception as e:
        st.error(f"連線至資料庫失敗，請確認您的 SQL 腳本是否已在 Supabase 執行成功。錯誤：{e}")
        st.stop()
        
    if not members:
        st.info("💡 目前系統中還沒有任何成員，請在下方新增第一個角色！")
    else:
        # 繪製精美的角色選取按鈕
        cols = st.columns(3)
        for idx, member in enumerate(members):
            col_idx = idx % 3
            if cols[col_idx].button(f"👤 {member['display_name']}", key=f"user_{member['id']}", use_container_width=True):
                st.session_state.current_user = member
                st.rerun()
                
    st.markdown("---")
    st.subheader("➕ 新增家庭新成員")
    
    with st.form("new_user_form"):
        new_name = st.text_input("成員稱呼 (例如：爸爸、媽媽、Leon、Lily)", placeholder="輸入好記的稱呼...")
        target_cal = st.number_input("每日目標熱量預算 (kcal)", min_value=800, max_value=5000, value=2000, step=100)
        submitted = st.form_submit_button("確認新增並登入", use_container_width=True)
        
        if submitted and new_name.strip():
            try:
                # 寫入 Supabase profiles 資料表
                new_user_payload = {
                    "display_name": new_name.strip(),
                    "target_calories": int(target_cal),
                    "family_id": "00000000-0000-0000-0000-000000000000"
                }
                insert_res = supabase.table("profiles").insert(new_user_payload).execute()
                if insert_res.data:
                    st.success(f"🎉 歡迎 {new_name} 加入健康久久家庭！")
                    st.session_state.current_user = insert_res.data[0]
                    st.rerun()
            except Exception as e:
                st.error(f"新增角色失敗，請確認資料表結構：{e}")

# ------------------------------------------
# 主系統介面
# ------------------------------------------
else:
    cur_user = st.session_state.current_user
    
    # 頂部 Sidebar 導覽列與角色切換
    with st.sidebar:
        st.write(f"當前使用者：**👤 {cur_user['display_name']}**")
        if st.button("🔄 切換身分 / 新增角色", use_container_width=True):
            st.session_state.current_user = None
            st.session_state.ai_parsed_result = None
            st.rerun()
        st.markdown("---")
        menu = st.radio(
            "🧭 功能選單",
            ["✨ AI 智慧紀錄", "⚡ 熱量收支與電池", "📊 跨維度數據報表", "💬 家族動態牆", "⚙️ 個人設定"]
        )
        
    # ------------------------------------------
    # 分頁 A：AI 智慧紀錄 (單一輸入、多卡自動拆分、雙軌微調與 Refresh)
    # ------------------------------------------
    if menu == "✨ AI 智慧紀錄":
        st.title("✨ AI 智慧混合紀錄")
        st.caption("直接像寫日記一樣打字！Gemini AI 會自動分拆多個飲食與運動項目，並支援直接修改與重新估算。")
        
        # 智慧輸入框
        user_desc = st.text_area(
            "今天做了什麼或吃了什麼？",
            value=st.session_state.user_raw_desc,
            placeholder="例: 我今天早餐吃了一個漢堡和冰奶茶，中午吃雞腿便當。下午去慢跑了30分鐘。",
            height=120
        )
        
        # 相機/相片上傳
        uploaded_image = st.file_uploader("📸 拍照或上傳今日餐點/運動照片 (選填)", type=["jpg", "png", "jpeg"])
        
        col1, col2 = st.columns(2)
        
        with col1:
            analyze_btn = st.button("✨ 智慧混合大腦分析", use_container_width=True, type="primary")
        with col2:
            if st.button("🧹 清除重寫", use_container_width=True):
                st.session_state.user_raw_desc = ""
                st.session_state.ai_parsed_result = None
                st.session_state.image_base64 = None
                st.rerun()
                
        # 執行 AI 分析
        if analyze_btn:
            if not user_desc.strip() and not uploaded_image:
                st.warning("請先輸入一些文字描述或上傳照片喔！")
            else:
                with st.spinner("🧠 AI 大腦正在全力拆分解析中..."):
                    try:
                        # 處理圖片
                        img_data = None
                        if uploaded_image:
                            st.session_state.image_base64 = image_to_base64(uploaded_image)
                            # 用於 Gemini 多模態輸入的 Image 物件
                            img_data = Image.open(uploaded_image)
                            
                        # 建構強大的 Gemini 系統提示詞
                        prompt = """
                        你是一位專業的家庭營養師與運動教練。
                        請分析使用者輸入的飲食與運動內容（如果是照片請仔細判斷食物種類，若照片含文字也請一併參考）。
                        請將內容拆分為飲食項目與運動項目，並嚴格以 JSON 格式回傳，格式如下：
                        {
                          "diets": [
                            {
                              "food_items": ["食物項目名稱"],
                              "calories": 估計總熱量(整數, kcal),
                              "protein": 蛋白質(整數, 克),
                              "carbs": 碳水化合物(整數, 克),
                              "fat": 脂肪(整數, 克),
                              "health_tip": "給家人的溫馨健康建議(50字內)"
                            }
                          ],
                          "exercises": [
                            {
                              "exercise_type": "運動項目名稱",
                              "duration_minutes": 運動時長(整數, 分鐘),
                              "calories_burned": 消耗熱量(整數, kcal),
                              "tip": "給家人的運動勉勵與提醒(50字內)"
                            }
                          ]
                        }
                        如果只有飲食，則 "exercises" 陣列為空；如果只有運動，則 "diets" 陣列為空。
                        請確保回傳內容是「純 JSON 格式」，不要包含任何 markdown 標記（如 ```json）或額外的說明文字。
                        """
                        
                        inputs = [prompt, user_desc]
                        if img_data:
                            inputs.append(img_data)
                            
                        response = model.generate_content(inputs)
                        raw_text = response.text.strip()
                        
                        # 清理 Markdown JSON 語法殘留
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        raw_text = raw_text.strip()
                        
                        st.session_state.ai_parsed_result = json.loads(raw_text)
                        st.session_state.user_raw_desc = user_desc
                    except Exception as e:
                        st.error(f"AI 解析失敗，請再試一次或改用文字描述得更詳細。錯誤：{e}")

        # ------------------------------------------
        # 雙軌微調與直接修改確認面板
        # ------------------------------------------
        if st.session_state.ai_parsed_result:
            st.markdown("---")
            st.subheader("💡 AI 智慧估算結果 (請於下方直接核對與微調)")
            
            parsed = st.session_state.ai_parsed_result
            diets_list = parsed.get("diets", [])
            exercises_list = parsed.get("exercises", [])
            
            # 使用單一儲存表單，讓使用者能一口氣儲存所有拆分出來的卡片
            with st.form("confirm_all_logs_form"):
                saved_diets = []
                saved_exercises = []
                
                # 1. 顯示並編輯所有偵測到的飲食卡片
                if diets_list:
                    st.markdown("#### 🍎 偵測到飲食項目")
                    for idx, diet in enumerate(diets_list):
                        with st.container():
                            st.markdown(f"**飲食紀錄 #{idx+1}**")
                            col1, col2 = st.columns(2)
                            with col1:
                                food_name = st.text_input(f"食物項目 (飲食 #{idx+1})", value=", ".join(diet.get("food_items", [])))
                            with col2:
                                cal = st.number_input(f"估計熱量 kcal (飲食 #{idx+1})", value=int(diet.get("calories", 0)), step=10)
                            
                            with st.expander(f"📊 微調三大營養素 (飲食 #{idx+1})"):
                                c1, c2, c3 = st.columns(3)
                                with c1: pro = st.number_input(f"蛋白質 g (飲食 #{idx+1})", value=int(diet.get("protein", 0)))
                                with c2: carbs = st.number_input(f"碳水 g (飲食 #{idx+1})", value=int(diet.get("carbs", 0)))
                                with c3: fat = st.number_input(f"脂肪 g (飲食 #{idx+1})", value=int(diet.get("fat", 0)))
                                
                            tip = st.text_input(f"AI 建議 (飲食 #{idx+1})", value=diet.get("health_tip", ""))
                            st.markdown("---")
                            
                            saved_diets.append({
                                "food_items": [f.strip() for f in food_name.split(",")],
                                "calories": cal,
                                "protein": pro,
                                "carbs": carbs,
                                "fat": fat,
                                "health_tip": tip
                            })
                            
                # 2. 顯示並編輯所有偵測到的運動卡片
                if exercises_list:
                    st.markdown("#### 🏃 偵測到運動項目")
                    for idx, ex in enumerate(exercises_list):
                        with st.container():
                            st.markdown(f"**運動紀錄 #{idx+1}**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                ex_type = st.text_input(f"運動項目 (運動 #{idx+1})", value=ex.get("exercise_type", ""))
                            with col2:
                                duration = st.number_input(f"時長 min (運動 #{idx+1})", value=int(ex.get("duration_minutes", 0)))
                            with col3:
                                burn = st.number_input(f"消耗熱量 kcal (運動 #{idx+1})", value=int(ex.get("calories_burned", 0)))
                                
                            ex_tip = st.text_input(f"AI 運動提醒 (運動 #{idx+1})", value=ex.get("tip", ""))
                            st.markdown("---")
                            
                            saved_exercises.append({
                                "exercise_type": ex_type,
                                "duration_minutes": duration,
                                "calories_burned": burn,
                                "tip": ex_tip
                            })
                
                # 如果使用者覺得不準，可以透過文字補充指令，重新驅動 AI 微調
                st.markdown("💬 **覺得估算不準？** 可以在最上方文字框**補充細節**（如：『排骨是炸的』或『跑步強度很高』），重新點擊『智慧混合大腦分析』，AI 就會即時自動重算喔！")
                
                submit_all = st.form_submit_button("💾 確定！一口氣全部記下來", use_container_width=True)
                
                if submit_all:
                    try:
                        # 逐筆寫入 Supabase health_logs 表格
                        now_str = datetime.now().isoformat()
                        
                        # 寫入飲食
                        for diet_item in saved_diets:
                            supabase.table("health_logs").insert({
                                "user_id": cur_user["id"],
                                "type": "diet",
                                "raw_input": st.session_state.image_base64 if st.session_state.image_base64 else st.session_state.user_raw_desc,
                                "parsed_data": diet_item,
                                "cheers": {},
                                "comments": []
                            }).execute()
                            
                        # 寫入運動
                        for ex_item in saved_exercises:
                            supabase.table("health_logs").insert({
                                "user_id": cur_user["id"],
                                "type": "exercise",
                                "raw_input": st.session_state.user_raw_desc,
                                "parsed_data": ex_item,
                                "cheers": {},
                                "comments": []
                            }).execute()
                            
                        st.success("🎉 所有項目已成功拆分儲存至雲端家庭牆！")
                        st.session_state.ai_parsed_result = None
                        st.session_state.user_raw_desc = ""
                        st.session_state.image_base64 = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"雲端儲存失敗：{e}")

    # ------------------------------------------
    # 分頁 B：熱量收支與能量電池
    # ------------------------------------------
    elif menu == "⚡ 熱量收支與電池":
        st.title("⚡ 每日卡路里收支看板")
        st.caption("拋棄冰冷數字！用直覺的「能量電池」看今日餘額，用「紅綠燈便當」看健康比例。")
        
        # 抓取今天的使用者日誌
        today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")
        try:
            logs_res = supabase.table("health_logs")\
                .select("*")\
                .eq("user_id", cur_user["id"])\
                .gte("logged_at", today_start)\
                .execute()
                
            today_logs = logs_res.data if logs_res.data else []
        except Exception as e:
            st.error(f"讀取收支數據出錯：{e}")
            today_logs = []
            
        target_cal = cur_user.get("target_calories", 2000)
        
        # 計算攝取與消耗
        total_eat = 0
        total_burn = 0
        carbs = 0
        protein = 0
        fat = 0
        
        for log in today_logs:
            data = log.get("parsed_data", {})
            if log["type"] == "diet":
                total_eat += data.get("calories", 0)
                protein += data.get("protein", 0)
                carbs += data.get("carbs", 0)
                fat += data.get("fat", 0)
            elif log["type"] == "exercise":
                total_burn += data.get("calories_burned", 0)
                
        net_calorie = total_eat - total_burn
        battery_level = min(100, max(5, round((net_calorie / target_cal) * 100))) if target_cal > 0 else 5
        
        # 決定電池顏色
        if battery_level > 100:
            battery_color = "linear-gradient(90deg, #ef4444 0%, #b91c1c 100%)"
            battery_status = "⚠️ 能量超載！今日卡路里已爆表，快去運動幫電池降溫！"
        elif battery_level > 80:
            battery_color = "linear-gradient(90deg, #f59e0b 0%, #d97706 100%)"
            battery_status = "⚡ 電量充足！已接近今日上限，晚餐請選擇清淡食物。"
        else:
            battery_color = "linear-gradient(90deg, #10b981 0%, #059669 100%)"
            battery_status = "🔋 電量安全！您今天控制得很棒，還有剩餘卡路里額度可以使用。"

        st.markdown("### 🔋 今日健康能量電池")
        # 繪製 HTML/CSS 電池
        st.markdown(f"""
        <div class="battery-container">
            <div class="battery-fluid" style="width: {battery_level}%; background: {battery_color};"></div>
            <div class="battery-text">{net_calorie} / {target_cal} kcal</div>
            <div style="position: absolute; right: -8px; top: 32px; width: 6px; height: 32px; background-color: #475569; border-radius: 0 4px 4px 0;"></div>
        </div>
        <p style="text-align: center; font-size: 13px; color: gray; margin-top: 8px;">當前電量: {battery_level}%</p>
        """, unsafe_allow_html=True)
        
        st.info(battery_status)
        
        # 🍱 紅綠燈便當圓餅盤 (三大營養素比例)
        st.markdown("### 🍱 今日飲食紅綠燈便當")
        total_macros_weight = carbs + protein + fat
        if total_macros_weight > 0:
            carbs_pct = round((carbs / total_macros_weight) * 100)
            protein_pct = round((protein / total_macros_weight) * 100)
            fat_pct = round((fat / total_macros_weight) * 100)
        else:
            # 預設黃金比例
            carbs_pct, protein_pct, fat_pct = 50, 20, 30
            
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-around;">
            <div style="width: 120px; height: 120px; border-radius: 50%; background: conic-gradient(#fbbf24 0% {carbs_pct}%, #3b82f6 {carbs_pct}% {carbs_pct + protein_pct}%, #ef4444 {carbs_pct + protein_pct}% 100%); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 2px 5px rgba(0,0,0,0.1);">
                <div style="width: 70px; height: 70px; border-radius: 50%; background-color: white; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                    <span style="font-size: 10px; color: gray;">總卡路里</span>
                    <strong style="font-size: 14px; color: #334155;">{total_eat}k</strong>
                </div>
            </div>
            <div style="font-size: 12px; line-height: 1.8;">
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#fbbf24; border-radius:50%; margin-right:6px;"></span>澱粉/碳水 (黃燈): <strong>{carbs_pct}%</strong></div>
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#3b82f6; border-radius:50%; margin-right:6px;"></span>優質蛋白 (藍燈): <strong>{protein_pct}%</strong></div>
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#ef4444; border-radius:50%; margin-right:6px;"></span>油脂/脂肪 (紅燈): <strong>{fat_pct}%</strong></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 貼心小技巧
        if carbs_pct > 55:
            st.warning("💡 **飲食小紅燈**：您今天的精緻澱粉比例稍微偏高，晚餐建議可以用雞胸肉、豆腐與多一盤燙青菜來平衡！")
        else:
            st.success("🍱 **飲食綠燈**：您今天的營養素比例非常均衡，繼續保持！")

    # ------------------------------------------
    # 分頁 C：跨維度數據統計報表
    # ------------------------------------------
    elif menu == "📊 跨維度數據報表":
        st.title("📊 家庭數據統計報表")
        st.caption("數據化追蹤！自動加總、表格化呈現您與家人的完整健康收支與體重增減。")
        
        period = st.segmented_control("📅 選擇報表週期", ["日報表", "週報表", "月報表"], default="日報表")
        
        try:
            # 撈取目前使用者所有的 logs 與體重紀錄
            all_logs_res = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).execute()
            all_weights_res = supabase.table("weight_logs").select("*").eq("user_id", cur_user["id"]).execute()
            
            logs_df = pd.DataFrame(all_logs_res.data) if all_logs_res.data else pd.DataFrame()
            weights_df = pd.DataFrame(all_weights_res.data) if all_weights_res.data else pd.DataFrame()
            
            if logs_df.empty and weights_df.empty:
                st.info("目前還沒有任何歷史數據，快去『AI 智慧紀錄』建立第一筆資料吧！")
            else:
                # 數據清理與日期正規化
                if not logs_df.empty:
                    logs_df["date"] = logs_df["logged_at"].apply(lambda x: x.split("T")[0])
                if not weights_df.empty:
                    weights_df["date"] = weights_df["logged_at"].apply(lambda x: x.split("T")[0])
                    
                # 建立日期主軸，合併收支與體重
                dates = sorted(list(set(
                    (logs_df["date"].tolist() if not logs_df.empty else []) + 
                    (weights_df["date"].tolist() if not weights_df.empty else [])
                )), reverse=True)
                
                rows = []
                for dt in dates:
                    day_diet = 0
                    day_ex = 0
                    
                    # 計算該日攝取與消耗
                    if not logs_df.empty:
                        day_logs = logs_df[logs_df["date"] == dt]
                        for _, row in day_logs.iterrows():
                            p_data = row.get("parsed_data", {})
                            if row["type"] == "diet":
                                day_diet += p_data.get("calories", 0)
                            elif row["type"] == "exercise":
                                day_ex += p_data.get("calories_burned", 0)
                                
                    # 抓取該日最新體重
                    day_w = "--"
                    if not weights_df.empty:
                        day_w_df = weights_df[weights_df["date"] == dt]
                        if not day_w_df.empty:
                            day_w = float(day_w_df.iloc[-1]["weight"])
                            
                    rows.append({
                        "date": dt,
                        "diet": day_diet,
                        "exercise": day_ex,
                        "net": day_diet - day_ex,
                        "weight": day_w
                    })
                    
                final_df = pd.DataFrame(rows)
                
                # 計算體重增減趨勢 (與前一次比)
                weight_changes = ["--"] * len(final_df)
                for i in range(len(final_df) - 1, -1, -1):
                    # 往前尋找有效的上一筆體重
                    prev_w = None
                    for j in range(i + 1, len(final_df)):
                        if final_df.iloc[j]["weight"] != "--":
                            prev_w = final_df.iloc[j]["weight"]
                            break
                    if prev_w and final_df.iloc[i]["weight"] != "--":
                        diff = round(final_df.iloc[i]["weight"] - prev_w, 1)
                        weight_changes[i] = f"🔺+{diff}kg" if diff > 0 else (f"📉{diff}kg" if diff < 0 else "0.0kg")
                        
                final_df["體重變化"] = weight_changes
                
                # 依據週期呈現
                if period == "日報表":
                    st.markdown("#### 📅 最近 10 天健康日誌")
                    display_df = final_df.head(10).copy()
                    display_df.columns = ["日期", "🍴 總攝取 (kcal)", "🏃 總消耗 (kcal)", "⚖️ 淨收支", "⚖️ 體重 (kg)", "📈 體重變化"]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                elif period == "週報表":
                    st.markdown("#### 📅 週數據加總報表")
                    # 將日期轉換為 Pandas 週次分組
                    final_df["date_parsed"] = pd.to_datetime(final_df["date"])
                    final_df["週別"] = final_df["date_parsed"].dt.to_period("W").apply(lambda r: f"{r.start.strftime('%m/%d')} ~ {r.end.strftime('%m/%d')}")
                    
                    weekly_grouped = final_df.groupby("週別").agg({
                        "diet": "sum",
                        "exercise": "sum",
                        "net": "sum"
                    }).reset_index().sort_values("週別", ascending=False)
                    
                    weekly_grouped.columns = ["週別期間", "🍴 總攝取 (kcal)", "🏃 總消耗 (kcal)", "⚖️ 淨收支 (kcal)"]
                    st.dataframe(weekly_grouped, use_container_width=True, hide_index=True)
                    
                else:
                    st.markdown("#### 📅 月數據加總報表")
                    final_df["date_parsed"] = pd.to_datetime(final_df["date"])
                    final_df["月份"] = final_df["date_parsed"].dt.strftime("%Y年 %m月")
                    
                    monthly_grouped = final_df.groupby("月份").agg({
                        "diet": "sum",
                        "exercise": "sum",
                        "net": "sum"
                    }).reset_index().sort_values("月份", ascending=False)
                    
                    monthly_grouped.columns = ["月份", "🍴 總攝取 (kcal)", "🏃 總消耗 (kcal)", "⚖️ 淨收支 (kcal)"]
                    st.dataframe(monthly_grouped, use_container_width=True, hide_index=True)
                    
        except Exception as e:
            st.error(f"讀取報表失敗：{e}")

    # ------------------------------------------
    # 分頁 D：家族留言動態牆 (留言板與愛心加油)
    # ------------------------------------------
    elif menu == "💬 家族動態牆":
        st.title("💬 家族動態留言牆")
        st.caption("看看家人的健康好習慣，點選愛心為他們加油，或在留言板留下溫馨鼓勵！")
        
        try:
            # 取得成員名稱對照字典
            members_res = supabase.table("profiles").select("id, display_name").execute()
            member_dict = {m["id"]: m["display_name"] for m in members_res.data}
            
            # 撈取所有日誌 (按時間排序)
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
                    
                    # 繪製卡片
                    st.markdown(f"""
                    <div class="{card_class}">
                        <div style="display: flex; justify-content: space-between;">
                            <strong>👤 {author} ({emoji})</strong>
                            <span style="color: gray; font-size: 11px;">{log_time}</span>
                        </div>
                        <hr style="margin: 8px 0; border: 0.5px solid #f1f5f9;">
                    """, unsafe_allow_html=True)
                    
                    # 處理照片與備註
                    raw_val = log.get("raw_input", "")
                    if raw_val and raw_val.startswith("data:image"):
                        st.image(raw_val, width=200)
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
                        
                    # 顯示加油團
                    cheers = log.get("cheers", {})
                    if cheers:
                        cheer_text = " ".join([f"{name}: {em}" for name, em in cheers.items()])
                        st.markdown(f"<div style='background-color:#fff3cd; padding:4px 10px; border-radius:10px; font-size:12px; font-weight: 500;'>💝 家人加油團：{cheer_text}</div>", unsafe_allow_html=True)
                        
                    # 顯示留言板串內容
                    comments = log.get("comments", [])
                    if comments:
                        st.markdown("<p style='font-size:11px; font-weight:bold; color:gray; margin-top:10px;'>💬 家族留言：</p>", unsafe_allow_html=True)
                        for c in comments:
                            st.markdown(f"""
                            <div style="background-color: #f8fafc; padding: 6px 12px; border-radius: 12px; margin-bottom: 4px; font-size: 11px; display: flex; justify-content: space-between;">
                                <span><strong>{c['user']}:</strong> {c['text']}</span>
                                <span style="color: gray; font-size: 9px;">{c.get('time', '')}</span>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 互動互動彈出選單 (Cheers & Comments)
                    with st.expander("💬 回覆與鼓勵家人", expanded=False):
                        # 加油按鈕
                        col1, col2, col3, col4 = st.columns(4)
                        cur_name = cur_user["display_name"]
                        
                        def send_cheer(emoji_selected, log_id=log["id"], current_cheers=cheers):
                            current_cheers[cur_name] = emoji_selected
                            supabase.table("health_logs").update({"cheers": current_cheers}).eq("id", log_id).execute()
                            st.rerun()
                            
                        if col1.button("👍 加油", key=f"c1_{log['id']}"): send_cheer("👍")
                        if col2.button("🔥 火熱", key=f"c2_{log['id']}"): send_cheer("🔥")
                        if col3.button("💪 強壯", key=f"c3_{log['id']}"): send_cheer("💪")
                        if col4.button("❤️ 溫暖", key=f"c4_{log['id']}"): send_cheer("❤️")
                        
                        # 留言板輸入
                        st.markdown("---")
                        new_comm_text = st.text_input("寫下對家人的關心...", key=f"input_c_{log['id']}")
                        if st.button("💬 傳送留言", key=f"btn_c_{log['id']}"):
                            if new_comm_text.strip():
                                # 取得現有留言
                                current_comments = log.get("comments", [])
                                if not current_comments:
                                    current_comments = []
                                    
                                current_comments.append({
                                    "user": cur_name,
                                    "text": new_comm_text.strip(),
                                    "time": datetime.now().strftime("%H:%M")
                                })
                                # 更新 Supabase
                                supabase.table("health_logs").update({"comments": current_comments}).eq("id", log["id"]).execute()
                                st.rerun()
                    st.write("")
        except Exception as e:
            st.error(f"載入動態牆失敗：{e}")

    # ------------------------------------------
    # 分頁 E：個人設定 (體重登錄與目標卡路里調整)
    # ------------------------------------------
    elif menu == "⚙️ 個人設定":
        st.title("⚙️ 設定中心")
        
        # 1. 登錄體重
        st.subheader("⚖️ 今日體重記錄")
        with st.form("weight_log_form"):
            new_weight = st.number_input("今日體重 (kg)", min_value=1.0, max_value=300.0, value=65.0, step=0.1)
            submitted = st.form_submit_button("💾 記錄體重並儲存", use_container_width=True)
            if submitted:
                try:
                    supabase.table("weight_logs").insert({
                        "user_id": cur_user["id"], "weight": new_weight
                    }).execute()
                    st.success("🎉 今日體重已成功儲存！")
                except Exception as e:
                    st.error(f"記錄體重出錯：{e}")
                    
        # 2. 修改角色與卡路里目標
        st.markdown("---")
        st.subheader("👤 修改目標與名稱")
        with st.form("profile_update_form"):
            current_display_name = st.text_input("更換您的稱呼", value=cur_user["display_name"])
            target_cal_budget = st.number_input("修改每日目標熱量上限 (kcal)", value=int(cur_user.get("target_calories", 2000)), step=100)
            
            submitted = st.form_submit_button("💾 儲存修改", use_container_width=True)
            if submitted:
                try:
                    update_res = supabase.table("profiles").update({
                        "display_name": current_display_name,
                        "target_calories": int(target_cal_budget)
                    }).eq("id", cur_user["id"]).execute()
                    
                    if update_res.data:
                        st.success("設定更新成功！")
                        st.session_state.current_user = update_res.data[0]
                        st.rerun()
                except Exception as e:
                    st.error(f"修改個人設定失敗：{e}")