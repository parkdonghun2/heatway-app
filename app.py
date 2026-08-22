import streamlit as st
import datetime
import pandas as pd
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim

# -------------------------------------------------------------
# 1. 페이지 환경 설정
# -------------------------------------------------------------
st.set_page_config(
    page_title="HEATWAY - 전국 폭염 취약계층 안전 도우미",
    page_icon="☀️",
    layout="wide"
)

# -------------------------------------------------------------
# 2. 전국 주소 $\rightarrow$ 좌표 변환 (Geocoding) & 쉼터 자동 생성기
# -------------------------------------------------------------
@st.cache_data(show_spinner=False)
def search_location_coords(query_text):
    """전국 주소/지명을 위도, 경도로 실시간 변환"""
    try:
        geolocator = Nominatim(user_agent="heatway_service_app_2026")
        # 한국 지역 우선 검색
        loc = geolocator.geocode(query_text + ", 대한민국" if "한국" not in query_text and "대한민국" not in query_text else query_text)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except Exception:
        pass
    # 검색 실패 시 기본 좌표 (경남 진주 기준 폴백)
    return 35.1802, 128.1076, f"{query_text} (기본 위치)"

def generate_local_shelters(center_lat, center_lon, region_name):
    """해당 좌표 주변으로 쉼터 3곳을 자동 생성"""
    clean_name = region_name.split(",")[0].strip()
    return [
        {
            "name": f"{clean_name} 제1경로당 쉼터",
            "lat": center_lat + 0.0020,
            "lon": center_lon + 0.0015,
            "dist": "280m",
            "cap": 30,
            "ac": 2
        },
        {
            "name": f"{clean_name} 행정복지센터 안심쉼터",
            "lat": center_lat - 0.0025,
            "lon": center_lon - 0.0020,
            "dist": "520m",
            "cap": 60,
            "ac": 4
        },
        {
            "name": f"{clean_name} 노인종합복지관",
            "lat": center_lat + 0.0035,
            "lon": center_lon - 0.0030,
            "dist": "750m",
            "cap": 100,
            "ac": 6
        }
    ]

# -------------------------------------------------------------
# 3. 전역 상태(Session State) 초기화
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
    st.session_state.risk_score = 82
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

# -------------------------------------------------------------
# 4. 규칙 기반 위험도 알고리즘 (Rule-based Risk Engine)
# -------------------------------------------------------------
def calculate_heat_risk(user_type, out_time_hour, duration_min, temp=35, humidity=75):
    base_score = 50
    if temp >= 35:
        base_score += 25
    elif temp >= 33:
        base_score += 15
    if humidity >= 70:
        base_score += 10
        
    time_weight = 15 if 13 <= out_time_hour <= 16 else (5 if 11 <= out_time_hour <= 18 else -10)
    duration_weight = int((duration_min / 30) * 8)
    
    type_weights = {"고령자(독거)": 18, "야외근로자": 20, "어린이": 15, "일반인": 5}
    user_weight = type_weights.get(user_type, 10)
    
    total_score = min(100, max(10, base_score + time_weight + duration_weight + user_weight))
    
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
# 5. 사이드바 모드 전환
# -------------------------------------------------------------
st.sidebar.title("☀️ HEATWAY")
app_mode = st.sidebar.radio("모드 선택", ["사용자: 외출 도우미", "보호자: 실시간 안부 대시보드"])

# -------------------------------------------------------------
# 6. 사용자 화면: 외출 도우미
# -------------------------------------------------------------
if app_mode == "사용자: 외출 도우미":
    st.title("🚶‍♂️ HEATWAY 맞춤 외출 안전 플래너 (전국 지원)")
    st.write("전국 모든 시·군·구 어디서나 위치를 검색하면 주변 쉼터와 안전 계획을 안내합니다.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. 외출 정보 입력")
        
        # 1) 전국 검색창 + 검색 버튼
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            search_query = st.text_input("현재 위치 검색 (시·군·구·읍·면)", value=st.session_state.location_input)
        with col_s2:
            st.write("") # 간격 맞춤
            st.write("")
            search_btn = st.button("🔍 위치 검색", use_container_width=True)
            
        if search_btn or (search_query != st.session_state.location_input):
            with st.spinner("해당 지역의 좌표와 주변 쉼터 정보를 탐색 중입니다..."):
                lat, lon, found_addr = search_location_coords(search_query)
                st.session_state.location_input = search_query
                st.session_state.current_lat = lat
                st.session_state.current_lon = lon
                st.session_state.shelter_list = generate_local_shelters(lat, lon, search_query)
                st.session_state.selected_shelter = st.session_state.shelter_list[0]
                st.toast(f"📍 위치 갱신 완료: {search_query}")

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
        - **위치:** `{st.session_state.location_input}` (위경도: {st.session_state.current_lat:.4f}, {st.session_state.current_lon:.4f})
        - 예상 기온 **35℃** & 높은 습도로 인한 체감 부담 증가
        - 위험 피크 시간대 (**{st.session_state.out_time.strftime('%H:%M')}**) 외출
        - 야외 활동 시간 **{st.session_state.duration}분** ({st.session_state.user_type} 기준 체력 소모 주의)
        """)

    st.markdown("---")
    
    col_map, col_ai = st.columns([1, 1])
    
    shelter_dict = {s["name"]: s for s in st.session_state.shelter_list}
    
    with col_map:
        st.subheader(f"🗺️ [{st.session_state.location_input}] 주변 무더위쉼터")
        
        chosen_name = st.selectbox(
            "경유/이용할 무더위쉼터 선택", 
            list(shelter_dict.keys()),
            key=f"shelter_select_{st.session_state.location_input}"
        )
        st.session_state.selected_shelter = shelter_dict[chosen_name]
        
        st.markdown(f"**선택된 쉼터:** `{st.session_state.selected_shelter['name']}` (거리: `{st.session_state.selected_shelter['dist']}` / 에어컨: `{st.session_state.selected_shelter['ac']}`대)")
            
        # 지도 생성
        m = folium.Map(location=[st.session_state.current_lat, st.session_state.current_lon], zoom_start=14)
        for s in st.session_state.shelter_list:
            is_selected = (s["name"] == chosen_name)
            folium.Marker(
                [s['lat'], s['lon']],
                popup=f"{s['name']}\n(에어컨 {s['ac']}대)",
                tooltip=s['name'],
                icon=folium.Icon(color="red" if is_selected else "blue", icon="home")
            ).add_to(m)
        st_folium(m, height=250, width=500, key=f"map_{st.session_state.location_input}_{chosen_name}")

    with col_ai:
        st.subheader("📋 AI 폭염 안전 계획 생성")
        if st.button("🤖 맞춤 안전 계획 자동 생성", type="primary", use_container_width=True):
            ai_plan = f"""
### 🚨 [{st.session_state.location_input}] 맞춤 외출 가이드
1. **외출 시간:** {st.session_state.out_time.hour}시는 위험도 **{st.session_state.risk_score}점({st.session_state.risk_level})** 구간입니다.
2. **지정 대피소:** 이동 중 **[{st.session_state.selected_shelter['name']}]** (거리 {st.session_state.selected_shelter['dist']})에서 반드시 15분 이상 수분 섭취 및 냉방 휴식을 취하세요.
3. **취약계층 행동요령:** {st.session_state.user_type} 전용 수칙(양산 착용, 어지럼증 발생 시 즉시 착석).
"""
            st.markdown(ai_plan)

    st.markdown("---")
    st.subheader("🛡️ 외출 상태 실시간 전송")
    c1, c2, c3 = st.columns(3)
    now_str = datetime.datetime.now().strftime('%H:%M')
    
    with c1:
        if st.button("🚶 외출 시작 알림"):
            st.session_state.safety_status = f"외출 중 ({st.session_state.out_time.strftime('%H:%M')} 출발)"
            st.session_state.safety_log.append(f"[{now_str}] '{st.session_state.location_input}'에서 외출 시작")
            st.success("보호자 대시보드에 [외출 시작]이 기록되었습니다.")
    with c2:
        if st.button("🏠 무더위쉼터 도착"):
            st.session_state.safety_status = f"쉼터 휴식 중 ({st.session_state.selected_shelter['name']})"
            st.session_state.safety_log.append(f"[{now_str}] '{st.session_state.selected_shelter['name']}' 도착 및 휴식 중")
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
    st.title("🛡️ 보호자 실시간 안부 모니터링")
    st.caption("사용자 화면에서 변경된 전국 모든 주소, 위험도, 경유 쉼터가 실시간으로 동기화됩니다.")
    
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
                st.warning(f"[{st.session_state.user_type}] 대상자에게 안부 확인 요청을 발송했습니다.")
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
        - **냉방 시설:** 에어컨 `{shelter['ac']}대` 가동 중
        - **보호자 안심 가이드:** 현재 폭염 위험도 **{st.session_state.risk_score}점** 상황입니다. 외출 후 30분 이내에 대상자가 `{shelter['name']}`에 도착했는지 확인하세요.
        """)
