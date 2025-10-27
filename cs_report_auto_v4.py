import streamlit as st
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
from collections import Counter
import io
import altair as alt

# =============================
# 🔧 초기 설정 & 스타일
# =============================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

st.set_page_config(
    page_title="CS 일일보고 자동 요약 생성기",
    page_icon="📊",
    layout="wide",
)

# 글로벌 CSS
st.markdown("""
<style>
.app-header {font-size: 28px; font-weight:700; color:#2b6cb0; margin-bottom:4px}
.sub {color:#64748b; font-size:13px; margin-bottom:12px}
.card {border:1px solid #e2e8f0; border-radius:14px; padding:18px; background:#ffffff; box-shadow:0 2px 6px rgba(17,24,39,0.03);}
.kicker {font-weight:700; color:#0f172a; margin-bottom:10px}
.muted {color:#64748b; font-size:13px}
</style>
""", unsafe_allow_html=True)


# =============================
# 🧰 유틸 함수 (원본 그대로)
# =============================
def normalize_col(name: str) -> str:
    if name is None:
        return ""
    s = str(name)
    s = re.sub(r"\s+", "", s)
    s = s.replace("\u00A0", "")
    return s

def build_column_map(cols):
    REQUIRED = {"구분", "내용", "카테고리"}
    norm_to_actual = {normalize_col(c): c for c in cols}
    mapping = {}
    for need in REQUIRED:
        key = normalize_col(need)
        if key in norm_to_actual:
            mapping[norm_to_actual[key]] = need
    return mapping


CATEGORY_MAP = {  # ✅ 그대로
    "강좌/상품 신청, 배송 - 강좌신청": "넥스트패스/강좌/교재 신청, 배송",
    "강좌/상품 신청, 배송 - 상품신청": "넥스트패스/강좌/교재 신청, 배송",
    "강좌/상품 신청, 배송 - 반송": "넥스트패스/강좌/교재 신청, 배송",
    "강좌/상품 신청, 배송 - 배송": "넥스트패스/강좌/교재 신청, 배송",
    "강좌/상품 신청, 배송 - e-교재신청": "넥스트패스/강좌/교재 신청, 배송",
    "결제, 취소, 환불 - 결제": "결제/취소/환불",
    "결제, 취소, 환불 - 취소/환불": "결제/취소/환불",
    "동영상 수강-PC - 동영상 오류": "동영상, 모바일 기기 관련",
    "동영상 수강-PC - PC 기기": "동영상, 모바일 기기 관련",
    "모바일 기기 - 모바일 기기": "동영상, 모바일 기기 관련",
    "사이트 이용 - 부정사용": "홈페이지/이벤트 관련",
    "사이트 이용 - 사이트 오류": "홈페이지/이벤트 관련",
    "사이트 이용 - 수강기간": "홈페이지/이벤트 관련",
    "사이트 이용 - 업로드": "홈페이지/이벤트 관련",
    "사이트 이용 - 이벤트": "홈페이지/이벤트 관련",
    "사이트 이용 - 학력예측 풀서비스": "홈페이지/이벤트 관련",
    "사이트 이용 - 패스 환급": "홈페이지/이벤트 관련",
    "사이트 이용 - 패스 연장": "홈페이지/이벤트 관련",
    "회원정보 - 일반회원": "홈페이지/이벤트 관련",
    "공무원 수험정보 - 공무원 수험정보": "홈페이지/이벤트 관련",
    "기타 문의 - 건의사항": "홈페이지/이벤트 관련",
    "기타 문의 - 넥스트선생님": "홈페이지/이벤트 관련",
    "기타 문의 - 넥스트스터디 학원": "홈페이지/이벤트 관련",
    "기타 문의 - 기타": "홈페이지/이벤트 관련",
}
def map_category(v): return CATEGORY_MAP.get(str(v).strip(), v)

# ✅ 강사 리스트 그대로
TEACHER_NAMES = [    "임지혜", "이윤주", "조태정", "성정혜", "경선식", "박노준",
    "박수연", "고종훈", "라영환", "최영재", "전한길",
    "박찬혁", "황철곤", "이상헌", "신용한", "전효진", "정인국", "양승우",
    "이상현", "조여은", "서호성", "장병열", "신명", "박상민", "고비환",
    "김광훈", "김형준", "오정화", "남정선", "백광훈", "허서유", "오제현",
    "이종하", "최희준", "김창훈", "이진오", "진승현", "송아름", "이재훈",
    "송아영", "김종환", "심승아", "곽동진", "정인국", "임재희"
]
def detect_teacher(text):
    t = str(text)
    for n in TEACHER_NAMES:
        if n in t:
            return n
    return None

def preprocess_text(texts):
    safe = [str(t) for t in texts if pd.notna(t)]
    words = re.findall(r"[가-힣A-Za-z]+", " ".join(safe))
    return [w for w in words if len(w) > 1]


# ✅ 세션 상태
for key, default in {
    "analyzed": False,
    "keyword_buffer": None,
    "keyword_count": 0,
    "cards_payload": None,
    "report_text": None
}.items():
    st.session_state.setdefault(key, default)


st.markdown('<div class="app-header">📊 CS 일일보고 자동 요약 생성기</div>', unsafe_allow_html=True)

client = OpenAI(api_key=api_key)

# ✅ 사이드바 UI 안내 복구
st.sidebar.header("도움말 ❔")
st.sidebar.markdown(
    """
    일일업무 보고 중 카테고리 별 
    접수 내용을 요약정리하는 기능입니다.

    ✅ FAQ 관리자 송수신관리 엑셀 다운로드

    ✅ 엑셀 저장 방식을 .xslx 로 변경 
    
    ✅ 파일 업로드

    """
)

# ============================================================
# ✅ 탭 UI 구성 (요약 / 건수 통계)
# ============================================================
tab1, tab2 = st.tabs(["🔍 요약 생성", "📊 문의 건수 통계"])

# ✅ TAB 1 : 기존 기능 유지
with tab1:
    uploaded_file = st.file_uploader("📂 엑셀 업로드 (.xlsx)")
    run = st.button("🔍 요약 생성하기")

    # 🔁 기존 요약 생성 로직 그대로 유지
    if run and uploaded_file:
        st.session_state["analyzed"] = False
        status_box = st.empty()
        status_box.info("🔄 문의를 분석 중입니다...")

        df = pd.read_excel(uploaded_file)
        df = df.rename(columns=build_column_map(df.columns))
        df["대표카테고리"] = df["카테고리"].apply(map_category)
        df["강사명"] = df["내용"].apply(detect_teacher)

        q_df = df[df["구분"] == "Q"]
        grouped = q_df.groupby("대표카테고리")["내용"].apply(list).to_dict()

        KEYWORDS = ["중복", "iOS", "플레이어 ID", "충돌이슈", "초기화"]
        keyword_df = df[
            (df["대표카테고리"] == "동영상, 모바일 기기 관련") & 
            (df["내용"].str.contains("|".join(KEYWORDS), case=False, na=False))
        ]

        st.session_state["keyword_count"] = len(keyword_df)
        buf = io.BytesIO()
        keyword_df.to_excel(buf, index=False)
        buf.seek(0)
        st.session_state["keyword_buffer"] = buf

        cards_payload = []
        all_lines = []
        progress = st.progress(0)
        cols = st.columns(2)

        for i, (cat, qs) in enumerate(grouped.items(), start=1):
            common = [w for w, _ in Counter(preprocess_text(qs)).most_common(10)]
            teachers = q_df[q_df["대표카테고리"] == cat]["강사명"].dropna().unique()
            mention = (
                f"특정 강사 관련 문의 포함: {', '.join(teachers)} 선생님 관련 문의 포함."
                if len(teachers) else ""
            )

            joined = "\n".join([str(x) for x in qs[:30]])

            prompt = f"""
            아래는 '{cat}' 카테고리에 해당하는 회원 문의 내용입니다.
            총 {len(qs)}건의 문의가 있습니다.
            주요 키워드: {', '.join(common)}
            {mention}
            아래 조건을 반드시 지켜 요약하세요.
            1. 각 줄은 반드시 어떤 문의인지 알 수 있도록 간략하게 정리해서 '~ 관련 문의 접수' 형태로 끝날 것.
            2. 강사명이 포함된 경우 반드시 명시할 것 (예: '유휘운 선생님 교재 관련 문의 접수').
            3. 불필요한 설명, 원인, 사유, 문장형 해설 금지.
            4. 최대 5줄까지만 작성.
            5. 같은 의미의 문의는 하나로 묶을 것.

            문의 내용:
            {joined}
            """

            try:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                summary = resp.choices[0].message.content.strip()
            except:
                summary = "(요약 실패)"

            cards_payload.append({"cat": cat, "count": len(qs), "summary": summary})
            all_lines.append(f"**[{cat}]**\n{summary}\n")
            progress.progress(i / len(grouped))

        status_box.empty()

        st.session_state["cards_payload"] = cards_payload
        st.session_state["report_text"] = "\n".join(all_lines)
        st.session_state["analyzed"] = True

    # ✅ 요약 결과 출력
    if st.session_state["analyzed"]:
        st.success("✅ 분석 완료!")

        st.markdown(
            f"<div class='card'><strong>- iOS 기기ID 관련 기기삭제/해결 요청 문의 약 {st.session_state['keyword_count']}건</strong></div>",
            unsafe_allow_html=True,
        )

        st.download_button(
            "📥 키워드 추출 데이터 다운로드",
            st.session_state["keyword_buffer"],
            "keyword_extracted_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        cols = st.columns(2)
        for i, item in enumerate(st.session_state["cards_payload"], start=1):
            with cols[i % 2]:
                st.markdown(f"""
                    <div class='card'>
                        <div class='kicker'>📂 [{item['cat']}]</div>
                        <div class='muted'>총 {item['count']}건</div>
                        <div style='white-space:pre-wrap;'>{item['summary']}</div>
                    </div>
                """, unsafe_allow_html=True)

        st.download_button(
            "📥 전체 요약 다운로드",
            st.session_state["report_text"].encode("utf-8"),
            "CS_일일보고_v4_강사포함.txt",
            "text/plain",
        )


CATEGORY_MAP_MAIN = {
    "강좌/상품 신청, 배송": "넥스트패스/강좌/교재 신청, 배송",
    "결제, 취소, 환불": "결제/취소/환불",
    "동영상 수강-PC": "동영상, 모바일 기기 관련",
    "모바일 기기": "동영상, 모바일 기기 관련",
    "사이트 이용": "홈페이지/이벤트 관련",
    "회원정보": "홈페이지/이벤트 관련",
    "공무원 수험정보": "홈페이지/이벤트 관련",
    "기타 문의": "홈페이지/이벤트 관련",
}

def map_main_category(v):
    v = str(v).strip()
    return CATEGORY_MAP_MAIN.get(v, v)  # 매핑 없으면 원본 유지

with tab2:
    st.header("📊 대분류 기반 문의 건수 통계")

    uploaded_file_2 = st.file_uploader("📂 통계용 엑셀 업로드 (.xlsx)", key="stats_file")

    if uploaded_file_2:
        df2 = pd.read_excel(uploaded_file_2)
        df2 = df2.rename(columns=lambda x: str(x).strip())

        if "대분류" not in df2.columns or "문의량" not in df2.columns:
            st.error("❌ 필수 컬럼 누락: '대분류', '문의량' 필요")
            st.dataframe(df2.head())
            st.stop()

        df2["대표카테고리"] = df2["대분류"].apply(map_main_category)

        count_df = df2.groupby("대표카테고리")["문의량"].sum().reset_index()
        count_df = count_df.sort_values(by="문의량", ascending=False)

        st.subheader("📌 통계 결과")
        for _, row in count_df.iterrows():
            st.write(f"[{row['대표카테고리']}] : {int(row['문의량'])}건")

        st.divider()
        st.dataframe(count_df, use_container_width=True)

        chart = alt.Chart(count_df).mark_bar().encode(
            x=alt.X("대표카테고리:N", sort="-y", title="카테고리"),
            y=alt.Y("문의량:Q", title="문의수"),
            tooltip=["대표카테고리", "문의량"]
        ).properties(height=400)

        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("📂 통계용 엑셀 파일을 업로드해주세요.")
