import os
import re
import requests
import pymongo
from pymongo import MongoClient
from bs4 import BeautifulSoup
from datetime import datetime
from deep_translator import GoogleTranslator
import emoji

class BilingualCurrentAffairsScraper:
    def __init__(self, 
                 mongo_uri='MONGO_URI', 
                 db_name='news_scraper'):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.urls_collection = self.db['scraped_urls']
        
        # Telegram Bot Configuration
        self.bot_token = 'BOT_TOKEN'
        self.channel_username = '@gujtest'

    def get_article_urls(self, page_url):
        try:
            response = requests.get(page_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = soup.find_all('h1', id='list')
            urls = [a.find('a')['href'] for a in articles if a.find('a')]
            return urls
        except Exception as e:
            print(f"Error fetching URLs: {e}")
            return []

    def filter_new_urls(self, urls):
        new_urls = [url for url in urls if not self.urls_collection.find_one({'url': url})]
        return new_urls

    def save_urls(self, urls):
        for url in urls:
            self.urls_collection.update_one(
                {'url': url},
                {'$set': {
                    'scraped_at': datetime.now(),
                    'status': 'processed'
                }},
                upsert=True
            )

    def clean_text(self, text):
        return re.sub(r'\s+', ' ', text).strip()

    def extract_bilingual_content(self, article_urls):
        original_titles, original_paragraphs = [], []
        gujarati_titles, gujarati_paragraphs = [], []

        for article_url in article_urls:
            try:
                response = requests.get(article_url, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Check for featured image section
                featured_image_section = soup.find('div', 
                    class_='featured_image', 
                    style='margin-bottom:-5px;')
                
                if not featured_image_section:
                    print(f"Skipping {article_url} - No featured image")
                    continue

                # Original English Content
                original_title = self.clean_text(soup.find('h1', id='list', 
                    style="text-align:center; font-size:20px;").text)
                
                original_paragraph = self.clean_text(featured_image_section.find_next('p').text)
                
                # Translate to Gujarati
                gujarati_title = GoogleTranslator(source='en', target='gu').translate(original_title)
                gujarati_paragraph = GoogleTranslator(source='en', target='gu').translate(original_paragraph)
                
                original_titles.append(original_title)
                original_paragraphs.append(original_paragraph)
                gujarati_titles.append(gujarati_title)
                gujarati_paragraphs.append(gujarati_paragraph)

            except Exception as e:
                print(f"Error scraping {article_url}: {e}")

        return (original_titles, original_paragraphs, 
                gujarati_titles, gujarati_paragraphs)

    def format_bilingual_message(self, orig_titles, orig_paragraphs, guj_titles, guj_paragraphs):
        messages = []
        emoji_list = ['📰', '🌍', '🔍', '📡', '💡', '🌐', '📊', '🗞️', '📝', '🚀']
        
        for orig_title, orig_para, guj_title, guj_para in zip(
            orig_titles, orig_paragraphs, guj_titles, guj_paragraphs):
            
            random_emoji = emoji.emojize(f":star: {emoji_list[hash(orig_title) % len(emoji_list)]}")
            
            message = (
                f"{random_emoji} <b>English Title:</b> {orig_title}\n"
                f"<b>🇮🇳 Gujarati Title:</b> {guj_title}\n\n"
                f"🇬🇧 <i>English Content:</i>\n{orig_para[:400]}...\n\n"
                f"🇮🇳 <i>Gujarati Content:</i>\n{guj_para[:400]}...\n\n"
            )
            messages.append(message)
        
        return "\n\n".join(messages)

    def send_to_telegram(self, message):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        def split_message(text, max_length=4096):
            return [text[i:i+max_length] for i in range(0, len(text), max_length)]
        
        message_chunks = split_message(message)
        
        for chunk in message_chunks:
            payload = {
                'chat_id': self.channel_username,
                'text': chunk,
                'parse_mode': 'HTML'
            }
            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Telegram send error: {e}")

    def get_channel_promo_message(self):
        return (
            "🚀 <b>Daily Current Affairs નો ખજાનો એટલે CurrentAdda</b> 🌐\n\n"
            "🇬🇧 English & 🇮🇳 Gujarati Content\n"
            "<i>Join us for the latest news, https://telegram.me/currentadda </i>"
        )

    def main(self):
        base_url = "https://www.gktoday.in/current-affairs/"
        page_number = 1
        all_urls = []

        while True:
            page_url = f"{base_url}page/{page_number}/"
            article_urls = self.get_article_urls(page_url)
            
            if not article_urls:
                break
            
            all_urls.extend(article_urls)
            page_number += 1

        # Filter new URLs
        new_urls = self.filter_new_urls(all_urls)
        
        if new_urls:
            # Save and process new URLs
            self.save_urls(new_urls)
            
            # Extract bilingual content
            (orig_titles, orig_paragraphs, 
             guj_titles, guj_paragraphs) = self.extract_bilingual_content(new_urls)
            
            # Check if we have any valid articles after filtering
            if not orig_titles:
                print("No articles with featured images found.")
                return
            
            # Format bilingual message
            final_message = self.format_bilingual_message(
                orig_titles, orig_paragraphs, 
                guj_titles, guj_paragraphs
            )
            
            # Add header with date
            current_date = datetime.now().strftime('%d-%b-%Y')
            header = (f"🗓️ <b>Bilingual Current Affairs - {current_date}</b>\n"
                      f"📊 <i>Total New Articles: {len(orig_titles)}</i>\n\n")
            
            # Get channel promotional message
            promo_message = self.get_channel_promo_message()
            
            # Combine all messages
            complete_message = header + final_message + "\n\n" + promo_message
            
            # Send to Telegram
            self.send_to_telegram(complete_message)
        else:
            print("No new articles found.")

if __name__ == "__main__":
    scraper = BilingualCurrentAffairsScraper()
    scraper.main()
