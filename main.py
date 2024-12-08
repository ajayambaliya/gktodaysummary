import os
import re
import requests
import pymongo
from pymongo import MongoClient
from bs4 import BeautifulSoup
from datetime import datetime
from deep_translator import GoogleTranslator
import emoji


class FacebookPageManager:
    def __init__(self, app_id, app_secret, user_access_token, page_id):
        self.app_id = app_id
        self.app_secret = app_secret
        self.user_access_token = user_access_token
        self.page_id = page_id
        self.graph_version = 'v21.0'
        self.base_url = f'https://graph.facebook.com/{self.graph_version}'

    def generate_long_lived_token(self):
        url = f'{self.base_url}/oauth/access_token'
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': self.user_access_token
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get('access_token')

    def get_page_access_token(self):
        url = f'{self.base_url}/me/accounts'
        params = {
            'access_token': self.user_access_token,
            'fields': 'id,name,access_token'
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        accounts = response.json().get('data', [])
        for account in accounts:
            if account['id'] == self.page_id:
                return account['access_token']
        return None

    def post_to_page(self, page_access_token, message):
        url = f'{self.base_url}/{self.page_id}/feed'
        payload = {
            'message': message,
            'access_token': page_access_token
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        return response.json().get('id')


class BilingualCurrentAffairsScraper:
    def __init__(self, 
                 mongo_uri=os.getenv('MONGO_URI'), 
                 db_name='news_scraper'):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.urls_collection = self.db['scraped_urls']
        
        # Telegram Bot Configuration
        self.bot_token = os.getenv('BOT_TOKEN')
        self.channel_username = '@currentadda'
        print(f"Bot Token: {bool(self.bot_token)}")  # This will print True if token is set, False if None
        
        # Facebook Page Manager Configuration
        self.fb_manager = FacebookPageManager(
            app_id=os.getenv('APP_ID'),
            app_secret=os.getenv('APP_SECRET'),
            user_access_token=os.getenv('ACESS_TOKEN'),
            page_id=os.getenv('PAGE_ID')
        )
        self.fb_page_access_token = self.fb_manager.get_page_access_token()

    def get_channel_promo_message(self):
        """
        Generate a promotional message for Facebook and Telegram channels.
        """
        return (
            "🚀 Daily Current Affairs નો ખજાનો એટલે CurrentAdda 🌐\n\n"
            "🇬🇧 English & 🇮🇳 Gujarati Content\n"
            "Join us for the latest news:\n"
            "👉 Facebook: https://www.facebook.com/currentaddaa\n"
            "👉 Telegram: https://telegram.me/currentadda"
        )

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

    def format_bilingual_message(self, orig_titles, orig_paragraphs, guj_titles, guj_paragraphs, is_facebook=False):
        messages = []
        emoji_list = ['📰', '🌍', '🔍', '📡', '💡', '🌐', '📊', '🗞️', '📝', '🚀']
        
        for orig_title, orig_para, guj_title, guj_para in zip(
            orig_titles, orig_paragraphs, guj_titles, guj_paragraphs):
            
            random_emoji = emoji_list[hash(orig_title) % len(emoji_list)]
            
            if is_facebook:
                message = (
                    f"{random_emoji} English Title: {orig_title}\n"
                    f"Gujarati Title: {guj_title}\n\n"
                    f"English Content:\n{orig_para[:400]}...\n\n"
                    f"Gujarati Content:\n{guj_para[:400]}...\n\n"
                )
            else:
                message = (
                    f"{random_emoji} <b>English Title:</b> {orig_title}\n"
                    f"<b>🇮🇳 Gujarati Title:</b> {guj_title}\n\n"
                    f"🇬🇧 <i>English Content:</i>\n{orig_para[:400]}...\n\n"
                    f"🇮🇳 <i>Gujarati Content:</i>\n{guj_para[:400]}...\n\n"
                )
            messages.append(message)
        
        return "\n\n".join(messages)

    def post_to_facebook(self, message):
        """
        Post a message to the Facebook Page using the Page Access Token.
        """
        if not self.fb_page_access_token:
            print("❌ Facebook Page Access Token is missing.")
            return False

        print("\n=== Posting to Facebook ===")
        post_id = self.fb_manager.post_to_page(self.fb_page_access_token, message)
        if post_id:
            print(f"🎉 Successfully posted to Facebook with Post ID: {post_id}")
        else:
            print("❌ Failed to post to Facebook.")
        return post_id

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
            
            # Format bilingual messages
            final_message_telegram = self.format_bilingual_message(
                orig_titles, orig_paragraphs, 
                guj_titles, guj_paragraphs
            )
            
            final_message_facebook = self.format_bilingual_message(
                orig_titles, orig_paragraphs, 
                guj_titles, guj_paragraphs,
                is_facebook=True
            )
            
            # Add header with date
            current_date = datetime.now().strftime('%d-%b-%Y')
            header = f"🗓️ Current Affairs - {current_date}\n📊 Total New Articles: {len(orig_titles)}\n\n"
            
            # Get channel promotional message
            promo_message = self.get_channel_promo_message()
            
            # Combine all messages
            complete_message_telegram = header + final_message_telegram + "\n\n" + promo_message
            complete_message_facebook = header + final_message_facebook + "\n\n" + promo_message
            
            # Send to Telegram
            self.send_to_telegram(complete_message_telegram)
            
            # Post to Facebook
            self.post_to_facebook(complete_message_facebook)
        else:
            print("No new articles found.")

if __name__ == "__main__":
    scraper = BilingualCurrentAffairsScraper()
    scraper.main()
