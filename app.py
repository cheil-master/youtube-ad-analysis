import streamlit as st
import google.generativeai as genai
import yt_dlp
import os
import time
import cv2
import numpy as np
import tempfile

# 페이지 설정
st.set_page_config(page_title="유튜브 광고 소재 분석기", layout="wide")

# [추가] Secrets에서 쿠키를 읽어 임시 파일로 만드는 함수
def create_temp_cookie_file():
    """
    Streamlit Secrets에 저장된 YOUTUBE_COOKIES 텍스트를 
    yt-dlp가 인식할 수 있는 .txt 파일로 변환합니다.
    """
    if "YOUTUBE_COOKIES" in st.secrets:
        try:
            tmp_cookie = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8')
            tmp_cookie.write(st.secrets["YOUTUBE_COOKIES"])
            tmp_cookie.close()
            return tmp_cookie.name
        except Exception as e:
            st.error(f"쿠키 파일 생성 중 오류: {e}")
    return None

# 사이드바: API 키 입력
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    st.markdown("[Google AI Studio에서 키 발급받기](https://aistudio.google.com/app/apikey)")
    st.info("💡 403 에러 방지를 위해 Streamlit Secrets에 YOUTUBE_COOKIES를 설정해주세요.")

# 메인 화면
st.title("📹 유튜브 광고 소재 분석 & 메일 양식 생성기")
st.markdown("유튜브 링크를 넣으면 **광고 소재 분석 리포트**와 **스토리보드**를 생성합니다.")

# 입력 폼
with st.form("analysis_form"):
    video_url = st.text_input("유튜브 링크 (URL)", placeholder="https://www.youtube.com/watch?v=...")
    
    st.write("📢 **공개 채널 선택 (중복 가능)**")
    col1, col2, col3 = st.columns(3)
    c1 = col1.checkbox("TVC")
    c2 = col2.checkbox("브랜드 유튜브 채널")
    c3 = col3.checkbox("옥외광고 (극장광고 외)")
    
    submit = st.form_submit_button("분석 시작하기")

# 분석 로직
if submit:
    if not api_key:
        st.error("왼쪽 사이드바에 Google API Key를 먼저 입력해주세요.")
    elif not video_url:
        st.error("유튜브 링크를 입력해주세요.")
    else:
        selected_channels = []
        if c1: selected_channels.append("TVC")
        if c2: selected_channels.append("브랜드 유튜브 채널")
        if c3: selected_channels.append("옥외광고")
        channel_str = ", ".join(selected_channels) if selected_channels else "선택 없음"

        status_text = st.empty()
        progress_bar = st.progress(0)

        # 경로 변수 초기화
        video_path = None
        cookie_path = None

        try:
            # 1. 준비 작업 (쿠키 및 영상 경로)
            cookie_path = create_temp_cookie_file()
            
            # 고유한 임시 파일명을 사용하여 충돌 방지
            tmp_video_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            video_path = tmp_video_file.name
            tmp_video_file.close()

            # 2. 영상 다운로드 (yt-dlp 설정 최적화)
            status_text.info("📥 영상을 다운로드 중입니다...")
            progress_bar.progress(20)
            
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'outtmpl': video_path,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                },
            }

            # 쿠키가 설정되어 있다면 적용 (403 에러 해결 핵심)
            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            # 3. Gemini 설정 및 업로드
            genai.configure(api_key=api_key)
            status_text.info("📤 AI에게 영상을 전송하고 분석 중입니다...")
            progress_bar.progress(50)

            video_file = genai.upload_file(path=video_path)
            
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED":
                st.error("영상 처리에 실패했습니다.")
                st.stop()

            # 4. AI 분석 요청
            model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
            
            prompt = f"""
            당신은 전문적인 '광고 소재 관리자'입니다. 
            영상을 분석하여 아래 메일 양식을 완벽하게 작성해주세요.

            [입력 정보]
            - 공개채널 선택값: {channel_str}
            - 원본 링크: {video_url}

            [작성 지침]
            1. 타이틀: 유튜브 원본 제목
            2. 공개일: YYYY.MM.DD(요일) 형식
            3. 영상길이: 초 단위 (예: 15s)
            4. 자막: 영상 내 모든 텍스트. 특히 하단 법적 고지/유의사항은 앞에 *를 붙여서 줄바꿈하여 기재.
            5. 음성: 들리는 대로 스크립트 작성
            6. 중요: 스토리보드는 여기서 텍스트로 작성하지 말고, "하단 이미지 참조"라고만 적으세요.

            [출력 양식]
            □ 타이틀 : 
            □ 공개일 : 
            □ 공개채널 : 
            □ 영상길이 : 
            □ 링크 : 
            □ 스토리보드 : (하단 이미지 참조)
            
            □ 자막 : 

            □ 음성 : 
            """
            
            response = model.generate_content([video_file, prompt])
            analysis_result = response.text
            progress_bar.progress(80)

            # 5. 스토리보드 이미지 생성
            status_text.info("🖼️ 스토리보드(4x4) 이미지를 생성 중입니다...")
            
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            frame_indices = np.linspace(0, max(0, total_frames-1), 16, dtype=int)
            frames = []
            
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.resize(frame, (320, 180)) 
                    frames.append(frame)
            cap.release()

            if len(frames) == 16:
                row1 = np.hstack(frames[0:4])
                row2 = np.hstack(frames[4:8])
                row3 = np.hstack(frames[8:12])
                row4 = np.hstack(frames[12:16])
                grid_image = np.vstack([row1, row2, row3, row4])
            else:
                grid_image = None

            progress_bar.progress(100)
            status_text.success("분석 완료!")

            # 6. 결과 출력
            col_res1, col_res2 = st.columns([1, 1])

            with col_res1:
                st.subheader("📝 메일 본문 (복사용)")
                st.text_area("내용", value=analysis_result, height=600)
            
            with col_res2:
                st.subheader("🎬 스토리보드")
                if grid_image is not None:
                    st.image(grid_image, caption="4x4 Storyboard")
                else:
                    st.warning("영상이 너무 짧아 스토리보드를 만들 수 없습니다.")

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
        
        finally:
            # 7. 파일 정리 (중요: 사용 후 즉시 삭제)
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
            if cookie_path and os.path.exists(cookie_path):
                os.remove(cookie_path)
