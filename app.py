import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import json
import base64
from PIL import Image
import io
import uuid
from supabase import create_client

# ------------------------------------------
# 1. 頁面配置與精美 UI 樣式
# ------------------------------------------
st.set_page_config(
    page_title="小小家庭健康久久",
    page_icon="❤️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 自訂 CSS 提升整體視覺質感（包含卡片與電池動畫效果）
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
    
    .health-card {
        background-color: #ffffff;
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        border-left: 6px solid #f43f5e;
        margin-bottom: 15px;
    }
    .exercise-card { border-left: 6px solid #3b82f6; }
    .metric-val { font-size: 26px; font-weight: 900; color: #f43f5e; }
    .comment-box {
        background-color: #f8fafc;
        border-radius: 10px;
        padding: 8px 12px;
        margin-top: 5px;
        font-size: 13px;
        display: flex;
        justify-content: space-between;
    }
    
    /* 能量電池 UI */
    .battery-container {
        border: 4px solid #334155;
        border-radius: 15px;
        padding: 3px;
        background-color: #f1f5f9;
        width: 100%;
        max-width: 220px;
        height: 90px;
        position: relative;
        display: flex;
        align-items: center;
        margin: 10px auto;
    }
    .battery-fluid { height: 100%; border-radius: 10px; transition: width 0.6s ease; }
    .battery-text { position: absolute; width: 100%; text-align: center; font-weight: 900; font-size: 18px; color: #1e293b; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# 2. 雲端服務連線初始化
# ------------------------------------------
def check_secrets():
    for key in ["SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY"]:
        if key not in st.secrets:
            st.error(f"❌ 缺少雲端金鑰：{key}，請在 Streamlit Secrets 中設定。")
            st.stop()

check_secrets()

@st.cache_resource
def init_services():
    client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # 預設先建立連線，之後我們會有自動降級/備用模型的機制
    return client, genai.GenerativeModel("gemini-1.5-flash")

supabase, model = init_services()

# ------------------------------------------
# 3. 狀態管理與輔助函式
# ------------------------------------------
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "parsed_results" not in st.session_state:
    st.session_state.parsed_results = []
if "raw_val" not in st.session_state:
    st.session_state.raw_val = ""

def image_to_base64(uploaded_file):
    img = Image.open(uploaded_file)
    img.thumbnail((500, 500))  # 智慧型縮圖優化儲存空間
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

# 🎯 智慧型備用與容錯生成引擎：防止因為 404 導致系統崩潰
def generate_content_with_fallback(inputs):
    # 依序嘗試的模型名單（AI Studio 最新與最穩定版本）
    models_to_try = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-2.5-flash"
    ]
    last_error = None
    for model_name in models_to_try:
        try:
            temp_model = genai.GenerativeModel(model_name)
            response = temp_model.generate_content(inputs)
            return response, model_name
        except Exception as e:
            last_error = e
            continue
    # 如果全數失敗，拋出最後一次的錯誤
    raise last_error

# ------------------------------------------
# 4. 登入/切換角色頁面
# ------------------------------------------
if st.session_state.current_user is None:
    st.title("❤️ 小小家庭健康久久")
    st.caption("免註冊！點選您的名字即可開始記錄。")
    st.markdown("---")
    
    try:
        res = supabase.table("profiles").select("*").execute()
        members = res.data if res.data else []
    except Exception as e:
        st.error(f"連線資料庫失敗，請確認您的 Supabase 與 Secrets 設定是否正確。錯誤資訊: {e}")
        st.stop()
        
    st.subheader("👪 誰要開始記錄？")
    if members:
        cols = st.columns(2)
        for idx, m in enumerate(members):
            if cols[idx % 2].button(f"👤 {m['display_name']}", key=f"u_{m['id']}", use_container_width=True):
                st.session_state.current_user = m
                st.rerun()
    else:
        st.info("💡 目前資料庫中還沒有任何成員，請在下方建立第一個家庭成員！")
    
    st.markdown("---")
    st.subheader("➕ 新增家庭成員")
    with st.form("add_user"):
        new_name = st.text_input("成員稱呼 (如：爸爸、媽媽、Lily)")
        target_cal = st.number_input("每日熱量預算 (kcal)", value=2000, step=100)
        if st.form_submit_button("確認新增並登入", use_container_width=True) and new_name.strip():
            try:
                new_u = supabase.table("profiles").insert({
                    "display_name": new_name.strip(),
                    "target_calories": int(target_cal),
                    "family_id": "00000000-0000-0000-0000-000000000000"
                }).execute()
                if new_u.data:
                    st.session_state.current_user = new_u.data[0]
                    st.success(f"🎉 成功建立成員：{new_name.strip()}！")
                    st.rerun()
            except Exception as e:
                st.error(f"新增成員失敗，請確認 Supabase 資料表結構。錯誤: {e}")

# ------------------------------------------
# 5. 主系統介面
# ------------------------------------------
else:
    cur_user = st.session_state.current_user
    
    with st.sidebar:
        st.write(f"當前身分：**{cur_user['display_name']}**")
        if st.button("🔄 切換/登出角色", use_container_width=True):
            st.session_state.current_user = None
            st.session_state.parsed_results = []
            st.rerun()
        st.markdown("---")
        # 側邊選單按鈕
        menu = st.radio("功能導覽", ["📸 AI 智慧紀錄", "⚡ 熱量收支表", "📈 數據報表", "💬 家庭動態牆", "👤 個人設定"])

    # --- 分頁 A: AI 智慧紀錄 ---
    if menu == "📸 AI 智慧紀錄":
        st.title("📸 AI 智慧混合紀錄")
        st.caption("輸入整天做了什麼（文字或照片），AI 會自動拆分為多張卡片！")
        
        user_input = st.text_area("今天吃了什麼、或做了什麼運動？", placeholder="例：早餐吃漢堡配冰紅茶，下午慢跑了30分鐘...", height=100)
        uploaded_img = st.file_uploader("拍照或上傳今日餐點照片 (選填)", type=["jpg", "png", "jpeg"])
        
        if st.button("✨ 送出 AI 智慧分析", use_container_width=True, type="primary"):
            if not user_input.strip() and not uploaded_img:
                st.warning("請先輸入文字描述或上傳照片喔！")
            else:
                with st.spinner("AI 大腦正在全力分析拆分中..."):
                    try:
                        img_obj = Image.open(uploaded_img) if uploaded_img else None
                        prompt = """
                        分析輸入內容並拆分為 JSON 列表。格式必須嚴格如下：
                        [
                          {"type":"diet","food_items":["食物名稱"],"calories":熱量整數,"protein":蛋白質克數整數,"carbs":碳水克數整數,"fat":脂肪克數整數,"health_tip":"溫馨飲食建議"},
                          {"type":"exercise","exercise_type":"運動名稱","duration_minutes":運動時間整數,"calories_burned":消耗熱量整數,"tip":"運動提醒勉勵"}
                        ]
                        請確保回傳純 JSON，千萬不要包含 ```json 或任何 markdown 標記。
                        """
                        inputs = [prompt, user_input]
                        if img_obj: 
                            inputs.append(img_obj)
                        
                        # 呼叫具有備用容錯機制的產生函數
                        response, actual_model_used = generate_content_with_fallback(inputs)
                        raw_text = response.text.strip()
                        
                        # 清理可能的 markdown 包裝
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        raw_text = raw_text.strip()
                        
                        st.session_state.parsed_results = json.loads(raw_text)
                        st.session_state.raw_val = image_to_base64(uploaded_img) if uploaded_img else user_input
                    except Exception as e:
                        error_msg = str(e)
                        if "404" in error_msg or "not found" in error_msg:
                            st.error("""
                            ⚠️ **AI 解析失敗：您的 API Key 來源或權限不正確 (404 錯誤)**
                            
                            這通常是因為您設定的 `GEMINI_API_KEY` 權限與 API 連線點不匹配：
                            
                            1. **確認金鑰來源**：請務必至 [Google AI Studio](https://aistudio.google.com/) 申請 **免費的 API Key**。
                               * *注意：如果您是在 Google Cloud Console (GCP) 中建立的 API 金鑰，呼叫此 SDK 時會回報 404 錯誤。*
                            2. **重新貼入 Secrets**：
                               * 進入您 Streamlit Cloud 後台 -> **Manage app** -> **Settings** -> **Secrets**。
                               * 確保您將 AI Studio 複製出來的 `AIzaSy...` 完整、無空格地貼入：
                                 `GEMINI_API_KEY = "您的金鑰"` 並存檔。
                            3. **點擊重啟**：存檔後，在 Streamlit 後台點選 **Reboot app** 即可完美解決！
                            """)
                        else:
                            st.error(f"AI 解析失敗，請描述得更詳細一點並再試一次！錯誤原因: {e}")

        # 多卡編輯面板（當 AI 解析完畢後顯示）
        if st.session_state.parsed_results:
            st.markdown("---")
            st.subheader("💡 AI 智慧拆分結果 (可當場直接修改數字)")
            
            with st.form("confirm_logs"):
                confirmed_list = []
                for i, res in enumerate(st.session_state.parsed_results):
                    if res["type"] == "diet":
                        st.markdown(f"**🍎 飲食項目 #{i+1}**")
                        food = st.text_input("食物名稱", value=", ".join(res.get("food_items", [])), key=f"f_{i}")
                        c1, c2 = st.columns(2)
                        cal = c1.number_input("預估熱量 (kcal)", value=int(res.get("calories", 0)), key=f"c_{i}")
                        tip = st.text_input("AI 建議", value=res.get("health_tip", "飲食均衡身體棒！"), key=f"t_{i}")
                        
                        # 隱藏在展開欄位中的營養素微調
                        with st.expander(f"📊 微調三大營養素 (飲食 #{i+1})"):
                            nc1, nc2, nc3 = st.columns(3)
                            pro = nc1.number_input("蛋白質 (g)", value=int(res.get("protein", 0)), key=f"pro_{i}")
                            carb = nc2.number_input("碳水化合物 (g)", value=int(res.get("carbs", 0)), key=f"carb_{i}")
                            fat_val = nc3.number_input("脂肪 (g)", value=int(res.get("fat", 0)), key=f"fat_{i}")
                            
                        confirmed_list.append({
                            "type": "diet", 
                            "data": {
                                "food_items": [f.strip() for f in food.split(",")], 
                                "calories": cal, 
                                "health_tip": tip, 
                                "protein": pro, 
                                "carbs": carb, 
                                "fat": fat_val
                            }
                        })
                    else:
                        st.markdown(f"**🏃 運動項目 #{i+1}**")
                        ex = st.text_input("運動項目", value=res.get("exercise_type", "運動"), key=f"e_{i}")
                        c1, c2 = st.columns(2)
                        duration = c1.number_input("運動時長 (分鐘)", value=int(res.get("duration_minutes", 0)), key=f"dur_{i}")
                        burn = c2.number_input("消耗熱量 (kcal)", value=int(res.get("calories_burned", 0)), key=f"b_{i}")
                        ex_tip = st.text_input("AI 提醒", value=res.get("tip", "運動流汗真棒！"), key=f"et_{i}")
                        
                        confirmed_list.append({
                            "type": "exercise", 
                            "data": {
                                "exercise_type": ex, 
                                "duration_minutes": duration,
                                "calories_burned": burn, 
                                "tip": ex_tip
                            }
                        })
                
                st.markdown("💬 **貼心提示**：如果數據有偏差，您可以直接在上方打字手動修改數字，點擊儲存將以您的數值為準！")
                
                if st.form_submit_button("💾 確定！一口氣全部記下來", use_container_width=True):
                    try:
                        for item in confirmed_list:
                            supabase.table("health_logs").insert({
                                "user_id": cur_user["id"], 
                                "type": item["type"],
                                "raw_input": st.session_state.raw_val, 
                                "parsed_data": item["data"],
                                "cheers": {}, 
                                "comments": []
                            }).execute()
                        st.success("🎉 所有紀錄已成功同步儲存至雲端家庭動態牆！")
                        st.session_state.parsed_results = []
                        st.session_state.raw_val = ""
                        st.rerun()
                    except Exception as e:
                        st.error(f"雲端儲存失敗，請重試。錯誤: {e}")

    # --- 分頁 B: 熱量收支表 ---
    elif menu == "⚡ 熱量收支表":
        st.title("⚡ 每日卡路里收支看板")
        st.caption("直覺的「能量電池」看今日餘額，以及「紅綠燈便當」健康分析比例。")
        
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            logs = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).gte("logged_at", today).execute().data
        except:
            logs = []
            
        eat, burn = 0, 0
        carbs, protein, fat = 0, 0, 0
        
        for l in (logs or []):
            d = l.get("parsed_data", {})
            if l["type"] == "diet": 
                eat += d.get("calories", 0)
                protein += d.get("protein", 0)
                carbs += d.get("carbs", 0)
                fat += d.get("fat", 0)
            elif l["type"] == "exercise": 
                burn += d.get("calories_burned", 0)
            
        net = eat - burn
        target = cur_user.get("target_calories", 2000)
        
        # 電池進度百分比
        pct = min(100, max(5, int((net / target) * 100))) if target > 0 else 5
        color = "linear-gradient(90deg, #ef4444, #b91c1c)" if net > target else "linear-gradient(90deg, #10b981, #059669)"
        
        st.markdown("### 🔋 今日健康能量電池")
        st.markdown(f"""
        <div class="battery-container">
            <div class="battery-fluid" style="width:{pct}%; background:{color};"></div>
            <div class="battery-text">{net} / {target} kcal</div>
            <div style="position:absolute; right:-8px; width:6px; height:30px; background:#334155; border-radius:0 4px 4px 0;"></div>
        </div>
        <p style="text-align: center; font-size: 13px; color: gray; margin-top: 5px;">目前已消耗電量比：{pct}%</p>
        """, unsafe_allow_html=True)
        
        if net > target:
            st.warning("⚠️ **能量過載！** 今日攝取的熱量已經超出上限，建議晚餐吃得清淡一些，或多去走走消耗熱量喔！")
        else:
            st.success("🔋 **電量安全！** 今日飲食控制得非常理想，請繼續維持健康的生活節奏！")
            
        # 🍱 紅綠燈便當圓餅盤 (三大營養素比例)
        st.markdown("---")
        st.markdown("### 🍱 今日飲食紅綠燈便當")
        total_macros = carbs + protein + fat
        if total_macros > 0:
            carbs_pct = round((carbs / total_macros) * 100)
            protein_pct = round((protein / total_macros) * 100)
            fat_pct = round((fat / total_macros) * 100)
        else:
            carbs_pct, protein_pct, fat_pct = 50, 20, 30
            
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 20px; border: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-around;">
            <div style="width: 120px; height: 120px; border-radius: 50%; background: conic-gradient(#fbbf24 0% {carbs_pct}%, #3b82f6 {carbs_pct}% {carbs_pct + protein_pct}%, #ef4444 {carbs_pct + protein_pct}% 100%); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 2px 5px rgba(0,0,0,0.1);">
                <div style="width: 70px; height: 70px; border-radius: 50%; background-color: white; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                    <span style="font-size: 10px; color: gray;">總攝取</span>
                    <strong style="font-size: 14px; color: #334155;">{eat}k</strong>
                </div>
            </div>
            <div style="font-size: 12px; line-height: 1.8;">
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#fbbf24; border-radius:50%; margin-right:6px;"></span>澱粉/碳水 (黃燈): <strong>{carbs_pct}%</strong></div>
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#3b82f6; border-radius:50%; margin-right:6px;"></span>優質蛋白 (藍燈): <strong>{protein_pct}%</strong></div>
                <div><span style="display:inline-block; width:12px; height:12px; background-color:#ef4444; border-radius:50%; margin-right:6px;"></span>油脂/脂肪 (紅燈): <strong>{fat_pct}%</strong></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # --- 分頁 C: 數據報表 ---
    elif menu == "📈 數據報表":
        st.title("📈 歷史數據與統計報表")
        st.caption("數據化追蹤！自動加總並表格化呈現您的完整健康收支與熱量歷史。")
        
        period = st.segmented_control("選擇報表週期", ["日報表", "週報表", "月報表"], default="日報表")
        
        try:
            all_logs = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).execute().data
        except:
            all_logs = []
            
        if not all_logs:
            st.info("💡 目前還沒有任何歷史數據，快去『AI 智慧紀錄』寫下您的第一筆生活日誌吧！")
        else:
            df_rows = []
            for l in all_logs:
                dt_str = l["logged_at"][:10]
                p_data = l.get("parsed_data", {})
                is_diet = l["type"] == "diet"
                
                df_rows.append({
                    "date": dt_str,
                    "type": "diet" if is_diet else "exercise",
                    "calories": p_data.get("calories", 0) if is_diet else -p_data.get("calories_burned", 0)
                })
                
            base_df = pd.DataFrame(df_rows)
            
            if period == "日報表":
                st.markdown("#### 📅 最近 10 天健康收支表")
                # 分類加總每日數據
                pivot_df = base_df.groupby(["date", "type"])["calories"].sum().unstack(fill_value=0).reset_index()
                if "diet" not in pivot_df: pivot_df["diet"] = 0
                if "exercise" not in pivot_df: pivot_df["exercise"] = 0
                
                pivot_df["exercise"] = pivot_df["exercise"].abs()  # 轉回正數以利閱讀
                pivot_df["net"] = pivot_df["diet"] - pivot_df["exercise"]
                pivot_df = pivot_df.sort_values("date", ascending=False).head(10)
                
                pivot_df.columns = ["日期", "🍴 攝取 (kcal)", "🏃 消耗 (kcal)", "⚖️ 淨額收支"]
                st.dataframe(pivot_df, use_container_width=True, hide_index=True)
                
            elif period == "週報表":
                st.markdown("#### 📅 週數據加總趨勢")
                base_df["date_parsed"] = pd.to_datetime(base_df["date"])
                base_df["週別"] = base_df["date_parsed"].dt.to_period("W").apply(lambda r: f"{r.start.strftime('%m/%d')} ~ {r.end.strftime('%m/%d')}")
                
                # 計算飲食與運動
                base_df["diet_val"] = base_df.apply(lambda r: r["calories"] if r["type"] == "diet" else 0, axis=1)
                base_df["ex_val"] = base_df.apply(lambda r: abs(r["calories"]) if r["type"] == "exercise" else 0, axis=1)
                
                weekly = base_df.groupby("週別").agg({"diet_val": "sum", "ex_val": "sum"}).reset_index()
                weekly["net"] = weekly["diet_val"] - weekly["ex_val"]
                weekly = weekly.sort_values("週別", ascending=False)
                
                weekly.columns = ["週別區間", "🍴 總攝取 (kcal)", "🏃 總消耗 (kcal)", "⚖️ 淨收支"]
                st.dataframe(weekly, use_container_width=True, hide_index=True)
                
            else:
                st.markdown("#### 📅 月數據歷史加總")
                base_df["date_parsed"] = pd.to_datetime(base_df["date"])
                base_df["月份"] = base_df["date_parsed"].dt.strftime("%Y年 %m月")
                
                base_df["diet_val"] = base_df.apply(lambda r: r["calories"] if r["type"] == "diet" else 0, axis=1)
                base_df["ex_val"] = base_df.apply(lambda r: abs(r["calories"]) if r["type"] == "exercise" else 0, axis=1)
                
                monthly = base_df.groupby("月份").agg({"diet_val": "sum", "ex_val": "sum"}).reset_index()
                monthly["net"] = monthly["diet_val"] - monthly["ex_val"]
                monthly = monthly.sort_values("月份", ascending=False)
                
                monthly.columns = ["月份", "🍴 總攝取 (kcal)", "🏃 總消耗 (kcal)", "⚖️ 淨收支"]
                st.dataframe(monthly, use_container_width=True, hide_index=True)

    # --- 分頁 D: 家庭動態牆 ---
    elif menu == "💬 家庭動態牆":
        st.title("💬 家族動態留言牆")
        st.caption("看看家人的健康好習慣，點選愛心為他們加油，或在留言板留下溫馨鼓勵！")
        
        try:
            # 獲取家庭所有日誌
            logs = supabase.table("health_logs").select("*").order("logged_at", desc=True).limit(20).execute().data
            profiles = {p["id"]: p["display_name"] for p in supabase.table("profiles").select("id, display_name").execute().data}
        except:
            logs = []
            profiles = {}
            
        if not logs:
            st.info("💡 目前家庭內還沒有任何健康日誌，快去『AI 智慧紀錄』寫下第一筆吧！")
        else:
            for log in logs:
                name = profiles.get(log["user_id"], "未知成員")
                is_diet = log["type"] == "diet"
                log_time = datetime.fromisoformat(log["logged_at"].replace("Z", "+00:00")).strftime("%m/%d %H:%M")
                
                with st.container():
                    st.markdown(f"""
                    <div class="health-card {'exercise-card' if not is_diet else ''}">
                        <div style="display: flex; justify-content: space-between;">
                            <strong>👤 {name} ({'🍎 飲食' if is_diet else '🏃 運動'})</strong>
                            <span style="color: gray; font-size: 11px;">{log_time}</span>
                        </div>
                        <div style="font-size:20px; font-weight:900; color:{'#f43f5e' if is_diet else '#3b82f6'}; margin:8px 0;">
                            {log['parsed_data'].get('calories', log['parsed_data'].get('calories_burned', 0))} kcal
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 顯示原始描述或照片
                    raw_val = log.get("raw_input", "")
                    if raw_val and raw_val.startswith("data:image"):
                        st.image(raw_val, width=180)
                    elif raw_val:
                        st.write(f"📝 *原始備註: {raw_val}*")
                        
                    # 細節與小建议
                    p_data = log["parsed_data"]
                    if is_diet:
                        st.write(f"🍲 食物項目：**{', '.join(p_data.get('food_items', []))}**")
                        st.write(f"💡 *AI 建議：{p_data.get('health_tip', '無')}*")
                    else:
                        st.write(f"🏃 運動項目：**{p_data.get('exercise_type', '運動')}** (時長 {p_data.get('duration_minutes', 0)} 分鐘)")
                        st.write(f"✨ *AI 鼓勵：{p_data.get('tip', '無')}*")
                        
                    # 顯示加油團 (Cheers)
                    cheers = log.get("cheers", {})
                    if cheers:
                        cheer_text = " ".join([f"{u}: {emo}" for u, emo in cheers.items()])
                        st.markdown(f"<div style='background-color:#fff3cd; padding:4px 10px; border-radius:10px; font-size:12px; font-weight: 500;'>💝 家人加油團：{cheer_text}</div>", unsafe_allow_html=True)
                        
                    # 顯示留言板串內容
                    comments = log.get("comments", [])
                    if comments:
                        st.markdown("<p style='font-size:11px; font-weight:bold; color:gray; margin-top:10px;'>💬 家族留言：</p>", unsafe_allow_html=True)
                        for c in comments:
                            st.markdown(f"""
                            <div class="comment-box">
                                <span><strong>{c['user']}:</strong> {c['text']}</span>
                                <span style="color: gray; font-size: 9px;">{c.get('time', '')}</span>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 留言與加油按鈕
                    with st.popover("💬 回覆與鼓勵家人"):
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
                        if col4.button("❤️ 溫慢", key=f"c4_{log['id']}"): send_cheer("❤️")
                        
                        # 留言板輸入
                        st.markdown("---")
                        new_comm_text = st.text_input("寫下對家人的關心...", key=f"input_c_{log['id']}")
                        if st.button("傳送 🚀", key=f"btn_c_{log['id']}"):
                            if new_comm_text.strip():
                                current_comments = list(comments) if comments else []
                                current_comments.append({
                                    "user": cur_name,
                                    "text": new_comm_text.strip(),
                                    "time": datetime.now().strftime("%H:%M")
                                })
                                supabase.table("health_logs").update({"comments": current_comments}).eq("id", log["id"]).execute()
                                st.rerun()
                    st.write("")

    # --- 分頁 E: 個人設定 ---
    elif menu == "👤 個人設定":
        st.title("👤 個人設定中心")
        
        # 1. 登錄體重
        st.subheader("⚖️ 今日體重記錄")
        try:
            latest_w_data = supabase.table("weight_logs").select("*").eq("user_id", cur_user["id"]).order("logged_at", desc=True).limit(1).execute().data
            current_w = float(latest_w_data[0]["weight"]) if latest_w_data else 65.0
        except:
            current_w = 65.0
            
        with st.form("weight_log_form"):
            new_weight = st.number_input("今日體重 (kg)", min_value=1.0, max_value=300.0, value=current_w, step=0.1)
            submitted_weight = st.form_submit_button("💾 記錄體重並儲存", use_container_width=True)
            if submitted_weight:
                try:
                    supabase.table("weight_logs").insert({
                        "user_id": cur_user["id"], "weight": new_weight
                    }).execute()
                    st.success("🎉 今日體重已成功儲存至雲端資料庫！")
                except Exception as e:
                    st.error(f"記錄體重出錯：{e}")
                    
        # 2. 修改角色與卡路里目標
        st.markdown("---")
        st.subheader("👤 修改目標與名稱")
        with st.form("profile_update_form"):
            current_display_name = st.text_input("更換您的稱呼", value=cur_user["display_name"])
            target_cal_budget = st.number_input("修改每日目標熱量上限 (kcal)", value=int(cur_user.get("target_calories", 2000)), step=100)
            
            submitted_profile = st.form_submit_button("💾 儲存修改", use_container_width=True)
            if submitted_profile:
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