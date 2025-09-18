#!/usr/bin/env python
# coding: utf-8

# In[1]:


import requests
import json
import csv
from datetime import datetime
from collections import Counter
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from googletrans import Translator
from konlpy.tag import Okt

NAVER_CLIENT_ID = "KHG6B47JKqTFQWmugqCK"
NAVER_CLIENT_SECRET = "V_bPvO06sv"
DB_FILE = "news_monitoring.db" 

try:
    font_path = "c:/Windows/Fonts/malgun.ttf"
    font = font_manager.FontProperties(fname=font_path).get_name()
    rc('font', family=font)
except FileNotFoundError:
    print("Malgun Gothic 폰트를 찾을 수 없습니다. 시각화 시 한글이 깨질 수 있습니다.")
    print("Mac의 경우 'AppleGothic', Linux의 경우 'NanumGothic' 등을 시도해 보세요.")


def get_naver_news(query, display=20):
    """네이버 뉴스 API를 호출하는 함수 (최신순 정렬)"""
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display={display}&sort=date"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['items']

def init_db(db_path):
    """데이터베이스 초기화 함수: 'articles' 테이블 생성"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_timestamp TEXT NOT NULL,
                final_query TEXT NOT NULL,
                title TEXT NOT NULL,
                original_link TEXT NOT NULL UNIQUE,
                sentiment_score REAL NOT NULL
            )
        ''')
        conn.commit()

def analyze_and_process_articles(articles, final_query, db_path):
    """
    뉴스 기사 리스트를 받아 작업을 수행합니다:
    1. 감성 분석 수행 및 평균 점수 계산
    2. 모든 기사 본문에서 핵심 키워드(명사) 추출
    3. 분석 결과를 데이터베이스에 저장 (중복 방지)
    """
    analyzer = SentimentIntensityAnalyzer()
    translator = Translator()
    okt = Okt()

    total_compound_score = 0
    article_count = 0
    all_descriptions = ""
    new_article_count = 0

    print("\n--- 개별 뉴스 분석 및 결과 저장 ---")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for article in articles:
            try:
                link = article.get('originallink', '')
                if not link: continue

                cursor.execute("SELECT id FROM articles WHERE original_link = ?", (link,))
                if cursor.fetchone() is not None:
                    continue

                title = article.get('title', '').replace('<b>', '').replace('</b>', '')
                description = article.get('description', '').replace('<b>', '').replace('</b>', '')
                if not description: continue
                
                all_descriptions += description + " "

                translated_text = translator.translate(description, src='ko', dest='en').text
                vs = analyzer.polarity_scores(translated_text)
                compound_score = vs['compound']
                
                print(f" - (신규) 제목: {title}")
                print(f"   감성 점수: {compound_score:.4f}")

                total_compound_score += compound_score
                article_count += 1
                new_article_count += 1

                # 3. DB에 저장
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    "INSERT INTO articles (search_timestamp, final_query, title, original_link, sentiment_score) VALUES (?, ?, ?, ?, ?)",
                    (now, final_query, title, link, compound_score)
                )

            except Exception as e:
                print(f"오류 발생으로 기사 하나를 건너뜁니다: {e}")
                continue
        conn.commit()
    
    print(f"\n>> 총 {new_article_count}개의 새로운 기사를 DB에 저장했습니다.")

    nouns = okt.nouns(all_descriptions)
    filtered_nouns = [n for n in nouns if len(n) > 1]
    
    top_keywords = Counter(filtered_nouns).most_common(10)
    average_score = total_compound_score / article_count if article_count > 0 else 0
    
    return average_score, top_keywords

def visualize_trends(db_path):
    keyword = input("\n[시계열 분석] 분석하고 싶은 키워드를 입력하세요 (전체는 Enter): ")

    with sqlite3.connect(db_path) as conn:
        query = "SELECT search_timestamp, sentiment_score FROM articles"
        params = []
        if keyword:
            query += " WHERE title LIKE ?"
            params.append(f'%{keyword}%')
        
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        print("해당 키워드에 대한 데이터가 없습니다.")
        return

    df['date'] = pd.to_datetime(df['search_timestamp']).dt.date
    daily_stats = df.groupby('date').agg(
        mention_count=('sentiment_score', 'count'),
        avg_sentiment=('sentiment_score', 'mean')
    ).reset_index()

    # 시각화
    fig, ax1 = plt.subplots(figsize=(12, 6))

    ax1.bar(daily_stats['date'], daily_stats['mention_count'], color='skyblue', label='일일 언급량(기사 수)')
    ax1.set_xlabel('날짜')
    ax1.set_ylabel('언급량(건)', color='skyblue')
    ax1.tick_params(axis='y', labelcolor='skyblue')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)

    ax2 = ax1.twinx()
    ax2.plot(daily_stats['date'], daily_stats['avg_sentiment'], color='tomato', marker='o', linestyle='--', label='평균 감성 점수')
    ax2.set_ylabel('평균 감성 점수', color='tomato')
    ax2.tick_params(axis='y', labelcolor='tomato')
    ax2.axhline(0, color='gray', linewidth=0.8, linestyle=':') 

    plot_title = f"'{keyword}' 관련 뉴스 트렌드 분석" if keyword else "전체 뉴스 트렌드 분석"
    plt.title(plot_title)
    fig.tight_layout()
    fig.legend(loc='upper right', bbox_to_anchor=(1,1), bbox_transform=ax1.transAxes)
    plt.grid(True, axis='y', linestyle=':', alpha=0.6)
    
    print("\n분석 그래프를 출력합니다. (그래프 창을 닫으면 프로그램이 종료됩니다.)")
    plt.show()


if __name__ == "__main__":
    init_db(DB_FILE)

    base_query = input("검색할 기관/주제명을 입력하세요: ")
    
    print("\n[ 검색어 상세화 옵션 ]")
    print("1: 기본 검색어만 사용")
    print("2: '기업', 'MOU', '사회공헌' 등 기업 파트너십/CSR 관련 뉴스")
    print("3: '정책', '법률', '권리', '캠페인' 등 정책/권리옹호 관련 뉴스")
    print("4: '우크라이나', '긴급구호' 등 국제 분쟁/긴급구호 관련 뉴스")
    print("5: '홍보대사', '모금', '후원자' 등 기금 마련/대중 캠페인 관련 뉴스")

    option = ""
    while option not in ['1', '2', '3', '4', '5']:
        option = input("원하는 옵션을 선택하세요: ")

    final_query = base_query
    if option == '2':
        final_query = f'"{base_query}" AND (기업 OR 협약 OR 파트너십 OR MOU OR 후원 OR 기부)'
    elif option == '3':
        final_query = f'"{base_query}" AND (정책 OR 법률 OR 제도 OR 권리 OR 정부)'
    elif option == '4':
        final_query = f'"{base_query}" AND (우크라이나 OR 가자지구 OR 아프가니스탄 OR 난민촌 OR 긴급구호 OR 분쟁)'
    elif option == '5':
        final_query = f'"{base_query}" AND (캠페인 OR 홍보대사 OR 모금 OR 후원자 OR 기금 OR 콘서트)'

    print(f"\n>> 최종 검색어: '{final_query}'")
    
    try:
        if "YOUR_NAVER_CLIENT_ID" in NAVER_CLIENT_ID:
            raise ValueError("코드에 네이버 클라이언트 ID와 시크릿을 입력해주세요.")
        
        print("네이버 뉴스 API에서 최신순으로 검색 중...")
        news_articles = get_naver_news(final_query)

        if news_articles:
            avg_sentiment, top_keywords = analyze_and_process_articles(news_articles, final_query, DB_FILE)
            
            print("\n" + "="*50)
            print(" 신규 수집 뉴스 분석 결과 요약 ")
            print("="*50)
            print(f" 평균 감성 점수: {avg_sentiment:.4f}")
            if avg_sentiment > 0.05:
                print("  >> 전반적으로 '긍정적' 뉘앙스의 뉴스들이 많습니다.")
            elif avg_sentiment < -0.05:
                print("  >> 전반적으로 '부정적' 뉘앙스의 뉴스들이 많습니다.")
            else:
                print("  >> 전반적으로 '중립적' 뉘앙스의 뉴스들이 많습니다.")
            
            print("\n 주요 핵심 키워드 (상위 10개):")
            for keyword, count in top_keywords:
                print(f"  - {keyword} ({count}회)")
            
            print("\n" + "="*50)
            print(f" 모든 결과를 '{DB_FILE}' 파일에 누적 저장했습니다.")

        else:
            print("새롭게 검색된 뉴스가 없습니다.")
            
    except Exception as e:
        print(f"\n오류가 발생했습니다: {e}")

    # 3. 시계열 분석 및 시각화
    while True:
        choice = input("\nDB 기반 시계열 분석을 수행하시겠습니까? (y/n): ").lower()
        if choice == 'y':
            visualize_trends(DB_FILE)
            break
        elif choice == 'n':
            print("프로그램을 종료합니다.")
            break
        else:
            print("잘못된 입력입니다. 'y' 또는 'n'을 입력해주세요.")


# In[ ]:




