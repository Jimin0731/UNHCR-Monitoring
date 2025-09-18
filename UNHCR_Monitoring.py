import requests
import json
import csv
from datetime import datetime
from collections import Counter
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from googletrans import Translator

NAVER_CLIENT_ID = "KHG6B47JKqTFQWmugqCK"
NAVER_CLIENT_SECRET = "V_bPvO06sv"

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

def analyze_and_process_articles(articles, final_query):
    """
    뉴스 기사 리스트를 받아 작업을 수행합니다:
    1. 감성 분석 수행 및 평균 점수 계산
    2. 모든 기사 본문에서 핵심 키워드(명사) 추출
    3. 분석 결과를 CSV 파일로 저장
    """
    analyzer = SentimentIntensityAnalyzer()
    translator = Translator()
    okt = Okt() # 형태소 분석기 초기화

    total_compound_score = 0
    article_count = 0
    all_descriptions = "" # 모든 뉴스 요약을 합칠 변수

    print("\n--- 개별 뉴스 분석 및 결과 저장 ---")
    
    # CSV 파일 준비
    csv_filename = "news_monitoring_log.csv"
    # 'a' 모드는 파일 끝에 이어서 쓰라는 의미 (데이터 누적)
    with open(csv_filename, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        # 파일이 비어있다면, 맨 위에 헤더(제목)를 추가
        if f.tell() == 0:
            writer.writerow(['검색일시', '최종검색어', '기사제목', '원본링크', '감성점수'])

        for article in articles:
            try:
                title = article.get('title', '').replace('<b>', '').replace('</b>', '')
                link = article.get('originallink', '')
                description = article.get('description', '').replace('<b>', '').replace('</b>', '')
                if not description: continue
                
                all_descriptions += description + " "

                # 1. 감성 분석
                translated_text = translator.translate(description, src='ko', dest='en').text
                vs = analyzer.polarity_scores(translated_text)
                compound_score = vs['compound']
                
                print(f" - 제목: {title}")
                print(f"   감성 점수: {compound_score:.4f}")

                total_compound_score += compound_score
                article_count += 1

                # 3. CSV 파일에 한 줄씩 저장
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                writer.writerow([now, final_query, title, link, f'{compound_score:.4f}'])

            except Exception as e:
                print(f"오류 발생으로 기사 하나를 건너뜁니다: {e}")
                continue
    
    # 2. 핵심 키워드 분석
    # Okt 형태소 분석기를 사용해 모든 요약문에서 명사만 추출
    nouns = okt.nouns(all_descriptions)
    # 두 글자 이상인 명사만 필터링
    filtered_nouns = [n for n in nouns if len(n) > 1]
    
    # 가장 많이 나온 명사 10개 추출
    top_keywords = Counter(filtered_nouns).most_common(10)

    # 평균 감성 점수 계산
    average_score = total_compound_score / article_count if article_count > 0 else 0
    
    return average_score, top_keywords

if __name__ == "__main__":
    base_query = input("검색할 기관/주제명을 입력하세요 (예: 유엔난민기구): ")
    
    # UNHCR 실무에 맞게 상세화 옵션 수정
    print("\n[ 검색어 상세화 옵션 ]")
    print("1: 기본 검색어만 사용")
    print("2: '난민법', '정책', '심사' 등 법률/제도 관련 뉴스")
    print("3: '아프간 특별기여자', '우크라이나' 등 특정 국가/이슈 관련 뉴스")
    print("4: '인도적 체류', '재정착' 등 지위/자격 관련 뉴스")
    
    option = ""
    while option not in ['1', '2', '3']:
        option = input("원하는 옵션을 선택하세요: ")

    # 상세 옵션에 따라 최종 검색어 조합
    final_query = base_query
    if option == '2':
        final_query = f'"{base_query}" AND (법 OR 정책 OR 심사)'
    elif option == '3':
        final_query = f'"{base_query}" AND (아프간 OR 아프가니스탄 OR 우크라이나)'

    print(f"\n>> 최종 검색어: '{final_query}'")
    
    try:
        if NAVER_CLIENT_ID == "YOUR_NAVER_CLIENT_ID":
            raise ValueError("코드에 네이버 클라이언트 ID와 시크릿을 입력해주세요.")
        
        print("네이버 뉴스 API에서 최신순으로 검색 중...")
        news_articles = get_naver_news(final_query)

        if news_articles:
            avg_sentiment, top_keywords = analyze_and_process_articles(news_articles, final_query)
            
            print("\n" + "="*50)
            print(" 최종 분석 결과 요약 ")
            print("="*50)
            print(f" 평균 감성 점수: {avg_sentiment:.4f}")
            if avg_sentiment > 0.05:
                print("  >> 전반적으로 '긍정적' 뉘앙스의 뉴스들이 많습니다. ")
            elif avg_sentiment < -0.05:
                print("  >> 전반적으로 '부정적' 뉘앙스의 뉴스들이 많습니다. ")
            else:
                print("  >> 전반적으로 '중립적' 뉘앙스의 뉴스들이 많습니다. ")
            
            print("\n 주요 핵심 키워드 (상위 10개):")
            for keyword, count in top_keywords:
                print(f"  - {keyword} ({count}회)")
            
            print("\n" + "="*50)
            print(f" 모든 결과는 'news_monitoring_log.csv' 파일에 누적 저장되었습니다.")

        else:
            print("뉴스 검색 결과가 없습니다.")
            
    except Exception as e:
        print(f"\n오류가 발생했습니다: {e}")


# In[ ]:




