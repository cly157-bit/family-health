import streamlit as st
import pandas as pd
from datetime import datetime
import json
import base64
from PIL import Image
import io
import google.generativeai as genai
from supabase import create_client

# ------------------------------------------
# 1. 頁面基礎配置與精美 UI 樣式
# ------------------------------------------
st.set_page_config(
    page_title="小小家庭健康久久",
    page_icon="❤️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 載入極致質感的 CSS 樣式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
    
    /* 備份公告樣式 */
    .pin-notice {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border: 2px dashed #f59e0b;
        border-radius: 20px;
        padding: 16px;
        margin-bottom: 20px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
    }
    
    /* 飲食健康日誌卡片 */
    .health-card {
        background-color: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 24px;
        padding: 20px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.4);
        border-left: 6px solid #f43f5e;
        margin-bottom: 18px;
    }
    
    /* 運動健康日誌卡片 */
    .exercise-card {
        border-left: 6px solid #3b82f6 !important;
    }
    
    .metric-val {
        font-size: 24px;
        font-weight: 900;
        color: #f43f5e;
    }
    
    /* 玻璃卡片容器 */
    .glass-container {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(12px);
        border-radius: 28px;
        padding: 22px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: 0 10px 25px rgba(0,0,0,0.03);
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# 2. 初始化 Supabase 與 Gemini 大腦
# ------------------------------------------
@st.cache_resource
def init_connections():
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    client = create_client(supabase_url, supabase_key)
    
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return client

try:
    supabase = init_connections()
except Exception as e:
    st.error(f"❌ 雲端連線初始化失敗，請確認 Streamlit Secrets 設定！錯誤：{e}")
    st.stop()

# ------------------------------------------
# 3. 雲端背景設置套用模組
# ------------------------------------------
def apply_cloud_background(bg_base64, opacity):
    if bg_base64:
        st.markdown(f"""
            <style>
            .stApp {{
                background-image: linear-gradient(rgba(241, 245, 249, {opacity}), rgba(241, 245, 249, {opacity})), url("{bg_base64}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
            </style>
        """, unsafe_allow_html=True)

# ------------------------------------------
# 4. 身分驗證與路由控制大腦 (Session State)
# ------------------------------------------
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "ai_parsed_result" not in st.session_state:
    st.session_state.ai_parsed_result = None
if "active_type" not in st.session_state:
    st.session_state.active_type = None
if "image_base64" not in st.session_state:
    st.session_state.image_base64 = None
if "user_raw_desc" not in st.session_state:
    st.session_state.user_raw_desc = None
if "hide_notice" not in st.session_state:
    st.session_state.hide_notice = False

# 讀取 URL 參數
query_params = st.query_params

# 🔒 簡易免密碼自動登入路由
if "restore_key" in query_params:
    restore_id = query_params["restore_key"]
    try:
        fam_res = supabase.table("families").select("*").eq("id", restore_id).execute()
        if fam_res.data:
            prof_res = supabase.table("profiles").select("*").eq("family_id", restore_id).execute()
            if prof_res.data:
                st.session_state.current_user = prof_res.data[0]
                st.toast(f"🔑 復活網址讀取成功！歡迎回到【{fam_res.data[0]['family_name']}】")
    except Exception as e:
         st.error(f"鑰匙無效或過期：{e}")

# --- 強制阻擋機制：如果無帳號狀態，顯示登入/註冊畫面 ---
if not st.session_state.current_user:
    st.title("❤️ 小小家庭健康久久")
    st.caption("簡單、溫馨，與家人一起健康生活的點滴日記")
    
    tab_login, tab_register = st.tabs(["🔐 舊成員登入", "🆕 創立全新健康小屋"])
    
    with tab_login:
        st.subheader("一鍵安全回娘家")
        with st.form("quick_login_form"):
            login_key = st.text_input("請輸入您的家庭復活金鑰 / 代碼", placeholder="例如: 您的家庭UUID")
            btn_login = st.form_submit_button("進入我的家庭空間 ➔", use_container_width=True)
            if btn_login and login_key.strip():
                try:
                    fam_res = supabase.table("families").select("*").eq("id", login_key.strip()).execute()
                    if fam_res.data:
                        prof_res = supabase.table("profiles").select("*").eq("family_id", login_key.strip()).execute()
                        st.session_state.current_user = prof_res.data[0] if prof_res.data else None
                        st.success("🎉 認證成功！")
                        st.rerun()
                    else:
                        st.error("找不到此金鑰代碼，請重新確認或使用下方註冊建立新家！")
                except Exception as e:
                    st.error(f"登入失敗: {e}")
                    
    with tab_register:
        st.subheader("建立您與家人的獨立看板")
        with st.form("register_new_family_form"):
            new_fam_name = st.text_input("1. 請幫您的家庭取個名字", placeholder="例：天母張家、快樂健康基地")
            creator_name = st.text_input("2. 您的稱呼是什麼？", placeholder="例：爸爸、Leon")
            btn_register = st.form_submit_button("🚀 建立新家並自動綁定 ➔", use_container_width=True)
            if btn_register and new_fam_name.strip() and creator_name.strip():
                try:
                    # 1. 建立家庭群組
                    new_code = f"FAM{datetime.now().strftime('%M%S')}"
                    fam_insert = supabase.table("families").insert({
                        "family_code": new_code,
                        "family_name": new_fam_name.strip()
                    }).execute()
                    
                    if fam_insert.data:
                        new_fam_id = fam_insert.data[0]["id"]
                        
                        # 2. 建立預設使用者帳號
                        mock_auth_id = fam_insert.data[0]["id"] # 使用家庭ID作為首位管理者代碼
                        profile_insert = supabase.table("profiles").insert({
                            "id": mock_auth_id,
                            "family_id": new_fam_id,
                            "display_name": creator_name.strip()
                        }).execute()
                        
                        if profile_insert.data:
                            st.session_state.current_user = profile_insert.data[0]
                            st.success("🎉 家庭建立成功！")
                            st.rerun()
                except Exception as e:
                    st.error(f"建立新家庭失敗：{e}")
    st.stop()

# ------------------------------------------
# 5. 身分認證通過，讀取核心家庭背景設定
# ------------------------------------------
cur_user = st.session_state.current_user
cur_fam_id = cur_user["family_id"]

# 讀取家庭詳細資訊 (含背景圖片設定)
try:
    family_query = supabase.table("families").select("*").eq("id", cur_fam_id).execute()
    if family_query.data:
        cur_fam_info = family_query.data[0]
        apply_cloud_background(cur_fam_info.get("background_image"), cur_fam_info.get("background_opacity", 0.45))
    else:
        cur_fam_info = {"family_name": "溫馨健康家", "target": 2200}
except Exception:
    cur_fam_info = {"family_name": "溫馨健康家", "target": 2200}

# ------------------------------------------
# 6. 主系統頁面導覽選單
# ------------------------------------------
st.sidebar.title("❤️ 小小家庭健康久久")
st.sidebar.caption(f"👤 目前使用者：**{cur_user['display_name']}**")
menu = st.sidebar.radio("主選單", ["🍎 AI 智慧紀錄", "📊 熱量與電量收支", "💬 家庭動態牆", "⚙️ 設定與分享"])

# ------------------------------------------
# 分頁 A：AI 智慧紀錄
# ------------------------------------------
if menu == "🍎 AI 智慧紀錄":
    st.title("🍎 AI 智慧健康紀錄")
    st.caption("直接輸入您吃的東西、做的運動，大腦會自動為您拆分多張紀錄卡片。")
    
    with st.container():
        st.markdown('<div class="glass-container">', unsafe_allow_html=True)
        st.markdown("##### 💡 點選以下快速標籤，秒速測試：")
        
        col_tag1, col_tag2 = st.columns(2)
        if col_tag1.button("🥪 [快速綜合測試] 早餐麵包咖啡、下午慢跑30分鐘", use_container_width=True):
            st.session_state.user_raw_desc = "我早餐吃了草莓麵包與中杯美式，下午去跑步三十分鐘。"
        if col_tag2.button("🚶 [日常飲食運動] 中午吃排骨便當、晚上去散步半小時", use_container_width=True):
            st.session_state.user_raw_desc = "中午吃了排骨便當，晚上和妹妹散步半小時。"
            
        user_desc = st.text_area("今天吃了什麼、做什麼運動？", value=st.session_state.user_raw_desc if st.session_state.user_raw_desc else "", placeholder="例如：早餐吃了個草莓麵包，下午去慢跑了 30 分鐘！")
        
        # 圖片上傳
        uploaded_file = st.file_uploader("📸 拍照或上傳飲食食物照片", type=["jpg", "jpeg", "png"])
        
        btn_analyze = st.button("✨ 智慧大腦一鍵分析 (飲食 + 運動)", use_container_width=True, type="primary")
        st.markdown('</div>', unsafe_allow_html=True)

        if btn_analyze and (user_desc.strip() or uploaded_file):
            with st.spinner("🧠 智慧 AI 正結合營養與健身大腦，極速拆分並估算中..."):
                try:
                    # 使用預先定義支持的 Gemini 模組
                    model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")
                    
                    # 提示詞 (一律拆分成飲食與運動的多卡 JSON 結構)
                    prompt = """
                    你是一位專業的營養師與健身教練。請分析使用者的這段健康描述或照片。
                    請將它『智慧拆分』成個別獨立的「飲食卡片」與「運動卡片」清單。
                    請嚴格『只』回傳以下結構的 JSON 格式數據，不要有任何多餘的前言或 Markdown 裝飾文字：
                    {
                      "cards": [
                        {
                          "type": "diet",
                          "food_name": "食物項目名稱",
                          "calories": 估計卡路里數字,
                          "protein": 估計蛋白質克數,
                          "carbs": 估計碳水克數,
                          "fat": 估計脂肪克數,
                          "tip": "一對一親切健康建議"
                        },
                        {
                          "type": "exercise",
                          "exercise_name": "運動項目名稱",
                          "duration_minutes": 運動時長分鐘數字,
                          "calories_burned": 估算消耗熱量數字,
                          "tip": "暖心運動勉勵與提醒"
                        }
                      ]
                    }
                    """
                    
                    if uploaded_file:
                        img = Image.open(uploaded_file)
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG")
                        img_base64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode()
                        st.session_state.image_base64 = img_base64
                        
                        response = model.generate_content([prompt, img])
                    else:
                        response = model.generate_content(f"使用者輸入: {user_desc}\n\n{prompt}")
                    
                    raw_text = response.text.strip()
                    # 安全解析 JSON 清理
                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                    raw_text = raw_text.strip()
                    
                    st.session_state.ai_parsed_result = json.loads(raw_text)
                    st.session_state.user_raw_desc = user_desc
                    
                except Exception as e:
                    st.error(f"AI 解析失敗，請再試一次，或改用文字詳細描述。錯誤：{e}")

        # 顯示 AI 解析後的預覽修改卡片
        if st.session_state.ai_parsed_result:
            st.markdown("---")
            st.subheader("💡 AI 智慧拆分結果 (您可以現場微調修改數字)")
            
            cards = st.session_state.ai_parsed_result.get("cards", [])
            confirmed_cards = []
            
            with st.form("confirm_all_cards_form"):
                for idx, card in enumerate(cards):
                    c_type = card.get("type", "diet")
                    
                    if c_type == "diet":
                        st.markdown(f"🍎 **卡片 {idx+1}：飲食部分**")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1: f_name = st.text_input("食物項目", value=card.get("food_name", "食物"), key=f"f_name_{idx}")
                        with col2: f_cal = st.number_input("熱量 kcal", value=int(card.get("calories", 0)), key=f"f_cal_{idx}")
                        with col3: f_pro = st.number_input("蛋白 g", value=int(card.get("protein", 0)), key=f"f_pro_{idx}")
                        with col4: f_carbs = st.number_input("碳水 g", value=int(card.get("carbs", 0)), key=f"f_carbs_{idx}")
                        with col5: f_fat = st.number_input("油脂 g", value=int(card.get("fat", 0)), key=f"f_fat_{idx}")
                        f_tip = st.text_input("AI 建議提示", value=card.get("tip", "無"), key=f"f_tip_{idx}")
                        
                        confirmed_cards.append({
                            "type": "diet",
                            "parsed_data": {
                                "food_items": [f_name],
                                "calories": f_cal, "protein": f_pro, "carbs": f_carbs, "fat": f_fat, "health_tip": f_tip
                            }
                        })
                    else:
                        st.markdown(f"🏃 **卡片 {idx+1}：運動部分**")
                        col1, col2, col3 = st.columns(3)
                        with col1: ex_name = st.text_input("運動項目", value=card.get("exercise_name", "運動"), key=f"ex_name_{idx}")
                        with col2: ex_dur = st.number_input("時長 (分鐘)", value=int(card.get("duration_minutes", 0)), key=f"ex_dur_{idx}")
                        with col3: ex_burned = st.number_input("消耗 kcal", value=int(card.get("calories_burned", 0)), key=f"ex_burned_{idx}")
                        ex_tip = st.text_input("AI 運動勉勵", value=card.get("tip", "無"), key=f"ex_tip_{idx}")
                        
                        confirmed_cards.append({
                            "type": "exercise",
                            "parsed_data": {
                                "exercise_type": ex_name,
                                "duration_minutes": ex_dur, "calories_burned": ex_burned, "tip": ex_tip
                            }
                        })
                    st.markdown("---")
                
                submitted = st.form_submit_button("💾 確定！一口氣將上述調整後資料儲存", use_container_width=True, type="primary")
                if submitted:
                    try:
                        for item in confirmed_cards:
                            supabase.table("health_logs").insert({
                                "user_id": cur_user["id"],
                                "type": item["type"],
                                "raw_input": st.session_state.image_base64 if st.session_state.image_base64 else st.session_state.user_raw_desc,
                                "parsed_data": item["parsed_data"],
                                "cheers": {},
                                "comments": []
                            }).execute()
                        
                        st.success("🎉 所有健康日誌已成功儲存至雲端！")
                        st.session_state.ai_parsed_result = None
                        st.session_state.image_base64 = None
                        st.session_state.user_raw_desc = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"儲存失敗：{e}")

# ------------------------------------------
# 分頁 B：熱量與電量收支
# ------------------------------------------
elif menu == "📊 熱量與電量收支":
    st.title("📊 熱量與電量收支")
    
    try:
        logs_res = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).execute()
        total_diet = 0
        total_exercise = 0
        
        # 營養素比例加總
        protein_total = 0
        carbs_total = 0
        fat_total = 0
        
        for log in logs_res.data:
            p_data = log["parsed_data"]
            if log["type"] == "diet":
                total_diet += p_data.get("calories", 0)
                protein_total += p_data.get("protein", 0)
                carbs_total += p_data.get("carbs", 0)
                fat_total += p_data.get("fat", 0)
            else:
                total_exercise += p_data.get("calories_burned", 0)
                
        net_calories = total_diet - total_exercise
        target_calories = cur_fam_info.get("target", 2200)
        battery_pct = min(100, max(5, round((net_calories / target_calories) * 100))) if target_calories > 0 else 50
        
        # 🔋 電池能量條視覺化
        battery_color = "#10b981" # 綠色
        alert_text = "🔋 電量安全！今日熱量控制在綠色安全區，做得非常完美！"
        
        if battery_pct > 100:
            battery_color = "#ef4444" # 紅色
            alert_text = f"⚠️ 能量過載！您今天攝取的淨熱量多出了 {net_calories - target_calories} kcal，多去走走消電吧！"
        elif battery_pct > 80:
            battery_color = "#f59e0b" # 黃色
            alert_text = "⚠️ 電量偏高！建議晚餐搭配一些輕量慢跑或散步來消耗多餘儲能。"

        st.markdown(f"""
        <div class="glass-container" style="text-align: center; margin-bottom: 20px;">
            <h4 style="margin: 0 0 10px 0; color: gray;">⚡ 您的今日健康能量電池</h4>
            <div style="display: flex; justify-content: center; margin: 15px 0;">
                <div style="position: relative; width: 220px; height: 100px; border: 4px solid #334155; border-radius: 22px; padding: 2px; background: #f8fafc; display: flex; align-items: center; overflow: hidden;">
                    <div style="position: absolute; right: -1px; width: 8px; height: 35px; background: #334155; border-radius: 0 6px 6px 0;"></div>
                    <div class="battery-fluid" style="height: 100%; width: {battery_pct}%; background: {battery_color}; border-radius: 14px;"></div>
                    <div style="position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;">
                        <span style="font-size: 20px; font-weight: 900; color: #1e293b;">{net_calories} / {target_calories}</span>
                        <span style="font-size: 9px; font-weight: bold; color: #64748b;">今日淨收支 kcal</span>
                    </div>
                </div>
            </div>
            <div style="background-color: {battery_color}15; border: 1px solid {battery_color}30; padding: 12px; border-radius: 16px; font-size: 13px; color: #1e293b;">
                {alert_text}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 🍱 盤子紅綠燈比例圖
        st.subheader("🍱 今日飲食紅綠燈比例")
        macronutrient_total = protein_total + carbs_total + fat_total
        if macronutrient_total > 0:
            p_pct = round((protein_total / macronutrient_total) * 100)
            c_pct = round((carbs_total / macronutrient_total) * 100)
            f_pct = round((fat_total / macronutrient_total) * 100)
            
            st.markdown(f"""
            <div class="glass-container" style="display: flex; align-items: center; justify-content: space-around;">
                <div style="width: 120px; height: 120px; border-radius: 50%; background: conic-gradient(#fcd34d 0% {c_pct}%, #60a5fa {c_pct}% {c_pct+p_pct}%, #f87171 {c_pct+p_pct}% 100%); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);">
                    <div style="width: 70px; height: 70px; background: white; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                        <span style="font-size: 9px; color: gray; font-weight: bold;">總攝取</span>
                        <span style="font-size: 14px; font-weight: 900; color: #1e293b;">{total_diet}</span>
                    </div>
                </div>
                <div style="font-size: 13px; font-weight: bold; color: #475569;">
                    <div><span style="display: inline-block; width: 10px; height: 10px; background-color: #fcd34d; border-radius: 50%; margin-right: 8px;"></span>澱粉 (碳水): {c_pct}%</div>
                    <div style="margin: 4px 0;"><span style="display: inline-block; width: 10px; height: 10px; background-color: #60a5fa; border-radius: 50%; margin-right: 8px;"></span>蛋白: {p_pct}%</div>
                    <div><span style="display: inline-block; width: 10px; height: 10px; background-color: #f87171; border-radius: 50%; margin-right: 8px;"></span>油脂: {f_pct}%</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("尚無飲食紀錄，請先至 AI 智慧紀錄寫下今天的飲食吧！")
            
    except Exception as e:
        st.error(f"載入能量電池失敗：{e}")

# ------------------------------------------
# 分頁 C：家庭動態牆 (全新加入一鍵 ✕ 關閉公告 + 即時留言板)
# ------------------------------------------
elif menu == "💬 家庭動態牆":
    st.title("💬 家庭健康動態牆")
    
    # ✕ 一鍵點擊隱藏置頂公告功能
    if not st.session_state.hide_notice:
        restore_url = f"https://family-health-chang.streamlit.app/?restore_key={cur_fam_id}"
        st.markdown(f"""
        <div class="pin-notice" style="position: relative;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <strong>📌 【{cur_fam_info['family_name']}】健康救命備份公告</strong>
            </div>
            <p style="font-size:12.5px; color:#475569; margin: 8px 0 0 0;">
                親愛的家人！萬一哪天手機清空、紀錄不見了，<b>不要緊張！</b><br>
                點擊下方專屬復活連結，全家人紀錄就會一秒完美歸隊：<br>
                <a href="{restore_url}" target="_blank" style="word-break:break-all; color:#d97706; font-weight:bold; text-decoration: underline;">{restore_url}</a>
            </p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("✕ 暫時隱藏此置頂備份公告", key="hide_notice_btn"):
            st.session_state.hide_notice = True
            st.rerun()

    st.write("")
    
    # 讀取家庭成員清單與所有日誌
    try:
        members_res = supabase.table("profiles").select("id, display_name").eq("family_id", cur_fam_id).execute()
        member_dict = {m["id"]: m["display_name"] for m in members_res.data}
        member_ids = list(member_dict.keys())
        
        if member_ids:
            logs_res = supabase.table("health_logs").select("*").in_("user_id", member_ids).order("logged_at", desc=True).execute()
            
            if not logs_res.data:
                st.info("目前家庭內還沒有任何日誌，快去寫下第一筆吧！")
            else:
                for log in logs_res.data:
                    author = member_dict.get(log["user_id"], "新家人")
                    log_time = datetime.fromisoformat(log["logged_at"].replace("Z", "+00:00")).strftime("%m/%d %H:%M")
                    
                    is_diet = log["type"] == "diet"
                    card_class = "health-card" if is_diet else "health-card exercise-card"
                    emoji = "🍎 飲食紀錄" if is_diet else "🏃 運動紀錄"
                    
                    st.markdown(f"""
                    <div class="{card_class}">
                        <div style="display: flex; justify-content: space-between;">
                            <strong>👤 {author} ({emoji})</strong>
                            <span style="color: gray; font-size: 11px;">{log_time}</span>
                        </div>
                        <hr style="margin: 8px 0; border: 0; border-top: 1px solid rgba(0,0,0,0.05);">
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
                        🔥 消耗: <span class="metric-val" style="color:#3b82f6;">{data.get('calories_burned', 0)}</span> kcal
                        """, unsafe_allow_html=True)
                        st.write(f"✨ *AI 鼓勵：{data.get('tip', '無')}*")
                        
                    # 顯示拍手/鼓勵按讚
                    cheers = log.get("cheers", {})
                    if cheers:
                        cheer_text = "  ".join([f"{name}: {em}" for name, em in cheers.items()])
                        st.markdown(f"<div style='background-color:#fff3cd; padding:5px 10px; border-radius:12px; font-size:12px; margin-top: 8px; font-weight: bold;'>💝 家人加油團：{cheer_text}</div>", unsafe_allow_html=True)
                    
                    # 💬 顯示留言串 (100% 雲端同步動態顯示)
                    comments_list = log.get("comments", []) or []
                    if comments_list:
                        st.write("")
                        st.markdown("**💬 家庭留言板**")
                        for comment in comments_list:
                            st.markdown(f"""
                            <div style="background-color: rgba(0,0,0,0.02); padding: 6px 12px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.03); margin-bottom: 4px; font-size:12px;">
                                <strong>{comment['user']}:</strong> {comment['text']} 
                                <span style="float: right; color: #94a3b8; font-size: 10px;">{comment.get('time', '')}</span>
                            </div>
                            """, unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 留言板發送表單 (修復核心留言 Bug)
                    with st.expander(f"💬 留言或給 {author} 鼓勵加油"):
                        # 留言輸入框與傳送按鈕
                        with st.form(key=f"comment_form_{log['id']}", clear_on_submit=True):
                            comment_txt = st.text_input("輸入要對家人說的貼心關懷...", key=f"inp_{log['id']}")
                            if st.form_submit_button("傳送留言", use_container_width=True):
                                if comment_txt.strip():
                                    current_time_str = datetime.now().strftime("%H:%M")
                                    new_comment_obj = {
                                        "user": cur_user["display_name"],
                                        "text": comment_txt.strip(),
                                        "time": current_time_str
                                    }
                                    updated_comments = comments_list + [new_comment_obj]
                                    supabase.table("health_logs").update({"comments": updated_comments}).eq("id", log["id"]).execute()
                                    st.toast("💬 留言發送成功！")
                                    st.rerun()
                        
                        # 拍手/鼓勵按讚模組
                        col1, col2, col3, col4, col5 = st.columns(5)
                        cur_name = cur_user["display_name"]
                        
                        def send_cheer(emoji_selected, log_id=log["id"], current_cheers=cheers):
                            current_cheers[cur_name] = emoji_selected
                            supabase.table("health_logs").update({"cheers": current_cheers}).eq("id", log_id).execute()
                            st.toast(f"已送出 {emoji_selected} 鼓勵！")
                            st.rerun()
                            
                        if col1.button("👍", key=f"cheer1_{log['id']}"): send_cheer("👍")
                        if col2.button("🔥", key=f"cheer2_{log['id']}"): send_cheer("🔥")
                        if col3.button("💪", key=f"cheer3_{log['id']}"): send_cheer("💪")
                        if col4.button("❤️", key=f"cheer4_{log['id']}"): send_cheer("❤️")
                        if col5.button("🌟", key=f"cheer5_{log['id']}"): send_cheer("🌟")
                        
                    st.write("")
        else:
            st.info("尚無家庭成員資訊。")
    except Exception as e:
        st.error(f"載入動態牆失敗：{e}")

# ------------------------------------------
# 分頁 D：設定與分享 (全新背景上傳與透明度滑桿)
# ------------------------------------------
elif menu == "⚙️ 設定與分享":
    st.title("⚙️ 設定與分享中心")
    
    # 🎨 1. 家庭空間自訂背景與透明度佈置
    st.subheader("🎨 家庭空間佈置 (全新功能)")
    st.caption("上傳您與家人的生活合照，自訂屬於您們獨一無二的溫馨家庭牆背景：")
    
    with st.container():
        st.markdown('<div class="glass-container">', unsafe_allow_html=True)
        bg_file = st.file_uploader("📸 上傳家庭合照或溫馨背景照片", type=["jpg", "jpeg", "png"], key="bg_uploader")
        
        # 讀取當前透明度
        current_opacity = float(cur_fam_info.get("background_opacity", 0.45))
        bg_opacity_slider = st.slider("背景清透度 (拉桿越右邊，背景照片越鮮色，文字越清亮)", min_value=0.10, max_value=0.95, value=current_opacity, step=0.05)
        
        btn_save_bg = st.button("💾 確定套用家庭背景裝飾", use_container_width=True, type="primary")
        st.markdown('</div>', unsafe_allow_html=True)
        
        if btn_save_bg:
            try:
                update_payload = {"background_opacity": bg_opacity_slider}
                
                # 如果有上傳新背景圖，轉成 Base64 寫入
                if bg_file:
                    img = Image.open(bg_file)
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG")
                    img_base64_str = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode()
                    update_payload["background_image"] = img_base64_str
                
                supabase.table("families").update(update_payload).eq("id", cur_fam_id).execute()
                st.success("🎨 空間美化裝飾設定成功！正在即時刷新...")
                st.rerun()
            except Exception as e:
                st.error(f"背景設定更新失敗：{e}")
                
    st.write("")
    
    # 👤 2. 稱呼修改與目標設定
    st.subheader("👤 個人暱稱與全家目標設定")
    with st.form("profile_target_form"):
        new_name = st.text_input("更換您在家人面前的稱呼", value=cur_user["display_name"])
        new_target = st.number_input("全家每日每人建議熱量目標 (kcal)", value=int(cur_fam_info.get("target", 2200)), step=100)
        
        btn_save_profile = st.form_submit_button("儲存暱稱與熱量設定", use_container_width=True)
        if btn_save_profile:
            try:
                # 更新個人暱稱
                prof_res = supabase.table("profiles").update({"display_name": new_name.strip()}).eq("id", cur_user["id"]).execute()
                # 更新全家每日目標
                supabase.table("families").update({"target": new_target}).eq("id", cur_fam_id).execute()
                
                if prof_res.data:
                    st.session_state.current_user = prof_res.data[0]
                    st.success("設定更新成功！")
                    st.rerun()
            except Exception as e:
                st.error(f"更新設定出錯：{e}")

    st.write("")
    
    # 🔑 3. 常駐防護金鑰與雙軌分流分享
    st.subheader("🔑 常駐防護與分享邀請")
    st.info(f"🗝️ **家庭專屬復活代碼：** `{cur_fam_id}`\n\n建議將此代碼或復活連結複製存入您的 LINE 群組記事本中！")
    
    # 雙軌邀請分流按鈕
    col_invite1, col_invite2 = st.columns(2)
    with col_invite1:
        st.markdown("**🤝 邀請「家人」加入我們家**")
        st.caption("點開連結後，家人會直接加入目前這個家庭看板共用電池。")
        invite_url = f"https://family-health-chang.streamlit.app/?family_id={cur_fam_id}&action=bind_family"
        st.code(invite_url, language="text")
        if st.button("📋 複製家人邀請網址", key="copy_invite_btn"):
            st.toast("已複製家人邀請網址！")
            
    with col_invite2:
        st.markdown("**🏠 推薦「朋友」創立新家**")
        st.caption("點開連結後，同事會引導去自己開一間新小屋，完全不帶您的家庭隱私。")
        recommend_url = "https://family-health-chang.streamlit.app/?action=create_new_family"
        st.code(recommend_url, language="text")
        if st.button("📋 複製推薦新家網址", key="copy_recommend_btn"):
            st.toast("已複製推薦創家網址！")