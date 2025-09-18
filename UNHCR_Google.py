#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import pandas as pd
from datetime import datetime, timedelta
from collections import Counter
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from googletrans import Translator
from konlpy.tag import Okt
import platform
import sqlite3
from matplotlib import font_manager, rc 
import matplotlib.pyplot as plt
from gnews import GNews
import time
import random


# In[ ]:


DB_FILE = "google_news_monitoring.db"

os_name = platform.system()
if os_name == 'Windows':
    font_name = 'Malgun Gothic'
elif os_name == 'Darwin': # macOS
    font_name = 'AppleGothic'
elif os_name == 'Linux':
    font_name = 'NanumGothic'
else:
    font_name = None

if font_name:
    try:
        rc('font', family=font_name)
        print(f"{os_name} OS에서 '{font_name}' 폰트를 설정했습니다.")
    except Exception as e:
        print(f"'{font_name}' 폰트를 찾을 수 없습니다. 시각화 시 한글이 깨질 수 있습니다. 오류: {e}")
else:
    print("지원되지 않는 OS입니다. 폰트 설정이 필요합니다.")

def get_google_news(query, max_results=50, period='7d'):

    print(f"Searching Google News for: '{query}' (period: {period})")
    
    google_news = GNews(
        language='ko', 
        country='KR', 
        period=period,
        max_results=max_results,
        exclude_websites=['youtube.com', 'facebook.com'] 
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            articles = google_news.get_news(query)
            print(f"Found {len(articles)} articles (attempt {attempt + 1})")
            
            if articles:
                return articles
            else:
                if period == '7d' and attempt < max_retries - 1:
                    print("7일 기간에서 결과가 없어 30일로 확장합니다...")
                    google_news.period = '30d'
                elif period == '30d' and attempt < max_retries - 1:
                    print("30일 기간에서 결과가 없어 전체 기간으로 확장합니다...")
                    google_news.period = None
                    
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            
    print("모든 재시도 실패")
    return []

def create_flexible_queries(base_query):

    basic_queries = [
        base_query,  
        base_query.replace('"', ''), 
    ]
    
    unhcr_synonyms = ['유엔난민기구', 'UNHCR', '유엔 난민기구', '유엔난민청']
    
    related_keywords = [
        ['난민', '피난민', '이주민'],
        ['지원', '원조', '구호', '도움'],
        ['갈등', '분쟁', '위기', '전쟁'],
        ['인도적', '인권', '보호']
    ]
    
    queries = basic_queries.copy()
    
    for synonym in unhcr_synonyms:
        if synonym.lower() in base_query.lower():
            continue
        queries.append(f"{base_query} {synonym}")
        queries.append(f"{synonym} {base_query}")
    
    for keyword_group in related_keywords:
        for keyword in keyword_group[:2]:
            queries.append(f"{base_query} {keyword}")
    
    return list(set(queries)) 

def test_search_queries(base_query):

    test_queries = create_flexible_queries(base_query)
    
    additional_queries = [
        f'"{base_query}" 난민',
        f'"{base_query}" 지원',
        f'{base_query} 뉴스',
        f'{base_query} 최신',
        base_query.split()[0] if ' ' in base_query else base_query,  
    ]
    
    test_queries.extend(additional_queries)
    test_queries = list(set(test_queries)) 
    
    print(f"\n=== Testing {len(test_queries)} different search patterns ===")
    results = {}
    
    for i, query in enumerate(test_queries, 1):
        try:
            print(f"\n[Test {i}/{len(test_queries)}] Query: '{query}'")
            articles = get_google_news(query, max_results=20)  
            results[query] = len(articles)
            
            if articles:
                print(f"  -> Found {len(articles)} articles.")
                first_title = articles[0].get('title', '')
                print(f"  Example: {first_title[:60]}...")
            else:
                print(f"  -> No results found.")
                
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error: {e}")
            results[query] = 0
            
    print("\n=== Search Test Summary ===")
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    for query, count in sorted_results:
        print(f"'{query}': {count} articles")
    
    return dict(sorted_results)

def init_db(db_path):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_timestamp TEXT NOT NULL,
            final_query TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            link TEXT NOT NULL UNIQUE,
            published_date TEXT,
            sentiment_score REAL NOT NULL,
            publisher TEXT
            )
        ''')
        conn.commit()

def extract_keywords(text):
    """키워드 추출 함수 개선"""
    try:
        okt = Okt()
        nouns = okt.nouns(text)
        filtered_nouns = [n for n in nouns if len(n) > 1 and not n.isdigit()]
        return filtered_nouns
    except Exception as e:
        print(f"키워드 추출 중 오류: {e}")
        return []

def analyze_and_process_articles(articles, final_query, db_path):
    translator = Translator()
    analyzer = SentimentIntensityAnalyzer()
    
    total_compound_score = 0
    article_count = 0
    all_descriptions = ""
    new_article_count = 0
    
    print("\n--- Analyzing new articles and saving to database ---")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for i, article in enumerate(articles, 1):
            try: 
                link = article.get('url', '')
                if not link: 
                    continue
                    
                cursor.execute("SELECT id FROM articles WHERE link = ?", (link,))
                if cursor.fetchone() is not None:
                    continue
                    
                title = article.get('title', '')
                description = article.get('description', '')
                published_date = article.get('published date', '')
                publisher = article.get('publisher', {}).get('title', '') if isinstance(article.get('publisher'), dict) else str(article.get('publisher', ''))
                
                if not title:
                    continue
                
                analysis_text = f"{title} {description}" if description else title
                all_descriptions += analysis_text + " "
                
                try:
                    translated_text = translator.translate(analysis_text[:500], src='ko', dest='en').text  # 길이 제한
                    vs = analyzer.polarity_scores(translated_text)
                    compound_score = vs['compound']
                except Exception as trans_error:
                    print(f"  번역 오류, 원문으로 분석: {trans_error}")
                    vs = analyzer.polarity_scores(analysis_text)
                    compound_score = vs['compound']
                
                print(f" [{i}/{len(articles)}] (New) Title: {title[:50]}...")
                print(f"   Sentiment Score: {compound_score:.4f}")
                
                total_compound_score += compound_score
                article_count += 1
                new_article_count += 1
                
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    "INSERT INTO articles (search_timestamp, final_query, title, description, link, published_date, sentiment_score, publisher) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (now, final_query, title, description, link, published_date, compound_score, publisher)
                )
                
               
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Skipping article {i} due to error: {e}")
                continue
                
        conn.commit()
                      
    print(f"\n>> Saved {new_article_count} new articles to the database.")
    

    if all_descriptions:
        nouns = extract_keywords(all_descriptions)
        top_keywords = Counter(nouns).most_common(10)
    else:
        top_keywords = []
        
    average_score = total_compound_score / article_count if article_count > 0 else 0
                      
    return average_score, top_keywords

def visualize_top_keywords_sentiment(db_path):

    print("\n[Keyword Sentiment Analysis] Analyzing all data in the DB to generate a graph...")
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query("SELECT title, description, sentiment_score FROM articles", conn)
                      
        if df.empty:
            print("No data in the database to analyze.")
            return
        
        all_text = ' '.join((df['title'] + ' ' + df['description'].fillna('')).tolist())
        nouns = extract_keywords(all_text)
        top_10_keywords = [keyword for keyword, count in Counter(nouns).most_common(10)]
                      
        if not top_10_keywords:
            print("Could not find any keywords to analyze.")
            return
        
        print(f"\n>> Top 10 keywords for analysis: {', '.join(top_10_keywords)}")
              
        keyword_sentiments = {}
        for keyword in top_10_keywords:
            mask = (df['title'].str.contains(keyword, case=False, na=False) | 
                   df['description'].str.contains(keyword, case=False, na=False))
            avg_score = df[mask]['sentiment_score'].mean()
            if pd.notna(avg_score):
                keyword_sentiments[keyword] = avg_score
              
        if not keyword_sentiments:
            print("키워드별 감성 분석 데이터를 찾을 수 없습니다.")
            return
            
        sorted_sentiments = sorted(keyword_sentiments.items(), key=lambda item: item[1], reverse=True)
              
        keywords = [item[0] for item in sorted_sentiments]
        scores = [item[1] for item in sorted_sentiments]
        
        plt.figure(figsize=(12, 8))
        bars = plt.bar(keywords, scores, color='skyblue')
        plt.axhline(0, color='gray', linewidth=0.8, linestyle='--')
              
        plt.title('Top 10 Keywords AVG Sentiment Score', fontsize=16)
        plt.xlabel('Keyword', fontsize=12)
        plt.ylabel('AVG Sentiment Score (Neg/Pos)', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.grid(True, axis='y', linestyle=':', alpha=0.6)
              
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval, f'{yval:.3f}', 
                    va='bottom' if yval >= 0 else 'top', ha='center')
              
        plt.tight_layout()
        print("\nDisplaying analysis graph. Close the graph window to continue.")
        plt.show()
              
    except Exception as e:
        print(f"An error occurred while generating the graph: {e}")

def main():
    init_db(DB_FILE)

    base_query = input("검색할 기관/주제명을 입력하세요: ")

    print("\nTesting different search patterns to check for viability...")
    test_results = test_search_queries(base_query)

   
    valid_results = {q: c for q, c in test_results.items() if c > 0}
    
    if not valid_results:
        print("\n 모든 검색어에서 결과를 찾지 못했습니다.")
        print("\n 해결 방법:")
        print("1. 더 간단한 키워드로 시도해보세요 (예: '난민', '유엔' 등)")
        print("2. 영문 키워드를 시도해보세요 (예: 'UNHCR', 'refugee' 등)")
        print("3. 네트워크 연결을 확인해주세요")
        print("4. 잠시 후 다시 시도해주세요")
        return
    
    print(f"\n {len(valid_results)}개의 유효한 검색어를 찾았습니다!")
    
    print("\n[ 검색어 상세화 옵션 ]")
    print("1: 가장 많은 결과를 가진 검색어 사용")
    print("2: 기본 검색어만 사용")
    print("3: 수동으로 검색어 선택")

    option = ""
    while option not in ['1', '2', '3']:
        option = input("원하는 옵션을 선택하세요: ")

    if option == '1':
        best_query = max(valid_results, key=valid_results.get)
        final_query = best_query
        print(f"\n가장 많은 결과({valid_results[best_query]}개)를 가진 검색어를 사용합니다: '{best_query}'")
    elif option == '2':
        final_query = base_query
    else:  
        print("\n사용 가능한 검색어들:")
        query_list = list(valid_results.keys())
        for i, (query, count) in enumerate(valid_results.items(), 1):
            print(f"{i}: '{query}' ({count}개 결과)")
        
        while True:
            try:
                choice = int(input(f"선택하세요 (1-{len(query_list)}): ")) - 1
                if 0 <= choice < len(query_list):
                    final_query = query_list[choice]
                    break
                else:
                    print("올바른 번호를 입력하세요.")
            except ValueError:
                print("숫자를 입력하세요.")

    print(f"\n>> Final search query: '{final_query}'")

    try:
        print("\nFinal search in progress...")
        news_articles = get_google_news(final_query, max_results=100)

        if news_articles:
            avg_sentiment, top_keywords = analyze_and_process_articles(news_articles, final_query, DB_FILE)

            print("\n" + "="*60)
            print(" Summary of Newly Collected News Analysis ")
            print("="*60)
            print(f" Articles found: {len(news_articles)}")
            print(f" Average Sentiment Score: {avg_sentiment:.4f}")
            if avg_sentiment > 0.05:
                print("  >> Overall sentiment appears to be 'Positive' ")
            elif avg_sentiment < -0.05:
                print("  >> Overall sentiment appears to be 'Negative' ")
            else:
                print("  >> Overall sentiment appears to be 'Neutral' ")

            if top_keywords:
                print("\n Top 10 Keywords:")
                for keyword, count in top_keywords:
                    print(f"  - {keyword} ({count} times)")

            print("\n" + "="*60)
            print(f" All results have been cumulatively saved to '{DB_FILE}'.")

        else:
            print("\n 최종 검색에서 결과를 찾지 못했습니다.")

    except Exception as e:
        print(f"\nA critical error occurred: {e}")

    while True:
        choice = input("\nDB에 저장된 모든 데이터를 기반으로 키워드 감성 분석을 수행하시겠습니까? (y/n): ").lower()
        if choice == 'y':
            visualize_top_keywords_sentiment(DB_FILE)
            break
        elif choice == 'n':
            print("프로그램을 종료합니다.")
            break
        else:
            print("잘못된 입력입니다. 'y' 또는 'n'을 입력해주세요.")

if __name__ == "__main__":
    main()


