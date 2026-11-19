import configparser
import os
import platform
import plistlib
import random
import winreg
import re

import shutil
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from urllib.parse import urlparse
from configparser import ConfigParser
import pandas as pd
from openpyxl import Workbook
import pyperclip
import undetected_chromedriver as webdriver 
from undetected_chromedriver import ChromeOptions, Chrome
import os
import psutil
from pathlib import Path
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import json
import platform
import sys
import time
import webbrowser
from pathlib import Path

import requests

BASE_URL = "https://toolshive.io"      # use http://127.0.0.1:8000 while testing
PRODUCT_SLUG = "whatnot-bot"            # the product's slug on the website
TOKEN_FILE = Path.home() / ".toolshive" / "token.json"
TIMEOUT = 15

def create_config_if_not_exists(filename="config.ini"):
    if not os.path.exists(filename):
        config = ConfigParser()
        config["SETTINGS"] = {
            "page_link": "https://www.whatnot.com",
            "min_users": "100",
            "category": "",
            "max_reviews_from_each_profile": "50"
        }
        with open(filename, "w") as f:
            config.write(f)
def get_settings():
	if not os.path.exists("config.ini"):
		#print("ERROR: config.ini not found.")
		return None, None, None, None

	config = ConfigParser() 
	config.read("config.ini")

	try:
		settings = config["SETTINGS"]
		min_users = int(settings.get("min_users", 0)) if settings.get("min_users") else None
		category = settings.get("category", None)
		max_reviews = int(settings.get("max_reviews_from_each_profile", 0)) if settings.get("max_reviews_from_each_profile") else None

		return min_users, category, max_reviews

	except KeyError as e:
		#print(f"ERROR: {e} not found.")
		pass
	except ValueError:
		#print("ERROR: min_users or max_reviews_from_each_profile must be a number.")
		pass

	return None, None, None, None
try:
    min_viewers, review_category_url, max_reviews_from_each_profile = get_settings()
    #print(f"Settings loaded: min_viewers={min_viewers}, review_category_url={review_category_url}, max_reviews_from_each_profile={max_reviews_from_each_profile}")
except Exception:
    min_viewers = 50
    review_category_url = "https://www.whatnot.com/"
    max_reviews_from_each_profile = 1500

def run_account_setup_mode(config_file="config.ini"):
    try:
        config = ConfigParser()

        # 1. Create the config file if it does not exist in the directory
        if not os.path.exists(config_file):
            create_config_if_not_exists(config_file)

        config.read(config_file)

        # 2. Ensure the [SETTINGS] section exists
        if not config.has_section("SETTINGS"):
            config.add_section("SETTINGS")

        settings = config["SETTINGS"]

        # (config_key, Title, One-line explanation, Fallback default)
        fields = [
            ("min_users", "Minimum Live Viewers", "Scrape only live streams with viewers greater than or equal to this number", "100"),
            ("category", "Category URL", "Direct URL of the Whatnot category page matching your account niche", "None"),
            ("max_reviews_from_each_profile", "Max Reviews Per Profile", "Maximum number of reviews to scrape from each user profile", "2000")
        ]

        print("\n--- Whatnot Scraper Configuration ---")
        print("Press ENTER to keep the current value, or type a new value to update.\n")

        # 3. Display current values, explain each field, and update only if new input is given
        for key, title, desc, default in fields:
            current_val = settings.get(key, default)
            print(f"{title}: {desc}")
            new_val = input(f"  Current = {current_val} -> New: ").strip()

            if new_val:
                if key in ("min_users", "max_reviews_from_each_profile") and not new_val.isdigit():
                    print(f"  Invalid number. Keeping previous value ({current_val}).")
                else:
                    settings[key] = new_val
            elif key not in settings:
                settings[key] = default

        # 4. Write changes back to config.ini
        with open(config_file, "w") as f:
            config.write(f)

        print("\nConfiguration saved successfully.")

    except Exception as e:
        print(f"\nError during setup: {e}")


def close_browser(user_data_dir):
    """
    Close only Chrome processes using the specified user-data directory.
    """

    target_dir = os.path.normcase(os.path.abspath(str(user_data_dir)))
    processes_to_close = {}

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            info = proc.info
            name = (info['name'] or '').lower()

            if name != 'chrome.exe':
                continue

            cmdline = info['cmdline'] or []
            process_user_dir = None

            for i, arg in enumerate(cmdline):
                if arg.lower().startswith('--user-data-dir='):
                    process_user_dir = arg.split('=', 1)[1].strip('"')
                    break

                elif arg.lower() == '--user-data-dir' and i + 1 < len(cmdline):
                    process_user_dir = cmdline[i + 1].strip('"')
                    break

            if not process_user_dir:
                continue

            process_user_dir = os.path.normcase(
                os.path.abspath(process_user_dir)
            )

            if process_user_dir == target_dir:
                chrome_proc = psutil.Process(info['pid'])

                for child in chrome_proc.children(recursive=True):
                    processes_to_close[child.pid] = child

                processes_to_close[chrome_proc.pid] = chrome_proc

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not processes_to_close:
        # print("No previous automation browser found.")
        return

    process_list = list(processes_to_close.values())

    print("Closing previous automation browser...")

    for proc in process_list:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(process_list, timeout=5)

    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def get_installed_chrome_version():
    """Automatically detect the exact Chrome version installed on your PC"""
    try:
        
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        major_version = int(version.split('.')[0])
        print(f"✅ Detected Chrome version: {major_version} on your PC")
        return major_version
    except Exception as e:
        print(e)
        print("⚠️ Could not detect Chrome version automatically. Will let undetected_chromedriver try.")
        return get_installed_chrome_version_mac()

def get_installed_chrome_version_mac():
    """Detect Chrome version on macOS using Info.plist"""
    try:
        plist_path = "/Applications/Google Chrome.app/Contents/Info.plist"
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        version = plist.get("CFBundleShortVersionString")
        major_version = int(version.split('.')[0])
        print(f"✅ Detected Chrome version: {major_version} on your Mac")
        return major_version
    except Exception as e:
        print(e)
        print("⚠️ Could not detect Chrome version automatically.")
        return None

def open_browser(enable_background_args=True):
    # Get the current directory path
    current_directory = Path(os.getcwd())
   
    # Your custom user data directory
    user_data_dir = current_directory / "driver/User Data1"
   
    # Create Chrome options using undetected_chromedriver
    options = webdriver.ChromeOptions()
    
    # Make browser visible
    options.headless = False

    # User data directory (keeps logins, cookies, profiles)
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument('--profile-directory=Default')
    
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-features=CalculateNativeWinOcclusion")
    options.add_argument("--disable-features=BlockInsecurePrivateNetworkRequests")

    if enable_background_args:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        #print("⚙️ Background throttling arguments enabled for smooth bot running.")
    # Auto-detect Chrome version on your PC
    chrome_version = get_installed_chrome_version()
    
    # Create driver
    driver = Chrome(
        options=options,
        version_main=chrome_version,
    )
    
    for tab in driver.window_handles:
        driver.switch_to.window(tab)
        url = driver.current_url
        if "chrome://new-tab-page/" in url:
            break  # stop when found
            
    return driver

def is_login_page(driver):
    try:
        url, title, html = driver.current_url.lower(), driver.title.lower(), driver.page_source
        return "/login" in url or any(x in title for x in ("log in", "login", "sign up", "sign in")) or bool(re.search(r'<header[^>]*data-testid="home-splash-header"', html, re.I) and re.search(r'>Log in<', html, re.I) and re.search(r'>Sign up<', html, re.I))
    except Exception:
        return False
def switch_browser():
    current_directory = Path(os.getcwd())
    user_data_dir = current_directory / "driver/User Data1"
    close_browser(user_data_dir)
    driver = open_browser(enable_background_args=True)
    driver.get("https://www.whatnot.com/")
    time.sleep(random.uniform(2, 4))
    if is_login_page(driver):
        print("Login page Detected...")
        driver.quit()
        time.sleep(2)
        try:
            driver = open_browser(enable_background_args=False)
            driver.get("https://www.whatnot.com/")
            time.sleep(1)
            input("After Login Press Enter: ")
            
            driver.quit()
            time.sleep(1)
            try:
                driver = open_browser(enable_background_args=True)
                driver.get("https://www.whatnot.com/")
                time.sleep(random.uniform(2, 4))
                print("🚀 Browser opened successfully!")
                input("Press Enter to continue..")
                return driver
            except Exception as e:
                print("After login failed to open Browser. Try again")
                driver.quit()
            
        except Exception as e: 
            driver.quit()
            print(f"Login Failed: {e}")
    else:
        print("🚀 Browser opened successfully!")
        input("Press Enter to continue..")
        return driver
    
def open_and_read_excel():
    global file_path
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select an Excel File",filetypes=[("Excel Files", "*.xlsx *.xls")])
    if not file_path:
        print("No file selected.")
        return
    try:
        df = pd.read_excel(file_path)
        print("Excel file successfully loaded.")
        return df
    except Exception as e:
        print(f"Error reading the Excel file: {e}")
def save_excel(df,file_path):
    for i in range(3):
        try:
            df.to_excel(file_path, index=False)
            return
        except Exception as e:
            print("Excel save failed, retrying...", e)
def click_follow_button(user):
    buttons = driver.find_elements(By.XPATH, "//button[.//span[text()='Follow']]")
    if not buttons:
        buttons = driver.find_elements(By.XPATH, "//button[normalize-space()='Follow']")

    for button in buttons:
        button_text = button.text
        if button_text != "Following":  # Only click if the text is not "Following"
            try:
                button.click() 
                print(f"Followed   :  {user}")
                return
            except:
                pass    
    print(f"Already Followed : {user}") 

def follow_users_from_excel_file_mode():
    print("Select an Excel file containing both 'users' and 'status' columns.")
    df = open_and_read_excel()
    print("Total users : ", len(df))

    start = int(input("Enter start index (1-based): ")) - 1
    end = int(input("Enter end index (1-based): ")) - 1
    delay = int(input("Delay after follow each user (seconds): "))

    if end >= len(df):
        end = len(df) - 1

    for index in range(start, end):
        try:
            user = str(df.at[index, "users"]).strip()
            status = df.at[index, "status"] if "status" in df.columns else "scraped"
            status = str(status).strip().lower()

            if pd.isna(df.at[index, "status"]) or not status:
                status = "scraped"

            if status == "scraped" or status == "unfollowed":
                if "https://www.whatnot.com/user/" not in user:
                    user = "https://www.whatnot.com/user/" + user

                driver.get(user)
                click_follow_button(user)
                time.sleep(delay)
                df.at[index, "status"] = "Followed"
            else:
                print(f"Skipping user {user} at index {index + 1} as status is '{status}'.")
        except Exception as e:
            print(f"Error during following users: {e}")

        if index % 100 == 0 and index != 0:
            save_excel(df, file_path)

    save_excel(df, file_path)

def click_unfollow_button(user):
    buttons = driver.find_elements(By.XPATH, "//button[.//span[text()='Following']]")
    if not buttons:
        buttons = driver.find_elements(By.XPATH, "//button[normalize-space()='Following']")
    for button in buttons:
        button_text = button.text
        if button_text != "Follow":  # Only click if the text is not "Following"
            try:
                button.click() 
                print(f"UnFollowed   :  {user}")
                return
            except:
                pass    
    print(f"Already UnFollowed : {user}")

def unfollow_users_from_excel_mode():
    print("Select an Excel file containing both 'users' and 'status' columns.")
    df = open_and_read_excel()
    print(f"Total users: {len(df)}")

    start = int(input("Enter start index (1-based): ")) - 1
    end = int(input("Enter end index (1-based): ")) - 1
    delay = int(input("Delay after unfollow (seconds): "))

    if end >= len(df):
        end = len(df) - 1

    for index in range(start, end):
        try:
            user = df.at[index, "users"]
            status = df.at[index, "status"] if "status" in df.columns else "Followed"

            if str(status).strip().lower() == "followed":
                if "https://www.whatnot.com/user/" not in user:
                    user = "https://www.whatnot.com/user/" + user

                driver.get(user)
                click_unfollow_button(user)
                time.sleep(delay)
                df.at[index, "status"] = "Unfollowed"

            else:
                print(f"Skipping user {user} at index {index + 1} as status is '{status}'.")

        except Exception as e:
            print(f"Error: {e}")

        if index % 100 == 0 and index != 0:
            save_excel(df, file_path)

    save_excel(df, file_path)


def scroll_livestream_or_review_page(times=10, step=200, delay=1):
    for _ in range(times):
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(delay)

def create_reviews_excel_if_not_exists(filename="reviews_prfoile.xlsx"):
    if not os.path.exists(filename):
        wb = Workbook()
        ws = wb.active
        ws.append(["users", "number of profiles"])
        wb.save(filename)
def scrape_and_follow_users_from_reviews_excel_file_mode():
    print("""📄 Please select your input Excel file
            Your Excel sheet must contain 2 columns:
            1. users               (review page link)
            2. number of profiles  (how many profiles to scrape) """)

    input_df = open_and_read_excel()

    if input_df is None or "users" not in input_df.columns or "number of profiles" not in input_df.columns:
        print("ERROR: Invalid Excel file format.")
        print("Make sure your Excel file has 'users' and 'number of profiles' columns.")
        return

    follow_flag = input("Do you also want to follow scraped users? (y/n): ").strip().lower()
    if follow_flag not in ("y", "n"):
        print("ERROR: Please enter only y or n.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"scraped_users_from_reviews_{timestamp}.xlsx"
    master_df = pd.DataFrame(columns=["users", "status"])

    for i in range(len(input_df)):
        review_link = input_df["users"][i]
        reviews = int(input_df["number of profiles"][i])
        driver.get(review_link)
        print(f"Scraping reviews from: {review_link}")
        time.sleep(random.uniform(5, 10))
        try:
            users = collect_review_profile_links(reviews)
            print(f"Collected {len(users)} unique profile links from {review_link}")

        except Exception as e:
            print(f"Error scraping reviews from {review_link}")

        temp_df = pd.DataFrame({"users": users, "status": ["Scraped"] * len(users)})
        master_df = pd.concat([master_df, temp_df], ignore_index=True)
        master_df.drop_duplicates(subset="users", keep="first", inplace=True)

        if follow_flag == "y":
            scraped_users = master_df.loc[master_df["status"] == "Scraped", "users"].tolist()
            for user in scraped_users:
                try:
                    driver.get(user)
                    click_follow_button(user)
                    time.sleep(random.uniform(1, 3))
                    master_df.loc[master_df["users"] == user, "status"] = "Followed"
                except Exception as e:
                    print(f"Error following {user}: {e}")

        master_df.to_excel(file_name, index=False)

    print(f"Combined Excel file saved as {file_name}")

def scroll_following_followers_popup(scroll_count=100):
    try:
        for i in range(scroll_count):
            try:
                container = driver.find_element(By.CSS_SELECTOR, "main.overflow-y-auto")
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", container)
                time.sleep(0.3)
            except Exception:
                try:
                    time.sleep(1)
                    modal = driver.find_element(By.CSS_SELECTOR, "dialog[open]")
                    container = modal.find_element(By.CSS_SELECTOR, "main.overflow-y-auto")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", container)
                    continue
                except Exception:
                    break
        return True
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        
def scrape_users_from_follower_section_mode():
    df = pd.DataFrame(columns=["users", "status"])
    input("Open the user profile page and go to followers/following section: ")
    followers_count = int(input("Enter the number of followers to scrape: "))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"followers_output_{timestamp}.xlsx"
    users = set()
    unchanged_count = 0

    while len(users) <= followers_count:
        try:
            print("Scrolling popup...")
            scroll_following_followers_popup(scroll_count=100)
        except Exception as e:
            print(f"Error during scrolling: {e}")
            break

        try:
            print("Now scraping users ...")
            links = driver.find_elements(By.XPATH, '//a[starts-with(@href, "/user/")]')
            profile_links = [link.get_attribute("href") for link in links]
            profile_links = [link for link in profile_links if re.match(r"^https://www\.whatnot\.com/user/[^/?]+$", link or "")]

            previous_total = len(users)
            users.update(profile_links)
            current_total = len(users)

            print(f"Users Scraped: {current_total}")

            if current_total == previous_total:
                unchanged_count += 1
            else:
                unchanged_count = 0

            if current_total >= followers_count:
                break

            if unchanged_count >= 10:
                print("No more users left to scrape.")
                break

        except Exception as e:
            print(f"Error in loop: {e}")
            break

    users = list(users)
    df["users"] = users
    df["status"] = "Scraped"
    df.to_excel(file_name, index=False)
    print(f"Collected {len(users)} unique profile links.")
    print(f"DataFrame saved as {file_name}")

    try:
        driver.find_element(By.CSS_SELECTOR, "[data-dialog-dismiss]").click()
    except:
        pass

def get_message_from_file(filename="message.txt") -> str:
    """
    Reads the contents of the given text file and returns it as a string.
    Default file: message.txt
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            message = file.read().strip()
        return message
    except:
        #create message file :
        with open(filename, "w", encoding="utf-8") as file:
            message = input("message.txt not found. Please enter the message you want to send (use 'NAME' as a placeholder for the username): ")
            file.write(message)

def get_username_for_message():
    try:
        name = driver.find_element(By.XPATH, "//*[@data-testid='user-profile-username']/ancestor::section[1]/following-sibling::strong").text.replace("\xa0", "").strip()
        if name:
            return name
    except:
        pass

    try:
        return driver.find_element(By.CSS_SELECTOR, "strong[class*='text-neutral']").text.replace("\xa0", "").strip()
    except:
        return driver.current_url.rstrip("/").split("/")[-1]
def send_message(message, show_link=None, add_username=False):
    os_name = platform.system()

    if add_username:
        person_name = get_username_for_message()
        if "NAME" in message:
            message = message.replace("NAME", person_name)
        else:
            print("❌ ERROR: 'NAME' keyword is missing from message.txt!")

    message_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.LINK_TEXT, "Message"))
    )
    driver.get(message_box.get_attribute("href"))
    time.sleep(random.uniform(5, 10))

    wait = WebDriverWait(driver, 20)

    if show_link:
        message_box = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'textarea[data-testid="input-message"]')
            )
        )
        message_box.click()
        pyperclip.copy(show_link)

        actions = ActionChains(driver)
        key = Keys.COMMAND if os_name == "Darwin" else Keys.CONTROL
        actions.key_down(key).send_keys("v").key_up(key).perform()

        time.sleep(1)
        message_box.send_keys(Keys.ENTER)
        print("Message sent successfully!")
        time.sleep(5)

    message_box = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'textarea[data-testid="input-message"]')
        )
    )
    message_box.click()
    pyperclip.copy(message)

    actions = ActionChains(driver)
    key = Keys.COMMAND if os_name == "Darwin" else Keys.CONTROL
    actions.key_down(key).send_keys("v").key_up(key).perform()

    time.sleep(1)
    message_box.send_keys(Keys.ENTER)
    print("Message sent successfully!")
    time.sleep(5)

    return True
def message_mode():
    print("Select an Excel file containing both 'users' and 'status' columns.For each user, the bot will send a message from message.txt.")
    df = open_and_read_excel()
    message = get_message_from_file()

    include_name = input("Do you want to add the username in the message? (y/n): ").strip().lower()
    add_username = True if include_name == 'y' else False

    start = int(input("Enter start index: "))
    end = int(input("Enter end index: "))
    delay = int(input("Please Enter the Time delay between each message: "))
    link = input("Please Enter the link of the show or Leave Empty If you don't want to add show link:" \
    "or if show link already in message.txt then also leave blank: ").strip()
    
    start = start - 2
    end = end - 2

    for index in range(start, end):
        try:
            user = str(df.at[index, 'users']).strip()

            if "https://www.whatnot.com/user/" not in user:
                user_link = "https://www.whatnot.com/user/" + user
            else:
                user_link = user

            driver.get(user_link)
            time.sleep(delay)
            
            success = send_message(message, link, add_username=add_username)
            if not success:
                print("Stopping messaging process.")
                break

            df.at[index, 'status'] = "Messaged"           
            df.to_excel(file_path, index=False)
        except Exception as e:
            print(e)
def parse_livestream_views_count(text):
    try:
        text = text.upper().replace(",", "").strip()
        multiplier = {"K": 1_000, "M": 1_000_000}
        return int(float(text[:-1]) * multiplier[text[-1]]) if text[-1] in multiplier else int(text)
    except:
        nums = re.findall(r"[\d.]+", text)
        return int(float(nums[-1])) if nums else 0
def get_livestreams_with_min_viewers(viewer_limit=min_viewers):
    driver.get(page_link or "https://www.whatnot.com/")
    time.sleep(10)
    print("Scrolling livestreams page")
    scroll_livestream_or_review_page(times=15, step=random.randint(200, 500), delay=random.uniform(0.5, 1.5))

    streams_data = []
    livestream_cards = driver.find_elements(
        By.CSS_SELECTOR, 'section[data-type="LivestreamCard"]'
    )

    for card in livestream_cards:
        try:
            live_link = card.find_element(
                By.CSS_SELECTOR, 'a[href*="/live/"]'
            ).get_attribute("href")

            try:
                viewer_text = card.find_element(
                    By.XPATH,
                    './/span[contains(@class, "bg-background-brand-live-red")]'
                ).text.strip()

                raw_viewers = viewer_text.split("·")[-1].strip()
                viewers = parse_livestream_views_count(raw_viewers)
            except:
                viewers = viewer_limit
                print(f"Livestream viewers not found so default viewers : {viewer_limit}")

            if viewers >= viewer_limit:
                streams_data.append({
                    "link": live_link,
                    "viewers": viewers
                })

        except Exception as e:
            print(f"Error during scraping livestreams urls : {e}")

    print(f"Found {len(streams_data)} livestreams above {viewer_limit} viewers.")

    if not streams_data:
        print("No livestreams found.")
        return None

    return random.choice(streams_data)["link"]
def follow_users_in_livestream():
    elements = driver.find_elements(By.XPATH, "//div[@id='chat']//a[contains(@href, '/user/')]")
    for el in elements:
        try:
            el.click()
            time.sleep(2)
            try:
                # --- Wait for the Follow button to appear ---
                wait = WebDriverWait(driver, 5)
                follow_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Follow']")))
                driver.execute_script("arguments[0].click();", follow_button)  # JS click (more reliable)
                print("✅ Follow button clicked!")
                time.sleep(2)
            except:
                pass
        except:
            pass
        try:
            chat_box =  driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Say something..."]')
            chat_box.click()
        except:
            pass
def get_random_comment():
    with open("comments.txt", "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    return random.choice(comments) if comments else None
def close_livestream_popup():
    dialog = (By.CSS_SELECTOR, 'dialog[open]')
    close = (By.CSS_SELECTOR, 'dialog[open] button:has(svg[aria-label="Close modal"])')
    wait = WebDriverWait(driver, 5)

    try:
        button = wait.until(EC.presence_of_element_located(close))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)

        try:
            button.click()
            if wait.until(EC.invisibility_of_element_located(dialog)):
                print("✅ Popup closed with normal click.")
                return True
        except:
            pass

        try:
            ActionChains(driver).move_to_element(button).pause(0.2).click().perform()
            if wait.until(EC.invisibility_of_element_located(dialog)):
                print("✅ Popup closed with ActionChains.")
                return True
        except:
            pass

        try:
            driver.execute_script("arguments[0].click();", button)
            if wait.until(EC.invisibility_of_element_located(dialog)):
                print("✅ Popup closed with JavaScript.")
                return True
        except:
            pass

        try:
            ActionChains(driver).move_to_element_with_offset(
                driver.find_element(By.TAG_NAME, "body"), 10, 10
            ).click().perform()
            if wait.until(EC.invisibility_of_element_located(dialog)):
                print("✅ Clicked outside popup.")
                return True
        except:
            pass

        try:
            driver.execute_script(
                "document.querySelector('dialog[open]')?.close();"
            )
            if wait.until(EC.invisibility_of_element_located(dialog)):
                print("✅ Popup closed using dialog.close().")
                return True
        except:
            pass

        print("⚠️ Popup still appears to be open.")
        return False

    except Exception as e:
        print(f"❌ Error closing popup: {type(e).__name__}: {e}")
        return False
def follow_users_in_livestream_mode(run_for_seconds=None):
    
    end_time=None
    if run_for_seconds:
        end_time = time.time() + run_for_seconds

    while True:
        try:
            if end_time and time.time() > end_time:
                break
            stream_link = get_livestreams_with_min_viewers(min_viewers)

            if stream_link:
                driver.get(stream_link)
                time.sleep(10)
                driver.find_element(By.TAG_NAME, "body").click()
                close_livestream_popup()
                print("Joined live stream.")

                start_time = time.time()
                last_comment_time = start_time
                comment_count = 0
                max_comments = 1
                max_duration = 15 * 60  # 15 minutes
                comment_gap = 10 * 60    # 5 minutes

                while True:
                    elapsed_time = time.time() - start_time
                    if elapsed_time > max_duration:
                        print("⏰ Leaving stream after 15 minutes.")
                        break

                    # Always follow users in the live stream
                    follow_users_in_livestream()

                    # Check if it’s time to make a comment
                    if (comment_count < max_comments) and (time.time() - last_comment_time >= comment_gap):
                        try:
                            comment = get_random_comment()
                            try:
                                chat_box = driver.find_element(By.CSS_SELECTOR, "input.chatInput[data-cy='chat_text_field']")
                            except:
                                chat_box =  driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Say something..."]')
                            chat_box.send_keys(comment)
                            chat_box.send_keys(Keys.ENTER)
                            time.sleep(5)
                            comment_count += 1
                            last_comment_time = time.time()
                            print(f"💬 Commented: {comment}")
                        except Exception as e:
                            print(f"Error sending comment: {e}")
                            close_livestream_popup()
                            comment_count += 1
                            last_comment_time = time.time()
                    # Small delay to prevent overloading CPU / DOM
                    time.sleep(5)

        except Exception as e:
            print(e)

def click_our_customers_next_page_button():
    buttons = driver.find_elements(
        By.XPATH,
        "//div[contains(@class,'flex items-center gap-3')]//button[last()]"
    )

    if not buttons:
        print("Next button not found. Stopping.")
        return False

    button = buttons[0]

    if button.get_attribute("disabled") is not None:
        print("Next button disabled. Finished scraping.")
        return False

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", button
    )
    driver.execute_script("arguments[0].click();", button)

    print("Customers next page button clicked successfully")
    time.sleep(10)

    return True
    
def scrape_our_customers_mode():
    whatnot_users = []
    file_name = f"Our Customers {datetime.now():%Y-%m-%d_%H-%M-%S}.xlsx"

    driver.get("https://www.whatnot.com/dashboard/orders?first=100")
    time.sleep(5)

    while True:
        wait = WebDriverWait(driver, 20)
        xpath = "//a[contains(@href,'participantId')]"

        wait.until(EC.presence_of_all_elements_located((By.XPATH, xpath)))

        for element in driver.find_elements(By.XPATH, xpath):
            try:
                username = element.text.strip()
                profile_link = f"https://www.whatnot.com/user/{username}"

                if username and profile_link not in whatnot_users:
                    whatnot_users.append(profile_link)
                    print(profile_link)

            except StaleElementReferenceException:
                continue

        pd.DataFrame({
            "users": whatnot_users,
            "status": "Scraped"
        }).to_excel(file_name, index=False)

        print(f"Saved {len(whatnot_users)} users")

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)
        if not click_our_customers_next_page_button():
            print("Successflly scrape & save all customers.")
            break
def collect_and_follow_bidders_from_livestream_mode(run_for_seconds=None):
    end_time = time.time() + run_for_seconds if run_for_seconds else None
    message = get_message_from_file()
    driver.get("https://www.whatnot.com/")

    df = pd.DataFrame(columns=["users", "bid_amount", "status"])
    filename = f"Bidders_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    seen_users = set()

    while True:
        try:
            if end_time and time.time() > end_time:
                break

            stream_link = get_livestreams_with_min_viewers(min_viewers)
            if not stream_link:
                continue

            driver.get(stream_link)
            time.sleep(10)
            driver.find_element(By.TAG_NAME, "body").click()
            close_livestream_popup()
            print("Joined live stream.")

            start_time = time.time()
            last_follow_time = start_time

            while time.time() - start_time < 15 * 60:
                try:
                    winning = driver.find_element(
                        By.CSS_SELECTOR, '[data-testid="show-winning-status"]'
                    )
                    text = driver.execute_script(
                        "return arguments[0].textContent;", winning
                    )
                    username = text.split()[0]

                    try:
                        bid = driver.find_element(
                            By.CSS_SELECTOR,
                            "strong.text-right.text-balance.text-neutral-50.block.font-sans.font-semibold.tabular-nums"
                        )
                        bid_amount = float(
                            driver.execute_script(
                                "return arguments[0].textContent;", bid
                            ).replace("$", "").strip()
                        )
                    except:
                        bid_amount = 30

                    if bid_amount > 2 and username not in seen_users:
                        seen_users.add(username)
                        profile_url = f"https://www.whatnot.com/user/{username}"
                        df.loc[len(df)] = [profile_url, bid_amount, "Scraped"]
                        print(f"Scraped bidder: {profile_url} - ${bid_amount}")

                except:
                    pass

                if time.time() - last_follow_time >= 5 * 60:
                    print("Follow Time..")
                    scraped_users = df.loc[
                        df["status"] == "Scraped", "users"].tolist()
                    if not scraped_users:
                        print("No users found to follow")
                        continue
                    if scraped_users:
                        main_window = driver.current_window_handle
                        driver.execute_script("window.open('');")
                        driver.switch_to.window(driver.window_handles[-1])

                        for profile_url in scraped_users:
                            try:
                                print(f"Following User: {profile_url}")
                                driver.get(profile_url)
                                click_follow_button(profile_url)
                                send_message(message)
                                df.loc[df["users"] == profile_url, "status"] = "Followed"
                            except Exception as e:
                                print(f"Error following {profile_url}: {e}")    

                        driver.close()
                        driver.switch_to.window(main_window)
                        df.to_excel(filename, index=False)
                        print(f"Saved DF to {filename}")

                    last_follow_time = time.time()

        except Exception as e:
            print(e)

def follow_unfollow_profile_at_same_time():
    global driver
    time.sleep(3)
    print("Select an Excel file containing both 'users' and 'status' columns.")
    df = open_and_read_excel()
    print("Total users:", len(df))

    start = int(input("Enter start index (1-based): ")) - 1
    end = int(input("Enter end index (1-based): ")) - 1
    delay = int(input("Delay after clicking follow (seconds): "))

    if end >= len(df):
        end = len(df) - 1

    for index in range(start, end):
        try:
            user = df.at[index, "users"]
            status = df.at[index, "status"] if "status" in df.columns else "Scraped"

            if status == "Scraped":
                if "https://www.whatnot.com/user/" not in user:
                    user = "https://www.whatnot.com/user/" + user
                try:
                    driver.get(user)
                    time.sleep(1)
                    click_follow_button(user)
                    time.sleep(delay)
                    click_unfollow_button(user)
                    df.at[index, "status"] = "Unfollowed"
                except Exception as e:
                    print(f"Error during follow - unfollow user : {user} -> Error : {e} ")

        except Exception as e:
            print(e)

        if index % 100 == 0 and index != 0:
            save_excel(df, file_path)

    save_excel(df, file_path)

def click_profile_following_button(timeout=15):
    xpath = "//button[.//strong[contains(.,'Following')] and not(contains(.,'Followers'))]"

    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)

        try:
            button.click()
        except:
            driver.execute_script("arguments[0].click();", button)

        return True

    except Exception as e:
        print(f"❌ Failed to click Following: {e}")
        return False
def scrape_and_unfollow_mode(): 
    profile_link = input("Enter your own profile URL: ")
    followers_count = int(input("Please Enter the Number of Followers to Scrape & Unfollow : "))
    delay = int(input("Delay after clicking follow (seconds): "))

    driver.get(profile_link)
    time.sleep(5)
    click_profile_following_button()
    time.sleep(5)

    users = set()
    unchanged_count = 0
    total_unfollowed = 0
    
    while total_unfollowed < followers_count:
    
        try:
            print("Scrolling following popup ...")
            scroll_following_followers_popup(scroll_count=100)
        except TimeoutException:
            print("Scrollable element not found.")
            break
    
        try:
            links = driver.find_elements(By.XPATH, '//a[starts-with(@href, "/user/")]')
            profile_links = {
                link.get_attribute("href")
                for link in links
                if re.match(r"^https://www\.whatnot\.com/user/[^/?]+$", link.get_attribute("href") or "")
            }
    
            old_total = len(users)
            users.update(profile_links)
            current_total = len(users)
    
            print(f"Users collected: {current_total}")
    
            # No new users found
            if current_total == old_total:
                unchanged_count += 1
                print(f"No new users: {unchanged_count}/5")
            else:
                unchanged_count = 0
    
            # Stop after 5 consecutive cycles with no new users
            if unchanged_count >= 5:
                print("No new users found for 5 consecutive cycles. Done.")
                break
    
            if current_total >= 1000:
                for user in list(users):
                    driver.get(user)
                    click_unfollow_button(user)
                    time.sleep(delay)
    
                    users.discard(user)
                    total_unfollowed += 1
    
                    if total_unfollowed >= followers_count:
                        print(f"Done. Unfollowed {total_unfollowed} users.")
                        return
    
                driver.get(profile_link)
                time.sleep(5)
                click_profile_following_button()
                time.sleep(5)
    
        except Exception as e:
            print(f"Error in loop: {e}")
            break
    if users:
        print(f"Processing remaining {len(users)} users...")
        for user in list(users):
            driver.get(user)
            click_unfollow_button(user)
            time.sleep(delay)
            total_unfollowed += 1
            if total_unfollowed >= followers_count:
                break

    print(f"Done. Total unfollowed: {total_unfollowed}")

    try:
        close_button = driver.find_element(By.CSS_SELECTOR, '[data-dialog-dismiss]')
        close_button.click()
    except:
        pass

def click_profile_follower_button(timeout=15):
    xpath = "//button[.//strong[contains(.,'Followers')]]"

    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", button)
        try:
            button.click()
        except:
            driver.execute_script("arguments[0].click();", button)

        return True

    except Exception as e:
        print(f"❌ Failed to click Followers: {e}")
        return False
def create_excel_if_not_exists(filename="profiles.xlsx"):
    import os
    from openpyxl import Workbook

    if not os.path.exists(filename):
        wb = Workbook()
        ws = wb.active
        ws.append(["profile_url", "followers_count"])
        wb.save(filename)
def scrape_multiple_profiles_mode():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"followers_output_{timestamp}.xlsx"
    print("Select an Excel file containing both 'profile_url' and 'followers_count' columns.")
    df = open_and_read_excel()
    master_users = {}
    profile_re = re.compile(r"^https://www\.whatnot\.com/user/[^/?]+$")

    follow = input("Do you also want to follow scraped users? (y/n): ").strip().lower() == "y"

    for row in df.itertuples(index=False):
        profile_url = row.profile_url
        followers_count = int(row.followers_count)

        print(f"\nURL: {profile_url} | Target: {followers_count}")

        driver.get(profile_url)
        time.sleep(random.uniform(10, 15))

        if not click_profile_follower_button():
            print("Followers button not found.")
            continue

        time.sleep(5)
        users = set()
        unchanged_count = 0

        while len(users) < followers_count:
            try:
                print("Scrolling popup...")
                scroll_following_followers_popup(scroll_count=100)
            except Exception as e:
                print(f"Scrolling error: {e}")
                continue

            old_total = len(users)

            try:
                links = driver.find_elements(
                    By.XPATH, "//a[starts-with(@href, '/user/')]"
                )

                users.update(
                    href for href in (link.get_attribute("href") for link in links)
                    if href and profile_re.match(href)
                )

                current_total = len(users)
                print(f"Users scraped: {current_total}")

                if current_total == old_total:
                    unchanged_count += 1
                    print(f"No new users: {unchanged_count}/5")
                else:
                    unchanged_count = 0

                if current_total >= followers_count:
                    break

                if unchanged_count >= 5:
                    print("No new users found. Scraping finished.")
                    break

            except Exception as e:
                print(f"Scraping error: {e}")
                break

        # Save users and optionally follow them
        for user in users:
            if user in master_users:
                continue

            status = "Scraped"

            if follow:
                try:
                    driver.get(user)
                    click_follow_button(user)
                    status = "Followed"
                    print(f"Followed: {user}")
                except Exception as e:
                    print(f"Follow error: {e}")

            master_users[user] = status

        pd.DataFrame(
            [{"users": user, "status": status}
             for user, status in master_users.items()]
        ).to_excel(file_name, index=False)

        print(f"Saved {len(users)} users to Excel.")

    print(f"\nDone. Total unique users: {len(master_users)}")

def scrape_username(joined_users, current_batch):
    chats = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="chat-message"]')

    for chat in chats:
        username = None

        try:
            href = chat.find_element(
                By.CSS_SELECTOR, 'a[data-testid="chat-message-avatar-link"]'
            ).get_attribute("href")
            username = href.rstrip("/").split("/")[-1] if href else None
        except:
            pass

        if not username:
            try:
                label = chat.find_element(
                    By.CSS_SELECTOR, 'button[aria-label^="Open actions for @"]'
                ).get_attribute("aria-label")
                username = label.replace("Open actions for @", "").strip() if label else None
            except:
                pass

        if not username or username in joined_users:
            continue

        joined_users.add(username)
        current_batch.append({
            "users": f"https://whatnot.com/user/{username}",
            "status": "Scraped"
        })
        print(f"{len(current_batch)} unique users")
def follow_scraped_users(df, filename):
    scraped_users = df.loc[df["status"] == "Scraped", "users"].tolist()

    if not scraped_users:
        return

    main_window = driver.current_window_handle
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])

    for user in scraped_users:
        driver.get(user)
        click_follow_button(user)
        df.loc[df["users"] == user, "status"] = "Followed"

    driver.close()
    driver.switch_to.window(main_window)

    df.to_excel(filename, index=False)
    print(f"Saved DF to {filename}")
def scrape_and_follow_livestream_joined_users_mode(run_for_seconds=None):
    choice = int(input(
        "Press 1 to run on a specific Live Stream\n"
        "Press 2 to run on multiple Live Streams in your Niche: "
    ))

    if choice == 1:
        url = input("Enter live stream Url: ")
    elif choice != 2:
        print("Wrong Choice!!")
        return

    end_time = time.time() + run_for_seconds if run_for_seconds else None

    joined_users = set()
    current_batch = []
    filename = f"Live_stream_viewers_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    df = pd.DataFrame(columns=["users", "status"])

    while not end_time or time.time() <= end_time:
        if choice == 1:
            stream_url = url
            max_duration = float("inf")
        else:
            stream_url = get_livestreams_with_min_viewers(min_viewers)
            if not stream_url:
                continue
            max_duration = 15 * 60

        driver.get(stream_url)
        time.sleep(10)

        try:
            if choice == 2:
                driver.find_element(By.TAG_NAME, "body").click()
            close_livestream_popup()
            print("Joined live stream.")
        except Exception:
            pass

        stream_start = time.time()
        next_save_time = stream_start + 300
        next_follow_time = stream_start + 300

        while time.time() - stream_start <= max_duration:
            try:
                scrape_username(joined_users, current_batch)
            except Exception as e:
                print("Scraping error:", e)

            if time.time() >= next_save_time and current_batch:
                df = pd.concat([df, pd.DataFrame(current_batch)], ignore_index=True)
                df.to_excel(filename, index=False)
                current_batch.clear()
                print("Saved users to Excel.")
                next_save_time = time.time() + 300

            if time.time() >= next_follow_time:
                print("Processing follows...")
                follow_scraped_users(df, filename)
                next_follow_time = time.time() + 320

            time.sleep(random.uniform(5, 8))

        if choice == 1:
            break
def get_buyers_names(link):
    driver.get(link)
    time.sleep(15)
    driver.find_element(By.TAG_NAME, "body").click()
    close_livestream_popup()
    print("Joined live stream.")

    buyers_set = set()
    unchanged_count = 0

    try:
        sold_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[data-testid='show-refinement-button-sold']")
            )
        )
        sold_btn.click()
        time.sleep(10)

        while unchanged_count < 5:
            buyers = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, "//strong[@data-testid='show-buyer-details']//a/strong")
                )
            )

            new_buyers = {b.text.strip() for b in buyers if b.text.strip()}
            old_count = len(buyers_set)
            buyers_set.update(new_buyers)

            unchanged_count = unchanged_count + 1 if len(buyers_set) == old_count else 0

            print(f"Unique buyers: {len(buyers_set)} | No change: {unchanged_count}")

            if unchanged_count >= 5:
                break

            scrollable = driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-overlayscrollbars-initialize] > div[data-overlayscrollbars-contents]"
            )[1]

            for _ in range(10):
                scrollable.send_keys(Keys.PAGE_DOWN)
                scrollable.send_keys(Keys.PAGE_DOWN)
                scrollable.send_keys(Keys.PAGE_DOWN)
                scrollable.send_keys(Keys.PAGE_DOWN)
                time.sleep(1)

            time.sleep(1.2)

    except Exception:
        pass

    return list(buyers_set)
def collect_and_follow_buyers_mode():
    driver.get("https://www.whatnot.com/")

    df = pd.DataFrame(columns=["users", "status"])
    filename = f"Buyers_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    seen_users = set()

    while True:
        try:
            stream_url = get_livestreams_with_min_viewers(min_viewers)

            if not stream_url:
                print("No livestreams found")
                continue

            print(f"🎥 Joining stream: {stream_url}")
            driver.get(stream_url)
            time.sleep(10)

            try:
                driver.find_element(By.TAG_NAME, "body").click()
                close_livestream_popup()
                print("✅ Joined live stream")
            except:
                pass

            buyers = get_buyers_names(stream_url)
            print(f"Found buyers: {len(buyers)}")

            for buyer in buyers:
                if buyer not in seen_users:
                    seen_users.add(buyer)
                    df.loc[len(df)] = [buyer, "Scraped"]

            scraped = df.loc[df["status"] == "Scraped", "users"].tolist()

            if scraped:
                print(f"Following {len(scraped)} buyers...")

                main_window = driver.current_window_handle
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[-1])

                for username in scraped:
                    try:
                        driver.get(f"https://www.whatnot.com/user/{username}")
                        time.sleep(3)
                        click_follow_button(f"https://www.whatnot.com/user/{username}")
                        df.loc[df["users"] == username, "status"] = "Followed"
                        print(f"✅ Followed {username}")
                    except Exception as e:
                        print(f"Follow failed {username}: {e}")

                driver.close()
                driver.switch_to.window(main_window)

                df.to_excel(filename, index=False)
                print(f"Saved: {filename}")

            print("➡️ Moving to next livestream...")
            time.sleep(10)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)
def click_share_button():
    selectors = [
        (By.CSS_SELECTOR, "button[data-testid='show-share-button']"),
        (By.XPATH, "//button[.//strong[normalize-space()='Share']]")
    ]

    for by, selector in selectors:
        try:
            button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by, selector))
            )

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", button
            )

            try:
                button.click()
            except:
                driver.execute_script("arguments[0].click();", button)

            print("Share button clicked.")
            return True

        except:
            continue

    print("Share button not found.")
    return False
def share_live_stream_mode():
    live_stream_link = input("Enter the live stream link: ").strip()
    if not live_stream_link:
        print("No live stream link entered.")
        return

    print("Select the Excel File To Share the Live to Users")
    df = open_and_read_excel()

    if df is None or df.empty:
        print("Excel file is empty or could not be loaded.")
        return

    if not {"users", "status"}.issubset(df.columns):
        print("Excel must contain 'users' and 'status' columns.")
        return

    filename = f"Shared_users_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    total_users = len(df)

    try:
        start = int(input(f"Enter starting index (1-{total_users}): "))
        end = int(input(f"Enter ending index (1-{total_users}): "))
        delay = float(input("Enter delay between messages in seconds: "))
    except ValueError:
        print("Invalid input.")
        return

    if not (1 <= start <= end <= total_users):
        print("Invalid index range.")
        return

    if delay < 0:
        print("Delay cannot be negative.")
        return

    choice = input(
        "Send message from message.txt? Enter 1 for yes, 2 for no: "
    ).strip()

    if choice == "1":
        try:
            with open("message.txt", encoding="utf-8") as file:
                message = file.read().strip()
        except Exception as e:
            print(f"Error reading message.txt: {e}")
            return
    elif choice == "2":
        message = ""
    else:
        print("Invalid choice.")
        return

    driver.get(live_stream_link)
    time.sleep(15)
    close_livestream_popup()
    print("✅ Joined live stream")

    for index in range(start - 1, end):
        user_link = str(df.at[index, "users"]).strip()
        print(f"\nProcessing {index + 1}/{total_users}: {user_link}")

        if not user_link or user_link.lower() == "nan":
            df.at[index, "status"] = "Failed"
            continue

        try:
            username = urlparse(user_link).path.rstrip("/").split("/")[-1]

            if not username:
                df.at[index, "status"] = "Failed"
                continue
            
            if not click_share_button():
                print("Share button not found.")
                df.at[index, "status"] = "Failed"
                continue

            try:
                search_box = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//label[normalize-space()='Search users...']/preceding-sibling::input"
                    ))
                )
                search_box.clear()
                search_box.send_keys(username)
                time.sleep(1)
            except Exception as e:
                print(f"Error finding search box for {username}: {e}")
                df.at[index, "status"] = "Failed"
                continue    

            try:
                button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        f"//button[.//strong[normalize-space()='{username}']]"
                    ))
                )
                button.click()
            except Exception as e:
                print(f"User NOT FOUND: {username} . Error: {e}")
                df.at[index, "status"] = "Failed"

                driver.refresh()
                time.sleep(10)
                close_livestream_popup()
                continue
            try:
                message_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        f"//label[contains(normalize-space(), 'Message @{username}')]/following-sibling::input"
                    ))
                )

                if message:
                    message_input.send_keys(message)

                send_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[normalize-space()='Send']"
                    ))
                )
                send_button.click()

                df.at[index, "status"] = "Messaged"
                print(f"✅ Shared with {username}")
            except Exception as e:
                print(f"Error sending message to {username}: {e}")
                df.at[index, "status"] = "Failed"
                
        except Exception as e:
            print(f"❌ Failed {username}: {e}")
            df.at[index, "status"] = "Failed"

        df.to_excel(filename, index=False)

        if index < end - 1:
            time.sleep(delay)

    print(f"\n✅ Finished. Saved to {filename}")
def get_streams_data():
    streams_data = []

    while True:
        url = input("Enter URL (leave blank to finish): ").strip()

        if url == "":
            break

        streams_data.append({"link": url})

    return streams_data
def collect_bidders_and_buyers_from_specific_live_stream_mode(run_for_seconds=None):
    end_time = time.time() + run_for_seconds if run_for_seconds else None
    print("Enter the live stream URLs you want to scrape bidders and buyers from.")
    streams_data = get_streams_data()

    driver.get("https://www.whatnot.com/")

    df = pd.DataFrame(columns=["users", "bid_amount", "status"])
    filename = f"scraped_bidders_and_buyers{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    seen_users = set()
    i = 0

    while not end_time or time.time() <= end_time:
        try:
            if not streams_data:
                print("No streams found.")
                break

            stream = streams_data[i % len(streams_data)]["link"]
            i += 1

            # Get buyers
            for buyer in get_buyers_names(stream):
                if buyer not in seen_users:
                    seen_users.add(buyer)
                    df.loc[len(df)] = [buyer, 2, "Scraped"]

            # Join stream
            driver.get(stream)
            time.sleep(15)

            try:
                driver.find_element(By.TAG_NAME, "body").click()
                close_livestream_popup()
            except:
                pass

            print("Joined live stream.")
            start_time = time.time()
            last_follow_time = time.time()

            while time.time() - start_time <= 15 * 60:
                try:
                    username = None

                    try:
                        element = driver.find_element(
                            By.CSS_SELECTOR, '[data-testid="show-winning-status"]'
                        )
                        text = driver.execute_script(
                            "return arguments[0].textContent;", element
                        )
                        username = text.split()[0]
                    except:
                        pass

                    try:
                        element = driver.find_element(
                            By.CSS_SELECTOR,
                            "strong.text-right.text-balance.text-neutral-50.block.font-sans.font-semibold.tabular-nums"
                        )
                        bid = driver.execute_script(
                            "return arguments[0].textContent;", element
                        )
                        bid_amount = float(bid.replace("$", "").strip())
                    except:
                        bid_amount = 30

                    if username and bid_amount >= 2 and username not in seen_users:
                        seen_users.add(username)
                        df.loc[len(df)] = [username, bid_amount, "Scraped"]
                        print(f"Added bidder: {username}")

                except Exception as e:
                    print(f"Scraping error: {e}")

                if time.time() - last_follow_time >= 5 * 60:
                    scraped = df.loc[df["status"] == "Scraped", "users"].tolist()

                    if scraped:
                        main_window = driver.current_window_handle
                        driver.execute_script("window.open('');")
                        driver.switch_to.window(driver.window_handles[-1])

                        for username in scraped:
                            try:
                                driver.get(f"https://www.whatnot.com/user/{username}")
                                click_follow_button(f"https://www.whatnot.com/user/{username}")
                                df.loc[df["users"] == username, "status"] = "Followed"
                            except Exception as e:
                                print(f"Follow failed {username}: {e}")

                        driver.close()
                        driver.switch_to.window(main_window)

                        df.to_excel(filename, index=False)
                        print(f"Saved: {filename}")

                    last_follow_time = time.time()

        except Exception as e:
            print(f"Error: {e}")

def get_profile_urls():
    """Collect streamer profile URLs from the livestream cards on the category page."""
    profile_urls = set()
    try:
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            'section[data-testid="livestream-card"], section[data-type="LivestreamCard"]',
        )
        for card in cards:
            try:
                link = card.find_element(By.CSS_SELECTOR, 'a[href^="/user/"]')
                url = link.get_attribute("href")
                if url:
                    profile_urls.add(url)
            except Exception:
                continue
    except Exception as e:
        print("No livestream found, make sure your category in config file is correct")
        print(f"Error : {e}")
    return profile_urls


def follow_users(users):
    for u_link in users:
        try:
            driver.get(u_link)
            click_follow_button(u_link)
            time.sleep(2)
        except Exception as e:
            print(f"Error following {u_link}: {e}")


def collect_review_profile_links(max_profiles):
    """Scroll the current reviews page and return the unique user profile links found."""
    users = set()
    scroll_limit = 5
    no_change_scrolls = 0

    while len(users) < max_profiles and no_change_scrolls < scroll_limit:
        try:
            anchors = driver.find_elements(By.XPATH, '//a[starts-with(@href, "/user/")]')
            all_links = [a.get_attribute("href") for a in anchors]
            profile_links = [
                l for l in all_links
                if l and re.match(r"^https://www\.whatnot\.com/user/[^/?]+$", l)
            ]

            initial_count = len(users)
            users.update(profile_links)

            if len(users) > initial_count:
                no_change_scrolls = 0
            else:
                no_change_scrolls += 1
                time.sleep(5)

            scroll_livestream_or_review_page(20, 300, 0.5)
            print("Users Scraped:", len(users))
        except Exception as e:
            print(f"Error scraping users: {e}")
            break

    return list(users)

def follow_users_from_review_category_mode():
    review_urls_file = "scraped_review_profiles.txt"
    if not os.path.exists(review_urls_file):
        open(review_urls_file, "w", encoding="utf-8").close()

    while True:
        driver.get(review_category_url)
        time.sleep(5)

        print("Scrolling livestream page to load profiles..")
        scroll_livestream_or_review_page(times=60, step=250, delay=0.5)

        print("Scraping profile urls..")
        profile_urls = get_profile_urls()
        print(f"{len(profile_urls)} profile urls found")
        if not profile_urls:
            print("No profile urls found, make sure category in config.ini is correct. Retrying in 30s...")
            time.sleep(30)
            continue

        with open(review_urls_file, "r", encoding="utf-8") as f:
            file_urls = set(line.strip() for line in f if line.strip())

        for profile_url in profile_urls:
            review_page = profile_url.rstrip("/") + "/reviews"
            if review_page in file_urls:
                print(f"Already scraped & followed through: {review_page} . Skipping this profile")
                continue
            try:
                driver.get(review_page)
                print(f"Scraping & following users from : {review_page}")
                time.sleep(5)

                users = collect_review_profile_links(max_reviews_from_each_profile)
                if users:
                    print(f"After scraping {len(users)} users. Now following them.")
                    follow_users(users)
                else:
                    print("No review users found!")

                with open(review_urls_file, "a", encoding="utf-8") as f:
                    f.write(review_page + "\n")
                file_urls.add(review_page)
            except Exception as e:
                print(f"Error processing {review_page}: {e}")

def collect_and_follow_bidders_from_specific_livestreams_mode(run_for_seconds=None):
    end_time = time.time() + run_for_seconds if run_for_seconds else None
    #message = get_message_from_file()
    stream_data = get_streams_data()
    driver.get("https://www.whatnot.com/")

    df = pd.DataFrame(columns=["users", "bid_amount", "status"])
    filename = f"Bidders_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    seen_users = set()
    i = 0
    while True:
        try:
            if end_time and time.time() > end_time:
                break

            if stream_data:
                stream_link = stream_data[i % len(stream_data)]["link"]
                i += 1
            else:
                stream_link = None

            if not stream_link:
                continue

            driver.get(stream_link)
            time.sleep(10)
            driver.find_element(By.TAG_NAME, "body").click()
            close_livestream_popup()
            print("Joined live stream.")

            start_time = time.time()
            last_follow_time = start_time

            while time.time() - start_time < 15 * 60:
                try:
                    winning = driver.find_element(
                        By.CSS_SELECTOR, '[data-testid="show-winning-status"]'
                    )
                    text = driver.execute_script(
                        "return arguments[0].textContent;", winning
                    )
                    username = text.split()[0]

                    try:
                        bid = driver.find_element(
                            By.CSS_SELECTOR,
                            "strong.text-right.text-balance.text-neutral-50.block.font-sans.font-semibold.tabular-nums"
                        )
                        bid_amount = float(
                            driver.execute_script(
                                "return arguments[0].textContent;", bid
                            ).replace("$", "").strip()
                        )
                    except:
                        bid_amount = 5

                    if bid_amount > 2 and username not in seen_users:
                        seen_users.add(username)
                        profile_url = f"https://www.whatnot.com/user/{username}"
                        df.loc[len(df)] = [profile_url, bid_amount, "Scraped"]
                        print(f"Scraped bidder: {profile_url} - ${bid_amount}")

                except Exception as e:
                    print(f"Scraping error: {e}")
                    

                if time.time() - last_follow_time >= 5 * 60:
                    print("Follow Time..")
                    scraped_users = df.loc[
                        df["status"] == "Scraped", "users"].tolist()
                    if not scraped_users:
                        print("No users found to follow")
                        continue
                    if scraped_users:
                        main_window = driver.current_window_handle
                        driver.execute_script("window.open('');")
                        driver.switch_to.window(driver.window_handles[-1])

                        for profile_url in scraped_users:
                            try:
                                print(f"Following User: {profile_url}")
                                driver.get(profile_url)
                                click_follow_button(profile_url)
                                #send_message(message)
                                df.loc[df["users"] == profile_url, "status"] = "Followed"
                            except Exception as e:
                                print(f"Error following {profile_url}: {e}")    

                        driver.close()
                        driver.switch_to.window(main_window)
                        df.to_excel(filename, index=False)
                        print(f"Saved DF to {filename}")

                    last_follow_time = time.time()

        except Exception as e:
            print(e)

ACTIONS = {
    # Account Management
    "account-setup": (
        "Account Setup",
        run_account_setup_mode,
        "Create or update your bot configuration file, including account settings and other required options."
    ),

    # Follow & Unfollow Users
    "follow-reviews": (
        "Follow Review Users",
        scrape_and_follow_users_from_reviews_excel_file_mode,
        "Scrape users who have submitted reviews and automatically follow them."
    ),

    "follow-users": (
        "Follow Users",
        follow_users_from_excel_file_mode,
        "Read user profiles from an Excel file and follow them automatically."
    ),

    "unfollow-users": (
        "Unfollow Users",
        unfollow_users_from_excel_mode,
        "Read user profiles from an Excel file and automatically unfollow them."
    ),

    "follow-followers": (
        "Follow Profile Followers",
        scrape_users_from_follower_section_mode,
        "Scrape followers from a specific profile and follow the collected users."
    ),

    "follow-live-users": (
        "Follow Live Stream Users",
        follow_users_in_livestream_mode,
        "Collect users from live streams and follow the selected users."
    ),

    "follow-bidders": (
        "Follow Bidders",
        collect_and_follow_bidders_from_livestream_mode,
        "Collect users who place bids during live streams and follow them."
    ),

    "follow-buyers": (
        "Follow Buyers",
        collect_and_follow_buyers_mode,
        "Identify buyers from live stream activity and follow the collected users."
    ),

    "follow-joined-users": (
        "Follow Joined Users",
        scrape_and_follow_livestream_joined_users_mode,
        "Scrape users who have joined a live stream and follow them."
    ),

    "follow-multiple-profiles": (
        "Follow Multiple Profiles",
        scrape_multiple_profiles_mode,
        "Scrape users from multiple specified profiles and follow the collected users."
    ),

    "follow-bidders-buyers": (
        "Follow Bidders & Buyers",
        collect_bidders_and_buyers_from_specific_live_stream_mode,
        "Collect both bidders and buyers from a specific live stream and follow them."
    ),

    "follow-review-category": (
        "Follow Review Category Users",
        follow_users_from_review_category_mode,
        "Scrape users from a review category you specify and follow the collected users."
    ),

    "follow-specific-bidders": (
        "Follow Bidders from Specific Streams",
        collect_and_follow_bidders_from_specific_livestreams_mode,
        "Collect bidders from specific live stream URLs that you provide and follow them."
    ),

    # Messaging & Engagement
    "send-messages": (
        "Send Messages",
        message_mode,
        "Send predefined or customized messages to users."
    ),

    "share-livestream": (
        "Share Live Stream",
        share_live_stream_mode,
        "Share a specified live stream with selected users."
    ),

    # Customer Management
    "scrape-customers": (
        "Scrape Customers",
        scrape_our_customers_mode,
        "Collect customer profiles from your account or relevant activity."
    ),

    "scrape-unfollow": (
        "Scrape & Unfollow",
        scrape_and_unfollow_mode,
        "Scrape users from your following list and automatically unfollow them."
    ),

    "follow-unfollow": (
        "Follow & Unfollow Profiles",
        follow_unfollow_profile_at_same_time,
        "Follow users from one source while unfollowing users from another profile."
    ),
}


# Features that require Account Setup
SETUP_REQUIRED_FEATURES = {
    "follow-review-category",
    "follow-bidders",
    "share-livestream",
    "follow-bidders",
    "follow_buyers",
    "follow-specific-bidders",
    "follow-bidders-buyers",
    "follow-joined-users",
    "follow-live-users",
}

driver = None
# --------------------------------------------------------------------------
# Token storage
# --------------------------------------------------------------------------
def load_token():
    try:
        return json.loads(TOKEN_FILE.read_text())["access_token"]
    except (OSError, ValueError, KeyError):
        return None


def save_token(access_token, expires_at):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({"access_token": access_token, "expires_at": expires_at}))
    try:
        TOKEN_FILE.chmod(0o600)  # owner-only (no effect on Windows)
    except OSError:
        pass


def clear_token():
    try:
        TOKEN_FILE.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# Talking to ToolsHive
# --------------------------------------------------------------------------
def sign_in():
    """Open the browser, let the user approve, then collect the token."""
    start = requests.post(
        f"{BASE_URL}/api/v1/device/start/",
        json={"device_name": platform.node()},
        timeout=TIMEOUT,
    )
    start.raise_for_status()
    info = start.json()

    print("\nYour browser will open so you can sign in to ToolsHive.")
    print(f"Check that this code matches: {info['user_code']}")
    print(f"If the browser doesn't open, go to: {info['verification_url']}\n")
    webbrowser.open(info["verification_url"])

    deadline = time.time() + info["expires_in"]
    interval = info["interval"]

    while time.time() < deadline:
        time.sleep(interval)
        response = requests.post(
            f"{BASE_URL}/api/v1/device/token/",
            json={"device_code": info["device_code"]},
            timeout=TIMEOUT,
        )
        if response.status_code == 202:      # still waiting for the user
            continue
        if response.status_code == 429:      # polling too fast
            interval += 5
            continue
        if response.status_code == 200:
            data = response.json()
            save_token(data["access_token"], data["expires_at"])
            print(f"Signed in as {data['user']['email']}.")
            return data["access_token"]

        print("Sign-in failed:", response.json().get("message") or response.json().get("error"))
        return None

    print("Sign-in timed out. Please run the app again.")
    return None


def fetch_features(token):
    """Returns the list of features, or None if the token is missing/expired/invalid."""
    response = requests.get(
        f"{BASE_URL}/api/v1/features/",
        params={"product": PRODUCT_SLUG},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    if response.status_code == 401:
        return None
    response.raise_for_status()
    return response.json()["features"]


def get_features():
    token = load_token()
    #print(f"Loaded token: {token[:8]}...") if token else print("No token found.")
    features = fetch_features(token) if token else None

    if features is None:          # no token yet, or it expired -> sign in again via the browser
        clear_token()
        token = sign_in()
        if not token:
            sys.exit(1)
        features = fetch_features(token)

    return features or []


# --------------------------------------------------------------------------
# The menu
# --------------------------------------------------------------------------
def main():
    global driver
    try:
        features = get_features()
        
        # print(f"Fetched {len(features)} features from ToolsHive.")
        # print(features)
    except requests.RequestException as exc:
        print("Could not reach ToolsHive:", exc)
        sys.exit(1)


    # owned_keys = {f["key"] for f in features}
    owned_keys = {f["key"] for f in features}

    # Get user's available features (excluding account setup)
    available = [
        (key, *ACTIONS[key])
        for key in ACTIONS
        if key in owned_keys and key != "account-setup"
    ]

    # Check whether any owned feature requires account setup
    needs_setup = bool(owned_keys & SETUP_REQUIRED_FEATURES)

    # Automatically add Account Setup as the first mode
    if needs_setup:
        available.insert(0, ("account-setup", *ACTIONS["account-setup"]))

    # Display available features
    if available:

        available_keys = {key for key, *_ in available}

        if "follow-multiple-profiles" in available_keys:
            create_excel_if_not_exists(filename="multiple_profiles_urls_for_scraping.xlsx")
        if "account-setup" in available_keys:
            create_config_if_not_exists(filename="config.ini")
        if "follow-reviews" in available_keys:
            create_reviews_excel_if_not_exists(filename="reviews_profiles_url_for_scraping.xlsx")


        # print(
        #     f"Available features: {', '.join(key for key, _label, _fn, _description in available)}"
        # )
    else:
        print("No features available yet.")
        return
    
    driver = switch_browser()
    
    while True:
        print("\nChoose a mode:")
        for number, (_key, label, _fn, description) in enumerate(available, start=1):
            print(f"{number:2}. {label}")
            print(f"    - {description}")
        print("  0. Exit")

        choice = input("> ").strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            available[int(choice) - 1][2]()
        else:
            print("Please enter one of the numbers above.")


if __name__ == "__main__":
    main()
