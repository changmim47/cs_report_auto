import streamlit as st
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
from collections import Counter
from io import StringIO

# =============================
# 🔧 초기 설정 & 스타일
# =============================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

st.set_page_config(
    page_title="CS 일일보고 자동 요약 생성기 v4",
    page_icon="📊",
    layout="wide",
)

# 글로벌 CSS (카드/배지/색상)
st.markdown(
    """
    <style>
    .app-header {font-size: 28px; font-weight:700; color:#2b6cb0; margin-bottom:4px}
    .sub {color:#64748b; font-size:13px; margin-bottom:12px}
    .card {border:1px solid #e2e8f0; border-radius:14px; padding:18px; background:#ffffff; box-shadow:0 2px 6px rgba(17,24,39,0.03);}
    .badge {display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid #cbd5e1; font-size:11px; color:#334155; background:#f8fafc; margin-right:8px}
    .badge.green {border-color:#34d399; color:#065f46; background:#ecfdf5}
    .badge.red {border-color:#f87171; color:#7f1d1d; background:#fef2f2}
    .kicker {font-weight:700; color:#0f172a; margin-bottom:10px}
    .muted {color:#64748b; font-size:13px}
    .download-sticky {position: sticky; bottom: 10px; background: #ffffffaa; padding: 8px 12px; backdrop-filter: blur(6px); border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================
# 🧰 유틸 함수
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

# 카테고리 매핑
CATEGORY_MAP = {
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

def map_category(value):
    return CATEGORY_MAP.get(str(value).strip(), value)

# 강사명 리스트
TEACHER_NAMES = [
    "임지혜", "이윤주", "조태정", "성정혜", "경선식", "박노준",
    "박수연", "고종훈", "라영환", "최영재", "전한길",
    "박찬혁", "황철곤", "이상헌", "신용한", "전효진", "정인국", "양승우",
    "이상현", "조여은", "서호성", "장병열", "신명", "박상민", "고비환",
    "김광훈", "김형준", "오정화", "남정선", "백광훈", "허서유", "오제현",
    "이종하", "최희준", "김창훈", "이진오", "진승현", "송아름", "이재훈",
    "송아영", "김종환", "심승아", "곽동진", "정인국", "임재희"
]


def detect_teacher(text):
    for name in TEACHER_NAMES:
        if name in str(text):
            return name
    return None


def preprocess_text(texts):
    words = re.findall(r"[가-힣a-zA-Z]+", " ".join(texts))
    return [w for w in words if len(w) > 1]

# =============================
# 🧭 사이드바 (도움말/옵션)
# =============================
st.sidebar.header("도움말 ❔")
st.sidebar.markdown(
    """
    **사용 방법**
    1) CS 엑셀 파일(.xlsx)을 업로드합니다.
    2) 필수 컬럼(구분/내용/카테고리)을 자동으로 인식합니다.
    3) 카테고리별로 상위 키워드와 강사 언급을 반영해 5줄 이내 요약을 생성합니다.
    4) 하단에서 전체 요약을 `TXT`로 다운로드하세요.
    """
)

# 모델/온도 간단 옵션
with st.sidebar.expander("고급 옵션", expanded=False):
    model_name = st.selectbox("모델", ["gpt-4o-mini"], index=0)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)

# =============================
# 🏷️ 헤더 & 체크
# =============================
st.markdown('<div class="app-header">📊 CS 일일보고 자동 요약 생성기 (강사명 포함 자동 인식 v4)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">엑셀 업로드 → 카테고리별 요약 카드 → 통합 다운로드</div>', unsafe_allow_html=True)

if not api_key:
    st.error("❌ OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    st.stop()

client = OpenAI(api_key=api_key)

uploaded_file = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"])  # 📂

# =============================
# 🧪 본 처리
# =============================
report_text = ""

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"엑셀 로드 실패: {e}")
        st.stop()

    # 컬럼 매핑/리네임
    col_map = build_column_map(df.columns)
    df = df.rename(columns=col_map)

    required_cols = {"구분", "내용", "카테고리"}
    if not required_cols.issubset(df.columns):
        st.error(f"엑셀에 {required_cols} 컬럼이 포함되어야 합니다.\n실제 컬럼: {list(df.columns)}")
        st.stop()

    # 대표카테고리/강사명 감지
    df["대표카테고리"] = df["카테고리"].apply(map_category)
    df["강사명"] = df["내용"].apply(detect_teacher)

    q_df = df[df["구분"] == "Q"].dropna(subset=["내용", "대표카테고리"])
    if q_df.empty:
        st.warning("⚠️ 'Q' 구분의 데이터가 없습니다.")
        st.stop()

    grouped = q_df.groupby("대표카테고리")["내용"].apply(list).to_dict()
    # ✅ 특정 키워드 포함 행 카운트
    TARGET_CATEGORY = "모바일 기기 - 모바일 기기"
    KEYWORDS = ["중복", "iOS", "플레이어 ID", "충돌이슈", "초기화"]

    def contains_keyword(text):
        return any(keyword.lower() in str(text).lower() for keyword in KEYWORDS)

    keyword_df = df[
        df["구분"].isin(["Q", "A"]) &
        df["카테고리"].astype(str).str.contains(TARGET_CATEGORY) &
        df["내용"].apply(contains_keyword)
    ]

    keyword_count = len(keyword_df)

    # ✅ UI에 표시
    st.markdown(
        f"<div class='card'><strong>- iOS 디바이스ID 지속 변경 이슈로 기기삭제 요청 및 해결 요청 문의 - 약 {keyword_count}건 (모바일 기기 카테고리)</strong></div>",
        unsafe_allow_html=True,
    )
    # ✅ 키워드 필터링 결과 다운로드 기능 추가
    if keyword_count > 0:
        import io
        excel_buffer = io.BytesIO()
        keyword_df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)

        st.download_button(
            label="📥 키워드 추출 데이터 다운로드 (Excel)",
            data=excel_buffer,
            file_name="keyword_extracted_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.info(f"총 **{len(grouped)}개 대표 카테고리**에서 문의를 분석합니다.")

    progress = st.progress(0)
    cards_buf = []  # 카드 HTML 누적

    # 좌/우 2열 카드 레이아웃
    cols = st.columns(2, gap="large")

    for i, (category, questions) in enumerate(grouped.items(), start=1):
        words = preprocess_text(questions)
        common_words = [w for w, _ in Counter(words).most_common(10)]
        joined_text = "\n".join(questions[:30])

        # 강사명 언급
        teacher_mentions = [
            t for t in q_df[q_df["대표카테고리"] == category]["강사명"].dropna().unique() if t
        ]
        teacher_info_line = ", ".join(teacher_mentions) if teacher_mentions else "없음"

        # ✅ mention_line 정의
        mention_line = ""
        if teacher_mentions:
            mention_line = f"특정 강사 관련 문의 포함: {', '.join(teacher_mentions)} 선생님 관련 문의 포함."

        # 프롬프트
        prompt = f"""
        아래는 '{category}' 카테고리에 해당하는 회원 문의 내용입니다.
        총 {len(questions)}건의 문의가 있습니다.
        주요 키워드: {', '.join(common_words)}
        {mention_line}
아래 조건을 반드시 지켜 요약하세요.
        1. 각 줄은 반드시 어떤 문의인지 알 수 있도록 간략하게 정리해서 '~ 관련 문의 접수' 형태로 끝날 것.
        2. 강사명이 포함된 경우 반드시 명시할 것 (예: '유휘운 선생님 교재 관련 문의 접수').
        3. 불필요한 설명, 원인, 사유, 문장형 해설 금지.
        4. 최대 5줄까지만 작성.
        5. 같은 의미의 문의는 하나로 묶을 것.

        문의 내용:
        {joined_text}
        """

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            summary = response.choices[0].message.content.strip()
        except Exception as e:
            summary = f"(요약 실패: {e})"

        # 카드 렌더링
        col = cols[i % 2]
        with col:
            st.markdown(
                f"""
                <div class='card'>
                    <div class='kicker'>📂 [{category}]</div>
                    <div class='muted'>총 {len(questions)}건 • 주요 키워드: {', '.join(common_words) if common_words else '—'}</div>
                    <div style='margin:8px 0;'>
                        <span class='badge'>카테고리</span>
                        <span class='badge green'>요약 생성 완료</span>
                        <span class='badge'>강사: {teacher_info_line}</span>
                    </div>
                    <div style='white-space:pre-wrap; line-height:1.6;'>{summary}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        cards_buf.append(f"**[{category}]**\n{summary}\n")
        progress.progress(i / len(grouped))

    # 최종 보고 텍스트
    report_text = "## 🧾 주요 문의 요약 (강사 포함 자동 인식)\n\n" + "\n".join(cards_buf)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("<div class='download-sticky'>", unsafe_allow_html=True)
    st.download_button(
        label="📥 요약 결과 다운로드",
        data=report_text.encode("utf-8"),
        file_name="CS_일일보고_v4_강사포함.txt",
        mime="text/plain",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.warning("엑셀(.xlsx) 파일을 업로드하면 요약이 시작됩니다.")
