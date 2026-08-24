import streamlit as st
import datetime
import pandas as pd
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim
import os

# -------------------------------------------------------------
# 1. 페이지 환경 설정 (투명 로고 우선 적용)
# -------------------------------------------------------------
if os.path.exists("logo-removebg-preview.png"):
    logo_file = "logo-removebg-preview.png"
elif os.path.exists("logo.png"):
    logo_file = "logo.png"
else:
    logo_file = None

page_icon_img = logo_file if logo_file else "☀️"

st.set_page_config(
    page_title="HEATWAY - 전국 폭염 취약계층 안전 도우미",
    page_icon=page_icon_img,
    layout="wide"
)

# -------------------------------------------------------------
# 2. 전국 주소 -> 좌표 변환 (Geocoding) & 쉼터 자동 생성기
# -------------------------------------------------------------
@st.cache_data(show_spinner=False)
def search_location_coords(query_text):
    """전국 주소/지명을 위도, 경드로 실시간 변환"""
    try:
        geolocator = Nominatim(user_agent="heatway_service_app_2026")
        loc = geolocator.geocode(query_text + ", 대한민국" if "한국" not in query_text and "대한민국" not in query_text else query_text)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except Exception:
        pass
    return 35.1802, 128.1076, f"{query_text} (기본 위치)"

def generate_local_shelters(center_lat, center_lon, region_name):
    """해당 좌표 주변 쉼터 생성 및 KST 현재 시각 기준 이용 가능 여부 실시간 판별"""
    clean_name = region_name.split(",")[0].strip()
    
    # 한국 표준시(KST) 현재 시각 추출
    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    current_hour = kst_now.hour

    shelter_candidates = [
        {
            "name": f"{clean_name} 제1경로당 쉼터",
            "lat": center_lat + 0.0025,
            "lon": center_lon + 0.0020,
            "dist": "280m",
            "cap": 30,
            "ac": 2,
            "open_h": 9,
            "close_h": 18
        },
        {
            "name": f"{clean_name} 행정복지센터 안심쉼터",
            "lat": center_lat - 0.0030,
            "lon": center_lon - 0.0025,
            "dist": "520m",
            "cap": 60,
            "ac": 4,
            "open_h": 9,
            "close_h": 21  # 야간 연장 쉼터
        },
        {
            "name": f"{clean_name} 노인종합복지관",
            "lat": center_lat + 0.0040,
            "lon": center_lon - 0.0035,
            "dist": "750m",
            "cap": 100,
            "ac": 6,
            "open_h": 9,
            "close_h": 18
        }
    ]

    # 현재 시각 기준 이용 가능(운영 중) 여부 자동 판별 필터링
    for s in shelter_candidates:
        s["is_open"] = (s["open_h"] <= current_hour < s["close_h"])
        s["status_tag"] = "🟢 현재 이용가능 (운영중)" if s["is_open"] else "🔴 운영시간 종료"
        s["display_name"] = f"{s['name']} [{s['status_tag']}]"

    return shelter_candidates

# -------------------------------------------------------------
# 3. 전역 상태(Session State) 초기화 (누락되었던 세션 생성 로직)
# -------------------------------------------------------------
if "location_input" not in st.session_state:
    st.session_state.location_input = "경남 진주시"
if "current_lat" not in st.session_state:
    st.session_state.current_lat = 35.1802
if "current_lon" not in st.session_state:
    st.session_state.current_lon = 128.1076
if "user_type" not in st.session_state:
    st.session_state.user_type = "고령자(독거)"
if "out_time" not in st.session_state:
    st.session_state.out_time = datetime.time(14, 0)
if "duration" not in st.session_state:
    st.session_state.duration = 70
if "risk_score" not in st.session_state:
    st.session_state.risk_score = 86
if "risk_level" not in st.session_state:
    st.session_state.risk_level = "위험 (외출 자제)"
if "shelter_list" not in st.session_state:
    st.session_state.shelter_list = generate_local_shelters(35.1802, 128.1076, "경남 진주시")
if "selected_shelter" not in st.session_state:
    st.session_state.selected_shelter = st.session_state.shelter_list[0]
if "safety_status" not in st.session_state:
    st.session_state.safety_status = "외출 대기"
if "safety_log" not in st.session_state:
    st.session_state.safety_log = []
if "check_requested" not in st.session_state:
    st.session_state.check_requested = False

# -------------------------------------------------------------
# 4. 규칙 기반 위험도 알고리즘
# -------------------------------------------------------------
def calculate_heat_risk(user_type, out_time_hour, duration_min, temp=35, humidity=75):
    base_score = 20
    
    if 12 <= out_time_hour <= 16:
        time_weight = 35
    elif 10 <= out_time_hour <= 18:
        time_weight = 20
    elif 19 <= out_time_hour <= 21:
        time_weight = 5
    else:
        time_weight = -15
        
    weather_weight = 15 if (10 <= out_time_hour <= 18) else 5
    if humidity >= 70:
        weather_weight += 5

    duration_weight = int((duration_min / 30) * 5)
    
    type_weights = {"고령자(독거)": 15, "야외근로자": 18, "어린이": 12, "일반인": 5}
    user_weight = type_weights.get(user_type, 8)
    
    total_score = min(100, max(10, base_score + time_weight + weather_weight + duration_weight + user_weight))
    
    if total_score >= 80:
        level = "위험 (외출 자제)"
    elif total_score >= 60:
        level = "경고 (주의 필요)"
    elif total_score >= 40:
        level = "주의 (휴식 필수)"
    else:
        level = "보통 (안전)"
        
    return total_score, level

# -------------------------------------------------------------
# 5. 사이드바 (투명 로고 연동)
# -------------------------------------------------------------
with st.sidebar:
    if logo_file:
        st.image(logo_file, width=120)
    st.title("더위쉼표 (HEATWAY)")
    app_mode = st.radio("모드 선택", ["사용자: 외출 도우미", "보호자: 실시간 안부 대시보드"])

def get_kst_now_str():
    kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    return kst_now.strftime('%H:%M')

# -------------------------------------------------------------
# 6. 사용자 화면: 외출 도우미
# -------------------------------------------------------------
if app_mode == "사용자: 외출 도우미":
    head_c1, head_c2 = st.columns([1, 8])
    with head_c1:
        if logo_file:
            st.image(logo_file, width=75)
    with head_c2:
        st.title("더위쉼표 맞춤 외출 플래너")
        st.caption("폭염 취약계층을 위한 실시간 위치기반 외출 안전 가이드")
    
    # 보호자가 안부 요청을 보냈을 때 뜨는 실시간 팝업 안내창
    if st.session_state.check_requested:
        st.error("🚨 **[긴급 안부 요청]** 보호자가 대상자의 안전 상태를 확인하고 있습니다!")
        pop_col1, pop_col2 = st.columns([2, 1])
        with pop_col1:
            st.warning("폭염 위험 시간대입니다. 건강에 이상이 없으시다면 아래 버튼을 눌러주세요.")
        with pop_col2:
            if st.button("👍 네, 안전해요 (안부 확인)", type="primary", use_container_width=True):
                st.session_state.check_requested = False
                now_str = get_kst_now_str()
                st.session_state.safety_status = "안전 확인됨 (보호자 응답)"
                st.session_state.safety_log.append(f"[{now_str}] 대상자가 보호자의 안부 요청에 '안전함'으로 응답 완료")
                st.toast("보호자에게 안전 확인 응답이 전달되었습니다!")
                st.rerun()

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. 외출 정보 입력")
        
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            search_query = st.text_input("현재 위치 검색 (시·군·구·읍·면)", value=st.session_state.location_input)
        with col_s2:
            st.write("")
            st.write("")
            search_btn = st.button("🔍 검색", use_container_width=True)
            
        if search_btn or (search_query != st.session_state.location_input):
            with st.spinner("지역 탐색 중..."):
                lat, lon, found_addr = search_location_coords(search_query)
                st.session_state.location_input = search_query
                st.session_state.current_lat = lat
                st.session_state.current_lon = lon
                st.session_state.shelter_list = generate_local_shelters(lat, lon, search_query)
                st.session_state.selected_shelter = st.session_state.shelter_list[0]
                st.rerun()

        st.session_state.user_type = st.selectbox(
            "사용자 유형", 
            ["고령자(독거)", "야외근로자", "어린이", "일반인"],
            index=["고령자(독거)", "야외근로자", "어린이", "일반인"].index(st.session_state.user_type)
        )
        st.session_state.out_time = st.time_input("외출 예정 시간", st.session_state.out_time)
        st.session_state.duration = st.slider("예상 야외 활동 시간 (분)", min_value=10, max_value=180, value=st.session_state.duration, step=10)
        
        st.info("🌡️ **현재 기상청 예보:** 기온 35℃ | 습도 75% | 폭염영향예보 '경고' 발효 중")
        
    with col2:
        st.subheader("2. 폭염 위험도 분석 결과")
        score, level = calculate_heat_risk(st.session_state.user_type, st.session_state.out_time.hour, st.session_state.duration)
        st.session_state.risk_score = score
        st.session_state.risk_level = level
        
        st.metric(label="현재 폭염 위험도", value=f"{st.session_state.risk_score}점", delta=st.session_state.risk_level, delta_color="inverse")
        
        st.markdown(f"""
        **주요 원인 분석:**
        - **위치:** `{st.session_state.location_input}`
        - 예상 기온 **35℃** & 높은 습도로 인한 체감 부담 증가
        - 외출 시간대 (**{st.session_state.out_time.strftime('%H:%M')}**) 가중치 반영
        - 야외 활동 시간 **{st.session_state.duration}분** ({st.session_state.user_type} 기준 체력 소모)
        """)

    st.markdown("---")
    
    col_map, col_ai = st.columns([1, 1])
    
    shelter_dict = {s["name"]: s for s in st.session_state.shelter_list}
    
    with col_map:
        st.subheader(f"🗺️ [{st.session_state.location_input}] 주변 무더위쉼터")
        
        current_selected_name = st.session_state.selected_shelter["name"]
        default_idx = list(shelter_dict.keys()).index(current_selected_name) if current_selected_name in shelter_dict else 0
        
        chosen_name = st.selectbox(
            "경유/이용할 무더위쉼터 선택 (선택 시 지도가 해당 쉼터로 이동)", 
            list(shelter_dict.keys()),
            index=default_idx,
            key="shelter_dropdown_key"
        )
        
        st.session_state.selected_shelter = shelter_dict[chosen_name]
        target_shelter = st.session_state.selected_shelter
        
        status_info = target_shelter.get('status_tag', '')
        st.success(f"📍 **선택된 쉼터:** `{target_shelter['name']}` ({status_info})  \n(거리: `{target_shelter['dist']}` | 에어컨: `{target_shelter['ac']}대` 가동 중)")
            
        m = folium.Map(location=[target_shelter['lat'], target_shelter['lon']], zoom_start=15)
        
        folium.Marker(
            [st.session_state.current_lat, st.session_state.current_lon],
            popup=f"현재 위치: {st.session_state.location_input}",
            tooltip="현재 위치",
            icon=folium.Icon(color="green", icon="user")
        ).add_to(m)
        
        for s in st.session_state.shelter_list:
            if s["name"] == chosen_name:
                folium.Marker(
                    [s['lat'], s['lon']],
                    popup=f"★ 선택된 쉼터: {s['name']}\n({s.get('status_tag', '')}, 에어컨 {s['ac']}대)",
                    tooltip=f"★ {s['name']} (선택됨)",
                    icon=folium.Icon(color="red", icon="star")
                ).add_to(m)
            else:
                folium.Marker(
                    [s['lat'], s['lon']],
                    popup=f"{s['name']}\n({s.get('status_tag', '')}, 에어컨 {s['ac']}대)",
                    tooltip=s['name'],
                    icon=folium.Icon(color="blue", icon="home")
                ).add_to(m)
                
        st_folium(m, height=270, width=500, key=f"folium_map_{st.session_state.location_input}_{chosen_name}")

    with col_ai:
        st.subheader("📋 AI 폭염 안전 계획 생성")
        if st.button("🤖 맞춤 안전 계획 자동 생성", type="primary", use_container_width=True):
            ai_plan = f"""
### 🚨 [{st.session_state.location_input}] 맞춤 외출 가이드
1. **외출 시간:** {st.session_state.out_time.hour}시는 위험도 **{st.session_state.risk_score}점({st.session_state.risk_level})** 구간입니다.
2. **지정 대피소:** 이동 중 **[{target_shelter['name']}]** (거리 {target_shelter['dist']})에서 반드시 15분 이상 수분 섭취 및 냉방 휴식을 취하세요.
3. **취약계층 행동요령:** {st.session_state.user_type} 전용 수칙(양산 착용, 어지럼증 발생 시 즉시 착석).
"""
            st.markdown(ai_plan)

    st.markdown("---")
    st.subheader("🛡️ 외출 상태 실시간 전송")
    c1, c2, c3 = st.columns(3)
    now_str = get_kst_now_str()
    
    with c1:
        if st.button("🚶 외출 시작 알림"):
            st.session_state.safety_status = f"외출 중 ({st.session_state.out_time.strftime('%H:%M')} 출발)"
            st.session_state.safety_log.append(f"[{now_str}] '{st.session_state.location_input}'에서 외출 시작")
            st.success("보호자 대시보드에 [외출 시작]이 기록되었습니다.")
    with c2:
        if st.button("🏠 무더위쉼터 도착"):
            st.session_state.safety_status = f"쉼터 휴식 중 ({target_shelter['name']})"
            st.session_state.safety_log.append(f"[{now_str}] '{target_shelter['name']}' 도착 및 휴식 중")
            st.info("보호자에게 [쉼터 도착] 알림이 전달되었습니다.")
    with c3:
        if st.button("✅ 안전 귀가 완료"):
            st.session_state.safety_status = "귀가 완료 (안전)"
            st.session_state.safety_log.append(f"[{now_str}] '{st.session_state.location_input}' 자택으로 귀가 완료")
            st.success("보호자에게 [귀가 완료] 확인이 전달되었습니다.")

# -------------------------------------------------------------
# 7. 보호자 화면: 실시간 안부 대시보드
# -------------------------------------------------------------
else:
    head_c1, head_c2 = st.columns([1, 8])
    with head_c1:
        if logo_file:
            st.image(logo_file, width=75)
    with head_c2:
        st.title("보호자 실시간 안부 모니터링")
        st.caption("사용자 화면에서 변경된 정보가 실시간으로 동기화됩니다.")
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("대상자 / 위치", f"{st.session_state.user_type}", st.session_state.location_input)
    with col_stat2:
        st.metric("현재 안전 상태", st.session_state.safety_status)
    with col_stat3:
        st.metric("외출 위험도", f"{st.session_state.risk_score}점 ({st.session_state.risk_level})", delta_color="inverse")
        
    st.markdown("---")
    
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        st.subheader("🕒 실시간 안부 타임라인")
        st.write(f"📅 **외출 예정 시간:** {st.session_state.out_time.strftime('%H:%M')} (예상 활동: {st.session_state.duration}분)")
        
        if st.session_state.safety_log:
            for log in reversed(st.session_state.safety_log):
                st.info(log)
        else:
            st.write("아직 등록된 외출 기록이 없습니다. (외출 대기 중)")
            
        st.markdown("---")
        st.subheader("🚨 비상 상황 체크")
        c_emer1, c_emer2 = st.columns(2)
        with c_emer1:
            if st.button("📞 안부 확인 요청 발송"):
                st.session_state.check_requested = True
                now_str = get_kst_now_str()
                st.session_state.safety_log.append(f"[{now_str}] 보호자가 대상자에게 긴급 안부 확인을 요청함")
                st.warning(f"[{st.session_state.user_type}] 대상자에게 안부 확인 팝업 요청을 발송했습니다. (사용자 화면 상단에 알림 표출)")
                st.rerun()
        with c_emer2:
            if st.button("⚠️ 긴급 연락망 호출"):
                st.error(f"[{st.session_state.location_input}] 인근 복지관 및 비상연락처로 긴급 출동 요청을 전송했습니다.")

    with col_t2:
        st.subheader("📍 경유 예정 무더위쉼터")
        shelter = st.session_state.selected_shelter
        st.success(f"🏢 **{shelter['name']}**")
        st.markdown(f"""
        - **기준 위치:** `{st.session_state.location_input}`
        - **이동 거리:** 동선 기준 약 `{shelter['dist']}`
        - **운영 상태:** `{shelter.get('status_tag', '운영중')}`
        - **냉방 시설:** 에어컨 `{shelter['ac']}대` 가동 중
        - **보호자 안심 가이드:** 현재 폭염 위험도 **{st.session_state.risk_score}점** 상황입니다. 외출 후 30분 이내에 대상자가 `{shelter['name']}`에 도착했는지 확인하세요.
        """)
