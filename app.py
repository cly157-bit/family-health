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

# 自訂 CSS 提升質感
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
    return client, genai.GenerativeModel("gemini-1.5-flash")

supabase, model = init_services()

# ------------------------------------------
# 3. 狀態管理與輔助函式
# ------------------------------------------
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "parsed_results" not in st.session_state:
    st.session_state.parsed_results = []

def image_to_base64(uploaded_file):
    img = Image.open(uploaded_file)
    img.thumbnail((500, 500)) # 雲端儲存空間優化
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

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
    except:
        st.error("連線資料庫失敗，請確認 Supabase 設定。")
        st.stop()
        
    st.subheader("👪 誰要開始記錄？")
    if members:
        cols = st.columns(2)
        for idx, m in enumerate(members):
            if cols[idx % 2].button(f"👤 {m['display_name']}", key=f"u_{m['id']}", use_container_width=True):
                st.session_state.current_user = m
                st.rerun()
    
    st.markdown("---")
    st.subheader("➕ 新增家庭成員")
    with st.form("add_user"):
        new_name = st.text_input("成員稱呼")
        target_cal = st.number_input("每日熱量預算", value=2000, step=100)
        if st.form_submit_button("新增並登入", use_container_width=True) and new_name.strip():
            new_u = supabase.table("profiles").insert({
                "display_name": new_name.strip(),
                "target_calories": target_cal,
                "family_id": "00000000-0000-0000-0000-000000000000"
            }).execute()
            if new_u.data:
                st.session_state.current_user = new_u.data[0]
                st.rerun()

# ------------------------------------------
# 5. 主系統介面
# ------------------------------------------
else:
    cur_user = st.session_state.current_user
    
    with st.sidebar:
        st.write(f"當前身分：**{cur_user['display_name']}**")
        if st.button("🔄 切換/登出角色", use_container_width=True):
            st.session_state.current_user = None
            st.rerun()
        st.markdown("---")
        menu = st.radio("功能導覽", ["📸 AI 智慧紀錄", "⚡ 熱量收支表", "📈 數據報表", "💬 家庭動態牆", "👤 個人設定"])

    # --- 分頁 A: AI 智慧紀錄 ---
    if menu == "📸 AI 智慧紀錄":
        st.title("📸 AI 智慧混合紀錄")
        st.caption("輸入整天做了什麼（文字或照片），AI 會自動拆分為多張卡片！")
        
        user_input = st.text_area("寫點什麼吧", placeholder="例：早餐吃漢堡配紅茶，中午跑步30分鐘...", height=100)
        uploaded_img = st.file_uploader("拍照/上傳 (選填)", type=["jpg", "png", "jpeg"])
        
        if st.button("✨ 送出 AI 智慧分析", use_container_width=True, type="primary"):
            if not user_input.strip() and not uploaded_img:
                st.warning("請輸入內容！")
            else:
                with st.spinner("AI 大腦拆分中..."):
                    try:
                        img_obj = Image.open(uploaded_img) if uploaded_img else None
                        prompt = """
                        分析內容並拆分為 JSON 列表。格式：
                        [{"type":"diet","food_items":["名稱"],"calories":數字,"protein":數字,"carbs":數字,"fat":數字,"health_tip":"建議"},
                         {"type":"exercise","exercise_type":"名稱","duration_minutes":數字,"calories_burned":數字,"tip":"勉勵"}]
                        必須是純 JSON，無 markdown。
                        """
                        inputs = [prompt, user_input]
                        if img_obj: inputs.append(img_obj)
                        
                        response = model.generate_content(inputs)
                        st.session_state.parsed_results = json.loads(response.text.strip().replace("```json","").replace("```",""))
                        st.session_state.raw_val = image_to_base64(uploaded_img) if uploaded_img else user_input
                    except:
                        st.error("AI 解析失敗，請描述更詳細一點。")

        # 多卡編輯面板
        if st.session_state.parsed_results:
            st.markdown("---")
            st.subheader("💡 智慧拆分結果 (可手動修改)")
            with st.form("confirm_logs"):
                confirmed_list = []
                for i, res in enumerate(st.session_state.parsed_results):
                    if res["type"] == "diet":
                        st.markdown(f"**🍎 飲食 #{i+1}**")
                        food = st.text_input("食物", value=", ".join(res.get("food_items",[])), key=f"f_{i}")
                        c1, c2 = st.columns(2)
                        cal = c1.number_input("卡路里", value=int(res.get("calories",0)), key=f"c_{i}")
                        tip = st.text_input("AI 建議", value=res.get("health_tip",""), key=f"t_{i}")
                        confirmed_list.append({"type":"diet", "data":{"food_items":[food], "calories":cal, "health_tip":tip, "protein":res.get("protein",0), "carbs":res.get("carbs",0), "fat":res.get("fat",0)}})
                    else:
                        st.markdown(f"**🏃 運動 #{i+1}**")
                        ex = st.text_input("項目", value=res.get("exercise_type",""), key=f"e_{i}")
                        c1, c2 = st.columns(2)
                        burn = c1.number_input("消耗熱量", value=int(res.get("calories_burned",0)), key=f"b_{i}")
                        confirmed_list.append({"type":"exercise", "data":{"exercise_type":ex, "calories_burned":burn, "tip":res.get("tip",""), "duration_minutes":res.get("duration_minutes",0)}})
                
                if st.form_submit_button("💾 確定！一口氣全部記下來", use_container_width=True):
                    for item in confirmed_list:
                        supabase.table("health_logs").insert({
                            "user_id": cur_user["id"], "type": item["type"],
                            "raw_input": st.session_state.raw_val, "parsed_data": item["data"],
                            "cheers": {}, "comments": []
                        }).execute()
                    st.success("🎉 已同步至雲端！")
                    st.session_state.parsed_results = []
                    st.rerun()

    # --- 分頁 B: 熱量收支表 ---
    elif menu == "⚡ 熱量收支與電池":
        st.title("⚡ 每日熱量看板")
        today = datetime.now().strftime("%Y-%m-%d")
        logs = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).gte("logged_at", today).execute().data
        
        eat, burn = 0, 0
        for l in (logs or []):
            d = l["parsed_data"]
            if l["type"] == "diet": eat += d.get("calories",0)
            else: burn += d.get("calories_burned",0)
            
        net = eat - burn
        target = cur_user.get("target_calories", 2000)
        pct = min(100, max(5, int((net/target)*100))) if target > 0 else 5
        color = "linear-gradient(90deg, #ef4444, #b91c1c)" if pct > 100 else "linear-gradient(90deg, #10b981, #059669)"
        
        st.markdown(f"""
        <div class="battery-container">
            <div class="battery-fluid" style="width:{pct}%; background:{color};"></div>
            <div class="battery-text">{net} / {target} kcal</div>
            <div style="position:absolute; right:-8px; width:6px; height:30px; background:#334155; border-radius:0 4px 4px 0;"></div>
        </div>
        """, unsafe_allow_html=True)
        st.metric("今日攝取", f"{eat} kcal", f"-{burn} 消耗")

    # --- 分頁 C: 數據報表 ---
    elif menu == "📈 數據報表":
        st.title("📈 數據統計報表")
        period = st.segmented_control("統計週期", ["日", "週", "月"], default="日")
        # 此處實作與原型一致之表格運算邏輯...
        st.info("數據分析引擎載入中，將呈現您的歷史盈餘趨勢。")
        all_logs = supabase.table("health_logs").select("*").eq("user_id", cur_user["id"]).execute().data
        if all_logs:
            df = pd.DataFrame([{"日期": l["logged_at"][:10], "類型": l["type"], "熱量": l["parsed_data"].get("calories",0) if l["type"]=="diet" else -l["parsed_data"].get("calories_burned",0)} for l in all_logs])
            st.dataframe(df.groupby("日期")["熱量"].sum(), use_container_width=True)

    # --- 分頁 D: 家庭動態牆 ---
    elif menu == "💬 家庭動態牆":
        st.title("💬 家族動態留言牆")
        logs = supabase.table("health_logs").select("*").order("logged_at", desc=True).limit(20).execute().data
        profiles = {p["id"]: p["display_name"] for p in supabase.table("profiles").select("id, display_name").execute().data}
        
        for log in (logs or []):
            name = profiles.get(log["user_id"], "未知")
            is_diet = log["type"] == "diet"
            with st.container():
                st.markdown(f"""<div class="health-card {'exercise-card' if not is_diet else ''}">
                    <strong>👤 {name} ({'🍎 飲食' if is_diet else '🏃 運動'})</strong>
                    <div style="font-size:20px; font-weight:900; color:#f43f5e; margin:10px 0;">
                        {log['parsed_data'].get('calories', log['parsed_data'].get('calories_burned', 0))} kcal
                    </div>
                """, unsafe_allow_html=True)
                
                # 顯示留言板
                comments = log.get("comments", [])
                if comments:
                    for c in comments:
                        st.markdown(f"""<div class="comment-box">
                            <span><strong>{c['user']}:</strong> {c['text']}</span>
                            <span style="color:gray; font-size:10px;">{c['time']}</span>
                        </div>""", unsafe_allow_html=True)
                
                # 回覆功能
                with st.popover("💬 寫留言/加油"):
                    msg = st.text_input("關心家人...", key=f"in_{log['id']}")
                    if st.button("傳送 🚀", key=f"btn_{log['id']}") and msg.strip():
                        new_comments = comments + [{"user":cur_user["display_name"], "text":msg, "time":datetime.now().strftime("%H:%M")}]
                        supabase.table("health_logs").update({"comments": new_comments}).eq("id", log["id"]).execute()
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    # --- 分頁 E: 個人設定 ---
    elif menu == "👤 個人設定":
        st.title("👤 個人設定中心")
        with st.form("update_p"):
            name = st.text_input("修改名稱", value=cur_user["display_name"])
            cal = st.number_input("修改目標熱量", value=int(cur_user["target_calories"]))
            if st.form_submit_button("儲存修改"):
                res = supabase.table("profiles").update({"display_name":name, "target_calories":cal}).eq("id", cur_user["id"]).execute()
                if res.data:
                    st.session_state.current_user = res.data[0]
                    st.success("更新成功！")
                    st.rerun()